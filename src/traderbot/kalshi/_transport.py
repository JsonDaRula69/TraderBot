from __future__ import annotations

import logging
import random
from types import TracebackType
from typing import Literal, Self, override
from urllib.parse import urlparse

import anyio
import httpx
from pydantic import SecretStr, ValidationError

from traderbot.kalshi.errors import (
    AuthenticationError,
    ConfigurationError,
    ErrorPayload,
    KalshiAPIError,
    KalshiError,
    RateLimitError,
    RetryExhaustedError,
)
from traderbot.kalshi.historical import KalshiHistoricalMethods, QueryParams
from traderbot.kalshi.pinning import create_pinned_ssl_context, trusted_pins_for
from traderbot.kalshi.public_paths import is_public_path
from traderbot.kalshi.rate_limit import TokenBucketRateLimiter
from traderbot.kalshi.signing import auth_headers

logger = logging.getLogger(__name__)

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type QueryParamValue = str | int | float | bool | None
type Environment = Literal["production", "demo"]
KALSHI_ENVIRONMENTS: tuple[Environment, ...] = ("production", "demo")

_BASE_URLS: dict[Environment, str] = {
    "production": "https://external-api.kalshi.com/trade-api/v2",
    "demo": "https://external-api.demo.kalshi.co/trade-api/v2",
}


class KalshiTransport(KalshiHistoricalMethods):
    def __init__(
        self,
        api_key: str | None = None,
        private_key_pem: str | None = None,
        *,
        environment: Environment = "production",
        base_url: str | None = None,
        read_budget_tokens: float = 200.0,
        write_budget_tokens: float = 100.0,
        read_burst_capacity: float = 200.0,
        write_burst_capacity: float = 100.0,
        endpoint_cost: float = 10.0,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        super().__init__()
        self._api_key: SecretStr | None = SecretStr(api_key) if api_key is not None else None
        self._private_key_pem: SecretStr | None = (
            SecretStr(private_key_pem) if private_key_pem is not None else None
        )
        resolved_base_url = base_url or _BASE_URLS.get(environment)
        if resolved_base_url is None:
            raise ConfigurationError(
                f"Unknown Kalshi environment {environment!r}; expected one of {sorted(_BASE_URLS)}"
            )
        if endpoint_cost <= 0:
            raise ConfigurationError(f"endpoint_cost must be > 0, got {endpoint_cost}")
        self._base_url: str = resolved_base_url
        self._environment: Environment = environment
        self._endpoint_cost: float = endpoint_cost
        self._max_retries: int = max_retries
        self._retry_base_delay: float = retry_base_delay
        self._read_limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(
            tokens_per_second=read_budget_tokens / endpoint_cost,
            burst_capacity=int(read_burst_capacity / endpoint_cost),
        )
        self._write_limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(
            tokens_per_second=write_budget_tokens / endpoint_cost,
            burst_capacity=int(write_burst_capacity / endpoint_cost),
        )
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            verify=create_pinned_ssl_context(trusted_pins_for(environment)),
        )

    @staticmethod
    def _full_api_path(base_url: str, relative_path: str) -> str:
        return urlparse(base_url).path.rstrip("/") + "/" + relative_path.lstrip("/")

    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        if self._api_key is None or self._private_key_pem is None:
            raise ConfigurationError(
                "Authenticated Kalshi endpoint requires api_key and private_key_pem"
            )
        return auth_headers(
            self._api_key.get_secret_value(),
            self._private_key_pem.get_secret_value(),
            method,
            self._full_api_path(self._base_url, path),
        )

    def _headers_for(self, method: str, path: str) -> dict[str, str]:
        if is_public_path(path):
            return {}
        return self._build_auth_headers(method, path)

    @staticmethod
    def _error_from_response(response: httpx.Response) -> KalshiError | None:
        if response.is_success:
            return None
        try:
            payload = ErrorPayload.model_validate_json(response.content)
        except ValidationError:
            payload = ErrorPayload()
        status_code = response.status_code
        path = response.request.url.path
        if status_code == 429:
            message = (
                f"Kalshi rate limit exceeded on {response.request.method} {path} "
                + f"({payload.message or payload.code})"
            )
            return RateLimitError(message)
        if status_code in (401, 403):
            message = (
                f"Kalshi authentication failed (HTTP {status_code}) on "
                + f"{response.request.method} {path}: {payload.code or payload.message}"
            )
            return AuthenticationError(message)
        retryable = status_code >= 500
        kind = "server error" if retryable else "API error"
        message = (
            f"Kalshi {kind} (HTTP {status_code}) on {response.request.method} {path}: "
            + f"{payload.message or payload.code}"
        )
        return KalshiAPIError(
            message,
            code=payload.code,
            details=payload.details,
            status_code=status_code,
            path=path,
            retryable=retryable,
        )

    async def _request(
        self,
        method: str,
        path: str,
        timeout: float = 30.0,
        *,
        query_params: QueryParams | None = None,
        body: JsonValue | None = None,
    ) -> httpx.Response:
        headers = self._headers_for(method, path)
        is_read = method.upper() in ("GET", "DELETE")
        rate_limiter = self._read_limiter if is_read else self._write_limiter
        last_error: httpx.HTTPError | KalshiError | None = None
        for attempt in range(self._max_retries + 1):
            await rate_limiter.acquire()
            try:
                if is_read:
                    response = await self._client.request(
                        method, path, params=query_params, headers=headers, timeout=timeout
                    )
                else:
                    response = await self._client.request(
                        method, path, json=body, headers=headers, timeout=timeout
                    )
            except httpx.HTTPError as error:
                logger.warning("HTTP error on %s %s: %s", method, path, error)
                last_error = error
            else:
                error = self._error_from_response(response)
                if error is None:
                    return response
                if not error.retryable:
                    raise error
                last_error = error
            if attempt < self._max_retries:
                delay = self._retry_base_delay * 2.0**attempt + random.uniform(0, 0.5)
                await anyio.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RetryExhaustedError("Max retries exceeded")

    @override
    async def get(
        self,
        path: str,
        timeout: float = 30.0,
        *,
        query_params: QueryParams | None = None,
        **params: QueryParamValue,
    ) -> httpx.Response:
        resolved_params = params if query_params is None else query_params
        return await self._request("GET", path, timeout=timeout, query_params=resolved_params)

    async def post(self, path: str, timeout: float = 30.0, **body: JsonValue) -> httpx.Response:
        return await self._request("POST", path, timeout=timeout, body=body)

    async def delete(
        self, path: str, timeout: float = 30.0, **params: QueryParamValue
    ) -> httpx.Response:
        return await self._request("DELETE", path, timeout=timeout, query_params=params)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
