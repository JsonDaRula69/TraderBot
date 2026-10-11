from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.kalshi_rest_fixtures import live_candle_payload, market_payload
from tests.test_backfill_kalshi import FakeKalshiHistory, FixedClock
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill import BackfillPorts, BackfillRequest, run_backfill
from traderbot.deploy.backfill_discovery import (
    KalshiBackfillError,
    MarketCandidate,
    _merge,
)
from traderbot.kalshi.models import CutoffTimestamps
from traderbot.kalshi.rest_models import (
    ForecastHistoryResponse,
    KalshiMarket,
    LiveCandlestickResponse,
    MarketListResponse,
)


def _market(**updates: str) -> KalshiMarket:
    return KalshiMarket.model_validate_json(json.dumps({**market_payload(), **updates}))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            MarketCandidate(
                _market(occurrence_datetime="2026-07-01T12:00:00Z"), "KXONE", "current"
            ),
            MarketCandidate(
                _market(occurrence_datetime="2026-07-02T12:00:00Z"), "KXONE", "current"
            ),
        ),
        (
            MarketCandidate(_market(), "KXONE", "current"),
            MarketCandidate(_market(), "KXTWO", "current"),
        ),
        (
            MarketCandidate(_market(), "KXONE", "current"),
            MarketCandidate(_market(), "KXONE", "archive"),
        ),
    ],
)
def test_duplicate_ticker_conflicts_include_payload_series_and_tier(
    first: MarketCandidate, second: MarketCandidate
) -> None:
    with pytest.raises(KalshiBackfillError, match="conflicting_market_ticker"):
        _ = _merge([first, second])


def test_exact_duplicate_market_candidate_deduplicates() -> None:
    candidate = MarketCandidate(_market(), "KXONE", "current")

    assert _merge([candidate, candidate]) == (candidate,)


def test_unknown_additive_market_fields_do_not_create_false_conflicts() -> None:
    first = MarketCandidate(_market(future_addition="one"), "KXONE", "current")
    second = MarketCandidate(_market(future_addition="two"), "KXONE", "current")

    assert _merge([first, second]) == (first,)


class _ConflictKalshi(FakeKalshiHistory):
    def __init__(self) -> None:
        super().__init__()
        self.detail_calls = 0

    async def get_historical_cutoff(self) -> CutoffTimestamps:
        value = datetime(2026, 1, 1, tzinfo=UTC)
        return CutoffTimestamps(
            market_settled_ts=value,
            trades_created_ts=value,
            orders_updated_ts=value,
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
        _ = (status, limit, cursor, series_ticker, min_settled_ts, max_settled_ts)
        common = {
            **market_payload(),
            "ticker": "KX-CONFLICT",
            "open_time": "2026-06-01T00:00:00Z",
            "close_time": "2026-06-30T00:00:00Z",
            "settlement_ts": "2026-07-01T00:00:00Z",
        }
        return MarketListResponse.model_validate_json(
            json.dumps(
                {
                    "markets": [
                        {**common, "occurrence_datetime": "2026-06-29T00:00:00Z"},
                        {**common, "occurrence_datetime": "2026-06-30T00:00:00Z"},
                    ],
                    "cursor": "",
                }
            )
        )

    async def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> LiveCandlestickResponse:
        self.detail_calls += 1
        return await super().get_candlesticks(
            series_ticker, ticker, start_ts, end_ts, period_interval
        )


@pytest.mark.asyncio
async def test_market_conflict_aborts_before_details_and_storage(tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    client = _ConflictKalshi()
    pool = SQLiteConnectionPool()
    try:
        result = await run_backfill(
            BackfillRequest(months=6, target_db=target),
            BackfillPorts(
                client=client,
                pool=pool,
                clock=FixedClock(),
                default_collector_path=tmp_path / "missing.db",
            ),
        )
    finally:
        pool.shutdown()

    assert result.status == "failure"
    assert client.detail_calls == 0
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM kalshi_markets").fetchone() == (0,)


class _OverReturningKalshi(_ConflictKalshi):
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
        _ = (status, limit, cursor, series_ticker, min_settled_ts, max_settled_ts)
        return MarketListResponse.model_validate_json(
            json.dumps(
                {
                    "markets": [
                        {
                            **market_payload(),
                            "ticker": "KX-BOUNDS",
                            "open_time": "2026-01-01T00:00:00Z",
                            "close_time": "2026-08-31T11:59:59Z",
                            "settlement_ts": "2026-08-31T11:59:59.500000Z",
                        }
                    ],
                    "cursor": "",
                }
            )
        )

    async def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> LiveCandlestickResponse:
        _ = (series_ticker, start_ts, end_ts, period_interval)
        start = int(datetime(2026, 2, 28, 12, tzinfo=UTC).timestamp())
        end = int(datetime(2026, 8, 31, 12, tzinfo=UTC).timestamp())
        candles = [
            {**live_candle_payload(), "end_period_ts": timestamp}
            for timestamp in (start - 1, start, end - 1, end)
        ]
        return LiveCandlestickResponse.model_validate({"ticker": ticker, "candlesticks": candles})

    async def get_forecast_percentile_history(
        self,
        series_ticker: str,
        event_ticker: str,
        start_ts: int,
        end_ts: int,
        percentiles: Sequence[int],
        period_interval: int,
    ) -> ForecastHistoryResponse:
        _ = (series_ticker, start_ts, end_ts, percentiles, period_interval)
        start = int(datetime(2026, 2, 28, 12, tzinfo=UTC).timestamp())
        end = int(datetime(2026, 8, 31, 12, tzinfo=UTC).timestamp())
        points = [
            {
                "event_ticker": event_ticker,
                "end_period_ts": timestamp,
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
            for timestamp in (start - 1, start, end - 1, end)
        ]
        return ForecastHistoryResponse.model_validate_json(json.dumps({"forecast_history": points}))


@pytest.mark.asyncio
async def test_candles_and_forecasts_are_final_filtered_to_window(tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    pool = SQLiteConnectionPool()
    try:
        result = await run_backfill(
            BackfillRequest(months=6, target_db=target),
            BackfillPorts(
                client=_OverReturningKalshi(),
                pool=pool,
                clock=FixedClock(),
                default_collector_path=tmp_path / "missing.db",
            ),
        )
    finally:
        pool.shutdown()

    start = int(datetime(2026, 2, 28, 12, tzinfo=UTC).timestamp())
    end = int(datetime(2026, 8, 31, 12, tzinfo=UTC).timestamp())
    assert not result.failures, result.failures
    assert result.status == "complete", result.model_dump()
    assert result.kalshi.candlesticks.seen == 2
    assert result.kalshi.forecast_history.seen == 2
    assert result.api.candlesticks == 4
    assert result.api.forecasts == 4
    assert "kalshi_candlesticks_skipped_out_of_window=2" in result.warnings
    assert "kalshi_forecast_points_skipped_out_of_window=2" in result.warnings
    with sqlite3.connect(target) as connection:
        candle_times = connection.execute(
            "SELECT end_period_ts FROM kalshi_candlesticks ORDER BY end_period_ts"
        ).fetchall()
        forecast_times = connection.execute(
            "SELECT end_period_ts FROM kalshi_forecast_history ORDER BY end_period_ts"
        ).fetchall()
    assert candle_times == [(start,), (end - 1,)]
    assert forecast_times == [(start,), (end - 1,)]
