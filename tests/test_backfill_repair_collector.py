from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import pytest

from tests.test_backfill_collector import SOURCE_SCHEMA, _source
from tests.test_backfill_kalshi import FakeKalshiHistory, FixedClock
from traderbot.db.migrations import init_schema
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy import backfill_collector
from traderbot.deploy.backfill import BackfillRequest, run_backfill
from traderbot.deploy.backfill_collector import CollectorPathError, import_collector
from traderbot.deploy.backfill_ports import BackfillRuntime


class _LazyDependencies:
    def __init__(self, default_collector_path: Path) -> None:
        self.default_collector_path = default_collector_path
        self.opens = 0

    def now(self) -> datetime:
        return FixedClock().now()

    @asynccontextmanager
    async def open_runtime(
        self,
        environment: Literal["production", "demo"] = "production",
    ) -> AsyncIterator[BackfillRuntime]:
        del environment
        self.opens += 1
        pool = SQLiteConnectionPool()
        try:
            yield BackfillRuntime(client=FakeKalshiHistory(), pool=pool)
        finally:
            pool.shutdown()


@pytest.mark.asyncio
async def test_malformed_explicit_source_leaves_target_absent(tmp_path: Path) -> None:
    source = tmp_path / "malformed.db"
    target = tmp_path / "target.db"
    with sqlite3.connect(source) as connection:
        _ = connection.execute("CREATE TABLE weather_forecasts (id INTEGER PRIMARY KEY)")
    dependencies = _LazyDependencies(tmp_path / "unused.db")
    result = await run_backfill(
        BackfillRequest(months=6, collector_db=source, target_db=target),
        dependencies,
    )

    assert result.status == "invalid_input"
    assert dependencies.opens == 0
    assert not target.exists()


def test_source_replacement_during_snapshot_cannot_write_target(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    original = tmp_path / "original.db"
    target = tmp_path / "target.db"
    _source(source, 1)
    init_schema(target)
    pool = SQLiteConnectionPool()

    def replace_source() -> None:
        source.rename(original)
        _source(source, 2)

    try:
        with pytest.raises(CollectorPathError):
            _ = import_collector(
                source,
                target,
                pool,
                during_snapshot=replace_source,
            )
    finally:
        pool.shutdown()

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (0,)


def test_prepared_snapshot_is_query_only_secure_and_cleaned(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    _source(source, 1)
    prepare = backfill_collector.prepare_collector_source

    with prepare(source) as snapshot:
        snapshot_path = snapshot.path
        assert snapshot.query_only == 1
        assert snapshot_path.stat().st_mode & 0o777 == 0o600
        assert snapshot_path.stat().st_uid == source.stat().st_uid
        with sqlite3.connect(snapshot_path) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    assert not snapshot_path.exists()


def test_replacement_after_snapshot_does_not_change_copied_bytes(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    original = tmp_path / "original.db"
    target = tmp_path / "target.db"
    _source(source, 1)

    def replace_after_snapshot() -> None:
        source.rename(original)
        _source(source, 2)

    prepare = backfill_collector.prepare_collector_source
    pool = SQLiteConnectionPool()
    try:
        init_schema(target)
        with prepare(source, after_snapshot=replace_after_snapshot) as snapshot:
            result = backfill_collector.import_prepared_collector(snapshot, target, pool)
    finally:
        pool.shutdown()

    assert result.weather_observations.inserted == 1
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (1,)


def test_snapshot_schema_preflight_rejects_default_drift(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    schema = SOURCE_SCHEMA.replace(
        "snapshot_ts TEXT NOT NULL, city TEXT NOT NULL",
        "snapshot_ts TEXT NOT NULL DEFAULT 'x', city TEXT NOT NULL",
        1,
    )
    with sqlite3.connect(source) as connection:
        _ = connection.executescript(schema)

    with pytest.raises(backfill_collector.CollectorSchemaError):
        with backfill_collector.prepare_collector_source(source):
            pytest.fail("incompatible snapshot was yielded")


@pytest.mark.asyncio
async def test_non_sqlite_explicit_source_is_invalid_before_runtime(
    tmp_path: Path,
) -> None:
    source = tmp_path / "not-sqlite.db"
    target = tmp_path / "target.db"
    source.write_bytes(b"not a sqlite database")
    dependencies = _LazyDependencies(tmp_path / "unused.db")

    result = await run_backfill(
        BackfillRequest(months=6, collector_db=source, target_db=target), dependencies
    )

    assert result.status == "invalid_input"
    assert dependencies.opens == 0
    assert not target.exists()


def test_failed_snapshot_removes_secure_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "not-sqlite.db"
    source.write_bytes(b"not a sqlite database")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    with pytest.raises(CollectorPathError):
        with backfill_collector.prepare_collector_source(source):
            pytest.fail("invalid snapshot was yielded")

    assert tuple(tmp_path.glob(".traderbot-collector-snapshot-*")) == ()
