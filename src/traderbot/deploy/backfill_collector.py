from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Final

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_collector_schema import copy_collector, preflight_collector
from traderbot.deploy.backfill_collector_types import (
    CollectorPathError,
    CollectorSchemaError,
    PreparedCollector,
)
from traderbot.deploy.backfill_models import CollectorCounts

_QUERY_ONLY: Final = "PRAGMA query_only=ON"


def validate_collector_path(path: Path) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    current = lexical
    while current != current.parent:
        if current.is_symlink():
            raise CollectorPathError("links are not allowed")
        current = current.parent
    try:
        metadata = lexical.lstat()
    except FileNotFoundError as exc:
        raise CollectorPathError("file does not exist") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CollectorPathError("path must be a regular non-linked file")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise CollectorPathError("file must be owned by the current user")
    if metadata.st_mode & stat.S_IRUSR == 0:
        raise CollectorPathError("file is not owner-readable")
    return lexical


def _identity(path: Path) -> tuple[int, int, int, int]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise CollectorPathError("source identity changed during snapshot") from exc
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


def _query_only(connection: sqlite3.Connection) -> int:
    _ = connection.execute(_QUERY_ONLY)
    if connection.execute("PRAGMA query_only").fetchone() != (1,):
        raise CollectorPathError("source query-only mode could not be proven")
    return 1


def _backup_source(
    source: Path,
    snapshot_path: Path,
    during_snapshot: Callable[[], None] | None,
) -> int:
    callback_called = False

    def progress(status: int, remaining: int, total: int) -> None:
        nonlocal callback_called
        _ = (status, remaining, total)
        if during_snapshot is not None and not callback_called:
            callback_called = True
            during_snapshot()

    try:
        with (
            closing(
                sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, isolation_level=None)
            ) as source_connection,
            closing(sqlite3.connect(snapshot_path, isolation_level=None)) as snapshot_connection,
        ):
            query_only = _query_only(source_connection)
            _ = source_connection.execute("BEGIN")
            source_connection.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()
            source_connection.backup(snapshot_connection, pages=256, progress=progress)
            source_connection.rollback()
            return query_only
    except sqlite3.Error as exc:
        raise CollectorPathError("source is not a readable SQLite database") from exc


def _preflight_snapshot(snapshot_path: Path) -> None:
    try:
        with closing(
            sqlite3.connect(
                f"{snapshot_path.as_uri()}?mode=ro&immutable=1", uri=True, isolation_level=None
            )
        ) as snapshot_connection:
            _ = _query_only(snapshot_connection)
            preflight_collector(snapshot_connection)
    except sqlite3.Error as exc:
        raise CollectorPathError("source snapshot is not readable") from exc


@contextmanager
def prepare_collector_source(
    source_path: Path,
    *,
    during_snapshot: Callable[[], None] | None = None,
    after_snapshot: Callable[[], None] | None = None,
) -> Generator[PreparedCollector, None, None]:
    source = validate_collector_path(source_path)
    identity = _identity(source)
    descriptor, temp_name = tempfile.mkstemp(prefix=".traderbot-collector-snapshot-")
    os.close(descriptor)
    snapshot_path = Path(temp_name)

    try:
        query_only = _backup_source(source, snapshot_path, during_snapshot)
        if _identity(source) != identity:
            raise CollectorPathError("source identity or content changed during snapshot")
        snapshot_path.chmod(0o600)
        _preflight_snapshot(snapshot_path)
        if _identity(source) != identity:
            raise CollectorPathError("source identity or content changed during snapshot")
        prepared = PreparedCollector(path=snapshot_path, query_only=query_only)
        if after_snapshot is not None:
            after_snapshot()
        yield prepared
    finally:
        _ = snapshot_path.unlink(missing_ok=True)


def import_prepared_collector(
    prepared: PreparedCollector,
    target_path: Path,
    pool: SQLiteConnectionPool,
) -> CollectorCounts:
    with closing(
        sqlite3.connect(
            f"{prepared.path.as_uri()}?mode=ro&immutable=1", uri=True, isolation_level=None
        )
    ) as connection:
        _ = _query_only(connection)
        return copy_collector(connection, target_path, pool)


def import_collector(
    source_path: Path,
    target_path: Path,
    pool: SQLiteConnectionPool,
    *,
    during_snapshot: Callable[[], None] | None = None,
    after_snapshot: Callable[[], None] | None = None,
) -> CollectorCounts:
    with prepare_collector_source(
        source_path,
        during_snapshot=during_snapshot,
        after_snapshot=after_snapshot,
    ) as prepared:
        return import_prepared_collector(prepared, target_path, pool)


__all__ = [
    "CollectorPathError",
    "CollectorSchemaError",
    "PreparedCollector",
    "import_collector",
    "import_prepared_collector",
    "prepare_collector_source",
    "validate_collector_path",
]
