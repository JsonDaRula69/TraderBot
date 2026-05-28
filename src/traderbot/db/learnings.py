"""SQLite persistence for pattern learning and self-improvement."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

logger = logging.getLogger(__name__)

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
    FEATURE_REQUEST = "FeatureRequest"


class LearningStatus(StrEnum):
    """Status of a learned pattern."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"


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


class Priority(StrEnum):
    """Priority levels for feature requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeatureRequestRecord(BaseModel):
    """A feature request entry with full metadata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    category: LearningCategory
    pattern_key: str
    summary: str
    evidence: str
    justification: str
    impact: str
    priority: Priority
    recurrence_count: int
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
            updated_at TEXT NOT NULL,
            pattern_key TEXT,
            recurrence_count INTEGER DEFAULT 1,
            justification TEXT,
            impact TEXT,
            priority TEXT
        )"""
    )
    _migrate_feature_request_columns(conn)
    conn.commit()


def _migrate_feature_request_columns(conn: sqlite3.Connection) -> None:
    """Add feature-request columns if they don't exist."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(learnings)").fetchall()}
    if "pattern_key" not in cols:
        conn.execute("ALTER TABLE learnings ADD COLUMN pattern_key TEXT")
    if "recurrence_count" not in cols:
        conn.execute("ALTER TABLE learnings ADD COLUMN recurrence_count INTEGER DEFAULT 1")
    if "justification" not in cols:
        conn.execute("ALTER TABLE learnings ADD COLUMN justification TEXT")
    if "impact" not in cols:
        conn.execute("ALTER TABLE learnings ADD COLUMN impact TEXT")
    if "priority" not in cols:
        conn.execute("ALTER TABLE learnings ADD COLUMN priority TEXT")


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
    logger.info("Recorded learning pattern: category=%s summary='%s' confidence=%.2f", category.value, summary, confidence)
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
    logger.debug("Querying patterns: category=%s min_confidence=%.2f", category.value if category else None, min_confidence)
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
    logger.info("Promoted pattern %d to confidence=%.2f", learning_id, new_confidence)


def deprecate_pattern(conn: sqlite3.Connection, learning_id: int) -> None:
    """Mark pattern as no longer valid."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE learnings SET status = ?, updated_at = ? WHERE id = ?",
        (LearningStatus.DEPRECATED.value, now, learning_id),
    )
    conn.commit()
    logger.info("Deprecated pattern %d", learning_id)


def record_feature_request(
    conn: sqlite3.Connection,
    pattern_key: str,
    summary: str,
    evidence: str,
    justification: str,
    impact: str,
    priority: Priority,
    confidence: float = 0.5,
) -> int:
    """Insert a feature request and return its rowid."""
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        """INSERT INTO learnings
           (category, summary, evidence, confidence, status, created_at, updated_at,
            pattern_key, recurrence_count, justification, impact, priority)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            LearningCategory.FEATURE_REQUEST.value,
            summary,
            evidence,
            confidence,
            LearningStatus.ACTIVE.value,
            now,
            now,
            pattern_key,
            1,
            justification,
            impact,
            priority.value,
        ),
    )
    conn.commit()
    logger.info("Recorded feature request: key='%s' priority=%s", pattern_key, priority.value)
    return cursor.lastrowid


def increment_recurrence(conn: sqlite3.Connection, learning_id: int) -> int:
    """Increment recurrence_count and return the new value."""
    now = datetime.now(UTC).isoformat()
    row = conn.execute(
        "SELECT recurrence_count FROM learnings WHERE id = ?", (learning_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Learning not found: {learning_id}")
    new_count = (row["recurrence_count"] or 1) + 1
    conn.execute(
        "UPDATE learnings SET recurrence_count = ?, updated_at = ? WHERE id = ?",
        (new_count, now, learning_id),
    )
    conn.commit()
    return new_count


def set_status(conn: sqlite3.Connection, learning_id: int, status: LearningStatus) -> None:
    """Set the status of a learning entry."""
    now = datetime.now(UTC).isoformat()
    row = conn.execute("SELECT id FROM learnings WHERE id = ?", (learning_id,)).fetchone()
    if row is None:
        raise ValueError(f"Learning not found: {learning_id}")
    conn.execute(
        "UPDATE learnings SET status = ?, updated_at = ? WHERE id = ?",
        (status.value, now, learning_id),
    )
    conn.commit()


def list_feature_requests(
    conn: sqlite3.Connection,
    status: LearningStatus | None = None,
) -> list[FeatureRequestRecord]:
    """Query feature requests with optional status filter."""
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE category = ? AND status = ? ORDER BY priority DESC, recurrence_count DESC",
            (LearningCategory.FEATURE_REQUEST.value, status.value),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE category = ? ORDER BY priority DESC, recurrence_count DESC",
            (LearningCategory.FEATURE_REQUEST.value,),
        ).fetchall()
    return [_row_to_feature_request(r) for r in rows]


def find_by_pattern_key(
    conn: sqlite3.Connection,
    pattern_key: str,
    category: LearningCategory | None = None,
) -> list[FeatureRequestRecord]:
    """Find entries by pattern_key, optionally filtered by category."""
    if category is not None:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE pattern_key = ? AND category = ?",
            (pattern_key, category.value),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM learnings WHERE pattern_key = ?",
            (pattern_key,),
        ).fetchall()
    return [_row_to_feature_request(r) for r in rows]


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
    for col in ("pattern_key", "recurrence_count", "justification", "impact", "priority"):
        data.pop(col, None)
    return LearningRecord.model_validate(data)


def _row_to_feature_request(row: sqlite3.Row) -> FeatureRequestRecord:
    """Convert a sqlite3.Row to a FeatureRequestRecord."""
    data = dict(row)
    data["category"] = LearningCategory(data["category"])
    data["status"] = LearningStatus(data["status"])
    if data.get("priority"):
        data["priority"] = Priority(data["priority"])
    else:
        data["priority"] = Priority.MEDIUM
    if data.get("recurrence_count") is None:
        data["recurrence_count"] = 1
    if isinstance(data.get("created_at"), str):
        data["created_at"] = datetime.fromisoformat(data["created_at"])
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    return FeatureRequestRecord.model_validate(data)
