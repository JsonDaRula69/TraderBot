from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.kalshi_rest_fixtures import (
    historical_candle_payload,
    live_candle_payload,
    market_payload,
)
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill import BackfillPorts, BackfillRequest, run_backfill
from traderbot.kalshi.errors import AuthenticationError
from traderbot.kalshi.models import CutoffTimestamps
from traderbot.kalshi.rest_models import (
    ForecastHistoryResponse,
    HistoricalCandlestickResponse,
    LiveCandlestickResponse,
    MarketListResponse,
    SeriesListResponse,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 31, 12, tzinfo=UTC)


class FakeKalshiHistory:
    def __init__(self) -> None:
        self.live_candles: list[str] = []
        self.archive_candles: list[str] = []
        self.forecast_events: list[str] = []

    async def get_historical_cutoff(self) -> CutoffTimestamps:
        return CutoffTimestamps(
            market_settled_ts=datetime(2026, 6, 1, 0, 0, 0, 500000, tzinfo=UTC),
            trades_created_ts=datetime(2026, 6, 1, tzinfo=UTC),
            orders_updated_ts=datetime(2026, 6, 1, tzinfo=UTC),
        )

    async def get_series(self, category: str) -> SeriesListResponse:
        assert category == "weather"
        return SeriesListResponse.model_validate_json(
            json.dumps(
                {
                    "series": [
                        {
                            "ticker": "KXHIGHNY",
                            "frequency": "daily",
                            "title": "NYC high",
                            "category": "Weather",
                            "tags": [],
                            "settlement_sources": [],
                            "contract_url": "https://kalshi.com/contracts/KXHIGHNY",
                            "contract_terms_url": "https://kalshi.com/terms/KXHIGHNY",
                            "fee_type": "quadratic",
                            "fee_multiplier": 1.0,
                            "additional_prohibitions": [],
                        }
                    ]
                }
            )
        )

    async def get_markets(
        self,
        *,
        status: str,
        limit: int,
        cursor: str | None,
        series_ticker: str,
        min_settled_ts: int,
        max_settled_ts: int,
    ) -> MarketListResponse:
        return MarketListResponse.model_validate_json(
            json.dumps(
                {
                    "markets": [
                        {
                            **market_payload(),
                            "ticker": "KXHIGHNY-LIVE",
                            "open_time": "2026-06-02T00:00:00Z",
                            "close_time": "2026-06-30T00:00:00Z",
                            "settlement_ts": "2026-07-01T00:00:00Z",
                        }
                    ],
                    "cursor": "",
                }
            )
        )

    async def get_historical_markets(
        self, *, limit: int, cursor: str | None, series_ticker: str
    ) -> MarketListResponse:
        return MarketListResponse.model_validate_json(
            json.dumps(
                {
                    "markets": [
                        {
                            **market_payload(),
                            "ticker": "KXHIGHNY-ARCHIVE",
                            "open_time": "2026-03-01T00:00:00Z",
                            "close_time": "2026-04-30T00:00:00Z",
                            "settlement_ts": "2026-05-01T00:00:00Z",
                        }
                    ],
                    "cursor": "",
                }
            )
        )

    async def get_candlesticks(
        self, series_ticker: str, ticker: str, start_ts: int, end_ts: int, period_interval: int
    ) -> LiveCandlestickResponse:
        self.live_candles.append(ticker)
        candle = {**live_candle_payload(), "end_period_ts": 1782000000}
        return LiveCandlestickResponse.model_validate_json(
            json.dumps({"ticker": ticker, "candlesticks": [candle]})
        )

    async def get_historical_candlesticks(
        self, ticker: str, start_ts: int, end_ts: int, period_interval: int
    ) -> HistoricalCandlestickResponse:
        self.archive_candles.append(ticker)
        candle = {**historical_candle_payload(), "end_period_ts": 1775000000}
        return HistoricalCandlestickResponse.model_validate_json(
            json.dumps({"ticker": ticker, "candlesticks": [candle]})
        )

    async def get_forecast_percentile_history(
        self,
        series_ticker: str,
        event_ticker: str,
        start_ts: int,
        end_ts: int,
        percentiles: Sequence[int],
        period_interval: int,
    ) -> ForecastHistoryResponse:
        self.forecast_events.append(event_ticker)
        return ForecastHistoryResponse.model_validate_json(
            json.dumps(
                {
                    "forecast_history": [
                        {
                            "event_ticker": event_ticker,
                            "end_period_ts": 1786492800,
                            "period_interval": 60,
                            "percentile_points": [
                                {
                                    "percentile": 5000,
                                    "raw_numerical_forecast": "81.2500",
                                    "numerical_forecast": "81.20",
                                    "formatted_forecast": "81.2 F",
                                }
                            ],
                        }
                    ]
                }
            )
        )


class AuthFailingKalshiHistory(FakeKalshiHistory):
    async def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> LiveCandlestickResponse:
        raise AuthenticationError("sensitive backend message")


@pytest.mark.asyncio
async def test_kalshi_backfill_straddles_cutoff_and_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "traderbot.db"
    client = FakeKalshiHistory()
    pool = SQLiteConnectionPool()
    request = BackfillRequest(months=6, target_db=target, collector_db=None)
    ports = BackfillPorts(
        client=client,
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        first = await run_backfill(request, ports)
        second = await run_backfill(request, ports)
    finally:
        pool.shutdown()

    assert first.status == "complete", first.model_dump()
    assert first.kalshi.markets.inserted == 2
    assert first.kalshi.candlesticks.inserted == 2
    assert first.kalshi.forecast_history.inserted == 1
    assert second.kalshi.markets.inserted == 0
    assert second.kalshi.candlesticks.inserted == 0
    assert second.kalshi.forecast_history.inserted == 0
    assert client.live_candles == ["KXHIGHNY-LIVE", "KXHIGHNY-LIVE"]
    assert client.archive_candles == ["KXHIGHNY-ARCHIVE", "KXHIGHNY-ARCHIVE"]
    assert client.forecast_events == ["KXHIGHNY-26AUG11", "KXHIGHNY-26AUG11"]
    with sqlite3.connect(target) as connection:
        assert connection.execute(
            "SELECT raw_numerical_forecast, numerical_forecast FROM kalshi_forecast_history"
        ).fetchone() == ("81.2500", "81.20")


@pytest.mark.asyncio
async def test_systemic_detail_failure_stops_calls_and_preserves_committed_rows(
    tmp_path: Path,
) -> None:
    client = AuthFailingKalshiHistory()
    pool = SQLiteConnectionPool()
    ports = BackfillPorts(
        client=client,
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        result = await run_backfill(
            BackfillRequest(months=6, target_db=tmp_path / "target.db"), ports
        )
    finally:
        pool.shutdown()

    assert result.status == "partial"
    assert result.kalshi.markets.inserted == 2
    assert result.kalshi.candlesticks.inserted == 1
    assert result.failures[0].code == "kalshi_systemic_failure"
    assert "sensitive" not in result.model_dump_json()
    assert client.forecast_events == []
