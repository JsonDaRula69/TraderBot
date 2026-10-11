from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.kalshi_rest_fixtures import market_payload
from tests.test_backfill_kalshi import FakeKalshiHistory
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_discovery import KalshiJob, discover_markets
from traderbot.deploy.backfill_window import BackfillWindow
from traderbot.kalshi import MarketCategory as PackageMarketCategory
from traderbot.kalshi.models import CutoffTimestamps, MarketCategory
from traderbot.kalshi.order_models import MarketCategory as ExtractedMarketCategory
from traderbot.kalshi.rest_models import MarketListResponse


def _payload(value: str) -> str:
    return json.dumps(
        {
            "market_settled_ts": value,
            "trades_created_ts": value,
            "orders_updated_ts": value,
            "market_positions_last_updated_ts": value,
        }
    )


def test_cutoff_zulu_datetime_is_aware_utc_with_precision() -> None:
    cutoff = CutoffTimestamps.model_validate_json(_payload("2026-06-01T00:00:00.123456Z"))

    assert cutoff.market_settled_ts == datetime(2026, 6, 1, 0, 0, 0, 123456, tzinfo=UTC)
    assert cutoff.market_settled_ts.tzinfo is UTC


def test_cutoff_non_utc_offset_normalizes_without_precision_loss() -> None:
    cutoff = CutoffTimestamps.model_validate_json(_payload("2026-06-01T05:30:00.654321+05:30"))

    assert cutoff.market_settled_ts == datetime(2026, 6, 1, 0, 0, 0, 654321, tzinfo=UTC)
    assert cutoff.market_settled_ts.tzinfo is UTC


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: CutoffTimestamps.model_validate_json(_payload("2026-06-01T00:00:00")),
        lambda: CutoffTimestamps(
            market_settled_ts=datetime(2026, 6, 1),
            trades_created_ts=datetime(2026, 6, 1),
            orders_updated_ts=datetime(2026, 6, 1),
        ),
    ],
)
def test_cutoff_rejects_naive_json_and_python_datetime(
    constructor: Callable[[], CutoffTimestamps],
) -> None:
    with pytest.raises(ValidationError):
        _ = constructor()


class _UnavailableOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        _ = value
        return None

    def dst(self, value: datetime | None) -> timedelta | None:
        _ = value
        return None

    def tzname(self, value: datetime | None) -> str:
        _ = value
        return "unavailable"


def test_cutoff_rejects_datetime_with_unavailable_offset() -> None:
    value = datetime(2026, 6, 1, tzinfo=_UnavailableOffset())

    with pytest.raises(ValidationError):
        _ = CutoffTimestamps(
            market_settled_ts=value,
            trades_created_ts=value,
            orders_updated_ts=value,
        )


def test_extracted_model_reexports_preserve_identity() -> None:
    assert MarketCategory is ExtractedMarketCategory
    assert PackageMarketCategory is ExtractedMarketCategory


class _EqualityCutoffKalshi(FakeKalshiHistory):
    async def get_historical_cutoff(self) -> CutoffTimestamps:
        value = datetime(2026, 6, 1, 0, 0, 0, 500000, tzinfo=UTC)
        return CutoffTimestamps(
            market_settled_ts=value,
            trades_created_ts=value,
            orders_updated_ts=value,
        )

    def _equal_market_page(self) -> MarketListResponse:
        payload = {
            **market_payload(),
            "ticker": "KX-CUTOFF-EQUALITY",
            "open_time": "2026-05-01T00:00:00Z",
            "close_time": "2026-05-31T23:59:59Z",
            "settlement_ts": "2026-06-01T00:00:00.500000Z",
        }
        return MarketListResponse.model_validate_json(
            json.dumps({"markets": [payload], "cursor": ""})
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
        return self._equal_market_page()

    async def get_historical_markets(
        self, *, limit: int, cursor: str | None, series_ticker: str
    ) -> MarketListResponse:
        _ = (limit, cursor, series_ticker)
        return self._equal_market_page()


@pytest.mark.asyncio
async def test_market_at_cutoff_equality_belongs_only_to_current_tier(
    tmp_path: Path,
) -> None:
    pool = SQLiteConnectionPool()
    try:
        markets, pages = await discover_markets(
            KalshiJob(
                client=_EqualityCutoffKalshi(),
                pool=pool,
                target=tmp_path / "unused.db",
                window=BackfillWindow(
                    start=datetime(2026, 2, 28, 12, tzinfo=UTC),
                    end=datetime(2026, 8, 31, 12, tzinfo=UTC),
                ),
            )
        )
    finally:
        pool.shutdown()

    assert len(markets) == 1
    assert markets[0].tier == "current"
    assert pages == 2
