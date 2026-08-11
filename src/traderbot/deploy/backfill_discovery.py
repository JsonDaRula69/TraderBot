from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, override

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_ports import KalshiHistoryPort
from traderbot.deploy.backfill_window import BackfillWindow
from traderbot.kalshi.rest_models import KalshiMarket, MarketListResponse

_PAGE_LIMIT: Final = 1000
_MAX_PAGES: Final = 10_000


@dataclass(frozen=True, slots=True)
class KalshiBackfillError(RuntimeError):
    code: str

    @override
    def __str__(self) -> str:
        return f"Kalshi backfill aborted: {self.code}"


@dataclass(frozen=True, slots=True)
class MarketCandidate:
    market: KalshiMarket
    series_ticker: str
    tier: Literal["current", "archive"]


@dataclass(frozen=True, slots=True)
class KalshiJob:
    client: KalshiHistoryPort
    pool: SQLiteConnectionPool
    target: Path
    window: BackfillWindow


def _next_cursor(cursor: str, seen: set[str], pages: int) -> str | None:
    if cursor == "":
        return None
    if not cursor.strip() or cursor != cursor.strip() or not cursor.isprintable():
        raise KalshiBackfillError("malformed_cursor")
    if cursor in seen:
        raise KalshiBackfillError("repeated_cursor")
    if pages >= _MAX_PAGES:
        raise KalshiBackfillError("page_limit_exceeded")
    seen.add(cursor)
    return cursor


def settlement_time(market: KalshiMarket) -> datetime:
    if market.settlement_ts is None:
        raise KalshiBackfillError("settled_market_missing_settlement_ts")
    return market.settlement_ts


async def _current_pages(
    job: KalshiJob, series: str, cutoff: datetime
) -> tuple[list[MarketCandidate], int]:
    start = max(job.window.start, cutoff)
    if start >= job.window.end:
        return [], 0
    cursor: str | None = None
    seen: set[str] = set()
    candidates: list[MarketCandidate] = []
    pages = 0
    while True:
        response = await job.client.get_markets(
            status="settled",
            limit=_PAGE_LIMIT,
            cursor=cursor,
            series_ticker=series,
            min_settled_ts=math.floor(start.timestamp()),
            max_settled_ts=math.ceil(job.window.end.timestamp()) - 1,
        )
        pages += 1
        candidates.extend(
            MarketCandidate(market=market, series_ticker=series, tier="current")
            for market in response.markets
            if start <= settlement_time(market) < job.window.end
        )
        cursor = _next_cursor(response.cursor, seen, pages)
        if cursor is None:
            return candidates, pages


async def _archive_pages(
    job: KalshiJob, series: str, cutoff: datetime
) -> tuple[list[MarketCandidate], int]:
    end = min(job.window.end, cutoff)
    if job.window.start >= end:
        return [], 0
    cursor: str | None = None
    seen: set[str] = set()
    candidates: list[MarketCandidate] = []
    pages = 0
    while True:
        response: MarketListResponse = await job.client.get_historical_markets(
            limit=_PAGE_LIMIT,
            cursor=cursor,
            series_ticker=series,
        )
        pages += 1
        candidates.extend(
            MarketCandidate(market=market, series_ticker=series, tier="archive")
            for market in response.markets
            if job.window.start <= settlement_time(market) < end
        )
        cursor = _next_cursor(response.cursor, seen, pages)
        if cursor is None:
            return candidates, pages


def _merge(candidates: list[MarketCandidate]) -> tuple[MarketCandidate, ...]:
    merged: dict[str, MarketCandidate] = {}
    for candidate in candidates:
        previous = merged.get(candidate.market.ticker)
        if previous is not None and previous != candidate:
            raise KalshiBackfillError("conflicting_market_ticker")
        if previous is None:
            merged[candidate.market.ticker] = candidate
    return tuple(merged[ticker] for ticker in sorted(merged))


async def discover_markets(job: KalshiJob) -> tuple[tuple[MarketCandidate, ...], int]:
    cutoff = (await job.client.get_historical_cutoff()).market_settled_ts
    series = sorted(item.ticker for item in (await job.client.get_series("weather")).series)
    candidates: list[MarketCandidate] = []
    pages = 0
    for ticker in series:
        current, current_pages = await _current_pages(job, ticker, cutoff)
        archive, archive_pages = await _archive_pages(job, ticker, cutoff)
        candidates.extend(current)
        candidates.extend(archive)
        pages += current_pages + archive_pages
    return _merge(candidates), pages


__all__ = [
    "KalshiBackfillError",
    "KalshiJob",
    "MarketCandidate",
    "discover_markets",
    "settlement_time",
]
