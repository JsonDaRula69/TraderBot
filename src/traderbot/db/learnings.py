"""SQLite persistence for pattern learning and self-improvement."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import sqlite3


class LearningCategory(StrEnum):
    """Categories for learned patterns."""

    MARKET_BEHAVIOR = "MarketBehavior"
    RISK_SIGNAL = "RiskSignal"
    TIMING = "Timing"
    STRATEGY = "Strategy"
    EXECUTION = "Execution"


class LearningStatus(StrEnum):
    """Status of a learned pattern."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"


class LearningRecord(BaseModel):
    """A single learned pattern with metadata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    category: LearningCategory
    summary: str
    evidence: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    status: LearningStatus = LearningStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


def init_table(conn: sqlite3.Connection) -> None:
    """Create the learnings table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            evidence TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()


def record_pattern(
    conn: sqlite3.Connection,
    category: LearningCategory,
    summary: str,
    evidence: str,
    confidence: float,
) -> int:
    """Insert a learning and return its rowid."""
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        """INSERT INTO learnings (category, summary, evidence, confidence, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            category.value,
            summary,
            evidence,
            confidence,
            LearningStatus.ACTIVE.value,
            now,
            now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get(conn: sqlite3.Connection, learning_id: int) -> LearningRecord | None:
    """Return a learning by id, or None if not found."""
    row = conn.execute("SELECT * FROM learnings WHERE id = ?", (learning_id,)).fetchone()
    if row is None:
        return None
    return _row_to_model(row)


def get_patterns(
    conn: sqlite3.Connection,
    category: LearningCategory | None = None,
    min_confidence: float = 0.0,
) -> list[LearningRecord]:
    """Query patterns with optional filters."""
    if category is not None:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE category = ? AND confidence >= ? ORDER BY confidence DESC",
            (category.value, min_confidence),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE confidence >= ? ORDER BY confidence DESC",
            (min_confidence,),
        ).fetchall()
    return [_row_to_model(r) for r in rows]


def promote_pattern(conn: sqlite3.Connection, learning_id: int, confidence: float) -> None:
    """Update confidence after validation. Never exceeds 1.0."""
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")
    now = datetime.now(UTC).isoformat()
    row = conn.execute("SELECT confidence FROM learnings WHERE id = ?", (learning_id,)).fetchone()
    if row is None:
        raise ValueError(f"Learning not found: {learning_id}")
    new_confidence = min(row["confidence"] + confidence, 1.0)
    conn.execute(
        "UPDATE learnings SET confidence = ?, updated_at = ? WHERE id = ?",
        (new_confidence, now, learning_id),
    )
    conn.commit()


def deprecate_pattern(conn: sqlite3.Connection, learning_id: int) -> None:
    """Mark pattern as no longer valid."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE learnings SET status = ?, updated_at = ? WHERE id = ?",
        (LearningStatus.DEPRECATED.value, now, learning_id),
    )
    conn.commit()


def get_top_patterns(conn: sqlite3.Connection, n: int = 10) -> list[LearningRecord]:
    """Return the n highest confidence active patterns."""
    rows = conn.execute(
        "SELECT * FROM learnings WHERE status = ? ORDER BY confidence DESC LIMIT ?",
        (LearningStatus.ACTIVE.value, n),
    ).fetchall()
    return [_row_to_model(r) for r in rows]


def count(conn: sqlite3.Connection) -> int:
    """Return total number of learnings."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM learnings").fetchone()
    return row["cnt"]


def _row_to_model(row: sqlite3.Row) -> LearningRecord:
    """Convert a sqlite3.Row to a LearningRecord."""
    data = dict(row)
    data["category"] = LearningCategory(data["category"])
    data["status"] = LearningStatus(data["status"])
    if isinstance(data.get("created_at"), str):
        data["created_at"] = datetime.fromisoformat(data["created_at"])
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    return LearningRecord.model_validate(data)
