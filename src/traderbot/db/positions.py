"""SQLite persistence for trading positions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import sqlite3

    from traderbot.kalshi.models import Position


class DbPosition(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    ticker: str
    quantity: Annotated[int, Field(ge=0)]
    avg_price: Annotated[int, Field(ge=0, description="Average price in cents")]
    settlement_result: bool | None = None
    pnl_cents: int = 0
    updated_at: datetime


def init_table(conn: sqlite3.Connection) -> None:
    """Create the positions table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            avg_price INTEGER NOT NULL DEFAULT 0,
            settlement_result INTEGER,
            pnl_cents INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    _ensure_column(
        conn,
        "positions",
        "pnl_cents",
        "ALTER TABLE positions ADD COLUMN pnl_cents INTEGER DEFAULT 0",
    )
    conn.commit()

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(ddl)


def upsert(conn: sqlite3.Connection, position: Position) -> None:
    """Insert or replace a position by its unique ticker, preserving existing pnl_cents."""
    now = datetime.now(UTC).isoformat()
    existing = conn.execute(
        "SELECT pnl_cents FROM positions WHERE ticker = ?", (position.ticker,)
    ).fetchone()
    pnl_cents = existing["pnl_cents"] if existing else 0
    conn.execute(
        """INSERT OR REPLACE INTO positions
           (ticker, quantity, avg_price, settlement_result, pnl_cents, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            position.ticker,
            position.quantity,
            position.avg_price,
            position.settlement_result,
            pnl_cents,
            now,
        ),
    )
    conn.commit()
    logger.info("Upserted position %s: qty=%d price=%d", position.ticker, position.quantity, position.avg_price)


def get(conn: sqlite3.Connection, ticker: str) -> DbPosition | None:
    """Return a position by ticker, or None if not found."""
    row = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    if row is None:
        return None
    return _row_to_model(row)


def list_all(conn: sqlite3.Connection) -> list[DbPosition]:
    """Return all positions ordered by ticker."""
    rows = conn.execute("SELECT * FROM positions ORDER BY ticker").fetchall()
    logger.debug("Listed %d positions", len(rows))
    return [_row_to_model(r) for r in rows]


def delete(conn: sqlite3.Connection, ticker: str) -> None:
    """Delete a position by ticker."""
    conn.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    conn.commit()


def update_avg_price(
    conn: sqlite3.Connection,
    ticker: str,
    additional_quantity: int,
    new_price_cents: int,
) -> None:
    """Update position with weighted-average price after adding quantity."""
    row = conn.execute(
        "SELECT quantity, avg_price FROM positions WHERE ticker = ?", (ticker,)
    ).fetchone()
    if row is None:
        logger.warning("Cannot update avg price: position '%s' not found", ticker)
        raise ValueError(f"Position not found: {ticker}")
    old_qty: int = row["quantity"]
    old_avg: int = row["avg_price"]
    new_qty = old_qty + additional_quantity
    new_avg = (old_avg * old_qty + new_price_cents * additional_quantity) // new_qty
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE positions SET quantity = ?, avg_price = ?, updated_at = ? WHERE ticker = ?",
        (new_qty, new_avg, now, ticker),
    )
    conn.commit()


def update_settlement(
    conn: sqlite3.Connection,
    ticker: str,
    result: bool,
    pnl_cents: int,
) -> bool:
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        "UPDATE positions SET settlement_result = ?, pnl_cents = ?, updated_at = ? WHERE ticker = ?",
        (int(result), pnl_cents, now, ticker),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    if updated:
        logger.info("Updated settlement for %s: result=%s pnl=%d", ticker, result, pnl_cents)
    else:
        logger.warning("No position found to update settlement for ticker '%s'", ticker)
    return updated


def mark_closed(conn: sqlite3.Connection, ticker: str) -> bool:
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        "UPDATE positions SET quantity = 0, avg_price = 0, updated_at = ? WHERE ticker = ?",
        (now, ticker),
    )
    conn.commit()
    closed = cursor.rowcount > 0
    if closed:
        logger.info("Marked position '%s' as closed", ticker)
    return closed


def count_open(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM positions WHERE settlement_result IS NULL AND quantity > 0"
    ).fetchone()
    return row[0] if row else 0


def _row_to_model(row: sqlite3.Row) -> DbPosition:
    """Convert a sqlite3.Row to a DbPosition, parsing datetime strings."""
    data = dict(row)
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    if data.get("settlement_result") is not None:
        data["settlement_result"] = bool(data["settlement_result"])
    return DbPosition.model_validate(data)
