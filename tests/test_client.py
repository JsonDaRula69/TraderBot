"""Tests for traderbot.kalshi.client — KalshiClient, KalshiConfig, and helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
import respx

from traderbot.kalshi.client import (
    AuthenticationError,
    KalshiClient,
    KalshiConfig,
    RateLimitError,
    _normalize_api_response,
)
from traderbot.kalshi.models import Market, MarketListResponse


def _make_config(demo_mode: bool = False) -> KalshiConfig:
    return KalshiConfig(
        api_key="test-key",
        api_secret="test-secret",
        demo_mode=demo_mode,
        rate_limit_rps=10.0,
        max_retries=3,
        retry_base_delay=0.01,
    )


class TestKalshiConfig:
    def test_defaults(self) -> None:
        cfg = _make_config()
        assert cfg.base_url == "https://api.kalshi.co/trade-api/v2"
        assert cfg.demo_url == "https://demo-api.kalshi.co/trade-api/v2"
        assert cfg.demo_mode is False
        assert cfg.rate_limit_rps == 10.0
        assert cfg.max_retries == 3
        assert cfg.retry_base_delay == 0.01

    def test_active_url_production(self) -> None:
        cfg = _make_config(demo_mode=False)
        assert cfg.active_url == "https://api.kalshi.co/trade-api/v2"

    def test_active_url_demo(self) -> None:
        cfg = _make_config(demo_mode=True)
        assert cfg.active_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_api_secret_is_secret_str(self) -> None:
        cfg = _make_config()
        assert cfg.api_secret.get_secret_value() == "test-secret"

    def test_env_loading(self) -> None:
        with patch.dict(
            "os.environ",
            {"KALSHI_API_KEY": "env-key", "KALSHI_API_SECRET": "env-secret"},
            clear=False,
        ):
            cfg = KalshiConfig()
            assert cfg.api_key == "env-key"
            assert cfg.api_secret.get_secret_value() == "env-secret"


class TestNormalizeApiResponse:
    def test_string_price_to_int(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "question": "Will it happen?",
            "outcome_prices": ["0.60", "0.40"],
            "volume": 1000,
            "open_interest": 500,
            "close_time": 1700000000,
            "state": "open",
            "event_ticker": "KX-EVENT",
        }
        result = _normalize_api_response(raw, Market)
        assert isinstance(result, Market)
        assert isinstance(result.close_time, datetime)

    def test_nested_list_normalization(self) -> None:
        raw = {
            "markets": [
                {
                    "ticker": "KX-1",
                    "question": "Q1",
                    "outcome_prices": ["0.55", "0.45"],
                    "volume": 200,
                    "open_interest": 100,
                    "close_time": 1700000000,
                    "state": "open",
                    "event_ticker": "KX-E",
                },
                {
                    "ticker": "KX-2",
                    "question": "Q2",
                    "outcome_prices": ["0.30", "0.70"],
                    "volume": 300,
                    "open_interest": 150,
                    "close_time": 1700001000,
                    "state": "closed",
                    "event_ticker": "KX-E2",
                },
            ]
        }
        result = _normalize_api_response(raw, MarketListResponse)
        assert isinstance(result, MarketListResponse)
        assert len(result.markets) == 2
        assert all(isinstance(m.close_time, datetime) for m in result.markets)

    def test_timestamp_int_to_datetime(self) -> None:
        raw = {
            "ticker": "KX-TS",
            "question": "Timestamp test?",
            "outcome_prices": ["0.50", "0.50"],
            "volume": 0,
            "open_interest": 0,
            "close_time": 1700000000,
            "state": "open",
            "event_ticker": "KX-E",
        }
        result = _normalize_api_response(raw, Market)
        expected = datetime.fromtimestamp(1700000000, tz=UTC)
        assert result.close_time == expected


class TestLogin:
    @respx.mock
    async def test_login_success(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(200, json={"token": "abc123"})
        )
        async with KalshiClient(cfg) as client:
            token = await client.login()
            assert token == "abc123"
            assert client._session_token == "abc123"

    @respx.mock
    async def test_login_401_raises_authentication_error(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(401, json={"msg": "unauthorized"})
        )
        async with KalshiClient(cfg) as client:
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.login()

    @respx.mock
    async def test_login_403_raises_authentication_error(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(403, json={"msg": "forbidden"})
        )
        async with KalshiClient(cfg) as client:
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.login()

    @respx.mock
    async def test_login_500_raises_status_error(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )
        async with KalshiClient(cfg) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.login()


class TestRequest:
    @respx.mock
    async def test_request_injects_auth_header(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok123"
            await client.get("/markets")
            assert route.calls[0].request.headers["authorization"] == "Bearer tok123"

    @respx.mock
    async def test_request_without_login_raises_auth_error(self) -> None:
        cfg = _make_config()
        async with KalshiClient(cfg) as client:
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                await client.get("/markets")

    @respx.mock
    async def test_retry_on_500_then_success(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets")
        route.side_effect = [
            httpx.Response(500, json={"error": "temp"}),
            httpx.Response(200, json={"markets": [], "cursor": None}),
        ]
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            response = await client.get("/markets")
            assert response.status_code == 200
            assert route.call_count == 2

    @respx.mock
    async def test_retry_exhaustion_raises(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets")
        route.mock(return_value=httpx.Response(500, json={"error": "down"}))
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            with pytest.raises(httpx.HTTPStatusError, match="500"):
                await client.get("/markets")
            assert route.call_count == cfg.max_retries + 1

    @respx.mock
    async def test_429_raises_rate_limit_error(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            with pytest.raises(RateLimitError):
                await client.get("/markets")

    @respx.mock
    async def test_401_in_request_raises_auth_error(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(401, json={"msg": "unauthorized"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            with pytest.raises(AuthenticationError):
                await client.get("/markets")


class TestRateLimiting:
    @respx.mock
    async def test_semaphore_limits_concurrency(self) -> None:
        cfg = _make_config()
        cfg.rate_limit_rps = 2.0
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            max_concurrent = 0
            current = 0

            async def tracked_request() -> None:
                nonlocal current, max_concurrent
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
                await client.get("/markets")
                current -= 1

            await asyncio.gather(*[tracked_request() for _ in range(5)])
            assert max_concurrent <= 2


class TestConvenienceMethods:
    @respx.mock
    async def test_get_passes_params(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            await client.get("/markets", state="open")
            assert "state=open" in str(route.calls[0].request.url)

    @respx.mock
    async def test_post_sends_json_body(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order_id": "ord1"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            resp = await client.post("/portfolio/orders", ticker="KX-T", side="yes")
            assert resp.status_code == 200


class TestContextManager:
    @respx.mock
    async def test_context_manager_closes_client(self) -> None:
        cfg = _make_config()
        client = KalshiClient(cfg)
        assert not client._client.is_closed
        await client.__aenter__()
        assert not client._client.is_closed
        await client.__aexit__(None, None, None)
        assert client._client.is_closed


class TestDemoMode:
    @respx.mock
    async def test_demo_mode_uses_demo_url(self) -> None:
        cfg = _make_config(demo_mode=True)
        route = respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(200, json={"token": "demo-tok"})
        )
        async with KalshiClient(cfg) as client:
            await client.login()
            assert client._session_token == "demo-tok"
        assert "demo-api" in str(route.calls[0].request.url)

    @respx.mock
    async def test_production_mode_uses_production_url(self) -> None:
        cfg = _make_config(demo_mode=False)
        route = respx.post(f"{cfg.active_url}/login").mock(
            return_value=httpx.Response(200, json={"token": "prod-tok"})
        )
        async with KalshiClient(cfg) as client:
            await client.login()
        assert "demo-api" not in str(route.calls[0].request.url)
