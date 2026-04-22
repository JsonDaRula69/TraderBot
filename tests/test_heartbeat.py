"""Tests for the heartbeat cycle — 7-step self-review, adaptation, and health check."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from traderbot.cli import app
from traderbot.db.decisions import DbDecision
from traderbot.db.decisions import init_table as init_decisions_table
from traderbot.heartbeat import (
    AdaptationReview,
    CircuitBreakerReview,
    DecisionReview,
    HeartbeatResult,
    LearningPromotionReview,
    PerformanceReview,
    SystemHealthReview,
    run_heartbeat_cycle,
    step_bayesian_adaptation,
    step_circuit_breaker_check,
    step_decision_review,
    step_learning_promotion,
    step_performance_review,
    step_system_health,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize all required tables for heartbeat tests."""
    init_decisions_table(conn)
    from traderbot.db.learnings import init_table as init_learnings_table
    from traderbot.learning import init_task_observations_table

    init_learnings_table(conn)
    init_task_observations_table(conn)


def _insert_decision(
    conn: sqlite3.Connection,
    ticker: str = "KXBTCD-26MAR31-T55000",
    direction: str = "yes",
    quantity: int = 1,
    price: int = 50,
    confidence: float = 0.6,
    outcome: str = "executed",
    actual_result: int | None = None,
    hours_ago: float = 1.0,
) -> int:
    """Insert a decision row and return its id."""
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    cursor = conn.execute(
        """INSERT INTO decisions
           (timestamp, ticker, direction, quantity, price, signal_strength,
            confidence, edge_estimate, risk_checks, outcome, rejection_reason,
            actual_result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ts, ticker, direction, quantity, price, 0.5,
            confidence, 0.03, '{"all": true}', outcome, None,
            actual_result,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _make_decision(
    id: int = 1,
    direction: str = "yes",
    ticker: str = "KXBTCD-26MAR31-T55000",
    price: int = 50,
    quantity: int = 1,
    confidence: float = 0.6,
    outcome: str = "executed",
    actual_result: bool | None = None,
    hours_ago: float = 1.0,
) -> DbDecision:
    """Create a DbDecision instance for testing."""
    return DbDecision(
        id=id,
        timestamp=datetime.now(UTC) - timedelta(hours=hours_ago),
        ticker=ticker,
        direction=direction,
        quantity=quantity,
        price=price,
        signal_strength=0.5,
        confidence=confidence,
        edge_estimate=0.03,
        risk_checks={"all": True},
        outcome=outcome,
        rejection_reason=None,
        actual_result=actual_result,
    )


# ---------------------------------------------------------------------------
# Step 1: Performance Review
# ---------------------------------------------------------------------------


class TestPerformanceReview:
    def test_empty_decisions(self):
        result = step_performance_review([])
        assert result.trade_count == 0
        assert result.win_rate == 0.0
        assert result.total_pnl_cents == 0
        assert result.deviation_flag == ""

    def test_winning_trades(self):
        decisions = [
            _make_decision(id=1, direction="yes", price=40, actual_result=True),
            _make_decision(id=2, direction="yes", price=40, actual_result=True),
        ]
        result = step_performance_review(decisions)
        assert result.trade_count == 2
        assert result.win_rate == 1.0
        assert result.total_pnl_cents == 120
        assert result.avg_confidence == 0.6

    def test_losing_trades(self):
        decisions = [
            _make_decision(id=1, direction="yes", price=60, actual_result=False),
        ]
        result = step_performance_review(decisions)
        assert result.trade_count == 1
        assert result.win_rate == 0.0
        assert result.total_pnl_cents == -60

    def test_mixed_trades(self):
        decisions = [
            _make_decision(id=1, direction="yes", price=40, actual_result=True),
            _make_decision(id=2, direction="yes", price=60, actual_result=False),
        ]
        result = step_performance_review(decisions)
        assert result.trade_count == 2
        assert result.win_rate == 0.5

    def test_deviation_flag_above_expected(self):
        decisions = [
            _make_decision(id=i, direction="yes", price=40, actual_result=True)
            for i in range(8)
        ]
        result = step_performance_review(decisions)
        assert result.deviation_flag == "win_rate_above_expected"

    def test_deviation_flag_below_expected(self):
        decisions = [
            _make_decision(id=i, direction="yes", price=60, actual_result=False)
            for i in range(6)
        ]
        result = step_performance_review(decisions)
        assert result.deviation_flag == "win_rate_below_expected"

    def test_no_direction_trades_ignored(self):
        decisions = [
            _make_decision(id=1, outcome="rejected"),
            _make_decision(id=2, outcome="held"),
        ]
        result = step_performance_review(decisions)
        assert result.trade_count == 0

    def test_avg_confidence_multiple(self):
        decisions = [
            _make_decision(id=1, confidence=0.8, actual_result=True),
            _make_decision(id=2, confidence=0.4, actual_result=False),
        ]
        result = step_performance_review(decisions)
        assert abs(result.avg_confidence - 0.6) < 1e-9


# ---------------------------------------------------------------------------
# Step 2: Decision Review
# ---------------------------------------------------------------------------


class TestDecisionReview:
    def test_empty(self):
        result = step_decision_review([])
        assert result.closed_count == 0
        assert result.prediction_accuracy == 0.0
        assert result.open_count == 0

    def test_correct_yes_prediction(self):
        decisions = [
            _make_decision(id=1, direction="yes", actual_result=True),
        ]
        result = step_decision_review(decisions)
        assert result.closed_count == 1
        assert result.correct_predictions == 1
        assert result.prediction_accuracy == 1.0

    def test_incorrect_yes_prediction(self):
        decisions = [
            _make_decision(id=1, direction="yes", actual_result=False),
        ]
        result = step_decision_review(decisions)
        assert result.correct_predictions == 0
        assert result.prediction_accuracy == 0.0

    def test_correct_no_prediction(self):
        decisions = [
            _make_decision(id=1, direction="no", actual_result=False),
        ]
        result = step_decision_review(decisions)
        assert result.correct_predictions == 1
        assert result.prediction_accuracy == 1.0

    def test_open_decisions(self):
        decisions = [
            _make_decision(id=1, actual_result=None),
            _make_decision(id=2, actual_result=None),
        ]
        result = step_decision_review(decisions)
        assert result.open_count == 2
        assert result.pending_review == ["KXBTCD-26MAR31-T55000", "KXBTCD-26MAR31-T55000"]

    def test_pending_review_capped_at_five(self):
        decisions = [
            _make_decision(id=i, ticker=f"TICK{i}", actual_result=None)
            for i in range(8)
        ]
        result = step_decision_review(decisions)
        assert len(result.pending_review) == 5

    def test_rejected_decisions_excluded(self):
        decisions = [
            _make_decision(id=1, outcome="rejected", actual_result=True),
            _make_decision(id=2, outcome="executed", actual_result=True),
        ]
        result = step_decision_review(decisions)
        assert result.closed_count == 1
        assert result.correct_predictions == 1


# ---------------------------------------------------------------------------
# Step 3: Bayesian Adaptation
# ---------------------------------------------------------------------------


class TestBayesianAdaptation:
    def test_empty_decisions(self):
        result = step_bayesian_adaptation([])
        assert not result.updated
        assert "no decisions" in result.skipped_reason

    def test_no_executed_decisions(self):
        decisions = [_make_decision(id=1, outcome="rejected")]
        result = step_bayesian_adaptation(decisions)
        assert not result.updated
        assert "no executed" in result.skipped_reason

    def test_dry_run(self):
        decisions = [_make_decision(id=1, actual_result=True)]
        result = step_bayesian_adaptation(decisions, dry_run=True)
        assert not result.updated
        assert "dry_run" in result.skipped_reason

    def test_successful_update(self):
        decisions = [
            _make_decision(id=i, direction="yes", price=40, actual_result=True)
            for i in range(12)
        ]
        config = MagicMock()
        config.min_observations = 1
        config.max_updates_per_day = 100
        config.max_change_pct = 0.20
        config.variance_reset_threshold = 0.001
        config.drift_threshold_pct = 0.10
        config.drift_consecutive_count = 3

        from traderbot.simulation.adaptation import BayesianAdapter
        adapter = BayesianAdapter(config=config)
        result = step_bayesian_adaptation(decisions, adapter=adapter)
        assert result.updated
        assert result.direction in ("increase", "decrease", "maintain")
        assert result.method == "beta_binomial"

    def test_cooldown_blocks_update(self):
        decisions = [
            _make_decision(id=i, direction="yes", price=40, actual_result=True)
            for i in range(12)
        ]
        from traderbot.simulation.adaptation import BayesianAdapter, GuardrailConfig

        config = GuardrailConfig(min_observations=1, max_updates_per_day=1)
        adapter = BayesianAdapter(config=config)
        adapter._update_timestamps = [datetime.now(UTC)] * 4
        result = step_bayesian_adaptation(decisions, adapter=adapter)
        assert not result.updated
        assert "Cooldown" in result.skipped_reason


# ---------------------------------------------------------------------------
# Step 4: Learning Promotion
# ---------------------------------------------------------------------------


class TestLearningPromotion:
    def test_empty_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = step_learning_promotion(conn)
        assert result.candidates_found == 0
        assert result.promoted_count == 0
        conn.close()

    def test_dry_run_no_promotions(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = step_learning_promotion(conn, dry_run=True)
        assert result.promoted_count == 0
        conn.close()

    def test_promotion_with_eligible_pattern(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        from traderbot.db.learnings import LearningCategory, increment_recurrence, record_pattern
        from traderbot.learning import record_task_observation

        pattern_id = record_pattern(
            conn,
            category=LearningCategory.MARKET_BEHAVIOR,
            summary="Test pattern for heartbeat",
            evidence="Test evidence",
            confidence=0.8,
        )
        for _ in range(3):
            increment_recurrence(conn, pattern_id)
        for task_idx in range(3):
            record_task_observation(conn, pattern_id, f"task-{task_idx}")

        result = step_learning_promotion(conn)
        assert result.candidates_found == 1
        assert result.promoted_count == 1
        conn.close()


# ---------------------------------------------------------------------------
# Step 5: Circuit Breaker Check
# ---------------------------------------------------------------------------


class TestCircuitBreakerCheck:
    def test_default_normal(self):
        result = step_circuit_breaker_check()
        assert result.level == "NORMAL"
        assert result.can_trade is True

    def test_with_mock_breaker(self):
        from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreakerState

        mock_breaker = MagicMock()
        mock_breaker.get_state.return_value = CircuitBreakerState(
            level=BreakerLevel.HALT,
            can_trade=False,
            reason="Daily loss exceeds 2%",
        )
        result = step_circuit_breaker_check(breaker=mock_breaker)
        assert result.level == "HALT"
        assert not result.can_trade
        assert "2%" in result.reason


# ---------------------------------------------------------------------------
# Step 6: System Health
# ---------------------------------------------------------------------------


class TestSystemHealth:
    def test_healthy_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = step_system_health(conn)
        assert result.db_integrity == "ok"
        conn.close()

    def test_no_decisions_freshness(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = step_system_health(conn)
        assert result.data_freshness == "no_decisions_yet"
        conn.close()

    def test_stale_data_alert(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        _insert_decision(conn, hours_ago=48)
        result = step_system_health(conn)
        assert any("Stale" in a for a in result.alerts)
        conn.close()

    def test_api_unavailable(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        with patch.dict("sys.modules", {"traderbot.kalshi.client": None}):
            step_system_health(conn)
        conn.close()


# ---------------------------------------------------------------------------
# Full Heartbeat Cycle
# ---------------------------------------------------------------------------


class TestHeartbeatCycle:
    def test_full_cycle_empty_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        hb_path = Path("/tmp/test_heartbeat_empty.md")
        result = run_heartbeat_cycle(conn, heartbeat_path=hb_path, dry_run=True)
        assert "performance_review" in result.steps_completed
        assert "decision_review" in result.steps_completed
        assert "bayesian_adaptation" in result.steps_completed
        assert "learning_promotion" in result.steps_completed
        assert "circuit_breaker_check" in result.steps_completed
        assert "system_health" in result.steps_completed
        assert "update_heartbeat_md" in result.steps_completed
        assert len(result.steps_completed) == 7
        conn.close()

    def test_full_cycle_with_decisions(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        _insert_decision(conn, direction="yes", price=40, actual_result=1, hours_ago=1)
        _insert_decision(conn, direction="yes", price=40, actual_result=1, hours_ago=2)
        _insert_decision(conn, direction="yes", price=60, actual_result=0, hours_ago=3)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        result = run_heartbeat_cycle(conn, heartbeat_path=hb_path)
        assert result.performance.trade_count == 3
        assert result.decisions.closed_count == 3
        conn.close()

    def test_heartbeat_md_written(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        run_heartbeat_cycle(conn, heartbeat_path=hb_path)
        assert hb_path.exists()
        content = hb_path.read_text()
        assert "Heartbeat:" in content
        assert "Performance" in content
        assert "Adaptation" in content
        assert "Circuit Breaker" in content
        assert "System Health" in content
        conn.close()

    def test_heartbeat_md_timestamp(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        before = datetime.now(UTC)
        run_heartbeat_cycle(conn, heartbeat_path=hb_path)
        after = datetime.now(UTC)

        content = hb_path.read_text()
        ts_line = next(line for line in content.split("\n") if line.startswith("## Last Heartbeat:"))
        ts_str = ts_line.replace("## Last Heartbeat:", "").strip()
        ts = datetime.fromisoformat(ts_str)
        assert before <= ts <= after
        conn.close()

    def test_dry_run_no_file_written(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        run_heartbeat_cycle(conn, heartbeat_path=hb_path, dry_run=True)
        assert not hb_path.exists()
        conn.close()

    def test_steps_in_correct_order(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = run_heartbeat_cycle(conn, dry_run=True)
        expected_order = [
            "performance_review",
            "decision_review",
            "bayesian_adaptation",
            "learning_promotion",
            "circuit_breaker_check",
            "system_health",
            "update_heartbeat_md",
        ]
        assert result.steps_completed == expected_order
        conn.close()


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------


class TestHeartbeatCLI:
    def test_heartbeat_help(self):
        result = runner.invoke(app, ["heartbeat", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output
        assert "--dry-run" in result.output

    def test_heartbeat_json_output(self):
        result = runner.invoke(app, ["heartbeat", "--json", "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "timestamp" in data
        assert "performance" in data
        assert "decisions" in data
        assert "adaptation" in data
        assert "learning_promotion" in data
        assert "circuit_breaker" in data
        assert "system_health" in data
        assert "steps_completed" in data

    def test_heartbeat_rich_output(self):
        result = runner.invoke(app, ["heartbeat", "--dry-run"])
        assert result.exit_code == 0
        assert "Heartbeat" in result.output
        assert "Performance" in result.output
        assert "Adaptation" in result.output
        assert "Circuit Breaker" in result.output

    def test_heartbeat_dry_run_flag(self):
        result = runner.invoke(app, ["heartbeat", "--json", "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "dry_run" in data["adaptation"]["skipped_reason"] or "no decisions" in data["adaptation"]["skipped_reason"]

    def test_heartbeat_no_dry_run(self):
        result = runner.invoke(app, ["heartbeat", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["steps_completed"]) == 7


# ---------------------------------------------------------------------------
# HeartbeatResult model serialization
# ---------------------------------------------------------------------------


class TestHeartbeatResultModel:
    def test_json_round_trip(self):
        now = datetime.now(UTC)
        result = HeartbeatResult(
            timestamp=now,
            performance=PerformanceReview(trade_count=5, win_rate=0.6),
            decisions=DecisionReview(closed_count=3, correct_predictions=2),
            adaptation=AdaptationReview(updated=True, direction="increase"),
            learning_promotion=LearningPromotionReview(candidates_found=1),
            circuit_breaker=CircuitBreakerReview(level="NORMAL"),
            system_health=SystemHealthReview(db_integrity="ok"),
            steps_completed=["performance_review"],
        )
        data = result.model_dump(mode="json")
        assert data["performance"]["trade_count"] == 5
        assert data["adaptation"]["direction"] == "increase"
        assert data["circuit_breaker"]["level"] == "NORMAL"

    def test_all_pydantic_strict(self):
        """Verify ConfigDict(strict=True, extra='forbid') on all models."""
        for model_cls in [
            PerformanceReview, DecisionReview, AdaptationReview,
            LearningPromotionReview, CircuitBreakerReview,
            SystemHealthReview, HeartbeatResult,
        ]:
            cfg = model_cls.model_config
            assert cfg.get("strict") is True, f"{model_cls.__name__} not strict"
            assert cfg.get("extra") == "forbid", f"{model_cls.__name__} allows extra"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_graceful_empty_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        result = run_heartbeat_cycle(conn, dry_run=True)
        assert result.performance.trade_count == 0
        assert result.decisions.closed_count == 0
        assert result.adaptation.skipped_reason != ""
        conn.close()

    def test_api_unreachable_graceful(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        with patch.dict("sys.modules", {"traderbot.kalshi.client": None}):
            result = step_system_health(conn)
            assert result.api_connectivity in ("unavailable", "not_checked", "unknown")
        conn.close()

    def test_single_decision(self):
        decisions = [_make_decision(id=1, actual_result=True)]
        perf = step_performance_review(decisions)
        review = step_decision_review(decisions)
        assert perf.trade_count == 1
        assert review.closed_count == 1

    def test_many_stale_decisions(self):
        decisions = [
            _make_decision(id=i, actual_result=None, hours_ago=72)
            for i in range(20)
        ]
        perf = step_performance_review(decisions)
        # None actual_result → no wins counted for those that are executed but unresolved
        assert perf.trade_count == 20

    def test_heartbeat_md_contains_circuit_breaker_level(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        run_heartbeat_cycle(conn, heartbeat_path=hb_path)
        content = hb_path.read_text()
        assert "NORMAL" in content
        conn.close()

    def test_heartbeat_md_contains_alerts_section(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        run_heartbeat_cycle(conn, heartbeat_path=hb_path)
        content = hb_path.read_text()
        assert "Alerts" in content
        conn.close()
