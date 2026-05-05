"""Learning system orchestration — promotion, feature requests, and feedback loops."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from traderbot.db.learnings import (
    FeatureRequestRecord,
    LearningCategory,
    LearningRecord,
    LearningStatus,
    Priority,
    find_by_pattern_key,
    get,
    get_patterns,
    increment_recurrence,
    list_feature_requests,
    promote_pattern,
    record_feature_request,
    set_status,
)

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)

PROMOTION_THRESHOLD = 3
MAX_AGE_DAYS = 30
HEARTBEAT_INTERVAL_HOURS = 6

DEFAULT_LEARNINGS_DIR = Path(".openclaw/workspace/.learnings")
FEATURE_REQUESTS_FILE = DEFAULT_LEARNINGS_DIR / "FEATURE_REQUESTS.md"


def log_or_increment_feature_request(
    conn: sqlite3.Connection,
    pattern_key: str,
    summary: str,
    evidence: str,
    justification: str,
    impact: str,
    priority: Priority,
) -> int:
    """Log a feature request or increment recurrence if pattern_key exists."""
    existing = find_by_pattern_key(conn, pattern_key, LearningCategory.FEATURE_REQUEST)
    active_entries = [e for e in existing if e.status != LearningStatus.DEPRECATED]
    if active_entries:
        entry = active_entries[0]
        new_count = increment_recurrence(conn, entry.id)
        if new_count >= PROMOTION_THRESHOLD and entry.status == LearningStatus.ACTIVE:
            promote_feature_request(conn, entry.id)
        return entry.id
    return record_feature_request(
        conn,
        pattern_key=pattern_key,
        summary=summary,
        evidence=evidence,
        justification=justification,
        impact=impact,
        priority=priority,
    )


def promote_feature_request(conn: sqlite3.Connection, learning_id: int) -> None:
    """Promote a feature request to PENDING_REVIEW and write to FEATURE_REQUESTS.md."""
    set_status(conn, learning_id, LearningStatus.PENDING_REVIEW)
    requests = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)
    write_feature_requests_md(requests)


def write_feature_requests_md(requests: list[FeatureRequestRecord]) -> None:
    """Write pending-review feature requests to FEATURE_REQUESTS.md."""
    DEFAULT_LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Feature Requests\n"]
    if not requests:
        lines.append("_No pending feature requests._\n")
    for idx, req in enumerate(requests, start=1):
        lines.append(f"## Entry: FEAT-{idx:03d}\n")
        lines.append(f"**Logged**: {req.created_at.isoformat()}\n")
        lines.append(f"**Category**: {req.category.value.lower()}\n")
        lines.append(f"**Pattern-Key**: {req.pattern_key}\n")
        lines.append(f"**Recurrence-Count**: {req.recurrence_count}\n")
        lines.append(f"**Priority**: {req.priority.value}\n")
        lines.append(f"**Status**: {req.status.value}\n")
        lines.append(f"### Request\n{req.summary}\n")
        lines.append(f"### Justification\n{req.justification}\n")
        lines.append(f"### Impact\n{req.impact}\n")
        lines.append("\n")
    FEATURE_REQUESTS_FILE.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Pattern promotion engine
# ---------------------------------------------------------------------------


class PromotionCandidate(BaseModel):
    """A learning eligible for promotion with its recurrence stats."""

    model_config = ConfigDict(strict=True, extra="forbid")

    learning: LearningRecord
    recurrence_count: int = Field(ge=0)
    distinct_tasks: int = Field(ge=0)
    first_observed: datetime | None = None
    last_observed: datetime | None = None


def init_task_observations_table(conn: sqlite3.Connection) -> None:
    """Create the pattern_task_observations table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pattern_task_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            learning_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            FOREIGN KEY (learning_id) REFERENCES learnings(id)
        )"""
    )
    conn.commit()


def record_task_observation(
    conn: sqlite3.Connection,
    learning_id: int,
    task_id: str,
) -> int:
    """Record that a learning was observed in a specific task."""
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        """INSERT INTO pattern_task_observations (learning_id, task_id, observed_at)
           VALUES (?, ?, ?)""",
        (learning_id, task_id, now),
    )
    conn.commit()
    return cursor.lastrowid


def _get_task_observation_stats(
    conn: sqlite3.Connection,
    learning_id: int,
) -> tuple[int, int, datetime | None, datetime | None]:
    """Return (count, distinct_tasks, first_observed, last_observed) for a learning."""
    row = conn.execute(
        """SELECT COUNT(*) as cnt,
                  COUNT(DISTINCT task_id) as task_cnt,
                  MIN(observed_at) as first_obs,
                  MAX(observed_at) as last_obs
           FROM pattern_task_observations
           WHERE learning_id = ?""",
        (learning_id,),
    ).fetchone()
    first_obs = datetime.fromisoformat(row["first_obs"]) if row["first_obs"] else None
    last_obs = datetime.fromisoformat(row["last_obs"]) if row["last_obs"] else None
    return (row["cnt"], row["task_cnt"], first_obs, last_obs)


def _get_db_recurrence_count(conn: sqlite3.Connection, learning_id: int) -> int:
    """Read recurrence_count directly from the DB row."""
    row = conn.execute(
        "SELECT recurrence_count FROM learnings WHERE id = ?", (learning_id,)
    ).fetchone()
    if row is None or row["recurrence_count"] is None:
        return 1
    return row["recurrence_count"]


def get_db_pattern_key(conn: sqlite3.Connection, learning_id: int) -> str | None:
    """Read pattern_key directly from the DB row."""
    row = conn.execute(
        "SELECT pattern_key FROM learnings WHERE id = ?", (learning_id,)
    ).fetchone()
    if row is None or row["pattern_key"] is None:
        return None
    return row["pattern_key"]


def scan_for_promotions(
    conn: sqlite3.Connection,
    min_recurrence: int = PROMOTION_THRESHOLD,
    min_tasks: int = 2,
    max_age_days: int = MAX_AGE_DAYS,
) -> list[PromotionCandidate]:
    """Query learnings eligible for promotion by recurrence criteria."""
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    candidates: list[PromotionCandidate] = []

    active_patterns = get_patterns(conn)
    for learning in active_patterns:
        if learning.category == LearningCategory.FEATURE_REQUEST:
            continue

        recurrence = _get_db_recurrence_count(conn, learning.id)
        _, task_cnt, first_obs, last_obs = _get_task_observation_stats(conn, learning.id)

        if recurrence < min_recurrence:
            continue
        if task_cnt < min_tasks:
            continue
        if first_obs is not None and first_obs < cutoff:
            continue

        candidates.append(
            PromotionCandidate(
                learning=learning,
                recurrence_count=recurrence,
                distinct_tasks=task_cnt,
                first_observed=first_obs,
                last_observed=last_obs,
            )
        )

    candidates.sort(key=lambda c: c.recurrence_count, reverse=True)
    return candidates


def _format_promoted_entry(
    candidate: PromotionCandidate,
    pattern_key: str | None = None,
) -> str:
    """Format a promoted entry as markdown per the learning entry format spec."""
    learning = candidate.learning
    now = datetime.now(UTC)
    entry_id = f"PROMO-{learning.id:03d}"
    display_key = pattern_key or learning.summary.lower().replace(" ", "-")[:40]
    priority = "high" if learning.confidence >= 0.8 else "medium"

    lines = [
        f"## Entry: {entry_id}",
        f"**Logged**: {now.isoformat()}",
        f"**Pattern-Key**: {display_key}",
        f"**Recurrence-Count**: {candidate.recurrence_count}",
        f"**Priority**: {priority}",
        "**Status**: promoted",
        f"**Category**: {learning.category.value}",
        "### Learning",
        learning.evidence,
        "### Action",
        f"Promoted from learning #{learning.id}. Pending verification in next heartbeat.",
    ]
    return "\n".join(lines)


def write_promoted_entry(
    candidate: PromotionCandidate,
    learnings_dir: Path | str | None = None,
    pattern_key: str | None = None,
) -> Path:
    """Format and write a promoted entry to LEARNINGS.md."""
    directory = Path(learnings_dir) if learnings_dir is not None else DEFAULT_LEARNINGS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    learnings_path = directory / "LEARNINGS.md"

    entry_text = _format_promoted_entry(candidate, pattern_key=pattern_key)
    entry_id = f"PROMO-{candidate.learning.id:03d}"

    if learnings_path.exists():
        existing = learnings_path.read_text()
        if f"## Entry: {entry_id}" in existing:
            logger.info("Entry %s already exists in LEARNINGS.md, skipping duplicate", entry_id)
            return learnings_path
        if existing.rstrip().endswith("(none yet)"):
            content = existing.replace("(none yet)", "").rstrip() + "\n\n" + entry_text + "\n"
        else:
            content = existing.rstrip() + "\n\n" + entry_text + "\n"
    else:
        header = (
            "# Learnings Log\n\n"
            "> Insights, corrections, and better approaches discovered during operation.\n"
            "> When Recurrence-Count >= 3 across 2+ sessions within 30 days, promote to AGENTS.md.\n\n"
            "## Entries\n\n"
        )
        content = header + entry_text + "\n"

    learnings_path.write_text(content)
    logger.info("Wrote promoted entry for learning #%d to %s", candidate.learning.id, learnings_path)
    return learnings_path


def promote_learning(
    conn: sqlite3.Connection,
    learning_id: int,
    learnings_dir: Path | str | None = None,
) -> Path | None:
    """Mark a learning as promoted in the DB and write to LEARNINGS.md."""
    learning = get(conn, learning_id)
    if learning is None:
        logger.warning("Learning #%d not found, skipping promotion", learning_id)
        return None
    if learning.status != LearningStatus.ACTIVE:
        logger.warning("Learning #%d is not active (status=%s), skipping promotion", learning_id, learning.status)
        return None

    _, task_cnt, first_obs, _ = _get_task_observation_stats(conn, learning_id)
    recurrence = _get_db_recurrence_count(conn, learning_id)

    if recurrence < PROMOTION_THRESHOLD:
        logger.warning("Learning #%d has insufficient recurrences (%d < %d), skipping promotion", learning_id, recurrence, PROMOTION_THRESHOLD)
        return None
    if task_cnt < 2:
        logger.warning("Learning #%d seen in only %d task(s) (need 2+), skipping promotion", learning_id, task_cnt)
        return None

    cutoff = datetime.now(UTC) - timedelta(days=MAX_AGE_DAYS)
    if first_obs is not None and first_obs < cutoff:
        logger.warning("Learning #%d first observation too old, skipping promotion", learning_id)
        return None

    promote_pattern(conn, learning_id, 0.1)
    set_status(conn, learning_id, LearningStatus.PENDING_REVIEW)

    updated_learning = get(conn, learning_id)
    if updated_learning is None:
        return None

    candidate = PromotionCandidate(
        learning=updated_learning,
        recurrence_count=recurrence,
        distinct_tasks=task_cnt,
        first_observed=first_obs,
        last_observed=first_obs,
    )

    return write_promoted_entry(candidate, learnings_dir, pattern_key=get_db_pattern_key(conn, learning_id))


def run_promotion_cycle(
    conn: sqlite3.Connection,
    learnings_dir: Path | str | None = None,
    min_recurrence: int = PROMOTION_THRESHOLD,
) -> list[Path]:
    """Full cycle: scan for eligible patterns and promote all that qualify."""
    candidates = scan_for_promotions(conn, min_recurrence=min_recurrence)
    promoted_paths: list[Path] = []
    for candidate in candidates:
        result = promote_learning(conn, candidate.learning.id, learnings_dir)
        if result is not None:
            promoted_paths.append(result)
    logger.info("Promotion cycle complete: %d of %d candidates promoted", len(promoted_paths), len(candidates))
    return promoted_paths
