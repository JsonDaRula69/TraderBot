"""Kalshi API client with auth, retry, rate limiting, and type normalization."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, SecretStr  # noqa: TC002
from pydantic_settings import BaseSettings, SettingsConfigDict

from traderbot.kalshi.models import MarketListResponse, TradeListResponse

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile


class RateLimitError(Exception):
    """Raised when the Kalshi API returns HTTP 429 (rate limit exceeded)."""


class AuthenticationError(Exception):
    """Raised when the Kalshi API returns an authentication failure (401/403)."""


class KalshiConfig(BaseSettings):
    """Configuration for Kalshi API client, loaded from environment variables."""

    model_config = SettingsConfigDict(
        strict=True,
        extra="forbid",
        env_prefix="KALSHI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    api_key: str
    api_secret: SecretStr
    base_url: str = "https://api.kalshi.co/trade-api/v2"
    demo_url: str = "https://demo-api.kalshi.co/trade-api/v2"
    demo_mode: bool = False
    rate_limit_rps: float = 5.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @property
    def active_url(self) -> str:
        return self.demo_url if self.demo_mode else self.base_url


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
    """Async Kalshi API client with auth, retries, rate limiting, and normalization."""

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
                # Use profile-aware credentials and demo mode
                from traderbot.profiles.config import resolve_kalshi_credentials
                
                api_key, api_secret = resolve_kalshi_credentials(profile)
                config = KalshiConfig(
                    api_key=api_key,
                    api_secret=SecretStr(api_secret),
                    demo_mode=profile.demo_mode,
                )
            else:
                # Fall back to env vars (backward compatibility)
                # This will raise ValidationError if KALSHI_API_KEY/KALSHI_API_SECRET not set
                config = KalshiConfig()  # type: ignore[call-arg]
        
        self._config = config
        self._session_token: str | None = None
        self._semaphore = asyncio.Semaphore(int(self._config.rate_limit_rps))
        self._client = httpx.AsyncClient(base_url=self._config.active_url)

    async def login(self) -> str:
        """Authenticate with Kalshi and store the session token.

        Returns:
            Session token string

        Raises:
            AuthenticationError: On 401/403 responses
            httpx.HTTPStatusError: On other non-2xx responses
        """
        response = await self._client.post(
            "/login",
            json={
                "api_key": self._config.api_key,
                "api_secret": self._config.api_secret.get_secret_value(),
            },
        )
        if response.status_code in (401, 403):
            raise AuthenticationError(f"Authentication failed: HTTP {response.status_code}")
        response.raise_for_status()
        body = response.json()
        token: str = body["token"]
        self._session_token = token
        return token

    async def _request(
        self,
        method: str,
        path: str,
        **params: Any,
    ) -> httpx.Response:
        """Core request handler with rate limiting, retry, and auth.

        Acquires the rate-limit semaphore, injects the Authorization header,
        and retries with exponential backoff + jitter on transient errors.
        """
        if self._session_token is None:
            msg = "Not authenticated — call login() first"
            raise AuthenticationError(msg)

        headers = {"Authorization": f"Bearer {self._session_token}"}

        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            async with self._semaphore:
                try:
                    if method.upper() == "GET":
                        response = await self._client.get(path, params=params, headers=headers)
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

            # Exponential backoff with jitter before retry (skip after last attempt).
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
