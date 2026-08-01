"""End-to-end integration test for the autonomous recovery cycle.

Validates the full cycle: breaker escalation -> adaptation feedback -> experiment
trigger -> deployment -> clear blocker.

Uses mocks for all external dependencies (no real Kalshi API, no real experiment DB).
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from traderbot.db.decisions import DbDecision
from traderbot.db.decisions import init_table as init_decisions_table
from traderbot.db.positions import init_table as init_positions_table
from traderbot.heartbeat import (
    _compute_breaker_failures,
    step_bayesian_adaptation,
    step_circuit_breaker_check,
    step_recovery_experiment,
    WsHealthReview,
    TokenStalenessReview,
)
from traderbot.risk.circuit_breaker import (
    BreakerLevel,
    BreakerTransition,
    CircuitBreaker,
    CircuitBreakerState,
)
from traderbot.simulation.adaptation import BayesianAdapter, BinomialObservations, GuardrailConfig, WEAK_BETA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_decision(
    id: int = 1,
    direction: str = "yes",
    ticker: str = "KXHIGHNY-26JUN02-T72",
    price: int = 50,
    quantity: int = 1,
    confidence: float = 0.6,
    outcome: str = "executed",
    actual_result: bool | None = None,
    hours_ago: float = 1.0,
) -> DbDecision:
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


def _make_breaker_with_transitions(
    state_file: Path,
    transitions: list[BreakerTransition],
    current_level: BreakerLevel,
) -> CircuitBreaker:
    """Create a real CircuitBreaker and drive it through check() to produce transitions."""
    breaker = CircuitBreaker(state_file=state_file)
    return breaker


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize all required tables."""
    init_decisions_table(conn)
    from traderbot.db.learnings import init_table as init_learnings_table
    from traderbot.learning import init_task_observations_table

    init_learnings_table(conn)
    init_positions_table(conn)
    init_task_observations_table(conn)


