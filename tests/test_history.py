"""Tests for HistoryService — cutoffs, historical trades, settled markets."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx
from pydantic import SecretStr

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.history import HistoryService

CLOSE_TIME_2026_03_31 = 1775001599
TRADE_TS_2025_04_20 = 1745150400
SETTLED_TS = 1775001600
CUTOFF_TRADE_TS = 1774900000
CUTOFF_ORDER_TS = 1774800000


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
    "status": "settled",
    "event_ticker": "KXBTCD-26MAR31",
    "category": "crypto",
    "settlement_result": True,
}

SAMPLE_MARKET_WITH_CUTOFFS = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "question": "Will BTC touch $55,000?",
    "outcome_prices": ["0.5", "0.5"],
    "volume": 100,
    "open_interest": 50,
    "close_time": CLOSE_TIME_2026_03_31,
    "status": "open",
    "event_ticker": "KXBTCD-26MAR31",
    "market_settled_ts": SETTLED_TS,
    "trade_cutoff_ts": CUTOFF_TRADE_TS,
    "order_cutoff_ts": CUTOFF_ORDER_TS,
}

SAMPLE_TRADE_RAW = {
    "ticker": "KXBTCD-26MAR31-T55000",
    "price_fp": "0.65",
    "count_fp": 10,
    "side": "yes",
    "timestamp": TRADE_TS_2025_04_20,
}

SAMPLE_SETTLED_MARKET_RAW = {
    "ticker": "KXELEC-24NOV05-SENATE",
    "question": "Which party controls the Senate after 2026?",
    "outcome_prices": ["0.58", "0.42"],
    "volume": 320000,
    "open_interest": 45000,
    "close_time": CLOSE_TIME_2026_03_31,
    "status": "settled",
    "event_ticker": "KXELEC-24NOV05",
    "category": "politics",
    "settlement_result": False,
}


class TestGetCutoffs:
    @respx.mock
    async def test_get_cutoffs_with_timestamps(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": SAMPLE_MARKET_WITH_CUTOFFS})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_cutoffs("KXBTCD-26MAR31-T55000")

        assert result.market_settled_ts is not None
        assert result.trade_cutoff_ts is not None
        assert result.order_cutoff_ts is not None

    @respx.mock
    async def test_get_cutoffs_missing_fields(self) -> None:
        cfg = _make_config()
        market_without_cutoffs = {
            "ticker": "KXBTCD-26MAR31-T55000",
            "question": "Will BTC touch $55,000?",
            "outcome_prices": ["0.5", "0.5"],
            "volume": 100,
            "open_interest": 50,
            "close_time": CLOSE_TIME_2026_03_31,
            "status": "open",
            "event_ticker": "KXBTCD-26MAR31",
        }
        respx.get(f"{cfg.base_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": market_without_cutoffs})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_cutoffs("KXBTCD-26MAR31-T55000")

        assert result.market_settled_ts is None
        assert result.trade_cutoff_ts is None
        assert result.order_cutoff_ts is None

    @respx.mock
    async def test_get_cutoffs_partial_fields(self) -> None:
        cfg = _make_config()
        market_partial = {**SAMPLE_MARKET_RAW, "market_settled_ts": SETTLED_TS}
        respx.get(f"{cfg.base_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": market_partial})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_cutoffs("KXBTCD-26MAR31-T55000")

        assert result.market_settled_ts is not None
        assert result.trade_cutoff_ts is None
        assert result.order_cutoff_ts is None


class TestGetHistoricalTrades:
    @respx.mock
    async def test_get_historical_trades_basic(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": [SAMPLE_TRADE_RAW], "cursor": "page2"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_historical_trades("KXBTCD-26MAR31-T55000")

        assert len(result.trades) == 1
        assert result.trades[0].price == 65
        assert result.trades[0].quantity == 10
        assert result.trades[0].side == "yes"
        assert result.trades[0].timestamp == datetime(2025, 4, 20, 12, 0, 0, tzinfo=UTC)
        assert result.cursor == "page2"

    @respx.mock
    async def test_get_historical_trades_with_time_filters(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.base_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": [SAMPLE_TRADE_RAW], "cursor": None})
        )
        after = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        before = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_historical_trades(
                "KXBTCD-26MAR31-T55000", after=after, before=before
            )

        assert route.called
        assert len(result.trades) == 1

    @respx.mock
    async def test_get_historical_trades_date_serialization(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.base_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": []})
        )
        after = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)

        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            await service.get_historical_trades("KXBTCD-26MAR31-T55000", after=after)

        request_url = str(route.calls[0].request.url)
        assert "min_ts" in request_url

    @respx.mock
    async def test_get_historical_trades_empty(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": []})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_historical_trades("KXBTCD-26MAR31-T55000")

        assert len(result.trades) == 0


class TestGetSettledMarkets:
    @respx.mock
    async def test_get_settled_markets(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets").mock(
            return_value=httpx.Response(
                200, json={"markets": [SAMPLE_SETTLED_MARKET_RAW], "cursor": "next"}
            )
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_settled_markets()

        assert len(result.markets) == 1
        assert result.markets[0].status == "settled"
        assert result.markets[0].settlement_result is False

    @respx.mock
    async def test_get_settled_markets_empty(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_settled_markets()

        assert len(result.markets) == 0

    @respx.mock
    async def test_get_settled_markets_with_cursor(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.base_url}/markets").mock(
            return_value=httpx.Response(
                200, json={"markets": [SAMPLE_SETTLED_MARKET_RAW]}
            )
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            await service.get_settled_markets(cursor="page2")

        assert route.called
        assert "cursor=page2" in str(route.calls[0].request.url)

    @respx.mock
    async def test_get_historical_trades_with_cursor(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.base_url}/markets/trades").mock(
            return_value=httpx.Response(
                200, json={"trades": [SAMPLE_TRADE_RAW]}
            )
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            await service.get_historical_trades("KX-TEST", cursor="abc123")

        assert route.called
        assert "cursor=abc123" in str(route.calls[0].request.url)


class TestGetMarketSeries:
    @respx.mock
    async def test_get_market_series(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/markets/KXBTCD-26MAR31-T55000").mock(
            return_value=httpx.Response(200, json={"market": SAMPLE_MARKET_RAW})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = HistoryService(client)
            result = await service.get_market_series("KXBTCD-26MAR31-T55000")

        assert result.ticker == "KXBTCD-26MAR31-T55000"
        assert result.status == "settled"
        assert result.settlement_result is True
