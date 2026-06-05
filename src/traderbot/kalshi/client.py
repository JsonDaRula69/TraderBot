"""Kalshi API client with RSA-PSS auth, retry, rate limiting, and type normalization."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from traderbot.kalshi.models import MarketListResponse, TradeListResponse
from traderbot.kalshi.pinning import create_pinned_ssl_context
from traderbot.kalshi.rate_limit import TokenBucketRateLimiter
from traderbot.kalshi.signing import auth_headers

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""


class RateLimitError(Exception):
    """Raised when the Kalshi API returns HTTP 429 (rate limit exceeded)."""


class AuthenticationError(Exception):
    """Raised when the Kalshi API returns an authentication failure (401/403)."""


class KalshiConfig(BaseSettings):
    """Configuration for Kalshi API client, loaded from environment variables."""

    model_config = SettingsConfigDict(
        strict=True,
        extra="ignore",
        env_prefix="KALSHI_",
        env_file=str(Path.home() / ".traderbot" / ".env"),
        env_file_encoding="utf-8",
    )

    api_key: SecretStr
    private_key_pem: SecretStr | None = None
    private_key_path: Path | None = None
    base_url: str = "https://external-api.kalshi.com/trade-api/v2"
    rate_limit_rps: float = (
        200.0  # token refill rate from Kalshi /account/limits; default 200 at tier
    )
    endpoint_cost: int = 10  # default token cost per request; see /account/endpoint_costs
    max_retries: int = 3
    retry_base_delay: float = 1.0

    def resolve_private_key(self) -> str:
        if self.private_key_path is not None:
            try:
                return self.private_key_path.read_text()
            except (FileNotFoundError, OSError):
                # The stored path may reference the host filesystem (e.g.
                # KALSHI_PRIVATE_KEY_PATH=/home/user/.traderbot/kalshi_key.pem)
                # which doesn't exist inside a sandbox container. Fall back
                # to the data directory using the filename only.
                from traderbot.paths import get_data_dir

                alt = get_data_dir() / self.private_key_path.name
                if alt.exists():
                    return alt.read_text()
                raise
        if self.private_key_pem is not None:
            return self.private_key_pem.get_secret_value()
        raise ConfigurationError(
            "No private key configured. Set KALSHI_PRIVATE_KEY_PEM or KALSHI_PRIVATE_KEY_PATH."
        )


# Fields where Kalshi returns strings that must be converted to int cents.
_INT_CENTS_FIELDS: frozenset[str] = frozenset({"price", "avg_price"})
# Fields holding Unix timestamps that must become datetime.
_TIMESTAMP_FIELDS: frozenset[str] = frozenset({"close_time", "timestamp", "created_time"})
# Top-level list-wrapper response models keyed by the list field name.
_LIST_WRAPPERS: dict[str, type[BaseModel]] = {
    "markets": MarketListResponse,
    "trades": TradeListResponse,
}


def _normalize_api_response(data: dict[str, Any], model_class: type[BaseModel]) -> BaseModel:
    """Convert raw Kalshi API dicts into validated Pydantic models.

    Handles three type mismatches common in Kalshi responses:
    1. Price fields arrive as strings ("55") — converted to int cents.
    2. Timestamp fields arrive as Unix ints — converted to datetime.
    3. outcome_prices are already correct as list[str] — passed through.
    """
    normalized = _deep_normalize(data)
    return model_class.model_validate(normalized)


def _deep_normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key in _INT_CENTS_FIELDS and isinstance(value, str):
                result[key] = int(value)
            elif key in _TIMESTAMP_FIELDS and isinstance(value, int):
                result[key] = datetime.fromtimestamp(value, tz=UTC)
            else:
                result[key] = _deep_normalize(value)
        return result
    if isinstance(obj, list):
        return [_deep_normalize(item) for item in obj]
    return obj


class KalshiClient:
    """Async Kalshi API client with RSA-PSS auth, retries, rate limiting, and normalization."""

    def __init__(
        self,
        config: KalshiConfig | None = None,
        profile: TradingProfile | None = None,
    ) -> None:
        """Initialize KalshiClient with optional profile-aware configuration.

        Args:
            config: KalshiConfig to use (if None, loads from env vars or profile)
            profile: TradingProfile to use for credentials (optional)

        Note:
            If both config and profile are None, attempts to load from KALSHI_* env vars.
            If profile is provided but config is None, uses profile credentials.
            If config is provided, profile is ignored (explicit config takes precedence).
        """
        if config is None:
            if profile is not None:
                from traderbot.profiles.config import resolve_kalshi_credentials

                api_key, private_key_pem = resolve_kalshi_credentials(profile)
                config = KalshiConfig(
                    api_key=SecretStr(api_key),
                    private_key_pem=SecretStr(private_key_pem) if private_key_pem else None,
                )
            else:
                config = KalshiConfig()  # type: ignore[call-arg]

        self._config = config
        effective_rps = config.rate_limit_rps / config.endpoint_cost
        self._rate_limiter = TokenBucketRateLimiter(tokens_per_second=effective_rps)
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            verify=create_pinned_ssl_context(),
        )

    @staticmethod
    def _full_api_path(base_url: str, relative_path: str) -> str:
        """Compute the full API-relative path from a base URL and relative path.

        Kalshi requires signing the full path from the API root (e.g.
        ``/trade-api/v2/portfolio/balance``), not the client-relative path
        (``/portfolio/balance``). See Kalshi docs: "Sign the full request
        path from the API root."
        """
        return urlparse(base_url).path.rstrip("/") + "/" + relative_path.lstrip("/")

    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        full_path = self._full_api_path(self._config.base_url, path)
        return auth_headers(
            self._config.api_key.get_secret_value(),
            self._config.resolve_private_key(),
            method,
            full_path,
        )

    async def _request(
        self,
        method: str,
        path: str,
        timeout: float = 30,
        **params: Any,
    ) -> httpx.Response:
        """Core request handler with rate limiting, retry, and RSA-PSS auth.

        Acquires the rate-limit semaphore, injects signed auth headers,
        and retries with exponential backoff + jitter on transient errors.
        """
        headers = self._build_auth_headers(method, path)

        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            await self._rate_limiter.acquire()
            logger.debug(
                "Request %s %s (attempt %d/%d)",
                method,
                path,
                attempt + 1,
                self._config.max_retries + 1,
            )
            try:
                if method.upper() in ("GET", "DELETE"):
                    response = await self._client.request(
                        method, path, params=params, headers=headers, timeout=timeout
                    )
                else:
                    response = await self._client.request(
                        method, path, json=params, headers=headers, timeout=timeout
                    )

                logger.info("API %s %s -> %d", method, path, response.status_code)

                if response.status_code == 429:
                    logger.warning("Rate limit exceeded on %s %s", method, path)
                    raise RateLimitError(f"Rate limit exceeded: {path}")

                if response.status_code in (401, 403):
                    logger.error(
                        "Auth failure on %s %s: HTTP %d", method, path, response.status_code
                    )
                    raise AuthenticationError(
                        f"Auth failure on {path}: HTTP {response.status_code}"
                    )

                if response.status_code >= 500:
                    logger.warning("Server error %d on %s %s", response.status_code, method, path)
                    last_exc = httpx.HTTPStatusError(
                        f"Server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                else:
                    return response

            except (RateLimitError, AuthenticationError):
                raise
            except httpx.HTTPError as exc:
                logger.warning("HTTP error on %s %s: %s", method, path, exc)
                last_exc = exc

            if attempt < self._config.max_retries:
                delay = self._config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)
                logger.debug(
                    "Retrying %s %s in %.2fs (attempt %d)", method, path, delay, attempt + 1
                )
                await asyncio.sleep(delay)

        logger.error("Max retries exceeded for %s %s", method, path)
        if last_exc is not None:
            raise last_exc
        msg = "Max retries exceeded"
        raise RuntimeError(msg)

    async def get(self, path: str, timeout: float = 30, **params: Any) -> httpx.Response:
        return await self._request("GET", path, timeout=timeout, **params)

    async def post(self, path: str, timeout: float = 30, **body: Any) -> httpx.Response:
        return await self._request("POST", path, timeout=timeout, **body)

    async def delete(self, path: str, timeout: float = 30, **params: Any) -> httpx.Response:
        return await self._request("DELETE", path, timeout=timeout, **params)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> KalshiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
