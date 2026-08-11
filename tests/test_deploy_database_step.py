"""Behavioral tests for deploy step 5 database and Chroma provisioning."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from traderbot.db.access import DatabaseIdentity
from traderbot.db.chroma_store import ChromaOwnershipError, ChromaStore
from traderbot.db.models import SHARED_CHROMA_COLLECTIONS
from traderbot.db.security import create_chroma_root
from traderbot.deploy.database_step import provision_deploy_databases
from traderbot.kalshi.models import MarketCategory

_DECISION_TABLES = {
    "schema_version",
    "decisions",
    "positions",
    "forecast_snapshots",
    "bias_tracking",
    "learnings",
    "circuit_breaker",
    "portfolio_summary",
}


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def test_selected_category_databases_and_lazy_chroma_are_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an isolated fresh deployment root with two selected categories.
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(tmp_path))
    categories = (MarketCategory.WEATHER, MarketCategory.CRYPTO)

    # When: step 5 provisions storage twice.
    first = provision_deploy_databases(categories, "backtest", tmp_path)
    second = provision_deploy_databases(categories, "backtest", tmp_path)

    # Then: only selected category databases exist with the complete current schema.
    expected_paths = {
        tmp_path / "backtest-weather" / "db" / "decisions.db",
        tmp_path / "backtest-crypto" / "db" / "decisions.db",
    }
    assert set(first.decision_paths) == expected_paths
    assert set(second.decision_paths) == expected_paths
    assert all(_tables(path) == _DECISION_TABLES for path in expected_paths)
    assert not tuple(tmp_path.glob("*-sysadmin/db/decisions.db"))
    assert first.sysadmin_visible_databases == 2
    assert first.shared_collection_manifest == tuple(sorted(SHARED_CHROMA_COLLECTIONS))

    # Then: deploy created no dimensionless collections and released ownership for reopen.
    with ChromaStore(tmp_path / "chromadb") as reopened:
        assert reopened.list_collections() == []


def test_chroma_lock_contention_blocks_before_category_database_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the hardened Chroma root is already owned by another component.
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(tmp_path))
    root = tmp_path / "chromadb"
    create_chroma_root(root)
    owner = ChromaStore(root)

    # When/Then: deploy reports contention without deleting state or creating category DBs.
    with pytest.raises(ChromaOwnershipError):
        _ = provision_deploy_databases((MarketCategory.WEATHER,), "backtest", tmp_path)
    assert root.is_dir()
    assert not (tmp_path / "backtest-weather" / "db" / "decisions.db").exists()

    owner.close()
    report = provision_deploy_databases((MarketCategory.WEATHER,), "backtest", tmp_path)
    assert len(report.decision_paths) == 1


def test_failure_closes_chroma_before_pool_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: instrumented storage adapters and a category schema verification failure.
    import traderbot.deploy.database_step as database_step

    calls: list[str] = []

    class Pool:
        def shutdown(self) -> None:
            calls.append("pool:shutdown")

    class Chroma:
        def __init__(self, root: Path) -> None:
            del root
            calls.append("chroma:open")

        def list_collections(self) -> list[str]:
            return []

        def close(self) -> None:
            calls.append("chroma:close")

    class Access:
        def __init__(self, pool: Pool, root: Path) -> None:
            del pool, root

        @contextmanager
        def writable_decisions(
            self,
            identity: DatabaseIdentity,
        ) -> Generator[sqlite3.Connection, None, None]:
            del identity
            with sqlite3.connect(":memory:") as connection:
                yield connection

    monkeypatch.setattr(database_step, "init_schema", lambda path: calls.append("schema"))
    monkeypatch.setattr(database_step, "SQLiteConnectionPool", Pool)
    monkeypatch.setattr(database_step, "create_chroma_root", lambda path: calls.append("root"))
    monkeypatch.setattr(database_step, "ChromaStore", Chroma)
    monkeypatch.setattr(database_step, "DatabaseAccess", Access)

    # When: provisioning fails after Chroma ownership was acquired.
    with pytest.raises(database_step.DatabaseProvisionError):
        _ = provision_deploy_databases((MarketCategory.WEATHER,), "backtest", tmp_path)

    # Then: cleanup exactly mirrors daemon ownership order.
    assert calls == ["schema", "root", "chroma:open", "chroma:close", "pool:shutdown"]