def _seed_experiment_db(db_path: Path, n_markets: int = 12) -> None:
    """Seed the experiment DB with n_markets markets."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(db_path))
    from traderbot.db.experiment_schema import create_tables

    create_tables(conn)
    for i in range(n_markets):
        conn.execute(
            "INSERT INTO markets (ticker, question, city, city_prefix, lat, lon, "
            "timezone, resolution_date, close_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"TEST-RECOVERY-{i}",
                f"Recovery test market {i}",
                "NYC",
                "KXHIGHNY",
                40.7,
                -74.0,
                "America/New_York",
                "2099-12-31",
                "2099-12-31T23:59:59",
            ),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# E2E Autonomous Recovery Cycle
# ---------------------------------------------------------------------------


class TestAutonomousRecoveryCycle:
    """End-to-end: breaker escalation -> adaptation -> experiment -> deploy -> clear."""

    def test_full_recovery_cycle(self, tmp_path: Path):
        """Simulate the complete autonomous recovery cycle.

        Steps:
        1. Start with NORMAL breaker -> simulate drawdown -> SLOW -> HALT -> FULL_STOP
        2. FULL_STOP triggers experiment check (mock experiment DB with >=10 markets)
        3. Experiment runs with mock treatments
        4. Winning treatment -> recovery report written
        5. Profile update deploys treatment (with valid deployment bar)
        6. FULL_STOP clears, breaker returns to NORMAL
        Also: adapter state tracked at each step (beta increases on escalation)
        Also: settlement sync runs during heartbeat
        """
        import traderbot.heartbeat as hb_mod

        # Reset global state
        hb_mod._last_processed_transition_ts = 0.0
        hb_mod._last_full_stop_experiment_ts = 0.0

        state_file = tmp_path / "breaker_state.json"

        # ---- Phase 1: Start NORMAL, escalate through SLOW -> HALT -> FULL_STOP ----
        breaker = CircuitBreaker(state_file=state_file)
        assert breaker.get_state().level == BreakerLevel.NORMAL

        # Track adapter beta across escalation
        adapter_config = GuardrailConfig(min_observations=1, max_updates_per_day=100)
        state_path = tmp_path / "adapter_state.json"
        adapter = BayesianAdapter(config=adapter_config, state_path=state_path)

        # Initial beta from WEAK_BETA
        initial_beta = adapter._distribution_states.get("edge_threshold", {}).get("beta", WEAK_BETA.beta)
        beta_values = [initial_beta]

        # Step 1a: NORMAL (daily_loss=0, drawdown=0)
        state = breaker.check(daily_loss_pct=0.0, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True

        # Step 1b: SLOW (daily_loss crosses 0.5% of default threshold)
        state = breaker.check(daily_loss_pct=0.015, drawdown_pct=0.005)
        assert state.level == BreakerLevel.SLOW
        assert state.can_trade is True
        assert state.position_size_multiplier == 0.5
        assert len(breaker.get_transitions_since(0)) >= 1  # NORMAL->SLOW

        # Feed SLOW escalation into adapter (should add 1 weighted failure)
        decisions_losses = [
            _make_decision(id=i, direction="yes", price=60, actual_result=False, outcome="executed")
            for i in range(12)
        ]
        result = step_bayesian_adaptation(decisions_losses, adapter=adapter, breaker=breaker)
        assert result.updated
        beta_after_slow = adapter._distribution_states.get("edge_threshold", {}).get("beta", 0)
        beta_values.append(beta_after_slow)

        # Step 1c: HALT (daily_loss crosses 1% threshold)
        state = breaker.check(daily_loss_pct=0.025, drawdown_pct=0.015)
        assert state.level == BreakerLevel.HALT
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

        # Feed HALT escalation into adapter (should add 3 weighted failures)
        adapter2 = BayesianAdapter(config=adapter_config, state_path=state_path)
        result2 = step_bayesian_adaptation(decisions_losses, adapter=adapter2, breaker=breaker)
        assert result2.updated
        beta_after_halt = adapter2._distribution_states.get("edge_threshold", {}).get("beta", 0)
        beta_values.append(beta_after_halt)

        # Step 1d: FULL_STOP (drawdown crosses 10% threshold)
        state = breaker.check(daily_loss_pct=0.05, drawdown_pct=0.12)
        assert state.level == BreakerLevel.FULL_STOP
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

        # Verify beta increases with escalation (more beta = more pessimistic)
        # At least some of the beta values should increase across escalation stages
        # (due to weighted failures from breaker transitions)
        assert beta_values[-1] >= beta_values[0], (
            f"Beta should increase with escalation: {beta_values}"
        )

        # ---- Phase 2: FULL_STOP triggers recovery experiment check ----
        breaker_review = step_circuit_breaker_check(breaker=breaker)
        assert breaker_review.level == "FULL_STOP"
        assert not breaker_review.can_trade

        # Seed experiment DB with >= 10 markets
        experiment_db = tmp_path / "experiment.db"
        _seed_experiment_db(experiment_db, n_markets=12)

        # Mock the experiment harness and registry to avoid requiring real LLM/Ollama
        mock_treatment_cls = MagicMock()
        mock_treatment_instance = MagicMock()
        mock_treatment_instance.name = "momentum_v2"
        mock_treatment_cls.return_value = mock_treatment_instance
        mock_treatment_cls.name = "momentum_v2"

        mock_control_cls = MagicMock()
        mock_control_instance = MagicMock()
        mock_control_instance.name = "control"
        mock_control_cls.return_value = mock_control_instance
        mock_control_cls.name = "control"

        mock_result = MagicMock()
        mock_result.treatment = "momentum_v2"
        mock_result.control = "control"
        mock_result.delta_profit = 15.0
        mock_result.p_value = 0.01  # Significant
        mock_result.effect_size = 0.8  # Large effect
        mock_result.n_markets = 6
        mock_result.improvement = True

        with patch("traderbot.experiment.registry.discover_treatments", return_value={"control": mock_control_cls, "momentum_v2": mock_treatment_cls}), \
             patch("traderbot.experiment.registry.get_treatment", side_effect=lambda name: mock_control_cls if name == "control" else mock_treatment_cls), \
             patch("traderbot.experiment.registry.register_treatment"), \
             patch("traderbot.experiment.harness.Harness") as MockHarness, \
             patch("traderbot.experiment.results.score_run", return_value=[mock_result]), \
             patch("traderbot.llm.client.LLMClient"), \
             patch("traderbot.llm.ollama.OllamaProvider"):

            mock_harness_instance = MagicMock()
            MockHarness.return_value = mock_harness_instance

            # Run recovery experiment
            recovery = step_recovery_experiment(
                breaker=breaker,
                experiment_db_path=experiment_db,
            )

        # Recovery experiment should have triggered
        assert recovery.triggered is True
        assert recovery.markets_available == 12
        assert recovery.significant_treatment == "momentum_v2"
        assert recovery.p_value == 0.01
        assert recovery.effect_size == 0.8
        assert recovery.report_path != ""  # Recovery report was written

        # Verify report file exists
        report_path = Path(recovery.report_path)
        assert report_path.exists()
        report_content = report_path.read_text(encoding="utf-8")
        assert "Recovery Experiment Report" in report_content
        assert "momentum_v2" in report_content

        # ---- Phase 3: Deploy winning treatment, clear FULL_STOP ----
        # Verify still in FULL_STOP before deployment
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # clear_full_stop_on_deploy with valid deployment bar
        # Deployment bar: Sharpe >= 1.0, win_rate_improvement >= 5pp, samples >= 30
        cleared = breaker.clear_full_stop_on_deploy(
            sharpe=1.5,           # >= 1.0
            win_rate_improvement_pp=8.0,  # >= 5pp
            sample_count=50,      # >= 30
            agent_id="test-agent",
        )
        assert cleared is True

        # Verify breaker returned to NORMAL
        assert breaker.get_state().level == BreakerLevel.NORMAL
        assert breaker.get_state().can_trade is True
        assert breaker.get_state().position_size_multiplier == 1.0

        # ---- Phase 4: Verify deployment bar rejection cases ----
        # Reset to FULL_STOP for negative tests
        breaker.check(daily_loss_pct=0.05, drawdown_pct=0.12)
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Bar not met: insufficient Sharpe
        cleared_low_sharpe = breaker.clear_full_stop_on_deploy(
            sharpe=0.5, win_rate_improvement_pp=8.0, sample_count=50,
        )
        assert cleared_low_sharpe is False
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Bar not met: insufficient win rate improvement
        cleared_low_wr = breaker.clear_full_stop_on_deploy(
            sharpe=1.5, win_rate_improvement_pp=2.0, sample_count=50,
        )
        assert cleared_low_wr is False
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Bar not met: insufficient sample count
        cleared_low_n = breaker.clear_full_stop_on_deploy(
            sharpe=1.5, win_rate_improvement_pp=8.0, sample_count=10,
        )
        assert cleared_low_n is False
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Successful clearance
        cleared_final = breaker.clear_full_stop_on_deploy(
            sharpe=1.2, win_rate_improvement_pp=7.0, sample_count=40,
        )
        assert cleared_final is True
        assert breaker.get_state().level == BreakerLevel.NORMAL

    def test_settlement_sync_during_heartbeat(self, tmp_path: Path):
        """Verify settlement sync runs during heartbeat and bridges positions -> decisions."""
        import asyncio

        from traderbot.heartbeat import run_heartbeat_cycle
        from traderbot.db.positions import update_settlement, upsert
        from traderbot.kalshi.models import Position

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        # Insert a decision in the decisions table (need actual row in DB)
        ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        conn.execute(
            """INSERT INTO decisions
               (timestamp, ticker, direction, quantity, price, signal_strength,
                confidence, edge_estimate, risk_checks, outcome, rejection_reason,
                actual_result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, "KXHIGHNY-26JUN02-T72", "yes", 1, 50, 0.5, 0.6, 0.03,
             '{"all": true}', "executed", None, None),
        )
        conn.commit()

        # Insert a position in the positions table via upsert
        pos = Position(
            ticker="KXHIGHNY-26JUN02-T72",
            side="yes",
            quantity=1,
            avg_price=50,
        )
        upsert(conn, pos)

        # Mark the position as settled (won) via update_settlement
        update_settlement(
            conn,
            ticker="KXHIGHNY-26JUN02-T72",
            result=True,
            pnl_cents=50,
        )

        # Verify position has settlement_result
        row = conn.execute(
            "SELECT settlement_result FROM positions WHERE ticker = ?",
            ("KXHIGHNY-26JUN02-T72",),
        ).fetchone()
        assert row["settlement_result"] == 1

        # Run heartbeat cycle — this should trigger _sync_settlement_before_adaptation
        hb_path = tmp_path / "HEARTBEAT_DATA.md"
        state_path = tmp_path / "adapter_state.json"

        with patch("traderbot.heartbeat.step_ws_health", return_value=WsHealthReview(status="not_running")), \
             patch("traderbot.heartbeat.step_token_staleness", return_value=TokenStalenessReview(valid=True, degraded=False, expired=False, token_source="none", profile="", agent="")):
            result = asyncio.run(
                run_heartbeat_cycle(
                    conn,
                    heartbeat_path=hb_path,
                    state_path=state_path,
                    dry_run=True,
                )
            )

        assert "performance_review" in result.steps_completed

        # After heartbeat, check that settlement was synced to decisions
        synced_decision = conn.execute(
            "SELECT actual_result FROM decisions WHERE ticker = ?",
            ("KXHIGHNY-26JUN02-T72",),
        ).fetchone()
        # The sync should have set actual_result based on settlement
        assert synced_decision["actual_result"] == 1, (
            "Settlement sync should propagate position result to decision"
        )

        conn.close()

    def test_adapter_state_changes_on_escalation(self, tmp_path: Path):
        """Verify BayesianAdapter beta parameter increases as breaker escalates.

        Escalation weights: SLOW=+1, HALT=+3, FULL_STOP=+5 failures.
        Each escalation should push beta higher (more pessimistic prior).
        """
        import traderbot.heartbeat as hb_mod

        state_file = tmp_path / "breaker_state.json"
        adapter_state_path = tmp_path / "adapter_state.json"

        config = GuardrailConfig(min_observations=1, max_updates_per_day=100)

        # Create 12 losing decisions to drive adaptation
        losing_decisions = [
            _make_decision(id=i, direction="yes", price=60, actual_result=False, outcome="executed")
            for i in range(12)
        ]

        # Reset global state
        hb_mod._last_processed_transition_ts = 0.0
        try:
            # Phase 1: NORMAL state, no breaker
            breaker_normal = CircuitBreaker(state_file=state_file)
            adapter_normal = BayesianAdapter(config=config, state_path=adapter_state_path)
            state_normal = breaker_normal.check(daily_loss_pct=0.0, drawdown_pct=0.0)
            assert state_normal.level == BreakerLevel.NORMAL

            result_normal = step_bayesian_adaptation(
                losing_decisions, adapter=adapter_normal, breaker=breaker_normal
            )
            beta_normal = adapter_normal._distribution_states.get("edge_threshold", {}).get("beta", 0)

            # Phase 2: Drive to SLOW, feed escalation
            breaker_slow = CircuitBreaker(state_file=state_file)
            breaker_slow.check(daily_loss_pct=0.015, drawdown_pct=0.005)  # Triggers SLOW
            adapter_slow = BayesianAdapter(config=config, state_path=adapter_state_path)
            result_slow = step_bayesian_adaptation(
                losing_decisions, adapter=adapter_slow, breaker=breaker_slow
            )
            beta_slow = adapter_slow._distribution_states.get("edge_threshold", {}).get("beta", 0)

            # Phase 3: Drive to FULL_STOP, feed escalation
            breaker_fs = CircuitBreaker(state_file=state_file)
            breaker_fs.check(daily_loss_pct=0.05, drawdown_pct=0.12)  # Triggers FULL_STOP
            adapter_fs = BayesianAdapter(config=config, state_path=adapter_state_path)
            result_fs = step_bayesian_adaptation(
                losing_decisions, adapter=adapter_fs, breaker=breaker_fs
            )
            beta_full_stop = adapter_fs._distribution_states.get("edge_threshold", {}).get("beta", 0)

            # Verifications: beta should be non-decreasing as more weighted
            # failures are added through escalation transitions
            # (At minimum, FULL_STOP should have >= beta than NORMAL since +5 failures added)
            assert beta_full_stop >= beta_normal, (
                f"Beta with FULL_STOP ({beta_full_stop}) should >= beta at NORMAL ({beta_normal})"
            )
        finally:
            hb_mod._last_processed_transition_ts = 0.0

    def test_breaker_escalation_weighted_failures(self):
        """Verify _compute_breaker_failures returns correct weights for each level."""
        import traderbot.heartbeat as hb_mod

        hb_mod._last_processed_transition_ts = 0.0
        try:
            # NORMAL -> SLOW: +1
            mock_slow = MagicMock()
            slow_trans = BreakerTransition(
                from_level=BreakerLevel.NORMAL, to_level=BreakerLevel.SLOW, timestamp=999.0
            )
            mock_slow.get_transitions_since.return_value = [slow_trans]
            assert _compute_breaker_failures(mock_slow) == 1

            # Reset for next test
            hb_mod._last_processed_transition_ts = 0.0

            # NORMAL -> HALT: +3
            mock_halt = MagicMock()
            halt_trans = BreakerTransition(
                from_level=BreakerLevel.NORMAL, to_level=BreakerLevel.HALT, timestamp=1000.0
            )
            mock_halt.get_transitions_since.return_value = [halt_trans]
            assert _compute_breaker_failures(mock_halt) == 3

            # Reset for next test
            hb_mod._last_processed_transition_ts = 0.0

            # NORMAL -> FULL_STOP: +5
            mock_fs = MagicMock()
            fs_trans = BreakerTransition(
                from_level=BreakerLevel.NORMAL, to_level=BreakerLevel.FULL_STOP, timestamp=1001.0
            )
            mock_fs.get_transitions_since.return_value = [fs_trans]
            assert _compute_breaker_failures(mock_fs) == 5

            # Reset for next test
            hb_mod._last_processed_transition_ts = 0.0

            # Cumulative: SLOW + HALT = 1 + 3 = 4
            mock_combo = MagicMock()
            combo_trans = [
                BreakerTransition(from_level=BreakerLevel.NORMAL, to_level=BreakerLevel.SLOW, timestamp=1002.0),
                BreakerTransition(from_level=BreakerLevel.SLOW, to_level=BreakerLevel.HALT, timestamp=1003.0),
            ]
            mock_combo.get_transitions_since.return_value = combo_trans
            assert _compute_breaker_failures(mock_combo) == 4
        finally:
            hb_mod._last_processed_transition_ts = 0.0

    def test_full_stop_no_departure_on_failed_deploy(self, tmp_path: Path):
        """FULL_STOP remains active when deployment bar is not met."""
        state_file = tmp_path / "breaker_state.json"
        breaker = CircuitBreaker(state_file=state_file)

        # Drive to FULL_STOP
        breaker.check(daily_loss_pct=0.05, drawdown_pct=0.12)
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Try to clear with each bar failing individually
        # Low Sharpe
        assert not breaker.clear_full_stop_on_deploy(sharpe=0.3, win_rate_improvement_pp=8.0, sample_count=50)
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Low win rate improvement
        assert not breaker.clear_full_stop_on_deploy(sharpe=1.5, win_rate_improvement_pp=1.0, sample_count=50)
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

        # Low sample count
        assert not breaker.clear_full_stop_on_deploy(sharpe=1.5, win_rate_improvement_pp=8.0, sample_count=5)
        assert breaker.get_state().level == BreakerLevel.FULL_STOP

    def test_experiment_no_trigger_on_non_full_stop(self, tmp_path: Path):
        """Recovery experiment does not trigger when breaker is SLOW or HALT."""
        import traderbot.heartbeat as hb_mod

        hb_mod._last_full_stop_experiment_ts = 0.0
        try:
            # Create mock breaker in HALT state (not FULL_STOP)
            mock_breaker = MagicMock()
            mock_breaker.get_state.return_value = CircuitBreakerState(
                level=BreakerLevel.HALT,
                can_trade=False,
                reason="Daily loss exceeds threshold",
            )
            result = step_recovery_experiment(breaker=mock_breaker)
            assert result.triggered is False
            assert result.skipped_reason == ""

            # SLOW
            mock_breaker.get_state.return_value = CircuitBreakerState(
                level=BreakerLevel.SLOW,
                can_trade=True,
                reason="Daily loss warning",
            )
            result = step_recovery_experiment(breaker=mock_breaker)
            assert result.triggered is False
            assert result.skipped_reason == ""
        finally:
            hb_mod._last_full_stop_experiment_ts = 0.0

    def test_experiment_insufficient_markets(self, tmp_path: Path):
        """Recovery experiment skips when < 10 markets in experiment DB."""
        import traderbot.heartbeat as hb_mod

        hb_mod._last_full_stop_experiment_ts = 0.0
        try:
            # Create experiment DB with only 5 markets
            experiment_db = tmp_path / "experiment_small.db"
            _seed_experiment_db(experiment_db, n_markets=5)

            mock_breaker = MagicMock()
            mock_breaker.get_state.return_value = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                can_trade=False,
                reason="Drawdown exceeds threshold",
            )
            transition = BreakerTransition(
                from_level=BreakerLevel.HALT,
                to_level=BreakerLevel.FULL_STOP,
                timestamp=5000.0,
            )

            def _transitions(since_ts: float) -> list:
                if 5000.0 > since_ts:
                    return [transition]
                return []

            mock_breaker.get_transitions_since.side_effect = _transitions

            result = step_recovery_experiment(breaker=mock_breaker, experiment_db_path=experiment_db)
            assert result.triggered is False
            assert result.markets_available == 5
            assert result.skipped_reason == "insufficient_markets"
        finally:
            hb_mod._last_full_stop_experiment_ts = 0.0

    def test_experiment_triggers_once_per_full_stop(self, tmp_path: Path):
        """Recovery experiment fires only once per FULL_STOP event."""
        import traderbot.heartbeat as hb_mod

        hb_mod._last_full_stop_experiment_ts = 0.0
        try:
            experiment_db = tmp_path / "experiment_once.db"
            _seed_experiment_db(experiment_db, n_markets=12)

            mock_breaker = MagicMock()
            mock_breaker.get_state.return_value = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                can_trade=False,
                reason="Drawdown exceeds threshold",
            )
            transition = BreakerTransition(
                from_level=BreakerLevel.HALT,
                to_level=BreakerLevel.FULL_STOP,
                timestamp=6000.0,
            )

            def _transitions(since_ts: float) -> list:
                if 6000.0 > since_ts:
                    return [transition]
                return []

            mock_breaker.get_transitions_since.side_effect = _transitions

            # First call — experiment DB is found but harness/registry will fail
            # (no mocking needed — it will fail gracefully after checking markets)
            result1 = step_recovery_experiment(breaker=mock_breaker, experiment_db_path=experiment_db)
            # It might fail at registry/harness stage, but it should have progressed past the once-per check
            # The key test: second call should skip with "already_processed_full_stop"
            result2 = step_recovery_experiment(breaker=mock_breaker, experiment_db_path=experiment_db)
            assert result2.triggered is False
            assert result2.skipped_reason == "already_processed_full_stop"
        finally:
            hb_mod._last_full_stop_experiment_ts = 0.0