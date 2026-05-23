"""Tests for scoring.py — P&L, weighted Brier, delta profit, skip rate, and score_run."""

import pytest

from experiments.v3.db_schema import create_tables
from experiments.v3.scoring import (
    compute_brier,
    compute_delta_profit,
    compute_pnl,
    compute_skip_rate,
    compute_weighted_brier,
    score_run,
)

# ---------------------------------------------------------------------------
# compute_pnl
# ---------------------------------------------------------------------------


class TestComputePnl:
    def test_buy_yes_settles_yes(self):
        """buy_yes at yes=0.60, YES → 40 cents."""
        assert compute_pnl("buy_yes", yes_price=0.60, settlement="YES") == 40

    def test_buy_yes_settles_no(self):
        """buy_yes at yes=0.60, NO → -60 cents."""
        assert compute_pnl("buy_yes", yes_price=0.60, settlement="NO") == -60

    def test_buy_no_settles_no(self):
        """buy_no at yes=0.60, NO → 60 cents."""
        assert compute_pnl("buy_no", yes_price=0.60, settlement="NO") == 60

    def test_buy_no_settles_yes(self):
        """buy_no at yes=0.60, YES → -40 cents."""
        assert compute_pnl("buy_no", yes_price=0.60, settlement="YES") == -40

    def test_skip_returns_zero(self):
        """skip → 0, regardless of settlement."""
        assert compute_pnl("skip", yes_price=0.60, settlement="YES") == 0
        assert compute_pnl("skip", yes_price=0.60, settlement="NO") == 0

    def test_none_settlement_returns_zero(self):
        """None settlement → 0 for any decision."""
        assert compute_pnl("buy_yes", yes_price=0.60, settlement=None) == 0
        assert compute_pnl("buy_no", yes_price=0.60, settlement=None) == 0


# ---------------------------------------------------------------------------
# compute_brier
# ---------------------------------------------------------------------------


class TestComputeBrier:
    def test_brier_yes(self):
        """brier(0.70, 'YES') → (0.70 - 1.0)^2 = 0.09."""
        assert compute_brier(0.70, "YES") == pytest.approx(0.09)

    def test_brier_no(self):
        """brier(0.30, 'NO') → (0.30 - 0.0)^2 = 0.09."""
        assert compute_brier(0.30, "NO") == pytest.approx(0.09)

    def test_brier_perfect_yes(self):
        """Perfect prediction gets zero."""
        assert compute_brier(1.0, "YES") == 0.0

    def test_brier_perfect_no(self):
        """Perfect prediction gets zero."""
        assert compute_brier(0.0, "NO") == 0.0

    def test_brier_worst_yes(self):
        """Worst prediction: prob 0.0 when YES."""
        assert compute_brier(0.0, "YES") == 1.0


# ---------------------------------------------------------------------------
# compute_delta_profit
# ---------------------------------------------------------------------------


class TestComputeDeltaProfit:
    def test_delta_profit(self):
        """treatment_pnl=35, control_pnl=-20 → delta=55."""
        result = compute_delta_profit(
            treatment_pnl=35,
            control_pnl=-20,
        )
        assert result["treatment_pnl"] == 35
        assert result["control_pnl"] == -20
        assert result["delta_profit"] == 55

    def test_both_zero(self):
        result = compute_delta_profit(treatment_pnl=0, control_pnl=0)
        assert result["delta_profit"] == 0

    def test_negative_delta(self):
        """Treatment worse than control."""
        result = compute_delta_profit(treatment_pnl=10, control_pnl=30)
        assert result["delta_profit"] == -20


# ---------------------------------------------------------------------------
# compute_weighted_brier
# ---------------------------------------------------------------------------


