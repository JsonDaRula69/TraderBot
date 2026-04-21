"""WebSocket streaming module for Kalshi real-time market data."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import websockets
from pydantic import BaseModel, SecretStr
from websockets import ConnectionClosed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class WebSocketConfig(BaseModel):
    """Configuration for Kalshi WebSocket connections."""

    api_key: str
    api_secret: SecretStr
    base_url: str = "wss://api.kalshi.co/trade-api/ws/v2"
    demo_url: str = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    demo_mode: bool = False
    reconnect_delay: float = 1.0
    max_reconnect_attempts: int = 10

    @property
    def active_url(self) -> str:
        """Return the WebSocket URL based on demo_mode."""
        return self.demo_url if self.demo_mode else self.base_url


class MarketStream:
    """WebSocket client with subscribe/unsubscribe, auto-reconnect, and async iteration."""

    def __init__(self, config: WebSocketConfig) -> None:
        self._config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_context: Any = None
        self._subscribed_tickers: set[str] = set()
        self._reconnect_attempt = 0
        self._closed = False

    async def connect(self) -> None:
        """Establish WebSocket connection and authenticate with Kalshi."""
        url = self._config.active_url
        self._ws_context = websockets.connect(url)
        self._ws = await self._ws_context.__aenter__()
        await self._authenticate()
        self._reconnect_attempt = 0
        logger.info("Connected to Kalshi WebSocket at %s", url)

    async def _authenticate(self) -> None:
        """Send authentication message over the WebSocket."""
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        auth_msg: dict[str, Any] = {
            "type": "auth",
            "api_key": self._config.api_key,
            "api_secret": self._config.api_secret.get_secret_value(),
        }
        await self._ws.send(json.dumps(auth_msg))
        response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        parsed = json.loads(response)
        if parsed.get("type") != "auth_approved":
            msg = f"WebSocket authentication failed: {parsed}"
            raise RuntimeError(msg)

    async def subscribe(self, tickers: list[str]) -> None:
        """Subscribe to real-time updates for the given market tickers."""
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        sub_msg: dict[str, Any] = {
            "type": "subscribe",
            "channels": [{"ticker": ticker, "side": "all"} for ticker in tickers],
        }
        await self._ws.send(json.dumps(sub_msg))
        self._subscribed_tickers.update(tickers)
        logger.debug("Subscribed to tickers: %s", tickers)

    async def unsubscribe(self, tickers: list[str]) -> None:
        """Unsubscribe from real-time updates for the given market tickers."""
        if self._ws is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        unsub_msg: dict[str, Any] = {
            "type": "unsubscribe",
            "channels": [{"ticker": ticker, "side": "all"} for ticker in tickers],
        }
        await self._ws.send(json.dumps(unsub_msg))
        self._subscribed_tickers -= set(tickers)
        logger.debug("Unsubscribed from tickers: %s", tickers)

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed messages; auto-reconnects with exponential backoff on disconnect."""
        while not self._closed:
            if self._ws is None:
                await self.connect()
                await self._resubscribe()

            try:
                raw = await self._ws.recv()
                msg: dict[str, Any] = json.loads(raw)
                yield msg
            except ConnectionClosed:
                logger.warning("WebSocket connection closed, attempting reconnect")
                self._ws = None
                if not await self._try_reconnect():
                    return

    async def _resubscribe(self) -> None:
        """Re-issue subscriptions for all tracked tickers after reconnection."""
        if self._subscribed_tickers:
            await self.subscribe(list(self._subscribed_tickers))

    async def _try_reconnect(self) -> bool:
        """Reconnect with exponential backoff; returns False when attempts exhausted."""
        while self._reconnect_attempt < self._config.max_reconnect_attempts:
            delay = self._config.reconnect_delay * (2**self._reconnect_attempt)
            logger.info(
                "Reconnect attempt %d/%d in %.1fs",
                self._reconnect_attempt + 1,
                self._config.max_reconnect_attempts,
                delay,
            )
            await asyncio.sleep(delay)
            self._reconnect_attempt += 1

            try:
                await self.connect()
                await self._resubscribe()
                return True
            except Exception:
                logger.exception("Reconnect attempt %d failed", self._reconnect_attempt)
                continue

        logger.error("Max reconnect attempts (%d) exhausted", self._config.max_reconnect_attempts)
        return False

    async def close(self) -> None:
        """Close the WebSocket connection and prevent further reconnection."""
        self._closed = True
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._ws_context is not None:
            await self._ws_context.__aexit__(None, None, None)
            self._ws_context = None
            logger.info("WebSocket connection closed")

    async def __aenter__(self) -> MarketStream:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
