"""SQLite persistence layer for positions and decisions."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.db.decisions import init_table as init_decisions_table
from traderbot.db.positions import init_table as init_positions_table
from traderbot.paths import get_db_path as _get_db_path

if TYPE_CHECKING:
    from collections.abc import Iterator

DB_PATH: Path = _get_db_path()


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        path.chmod(0o600)
    except OSError:
        pass
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Create positions and decisions tables if they do not exist."""
    init_positions_table(conn)
    init_decisions_table(conn)


__all__ = ["DB_PATH", "get_connection", "init_schema"]
