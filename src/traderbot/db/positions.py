"""SQLite persistence for trading positions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

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
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()


def upsert(conn: sqlite3.Connection, position: Position) -> None:
    """Insert or replace a position by its unique ticker."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO positions (ticker, quantity, avg_price, settlement_result, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            position.ticker,
            position.quantity,
            position.avg_price,
            position.settlement_result,
            now,
        ),
    )
    conn.commit()


def get(conn: sqlite3.Connection, ticker: str) -> DbPosition | None:
    """Return a position by ticker, or None if not found."""
    row = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    if row is None:
        return None
    return _row_to_model(row)


def list_all(conn: sqlite3.Connection) -> list[DbPosition]:
    """Return all positions ordered by ticker."""
    rows = conn.execute("SELECT * FROM positions ORDER BY ticker").fetchall()
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


def _row_to_model(row: sqlite3.Row) -> DbPosition:
    """Convert a sqlite3.Row to a DbPosition, parsing datetime strings."""
    data = dict(row)
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    if data.get("settlement_result") is not None:
        data["settlement_result"] = bool(data["settlement_result"])
    return DbPosition.model_validate(data)
