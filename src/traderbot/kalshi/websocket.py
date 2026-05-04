"""Async WebSocket client for Kalshi real-time market data."""

from __future__ import annotations

import json
from typing import Any

import websockets
from pydantic import SecretStr  # noqa: TC002 — needed at runtime for BaseSettings field
from pydantic_settings import BaseSettings, SettingsConfigDict

from traderbot.kalshi.signing import auth_headers


class WebSocketConfig(BaseSettings):
    """Configuration for Kalshi WebSocket client."""

    model_config = SettingsConfigDict(
        strict=True,
        extra="forbid",
        env_prefix="KALSHI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    api_key: SecretStr
    private_key_pem: SecretStr | None = None
    base_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    demo_url: str = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    demo_mode: bool = False

    @property
    def active_url(self) -> str:
        return self.demo_url if self.demo_mode else self.base_url

    def resolve_private_key(self) -> str:
        """Resolve private key PEM for signing."""
        if self.private_key_pem is not None:
            return self.private_key_pem.get_secret_value()
        if self.demo_mode:
            return ""
        raise ValueError("No private key configured. Set KALSHI_PRIVATE_KEY_PEM.")


class KalshiWebSocket:
    """Async WebSocket client for Kalshi real-time market data."""

    def __init__(self, config: WebSocketConfig | None = None) -> None:
        self._config = config or WebSocketConfig()
        self._ws: Any = None
        self._message_id = 0

    async def connect(self) -> None:
        """Connect to the Kalshi WebSocket with RSA-PSS auth headers."""
        headers = {"Content-Type": "application/json"}
        if not self._config.demo_mode:
            headers.update(
                auth_headers(
                    self._config.api_key.get_secret_value(),
                    self._config.resolve_private_key(),
                    "GET",
                    "/trade-api/ws/v2",
                )
            )

        self._ws = await websockets.connect(
            self._config.active_url,
            additional_headers=headers,
        )

    async def subscribe(self, channels: list[str], market_ticker: str) -> None:
        """Subscribe to channels for a specific market.

        Args:
            channels: List of channel names (e.g., ["ticker", "orderbook"])
            market_ticker: Market ticker symbol
        """
        self._message_id += 1
        msg = {
            "id": self._message_id,
            "cmd": "subscribe",
            "params": {
                "channels": channels,
                "market_ticker": market_ticker,
            },
        }
        await self._ws.send(json.dumps(msg))

    async def unsubscribe(self, channels: list[str], market_ticker: str) -> None:
        """Unsubscribe from channels for a specific market.

        Args:
            channels: List of channel names
            market_ticker: Market ticker symbol
        """
        self._message_id += 1
        msg = {
            "id": self._message_id,
            "cmd": "unsubscribe",
            "params": {
                "channels": channels,
                "market_ticker": market_ticker,
            },
        }
        await self._ws.send(json.dumps(msg))

    async def receive(self) -> dict[str, Any]:
        """Receive the next message from the WebSocket.

        Returns:
            Parsed JSON message as a dict.
        """
        raw = await self._ws.recv()
        return json.loads(raw)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            await self._ws.close()

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
