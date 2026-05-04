"""Tests for the Kalshi WebSocket streaming module."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from traderbot.kalshi.websocket import KalshiWebSocket, WebSocketConfig


def _make_config(**overrides: Any) -> WebSocketConfig:
    defaults: dict[str, Any] = {
        "api_key": SecretStr("test-key"),
        "private_key_pem": SecretStr('-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCgA3V0QIS7k5fx\ngaPK//Oe7zRjqOnloXC+fnMlnC5a+7NW+pv+Y4y+7OzMHfnnGnSweWqpVF7sjeJL\nUadWJw+UDMEsM4h06jFHZ14oKw2mN91PbKOe+XLzRr8+n4ykDavte1okHlvp4Pjr\nSKk44cr0DyulU4U3qwcVV/vFO5jx7CBVPD7d049Ipp0infhWKaOiZ8Ad0UXjdtM+\nh5R3Fl2HV+9NRHU47+oHllIWhYtc5oCo6sIUno+BYwY6C7t1IZmDqISDeHDqqZ0l\nkbrx+3C5QLL0sron/gO09bR6jMsBqZx4O3zu4LlH9K4FYYcz6pTB52N+8qE0qFwm\nuR7sCJuVAgMBAAECggEAAUp92loB6CSE848c8/CUNdpOtSYh+vcOOo85HRrROe0x\ncXh0pT0G3+x37Z6pSz7IpbrZDDQwzt5HLt3iCH0osERZE6L3zR+tlZqlJRRR2B83\nwyIIgOoYzhMqTFZLs3AjzLbzz3pKOg0VXQqZSOrzcPwlWUBfAQe5dyfeUWVNctg2\nVgOolcoLABH/Lr0mVnqZfhcNzvTTILJ8LtfMiREEJZDkYSrhkBvf0xv/7bJpx8ed\nokHcaeAsoChRWbRU8PvD7QcCj2e24p+TmBDtBjIOLizWNeOl9LYXg7fHfwnT3CWY\nHnp5DXed0TY3R6tubkH0cNvFkstK0xwkU7wir0f30QKBgQDW2q8zGzbJS5GFpwo+\n3FMk1Rwp1YiK4WR69ABnG1NSGGwX6FuHvhzndl9ru3Vw0ExKmWCLBVQYogu6AmPF\noPv5lWrRfFLVYdVenY0CFNiRdZay7BM9Ef1RsdgWFy1quAi2dSjA/SlI+FipU7r8\n+26K1wrwMp4tnU8NrR49lNn5cQKBgQC+qC+OBlU4Mhlyogco5EM0B0BCJ4nuMo3d\nJ8xZmm+LdDpsPqfwRL/q+OjufcHNO29IpC4FUZQOYAi9Ixyxh8qlelDIAkscR11m\nCtpvdGXeEDa0Ri4HI8c2hbJk+3v9pvkCDuP/ZIB4QwFVPbZ3+R1pBjv7668Nmgcm\nl2YlSNNSZQKBgQCfiqnYYFfxZ8z6mwxPm1meGyWbpvWKc04iwvddmPvpFTuHEUKO\nbMyXz92RaRUPHY3ZQ0VeVimZVRMyH74orZ8OOTalshTsYIaJiKKBrisW8GNkH0s1\n6RrbRB16YeGWwmut2RfXHuY+SjPEIOnUG3x9WqvDq0KsCoj+VdQD1Hl78QKBgC7o\n+NJsEnnCMeq3nSVdjH93rULZsaFPBQK+MRR24C0iyuEpRW7jq4jn93/+pzmU/xuT\ncdNTMCedT2kiA4RW0fCHOOsNTWfG018xGm/D5vCNcrhGcDrHfdOXb75S9j4B4FC2\nUzjahJWSfvh3N7crLyZRJ18jrS2ekVXYeISB96TVAoGBANYXaeqICg7Rj2r6xWzt\n5aWjWYHdcX/yrQk0mUexPpOtz/6q3AHu2DKktm/syg7eD+vIV2r/oZbzD8bbesDm\nFTkU25sA54vHPWiKUmozhfgrKDIxN2G5zSr/9p1KTy6E+FNzvQvooGkAVEO/WCh+\n2x5aiCRd24sxLhUju7Dtk15U\n-----END PRIVATE KEY-----\n'),
    }
    defaults.update(overrides)
    return WebSocketConfig(**defaults)


class TestWebSocketConfig:
    def test_defaults(self) -> None:
        config = _make_config()
        assert config.base_url == "wss://api.elections.kalshi.com/trade-api/ws/v2"
        assert config.demo_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"
        assert config.demo_mode is False

    def test_active_url_production(self) -> None:
        config = _make_config(demo_mode=False)
        assert config.active_url == "wss://api.elections.kalshi.com/trade-api/ws/v2"

    def test_active_url_demo(self) -> None:
        config = _make_config(demo_mode=True)
        assert config.active_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"

    def test_private_key_not_logged(self) -> None:
        config = _make_config()
        dumped = config.model_dump()
        assert dumped["private_key_pem"] != config.private_key_pem.get_secret_value()

    def test_extra_field_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WebSocketConfig(api_key=SecretStr("k"), private_key_pem=SecretStr("pem"), extra_field=True)


class TestKalshiWebSocketSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_message_format(self) -> None:
        config = _make_config(demo_mode=True)
        ws_client = KalshiWebSocket(config)
        mock_ws = AsyncMock()
        sent_messages: list[str] = []
        mock_ws.send = AsyncMock(side_effect=lambda data: sent_messages.append(data))

        ws_client._ws = mock_ws

        await ws_client.subscribe(["ticker"], "KXBTCD-26MAR31-T55000")

        assert len(sent_messages) == 1
        msg = json.loads(sent_messages[0])
        assert msg["cmd"] == "subscribe"
        assert msg["params"]["channels"] == ["ticker"]
        assert msg["params"]["market_ticker"] == "KXBTCD-26MAR31-T55000"
        assert "id" in msg

    @pytest.mark.asyncio
    async def test_unsubscribe_message_format(self) -> None:
        config = _make_config(demo_mode=True)
        ws_client = KalshiWebSocket(config)
        mock_ws = AsyncMock()
        sent_messages: list[str] = []
        mock_ws.send = AsyncMock(side_effect=lambda data: sent_messages.append(data))

        ws_client._ws = mock_ws

        await ws_client.unsubscribe(["ticker"], "KXBTCD-26MAR31-T55000")

        assert len(sent_messages) == 1
        msg = json.loads(sent_messages[0])
        assert msg["cmd"] == "unsubscribe"

    @pytest.mark.asyncio
    async def test_message_id_increments(self) -> None:
        config = _make_config(demo_mode=True)
        ws_client = KalshiWebSocket(config)
        mock_ws = AsyncMock()
        sent_messages: list[str] = []
        mock_ws.send = AsyncMock(side_effect=lambda data: sent_messages.append(data))

        ws_client._ws = mock_ws

        await ws_client.subscribe(["ticker"], "TICKER_1")
        await ws_client.subscribe(["ticker"], "TICKER_2")

        msg1 = json.loads(sent_messages[0])
        msg2 = json.loads(sent_messages[1])
        assert msg2["id"] > msg1["id"]


class TestKalshiWebSocketConnect:
    @pytest.mark.asyncio
    async def test_connect_uses_auth_headers_in_production(self) -> None:
        config = _make_config(demo_mode=False)
        ws_client = KalshiWebSocket(config)

        mock_ws = AsyncMock()
        async def mock_connect_fn(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_ws

        with patch("traderbot.kalshi.websocket.websockets.connect", side_effect=mock_connect_fn) as mock_connect:
            await ws_client.connect()

            # Verify connect was called with additional_headers
            call_kwargs = mock_connect.call_args
            headers = call_kwargs.kwargs.get("additional_headers", {})
            assert "KALSHI-ACCESS-KEY" in headers
            assert "KALSHI-ACCESS-SIGNATURE" in headers
            assert ws_client._ws is not None

    @pytest.mark.asyncio
    async def test_connect_demo_mode_no_auth(self) -> None:
        config = _make_config(demo_mode=True)
        ws_client = KalshiWebSocket(config)

        mock_ws = AsyncMock()
        async def mock_connect_fn(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_ws

        with patch("traderbot.kalshi.websocket.websockets.connect", side_effect=mock_connect_fn) as mock_connect:
            await ws_client.connect()

            # Demo mode should not include RSA-PSS auth headers
            call_kwargs = mock_connect.call_args
            headers = call_kwargs.kwargs.get("additional_headers", {})
            assert "KALSHI-ACCESS-KEY" not in headers
            assert ws_client._ws is not None
