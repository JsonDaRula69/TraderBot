"""Behavioral tests for the owner-thread SQLite connection pool."""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from traderbot.db.pool import (
    ConnectionPoolClosedError,
    ConnectionPoolTimeoutError,
    CrossThreadAccessError,
    SQLiteConnectionPool,
)


class _RollbackProbeError(RuntimeError):
    pass


def test_fixed_defaults_are_exposed() -> None:
    # Given/When: a pool is constructed with no overrides.
    pool = SQLiteConnectionPool()

    # Then: the fixed capacity and checkout timeout are observable.
    assert pool.max_connections_per_path == 4
    assert pool.checkout_timeout == 5.0


def test_writable_connection_applies_all_optimization_pragmas(tmp_path: Path) -> None:
    # Given: a fresh writable database path.
    pool = SQLiteConnectionPool()

    # When: its first pooled handle is checked out.
    with pool.connection(tmp_path / "pragmas.db") as connection:
        # Then: every required optimization is active on that handle.
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute("PRAGMA synchronous").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        assert connection.execute("PRAGMA cache_size").fetchone() == (-64000,)
        assert connection.execute("PRAGMA temp_store").fetchone() == (2,)
        assert connection.execute("PRAGMA mmap_size").fetchone() == (268435456,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    pool.shutdown()


def test_readonly_connection_uses_uri_mode_ro(tmp_path: Path) -> None:
    # Given: an existing database and a fresh pool.
    path = tmp_path / "read only.db"
    writer = SQLiteConnectionPool()
    with writer.connection(path) as connection:
        _ = connection.execute("CREATE TABLE sample (value INTEGER)")
    writer.shutdown()

    # When: a read-only handle is opened.
    with patch("traderbot.db.pool.sqlite3.connect", wraps=sqlite3.connect) as connect_mock:
        pool = SQLiteConnectionPool()
        with pool.connection(path, readonly=True) as connection:
            assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (0,)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                _ = connection.execute("INSERT INTO sample VALUES (1)")

    # Then: sqlite received an encoded file URI with mode=ro and URI parsing enabled.
    assert connect_mock.call_args.args[0] == f"{path.resolve().as_uri()}?mode=ro"
    assert connect_mock.call_args.kwargs["uri"] is True
    assert connect_mock.call_args.kwargs["check_same_thread"] is True
    pool.shutdown()


def test_returned_connection_is_reused(tmp_path: Path) -> None:
    # Given: a pool with one path checked out and returned.
    pool = SQLiteConnectionPool()
    path = tmp_path / "reuse.db"
    with pool.connection(path) as first:
        _ = first.execute("CREATE TABLE sample (value INTEGER)")

    # When: the same path and mode are checked out again.
    with pool.connection(path) as second:
        # Then: the same SQLite handle is reused.
        assert second is first

    pool.shutdown()


def test_exclusive_checkout_waits_until_timeout(tmp_path: Path) -> None:
    # Given: the sole handle for a path is already checked out.
    timeout = 0.2
    pool = SQLiteConnectionPool(max_connections_per_path=1, checkout_timeout=timeout)
    path = tmp_path / "exclusive.db"
    with pool.connection(path):
        started = time.monotonic()

        # When/Then: a second checkout blocks until the configured timeout.
        with pytest.raises(ConnectionPoolTimeoutError):
            with pool.connection(path):
                pytest.fail("an exclusively checked-out handle must not be shared")
        assert time.monotonic() - started >= timeout * 0.8

    pool.shutdown()


def test_path_capacity_exhaustion_raises_typed_timeout(tmp_path: Path) -> None:
    # Given: every allowed handle for one path is checked out.
    pool = SQLiteConnectionPool(max_connections_per_path=2, checkout_timeout=0.01)
    path = tmp_path / "exhausted.db"
    with pool.connection(path), pool.connection(path):
        # When/Then: another checkout fails with path and capacity context.
        with pytest.raises(ConnectionPoolTimeoutError) as raised:
            with pool.connection(path):
                pytest.fail("pool capacity must be bounded")

    assert raised.value.path == path.resolve()
    assert raised.value.max_connections == 2
    pool.shutdown()


def test_normal_exit_commits_transaction(tmp_path: Path) -> None:
    # Given: a table created through the pool.
    pool = SQLiteConnectionPool()
    path = tmp_path / "commit.db"
    with pool.connection(path) as connection:
        _ = connection.execute("CREATE TABLE sample (value INTEGER)")

    # When: a write context exits normally.
    with pool.connection(path) as connection:
        _ = connection.execute("INSERT INTO sample VALUES (7)")

    # Then: a separate read-only handle observes the committed row.
    with pool.connection(path, readonly=True) as connection:
        assert connection.execute("SELECT value FROM sample").fetchall() == [(7,)]

    pool.shutdown()


def test_exception_exit_rolls_back_transaction(tmp_path: Path) -> None:
    # Given: an empty committed table.
    pool = SQLiteConnectionPool()
    path = tmp_path / "rollback.db"
    with pool.connection(path) as connection:
        _ = connection.execute("CREATE TABLE sample (value INTEGER)")

    # When: user code raises after inserting a row.
    with pytest.raises(_RollbackProbeError):
        with pool.connection(path) as connection:
            _ = connection.execute("INSERT INTO sample VALUES (9)")
            raise _RollbackProbeError

    # Then: the transaction was rolled back before the handle was returned.
    with pool.connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (0,)

    pool.shutdown()


def test_cross_thread_access_is_rejected_by_pool_owner_check(tmp_path: Path) -> None:
    # Given: a pool owned by the current thread.
    pool = SQLiteConnectionPool()
    errors: queue.SimpleQueue[CrossThreadAccessError] = queue.SimpleQueue()

    # When: another thread attempts a checkout.
    def attempt_checkout() -> None:
        try:
            with pool.connection(tmp_path / "thread.db"):
                pytest.fail("cross-thread checkout must not succeed")
        except CrossThreadAccessError as error:
            errors.put(error)

    worker = threading.Thread(target=attempt_checkout)
    worker.start()
    worker.join()

    # Then: rejection occurs before sqlite can create or use a handle.
    error = errors.get_nowait()
    assert error.owner_thread_id == threading.get_ident()
    assert error.access_thread_id == worker.ident
    pool.shutdown()


def test_shutdown_closes_handles_and_rejects_future_checkout(tmp_path: Path) -> None:
    # Given: a returned pooled handle.
    pool = SQLiteConnectionPool()
    path = tmp_path / "shutdown.db"
    with pool.connection(path) as connection:
        _ = connection.execute("SELECT 1")

    # When: the pool shuts down.
    pool.shutdown()

    # Then: the handle is closed and the pool cannot be reused.
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        _ = connection.execute("SELECT 1")
    with pytest.raises(ConnectionPoolClosedError):
        with pool.connection(path):
            pytest.fail("a shut down pool must remain closed")


def test_manual_checkpoint_executes_truncate_mode(tmp_path: Path) -> None:
    # Given: a WAL database whose reusable handle records executed SQL.
    pool = SQLiteConnectionPool()
    path = tmp_path / "checkpoint.db"
    statements: list[str] = []
    with pool.connection(path) as connection:
        _ = connection.execute("CREATE TABLE sample (value INTEGER)")
        _ = connection.execute("INSERT INTO sample VALUES (1)")
        connection.set_trace_callback(statements.append)

    # When: the explicit checkpoint helper is invoked.
    pool.checkpoint(path)

    # Then: the manual helper issued a truncating WAL checkpoint.
    assert "PRAGMA wal_checkpoint(TRUNCATE)" in statements
    pool.shutdown()
