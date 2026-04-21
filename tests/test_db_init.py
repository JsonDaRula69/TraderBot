"""Tests for db/__init__.py — connection management and schema init."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.db import get_connection, init_schema

if TYPE_CHECKING:
    from pathlib import Path


class TestGetConnection:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            conn.execute("SELECT 1")
        assert db_file.exists()

    def test_wal_mode_set(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_foreign_keys_on(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_file = tmp_path / "nested" / "dir" / "test.db"
        with get_connection(db_file) as conn:
            conn.execute("SELECT 1")
        assert db_file.exists()


class TestInitSchema:
    def test_creates_positions_table(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
            ).fetchall()
        assert len(rows) == 1

    def test_creates_decisions_table(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'"
            ).fetchall()
        assert len(rows) == 1