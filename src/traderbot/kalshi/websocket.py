"""Kalshi WebSocket client — WS-first real-time market data (DD-016).

The WebSocket stream is the sole source of real-time Kalshi data. REST is used
only for startup cache seeding, disconnect recovery, and historical data (see
``traderbot.kalshi.client``). This module implements the v2 WebSocket protocol
verified against docs.kalshi.com 2026-08-04:

* ``subscribe`` / ``unsubscribe`` / ``update_subscription`` /
  ``list_subscriptions`` command formats.
* ``subscribed`` / ``unsubscribed`` / ``ok`` / ``error`` response handling,
  including the full 1-28 server error-code table.
* ``sids``-based unsubscription (the server issues a ``sid`` per subscription in
  the ``subscribed`` ack — unsubscription is *by sid*, never by channel name).
* ``use_yes_price`` awareness for the orderbook channel (unified yes-leg
  pricing; the API defaults to no-leg pricing but will flip in a future
  release). TraderBot always sets ``use_yes_price=true`` so a single
  ``price_dollars`` scale applies to both sides.
* TLS SPKI pinning per environment (production/demo) — see ``pinning.py``.
* Keep-alive is handled automatically by the ``websockets`` library; no manual
  heartbeat is needed.

Two public classes:

* :class:`KalshiWebSocket` — a single authenticated connection with typed
  subscribe/unsubscribe/update/list operations and a ``receive()`` iterator.
* :class:`KalshiWebSocketManager` — wraps a connection in an asyncio task with
  automatic reconnection (exponential backoff capped at 30s, bounded retries)
  and re-subscription of the configured channels on every reconnect. On
  persistent failure (max retries exceeded) it invokes a fail-open callback so
  the caller can seed from REST rather than hang.

Credentials come from the caller (typically a :class:`traderbot.secrets.store.
SecretsStore` lookup) — this module never reads env files.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Final, Literal, Self

import websockets.asyncio.client
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from traderbot.kalshi.pinning import create_pinned_ssl_context, trusted_pins_for
from traderbot.kalshi.signing import auth_headers

logger = logging.getLogger(__name__)

# Recursive JSON value types — matches the rest of the kalshi package so the
# module stays strict-typed without ``Any``.
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

# All public channels TraderBot subscribes to. ``market_lifecycle_v2`` is the
# current lifecycle channel (v1 was deprecated); ``fill`` / ``user_orders`` /
# ``market_positions`` are private (require the authenticated connection);
# ``ticker`` / ``orderbook_delta`` carry public market data (the connection
# still requires authentication).
VALID_CHANNELS: Final = frozenset(
    {
        "ticker",
        "orderbook_delta",
        "market_lifecycle_v2",
        "fill",
        "user_orders",
        "market_positions",
    }
)

# Channels that are private to the authenticated user.
_PRIVATE_CHANNELS: Final = frozenset({"fill", "user_orders", "market_positions"})

# Full WebSocket error code table from docs.kalshi.com (websocket-connection).
KALSHI_WS_ERROR_CODES: Final = {
    1: "Unable to process message - General processing error",
    2: "Params required - Missing params object in command",
    3: "Channels required - Missing channels array in subscribe",
    4: "Subscription IDs required - Missing sids in unsubscribe",
    5: "Unknown command - Invalid command name",
    6: "Already subscribed - Duplicate subscription attempt",
    7: "Unknown subscription ID - Subscription ID not found",
    8: "Unknown channel name - Invalid channel in subscribe",
    9: "Authentication required - Channel requires authenticated connection",
    10: "Channel error - Channel-specific error",
    11: "Invalid parameter - Malformed parameter value",
    12: "Exactly one subscription ID is required - For update_subscription",
    13: "Unsupported action - Invalid action for update_subscription",
    14: "Market Ticker required - Missing market specification",
    15: "Action required - Missing action in update_subscription",
    16: "Market not found - Invalid market_ticker or market_id",
    17: "Internal error - Server-side processing error",
    18: "Command timeout - Server timed out while processing command",
    19: "shard_factor must be > 0 - Invalid shard_factor",
    20: "shard_factor is required when shard_key is set",
    21: "shard_key must be >= 0 and < shard_factor - Invalid shard_key",
    22: "shard_factor must be <= 100 - shard_factor too large",
    23: "Match IDs required - Missing match_ids for the channel/action",
    24: "Index IDs required - Missing index_ids for the channel/action",
    25: "Subscription buffer overflow - The subscription's buffer is full",
    26: "Subscription market limit exceeded - Adding markets would exceed the "
    "per-subscription market limit",
    27: "Too many requests - The subscription exceeded its command rate limit",
    28: "Underlying tickers required - Missing underlying_tickers",
}

# Per-environment WebSocket base URLs (docs.kalshi.com — API Environments).
_WS_BASE_URLS: Final = {
    "production": "wss://external-api-ws.kalshi.com/trade-api/ws/v2",
    "demo": "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2",
}

# Signing path for the WebSocket handshake (fixed, from the API root).
_WS_SIGNING_PATH: Final = "/trade-api/ws/v2"

# Action values for update_subscription (docs.kalshi.com).
UpdateSubscriptionAction = Literal["add_markets", "delete_markets", "get_snapshot"]

# Exponential backoff bounds for reconnection.
_BACKOFF_START_S: Final = 1.0
_BACKOFF_MAX_S: Final = 30.0
_DEFAULT_MAX_RETRIES: Final = 10


class WebSocketError(RuntimeError):
    """Raised for server-reported WebSocket errors (codes 1-28)."""

    def __init__(self, code: int, message: str) -> None:
        self.code: int = code
        self.message: str = message
        super().__init__(f"kalshi ws error {code}: {message}")


def _as_json_object(value: JsonValue | None) -> JsonObject:
    """Coerce a JSON value to a dict, returning {} for non-dicts."""
    if isinstance(value, dict):
        return value
    return {}


def _as_int(value: JsonValue | None) -> int | None:
    """Coerce a JSON value to int, returning None for non-ints."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_str(value: JsonValue | None) -> str | None:
    """Coerce a JSON value to str, returning None for non-strs."""
    if isinstance(value, str):
        return value
    return None


