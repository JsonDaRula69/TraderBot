"""Kalshi API client with RSA-PSS auth, retry, rate limiting, and type normalization."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — needed at runtime by Pydantic BaseSettings
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from traderbot.kalshi.models import AccountLimits, MarketListResponse, TradeListResponse
from traderbot.kalshi._normalize import _parse_datetime, _to_cents, _to_count

logger = logging.getLogger(__name__)
from traderbot.kalshi.rate_limit import TokenBucketRateLimiter
from traderbot.kalshi.signing import auth_headers

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile


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
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    demo_url: str = "https://demo-api.kalshi.co/trade-api/v2"
    demo_mode: bool = False
    rate_limit_rps: float = 20.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @property
    def active_url(self) -> str:
        return self.demo_url if self.demo_mode else self.base_url

    def resolve_private_key(self) -> str:
        """Resolve private key PEM: direct → file → env → raise."""
        if self.private_key_pem is not None:
            return self.private_key_pem.get_secret_value()
        if self.private_key_path is not None:
            return self.private_key_path.read_text()
        if not self.demo_mode:
            raise ConfigurationError(
                "No private key configured. Set KALSHI_PRIVATE_KEY_PEM or KALSHI_PRIVATE_KEY_PATH."
            )
        return ""


# Fields where Kalshi returns strings that must be converted to int cents.
_INT_CENTS_FIELDS: frozenset[str] = frozenset({"price", "avg_price"})
# V2 dollar-denominated fields that must be converted to cents.
_V2_DOLLAR_CENTS_FIELDS: frozenset[str] = frozenset({
    "last_price_dollars", "yes_bid_dollars", "yes_ask_dollars",
    "no_bid_dollars", "no_ask_dollars", "price_dollars",
    "avg_price_dollars", "yes_price_dollars", "no_price_dollars",
})
# V2 FixedPointCount fields that must be rounded to int.
_V2_COUNT_FP_FIELDS: frozenset[str] = frozenset({
    "volume_fp", "open_interest_fp", "count_fp", "initial_count_fp",
    "fill_count_fp", "remaining_count_fp", "quantity_fp",
})
# Fields holding Unix timestamps that must become datetime.
_TIMESTAMP_FIELDS: frozenset[str] = frozenset({"close_time", "timestamp", "created_time"})
# Top-level list-wrapper response models keyed by the list field name.
_LIST_WRAPPERS: dict[str, type[BaseModel]] = {
    "markets": MarketListResponse,
    "trades": TradeListResponse,
}


def _normalize_api_response(data: dict[str, Any], model_class: type[BaseModel]) -> BaseModel:
    """Convert raw Kalshi API dicts into validated Pydantic models.

    Handles two type mismatches common in Kalshi responses:
    1. Price fields arrive as strings ("55") — converted to int cents.
    2. Timestamp fields arrive as Unix ints — converted to datetime.
    """
    normalized = _deep_normalize(data)
    return model_class.model_validate(normalized)


def _deep_normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key in _INT_CENTS_FIELDS and isinstance(value, str):
                result[key] = int(value)
            elif key in _V2_DOLLAR_CENTS_FIELDS:
                new_key = key.replace("_dollars", "_cents").replace("price_cents", "price_cents")
                result[new_key] = _to_cents(value) if isinstance(value, (str, int, float)) else value
            elif key in _V2_COUNT_FP_FIELDS:
                result[key] = _to_count(value) if isinstance(value, (str, int, float)) else value
            elif key in _TIMESTAMP_FIELDS:
                if isinstance(value, int):
                    result[key] = datetime.fromtimestamp(value, tz=UTC)
                elif isinstance(value, str):
                    result[key] = _parse_datetime(value) or value
                else:
                    result[key] = value
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
            profile: TradingProfile to use for credentials and demo mode (optional)

        Note:
            If both config and profile are None, attempts to load from KALSHI_* env vars.
            If profile is provided but config is None, uses profile credentials and demo mode.
            If config is provided, profile is ignored (explicit config takes precedence).
        """
        if config is None:
            if profile is not None:
                from traderbot.profiles.config import resolve_kalshi_credentials

                api_key, private_key_pem = resolve_kalshi_credentials(profile)
                config = KalshiConfig(
                    api_key=SecretStr(api_key),
                    private_key_pem=SecretStr(private_key_pem) if private_key_pem else None,
                    demo_mode=profile.demo_mode,
                )
            else:
                config = KalshiConfig()  # type: ignore[call-arg]

        self._config = config
        if self._config.rate_limit_rps == 0 and not self._config.demo_mode:
            self._rate_limiter = TokenBucketRateLimiter(tokens_per_second=20.0)
            self._tier_detected = False
        elif self._config.rate_limit_rps == 0 and self._config.demo_mode:
            self._rate_limiter = TokenBucketRateLimiter(tokens_per_second=20.0)
            self._tier_detected = True
        else:
            self._rate_limiter = TokenBucketRateLimiter(tokens_per_second=self._config.rate_limit_rps)
            self._tier_detected = True
        self._client = httpx.AsyncClient(base_url=self._config.active_url)

    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Build authentication headers including RSA-PSS signature."""
        api_key = self._config.api_key.get_secret_value() if self._config.api_key else ""
        private_key = self._config.resolve_private_key()
        if not private_key:
            return {"Content-Type": "application/json", "KALSHI-ACCESS-KEY": api_key} if api_key else {"Content-Type": "application/json"}
        from urllib.parse import urlparse
        prefix = urlparse(self._config.active_url).path.rstrip("/")
        sign_path = f"{prefix}{path}"
        pem_str = private_key.get_secret_value() if isinstance(private_key, SecretStr) else private_key
        return auth_headers(api_key, pem_str, method, sign_path)

    async def _request(
        self,
        method: str,
        path: str,
        **params: Any,
    ) -> httpx.Response:
        """Core request handler with rate limiting, retry, and RSA-PSS auth."""
        if not self._tier_detected and not self._config.demo_mode:
            await self._detect_tier()
        headers = self._build_auth_headers(method, path)

        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                if method.upper() in ("GET", "DELETE"):
                    response = await self._client.request(
                        method, path, params=params, headers=headers
                    )
                else:
                    response = await self._client.request(
                        method, path, json=params, headers=headers
                    )

                if response.status_code == 429:
                    raise RateLimitError(f"Rate limit exceeded: {path}")

                if response.status_code in (401, 403):
                    raise AuthenticationError(
                        f"Auth failure on {path}: HTTP {response.status_code}"
                    )

                if response.status_code >= 500:
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
                last_exc = exc

            if attempt < self._config.max_retries:
                delay = self._config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

        if last_exc is not None:
            raise last_exc
        msg = "Max retries exceeded"
        raise RuntimeError(msg)

    async def get(self, path: str, **params: Any) -> httpx.Response:
        return await self._request("GET", path, **params)

    async def post(self, path: str, **body: Any) -> httpx.Response:
        return await self._request("POST", path, **body)

    async def delete(self, path: str, **params: Any) -> httpx.Response:
        return await self._request("DELETE", path, **params)

    async def get_api_limits(self) -> AccountLimits:
        """Fetch current API tier limits from GET /account/limits."""
        from traderbot.kalshi.models import AccountLimits

        resp = await self.get("/account/limits")
        resp.raise_for_status()
        data = resp.json()
        return AccountLimits.model_validate(data)

    async def _detect_tier(self) -> None:
        """Query GET /account/limits and reconfigure rate limiter."""
        self._tier_detected = True
        try:
            limits = await self.get_api_limits()
            self._rate_limiter.reconfigure(
                read_rate=float(limits.read.refill_rate),
                write_rate=float(limits.write.refill_rate),
                read_burst=limits.read.bucket_capacity,
                write_burst=limits.write.bucket_capacity,
            )
            logger.info(
                "Auto-detected Kalshi tier '%s': read=%d/s write=%d/s",
                limits.usage_tier,
                limits.read.refill_rate,
                limits.write.refill_rate,
            )
        except Exception as exc:
            logger.debug("Tier auto-detect failed, using config defaults: %s", exc)

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
