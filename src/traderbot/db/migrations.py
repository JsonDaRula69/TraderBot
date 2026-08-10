"""Typed, transactional SQLite migrations with durable legacy backups."""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

logger = logging.getLogger(__name__)

_SCHEMA_VERSION_SQL: Final = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"  # noqa: E501


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    description: str
    up_sql: tuple[str, ...]
    down_sql: tuple[str, ...] | None


MigrationError = RuntimeError


class MigrationNotAppliedError(MigrationError):
    def __init__(self, version: int | None) -> None:
        self.version: int | None = version
        super().__init__(f"migration version is not applied: {version}")


class NonLatestMigrationError(MigrationError):
    def __init__(self, requested: int, latest: int) -> None:
        self.requested: int = requested
        self.latest: int = latest
        super().__init__(f"cannot roll back version {requested}; latest applied is {latest}")


class IrreversibleMigrationError(MigrationError):
    def __init__(self, version: int) -> None:
        self.version: int = version
        super().__init__(f"migration {version} is irreversible")


type TableSignature = tuple[tuple[str, str, int, str | None, int], ...]


class _Cursor[T](Protocol):
    def fetchall(self) -> list[T]: ...


class _Connection[T](Protocol):
    def execute(self, sql: str, /) -> _Cursor[T]: ...


def _fetchall[T](connection: _Connection[T], sql: str) -> list[T]:
    return connection.execute(sql).fetchall()


class LegacySchemaMismatchError(MigrationError):
    def __init__(self, table: str, expected: TableSignature, actual: TableSignature) -> None:
        self.table: str = table
        self.expected: TableSignature = expected
        self.actual: TableSignature = actual
        super().__init__(f"legacy table {table!r} has an unexpected schema")


_PROFILES_SQL: Final = "CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')), description TEXT, enabled_categories TEXT, permissions TEXT, risk_multiplier REAL NOT NULL CHECK (risk_multiplier > 0 AND risk_multiplier <= 1.0), max_position_per_market_pct REAL NOT NULL CHECK (max_position_per_market_pct > 0), max_daily_loss_pct REAL NOT NULL CHECK (max_daily_loss_pct > 0), max_drawdown_pct REAL NOT NULL CHECK (max_drawdown_pct > 0), max_open_positions INTEGER NOT NULL CHECK (max_open_positions > 0), min_liquidity_threshold INTEGER NOT NULL CHECK (min_liquidity_threshold > 0), min_edge_pct REAL NOT NULL CHECK (min_edge_pct > 0), initial_balance_cents INTEGER DEFAULT 10000, created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')))"  # noqa: E501

_GLOBAL_V1_SQL: Final = (
    _PROFILES_SQL,
    "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')))",  # noqa: E501
    "CREATE TABLE IF NOT EXISTS market_data (ticker TEXT PRIMARY KEY, last_price REAL, bid REAL, ask REAL, volume REAL, open_interest REAL, updated_at REAL NOT NULL)",  # noqa: E501
    "CREATE TABLE IF NOT EXISTS orderbook (ticker TEXT PRIMARY KEY, bids_json TEXT NOT NULL, asks_json TEXT NOT NULL, updated_at REAL NOT NULL)",  # noqa: E501
    "CREATE TABLE IF NOT EXISTS weather_forecasts (snapshot_ts TEXT NOT NULL, city TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, model TEXT NOT NULL, valid_date TEXT NOT NULL, variable TEXT NOT NULL, value REAL NOT NULL, PRIMARY KEY (snapshot_ts, city, model, valid_date, variable))",  # noqa: E501
    "CREATE TABLE IF NOT EXISTS nws_forecasts (snapshot_ts TEXT NOT NULL, city TEXT NOT NULL, forecast_date TEXT NOT NULL, high_temp_f REAL, low_temp_f REAL, precip_prob REAL, wind_speed REAL, detailed_forecast TEXT, PRIMARY KEY (snapshot_ts, city, forecast_date))",  # noqa: E501
    "CREATE TABLE IF NOT EXISTS settlement_cache (ticker TEXT PRIMARY KEY, outcome INTEGER NOT NULL, settled_at TEXT NOT NULL)",  # noqa: E501
)

GLOBAL_MIGRATIONS: Final = (Migration(1, "Create global TraderBot schema", _GLOBAL_V1_SQL, None),)


def _ordered_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(sorted(migrations, key=lambda migration: migration.version))
    versions = tuple(migration.version for migration in ordered)
    if any(version <= 0 for version in versions) or len(set(versions)) != len(versions):
        raise MigrationError(f"migration versions must be unique positive integers: {versions}")
    return ordered


def _table_names(connection: sqlite3.Connection) -> set[str]:
    typed_connection: _Connection[tuple[str]] = connection
    rows: list[tuple[str]] = _fetchall(
        typed_connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )
    return {row[0] for row in rows}


def _table_signature(connection: sqlite3.Connection, table: str) -> TableSignature:
    quoted_table = table.replace('"', '""')
    typed_connection: _Connection[tuple[int, str, str, int, str | None, int]] = connection
    rows: list[tuple[int, str, str, int, str | None, int]] = _fetchall(
        typed_connection, f'PRAGMA table_info("{quoted_table}")'
    )
    return tuple(
        (name, declared_type.upper(), not_null, default, primary_key)
        for _, name, declared_type, not_null, default, primary_key in rows
    )


def _expected_global_signatures() -> dict[str, TableSignature]:
    with closing(sqlite3.connect(":memory:")) as connection:
        _ = connection.execute(_SCHEMA_VERSION_SQL)
        for statement in _GLOBAL_V1_SQL:
            _ = connection.execute(statement)
        return {table: _table_signature(connection, table) for table in _table_names(connection)}


