from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol, final

import pytest

from traderbot.db.migrations import init_schema
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_collector import (
    CollectorPathError,
    CollectorSchemaError,
    import_collector,
    validate_collector_path,
)

SOURCE_SCHEMA = """
CREATE TABLE weather_forecasts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_ts TEXT NOT NULL, city TEXT NOT NULL,
 latitude REAL NOT NULL, longitude REAL NOT NULL, model TEXT NOT NULL,
 valid_date TEXT NOT NULL, variable TEXT NOT NULL, value REAL NOT NULL,
 UNIQUE(snapshot_ts, city, model, valid_date, variable));
CREATE TABLE weather_observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, city TEXT NOT NULL,
 latitude REAL NOT NULL, longitude REAL NOT NULL, variable TEXT NOT NULL, value REAL NOT NULL,
 UNIQUE(date, city, variable));
CREATE TABLE nws_forecasts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_ts TEXT NOT NULL, city TEXT NOT NULL,
 forecast_date TEXT NOT NULL, high_temp_f REAL, low_temp_f REAL, precip_prob REAL,
 wind_speed REAL, detailed_forecast TEXT,
 UNIQUE(snapshot_ts, city, forecast_date));
"""


@final
class PoolConnection(Protocol):
    def __call__(
        self, path: str | Path, *, readonly: bool = False
    ) -> AbstractContextManager[sqlite3.Connection]: ...


@final
class FailSecondCheckout:
    def __init__(self, connection: PoolConnection) -> None:
        self._connection = connection
        self._checkouts = 0

    @contextmanager
    def connection(
        self, path: str | Path, *, readonly: bool = False
    ) -> Generator[sqlite3.Connection, None, None]:
        self._checkouts += 1
        if self._checkouts == 2:
            raise sqlite3.OperationalError("injected second-batch failure")
        with self._connection(path, readonly=readonly) as connection:
            yield connection


def _source(path: Path, rows: int) -> None:
    with sqlite3.connect(path) as connection:
        _ = connection.executescript(SOURCE_SCHEMA)
        _ = connection.executemany(
            """INSERT INTO weather_observations
               (date, city, latitude, longitude, variable, value)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (f"2026-01-{index // 100 + 1:02d}", f"city-{index}", 1.0, 2.0, "high", index)
                for index in range(rows)
            ),
        )


@pytest.mark.parametrize("row_count", [999, 1000, 1001, 2001])
def test_collector_import_batches_and_rerun_counts_are_truthful(
    tmp_path: Path, row_count: int
) -> None:
    source = tmp_path / "collector.db"
    target = tmp_path / "traderbot.db"
    _source(source, row_count)
    init_schema(target)
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before_stat = source.stat()
    pool = SQLiteConnectionPool()
    try:
        first = import_collector(source, target, pool)
        second = import_collector(source, target, pool)
    finally:
        pool.shutdown()

    assert first.weather_observations.seen == row_count
    assert first.weather_observations.inserted == row_count
    assert first.weather_observations.duplicate == 0
    assert second.weather_observations.inserted == 0
    assert second.weather_observations.duplicate == row_count
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    after_stat = source.stat()
    assert after_stat.st_ino == before_stat.st_ino
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert after_stat.st_mode == before_stat.st_mode
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (
            row_count,
        )
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (
            row_count,
        )


def test_collector_schema_drift_fails_before_target_mutation(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    target = tmp_path / "traderbot.db"
    with sqlite3.connect(source) as connection:
        _ = connection.execute("CREATE TABLE weather_forecasts (id INTEGER PRIMARY KEY)")
    init_schema(target)
    pool = SQLiteConnectionPool()
    try:
        with pytest.raises(CollectorSchemaError):
            _ = import_collector(source, target, pool)
    finally:
        pool.shutdown()

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_forecasts").fetchone() == (0,)


def test_explicit_linked_collector_is_rejected_before_target_creation(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    linked = tmp_path / "linked.db"
    target = tmp_path / "traderbot.db"
    _source(source, 1)
    _ = linked.symlink_to(source)

    with pytest.raises(CollectorPathError):
        validate_collector_path(linked)

    assert not target.exists()


def test_second_batch_failure_preserves_first_and_rerun_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "collector.db"
    target = tmp_path / "traderbot.db"
    _source(source, 1001)
    init_schema(target)
    failing_pool = SQLiteConnectionPool()
    failure = FailSecondCheckout(failing_pool.connection)
    monkeypatch.setattr(failing_pool, "connection", failure.connection)
    try:
        with pytest.raises(sqlite3.OperationalError):
            _ = import_collector(source, target, failing_pool)
    finally:
        failing_pool.shutdown()

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (1000,)

    pool = SQLiteConnectionPool()
    try:
        recovered = import_collector(source, target, pool)
    finally:
        pool.shutdown()

    assert recovered.weather_observations.inserted == 1
    assert recovered.weather_observations.duplicate == 1000


def test_missing_unreadable_and_nonregular_sources_are_rejected(tmp_path: Path) -> None:
    unreadable = tmp_path / "unreadable.db"
    _source(unreadable, 0)
    unreadable.chmod(0o200)

    with pytest.raises(CollectorPathError):
        validate_collector_path(tmp_path / "missing.db")
    with pytest.raises(CollectorPathError):
        validate_collector_path(unreadable)
    with pytest.raises(CollectorPathError):
        validate_collector_path(tmp_path)


def test_import_uses_one_snapshot_while_wal_writer_commits(tmp_path: Path) -> None:
    source = tmp_path / "collector.db"
    target = tmp_path / "traderbot.db"
    _source(source, 1)
    with sqlite3.connect(source) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    writer_ready = threading.Event()
    writer_done = threading.Event()
    writer_errors: list[BaseException] = []

    def writer() -> None:
        try:
            assert writer_ready.wait(timeout=5)
            with sqlite3.connect(source) as connection:
                _ = connection.execute(
                    """INSERT INTO weather_observations
                    (date, city, latitude, longitude, variable, value)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    ("2026-01-02", "concurrent", 1.0, 2.0, "high", 82.0),
                )
        except (AssertionError, sqlite3.Error) as exc:
            writer_errors.append(exc)
        finally:
            writer_done.set()

    def after_snapshot() -> None:
        writer_ready.set()
        assert writer_done.wait(timeout=5)

    thread = threading.Thread(target=writer)
    thread.start()
    pool = SQLiteConnectionPool()
    try:
        init_schema(target)
        result = import_collector(source, target, pool, during_snapshot=after_snapshot)
    finally:
        pool.shutdown()
        thread.join(timeout=5)

    assert writer_errors == []
    assert result.weather_observations.seen == 1
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT COUNT(*) FROM weather_observations").fetchone() == (2,)
