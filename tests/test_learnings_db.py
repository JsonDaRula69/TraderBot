"""Tests for db/learnings.py — pattern tracking CRUD operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from traderbot.db import get_connection, init_schema
from traderbot.db.learnings import (
    LearningCategory,
    LearningRecord,
    LearningStatus,
    count,
    deprecate_pattern,
    get,
    get_patterns,
    get_top_patterns,
    init_table,
    promote_pattern,
    record_pattern,
)

if TYPE_CHECKING:
    from pathlib import Path


def _init_learnings(conn) -> None:
    """Initialize both base schema and learnings table."""
    init_schema(conn)
    init_table(conn)


class TestRecordPattern:
    def test_insert_returns_rowid(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(
                conn,
                category=LearningCategory.MARKET_BEHAVIOR,
                summary="Test pattern",
                evidence="observed X",
                confidence=0.5,
            )
        assert rowid == 1

    def test_insert_increments_ids(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            id1 = record_pattern(conn, LearningCategory.TIMING, "A", "e", 0.3)
            id2 = record_pattern(conn, LearningCategory.STRATEGY, "B", "e", 0.4)
        assert id1 == 1
        assert id2 == 2

    def test_rejects_confidence_below_zero(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            try:
                record_pattern(conn, LearningCategory.EXECUTION, "X", "e", -0.1)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")

    def test_rejects_confidence_above_one(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            try:
                record_pattern(conn, LearningCategory.EXECUTION, "X", "e", 1.1)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")


class TestGet:
    def test_returns_record(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.RISK_SIGNAL, "Y", "ev", 0.7)
            result = get(conn, rowid)
        assert result is not None
        assert result.summary == "Y"
        assert result.category == LearningCategory.RISK_SIGNAL
        assert result.confidence == 0.7
        assert result.status == LearningStatus.ACTIVE

    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            result = get(conn, 999)
        assert result is None

    def test_record_has_timestamps(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "Z", "ev", 0.6)
            result = get(conn, rowid)
        assert result is not None
        assert isinstance(result.created_at, datetime)
        assert isinstance(result.updated_at, datetime)


class TestGetPatterns:
    def test_no_filters_returns_all(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "A", "e", 0.3)
            record_pattern(conn, LearningCategory.TIMING, "B", "e", 0.8)
            result = get_patterns(conn)
        assert len(result) == 2

    def test_filters_by_category(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "A", "e", 0.5)
            record_pattern(conn, LearningCategory.TIMING, "B", "e", 0.5)
            result = get_patterns(conn, category=LearningCategory.TIMING)
        assert len(result) == 1
        assert all(r.category == LearningCategory.TIMING for r in result)

    def test_filters_by_min_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.STRATEGY, "low", "e", 0.2)
            record_pattern(conn, LearningCategory.STRATEGY, "high", "e", 0.8)
            result = get_patterns(conn, min_confidence=0.5)
        assert len(result) == 1
        assert result[0].summary == "high"

    def test_combined_category_and_confidence_filter(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.EXECUTION, "A", "e", 0.3)
            record_pattern(conn, LearningCategory.EXECUTION, "B", "e", 0.9)
            record_pattern(conn, LearningCategory.TIMING, "C", "e", 0.9)
            result = get_patterns(conn, category=LearningCategory.EXECUTION, min_confidence=0.5)
        assert len(result) == 1
        assert result[0].summary == "B"

    def test_ordered_by_confidence_desc(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.STRATEGY, "low", "e", 0.2)
            record_pattern(conn, LearningCategory.STRATEGY, "mid", "e", 0.5)
            record_pattern(conn, LearningCategory.STRATEGY, "high", "e", 0.8)
            result = get_patterns(conn)
        assert [r.confidence for r in result] == [0.8, 0.5, 0.2]


class TestPromotePattern:
    def test_increments_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "P", "e", 0.5)
            promote_pattern(conn, rowid, 0.3)
            result = get(conn, rowid)
        assert result is not None
        assert result.confidence == 0.8

    def test_caps_at_one(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "P", "e", 0.9)
            promote_pattern(conn, rowid, 0.5)
            result = get(conn, rowid)
        assert result is not None
        assert result.confidence == 1.0

    def test_updates_updated_at(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "P", "e", 0.5)
            before = get(conn, rowid)
            promote_pattern(conn, rowid, 0.1)
            after = get(conn, rowid)
        assert after is not None
        assert before is not None
        assert after.updated_at >= before.updated_at

    def test_raises_for_unknown_id(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            try:
                promote_pattern(conn, 999, 0.1)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")

    def test_rejects_invalid_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "P", "e", 0.5)
            try:
                promote_pattern(conn, rowid, -0.1)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")


class TestDeprecatePattern:
    def test_marks_deprecated(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "D", "e", 0.5)
            deprecate_pattern(conn, rowid)
            result = get(conn, rowid)
        assert result is not None
        assert result.status == LearningStatus.DEPRECATED

    def test_updates_updated_at(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "D", "e", 0.5)
            before = get(conn, rowid)
            deprecate_pattern(conn, rowid)
            after = get(conn, rowid)
        assert after is not None
        assert before is not None
        assert after.updated_at >= before.updated_at


class TestGetTopPatterns:
    def test_returns_highest_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            record_pattern(conn, LearningCategory.STRATEGY, "low", "e", 0.2)
            record_pattern(conn, LearningCategory.STRATEGY, "mid", "e", 0.5)
            record_pattern(conn, LearningCategory.STRATEGY, "high", "e", 0.9)
            result = get_top_patterns(conn, n=2)
        assert len(result) == 2
        assert result[0].confidence == 0.9
        assert result[1].confidence == 0.5

    def test_excludes_deprecated(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            rowid = record_pattern(conn, LearningCategory.STRATEGY, "top", "e", 0.99)
            record_pattern(conn, LearningCategory.STRATEGY, "active", "e", 0.7)
            deprecate_pattern(conn, rowid)
            result = get_top_patterns(conn, n=10)
        assert len(result) == 1
        assert result[0].summary == "active"

    def test_respects_n_limit(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            for i in range(5):
                record_pattern(conn, LearningCategory.STRATEGY, f"P{i}", "e", float(i) / 10)
            result = get_top_patterns(conn, n=2)
        assert len(result) == 2


class TestCount:
    def test_returns_total(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_learnings(conn)
            assert count(conn) == 0
            record_pattern(conn, LearningCategory.STRATEGY, "A", "e", 0.5)
            record_pattern(conn, LearningCategory.STRATEGY, "B", "e", 0.5)
            assert count(conn) == 2


class TestCategoryEnum:
    def test_all_categories_valid(self) -> None:
        expected = {"MarketBehavior", "RiskSignal", "Timing", "Strategy", "Execution", "FeatureRequest"}
        assert {c.value for c in LearningCategory} == expected

    def test_str_enum_behavior(self) -> None:
        assert LearningCategory.MARKET_BEHAVIOR == "MarketBehavior"
        assert isinstance(LearningCategory.STRATEGY, str)


class TestStatusEnum:
    def test_all_statuses_valid(self) -> None:
        expected = {"active", "deprecated", "pending_review"}
        assert {s.value for s in LearningStatus} == expected

    def test_str_enum_behavior(self) -> None:
        assert LearningStatus.ACTIVE == "active"
        assert isinstance(LearningStatus.DEPRECATED, str)


class TestLearningRecord:
    def test_rejects_extra_fields(self) -> None:
        try:
            LearningRecord(
                id=1,
                category=LearningCategory.STRATEGY,
                summary="test",
                evidence="e",
                confidence=0.5,
                status=LearningStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                extra_field="bad",
            )
        except Exception:
            pass
        else:
            raise AssertionError("Expected validation error for extra field")

    def test_rejects_confidence_out_of_range(self) -> None:
        try:
            LearningRecord(
                id=1,
                category=LearningCategory.STRATEGY,
                summary="test",
                evidence="e",
                confidence=1.5,
                status=LearningStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        except Exception:
            pass
        else:
            raise AssertionError("Expected validation error for confidence >1.0")

    def test_strict_mode_rejects_wrong_types(self) -> None:
        try:
            LearningRecord(
                id="not_an_int",
                category=LearningCategory.STRATEGY,
                summary="test",
                evidence="e",
                confidence=0.5,
                status=LearningStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        except Exception:
            pass
        else:
            raise AssertionError("Expected validation error for wrong type")
