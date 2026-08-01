"""Async WebSocket client for Kalshi real-time market data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import websockets
from pydantic import SecretStr  # noqa: TC002 — needed at runtime for BaseSettings field
from pydantic_settings import BaseSettings, SettingsConfigDict

from traderbot.kalshi.pinning import create_pinned_ssl_context
from traderbot.kalshi.signing import auth_headers

logger = logging.getLogger(__name__)

VALID_CHANNELS: frozenset[str] = frozenset(
    {
        "ticker",
        "orderbook_delta",
        "market_lifecycle_v2",
        "fill",
        "user_orders",
        "market_positions",
    }
)


class WebSocketConfig(BaseSettings):
    """Configuration for Kalshi WebSocket client."""

    model_config = SettingsConfigDict(
        strict=True,
        extra="forbid",
        env_prefix="KALSHI_",
        env_file=str(Path.home() / ".traderbot" / ".env"),
        env_file_encoding="utf-8",
    )

    api_key: SecretStr
    private_key_pem: SecretStr | None = None
    base_url: str = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"

    def resolve_private_key(self) -> str:
        if self.private_key_pem is not None:
            return self.private_key_pem.get_secret_value()
        raise ValueError("No private key configured. Set KALSHI_PRIVATE_KEY_PEM.")


class KalshiWebSocket:
    """Async WebSocket client for Kalshi real-time market data."""

    def __init__(self, config: WebSocketConfig | None = None) -> None:
        self._config = config or WebSocketConfig()
        self._ws: Any = None
        self._message_id = 0

    async def connect(self) -> None:
        """Connect to the Kalshi WebSocket with RSA-PSS auth and TLS cert pinning."""
        logger.info("Connecting to WebSocket: %s", self._config.base_url)
        headers = auth_headers(
            self._config.api_key.get_secret_value(),
            self._config.resolve_private_key(),
            "GET",
            "/trade-api/ws/v2",
        )
        headers["Content-Type"] = "application/json"
        try:
            self._ws = await websockets.connect(
                self._config.base_url,
                additional_headers=headers,
                ssl=create_pinned_ssl_context(),
            )
            logger.info("WebSocket connected: %s", self._config.base_url)
        except Exception:
            logger.error("WebSocket connection failed: %s", self._config.base_url)
            raise

    async def subscribe(
        self,
        channels: list[str],
        market_ticker: str | None = None,
        market_tickers: list[str] | None = None,
    ) -> None:
        """Subscribe to channels for one or more markets.

        Args:
            channels: Channel names (must be in VALID_CHANNELS).
            market_ticker: Single market ticker symbol (mutually exclusive with market_tickers).
            market_tickers: Multiple market ticker symbols (mutually exclusive with market_ticker).

        Raises:
            ValueError: If channels contain invalid names or neither/both ticker params are provided.
        """
        invalid = [c for c in channels if c not in VALID_CHANNELS]
        if invalid:
            raise ValueError(f"Invalid channel(s): {invalid}. Valid: {sorted(VALID_CHANNELS)}")

        if market_ticker is not None and market_tickers is not None:
            raise ValueError("Provide market_ticker or market_tickers, not both.")
        if market_ticker is None and market_tickers is None:
            raise ValueError("Provide market_ticker or market_tickers.")

        self._message_id += 1
        params: dict[str, Any] = {"channels": channels}
        if market_tickers is not None:
            params["market_tickers"] = market_tickers
        else:
            params["market_ticker"] = market_ticker

        msg = {"id": self._message_id, "cmd": "subscribe", "params": params}
        await self._ws.send(json.dumps(msg))
        logger.info(
            "Subscribed to channels=%s ticker=%s", channels, market_ticker or market_tickers
        )

    async def unsubscribe(
        self,
        channels: list[str],
        market_ticker: str | None = None,
        market_tickers: list[str] | None = None,
    ) -> None:
        """Unsubscribe from channels for one or more markets.

        Args:
            channels: Channel names (must be in VALID_CHANNELS).
            market_ticker: Single market ticker symbol (mutually exclusive with market_tickers).
            market_tickers: Multiple market ticker symbols (mutually exclusive with market_ticker).

        Raises:
            ValueError: If channels contain invalid names or neither/both ticker params are provided.
        """
        invalid = [c for c in channels if c not in VALID_CHANNELS]
        if invalid:
            raise ValueError(f"Invalid channel(s): {invalid}. Valid: {sorted(VALID_CHANNELS)}")

        if market_ticker is not None and market_tickers is not None:
            raise ValueError("Provide market_ticker or market_tickers, not both.")
        if market_ticker is None and market_tickers is None:
            raise ValueError("Provide market_ticker or market_tickers.")

        self._message_id += 1
        params: dict[str, Any] = {"channels": channels}
        if market_tickers is not None:
            params["market_tickers"] = market_tickers
        else:
            params["market_ticker"] = market_ticker

        msg = {"id": self._message_id, "cmd": "unsubscribe", "params": params}
        await self._ws.send(json.dumps(msg))
        logger.info(
            "Unsubscribed from channels=%s ticker=%s", channels, market_ticker or market_tickers
        )

    async def receive(self) -> dict[str, Any]:
        """Receive the next message from the WebSocket.

        Returns:
            Parsed JSON message as a dict.
        """
        raw = await self._ws.recv()
        data = json.loads(raw)
        if isinstance(data, dict) and "channel" in data:
            logger.debug("WS message on channel=%s", data.get("channel"))
        return data

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            logger.info("Closing WebSocket connection")
            await self._ws.close()
            logger.info("WebSocket connection closed")

    async def __aenter__(self) -> KalshiWebSocket:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
