"""Tests for the Kalshi WebSocket streaming module."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from websockets.frames import Close

from traderbot.kalshi.websocket import MarketStream, WebSocketConfig


def _make_config(**overrides: Any) -> WebSocketConfig:
    defaults: dict[str, Any] = {
        "api_key": "test-key",
        "api_secret": "test-secret",
    }
    defaults.update(overrides)
    return WebSocketConfig(**defaults)


class TestWebSocketConfig:
    def test_defaults(self) -> None:
        config = _make_config()
        assert config.base_url == "wss://api.kalshi.co/trade-api/ws/v2"
        assert config.demo_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"
        assert config.demo_mode is False
        assert config.reconnect_delay == 1.0
        assert config.max_reconnect_attempts == 10

    def test_active_url_production(self) -> None:
        config = _make_config(demo_mode=False)
        assert config.active_url == "wss://api.kalshi.co/trade-api/ws/v2"

    def test_active_url_demo(self) -> None:
        config = _make_config(demo_mode=True)
        assert config.active_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"

    def test_secret_not_logged(self) -> None:
        config = _make_config()
        dumped = config.model_dump()
        assert dumped["api_secret"] != "test-secret"

    def test_extra_field_rejected(self) -> None:
        from pydantic import ValidationError

        from traderbot.kalshi.websocket import WebSocketConfig

        with pytest.raises(ValidationError):
            WebSocketConfig(api_key="k", api_secret="s", extra_field=True)


def _make_mock_ws(auth_response: dict[str, Any] | None = None) -> AsyncMock:
    ws = AsyncMock()
    recv_responses: list[str] = []
    sent_messages: list[str] = []

    if auth_response is None:
        recv_responses.append(json.dumps({"type": "auth_approved"}))
    else:
        recv_responses.append(json.dumps(auth_response))

    recv_index = 0

    async def fake_recv() -> str:
        nonlocal recv_index
        if recv_index < len(recv_responses):
            resp = recv_responses[recv_index]
            recv_index += 1
            return resp
        return json.dumps({"type": "ticker", "ticker": "KXBTCD-26MAR31-T55000"})

    async def fake_send(data: str) -> None:
        sent_messages.append(data)

    ws.recv = fake_recv
    ws.send = fake_send
    ws.close = AsyncMock()
    object.__setattr__(ws, "recv_responses", recv_responses)
    object.__setattr__(ws, "sent_messages", sent_messages)
    return ws


def _patch_connect(mock_ws: AsyncMock) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_ws)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestMarketStreamConnect:
    @pytest.mark.asyncio
    async def test_connect_sends_auth(self) -> None:
        mock_ws = _make_mock_ws()
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            await stream.connect()

        assert len(mock_ws.sent_messages) >= 1
        auth_msg = json.loads(mock_ws.sent_messages[0])
        assert auth_msg["type"] == "auth"
        assert auth_msg["api_key"] == "test-key"

    @pytest.mark.asyncio
    async def test_connect_rejects_bad_auth(self) -> None:
        mock_ws = _make_mock_ws(auth_response={"type": "auth_denied"})
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with (
            patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm),
            pytest.raises(RuntimeError, match="authentication failed"),
        ):
            await stream.connect()


class TestMarketStreamSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_message_format(self) -> None:
        mock_ws = _make_mock_ws()
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            await stream.connect()
            await stream.subscribe(["KXBTCD-26MAR31-T55000", "KXELEC-26NOV05-T270"])

        sub_msg = json.loads(mock_ws.sent_messages[1])
        assert sub_msg["type"] == "subscribe"
        assert len(sub_msg["channels"]) == 2
        tickers = {ch["ticker"] for ch in sub_msg["channels"]}
        assert tickers == {"KXBTCD-26MAR31-T55000", "KXELEC-26NOV05-T270"}

    @pytest.mark.asyncio
    async def test_subscribe_tracks_tickers(self) -> None:
        mock_ws = _make_mock_ws()
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            await stream.connect()
            await stream.subscribe(["KXBTCD-26MAR31-T55000"])

        assert "KXBTCD-26MAR31-T55000" in stream._subscribed_tickers

    @pytest.mark.asyncio
    async def test_unsubscribe_message_format(self) -> None:
        mock_ws = _make_mock_ws()
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            await stream.connect()
            await stream.subscribe(["KXBTCD-26MAR31-T55000", "KXELEC-26NOV05-T270"])
            await stream.unsubscribe(["KXBTCD-26MAR31-T55000"])

        unsub_msg = json.loads(mock_ws.sent_messages[2])
        assert unsub_msg["type"] == "unsubscribe"
        assert unsub_msg["channels"][0]["ticker"] == "KXBTCD-26MAR31-T55000"
        assert "KXBTCD-26MAR31-T55000" not in stream._subscribed_tickers


class TestMarketStreamListen:
    @pytest.mark.asyncio
    async def test_listen_yields_parsed_messages(self) -> None:
        mock_ws = _make_mock_ws()
        mock_ws.recv_responses.append(
            json.dumps({"type": "ticker", "ticker": "KXBTCD", "price": 65})
        )
        mock_ws.recv_responses.append(
            json.dumps({"type": "ticker", "ticker": "KXELEC", "price": 30})
        )

        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            await stream.connect()
            yielded: list[dict] = []
            async for msg in stream.listen():
                yielded.append(msg)
                if len(yielded) == 2:
                    await stream.close()

        assert yielded[0]["type"] == "ticker"
        assert yielded[0]["ticker"] == "KXBTCD"
        assert yielded[1]["price"] == 30


class TestMarketStreamReconnect:
    @pytest.mark.asyncio
    async def test_auto_reconnect_on_disconnect(self) -> None:
        from websockets.exceptions import ConnectionClosedError

        close_frame = Close(1000, "normal closure")
        connect_count = 0

        def make_cm_for(ws: AsyncMock) -> AsyncMock:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=ws)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        def connect_side_effect(url: str) -> Any:
            nonlocal connect_count
            connect_count += 1
            ws = _make_mock_ws()

            if connect_count == 1:
                recv_count = 0

                async def recv_then_disconnect() -> str:
                    nonlocal recv_count
                    recv_count += 1
                    if recv_count == 1:
                        return json.dumps({"type": "auth_approved"})
                    raise ConnectionClosedError(close_frame, close_frame, True)

                ws.recv = recv_then_disconnect
                ws.sent_messages = []
            ws.close = AsyncMock()
            return make_cm_for(ws)

        config = _make_config(reconnect_delay=0.01, max_reconnect_attempts=5)
        stream = MarketStream(config)

        with patch(
            "traderbot.kalshi.websocket.websockets.connect", side_effect=connect_side_effect
        ):
            await stream.connect()
            assert connect_count == 1
            yielded: list[dict] = []
            async for msg in stream.listen():
                yielded.append(msg)
                await stream.close()

        assert connect_count >= 2

    @pytest.mark.asyncio
    async def test_max_reconnect_attempts_exhaustion(self) -> None:
        from websockets.exceptions import ConnectionClosedError

        close_frame = Close(1000, "closed")
        config = _make_config(reconnect_delay=0.01, max_reconnect_attempts=2)
        stream = MarketStream(config)

        initial_ws = _make_mock_ws()
        recv_count = 0

        async def recv_auth_then_close() -> str:
            nonlocal recv_count
            recv_count += 1
            if recv_count == 1:
                return json.dumps({"type": "auth_approved"})
            raise ConnectionClosedError(close_frame, close_frame, True)

        initial_ws.recv = recv_auth_then_close
        initial_ws.sent_messages = []
        initial_ws.close = AsyncMock()

        initial_cm = AsyncMock()
        initial_cm.__aenter__ = AsyncMock(return_value=initial_ws)
        initial_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def connect_side_effect(url: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return initial_cm
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        with patch(
            "traderbot.kalshi.websocket.websockets.connect",
            side_effect=connect_side_effect,
        ):
            await stream.connect()
            yielded: list[dict] = []
            async for msg in stream.listen():
                yielded.append(msg)

        assert len(yielded) == 0


class TestMarketStreamContextManager:
    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        mock_ws = _make_mock_ws()
        config = _make_config()
        stream = MarketStream(config)
        cm = _patch_connect(mock_ws)

        with patch("traderbot.kalshi.websocket.websockets.connect", return_value=cm):
            async with stream:
                assert stream._ws is not None

        assert stream._ws is None
        assert stream._closed is True

    @pytest.mark.asyncio
    async def test_operations_before_connect_raise(self) -> None:
        config = _make_config()
        stream = MarketStream(config)

        with pytest.raises(RuntimeError, match="Not connected"):
            await stream.subscribe(["TICKER"])
        with pytest.raises(RuntimeError, match="Not connected"):
            await stream.unsubscribe(["TICKER"])
        with pytest.raises(RuntimeError, match="Not connected"):
            await stream._authenticate()


class TestResubscribe:
    @pytest.mark.asyncio
    async def test_resubscribe_sends_subscriptions(self) -> None:
        config = _make_config()
        stream = MarketStream(config)
        stream._subscribed_tickers = {"TICKER_A", "TICKER_B"}

        with patch.object(stream, "subscribe", new_callable=AsyncMock) as mock_sub:
            await stream._resubscribe()
            mock_sub.assert_awaited_once()
            called_tickers = list(mock_sub.call_args[0][0])
            assert set(called_tickers) == {"TICKER_A", "TICKER_B"}

    @pytest.mark.asyncio
    async def test_resubscribe_noop_when_no_subscriptions(self) -> None:
        config = _make_config()
        stream = MarketStream(config)
        stream._subscribed_tickers = set()

        with patch.object(stream, "subscribe", new_callable=AsyncMock) as mock_sub:
            await stream._resubscribe()
            mock_sub.assert_not_awaited()
