"""Tests for traderbot.kalshi.client — KalshiClient, KalshiConfig, and helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
from pydantic import SecretStr
import pytest
import respx

from traderbot.kalshi.client import (
    AuthenticationError,
    KalshiClient,
    KalshiConfig,
    RateLimitError,
    _normalize_api_response,
)
from traderbot.kalshi.models import Decision, Market, MarketListResponse
def _make_config(demo_mode: bool = False) -> KalshiConfig:
    return KalshiConfig(
        api_key=SecretStr("test-key"),
        private_key_pem=SecretStr('-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCoCcbqADDnFz16\notOGSWGB/dwKH+KOdrnFTZwnuZ6qydDpzL21HCvhoJ+pDLeqceYn0VPliVA30dE3\nnLuQeU/E35a7a1e4J6oaZ2/51TX/i6cUeJVW4rDDJ4KEsT+CF+KwjClqQA1hhaDr\nncIGNGmzPCYcsN2u2Qis5s/bRbznbQQaWs9HaJsQpGdVhhdcC/veJr4UVCQW+IxF\nznGnlYMbslbNquGItpMnwcEOVdWddl/VceW4c/JtCIWjiuePgzW9fw1t34aJCb6d\nvol5/R9qeLDEhRorWBDGi/+TudiCFF/bfpa0xjiIt3SXt3jLYRavgL8GpRgnt2Ip\n57kfktP3AgMBAAECggEAIHU7AeoliA26J10aRJ8aAZT6ks4T4fbW7WCPYDD/j/fJ\nrc+JeVlGtJ9lF69ILtkvXtOVRAog/5c8tWRF6qM0IFAb+nnCiOTIe68tNvHTK1hb\nXp3oIs9I23lfQahHHybj97wrJ8XVj9fS/JANcUtge2mL5xDW0TZE8bjnv3AaDA13\nIQQ6o3SXLLjYxgcTRnH74re33ITwQUzHDPGMvMqhZ2J+8XgUXwv9DmI7XYYMBOza\nZYFuxLWsx0aX+Iv4X0vvzAOuV3v4TXSSRAppohRsD0Xc1MBOzwcdpceKtfMsHCLd\nxBwIYG50G6G+L5Cr20BwKyMrbJPWOt/KoKXMp5NxkQKBgQDmlEpGfBdBHbUr95UQ\n7ZUUVvfLihW9jPMF8mRcyEuovRfVB8FNiV8U/krjEqO0O58RbXKw+hXI4WqBlcHq\nKJoG0UgvUhDUTXQcDos4jqf5duGyqXSCuiTFqCPYlytrojJ9AxN1zW9RxheHbznw\nBasWcMZmdmOIarbrEw+9/ftGXwKBgQC6kF73GHaHPdwCn9m+Grd9PkSiflYqtyNO\nRiLX2m12GtGgp2qAYPhSiLAAYxYkJzzwfAVZJEgW4XnAXYt+eoAfxt+ZY2jwh86B\nzmxfASwNgiRESVoXCoK8Kolje63UfWC0fsuUz6l683ILbOgpDzwmeYI3Zz0yfziI\nZBsyAhppaQKBgQDLfBqAUYqEIJ9+CaQ3qDNkG8vaiCXffcAKg3smlmyOoTGjApEI\nyC5s7G1SL2Tg7azXSGtq24jWGnhPm8Xhy6sCUTcO67GGakQJbpxWcS6z7MIJVZpI\ns9U3yca4oc/j0OQVht1pnL6cv+CL2RCcTaRKzYOJcPktrl923P+Lf9R8qQKBgEgm\nRyOmSUh6Kti0+x9i860y5JY255nzY2sFArqZlZWEP6eytyRY3BAHHpG3wDtRFWcn\nf2X++wYmQtCbHLRYKa6gWZ7XbCEBVGKs8wo2yNOcjev+tiGNBgxBIwrfLNWtezWy\nh4bQXInZFjTG9G3Un319pldIzMj3nGRa2o2XdKFpAoGBANpN5rnk2l2+Q/uWhWzi\n1ha54CKx7xz3wDqhJmqZ40fhbclqgGYe98L8qsPYmSOjnY6c9qQKSqhvMR+ViPlX\nokB5V3NcblTl1yGUlwmOiBil0rhBfa0YhYXEt4w1BsIs4Vcz90RaSlb35iVTlEQE\niY2uHj5DU0P/+4tttvV0IjxP\n-----END PRIVATE KEY-----\n'),
        demo_mode=demo_mode,
        rate_limit_rps=10.0,
        max_retries=3,
        retry_base_delay=0.01,
    )
class TestKalshiConfig:
    def test_defaults(self) -> None:
        cfg = _make_config()
        assert cfg.base_url == "https://api.elections.kalshi.com/trade-api/v2"
        assert cfg.demo_url == "https://demo-api.kalshi.co/trade-api/v2"
        assert cfg.demo_mode is False
        assert cfg.rate_limit_rps == 10.0
        assert cfg.max_retries == 3
        assert cfg.retry_base_delay == 0.01

    def test_active_url_production(self) -> None:
        cfg = _make_config(demo_mode=False)
        assert cfg.active_url == "https://api.elections.kalshi.com/trade-api/v2"

    def test_active_url_demo(self) -> None:
        cfg = _make_config(demo_mode=True)
        assert cfg.active_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_private_key_pem_is_secret_str(self) -> None:
        cfg = _make_config()
        assert cfg.private_key_pem is not None

    def test_env_loading(self) -> None:
        with patch.dict(
            "os.environ",
            {"KALSHI_API_KEY": "env-key", "KALSHI_PRIVATE_KEY_PEM": "env-secret"},
            clear=False,
        ):
            cfg = KalshiConfig()
            assert cfg.api_key.get_secret_value() == "env-key"
            assert cfg.private_key_pem is not None  # private_key_pem loaded from env

    def test_extra_field_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            KalshiConfig(api_key=SecretStr("k"), private_key_pem=SecretStr("pem"), extra_field=True)
class TestNormalizeApiResponse:
    def test_string_price_to_int(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "question": "Will it happen?",
            "outcome_prices": ["0.60", "0.40"],
            "volume": 1000,
            "open_interest": 500,
            "close_time": 1700000000,
            "status": "open",
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
                    "status": "open",
                    "event_ticker": "KX-E",
                },
                {
                    "ticker": "KX-2",
                    "question": "Q2",
                    "outcome_prices": ["0.30", "0.70"],
                    "volume": 300,
                    "open_interest": 150,
                    "close_time": 1700001000,
                    "status": "closed",
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
            "status": "open",
            "event_ticker": "KX-E",
        }
        result = _normalize_api_response(raw, Market)
        expected = datetime.fromtimestamp(1700000000, tz=UTC)
        assert result.close_time == expected
class TestRSAAuth:
    @respx.mock
    async def test_auth_headers_in_production(self) -> None:
        """RSA-PSS auth headers are sent on every request in production mode."""
        cfg = _make_config(demo_mode=False)
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            await client.get("/markets")
            assert "kalshi-access-key" in route.calls[0].request.headers
            assert "kalshi-access-signature" in route.calls[0].request.headers
            assert "kalshi-access-timestamp" in route.calls[0].request.headers

    @respx.mock
    async def test_demo_mode_sends_api_key_no_rsa(self) -> None:
        """Demo mode sends KALSHI-ACCESS-KEY but not RSA-PSS signature headers."""
        cfg = _make_config(demo_mode=True)
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            await client.get("/markets")
            assert "kalshi-access-key" in route.calls[0].request.headers
            assert "kalshi-access-signature" not in route.calls[0].request.headers

    @respx.mock
    async def test_auth_error_on_401(self) -> None:
        """401 response raises AuthenticationError."""
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(401, json={"msg": "unauthorized"})
        )
        async with KalshiClient(cfg) as client:
            with pytest.raises(AuthenticationError, match="Auth failure"):
                await client.get("/markets")

    @respx.mock
    async def test_auth_error_on_403(self) -> None:
        """403 response raises AuthenticationError."""
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(403, json={"msg": "forbidden"})
        )
        async with KalshiClient(cfg) as client:
            with pytest.raises(AuthenticationError, match="Auth failure"):
                await client.get("/markets")
class TestRequest:
    @respx.mock
    async def test_request_injects_auth_header(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            
            await client.get("/markets")
            assert "kalshi-access-signature" in route.calls[0].request.headers

    @respx.mock
    @respx.mock
    async def test_demo_mode_skips_rsa_auth_headers(self) -> None:
        """Demo mode sends API key but not RSA-PSS signature headers."""
        cfg = _make_config(demo_mode=True)
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            response = await client.get("/markets")
            assert response.status_code == 200
            auth_headers = route.calls[0].request.headers
            assert "kalshi-access-key" in auth_headers
            assert "kalshi-access-signature" not in auth_headers

    @respx.mock
    async def test_retry_on_500_then_success(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets")
        route.side_effect = [
            httpx.Response(500, json={"error": "temp"}),
            httpx.Response(200, json={"markets": [], "cursor": None}),
        ]
        async with KalshiClient(cfg) as client:
            
            response = await client.get("/markets")
            assert response.status_code == 200
            assert route.call_count == 2

    @respx.mock
    async def test_retry_exhaustion_raises(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets")
        route.mock(return_value=httpx.Response(500, json={"error": "down"}))
        async with KalshiClient(cfg) as client:
            
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
            
            with pytest.raises(RateLimitError):
                await client.get("/markets")

    @respx.mock
    async def test_401_in_request_raises_auth_error(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(401, json={"msg": "unauthorized"})
        )
        async with KalshiClient(cfg) as client:
            
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
            
            await client.get("/markets", state="open")
            assert "status=open" in str(route.calls[0].request.url) or "state=open" in str(route.calls[0].request.url)

    @respx.mock
    async def test_post_sends_json_body(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order_id": "ord1"})
        )
        async with KalshiClient(cfg) as client:
            
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
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            await client.get("/markets")
        assert "demo-api" in str(route.calls[0].request.url)

    @respx.mock
    async def test_production_mode_uses_production_url(self) -> None:
        cfg = _make_config(demo_mode=False)
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            await client.get("/markets")
        assert "electionions" in str(route.calls[0].request.url) or "api.elections" in str(route.calls[0].request.url)
class TestDeepNormalizeStringCents:
    """Cover line 78: _deep_normalize converts string cents fields to int."""

    def test_string_cents_converted_to_int(self) -> None:
        ts = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
        raw = {
            "timestamp": int(ts.timestamp()),
            "ticker": "KX-TEST",
            "direction": "yes",
            "quantity": 10,
            "price": "65",
            "signal_strength": 0.8,
            "confidence": 0.75,
            "edge_estimate": 5.0,
            "risk_checks": {"position_limit": True},
            "outcome": "executed",
        }
        result = _normalize_api_response(raw, Decision)
        assert isinstance(result.price, int)
        assert result.price == 65
class TestHTTPErrorsInRetry:
    """Cover lines 167-168: httpx.HTTPError caught in retry loop."""

    @pytest.mark.asyncio
    async def test_connect_error_raises_after_retries(self) -> None:
        cfg = _make_config()
        async with KalshiClient(cfg) as client:
            
            with (
                patch.object(
                    client._client, "request", side_effect=httpx.ConnectError("refused")
                ),
                pytest.raises(httpx.ConnectError, match="refused"),
            ):
                await client.get("/markets")
