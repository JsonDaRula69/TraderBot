"""Tests for MarketService — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.markets import MarketService

CLOSE_TIME_2026_03_31 = 1775001599
TRADE_TS_2025_04_20 = 1745150400


def _make_config() -> KalshiConfig:
    return KalshiConfig(
        api_key=SecretStr("test-key"),
        private_key_pem=None,
        demo_mode=True,
        rate_limit_rps=10.0,
        retry_base_delay=0.01,
    )


SAMPLE_MARKET_RAW = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "question": "Will BTC touch $55,000 before March 31?",
    "last_price_dollars": "0.65",
    "yes_bid_dollars": "0.64",
    "yes_ask_dollars": "0.66",
    "no_bid_dollars": "0.34",
    "no_ask_dollars": "0.36",
    "volume": 15000,
    "open_interest": 2500,
    "close_time": CLOSE_TIME_2026_03_31,
    "status": "active",
    "event_ticker": "KXBTCD-26MAR31",
    "category": "crypto",
}


SAMPLE_ORDERBOOK_RAW = {
    "yes_bids": [[64, 100], [63, 200]],
    "yes_asks": [[66, 150], [67, 100]],
    "no_bids": [[34, 100], [33, 200]],
    "no_asks": [[36, 150], [37, 100]],
}


class TestListMarkets:
    @respx.mock
    async def test_returns_empty_list(self) -> None:
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


class TestListMarketsByCategory:

    @respx.mock
    async def test_fetches_category_with_nested_markets(self) -> None:
        cfg = _make_config()
        base = cfg.active_url

        respx.get(f"{base}/series").mock(
            return_value=httpx.Response(200, json={
                "series": [{"ticker": "KXTRUMPMENTION", "title": "Trump Mention"}],
            })
        )
        respx.get(f"{base}/events").mock(
            return_value=httpx.Response(200, json={
                "events": [{
                    "ticker": "KXTRUMPMENTION-26MAY11",
                    "title": "What will Trump say?",
                    "category": "Mentions",
                    "state": "open",
                    "markets_count": 2,
                    "markets": [
                        {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-TRUM", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None, "status": "active"},
                        {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-BOBB", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None, "status": "active"},
                    ],
                }],
                "cursor": None,
            })
        )

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets_by_category(category="Mentions")

        assert len(result.markets) == 2
        assert result.markets[0].category == "Mentions"
        assert result.markets[0].market_category.value == "mentions"
        assert result.markets[1].category == "Mentions"

    @respx.mock
    async def test_no_events_returns_empty(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/series").mock(
            return_value=httpx.Response(200, json={"series": []})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets_by_category(category="crypto")

        assert result.markets == []

    @respx.mock
    async def test_deduplicates_markets_across_events(self) -> None:
        cfg = _make_config()
        base = cfg.active_url

        market_raw = {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-TRUM", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None, "status": "active"}
        respx.get(f"{base}/series").mock(
            return_value=httpx.Response(200, json={
                "series": [{"ticker": "KXTRUMPMENTION", "title": "Trump Mention"}],
            })
        )
        respx.get(f"{base}/events").mock(
            return_value=httpx.Response(200, json={
                "events": [
                    {
                        "ticker": "KXTRUMPMENTION-26MAY11",
                        "title": "Event 1",
                        "category": "Mentions",
                        "state": "open",
                        "markets_count": 1,
                        "markets": [market_raw],
                    },
                    {
                        "ticker": "KXTRUMPMENTION-26MAY10",
                        "title": "Event 2",
                        "category": "Mentions",
                        "state": "open",
                        "markets_count": 1,
                        "markets": [market_raw],
                    },
                ],
                "cursor": None,
            })
        )

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets_by_category(category="Mentions")

        assert len(result.markets) == 1

    @respx.mock
    async def test_filters_out_finalized_markets(self) -> None:
        cfg = _make_config()
        base = cfg.active_url

        respx.get(f"{base}/series").mock(
            return_value=httpx.Response(200, json={
                "series": [{"ticker": "KXTRUMPMENTION", "title": "Trump Mention"}],
            })
        )
        respx.get(f"{base}/events").mock(
            return_value=httpx.Response(200, json={
                "events": [{
                    "ticker": "KXTRUMPMENTION-26MAY11",
                    "title": "What will Trump say?",
                    "category": "Mentions",
                    "state": "open",
                    "markets_count": 3,
                    "markets": [
                        {**SAMPLE_MARKET_RAW, "ticker": "ACTIVE-1", "status": "active"},
                        {**SAMPLE_MARKET_RAW, "ticker": "FINALIZED-1", "status": "finalized"},
                        {**SAMPLE_MARKET_RAW, "ticker": "CLOSED-1", "status": "closed"},
                    ],
                }],
            })
        )

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets_by_category(category="Mentions")

        assert len(result.markets) == 1
        assert result.markets[0].ticker == "ACTIVE-1"


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
        assert market.status == "open"
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
    async def test_handles_v2_fields(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": {
                **SAMPLE_MARKET_RAW,
                "title": "Will BTC touch $55k?",
                "price": "0.64",
                "count": "10",
            }})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            market = await service.get_market("KXBTCD-26MAR31-T55000")

        assert market.question == "Will BTC touch $55k?"


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
            orderbook = await service.get_orderbook("KXBTCD-26MAR31-T55000")

        assert len(orderbook.yes_bids) == 2
        assert orderbook.yes_bids[0].price == 64
        assert orderbook.yes_bids[0].size == 100
        assert len(orderbook.no_bids) == 2

    @respx.mock
    async def test_handles_v2_field_names(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/KXBTCD-26MAR31-T55000/orderbook").mock(
            return_value=httpx.Response(200, json={
                "yes": [[65, 200]],
                "no": [[35, 300]],
            })
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            orderbook = await service.get_orderbook("KXBTCD-26MAR31-T55000")

        assert len(orderbook.yes_bids) == 1
        assert orderbook.yes_bids[0].price == 65
        assert len(orderbook.no_bids) == 1
        assert orderbook.no_bids[0].price == 35


class TestStringPriceNormalization:
    def test_dollar_format_normalization(self) -> None:
        from traderbot.kalshi._normalize import _normalize_market
        market = _normalize_market({
            "ticker": "KXTEST",
            "question": "Test?",
            "last_price_dollars": "0.64",
            "yes_bid_dollars": "0.63",
            "yes_ask_dollars": "0.65",
            "no_bid_dollars": "0.35",
            "no_ask_dollars": "0.37",
            "volume": 1000,
            "open_interest": 500,
            "close_time": CLOSE_TIME_2026_03_31,
            "status": "active",
            "event_ticker": "KXTEST",
            "category": "crypto",
        })
        assert market.volume == 1000
        assert market.open_interest == 500


class TestGetRecentTrades:
    @respx.mock
    async def test_returns_trades(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={
                "trades": [{
                    "ticker": "KXBTCD-26MAR31-T55000",
                    "price": "0.65",
                    "count": "5",
                    "timestamp": TRADE_TS_2025_04_20,
                    "side": "yes",
                }],
                "cursor": None,
            })
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.get_recent_trades("KXBTCD-26MAR31-T55000")

        assert len(result.trades) == 1
        assert result.trades[0].ticker == "KXBTCD-26MAR31-T55000"