"""SQLite persistence for trade decisions and audit trail."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import sqlite3

    from traderbot.kalshi.models import Decision


class DbDecision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    timestamp: datetime
    ticker: str
    direction: Literal["yes", "no", "neutral"]
    quantity: Annotated[int, Field(ge=0)]
    price: Annotated[int, Field(ge=0, description="Price in cents")]
    signal_strength: Annotated[float, Field(ge=0, le=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    edge_estimate: float
    risk_checks: dict[str, bool]
    outcome: Literal["executed", "rejected", "held"]
    rejection_reason: str | None = None
    actual_result: bool | None = None


def init_table(conn: sqlite3.Connection) -> None:
    """Create the decisions table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL,
            signal_strength REAL NOT NULL,
            confidence REAL NOT NULL,
            edge_estimate REAL NOT NULL,
            risk_checks TEXT NOT NULL,
            outcome TEXT NOT NULL,
            rejection_reason TEXT,
            actual_result INTEGER
        )"""
    )
    conn.commit()


def insert(conn: sqlite3.Connection, decision: Decision) -> int:
    """Insert a decision and return its rowid."""
    cursor = conn.execute(
        """INSERT INTO decisions
           (timestamp, ticker, direction, quantity, price, signal_strength,
            confidence, edge_estimate, risk_checks, outcome, rejection_reason,
            actual_result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision.timestamp.isoformat(),
            decision.ticker,
            decision.direction,
            decision.quantity,
            decision.price,
            decision.signal_strength,
            decision.confidence,
            decision.edge_estimate,
            json.dumps(decision.risk_checks),
            decision.outcome,
            decision.rejection_reason,
            decision.actual_result,
        ),
    )
    conn.commit()
    logger.info("Stored decision for %s: direction=%s outcome=%s qty=%d", decision.ticker, decision.direction, decision.outcome, decision.quantity)
    return cursor.lastrowid


def get(conn: sqlite3.Connection, id: int) -> DbDecision | None:
    """Return a decision by id, or None if not found."""
    row = conn.execute("SELECT * FROM decisions WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    return _row_to_model(row)


def list_by_ticker(conn: sqlite3.Connection, ticker: str) -> list[DbDecision]:
    """Return all decisions for a given ticker."""
    rows = conn.execute(
        "SELECT * FROM decisions WHERE ticker = ? ORDER BY timestamp", (ticker,)
    ).fetchall()
    logger.debug("Queried %d decisions for ticker '%s'", len(rows), ticker)
    return [_row_to_model(r) for r in rows]


def list_by_date_range(
    conn: sqlite3.Connection,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[DbDecision]:
    """Return decisions within an optional date range."""
    if start and end:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    elif start:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE timestamp >= ? ORDER BY timestamp",
            (start.isoformat(),),
        ).fetchall()
    elif end:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE timestamp <= ? ORDER BY timestamp",
            (end.isoformat(),),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM decisions ORDER BY timestamp").fetchall()
    return [_row_to_model(r) for r in rows]


def list_by_outcome(conn: sqlite3.Connection, outcome: str) -> list[DbDecision]:
    """Return all decisions with the given outcome."""
    rows = conn.execute(
        "SELECT * FROM decisions WHERE outcome = ? ORDER BY timestamp", (outcome,)
    ).fetchall()
    logger.debug("Queried %d decisions with outcome '%s'", len(rows), outcome)
    return [_row_to_model(r) for r in rows]


def update_actual_result(conn: sqlite3.Connection, id: int, result: bool) -> None:
    """Set the actual_result for a decision."""
    conn.execute("UPDATE decisions SET actual_result = ? WHERE id = ?", (result, id))
    conn.commit()
    logger.info("Updated actual_result for decision %d: %s", id, result)


def count(conn: sqlite3.Connection) -> int:
    """Return the total number of decisions."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM decisions").fetchone()
    cnt = row["cnt"]
    logger.debug("Decision count: %d", cnt)
    return cnt


def _row_to_model(row: sqlite3.Row) -> DbDecision:
    """Convert a sqlite3.Row to a DbDecision, parsing JSON and datetime."""
    data = dict(row)
    if isinstance(data.get("timestamp"), str):
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    data["risk_checks"] = json.loads(data["risk_checks"])
    if data.get("actual_result") is not None:
        data["actual_result"] = bool(data["actual_result"])
    return DbDecision.model_validate(data)