class TestComputeWeightedBrier:
    def test_contested_weight(self):
        """yes=0.50 (contested) → weight 2.0 on each brier."""
        # decisions with brier scores: 0.09, 0.01, 0.04 → mean = 0.0467
        # weight = 2.0 → 0.0933
        decisions = [
            {"decision": "buy_yes", "estimated_prob": 0.60, "yes_price": 0.50},
            {"decision": "buy_yes", "estimated_prob": 0.55, "yes_price": 0.50},
            {"decision": "buy_yes", "estimated_prob": 0.80, "yes_price": 0.50},
        ]
        settlement = "NO"
        result = compute_weighted_brier(decisions, settlement, yes_price=0.50)
        # Briers: (0.60-0)^2=0.36, (0.55-0)^2=0.3025, (0.80-0)^2=0.64
        # mean = (0.36+0.3025+0.64)/3 = 0.43417...
        # weighted = 2.0 * 0.43417 = 0.86833...
        expected = 2.0 * ((0.36 + 0.3025 + 0.64) / 3)
        assert result == pytest.approx(expected)

    def test_blowout_weight(self):
        """yes=0.10 (blowout) → weight 0.5 on each brier."""
        decisions = [
            {"decision": "buy_yes", "estimated_prob": 0.60, "yes_price": 0.10},
        ]
        settlement = "NO"
        result = compute_weighted_brier(decisions, settlement, yes_price=0.10)
        expected = 0.5 * 0.36  # (0.60-0)^2 = 0.36
        assert result == pytest.approx(expected)

    def test_empty_decisions(self):
        """No decisions → 0.0."""
        assert compute_weighted_brier([], "YES", yes_price=0.50) == 0.0

    def test_boundary_contested_low(self):
        """yes_price=0.20 is contested (boundary inclusive)."""
        decisions = [{"decision": "buy_yes", "estimated_prob": 0.50, "yes_price": 0.20}]
        result = compute_weighted_brier(decisions, "YES", yes_price=0.20)
        expected = 2.0 * 0.25  # (0.50-1.0)^2 = 0.25
        assert result == pytest.approx(expected)

    def test_boundary_contested_high(self):
        """yes_price=0.80 is contested (boundary inclusive)."""
        decisions = [{"decision": "buy_yes", "estimated_prob": 0.50, "yes_price": 0.80}]
        result = compute_weighted_brier(decisions, "YES", yes_price=0.80)
        expected = 2.0 * 0.25
        assert result == pytest.approx(expected)

    def test_uses_yes_price_param_not_dict_key(self):
        """The yes_price parameter to the function is what matters for weighting,
        not any key in the decision dict."""
        decisions = [{"decision": "buy_yes", "estimated_prob": 0.50}]
        result = compute_weighted_brier(decisions, "YES", yes_price=0.85)
        expected = 0.5 * 0.25  # blowout weight
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# compute_skip_rate
# ---------------------------------------------------------------------------


class TestComputeSkipRate:
    def test_basic_skip_rate(self):
        """3 skips out of 10 → 0.3."""
        decisions = [
            {"decision": "skip"}, {"decision": "skip"}, {"decision": "skip"},
            {"decision": "buy_yes"}, {"decision": "buy_no"},
            {"decision": "buy_yes"}, {"decision": "buy_no"},
            {"decision": "buy_yes"}, {"decision": "buy_no"},
            {"decision": "buy_yes"},
        ]
        assert compute_skip_rate(decisions) == 0.3

    def test_all_skip(self):
        decisions = [{"decision": "skip"}] * 5
        assert compute_skip_rate(decisions) == 1.0

    def test_no_skip(self):
        decisions = [{"decision": "buy_yes"}] * 5
        assert compute_skip_rate(decisions) == 0.0

    def test_empty(self):
        assert compute_skip_rate([]) == 0.0


# ---------------------------------------------------------------------------
# score_run — integration test with in-memory DB
# ---------------------------------------------------------------------------


