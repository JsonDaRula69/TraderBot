from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_backfill_kalshi import FakeKalshiHistory, FixedClock
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill import BackfillPorts, BackfillRequest, run_backfill
from traderbot.kalshi.errors import KalshiAPIError
from traderbot.kalshi.rest_models import HistoricalCandlestickResponse, MarketListResponse


class MissingArchiveCandleKalshi(FakeKalshiHistory):
    async def get_historical_candlesticks(
        self,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> HistoricalCandlestickResponse:
        raise KalshiAPIError(
            "sensitive raw detail",
            code="not_found",
            details="private payload",
            status_code=404,
            path="/historical/private",
            retryable=False,
        )


class RepeatedCursorKalshi(FakeKalshiHistory):
    def __init__(self) -> None:
        super().__init__()
        self.market_pages = 0

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
        self.market_pages += 1
        page = await super().get_markets(
            status=status,
            limit=limit,
            cursor=cursor,
            series_ticker=series_ticker,
            min_settled_ts=min_settled_ts,
            max_settled_ts=max_settled_ts,
        )
        return page.model_copy(update={"cursor": "same-cursor"})


def _ports(client: FakeKalshiHistory, pool: SQLiteConnectionPool, root: Path) -> BackfillPorts:
    return BackfillPorts(
        client=client,
        pool=pool,
        clock=FixedClock(),
        default_collector_path=root / "missing-default.db",
    )


@pytest.mark.asyncio
async def test_isolated_candle_404_continues_and_returns_partial(tmp_path: Path) -> None:
    client = MissingArchiveCandleKalshi()
    pool = SQLiteConnectionPool()
    try:
        result = await run_backfill(
            BackfillRequest(months=6, target_db=tmp_path / "target.db"),
            _ports(client, pool, tmp_path),
        )
    finally:
        pool.shutdown()

    assert result.status == "partial"
    assert result.kalshi.markets.inserted == 2
    assert result.kalshi.candlesticks.inserted == 1
    assert result.kalshi.forecast_history.inserted == 1
    assert result.failures[0].code == "candle_not_found"
    assert "sensitive" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_repeated_cursor_aborts_before_detail_calls(tmp_path: Path) -> None:
    client = RepeatedCursorKalshi()
    pool = SQLiteConnectionPool()
    try:
        result = await run_backfill(
            BackfillRequest(months=6, target_db=tmp_path / "target.db"),
            _ports(client, pool, tmp_path),
        )
    finally:
        pool.shutdown()

    assert result.status == "failure"
    assert result.failures[0].code == "kalshi_systemic_failure"
    assert client.market_pages == 2
    assert client.live_candles == []
    assert client.archive_candles == []
    assert client.forecast_events == []
