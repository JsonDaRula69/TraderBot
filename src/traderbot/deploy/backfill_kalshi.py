"""Backfill Kalshi candlesticks and forecast history."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Final, assert_never

import httpx
from pydantic import ValidationError

from traderbot.deploy.backfill_bounds import (
    filter_forecasts,
    filter_historical_candles,
    filter_live_candles,
)
from traderbot.deploy.backfill_discovery import (
    KalshiBackfillError,
    KalshiJob,
    MarketCandidate,
    discover_markets,
    settlement_time,
)
from traderbot.deploy.backfill_models import (
    ApiCounts,
    BackfillFailure,
    KalshiCounts,
    TableCounts,
)
from traderbot.deploy.backfill_store import (
    ForecastBatch,
    HistoricalCandleBatch,
    LiveCandleBatch,
    StoredMarket,
    write_forecasts,
    write_historical_candles,
    write_live_candles,
    write_markets,
)
from traderbot.kalshi.errors import AuthenticationError, KalshiAPIError, RateLimitError

_CANDLE_PERIOD: Final = 60
_FORECAST_PERIOD: Final = 60
_PERCENTILES: Final = (1000, 5000, 9000)
_MAX_FAILURES: Final = 25


class KalshiPhaseAbort(RuntimeError):
    def __init__(
        self, tables: KalshiCounts, api: ApiCounts, warnings: tuple[str, ...] = ()
    ) -> None:
        super().__init__("Kalshi phase aborted safely")
        self.tables: KalshiCounts = tables
        self.api: ApiCounts = api
        self.warnings: tuple[str, ...] = warnings


class _DetailAbort(RuntimeError):
    def __init__(self, counts: TableCounts, api_items: int, skipped: int) -> None:
        super().__init__("Kalshi detail phase aborted safely")
        self.counts: TableCounts = counts
        self.api_items: int = api_items
        self.skipped: int = skipped


@dataclass(frozen=True, slots=True)
class KalshiPhaseResult:
    tables: KalshiCounts
    api: ApiCounts
    failures: tuple[BackfillFailure, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DetailResult:
    counts: TableCounts
    failures: tuple[BackfillFailure, ...]
    api_items: int
    skipped: int


def _add(left: TableCounts, right: TableCounts) -> TableCounts:
    return TableCounts(
        seen=left.seen + right.seen,
        inserted=left.inserted + right.inserted,
        duplicate=left.duplicate + right.duplicate,
    )


def _failure(code: str, item: str) -> BackfillFailure:
    return BackfillFailure(code=code, item=item[:100], detail="item detail unavailable")


async def _candles(job: KalshiJob, candidates: tuple[MarketCandidate, ...]) -> _DetailResult:
    counts = TableCounts()
    failures: list[BackfillFailure] = []
    api_items = 0
    skipped = 0
    for candidate in candidates:
        start = max(job.window.start, candidate.market.open_time)
        end = min(job.window.end, settlement_time(candidate.market))
        if start >= end:
            failures.append(_failure("empty_candle_interval", candidate.market.ticker))
            continue
        start_ts = math.floor(start.timestamp())
        end_ts = math.ceil(end.timestamp()) - 1
        try:
            match candidate.tier:
                case "current":
                    response = await job.client.get_candlesticks(
                        candidate.series_ticker,
                        candidate.market.ticker,
                        start_ts,
                        end_ts,
                        _CANDLE_PERIOD,
                    )
                    api_items += len(response.candlesticks)
                    bounded, newly_skipped = filter_live_candles(response, start, end)
                    skipped += newly_skipped
                    written = write_live_candles(
                        job.pool,
                        job.target,
                        LiveCandleBatch(candidate.market.ticker, _CANDLE_PERIOD, bounded),
                    )
                case "archive":
                    response = await job.client.get_historical_candlesticks(
                        candidate.market.ticker, start_ts, end_ts, _CANDLE_PERIOD
                    )
                    api_items += len(response.candlesticks)
                    bounded, newly_skipped = filter_historical_candles(response, start, end)
                    skipped += newly_skipped
                    written = write_historical_candles(
                        job.pool,
                        job.target,
                        HistoricalCandleBatch(candidate.market.ticker, _CANDLE_PERIOD, bounded),
                    )
                case unreachable:
                    assert_never(unreachable)
        except KalshiAPIError as exc:
            if exc.status_code != 404:
                raise _DetailAbort(counts, api_items, skipped) from None
            failures.append(_failure("candle_not_found", candidate.market.ticker))
            continue
        except (AuthenticationError, RateLimitError, httpx.HTTPError, OSError, sqlite3.Error):
            raise _DetailAbort(counts, api_items, skipped) from None
        except ValidationError:
            failures.append(_failure("malformed_candle", candidate.market.ticker))
            continue
        counts = _add(counts, written)
    return _DetailResult(counts, tuple(failures), api_items, skipped)


async def _forecasts(job: KalshiJob, candidates: tuple[MarketCandidate, ...]) -> _DetailResult:
    events = sorted({(item.series_ticker, item.market.event_ticker) for item in candidates})
    counts = TableCounts()
    failures: list[BackfillFailure] = []
    api_items = 0
    skipped = 0
    for series, event in events:
        try:
            response = await job.client.get_forecast_percentile_history(
                series,
                event,
                math.floor(job.window.start.timestamp()),
                math.ceil(job.window.end.timestamp()) - 1,
                _PERCENTILES,
                _FORECAST_PERIOD,
            )
            api_items += len(response.forecast_history)
            bounded, newly_skipped = filter_forecasts(response, job.window.start, job.window.end)
            skipped += newly_skipped
            counts = _add(
                counts,
                write_forecasts(job.pool, job.target, ForecastBatch(series, bounded)),
            )
        except KalshiAPIError as exc:
            if exc.status_code != 404:
                raise _DetailAbort(counts, api_items, skipped) from None
            failures.append(_failure("forecast_not_found", event))
        except ValidationError:
            failures.append(_failure("malformed_forecast", event))
        except (AuthenticationError, RateLimitError, httpx.HTTPError, OSError, sqlite3.Error):
            raise _DetailAbort(counts, api_items, skipped) from None
    return _DetailResult(counts, tuple(failures), api_items, skipped)


def _warnings(candles_skipped: int, forecasts_skipped: int) -> tuple[str, ...]:
    warnings: list[str] = []
    if candles_skipped:
        warnings.append(f"kalshi_candlesticks_skipped_out_of_window={candles_skipped}")
    if forecasts_skipped:
        warnings.append(f"kalshi_forecast_points_skipped_out_of_window={forecasts_skipped}")
    return tuple(warnings)


async def backfill_kalshi(job: KalshiJob) -> KalshiPhaseResult:
    merged, pages = await discover_markets(job)
    market_counts = write_markets(
        job.pool,
        job.target,
        tuple(StoredMarket(item.market, item.series_ticker, "weather") for item in merged),
    )
    try:
        candles = await _candles(job, merged)
    except _DetailAbort as exc:
        tables = KalshiCounts(markets=market_counts, candlesticks=exc.counts)
        api = ApiCounts(pages=pages, markets=len(merged), candlesticks=exc.api_items)
        warnings = (
            (f"kalshi_candlesticks_skipped_out_of_window={exc.skipped}",) if exc.skipped else ()
        )
        raise KalshiPhaseAbort(tables, api, warnings) from None
    try:
        forecasts = await _forecasts(job, merged)
    except _DetailAbort as exc:
        tables = KalshiCounts(
            markets=market_counts,
            candlesticks=candles.counts,
            forecast_history=exc.counts,
        )
        api = ApiCounts(
            pages=pages,
            markets=len(merged),
            candlesticks=candles.api_items,
            forecasts=exc.api_items,
        )
        warnings = _warnings(candles.skipped, exc.skipped)
        raise KalshiPhaseAbort(tables, api, warnings) from None
    failures = candles.failures + forecasts.failures
    bounded_failures = failures[:_MAX_FAILURES]
    return KalshiPhaseResult(
        tables=KalshiCounts(
            markets=market_counts,
            candlesticks=candles.counts,
            forecast_history=forecasts.counts,
        ),
        api=ApiCounts(
            pages=pages,
            markets=len(merged),
            candlesticks=candles.api_items,
            forecasts=forecasts.api_items,
        ),
        failures=bounded_failures,
        warnings=_warnings(candles.skipped, forecasts.skipped),
    )


__all__ = [
    "KalshiBackfillError",
    "KalshiJob",
    "KalshiPhaseAbort",
    "KalshiPhaseResult",
    "backfill_kalshi",
]
