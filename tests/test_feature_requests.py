"""Tests for feature request flow — db operations, promotion, FEATURE_REQUESTS.md output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.db import get_connection, init_schema
from traderbot.db.learnings import (
    FeatureRequestRecord,
    LearningCategory,
    LearningStatus,
    Priority,
    find_by_pattern_key,
    increment_recurrence,
    init_table,
    list_feature_requests,
    record_feature_request,
    set_status,
)
from traderbot.learning import (
    log_or_increment_feature_request,
    promote_feature_request,
    write_feature_requests_md,
)

if TYPE_CHECKING:
    from pathlib import Path

    import sqlite3


def _init_db(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    init_table(conn)


class TestFeatureRequestEnums:
    def test_feature_request_category_value(self) -> None:
        assert LearningCategory.FEATURE_REQUEST == "FeatureRequest"

    def test_pending_review_status_value(self) -> None:
        assert LearningStatus.PENDING_REVIEW == "pending_review"

    def test_all_categories_include_feature_request(self) -> None:
        values = {c.value for c in LearningCategory}
        assert "FeatureRequest" in values

    def test_all_statuses_include_pending_review(self) -> None:
        values = {s.value for s in LearningStatus}
        assert "pending_review" in values


class TestPriorityEnum:
    def test_priority_values(self) -> None:
        assert Priority.LOW == "low"
        assert Priority.MEDIUM == "medium"
        assert Priority.HIGH == "high"
        assert Priority.CRITICAL == "critical"

    def test_str_enum(self) -> None:
        assert isinstance(Priority.HIGH, str)


class TestRecordFeatureRequest:
    def test_insert_returns_rowid(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="missing-sports-data",
                summary="Need sports data feed",
                evidence="Encountered 3 sports markets",
                justification="Sports markets are 15% of tracked markets",
                impact="Improved classification for ~15% of markets",
                priority=Priority.HIGH,
            )
        assert rowid >= 1

    def test_insert_sets_category(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            _ = record_feature_request(
                conn,
                pattern_key="test-key",
                summary="Test",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.MEDIUM,
            )
            results = list_feature_requests(conn)
        assert len(results) == 1
        assert results[0].category == LearningCategory.FEATURE_REQUEST

    def test_insert_sets_active_status(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            record_feature_request(
                conn,
                pattern_key="test-key",
                summary="Test",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            results = list_feature_requests(conn)
        assert results[0].status == LearningStatus.ACTIVE

    def test_insert_sets_recurrence_count_1(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            record_feature_request(
                conn,
                pattern_key="test-key",
                summary="Test",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            results = list_feature_requests(conn)
        assert results[0].recurrence_count == 1

    def test_rejects_invalid_confidence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            try:
                record_feature_request(
                    conn,
                    pattern_key="test",
                    summary="T",
                    evidence="e",
                    justification="j",
                    impact="i",
                    priority=Priority.LOW,
                    confidence=1.5,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError for confidence > 1.0")


class TestListFeatureRequests:
    def test_returns_feature_requests_only(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            from traderbot.db.learnings import record_pattern

            record_pattern(conn, LearningCategory.STRATEGY, "Normal pattern", "e", 0.5)
            record_feature_request(
                conn,
                pattern_key="feat-1",
                summary="Feature 1",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            results = list_feature_requests(conn)
        assert len(results) == 1
        assert results[0].category == LearningCategory.FEATURE_REQUEST

    def test_filters_by_status(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            _ = record_feature_request(
                conn,
                pattern_key="feat-1",
                summary="Active request",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            id2 = record_feature_request(
                conn,
                pattern_key="feat-2",
                summary="Another request",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.MEDIUM,
            )
            set_status(conn, id2, LearningStatus.PENDING_REVIEW)
            active = list_feature_requests(conn, status=LearningStatus.ACTIVE)
            pending = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)
        assert len(active) == 1
        assert active[0].pattern_key == "feat-1"
        assert len(pending) == 1
        assert pending[0].pattern_key == "feat-2"

    def test_no_status_filter_returns_all(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            id1 = record_feature_request(
                conn,
                pattern_key="feat-1",
                summary="A",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            record_feature_request(
                conn,
                pattern_key="feat-2",
                summary="B",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            set_status(conn, id1, LearningStatus.PENDING_REVIEW)
            results = list_feature_requests(conn)
        assert len(results) == 2

    def test_returns_feature_request_records(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            record_feature_request(
                conn,
                pattern_key="my-key",
                summary="Need API",
                evidence="3 calls failed",
                justification="Users need this",
                impact="100% improvement",
                priority=Priority.CRITICAL,
            )
            results = list_feature_requests(conn)
        assert isinstance(results[0], FeatureRequestRecord)
        assert results[0].pattern_key == "my-key"
        assert results[0].justification == "Users need this"
        assert results[0].impact == "100% improvement"
        assert results[0].priority == Priority.CRITICAL


class TestIncrementRecurrence:
    def test_increments_from_1(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="test",
                summary="T",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            new_count = increment_recurrence(conn, rowid)
            results = list_feature_requests(conn)
        assert new_count == 2
        assert results[0].recurrence_count == 2

    def test_raises_for_unknown_id(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            try:
                increment_recurrence(conn, 999)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")


class TestSetStatus:
    def test_sets_pending_review(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="test",
                summary="T",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            set_status(conn, rowid, LearningStatus.PENDING_REVIEW)
            results = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)
        assert len(results) == 1
        assert results[0].status == LearningStatus.PENDING_REVIEW

    def test_raises_for_unknown_id(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            try:
                set_status(conn, 999, LearningStatus.PENDING_REVIEW)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected ValueError")


class TestFindByPatternKey:
    def test_finds_matching_pattern_key(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            record_feature_request(
                conn,
                pattern_key="missing-sports-data",
                summary="Need sports data",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            record_feature_request(
                conn,
                pattern_key="missing-crypto-data",
                summary="Need crypto data",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.MEDIUM,
            )
            results = find_by_pattern_key(conn, "missing-sports-data")
        assert len(results) == 1
        assert results[0].pattern_key == "missing-sports-data"

    def test_filters_by_category(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            record_feature_request(
                conn,
                pattern_key="shared-key",
                summary="Feature request",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            results = find_by_pattern_key(conn, "shared-key", LearningCategory.FEATURE_REQUEST)
        assert len(results) == 1

    def test_returns_empty_for_no_match(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            results = find_by_pattern_key(conn, "nonexistent")
        assert results == []


class TestLogOrIncrementFeatureRequest:
    def test_creates_new_on_first_occurrence(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = log_or_increment_feature_request(
                conn,
                pattern_key="new-feature",
                summary="New feature needed",
                evidence="Encountered gap",
                justification="Implements capability X",
                impact="Saves 30 min per session",
                priority=Priority.MEDIUM,
            )
            results = list_feature_requests(conn)
        assert rowid >= 1
        assert len(results) == 1
        assert results[0].recurrence_count == 1
        assert results[0].status == LearningStatus.ACTIVE

    def test_increments_existing_pattern(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            log_or_increment_feature_request(
                conn,
                pattern_key="recurring-feature",
                summary="Recurring feature",
                evidence="e1",
                justification="j1",
                impact="i1",
                priority=Priority.HIGH,
            )
            log_or_increment_feature_request(
                conn,
                pattern_key="recurring-feature",
                summary="Recurring feature again",
                evidence="e2",
                justification="j2",
                impact="i2",
                priority=Priority.HIGH,
            )
            results = list_feature_requests(conn)
        assert len(results) == 1
        assert results[0].recurrence_count == 2
        assert results[0].status == LearningStatus.ACTIVE

    def test_promotes_at_threshold(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            for _ in range(3):
                log_or_increment_feature_request(
                    conn,
                    pattern_key="promo-feature",
                    summary="Promotion candidate",
                    evidence="e",
                    justification="j",
                    impact="i",
                    priority=Priority.HIGH,
                )
            active = list_feature_requests(conn, status=LearningStatus.ACTIVE)
            pending = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)
        assert len(active) == 0
        assert len(pending) == 1
        assert pending[0].recurrence_count >= 3

    def test_does_not_reativate_deprecated(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="deprecated-feature",
                summary="Deprecated",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            set_status(conn, rowid, LearningStatus.DEPRECATED)
            log_or_increment_feature_request(
                conn,
                pattern_key="deprecated-feature",
                summary="New occurrence",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.LOW,
            )
            all_requests = list_feature_requests(conn)
        new_entry = [r for r in all_requests if r.status != LearningStatus.DEPRECATED]
        assert len(new_entry) == 1
        assert new_entry[0].pattern_key == "deprecated-feature"
        assert new_entry[0].recurrence_count == 1


class TestPromoteFeatureRequest:
    def test_sets_pending_review(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="promo-test",
                summary="Test promotion",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            promote_feature_request(conn, rowid)
            pending = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)
        assert len(pending) == 1
        assert pending[0].pattern_key == "promo-test"


class TestWriteFeatureRequestsMd:
    def test_creates_file(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="md-test",
                summary="Need markdown output",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
            )
            set_status(conn, rowid, LearningStatus.PENDING_REVIEW)
            requests = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)

        import traderbot.learning as learning_mod

        original_dir = learning_mod.DEFAULT_LEARNINGS_DIR
        original_file = learning_mod.FEATURE_REQUESTS_FILE
        try:
            out_dir = tmp_path / ".openclaw" / "workspace" / ".learnings"
            learning_mod.DEFAULT_LEARNINGS_DIR = out_dir
            learning_mod.FEATURE_REQUESTS_FILE = out_dir / "FEATURE_REQUESTS.md"
            write_feature_requests_md(requests)

            content = learning_mod.FEATURE_REQUESTS_FILE.read_text()
        finally:
            learning_mod.DEFAULT_LEARNINGS_DIR = original_dir
            learning_mod.FEATURE_REQUESTS_FILE = original_file

        assert "FEAT-001" in content
        assert "md-test" in content
        assert "pending_review" in content
        assert "Need markdown output" in content

    def test_empty_requests(self, tmp_path: Path) -> None:
        import traderbot.learning as learning_mod

        original_dir = learning_mod.DEFAULT_LEARNINGS_DIR
        original_file = learning_mod.FEATURE_REQUESTS_FILE
        try:
            out_dir = tmp_path / ".openclaw" / "workspace" / ".learnings"
            learning_mod.DEFAULT_LEARNINGS_DIR = out_dir
            learning_mod.FEATURE_REQUESTS_FILE = out_dir / "FEATURE_REQUESTS.md"
            write_feature_requests_md([])

            content = learning_mod.FEATURE_REQUESTS_FILE.read_text()
        finally:
            learning_mod.DEFAULT_LEARNINGS_DIR = original_dir
            learning_mod.FEATURE_REQUESTS_FILE = original_file

        assert "No pending feature requests" in content

    def test_md_format_matches_spec(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            _init_db(conn)
            rowid = record_feature_request(
                conn,
                pattern_key="format-test",
                summary="Sports data feed missing",
                evidence="3 sports markets unclassified",
                justification="15% of markets need sports data",
                impact="Improved classification accuracy",
                priority=Priority.HIGH,
            )
            set_status(conn, rowid, LearningStatus.PENDING_REVIEW)
            requests = list_feature_requests(conn, status=LearningStatus.PENDING_REVIEW)

        import traderbot.learning as learning_mod

        original_dir = learning_mod.DEFAULT_LEARNINGS_DIR
        original_file = learning_mod.FEATURE_REQUESTS_FILE
        try:
            out_dir = tmp_path / ".openclaw" / "workspace" / ".learnings"
            learning_mod.DEFAULT_LEARNINGS_DIR = out_dir
            learning_mod.FEATURE_REQUESTS_FILE = out_dir / "FEATURE_REQUESTS.md"
            write_feature_requests_md(requests)

            content = learning_mod.FEATURE_REQUESTS_FILE.read_text()
        finally:
            learning_mod.DEFAULT_LEARNINGS_DIR = original_dir
            learning_mod.FEATURE_REQUESTS_FILE = original_file

        assert "**Pattern-Key**:" in content
        assert "**Recurrence-Count**:" in content
        assert "**Priority**:" in content
        assert "**Status**:" in content
        assert "### Request" in content
        assert "### Justification" in content
        assert "### Impact" in content


class TestFeatureRequestRecordModel:
    def test_rejects_extra_fields(self) -> None:
        from datetime import UTC, datetime

        try:
            FeatureRequestRecord(
                id=1,
                category=LearningCategory.FEATURE_REQUEST,
                pattern_key="test",
                summary="s",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
                recurrence_count=1,
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

    def test_rejects_invalid_confidence(self) -> None:
        from datetime import UTC, datetime

        try:
            FeatureRequestRecord(
                id=1,
                category=LearningCategory.FEATURE_REQUEST,
                pattern_key="test",
                summary="s",
                evidence="e",
                justification="j",
                impact="i",
                priority=Priority.HIGH,
                recurrence_count=1,
                confidence=1.5,
                status=LearningStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        except Exception:
            pass
        else:
            raise AssertionError("Expected validation error for confidence > 1.0")
