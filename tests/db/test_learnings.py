from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from traderbot.db.learnings import LearningCategory, LearningRecord, LearningStatus, init_table


class TestLearningEnums:
    def test_learning_category_values(self) -> None:
        assert LearningCategory.MARKET_BEHAVIOR.value == "MarketBehavior"
        assert LearningCategory.RISK_SIGNAL.value == "RiskSignal"
        assert LearningCategory.TIMING.value == "Timing"
        assert LearningCategory.STRATEGY.value == "Strategy"
        assert LearningCategory.EXECUTION.value == "Execution"
        assert LearningCategory.FEATURE_REQUEST.value == "FeatureRequest"

    def test_learning_status_values(self) -> None:
        assert LearningStatus.ACTIVE.value == "active"
        assert LearningStatus.DEPRECATED.value == "deprecated"
        assert LearningStatus.PENDING_REVIEW.value == "pending_review"


class TestLearningRecord:
    def test_minimal_record(self) -> None:
        now = datetime.now(UTC)
        record = LearningRecord(
            id=1,
            category=LearningCategory.MARKET_BEHAVIOR,
            summary="BTC rallies before Fed meetings",
            evidence="Observed 12 times in 2025",
            confidence=0.85,
            created_at=now,
            updated_at=now,
        )
        assert record.id == 1
        assert record.category == LearningCategory.MARKET_BEHAVIOR
        assert record.status == LearningStatus.ACTIVE
        assert record.confidence == 0.85

    def test_explicit_status(self) -> None:
        now = datetime.now(UTC)
        record = LearningRecord(
            id=2,
            category=LearningCategory.RISK_SIGNAL,
            summary="High VIX correlates with reversals",
            evidence="Backtest shows 70% accuracy",
            confidence=0.7,
            status=LearningStatus.PENDING_REVIEW,
            created_at=now,
            updated_at=now,
        )
        assert record.status == LearningStatus.PENDING_REVIEW


class TestInitTable:
    def test_creates_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        init_table(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='learnings'")
        assert cursor.fetchone() is not None
        conn.close()
