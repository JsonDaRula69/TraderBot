from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from traderbot.db.migrations import MigrationError, init_schema
from traderbot.deploy.backfill_collector import (
    CollectorPathError,
    CollectorSchemaError,
    PreparedCollector,
    import_prepared_collector,
    prepare_collector_source,
    validate_collector_path,
)
from traderbot.deploy.backfill_kalshi import (
    KalshiBackfillError,
    KalshiJob,
    KalshiPhaseAbort,
    backfill_kalshi,
)
from traderbot.deploy.backfill_models import (
    BackfillFailure,
    BackfillResult,
    CollectorCounts,
    KalshiCounts,
)
from traderbot.deploy.backfill_ports import (
    BackfillDependencies,
    BackfillPorts,
    BackfillRuntime,
)
from traderbot.deploy.backfill_window import BackfillWindow, BackfillWindowError, calendar_window
from traderbot.kalshi.errors import AuthenticationError, KalshiAPIError, RateLimitError


class BackfillRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid", frozen=True)

    months: int = Field(ge=1, le=60)
    target_db: Path
    collector_db: Path | None = None


def _failure(code: str, detail: str) -> tuple[BackfillFailure, ...]:
    return (BackfillFailure(code=code, detail=detail[:200]),)


def _validate_target(path: Path) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    if lexical.exists():
        current = lexical
        while current != current.parent:
            if current.is_symlink():
                raise CollectorPathError("target links are not allowed")
            current = current.parent
        metadata = lexical.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise CollectorPathError("target must be a regular file")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise CollectorPathError("target must be owned by the current user")
    return lexical


def _committed(collector: CollectorCounts, kalshi: KalshiCounts) -> bool:
    return any(
        count.inserted > 0
        for count in (
            collector.weather_forecasts,
            collector.nws_forecasts,
            collector.weather_observations,
            kalshi.markets,
            kalshi.candlesticks,
            kalshi.forecast_history,
        )
    )


def _collector_path(request: BackfillRequest, default_path: Path) -> Path | None:
    path = default_path if request.collector_db is None else request.collector_db
    if request.collector_db is None and not path.exists() and not path.is_symlink():
        return None
    return validate_collector_path(path)


@contextmanager
def _prepared_collector(
    path: Path | None,
) -> Generator[PreparedCollector | None, None, None]:
    if path is None:
        yield None
        return
    with prepare_collector_source(path) as prepared:
        yield prepared


async def _execute(
    runtime: BackfillRuntime,
    prepared: PreparedCollector | None,
    target: Path,
    window: BackfillWindow,
    warnings: list[str],
) -> BackfillResult:
    collector_counts = CollectorCounts()
    kalshi_counts = KalshiCounts()
    try:
        runtime.progress.phase("database")
        init_schema(target)
        if prepared is not None:
            runtime.progress.phase("collector")
            collector_counts = import_prepared_collector(prepared, target, runtime.pool)
    except (MigrationError, OSError, sqlite3.Error):
        return BackfillResult(
            status="failure",
            collector=collector_counts,
            warnings=tuple(warnings),
            failures=_failure("target_database_failure", "target database operation failed"),
        )

    try:
        runtime.progress.phase("kalshi")
        phase = await backfill_kalshi(KalshiJob(runtime.client, runtime.pool, target, window))
        kalshi_counts = phase.tables
    except KalshiPhaseAbort as exc:
        kalshi_counts = exc.tables
        status = "partial" if _committed(collector_counts, kalshi_counts) else "failure"
        return BackfillResult(
            status=status,
            collector=collector_counts,
            kalshi=kalshi_counts,
            api=exc.api,
            warnings=tuple(warnings) + exc.warnings,
            failures=_failure("kalshi_systemic_failure", "Kalshi phase aborted safely"),
        )
    except (
        AuthenticationError,
        RateLimitError,
        KalshiAPIError,
        KalshiBackfillError,
        ValidationError,
        httpx.HTTPError,
        OSError,
        sqlite3.Error,
    ):
        status = "partial" if _committed(collector_counts, kalshi_counts) else "failure"
        return BackfillResult(
            status=status,
            collector=collector_counts,
            kalshi=kalshi_counts,
            warnings=tuple(warnings),
            failures=_failure("kalshi_systemic_failure", "Kalshi phase aborted safely"),
        )

    status = "partial" if phase.failures else "complete"
    return BackfillResult(
        status=status,
        collector=collector_counts,
        kalshi=kalshi_counts,
        api=phase.api,
        warnings=tuple(warnings) + phase.warnings,
        failures=phase.failures,
    )


async def run_backfill(
    request: BackfillRequest, dependencies: BackfillDependencies
) -> BackfillResult:
    warnings: list[str] = []
    try:
        window = calendar_window(request.months, dependencies.now())
        target = _validate_target(request.target_db)
        collector = _collector_path(request, dependencies.default_collector_path)
        if collector is None:
            warnings.append("default collector database is absent; weather import skipped")
    except (BackfillWindowError, CollectorPathError, OSError) as exc:
        return BackfillResult(
            status="invalid_input",
            warnings=tuple(warnings),
            failures=_failure("invalid_input", str(exc)),
        )
    try:
        with _prepared_collector(collector) as prepared:
            async with dependencies.open_runtime() as runtime:
                return await _execute(runtime, prepared, target, window, warnings)
    except (CollectorPathError, CollectorSchemaError) as exc:
        return BackfillResult(
            status="invalid_input",
            warnings=tuple(warnings),
            failures=_failure("invalid_collector", str(exc)),
        )


async def run_prepared_backfill(
    request: BackfillRequest,
    dependencies: BackfillDependencies,
    prepared: PreparedCollector,
) -> BackfillResult:
    try:
        window = calendar_window(request.months, dependencies.now())
        target = _validate_target(request.target_db)
    except (BackfillWindowError, CollectorPathError, OSError) as exc:
        return BackfillResult(
            status="invalid_input",
            failures=_failure("invalid_input", str(exc)),
        )
    async with dependencies.open_runtime() as runtime:
        return await _execute(runtime, prepared, target, window, [])


__all__ = [
    "BackfillPorts",
    "BackfillRequest",
    "BackfillResult",
    "run_backfill",
    "run_prepared_backfill",
]
