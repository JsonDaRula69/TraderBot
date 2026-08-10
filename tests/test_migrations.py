"""Integration tests for the typed SQLite migration runner."""

from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from traderbot.db import migrations
from traderbot.db.migrations import (
    GLOBAL_MIGRATIONS,
    IrreversibleMigrationError,
    LegacySchemaMismatchError,
    Migration,
    MigrationNotAppliedError,
    NonLatestMigrationError,
    apply_migrations,
    init_schema,
    rollback_migration,
)


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _versions(db_path: Path) -> list[int]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    return [int(row[0]) for row in rows]


def test_migration_is_immutable() -> None:
    migration = Migration(1, "immutable", ("SELECT 1",), None)

    with pytest.raises(FrozenInstanceError):
        migration.version = 2


def test_apply_orders_migrations_and_skips_applied(tmp_path: Path) -> None:
    db_path = tmp_path / "ordered.db"
    ordered = (
        Migration(2, "second", ("ALTER TABLE sample ADD COLUMN label TEXT",), None),
        Migration(1, "first", ("CREATE TABLE sample (id INTEGER PRIMARY KEY)",), None),
    )

    assert apply_migrations(db_path, ordered) == [1, 2]
    assert apply_migrations(db_path, ordered) == []
    assert _versions(db_path) == [1, 2]


def test_failed_migration_rolls_back_statements_and_stamp(tmp_path: Path) -> None:
    db_path = tmp_path / "failed-up.db"
    migration = Migration(
        1,
        "fails atomically",
        ("CREATE TABLE transient (id INTEGER)", "INSERT INTO missing VALUES (1)"),
        None,
    )

    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(db_path, (migration,))

    assert "transient" not in _table_names(db_path)
    assert _versions(db_path) == []


