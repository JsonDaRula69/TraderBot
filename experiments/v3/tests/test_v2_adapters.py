"""Tests for V2 adapter direct_decide() method on V2BinCalTreatment, V2LogisticRegTreatment, V2EnsembleTreatment."""

import pytest

from experiments.v3.treatment_interface import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    TreatmentResponse,
)


def _make_context(**overrides) -> TreatmentContext:
    defaults = dict(
        market=MarketData(
            ticker="KXHIGHNY-01JUL25-B90",
            city="New York",
            strike_type="greater",
            threshold=90.0,
            resolution_date="2025-07-01",
        ),
        forecast=ForecastData(
            forecast_temp_f=88.5,
            source="NWS",
            days_before=3,
            timestep=1,
        ),
        accuracy=AccuracyData(
            city="New York",
            lead_time=3,
            mae=2.5,
            bias=0.3,
            sample_count=100,
        ),
        prices=PriceData(
            yes_price=0.65,
            no_price=0.35,
            trade_count=150,
            open_interest=500,
            implied_prob=0.65,
        ),
        technicals=TechnicalData(
            rsi=45.0,
            bollinger_position=0.55,
            ema5=64.0,
            ema20=61.0,
            signal_direction="yes",
            signal_confidence=0.7,
        ),
        prior=PriorDecisions(decisions=[]),
        timestep=1,
        remaining=3,
    )
    defaults.update(overrides)
    return TreatmentContext(**defaults)


class TestV2BinCalDirectDecide:
    def test_has_direct_decide(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        assert hasattr(t, "direct_decide")
        assert callable(t.direct_decide)

    def test_returns_treatment_response(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        result = t.direct_decide(_make_context())
        assert isinstance(result, TreatmentResponse)

    def test_valid_decision(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        result = t.direct_decide(_make_context())
        assert result.decision in ("buy_yes", "buy_no", "skip")

    def test_prob_and_confidence_ranges(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        result = t.direct_decide(_make_context())
        assert 0.0 <= result.estimated_prob <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_db_fallback(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        result = t.direct_decide(_make_context())
        assert result.estimated_prob == pytest.approx(0.5, abs=0.1)

    def test_consistent_with_compute_decision(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        ctx = _make_context()
        direct = t.direct_decide(ctx)
        compute = t.compute_decision(ctx)
        assert direct.decision == compute.decision
        assert direct.estimated_prob == compute.estimated_prob

    def test_buy_yes_when_estimated_prob_exceeds_yes_price(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        ctx = _make_context(prices=PriceData(
            yes_price=0.20, no_price=0.80, trade_count=10, open_interest=50, implied_prob=0.20,
        ))
        result = t.direct_decide(ctx)
        assert result.decision == "buy_yes"

    def test_buy_no_when_estimated_prob_below_yes_price(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        t = V2BinCalTreatment()
        ctx = _make_context(prices=PriceData(
            yes_price=0.90, no_price=0.10, trade_count=10, open_interest=50, implied_prob=0.90,
        ))
        result = t.direct_decide(ctx)
        assert result.decision == "buy_no"


class TestV2LogisticRegDirectDecide:
    def test_has_direct_decide(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        t = V2LogisticRegTreatment()
        assert hasattr(t, "direct_decide")
        assert callable(t.direct_decide)

    def test_returns_treatment_response(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        t = V2LogisticRegTreatment()
        result = t.direct_decide(_make_context())
        assert isinstance(result, TreatmentResponse)

    def test_valid_decision(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        t = V2LogisticRegTreatment()
        result = t.direct_decide(_make_context())
        assert result.decision in ("buy_yes", "buy_no", "skip")

    def test_prob_and_confidence_ranges(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        t = V2LogisticRegTreatment()
        result = t.direct_decide(_make_context())
        assert 0.01 <= result.estimated_prob <= 0.99
        assert 0.1 <= result.confidence <= 1.0

    def test_consistent_with_compute_decision(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        t = V2LogisticRegTreatment()
        ctx = _make_context()
        direct = t.direct_decide(ctx)
        compute = t.compute_decision(ctx)
        assert direct.decision == compute.decision
        assert direct.estimated_prob == compute.estimated_prob


class TestV2EnsembleDirectDecide:
    def test_has_direct_decide(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        assert hasattr(t, "direct_decide")
        assert callable(t.direct_decide)

    def test_returns_treatment_response(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        result = t.direct_decide(_make_context())
        assert isinstance(result, TreatmentResponse)

    def test_valid_decision(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        result = t.direct_decide(_make_context())
        assert result.decision in ("buy_yes", "buy_no", "skip")

    def test_prob_and_confidence_ranges(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        result = t.direct_decide(_make_context())
        assert 0.01 <= result.estimated_prob <= 0.99
        assert 0.1 <= result.confidence <= 1.0

    def test_consistent_with_compute_decision(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        ctx = _make_context()
        direct = t.direct_decide(ctx)
        compute = t.compute_decision(ctx)
        assert direct.decision == compute.decision
        assert direct.estimated_prob == compute.estimated_prob

    def test_reasoning_includes_ensemble_prefix(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        t = V2EnsembleTreatment()
        result = t.direct_decide(_make_context())
        assert result.reasoning.startswith("[ensemble]")


class TestHarnessDirectDecidePath:
    def test_harness_uses_direct_decide_over_compute_decision(self):
        """Verify harness prefers direct_decide when both methods exist."""
        import sqlite3
        from unittest.mock import MagicMock

        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        from experiments.v3.db_schema import create_tables
        from experiments.v3.harness import Harness

        class TrackingTreatment(V2BinCalTreatment):
            direct_count = 0
            compute_count = 0

            def direct_decide(self, ctx):
                self.direct_count += 1
                return super().direct_decide(ctx)

            def compute_decision(self, ctx):
                self.compute_count += 1
                return super().compute_decision(ctx)

        conn = sqlite3.connect(":memory:")
        try:
            create_tables(conn)
            conn.execute(
                "INSERT OR REPLACE INTO markets (ticker, city, strike_type, threshold, resolution_date, settlement_result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("KXHIGHNY", "New York", "greater", 90.0, "2025-07-01", "yes"),
            )
            for ts in range(5):
                conn.execute(
                    "INSERT INTO market_prices (ticker, timestep, yes_price, no_price, trade_count, open_interest) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("KXHIGHNY", ts, 0.65, 0.35, 150, 500),
                )
                conn.execute(
                    "INSERT INTO forecast_snapshots (ticker, timestep, days_before, forecast_temp_f, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("KXHIGHNY", ts, 5 - ts, 88.5, "NWS"),
                )
            conn.execute(
                "INSERT INTO forecast_accuracy (city, lead_time, mae, bias, sample_count, low_confidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("New York", 3, 2.5, 0.3, 100, 0),
            )
            conn.commit()

            mock_llm = MagicMock(spec=["call"])
            mock_llm.call = MagicMock(side_effect=RuntimeError("LLM should not be called"))
            harness = Harness(conn, mock_llm, seed=99)

            treatment = TrackingTreatment()
            harness._run_market(
                treatments=[treatment],
                run_id="test-direct-decide",
                ticker="KXHIGHNY",
                replicate=0,
            )
            assert treatment.direct_count > 0, "direct_decide should be called"
            assert treatment.compute_count == 0, "compute_decision should NOT be called when direct_decide exists"
        finally:
            conn.close()