class TestScoreRun:
    """Integration test using an in-memory SQLite database."""

    @pytest.fixture
    def db_conn(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        return conn

    def test_score_run_three_markets(self, db_conn):
        """3 markets, 2 treatments (control + model), 2 replicates each."""
        run_id = "run-001"

        # Insert experiment run
        db_conn.execute(
            "INSERT INTO experiment_runs (run_id, treatment_names_json, num_markets, num_replicates, seed, timestamp, status) "
            "VALUES (?, ?, 3, 2, 42, '2025-01-01T00:00:00', 'completed')",
            (run_id, '["control","model"]'),
        )

        # Insert 3 markets
        db_conn.execute(
            "INSERT INTO markets (ticker, city, strike_type, floor_strike, ceiling_strike, threshold, resolution_date, settlement_result, actual_value, event_ticker, series_ticker) "
            "VALUES ('MARKET-A', 'NYC', 'temp', 70, 80, 75, '2025-01-15', 'YES', 78.0, 'EVT-A', 'SER-A')"
        )
        db_conn.execute(
            "INSERT INTO markets (ticker, city, strike_type, floor_strike, ceiling_strike, threshold, resolution_date, settlement_result, actual_value, event_ticker, series_ticker) "
            "VALUES ('MARKET-B', 'LA', 'temp', 65, 75, 70, '2025-01-15', 'NO', 62.0, 'EVT-B', 'SER-B')"
        )
        db_conn.execute(
            "INSERT INTO markets (ticker, city, strike_type, floor_strike, ceiling_strike, threshold, resolution_date, settlement_result, actual_value, event_ticker, series_ticker) "
            "VALUES ('MARKET-C', 'CHI', 'temp', 50, 60, 55, '2025-01-15', 'YES', 57.0, 'EVT-C', 'SER-C')"
        )

        # Insert market_prices for each ticker at timestep 0
        for ticker in ("MARKET-A", "MARKET-B", "MARKET-C"):
            db_conn.execute(
                "INSERT INTO market_prices (ticker, timestep, yes_price, no_price) "
                "VALUES (?, 0, 0.60, 0.40)",
                (ticker,),
            )

        # Insert treatment decisions - 2 treatments x 2 replicates x 3 markets = 12 rows
        # control: "control" — always buys yes with estimated_prob=0.55 (decent but not perfect)
        # model: "model" — buys correctly (yes for A/C, no for B) with estimated_prob=0.70
        decisions_data = []
        for rep in (0, 1):
            # control treatment
            for ticker in ("MARKET-A", "MARKET-B", "MARKET-C"):
                decisions_data.append(
                    (run_id, ticker, 0, "control", rep, "buy_yes", 0.55, 0.80, "control always buys yes", 100)
                )
            # model treatment — trades correctly
            decisions_data.append(
                (run_id, "MARKET-A", 0, "model", rep, "buy_yes", 0.70, 0.85, "model predicts YES", 100)
            )
            decisions_data.append(
                (run_id, "MARKET-B", 0, "model", rep, "buy_no", 0.70, 0.85, "model predicts NO", 100)
            )
            decisions_data.append(
                (run_id, "MARKET-C", 0, "model", rep, "buy_yes", 0.70, 0.85, "model predicts YES", 100)
            )

        db_conn.executemany(
            "INSERT INTO treatment_decisions (run_id, ticker, timestep, treatment_name, replicate, decision, estimated_prob, confidence, reasoning, position_size_cents) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            decisions_data,
        )
        db_conn.commit()

        result = score_run(db_conn, run_id)

        # Basic structure
        assert isinstance(result, dict)
        assert "treatments" in result
        assert "control" in result["treatments"]
        assert "model" in result["treatments"]

        control = result["treatments"]["control"]
        model = result["treatments"]["model"]

        # Both treatments should have total_pnl (cross-replicate averaged)
        assert "total_pnl" in control
        assert "total_pnl" in model

        # model should outperform control because it trades correctly
        # control buys yes on all 3 markets → wins A/YES (+40), loses B/NO (-60), wins C/YES (+40) = +20
        # per replicate: 40 + (-60) + 40 = 20 → avg across 2 reps = 20
        # model: A/YES buy_yes=+40, B/NO buy_no=+60, C/YES buy_yes=+40 = +140 per rep → avg = 140
        assert control["total_pnl"] == 20
        assert model["total_pnl"] == 140

        # Delta profit
        assert "delta_profit" in result
        assert result["delta_profit"] == 120  # 140 - 20

        # Skip rates
        assert "skip_rate" in control
        assert "skip_rate" in model
        assert control["skip_rate"] == 0.0  # no skips
        assert model["skip_rate"] == 0.0

        # Weighted Brier
        assert "weighted_brier" in control
        assert "weighted_brier" in model

        # Per-market breakdown
        assert "per_market" in result
        assert "MARKET-A" in result["per_market"]
