"""Define protocols and dependency bundles for deploy backfill."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.kalshi.client import Environment
from traderbot.kalshi.models import CutoffTimestamps
from traderbot.kalshi.rest_models import (
    ForecastHistoryResponse,
    HistoricalCandlestickResponse,
    LiveCandlestickResponse,
    MarketListResponse,
    SeriesListResponse,
)


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class ProgressPort(Protocol):
    def phase(self, name: str) -> None: ...


class NullProgress:
    def phase(self, name: str) -> None:
        _ = name
        return None


class KalshiHistoryPort(Protocol):
    async def get_historical_cutoff(self) -> CutoffTimestamps: ...

    async def get_series(self, category: str) -> SeriesListResponse: ...

    async def get_markets(
        self,
        *,
        status: str,
        limit: int,
        cursor: str | None,
        series_ticker: str,
        min_settled_ts: int,
        max_settled_ts: int,
    ) -> MarketListResponse: ...

    async def get_historical_markets(
        self,
        *,
        limit: int,
        cursor: str | None,
        series_ticker: str,
    ) -> MarketListResponse: ...

    async def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> LiveCandlestickResponse: ...

    async def get_historical_candlesticks(
        self,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
    ) -> HistoricalCandlestickResponse: ...

    async def get_forecast_percentile_history(
        self,
        series_ticker: str,
        event_ticker: str,
        start_ts: int,
        end_ts: int,
        percentiles: Sequence[int],
        period_interval: int,
    ) -> ForecastHistoryResponse: ...


@dataclass(frozen=True, slots=True)
class BackfillRuntime:
    client: KalshiHistoryPort
    pool: SQLiteConnectionPool
    progress: ProgressPort = NullProgress()


class BackfillDependencies(Protocol):
    @property
    def default_collector_path(self) -> Path: ...

    def now(self) -> datetime: ...

    def open_runtime(
        self,
        environment: Environment,
    ) -> AbstractAsyncContextManager[BackfillRuntime]: ...


@dataclass(frozen=True, slots=True)
class BackfillPorts:
    client: KalshiHistoryPort
    pool: SQLiteConnectionPool
    clock: ClockPort
    default_collector_path: Path
    progress: ProgressPort = NullProgress()

    def now(self) -> datetime:
        return self.clock.now()

    @asynccontextmanager
    async def open_runtime(
        self,
        environment: Environment = "production",
    ) -> AsyncGenerator[BackfillRuntime, None]:
        del environment
        yield BackfillRuntime(client=self.client, pool=self.pool, progress=self.progress)


__all__ = [
    "BackfillDependencies",
    "BackfillPorts",
    "BackfillRuntime",
    "ClockPort",
    "KalshiHistoryPort",
    "NullProgress",
    "ProgressPort",
]