def _validate_global_tables(connection: sqlite3.Connection, *, existing_only: bool) -> None:
    expected = _expected_global_signatures()
    existing = _table_names(connection)
    for table, signature in expected.items():
        if existing_only and table not in existing:
            continue
        actual = _table_signature(connection, table)
        if actual != signature:
            raise LegacySchemaMismatchError(table, signature, actual)


def _backup_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _reserve_backup_path(db_path: Path) -> Path:
    for _attempt in range(100):
        candidate = db_path.with_name(
            f"{db_path.name}.bak.{_backup_timestamp()}-{secrets.token_hex(4)}"
        )
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return candidate
    raise MigrationError(f"could not reserve a backup name for {db_path}")


def _fsync_path(path: Path, *, best_effort: bool) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        if not best_effort:
            raise
        logger.warning(
            "migration.backup_directory_fsync_best_effort",
            extra={"directory": str(path), "error": str(exc)},
        )
        return
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if not best_effort:
            raise
        logger.warning(
            "migration.backup_directory_fsync_best_effort",
            extra={"directory": str(path), "error": str(exc)},
        )
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if not best_effort:
                raise
            logger.warning(
                "migration.backup_directory_fsync_best_effort",
                extra={"directory": str(path), "error": str(exc)},
            )


def _backup_legacy_database(db_path: Path) -> Path:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{db_path.name}.backup-", dir=db_path.parent)
    os.close(descriptor)
    temp_path = Path(temp_name)
    backup_path: Path | None = None
    published = False
    try:
        with (
            closing(sqlite3.connect(db_path)) as source,
            closing(sqlite3.connect(temp_path)) as target,
        ):
            source.backup(target)
        _fsync_path(temp_path, best_effort=False)
        backup_path = _reserve_backup_path(db_path)
        os.replace(temp_path, backup_path)
        published = True
        _fsync_path(db_path.parent, best_effort=sys.platform == "win32")
        return backup_path
    finally:
        if not published:
            _ = temp_path.unlink(missing_ok=True)
            if backup_path is not None:
                _ = backup_path.unlink(missing_ok=True)


def _prepare_database(db_path: Path, ordered: tuple[Migration, ...]) -> None:
    _ = db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists() or db_path.stat().st_size == 0:
        return
    with closing(sqlite3.connect(db_path)) as connection:
        tables = _table_names(connection)
    if not tables or "schema_version" in tables:
        return
    _ = _backup_legacy_database(db_path)
    if ordered == GLOBAL_MIGRATIONS:
        with closing(sqlite3.connect(db_path)) as connection:
            _validate_global_tables(connection, existing_only=True)


def _apply_one(connection: sqlite3.Connection, migration: Migration, validate_global: bool) -> None:
    _ = connection.execute("BEGIN IMMEDIATE")
    committed = False
    try:
        for statement in migration.up_sql:
            _ = connection.execute(statement)
        if validate_global:
            _validate_global_tables(connection, existing_only=False)
        _ = connection.execute(
            "INSERT INTO schema_version (version, description, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.description, datetime.now(UTC).isoformat()),
        )
        connection.commit()
        committed = True
    finally:
        if not committed and connection.in_transaction:
            connection.rollback()


def apply_migrations(db_path: str | Path, migrations: Sequence[Migration]) -> list[int]:
    """Apply pending migrations atomically and return their versions in order."""
    path = Path(db_path)
    ordered = _ordered_migrations(migrations)
    _prepare_database(path, ordered)
    applied_now: list[int] = []
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        _ = connection.execute(_SCHEMA_VERSION_SQL)
        typed_connection: _Connection[tuple[int]] = connection
        version_rows: list[tuple[int]] = _fetchall(
            typed_connection, "SELECT version FROM schema_version"
        )
        applied = {row[0] for row in version_rows}
        for migration in ordered:
            if migration.version in applied:
                continue
            _apply_one(
                connection, migration, ordered == GLOBAL_MIGRATIONS and migration.version == 1
            )
            applied_now.append(migration.version)
    return applied_now


def rollback_migration(
    db_path: str | Path,
    migrations: Sequence[Migration],
    *,
    version: int | None = None,
) -> int:
    """Atomically roll back the latest applied migration and return its version."""
    ordered = _ordered_migrations(migrations)
    with closing(sqlite3.connect(Path(db_path), isolation_level=None)) as connection:
        tables = _table_names(connection)
        if "schema_version" not in tables:
            raise MigrationNotAppliedError(version)
        typed_connection: _Connection[tuple[int]] = connection
        version_rows: list[tuple[int]] = _fetchall(
            typed_connection, "SELECT version FROM schema_version ORDER BY version"
        )
        applied = tuple(row[0] for row in version_rows)
        if not applied or (version is not None and version not in applied):
            raise MigrationNotAppliedError(version)
        latest = applied[-1]
        requested = latest if version is None else version
        if requested != latest:
            raise NonLatestMigrationError(requested, latest)
        migration = next((item for item in ordered if item.version == requested), None)
        if migration is None:
            raise MigrationNotAppliedError(requested)
        if migration.down_sql is None:
            raise IrreversibleMigrationError(requested)
        _ = connection.execute("BEGIN IMMEDIATE")
        committed = False
        try:
            for statement in migration.down_sql:
                _ = connection.execute(statement)
            _ = connection.execute("DELETE FROM schema_version WHERE version = ?", (requested,))
            connection.commit()
            committed = True
        finally:
            if not committed and connection.in_transaction:
                connection.rollback()
    return requested


def init_schema(db_path: str | Path) -> None:
    """Initialize or migrate the global TraderBot SQLite database."""
    _ = apply_migrations(db_path, GLOBAL_MIGRATIONS)
