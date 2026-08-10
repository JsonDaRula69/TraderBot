"""Unit tests for the Kalshi WebSocket client and manager (task 3)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from traderbot.kalshi.websocket import (
    KALSHI_WS_ERROR_CODES,
    KalshiWebSocket,
    KalshiWebSocketManager,
    WebSocketError,
)

API_KEY = "test-key"
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
_FAKE_AUTH_HEADERS = {
    "KALSHI-ACCESS-KEY": API_KEY,
    "KALSHI-ACCESS-SIGNATURE": "sig",
    "KALSHI-ACCESS-TIMESTAMP": "1234567890",
}


class _FakeConn:
    """Minimal stand-in for websockets ClientConnection."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, payload: str) -> None:
        cmd = json.loads(payload)
        self.sent.append(cmd)
        # Auto-ack subscriptions so _send_command does not block on recv.
        if cmd.get("cmd") == "subscribe":
            self.push(
                {"id": cmd["id"], "type": "subscribed", "msg": {"channel": "ticker", "sid": 1}}
            )

    async def recv(self) -> str:
        return await self._queue.get()

    async def close(self) -> None:
        pass

    def push(self, payload: dict) -> None:
        self._queue.put_nowait(json.dumps(payload))


@pytest.mark.asyncio
async def test_connect_subscribes_and_records_sids() -> None:
    conn = _FakeConn()
    with (
        patch("websockets.asyncio.client.connect", AsyncMock(return_value=conn)),
        patch("traderbot.kalshi.websocket.auth_headers", return_value=_FAKE_AUTH_HEADERS),
    ):
        ws = KalshiWebSocket(
            API_KEY,
            PRIVATE_KEY,
            channels={"ticker"},
            market_tickers=["KXWETHRM0700M"],
        )
        await ws.connect()

    assert ws.connected is True
    assert ws.channels == frozenset({"ticker"})
    assert ws.market_tickers == ["KXWETHRM0700M"]
    assert conn.sent[0]["cmd"] == "subscribe"
    assert conn.sent[0]["params"]["channels"] == ["ticker"]
    assert conn.sent[0]["params"]["market_tickers"] == ["KXWETHRM0700M"]


@pytest.mark.asyncio
async def test_connect_sends_auth_headers() -> None:
    conn = _FakeConn()
    with (
        patch("websockets.asyncio.client.connect", AsyncMock(return_value=conn)) as connect,
        patch("traderbot.kalshi.websocket.auth_headers", return_value=_FAKE_AUTH_HEADERS),
    ):
        ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"ticker"})
        await ws.connect()

    _, kwargs = connect.call_args
    assert "KALSHI-ACCESS-KEY" in kwargs["additional_headers"]
    assert "KALSHI-ACCESS-SIGNATURE" in kwargs["additional_headers"]
    assert "KALSHI-ACCESS-TIMESTAMP" in kwargs["additional_headers"]


@pytest.mark.asyncio
async def test_subscription_error_raises() -> None:
    conn = _FakeConn()
    conn.push({"id": 1, "type": "error", "msg": {"code": 2, "msg": "Params required"}})
    with (
        patch("websockets.asyncio.client.connect", AsyncMock(return_value=conn)),
        patch("traderbot.kalshi.websocket.auth_headers", return_value=_FAKE_AUTH_HEADERS),
    ):
        ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"orderbook_delta"})
        with pytest.raises(WebSocketError) as excinfo:
            await ws.connect()

    assert excinfo.value.code == 2
    assert excinfo.value.message == "Params required"


@pytest.mark.asyncio
async def test_receive_raises_error_messages() -> None:
    conn = _FakeConn()
    ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"ticker"})
    ws._conn = conn  # type: ignore[attr-defined]  # inject the fake connection directly
    conn.push({"id": 99, "type": "error", "msg": {"code": 5, "msg": "boom"}})

    with pytest.raises(WebSocketError) as excinfo:
        await ws.receive(timeout=1.0)

    assert excinfo.value.code == 5


