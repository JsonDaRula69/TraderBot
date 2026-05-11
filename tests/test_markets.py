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
        private_key_pem=SecretStr('-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDNjtDWFqzW5zUP\ngtqTevUWEgvoW3iCBruf8qOB21eIEOLKvqQdqMWzInkR1hWZKWrmfDwFGU//fx6C\nPPpB/Mr/EYzc/MsIHm1IqkP03YwbpMYfBX+FHmlIfMUBTrb1WmsJ+ho8n6V/pn9V\nTVI2sL6m6gffKML/VEopp0l3OWvCG5GYxKcAXgo4aMhM573QmPJ2TbGLzsg8SUkx\nGZlYBh2Qtx4VuIJ8Bi6cK/An/Oae8h4AL5/23A82gj8eef8X+szHX++PMS8nS0YK\n2ZmTi4bCi33DB8CPRAH9xzhC0NkLCNqD1hp6VWeky4DnLteQuLITvXuU5GwjkQYl\nLIYUSgbDAgMBAAECggEAK/AZipGJO1xrdpfRUdHn/mI4ImAe96gpxcwvEAxK/v4h\nBBZQ7TgMnjhBqcLZlgYI4CBxEePxuhq5cjxHgABhgbkGI5xzZ5ZdZLlkUjxi/Oux\nH6NkuRchiQmGcLubFwHPPHA12HyFey4jLKAc8SzBa9s9eIF1gO9K9PFZnj7rXi91\nBjaFm6jpHlEDeLY7oCT033HJxi7wvEflCz0J+j4lSf6XUM8rhgiApKOwwsYwFwZT\nynKxyj3rAf8wDHY/vTNdO984T2bD/eEymCyqDnXEY/zzMnrUDMwyRe+cm1HsfvE8\ns83x7EA6EPFwhEf796mCth7fLFbBOlsEMaPGTNjxYQKBgQD4JJbth+jyKihc/L5N\nS/BnGxUxIhKYbTS1uEPDqT5X/aMhgaxGY63AiOwQYoy1gfMN04zjE+dtH4I6ZUWH\nx4WcUlFciBqdVs479iVIMeIVULcwTzSCnWgPVF+fvaB+98oPPEj+USlcWhKTtcHj\nC2voN6qHOTpNQenlE2yIS79JYQKBgQDUEQm3tn2BHMAI5BwFENBmp1AzJgFk64gV\ngKxwUUH7ks5feSXXLc75ZfamR6oD5eGwqon4rFHf9cqg2ZUGhjXu0dQxVqeLSaej\nUzU9uZDnLvAfTRnMuy+nS3dR//Bd3Ee1nTqkQenD8dWi/nwuuQIl7L+EMZkBVqko\nIS73DlsOowKBgGZYAP/a7FLk3FztyTdsOKzt2KG5Id5IPFMuupQ6e4IjFGM/bmRh\nvEoKrwJbAxnhjPOI6zTFAtBZDIc1OaY0voCo2vHFGOUH5muIq/vIxyxva/66zDeK\n4F5iOEZUGZwEaww5mwl5RAvZAox1jJAuJ8VRID5BdjBjHSrkBgF47F5BAoGAZnc9\nDMleZu4vU5x0dXYkXBVnyO8KKWssu8cKitKYYSgUE0mEIS5/HT5JKRrjaTLAFA6y\nz7bjcKVgnMvFF/vtP1Gfh59pIQIbv+zKguKQw0OIvncQij2/zsPGCZby20c+VuB7\nnzZB722AXls8QY8fHJgCCau1VFI9Naii+rizAqUCgYEAuo3UCkhZdyU5yAK431yC\nzUFIT+WIaADq7UKi8+czvIv5SqQv1nNcLHHrzg0NXXDAVFAFwtwD/nho91MKH667\nVAiz14bK+fVXaSbUq1GMTj8QHq8VLRK56iMcY8FyY8mWyHgPa842l5b9ygZktkXg\nfoC58VQaR20DGjpjGUyXpoQ=\n-----END PRIVATE KEY-----\n'),
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
    "status": "open",
    "event_ticker": "KXBTCD-26MAR31",
    "category": "crypto",
}

SAMPLE_ORDERBOOK_RAW = {
    "yes_bids": [[64, 100], [63, 250], [62, 500]],
    "no_bids": [[36, 150], [37, 200], [38, 300]],
}

SAMPLE_TRADE_RAW = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "price_dollars": "0.65",
    "count_fp": 10.0,
    "side": "yes",
    "timestamp": TRADE_TS_2025_04_20,
}

SAMPLE_TRADE_RAW_2 = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "price_fp": 63.0,
    "count_fp": 5.0,
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
            await service.list_markets(status="open", event_ticker="KXBTCD-26MAR31")

        request_url = str(route.calls[0].request.url)
        assert "status=open" in request_url
        assert "event_ticker=KXBTCD" in request_url

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


class TestListMarketsByCategory:

    @respx.mock
    async def test_fetches_series_then_events_then_markets(self) -> None:
        cfg = _make_config()
        base = cfg.active_url

        respx.get(f"{base}/series").mock(
            return_value=httpx.Response(200, json={
                "series": [{"ticker": "KXTRUMPMENTION", "title": "Trump Mention", "category": "Mentions"}],
                "cursor": None,
            })
        )
        respx.get(f"{base}/events").mock(
            return_value=httpx.Response(200, json={
                "events": [{"ticker": "KXTRUMPMENTION-26MAY11", "title": "What will Trump say?", "category": "Mentions", "state": "open", "markets_count": 2}],
            })
        )
        respx.get(f"{base}/markets").mock(
            return_value=httpx.Response(200, json={
                "markets": [
                    {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-TRUM", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None},
                    {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-BOBB", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None},
                ],
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
    async def test_no_series_returns_empty(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/series").mock(
            return_value=httpx.Response(200, json={"series": [], "cursor": None})
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

        respx.get(f"{base}/series").mock(
            return_value=httpx.Response(200, json={
                "series": [{"ticker": "KXTRUMPMENTION", "title": "Trump", "category": "Mentions"}],
                "cursor": None,
            })
        )
        respx.get(f"{base}/events").mock(
            return_value=httpx.Response(200, json={
                "events": [
                    {"ticker": "KXTRUMPMENTION-26MAY11", "title": "Event 1", "category": "Mentions", "state": "open", "markets_count": 1},
                    {"ticker": "KXTRUMPMENTION-26MAY10", "title": "Event 2", "category": "Mentions", "state": "open", "markets_count": 1},
                ],
            })
        )
        market_raw = {**SAMPLE_MARKET_RAW, "ticker": "KXTRUMPMENTION-26MAY11-TRUM", "event_ticker": "KXTRUMPMENTION-26MAY11", "category": None}
        respx.get(f"{base}/markets").mock(
            return_value=httpx.Response(200, json={"markets": [market_raw], "cursor": None})
        )

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.list_markets_by_category(category="Mentions")

        assert len(result.markets) == 1


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
            "yes_bids": [["0.64", "100"], ["0.63", "250"]],
            "no_bids": [["0.36", "150"], ["0.37", "200"]],
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
        respx.get(f"{cfg.active_url}/markets/trades").mock(
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
        respx.get(f"{cfg.active_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": [SAMPLE_TRADE_RAW], "cursor": "page2"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = MarketService(client)
            result = await service.get_recent_trades("KXBTCD-26MAR31-T55000", cursor="page1")

        assert len(result.trades) == 1
        assert result.cursor == "page2"