def test_begin_immediate_rejects_competing_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "locked.db"
    with sqlite3.connect(db_path, isolation_level=None) as writer:
        writer.execute("CREATE TABLE legacy (id INTEGER)")
        writer.execute(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, "
            "description TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        writer.execute("BEGIN IMMEDIATE")
        migration = Migration(1, "locked", ("CREATE TABLE blocked (id INTEGER)",), None)

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            apply_migrations(db_path, (migration,))

    assert "blocked" not in _table_names(db_path)


def test_rollback_removes_only_highest_applied_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "rollback.db"
    chain = (
        Migration(1, "one", ("CREATE TABLE one (id INTEGER)",), ("DROP TABLE one",)),
        Migration(2, "two", ("CREATE TABLE two (id INTEGER)",), ("DROP TABLE two",)),
    )
    apply_migrations(db_path, chain)

    assert rollback_migration(db_path, chain) == 2
    assert _versions(db_path) == [1]
    assert _table_names(db_path).isdisjoint({"two"})


def test_rollback_rejects_unapplied_and_non_latest_versions(tmp_path: Path) -> None:
    db_path = tmp_path / "guarded-rollback.db"
    chain = (
        Migration(1, "one", ("CREATE TABLE one (id INTEGER)",), ("DROP TABLE one",)),
        Migration(2, "two", ("CREATE TABLE two (id INTEGER)",), ("DROP TABLE two",)),
        Migration(3, "three", ("CREATE TABLE three (id INTEGER)",), ("DROP TABLE three",)),
    )
    apply_migrations(db_path, chain[:2])

    with pytest.raises(NonLatestMigrationError):
        rollback_migration(db_path, chain, version=1)
    with pytest.raises(MigrationNotAppliedError):
        rollback_migration(db_path, chain, version=3)


def test_rollback_rejects_irreversible_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "irreversible.db"
    migration = Migration(1, "forward only", ("CREATE TABLE kept (id INTEGER)",), None)
    apply_migrations(db_path, (migration,))

    with pytest.raises(IrreversibleMigrationError):
        rollback_migration(db_path, (migration,))

    assert _versions(db_path) == [1]


def test_failed_rollback_restores_schema_and_stamp(tmp_path: Path) -> None:
    db_path = tmp_path / "failed-down.db"
    migration = Migration(
        1,
        "bad down",
        ("CREATE TABLE retained (id INTEGER)",),
        ("DROP TABLE retained", "DROP TABLE missing"),
    )
    apply_migrations(db_path, (migration,))

    with pytest.raises(sqlite3.OperationalError):
        rollback_migration(db_path, (migration,))

    assert "retained" in _table_names(db_path)
    assert _versions(db_path) == [1]


def test_init_schema_is_idempotent_and_creates_global_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "global.db"

    init_schema(db_path)
    init_schema(db_path)

    assert _versions(db_path) == [1]
    assert _table_names(db_path).issuperset(
        {
            "schema_version",
            "profiles",
            "config",
            "market_data",
            "orderbook",
            "weather_forecasts",
            "nws_forecasts",
            "settlement_cache",
        }
    )
    assert GLOBAL_MIGRATIONS[0].version == 1


def test_legacy_database_is_backed_up_and_preserved(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE market_data (ticker TEXT PRIMARY KEY, last_price REAL, "
            "bid REAL, ask REAL, volume REAL, open_interest REAL, updated_at REAL NOT NULL)"
        )
        connection.execute("INSERT INTO market_data VALUES ('LEGACY', 1, 2, 3, 4, 5, 6)")
        connection.execute("CREATE TABLE custom_legacy (value TEXT)")
        connection.execute("INSERT INTO custom_legacy VALUES ('preserved')")

    init_schema(db_path)

    backups = list(tmp_path.glob("legacy.db.bak.*"))
    assert len(backups) == 1
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT value FROM custom_legacy").fetchone() == ("preserved",)
        assert connection.execute("SELECT ticker FROM market_data").fetchone() == ("LEGACY",)
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert "schema_version" not in _table_names(backups[0])


def test_legacy_signature_mismatch_fails_closed_after_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "mismatch.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE market_data (ticker TEXT PRIMARY KEY, updated_at TEXT)")

    with pytest.raises(LegacySchemaMismatchError):
        init_schema(db_path)

    assert len(list(tmp_path.glob("mismatch.db.bak.*"))) == 1
    assert "schema_version" not in _table_names(db_path)


def test_backup_collision_preserves_existing_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "collision.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE custom_legacy (value TEXT)")
    old_backup = tmp_path / "collision.db.bak.20000101T000000Z-collision"
    old_backup.write_text("old", encoding="utf-8")
    tokens = iter(("collision", "fresh"))
    monkeypatch.setattr(migrations, "_backup_timestamp", lambda: "20000101T000000Z")
    monkeypatch.setattr(migrations.secrets, "token_hex", lambda _size: next(tokens))

    apply_migrations(db_path, (Migration(1, "new", ("CREATE TABLE new (id INTEGER)",), None),))

    assert old_backup.read_text(encoding="utf-8") == "old"
    assert (tmp_path / "collision.db.bak.20000101T000000Z-fresh").exists()


def test_backup_fsyncs_file_before_publish_and_directory_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "durable.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE custom_legacy (value TEXT)")
    events: list[str] = []
    real_replace = migrations.os.replace

    def record_fsync(path: Path, *, best_effort: bool) -> None:
        del best_effort
        events.append("directory" if path.is_dir() else "file")

    monkeypatch.setattr(migrations, "_fsync_path", record_fsync)

    def record_replace(source: Path, target: Path) -> None:
        events.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(migrations.os, "replace", record_replace)
    apply_migrations(
        db_path, (Migration(1, "durable", ("CREATE TABLE durable (id INTEGER)",), None),)
    )

    assert events == ["file", "replace", "directory"]


def test_backup_failure_cleans_temp_and_runs_no_migration_sql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "publication-failure.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE custom_legacy (value TEXT)")
    prior_backup = tmp_path / "publication-failure.db.bak.prior"
    prior_backup.write_text("keep", encoding="utf-8")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise PermissionError

    monkeypatch.setattr(migrations.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        apply_migrations(
            db_path, (Migration(1, "blocked", ("CREATE TABLE forbidden (id INTEGER)",), None),)
        )

    assert prior_backup.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".publication-failure.db.backup-*"))
    assert "schema_version" not in _table_names(db_path)
    assert "forbidden" not in _table_names(db_path)
