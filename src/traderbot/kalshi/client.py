"""Kalshi REST API client — v2, RSA-PSS auth, TLS pinning, rate limiting.

Ported from ``.trash/src/traderbot/kalshi/client.py`` (retired v1 client)
and modernized for the Phase 2 stack:

* Credentials are constructor arguments (``api_key`` / ``private_key_pem``),
  sourced by callers from :class:`traderbot.secrets.store.SecretsStore`.
  No ``pydantic_settings`` / ``BaseSettings`` / env files.
* ``environment="production" | "demo"`` selects the base URL:
  ``https://external-api.kalshi.com/trade-api/v2`` vs
  ``https://external-api.demo.kalshi.co/trade-api/v2``.
* ``httpx.AsyncClient`` with the pinned TLS context
  (:func:`traderbot.kalshi.pinning.create_pinned_ssl_context`).
* Token-bucket rate limiting (tier budgets, default cost 10 tokens/request).
* Kalshi 429 responses carry no ``Retry-After`` header — retries use
  exponential backoff + jitter only.
* Error responses branch on the ``code`` field. The ``service`` field was
  removed from error bodies on 2026-08-06 and is never read.
* Requests are signed with the full path from the API root (``/trade-api/v2/...``),
  without query parameters (see :meth:`KalshiClient._full_api_path`).

Only v2 API paths (``/trade-api/v2/*``) are used. The deprecated v1
``/portfolio/orders`` mutation endpoints are not supported.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal, Self, cast
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from traderbot.kalshi.pinning import create_pinned_ssl_context, trusted_pins_for
from traderbot.kalshi.rate_limit import TokenBucketRateLimiter
from traderbot.kalshi.signing import auth_headers

logger = logging.getLogger(__name__)

# Recursive JSON value types (matches ``traderbot.mcp.tools``) — used to
# type HTTP params/bodies and parsed error payloads without ``Any``.
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

# Flat primitive values accepted as URL query parameters (httpx
# ``PrimitiveData``); query strings cannot carry nested JSON.
type QueryParamValue = str | int | float | bool | None

# Current recommended REST base URLs (docs.kalshi.com — "API Environments and Endpoints").
_BASE_URLS: dict[str, str] = {
    "production": "https://external-api.kalshi.com/trade-api/v2",
    "demo": "https://external-api.demo.kalshi.co/trade-api/v2",
}

Environment = Literal["production", "demo"]

# Public Kalshi endpoints that don't require authentication. Per
# docs.kalshi.com: /markets, /events, /series, /exchange/status are public —
# auth headers are optional there.
_PUBLIC_ENDPOINTS: frozenset[str] = frozenset(
    {
        "/exchange/status",
        "/markets",
        "/markets/trades",
        "/markets/{ticker}",
        "/markets/{ticker}/orderbook",
        "/markets/{ticker}/candlesticks",
        "/markets/orderbooks",
        "/events",
        "/events/{event_ticker}",
        "/events/{event_ticker}/candlesticks",
        "/events/{event_ticker}/metadata",
        "/events/multivariate",
        "/series",
        "/series/{ticker}",
        "/multivariate/event-collections",
        "/multivariate/event-collections/{ticker}",
    }
)


class KalshiError(Exception):
    """Base class for all Kalshi client errors.

    ``retryable`` marks errors that are safe to retry with backoff (429
    rate limits and 5xx server errors). Non-retryable errors (auth, client
    errors) are raised immediately.
    """

    message: str
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(KalshiError):
    """Invalid client configuration (missing credentials, unknown environment)."""


class AuthenticationError(KalshiError):
    """Kalshi rejected the request credentials (HTTP 401/403)."""


class RateLimitError(KalshiError):
    """Kalshi rate limit exceeded (HTTP 429).

    Kalshi 429 responses do not include a ``Retry-After`` header, so the
    client retries with exponential backoff only.
    """

    retryable: bool = True


class KalshiAPIError(KalshiError):
    """Kalshi error response.

    Branch on :attr:`code` — the ``service`` field was removed from error
    response bodies on 2026-08-06 and is not read.
    """

    code: str
    details: str
    status_code: int
    path: str
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: str,
        status_code: int,
        path: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.status_code = status_code
        self.path = path
        self.retryable = retryable


class KalshiClient:
    """Async Kalshi REST client with RSA-PSS auth, retries, and rate limiting.

    Args:
        api_key: Kalshi API key (access key ID). Fetch from
            ``SecretsStore.get(service="kalshi", key="api_key")``.
        private_key_pem: PEM-encoded RSA private key used to sign requests.
            Fetch from ``SecretsStore.get(service="kalshi", key="private_key_pem")``.
        environment: ``"production"`` or ``"demo"`` — selects the base URL.
        base_url: Optional explicit base URL override (e.g. for tests or a
            proxy). Takes precedence over ``environment``.
        read_budget_tokens: Per-second read token budget for the configured
            tier (Basic 200 … Prestige 6000 per docs.kalshi.com).
        write_budget_tokens: Per-second write token budget (Basic 100 …
            Prestige 8000).
        read_burst_capacity: Read bucket capacity in tokens (default: budget,
            i.e. one second of budget).
        write_burst_capacity: Write bucket capacity in tokens.
        endpoint_cost: Token cost per request (default 10; non-default costs
            come from ``GET /account/endpoint_costs``).
        max_retries: Retry count for rate-limited and 5xx responses.
        retry_base_delay: Base delay (seconds) for exponential backoff.

    Note:
        Credentials are optional only if every requested path is a public
        endpoint (e.g. ``/markets``). Authenticated endpoints raise
        :class:`ConfigurationError` when credentials are missing.
    """

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
        self._api_key: SecretStr | None = SecretStr(api_key) if api_key is not None else None
        self._private_key_pem: SecretStr | None = (
            SecretStr(private_key_pem) if private_key_pem is not None else None
        )

        resolved_base_url = base_url or _BASE_URLS.get(environment)
        if resolved_base_url is None:
            raise ConfigurationError(
                f"Unknown Kalshi environment {environment!r}; expected one of "
                + f"{sorted(_BASE_URLS)}"
            )
        self._base_url: str = resolved_base_url
        self._environment: Environment = environment

        if endpoint_cost <= 0:
            raise ConfigurationError(f"endpoint_cost must be > 0, got {endpoint_cost}")
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
        """Compute the full API-relative path from a base URL and relative path.

        Kalshi requires signing the full path from the API root (e.g.
        ``/trade-api/v2/portfolio/balance``), not the client-relative path
        (``/portfolio/balance``). See docs.kalshi.com: "Sign the full request
        path from the API root, without query parameters."
        """
        return urlparse(base_url).path.rstrip("/") + "/" + relative_path.lstrip("/")

    @staticmethod
    def _is_public_path(path: str) -> bool:
        """Check if a relative path matches a public (unauthenticated) endpoint.

        Handles path parameters by normalizing variable segments to ``{param}``.
        """
        if path in _PUBLIC_ENDPOINTS:
            return True
        segments = path.strip("/").split("/")
        for public in _PUBLIC_ENDPOINTS:
            pub_segs = public.strip("/").split("/")
            if len(segments) != len(pub_segs):
                continue
            match = True
            for s, p in zip(segments, pub_segs, strict=False):
                if p.startswith("{") and p.endswith("}"):
                    continue
                if s != p:
                    match = False
                    break
            if match:
                return True
        return False

    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Generate signed Kalshi auth headers for ``method`` + client path."""
        if self._api_key is None or self._private_key_pem is None:
            raise ConfigurationError(
                "Authenticated Kalshi endpoint requires api_key and private_key_pem; "
                + "pass both to KalshiClient (e.g. from SecretsStore)."
            )
        full_path = self._full_api_path(self._base_url, path)
        return auth_headers(
            self._api_key.get_secret_value(),
            self._private_key_pem.get_secret_value(),
            method,
            full_path,
        )

    def _headers_for(self, method: str, path: str) -> dict[str, str]:
        """Return request headers: signed auth for private paths, empty for public."""
        if self._is_public_path(path):
            if self._api_key is None or self._private_key_pem is None:
                return {}
            logger.debug("Signing public endpoint %s (credentials available)", path)
            return self._build_auth_headers(method, path)
        return self._build_auth_headers(method, path)

    @staticmethod
    def _error_from_response(response: httpx.Response) -> KalshiError | None:
        """Classify a non-2xx response into a :class:`KalshiError`, or ``None`` for 2xx.

        Branches on the ``code`` field of the JSON error body (the ``service``
        field was removed from error responses on 2026-08-06). 429 and 5xx are
        retryable; 401/403 and other 4xx are raised immediately.
        """
        if response.is_success:
            return None

        status_code = response.status_code
        path = response.request.url.path
        code = ""
        message = ""
        details = ""
        try:
            parsed = cast(JsonValue, response.json())
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            code = str(parsed.get("code", ""))
            message = str(parsed.get("message", ""))
            details = str(parsed.get("details", ""))

        if status_code == 429:
            return RateLimitError(
                f"Kalshi rate limit exceeded on {response.request.method} {path}"
                + f" ({message or code})"
            )
        if status_code in (401, 403):
            return AuthenticationError(
                f"Kalshi authentication failed (HTTP {status_code}) on "
                + f"{response.request.method} {path}: {code or message}"
            )
        if status_code >= 500:
            return KalshiAPIError(
                f"Kalshi server error (HTTP {status_code}) on "
                + f"{response.request.method} {path}: {message or code}",
                code=code,
                details=details,
                status_code=status_code,
                path=path,
                retryable=True,
            )
        return KalshiAPIError(
            f"Kalshi API error (HTTP {status_code}) on "
            + f"{response.request.method} {path}: {code or message}",
            code=code,
            details=details,
            status_code=status_code,
            path=path,
            retryable=False,
        )

    async def _request(
        self,
        method: str,
        path: str,
        timeout: float = 30.0,
        *,
        query_params: dict[str, QueryParamValue] | None = None,
        body: JsonValue | None = None,
    ) -> httpx.Response:
        """Core request handler with rate limiting, retry, and RSA-PSS auth.

        Acquires the rate-limit token, injects signed auth headers for
        authenticated endpoints, and retries rate-limited (429) and 5xx
        responses with exponential backoff + jitter. Kalshi 429 responses do
        not include ``Retry-After``, so backoff is purely time-based.
        """
        headers = self._headers_for(method, path)
        is_read = method.upper() in ("GET", "DELETE")
        rate_limiter = self._read_limiter if is_read else self._write_limiter

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await rate_limiter.acquire()
            logger.debug(
                "Request %s %s (attempt %d/%d)",
                method,
                path,
                attempt + 1,
                self._max_retries + 1,
            )
            try:
                if is_read:
                    response = await self._client.request(
                        method, path, params=query_params, headers=headers, timeout=timeout
                    )
                else:
                    response = await self._client.request(
                        method, path, json=body, headers=headers, timeout=timeout
                    )
            except httpx.HTTPError as exc:
                logger.warning("HTTP error on %s %s: %s", method, path, exc)
                last_exc = exc
            else:
                error = self._error_from_response(response)
                if error is None:
                    logger.debug("API %s %s -> %d", method, path, response.status_code)
                    return response
                if not error.retryable:
                    raise error
                logger.warning("%s on %s %s: %s", type(error).__name__, method, path, error)
                last_exc = error

            if attempt >= self._max_retries:
                break
            delay: float = self._retry_base_delay * 2.0**attempt + random.uniform(0, 0.5)
            logger.debug("Retrying %s %s in %.2fs (attempt %d)", method, path, delay, attempt + 1)
            await asyncio.sleep(delay)

        logger.error("Max retries exceeded for %s %s", method, path)
        if last_exc is not None:
            raise last_exc
        msg = "Max retries exceeded"
        raise RuntimeError(msg)

    async def get(
        self, path: str, timeout: float = 30.0, **params: QueryParamValue
    ) -> httpx.Response:
        return await self._request("GET", path, timeout=timeout, query_params=params)

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
        exc_tb: object,
    ) -> None:
        await self.close()