@pytest.mark.asyncio
async def test_receive_returns_data_messages() -> None:
    conn = _FakeConn()
    ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"ticker"})
    ws._conn = conn  # type: ignore[attr-defined]
    conn.push({"type": "ticker", "msg": {"market_ticker": "KXWETHRM0700M", "last_price": 0.5}})

    msg = await ws.receive(timeout=1.0)

    assert msg["type"] == "ticker"
    assert msg["msg"]["last_price"] == 0.5


@pytest.mark.asyncio
async def test_close_resets_connection_and_sids() -> None:
    conn = _FakeConn()
    ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"ticker"})
    ws._conn = conn  # type: ignore[attr-defined]
    ws._sid_map = {"ticker": 1}

    await ws.close()

    assert ws.connected is False
    assert ws.sids == {}


@pytest.mark.asyncio
async def test_unsubscribe_uses_sids_not_channels() -> None:
    conn = _FakeConn()
    conn.push({"id": 1, "type": "ok", "msg": []})
    ws = KalshiWebSocket(API_KEY, PRIVATE_KEY, channels={"ticker"})
    ws._conn = conn  # type: ignore[attr-defined]
    ws._sid_map = {"ticker": 7}

    await ws.unsubscribe([7])

    assert conn.sent[0]["cmd"] == "unsubscribe"
    assert conn.sent[0]["params"] == {"sids": [7]}
    assert ws.sids == {}


@pytest.mark.asyncio
async def test_environment_validation() -> None:
    with pytest.raises(ValueError, match="unknown environment"):
        KalshiWebSocket(API_KEY, PRIVATE_KEY, environment="mars", channels={"ticker"})


@pytest.mark.asyncio
async def test_manager_retries_after_connection_failure() -> None:
    """The manager must retry (with backoff) after a failed connect."""
    from websockets.exceptions import ConnectionClosed

    attempts = {"count": 0}
    on_reconnect = AsyncMock()

    async def flaky_connect(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ConnectionClosed(rcvd=None, sent=None)
        return _FakeConn()

    manager = KalshiWebSocketManager(
        api_key=API_KEY,
        private_key_pem=PRIVATE_KEY,
        channels={"ticker"},
        on_reconnect=on_reconnect,
        backoff_start=0.01,
        backoff_max=0.02,
    )
    with (
        patch("websockets.asyncio.client.connect", side_effect=flaky_connect),
        patch("traderbot.kalshi.websocket.auth_headers", return_value=_FAKE_AUTH_HEADERS),
    ):
        start_task = asyncio.create_task(manager.start())
        for _ in range(200):
            if on_reconnect.await_count >= 1:
                break
            await asyncio.sleep(0.01)
        assert on_reconnect.await_count == 1, "manager did not reconnect after failure"
        await manager.stop()
        await start_task


@pytest.mark.asyncio
async def test_manager_fails_open_after_max_retries() -> None:
    from websockets.exceptions import ConnectionClosed

    on_fail_open = AsyncMock()

    async def always_fail(*_args, **_kwargs):
        raise ConnectionClosed(rcvd=None, sent=None)

    manager = KalshiWebSocketManager(
        api_key=API_KEY,
        private_key_pem=PRIVATE_KEY,
        channels={"ticker"},
        on_fail_open=on_fail_open,
        max_retries=3,
        backoff_start=0.01,
        backoff_max=0.02,
    )
    with (
        patch("websockets.asyncio.client.connect", side_effect=always_fail),
        patch("traderbot.kalshi.websocket.auth_headers", return_value=_FAKE_AUTH_HEADERS),
    ):
        start_task = asyncio.create_task(manager.start())
        for _ in range(200):
            if manager.fail_open_fired:
                break
            await asyncio.sleep(0.01)
        assert manager.fail_open_fired is True
        assert on_fail_open.await_count == 1
        await start_task


@pytest.mark.asyncio
async def test_error_code_table_is_populated() -> None:
    assert 1 in KALSHI_WS_ERROR_CODES
    assert 28 in KALSHI_WS_ERROR_CODES
    assert "Params" in KALSHI_WS_ERROR_CODES[2]