class KalshiWebSocket:
    """A single authenticated Kalshi WebSocket connection.

    Not itself an asyncio task — the caller drives it (typically via
    :class:`KalshiWebSocketManager` or ``async for msg in ws``).

    Args:
        api_key: Kalshi API key ID.
        private_key_pem: Kalshi RSA private key (PEM string).
        environment: ``"production"`` (default) or ``"demo"``. Selects the WS
            base URL and the matching SPKI pin. Demo keys only work against the
            demo endpoint, and vice versa.
        channels: Channels to subscribe to on :meth:`connect`. Must be a subset
            of :data:`VALID_CHANNELS`. Defaults to the full public set.
        market_tickers: Optional iterable of tickers to filter subscriptions
            (public channels). If omitted, public channels stream all markets.
    """

    def __init__(
        self,
        api_key: str,
        private_key_pem: str,
        *,
        environment: str = "production",
        channels: frozenset[str] | set[str] | None = None,
        market_tickers: list[str] | None = None,
        base_url: str | None = None,
    ) -> None:
        if environment not in _WS_BASE_URLS:
            raise ValueError(
                f"unknown environment {environment!r}; expected one of {sorted(_WS_BASE_URLS)}"
            )
        if not api_key or not private_key_pem:
            raise ValueError("api_key and private_key_pem are required")

        selected_channels = (
            frozenset(channels)
            if channels is not None
            else {c for c in VALID_CHANNELS if c not in _PRIVATE_CHANNELS}
        )
        invalid = selected_channels - VALID_CHANNELS
        if invalid:
            raise ValueError(
                f"unknown channels {sorted(invalid)}; expected subset of {sorted(VALID_CHANNELS)}"
            )
        if not selected_channels:
            raise ValueError("at least one channel is required")

        self._api_key: str = api_key
        self._private_key_pem: str = private_key_pem
        self._environment: str = environment
        self._channels: frozenset[str] = frozenset(selected_channels)
        self._market_tickers: list[str] = list(market_tickers) if market_tickers else []
        self._ws_url: str = base_url or _WS_BASE_URLS[environment]

        self._conn: ClientConnection | None = None
        self._cmd_id: int = 0
        # channel -> sid, populated from ``subscribed`` acks. This is the
        # authoritative map for unsubscription and update_subscription.
        self._sid_map: dict[str, int] = {}

    @property
    def channels(self) -> frozenset[str]:
        return self._channels

    @property
    def market_tickers(self) -> list[str]:
        return self._market_tickers

    @property
    def sids(self) -> dict[str, int]:
        """Return a copy of the channel -> sid mapping."""
        return dict(self._sid_map)

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def _next_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    def _auth_headers(self) -> dict[str, str]:
        return auth_headers(self._api_key, self._private_key_pem, "GET", _WS_SIGNING_PATH)

    async def connect(self) -> None:
        """Open the authenticated connection and subscribe to configured channels.

        Raises:
            WebSocketError: if the server rejects a subscription.
        """
        ssl_context = create_pinned_ssl_context(trusted_pins_for(self._environment))
        headers = self._auth_headers()
        self._conn = await websockets.asyncio.client.connect(
            self._ws_url,
            ssl=ssl_context,
            additional_headers=headers,
        )
        await self._subscribe(
            list(self._channels),
            market_ticker=None,
            market_tickers=list(self._market_tickers) or None,
        )

    async def _subscribe(
        self,
        channels: list[str],
        *,
        market_ticker: str | None = None,
        market_tickers: list[str] | None = None,
    ) -> None:
        """Issue a subscribe command and consume the ack(s)."""
        params: dict[str, JsonValue] = {"channels": [c for c in channels]}
        # Public channels may be market-scoped; private channels are not.
        if market_ticker is not None and not set(channels) & _PRIVATE_CHANNELS:
            params["market_ticker"] = market_ticker
        elif market_tickers is not None and not set(channels) & _PRIVATE_CHANNELS:
            params["market_tickers"] = [t for t in market_tickers]
        # Orderbook: always request unified yes-leg pricing so a single price
        # scale applies to both sides (the legacy no-leg default will flip off).
        if "orderbook_delta" in channels:
            params["use_yes_price"] = True

        result = await self._send_command("subscribe", params)
        if result is None:
            return
        if isinstance(result, list):
            entries: list[JsonValue] = result
        else:
            entries = [result]
        for entry in entries:
            obj = _as_json_object(entry)
            channel = _as_str(obj.get("channel"))
            sid = _as_int(obj.get("sid"))
            if channel is not None and sid is not None:
                self._sid_map[channel] = sid

    async def _send_command(
        self, cmd: str, params: dict[str, JsonValue] | None
    ) -> JsonValue | None:
        """Send a command and wait for its response.

        Returns the parsed ``msg`` payload of the response, or ``None`` for
        responses without a useful payload.

        Raises:
            WebSocketError: if the server replies with an ``error`` message.
        """
        if self._conn is None:
            raise RuntimeError("not connected")
        payload: dict[str, JsonValue] = {"id": self._next_id(), "cmd": cmd}
        if params is not None:
            payload["params"] = params
        await self._conn.send(json.dumps(payload))
        logger.debug("ws cmd sent: %s (id=%s)", cmd, payload["id"])
        # Read messages until we get the response matching our command id.
        while True:
            raw = await self._conn.recv()
            msg = json.loads(raw)
            if msg.get("id") != payload["id"]:
                continue
            return self._handle_response(msg)

    def _handle_response(self, msg: JsonObject) -> JsonValue | None:
        msg_type = _as_str(msg.get("type"))
        if msg_type == "error":
            err = _as_json_object(msg.get("msg"))
            code = _as_int(err.get("code")) or 0
            text = _as_str(err.get("msg")) or KALSHI_WS_ERROR_CODES.get(code, "unknown error")
            raise WebSocketError(code, text)
        if msg_type == "ok":
            return msg.get("msg")
        if msg_type == "subscribed":
            return msg.get("msg")
        return None

    async def subscribe_extra_markets(self, tickers: list[str]) -> None:
        """Add tickers to an existing public subscription via update_subscription.

        Uses ``update_subscription`` with ``action="add_markets"`` targeted at
        the first public (non-private) sid. This avoids WS error 6
        ("Already subscribed") that a duplicate subscribe would trigger.
        """
        if not tickers:
            return
        public_sid = self._first_public_sid()
        if public_sid is None:
            raise WebSocketError(7, "no public subscription to update")
        await self._send_command(
            "update_subscription",
            {
                "sids": [public_sid],
                "market_tickers": [t for t in tickers],
                "action": "add_markets",
            },
        )

    async def unsubscribe(self, sids: list[int]) -> None:
        """Cancel subscriptions by their server-issued sids."""
        if not sids:
            return
        await self._send_command("unsubscribe", {"sids": [s for s in sids]})
        for channel, sid in list(self._sid_map.items()):
            if sid in sids:
                del self._sid_map[channel]

    async def list_subscriptions(self) -> list[dict[str, JsonValue]]:
        """Return the active subscriptions (channel + sid)."""
        result = await self._send_command("list_subscriptions", None)
        if isinstance(result, list):
            for entry in result:
                obj = _as_json_object(entry)
                channel = _as_str(obj.get("channel"))
                sid = _as_int(obj.get("sid"))
                if channel is not None and sid is not None:
                    self._sid_map[channel] = sid
            return [_as_json_object(entry) for entry in result]
        return []

    def _first_public_sid(self) -> int | None:
        for channel, sid in self._sid_map.items():
            if channel not in _PRIVATE_CHANNELS:
                return sid
        return None

    async def receive(self, timeout: float | None = None) -> JsonObject:
        """Receive the next message from the server.

        Args:
            timeout: Optional per-receive timeout in seconds. ``None`` blocks.

        Returns:
            The parsed message dict. Server ``error`` responses are raised as
            :class:`WebSocketError`.

        Raises:
            asyncio.TimeoutError: if ``timeout`` is given and no message
                arrives in time.
        """
        if self._conn is None:
            raise RuntimeError("not connected")
        if timeout is not None:
            raw = await asyncio.wait_for(self._conn.recv(), timeout)
        else:
            raw = await self._conn.recv()
        msg = json.loads(raw)
        self._handle_response(msg)
        return msg

    async def stream(self) -> AsyncIterator[JsonObject]:
        """Iterate over inbound messages forever (until the connection closes)."""
        while True:
            try:
                yield await self.receive()
            except ConnectionClosed:
                return

    async def close(self) -> None:
        """Close the WebSocket connection if open."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._sid_map = {}

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


class KalshiWebSocketManager:
    """Asyncio task wrapper around :class:`KalshiWebSocket` with reconnect.

    Runs a persistent connection loop as a background asyncio task. On
    disconnect, reconnects with exponential backoff (1s -> 30s cap) and
    re-subscribes the configured channels. After ``max_retries`` consecutive
    failures, calls the ``on_fail_open`` callback (if provided) and stops.

    Args:
        api_key: Kalshi API key ID.
        private_key_pem: Kalshi RSA private key (PEM string).
        environment: ``"production"`` or ``"demo"``.
        channels: Channels to subscribe to.
        market_tickers: Optional ticker filter for public channels.
        on_message: Optional awaitable called with every inbound message.
        on_reconnect: Optional awaitable called after each successful reconnect.
        on_fail_open: Optional awaitable called after max retries exceeded.
            The caller can use it to seed a cache from REST.
        max_retries: Consecutive failure cap before fail-open (default 10).
        backoff_start: Initial backoff in seconds (default 1.0).
        backoff_max: Max backoff in seconds (default 30.0).
    """

    def __init__(
        self,
        api_key: str,
        private_key_pem: str,
        *,
        environment: str = "production",
        channels: frozenset[str] | set[str] | None = None,
        market_tickers: list[str] | None = None,
        on_message: Callable[[JsonObject], Awaitable[None]] | None = None,
        on_reconnect: Callable[[], Awaitable[None]] | None = None,
        on_fail_open: Callable[[], Awaitable[None]] | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_start: float = _BACKOFF_START_S,
        backoff_max: float = _BACKOFF_MAX_S,
    ) -> None:
        self._api_key: str = api_key
        self._private_key_pem: str = private_key_pem
        self._environment: str = environment
        self._channels: frozenset[str] | None = (
            frozenset(channels) if channels is not None else None
        )
        self._market_tickers: list[str] = list(market_tickers) if market_tickers else []
        self._on_message: Callable[[JsonObject], Awaitable[None]] | None = on_message
        self._on_reconnect: Callable[[], Awaitable[None]] | None = on_reconnect
        self._on_fail_open: Callable[[], Awaitable[None]] | None = on_fail_open
        self._max_retries: int = max_retries
        self._backoff_start: float = backoff_start
        self._backoff_max: float = backoff_max

        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._ws: KalshiWebSocket | None = None
        self._fail_open_fired: bool = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def fail_open_fired(self) -> bool:
        return self._fail_open_fired

    async def start(self) -> None:
        """Start the connection manager as an asyncio task."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="kalshi-ws-manager")

    async def stop(self) -> None:
        """Stop the manager and close any active connection."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _run(self) -> None:
        retries = 0
        backoff = self._backoff_start
        while not self._stop_event.is_set():
            ws = KalshiWebSocket(
                self._api_key,
                self._private_key_pem,
                environment=self._environment,
                channels=self._channels,
                market_tickers=self._market_tickers,
            )
            self._ws = ws
            try:
                await ws.connect()
                retries = 0
                backoff = self._backoff_start
                logger.info("kalshi ws connected (%s)", self._environment)
                if self._on_reconnect is not None:
                    await self._on_reconnect()
                async for msg in ws.stream():
                    if self._stop_event.is_set():
                        break
                    if self._on_message is not None:
                        await self._on_message(msg)
            except ConnectionClosed:
                logger.warning("kalshi ws closed; reconnecting")
            except Exception:  # noqa: BLE001 — reconnect after any error
                logger.warning("kalshi ws error; reconnecting", exc_info=True)
            finally:
                await ws.close()
                self._ws = None

            if self._stop_event.is_set():
                break

            retries += 1
            if retries >= self._max_retries:
                logger.error("kalshi ws failed %d times; failing open", retries)
                self._fail_open_fired = True
                if self._on_fail_open is not None:
                    await self._on_fail_open()
                break

            logger.info(
                "kalshi ws reconnect in %.1fs (retry %d/%d)",
                backoff,
                retries,
                self._max_retries,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, self._backoff_max)


__all__ = [
    "KALSHI_WS_ERROR_CODES",
    "KalshiWebSocket",
    "KalshiWebSocketManager",
    "UpdateSubscriptionAction",
    "VALID_CHANNELS",
    "WebSocketError",
]
