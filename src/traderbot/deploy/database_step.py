"""Daemon-aligned storage provisioning for deploy step 5."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, override

from traderbot.db.access import DatabaseAccess
from traderbot.db.chroma_ownership import ChromaCleanupError
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.migrations import init_schema
from traderbot.db.models import SHARED_CHROMA_COLLECTIONS
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.security import create_chroma_root
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.generic import create_category_profile
from traderbot.profiles.sysadmin import create_sysadmin_profile

type DeployMode = Literal["backtest"]

_EXPECTED_SHARED_COLLECTIONS: Final = frozenset(
    {"news", "data_points", "market_patterns", "news_signals", "market_conditions"}
)
_EXPECTED_DECISION_TABLES: Final = frozenset(
    {
        "schema_version",
        "decisions",
        "positions",
        "forecast_snapshots",
        "bias_tracking",
        "learnings",
        "circuit_breaker",
        "portfolio_summary",
    }
)


@dataclass(frozen=True, slots=True)
class DatabaseProvisionReport:
    global_database: Path
    decision_paths: tuple[Path, ...]
    sysadmin_visible_databases: int
    shared_collection_manifest: tuple[str, ...]
    existing_collections: tuple[str, ...]


class DatabaseProvisionError(RuntimeError):
    __slots__: tuple[str, ...] = ("reason",)

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason: str = reason

    @override
    def __str__(self) -> str:
        return f"deploy database provisioning failed: {self.reason}"


class DatabaseCleanupError(ExceptionGroup):
    """Aggregates Chroma and pool cleanup failures in ownership order."""


def _database_tables(connection: sqlite3.Connection) -> frozenset[str]:
    rows: list[tuple[str]] = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(row[0] for row in rows)


def provision_deploy_databases(
    categories: tuple[MarketCategory, ...],
    mode: DeployMode,
    data_root: Path,
) -> DatabaseProvisionReport:
    global_database = data_root / "traderbot.db"
    chroma_root = data_root / "chromadb"
    init_schema(global_database)
    pool = SQLiteConnectionPool()
    chroma: ChromaStore | None = None
    try:
        if not chroma_root.exists():
            create_chroma_root(chroma_root)
        chroma = ChromaStore(chroma_root)
        existing_collections = tuple(chroma.list_collections())
        if SHARED_CHROMA_COLLECTIONS != _EXPECTED_SHARED_COLLECTIONS:
            raise DatabaseProvisionError("shared Chroma collection manifest mismatch")

        access = DatabaseAccess(pool, data_root)
        decision_paths: list[Path] = []
        for category in categories:
            profile = create_category_profile(category.value, mode, (category,))
            path = data_root / f"{mode}-{profile.name}" / "db" / "decisions.db"
            if not path.resolve().is_relative_to(data_root.resolve()):
                raise DatabaseProvisionError("derived decisions path escapes deploy data root")
            with access.writable_decisions((profile, category.value)) as connection:
                if _database_tables(connection) != _EXPECTED_DECISION_TABLES:
                    raise DatabaseProvisionError("category decisions schema mismatch")
                _ = connection.execute("UPDATE schema_version SET version = version")
            decision_paths.append(path.resolve())

        sysadmin = create_sysadmin_profile()
        with access.all_agent_decisions((sysadmin, "sysadmin")) as connections:
            for connection in connections:
                if _database_tables(connection) != _EXPECTED_DECISION_TABLES:
                    raise DatabaseProvisionError("SysAdmin observed an invalid decisions schema")
            visible = len(connections)
        return DatabaseProvisionReport(
            global_database=global_database.resolve(),
            decision_paths=tuple(decision_paths),
            sysadmin_visible_databases=visible,
            shared_collection_manifest=tuple(sorted(SHARED_CHROMA_COLLECTIONS)),
            existing_collections=existing_collections,
        )
    finally:
        cleanup_errors: list[Exception] = []
        try:
            if chroma is not None:
                try:
                    chroma.close()
                except (
                    ChromaCleanupError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    cleanup_errors.append(exc)
        finally:
            try:
                pool.shutdown()
            except (OSError, RuntimeError, sqlite3.Error, TypeError) as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise DatabaseCleanupError("deploy storage cleanup failed", cleanup_errors)


__all__ = [
    "DatabaseProvisionError",
    "DatabaseCleanupError",
    "DatabaseProvisionReport",
    "DeployMode",
    "provision_deploy_databases",
]
