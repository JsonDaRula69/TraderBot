"""Tests for MarketService — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.markets import MarketService

CLOSE_TIME_2026_03_31 = 1775001599
TRADE_TS_2025_04_20 = 1745150400


def _make_config() -> KalshiConfig:
    return KalshiConfig(
        api_key="test-key",
        api_secret="test-secret",
        rate_limit_rps=10.0,
        retry_base_delay=0.01,
    )


SAMPLE_MARKET_RAW = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "question": "Will BTC touch $55,000 before March 31?",
    "outcome_prices": ["0.65", "0.35"],
    "volume": 15000,
    "open_interest": 2500,
    "close_time": CLOSE_TIME_2026_03_31,
    "state": "open",
    "event_ticker": "KXBTCD-26MAR31",
    "category": "crypto",
}

SAMPLE_ORDERBOOK_RAW = {
    "yes_bids": [[64, 100], [63, 250], [62, 500]],
    "no_bids": [[36, 150], [37, 200], [38, 300]],
}

SAMPLE_TRADE_RAW = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "yes_price": 65,
    "count": 10,
    "side": "yes",
    "timestamp": TRADE_TS_2025_04_20,
}

SAMPLE_TRADE_RAW_2 = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "price": 63,
    "quantity": 5,
    "side": "no",
    "created_time": TRADE_TS_2025_04_20,
}


class TestListMarkets:
    @respx.mock
    async def test_returns_market_list(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(
                200, json={"markets": [SAMPLE_MARKET_RAW], "cursor": "abc123"}
            )
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets()

        assert len(result.markets) == 1
        assert result.markets[0].ticker == "KXBTCD-26MAR31-T55000"
        assert result.cursor == "abc123"
        assert result.markets[0].close_time == datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC)

    @respx.mock
    async def test_passes_filter_params(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            await service.list_markets(category="crypto", state="open")

        request_url = str(route.calls[0].request.url)
        assert "category=crypto" in request_url
        assert "state=open" in request_url

    @respx.mock
    async def test_empty_list(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [], "cursor": None})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets()

        assert result.markets == []
        assert result.cursor is None


class TestGetMarket:
    @respx.mock
    async def test_returns_single_market(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": SAMPLE_MARKET_RAW})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            market = await service.get_market("KXBTCD-26MAR31-T55000")

        assert market.ticker == "KXBTCD-26MAR31-T55000"
        assert market.state == "open"
        assert isinstance(market.close_time, datetime)

    @respx.mock
    async def test_404_raises(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/INVALID").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            with pytest.raises(httpx.HTTPStatusError):
                await service.get_market("INVALID")

    @respx.mock
    async def test_flat_response_fallback(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json=SAMPLE_MARKET_RAW)
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.get_market("KXBTCD-26MAR31-T55000")

        assert result.ticker == "KXBTCD-26MAR31-T55000"


class TestGetOrderbook:
    @respx.mock
    async def test_returns_orderbook(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/orderbook").mock(
            return_value=httpx.Response(200, json=SAMPLE_ORDERBOOK_RAW)
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            ob = await service.get_orderbook("KXBTCD-26MAR31-T55000")

        assert len(ob.yes_bids) == 3
        assert ob.yes_bids[0].price == 64
        assert ob.yes_bids[0].size == 100
        assert len(ob.no_bids) == 3

    @respx.mock
    async def test_string_price_normalization(self) -> None:
        orderbook_raw = {
            "yes_bids": [["64", "100"], ["63", "250"]],
            "no_bids": [["36", "150"], ["37", "200"]],
        }
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/orderbook").mock(
            return_value=httpx.Response(200, json=orderbook_raw)
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            ob = await service.get_orderbook("KXBTCD-26MAR31-T55000")

        assert ob.yes_bids[0].price == 64
        assert ob.yes_bids[0].size == 100

    @respx.mock
    async def test_empty_orderbook(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KX-EMPTY/orderbook").mock(
            return_value=httpx.Response(200, json={"yes_bids": [], "no_bids": []})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            ob = await service.get_orderbook("KX-EMPTY")

        assert ob.yes_bids == []
        assert ob.no_bids == []

    @respx.mock
    async def test_alt_keys_yes_no(self) -> None:
        alt_orderbook = {
            "yes": [[65, 50], [64, 100]],
            "no": [[35, 75], [36, 125]],
        }
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/orderbook").mock(
            return_value=httpx.Response(200, json=alt_orderbook)
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            ob = await service.get_orderbook("KXBTCD-26MAR31-T55000")

        assert len(ob.yes_bids) == 2
        assert ob.yes_bids[0].price == 65


class TestGetRecentTrades:
    @respx.mock
    async def test_returns_trades(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/trades").mock(
            return_value=httpx.Response(
                200,
                json={"trades": [SAMPLE_TRADE_RAW, SAMPLE_TRADE_RAW_2], "cursor": "next_page"},
            )
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.get_recent_trades("KXBTCD-26MAR31-T55000")

        assert len(result.trades) == 2
        assert result.trades[0].price == 65
        assert result.trades[0].quantity == 10
        assert result.trades[0].side == "yes"
        assert result.trades[0].timestamp == datetime(2025, 4, 20, 12, 0, 0, tzinfo=UTC)
        assert result.trades[1].price == 63
        assert result.trades[1].quantity == 5
        assert result.cursor == "next_page"

    @respx.mock
    async def test_pagination(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/trades").mock(
            return_value=httpx.Response(200, json={"trades": [SAMPLE_TRADE_RAW], "cursor": "page2"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.get_recent_trades("KXBTCD-26MAR31-T55000", cursor="page1")

        assert len(result.trades) == 1
        assert result.cursor == "page2"
