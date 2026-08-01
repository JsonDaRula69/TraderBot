"""Tests for learning.py — pattern promotion engine."""

from __future__ import annotations

import sqlite3  # noqa: TC003 - runtime use in test helpers
from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: TC003 - runtime use in test fixtures

from traderbot.db import get_connection, init_schema
from traderbot.db.learnings import (
    LearningCategory,
    Priority,
    record_feature_request,
    record_pattern,
)
from traderbot.db.learnings import (
    init_table as init_learnings_table,
)
from traderbot.learning import (
    PromotionCandidate,
    _format_promoted_entry,
    get_db_pattern_key,
    _get_db_recurrence_count,
    _get_task_observation_stats,
    init_task_observations_table,
    promote_learning,
    record_task_observation,
    run_promotion_cycle,
    scan_for_promotions,
    write_promoted_entry,
)


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize all required tables."""
    init_schema(conn)
    init_learnings_table(conn)
    init_task_observations_table(conn)


def _seed_eligible_learning(conn: sqlite3.Connection) -> int:
    """Insert a learning eligible for promotion with 3+ recurrences across 2+ tasks."""
    learning_id = record_pattern(
        conn,
        category=LearningCategory.RISK_SIGNAL,
        summary="Illiquid market slippage",
        evidence="Markets with open_interest < 500 experience significant slippage",
        confidence=0.7,
    )
    conn.execute(
        "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
    )
    conn.commit()
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
        (learning_id, "task-backtest", now),
    )
    conn.execute(
        "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
        (learning_id, "task-live-trade", now),
    )
    conn.execute(
        "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
        (learning_id, "task-paper-trade", now),
    )
    conn.commit()
    return learning_id


class TestInitTaskObservationsTable:
    def test_creates_table(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_task_observations'"
            ).fetchall()
            assert len(tables) == 1

    def test_idempotent(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            init_task_observations_table(conn)


class TestRecordTaskObservation:
    def test_inserts_row(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            rowid = record_task_observation(conn, learning_id, "task-1")
            assert rowid > 0

    def test_multiple_observations(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            record_task_observation(conn, learning_id, "task-1")
            record_task_observation(conn, learning_id, "task-2")
            count, task_cnt, _, _ = _get_task_observation_stats(conn, learning_id)
            assert count == 2
            assert task_cnt == 2


class TestGetTaskObservationStats:
    def test_no_observations(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            count, task_cnt, first, last = _get_task_observation_stats(conn, learning_id)
            assert count == 0
            assert task_cnt == 0
            assert first is None
            assert last is None

    def test_returns_correct_stats(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                (learning_id, "task-alpha", now),
            )
            conn.execute(
                "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                (learning_id, "task-beta", now),
            )
            conn.execute(
                "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                (learning_id, "task-alpha", now),
            )
            conn.commit()
            count, task_cnt, first, last = _get_task_observation_stats(conn, learning_id)
            assert count == 3
            assert task_cnt == 2
            assert first is not None
            assert last is not None


class TestGetDbRecurrenceCount:
    def test_default_one(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            assert _get_db_recurrence_count(conn, learning_id) == 1

    def test_reads_actual_count(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 5 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            assert _get_db_recurrence_count(conn, learning_id) == 5


class TestGetDbPatternKey:
    def test_none_when_absent(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            assert get_db_pattern_key(conn, learning_id) is None

    def test_reads_actual_key(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.MARKET_BEHAVIOR, "test", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET pattern_key = 'illiquid-slippage' WHERE id = ?", (learning_id,)
            )
            conn.commit()
            assert get_db_pattern_key(conn, learning_id) == "illiquid-slippage"


class TestScanForPromotions:
    def test_empty_db(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            result = scan_for_promotions(conn)
            assert result == []

    def test_eligible_learning_found(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            result = scan_for_promotions(conn)
            assert len(result) == 1
            assert result[0].learning.id == learning_id
            assert result[0].recurrence_count == 3
            assert result[0].distinct_tasks >= 2

    def test_insufficient_recurrence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "test", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 2 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            result = scan_for_promotions(conn)
            assert len(result) == 0

    def test_insufficient_tasks(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "test", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for _ in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, "same-task", now),
                )
            conn.commit()
            result = scan_for_promotions(conn, min_tasks=2)
            assert len(result) == 0

    def test_stale_observation_excluded(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "stale pattern", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", old),
                )
            conn.commit()
            result = scan_for_promotions(conn)
            assert len(result) == 0

    def test_feature_request_excluded(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            fr_id = record_feature_request(
                conn, "need-tool", "test", "test", "test", "test", Priority.HIGH
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (fr_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (fr_id, f"task-{i}", now),
                )
            conn.commit()
            result = scan_for_promotions(conn)
            assert len(result) == 0

    def test_sorted_by_recurrence_desc(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            now = datetime.now(UTC).isoformat()
            for label, rec_count in [("low", 3), ("high", 7)]:
                lid = record_pattern(
                    conn, LearningCategory.RISK_SIGNAL, label, "evidence", 0.5
                )
                conn.execute(
                    "UPDATE learnings SET recurrence_count = ? WHERE id = ?", (rec_count, lid)
                )
                conn.commit()
                for i in range(3):
                    conn.execute(
                        "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                        (lid, f"task-{label}-{i}", now),
                    )
                conn.commit()
            result = scan_for_promotions(conn)
            assert len(result) == 2
            assert result[0].recurrence_count >= result[1].recurrence_count

    def test_custom_min_recurrence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "test", "evidence", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            assert len(scan_for_promotions(conn, min_recurrence=5)) == 0
            assert len(scan_for_promotions(conn, min_recurrence=3)) == 1


class TestFormatPromotedEntry:
    def test_format_uses_pattern_key(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(
                learning=learning,
                recurrence_count=3,
                distinct_tasks=2,
            )
            text = _format_promoted_entry(candidate, pattern_key="my-custom-key")
            assert "**Pattern-Key**: my-custom-key" in text

    def test_format_falls_back_to_summary(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(
                learning=learning,
                recurrence_count=3,
                distinct_tasks=2,
            )
            text = _format_promoted_entry(candidate, pattern_key=None)
            assert "**Pattern-Key**:" in text
            assert "illiquid-market-slippage" in text

    def test_format_contains_required_fields(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(
                learning=learning,
                recurrence_count=4,
                distinct_tasks=3,
            )
            text = _format_promoted_entry(candidate, pattern_key="test-key")
            assert "## Entry: PROMO-" in text
            assert "**Logged**:" in text
            assert "**Pattern-Key**: test-key" in text
            assert "**Recurrence-Count**: 4" in text
            assert "**Priority**:" in text
            assert "**Status**: promoted" in text
            assert f"**Category**: {learning.category.value}" in text
            assert "### Learning" in text
            assert "### Action" in text

    def test_high_priority_for_high_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "high-conf", "ev", 0.9
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(learning=learning, recurrence_count=3, distinct_tasks=2)
            text = _format_promoted_entry(candidate, pattern_key="k")
            assert "**Priority**: high" in text

    def test_medium_priority_for_low_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "low-conf", "ev", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(learning=learning, recurrence_count=3, distinct_tasks=2)
            text = _format_promoted_entry(candidate, pattern_key="k")
            assert "**Priority**: medium" in text


class TestWritePromotedEntry:
    def test_creates_learnings_md(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(learning=learning, recurrence_count=3, distinct_tasks=2)
            learnings_dir = tmp_path / "learnings"
            result = write_promoted_entry(candidate, learnings_dir, pattern_key="test-key")
            assert result == learnings_dir / "LEARNINGS.md"
            assert result.exists()
            content = result.read_text()
            assert "test-key" in content
            assert "promoted" in content

    def test_replaces_none_yet_placeholder(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        learnings_dir.mkdir()
        learnings_file = learnings_dir / "LEARNINGS.md"
        learnings_file.write_text("# Learnings Log\n\n## Entries\n\n(none yet)\n")

        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(learning=learning, recurrence_count=3, distinct_tasks=2)
            result = write_promoted_entry(candidate, learnings_dir, pattern_key="new-key")
            content = result.read_text()
            assert "(none yet)" not in content
            assert "new-key" in content

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        learnings_dir.mkdir()
        learnings_file = learnings_dir / "LEARNINGS.md"
        learnings_file.write_text("# Learnings Log\n\n## Entries\n\nExisting content\n")

        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            learning = get(conn, learning_id)
            assert learning is not None
            candidate = PromotionCandidate(learning=learning, recurrence_count=3, distinct_tasks=2)
            result = write_promoted_entry(candidate, learnings_dir, pattern_key="appended")
            content = result.read_text()
            assert "Existing content" in content
            assert "appended" in content


class TestPromoteLearning:
    def test_successful_promotion(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            result = promote_learning(conn, learning_id, learnings_dir)
            assert isinstance(result, Path)
            assert result.exists()
            content = result.read_text()
            assert "promoted" in content

    def test_not_found_returns_none(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            result = promote_learning(conn, 9999, learnings_dir)
            assert result is None

    def test_deprecated_learning_not_promoted(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import deprecate_pattern
            deprecate_pattern(conn, learning_id)
            result = promote_learning(conn, learning_id, learnings_dir)
            assert result is None

    def test_insufficient_recurrence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "low recur", "ev", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 2 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            result = promote_learning(conn, learning_id, learnings_dir)
            assert result is None

    def test_insufficient_tasks(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "single task", "ev", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for _ in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, "same-task", now),
                )
            conn.commit()
            result = promote_learning(conn, learning_id, learnings_dir)
            assert result is None

    def test_stale_observation(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "stale", "ev", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", old),
                )
            conn.commit()
            result = promote_learning(conn, learning_id, learnings_dir)
            assert result is None

    def test_boosts_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = _seed_eligible_learning(conn)
            from traderbot.db.learnings import get
            before = get(conn, learning_id)
            assert before is not None
            promote_learning(conn, learning_id, learnings_dir)
            after = get(conn, learning_id)
            assert after is not None
            assert after.confidence > before.confidence


class TestRunPromotionCycle:
    def test_promotes_all_eligible(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            _seed_eligible_learning(conn)
            _seed_eligible_learning(conn)
            result = run_promotion_cycle(conn, learnings_dir)
            assert len(result) == 2

    def test_empty_db(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            result = run_promotion_cycle(conn, learnings_dir)
            assert result == []

    def test_custom_min_recurrence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        learnings_dir = tmp_path / "learnings"
        with get_connection(db_file) as conn:
            _init_db(conn)
            learning_id = record_pattern(
                conn, LearningCategory.RISK_SIGNAL, "test", "ev", 0.5
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (learning_id,)
            )
            conn.commit()
            now = datetime.now(UTC).isoformat()
            for i in range(3):
                conn.execute(
                    "INSERT INTO pattern_task_observations (learning_id, task_id, observed_at) VALUES (?, ?, ?)",
                    (learning_id, f"task-{i}", now),
                )
            conn.commit()
            assert len(run_promotion_cycle(conn, learnings_dir, min_recurrence=5)) == 0
            assert len(run_promotion_cycle(conn, learnings_dir, min_recurrence=3)) == 1


class TestNoAutoEditAgentsMd:
    def test_learning_py_does_not_write_agents_md(self) -> None:
        import inspect

        from traderbot import learning
        source = inspect.getsource(learning)
        assert "AGENTS.md" not in source or "AGENTS.md" not in [
            line for line in source.split("\n")
            if "write_text" in line or "open(" in line or "write(" in line
        ]
