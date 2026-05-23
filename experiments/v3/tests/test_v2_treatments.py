"""Tests for V2 methodology adapters in V3 treatment wrappers."""

import sqlite3

import pytest

from experiments.treatments.bin_cal import BinCalTreatment
from experiments.treatments.ensemble import EnsembleTreatment
from experiments.treatments.llm_synthesis import LLMSynthesisTreatment
from experiments.treatments.logistic_reg import LogisticRegTreatment
from experiments.v3.db_schema import create_tables
from experiments.v3.harness import NUM_TIMESTEPS, Harness
from experiments.v3.llm_client import LLMResponse
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
            ticker="KXHIGHNY",
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


class MockLLM:
    def __init__(self, raise_on_call: bool = False):
        self.call_count = 0
        self._raise = raise_on_call

    def call(self, prompt: str) -> LLMResponse:
        if self._raise:
            raise RuntimeError("LLM should not be called")
        self.call_count += 1
        return LLMResponse(
            decision="skip",
            estimated_prob=0.5,
            confidence=0.3,
            reasoning="mock",
            raw_response="{}",
        )


def _seed_db(conn: sqlite3.Connection, ticker: str = "KXHIGHNY"):
    conn.execute(
        "INSERT OR REPLACE INTO markets (ticker, city, strike_type, threshold, resolution_date, settlement_result) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, "New York", "greater", 90.0, "2025-07-01", "yes"),
    )
    for ts in range(NUM_TIMESTEPS):
        conn.execute(
            "INSERT INTO market_prices (ticker, timestep, yes_price, no_price, trade_count, open_interest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, ts, 0.65, 0.35, 150, 500),
        )
        conn.execute(
            "INSERT INTO forecast_snapshots (ticker, timestep, days_before, forecast_temp_f, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticker, ts, 5 - ts, 88.5, "NWS"),
        )
    conn.execute(
        "INSERT INTO forecast_accuracy (city, lead_time, mae, bias, sample_count, low_confidence) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("New York", 3, 2.5, 0.3, 100, 0),
    )
    conn.commit()


# ── BinCalTreatment compute_decision ──────────────────────────────────

class TestBinCalComputeDecision:
    def test_has_compute_decision(self):
        t = BinCalTreatment()
        assert hasattr(t, "compute_decision")
        assert callable(t.compute_decision)

    def test_returns_treatment_response(self):
        t = BinCalTreatment()
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert isinstance(result, TreatmentResponse)

    def test_response_has_valid_decision(self):
        t = BinCalTreatment()
        result = t.compute_decision(_make_context())
        assert result.decision in ("buy_yes", "buy_no", "skip")

    def test_response_prob_in_range(self):
        t = BinCalTreatment()
        result = t.compute_decision(_make_context())
        assert 0.0 <= result.estimated_prob <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_db_fallback_uniform(self):
        t = BinCalTreatment()
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert result.estimated_prob == pytest.approx(0.5, abs=0.1)
        assert result.confidence == pytest.approx(0.1, abs=0.05)

    def test_custom_v2_db_path_is_respected(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"
        db_path.write_text("")
        t = BinCalTreatment(v2_db_path=str(db_path))
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert isinstance(result, TreatmentResponse)
        assert result.decision in ("buy_yes", "buy_no", "skip")


# ── LogisticRegTreatment compute_decision ─────────────────────────────

class TestLogisticRegComputeDecision:
    def test_has_compute_decision(self):
        t = LogisticRegTreatment()
        assert hasattr(t, "compute_decision")
        assert callable(t.compute_decision)

    def test_returns_treatment_response(self):
        t = LogisticRegTreatment()
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert isinstance(result, TreatmentResponse)

    def test_response_has_valid_decision(self):
        t = LogisticRegTreatment()
        result = t.compute_decision(_make_context())
        assert result.decision in ("buy_yes", "buy_no", "skip")

    def test_response_prob_in_range(self):
        t = LogisticRegTreatment()
        result = t.compute_decision(_make_context())
        assert 0.0 <= result.estimated_prob <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_db_fallback_uniform(self):
        t = LogisticRegTreatment()
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert 0.01 <= result.estimated_prob <= 0.99

    def test_custom_v2_db_path_is_respected(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"
        db_path.write_text("")
        t = LogisticRegTreatment(v2_db_path=str(db_path))
        ctx = _make_context()
        result = t.compute_decision(ctx)
        assert isinstance(result, TreatmentResponse)


# ── Non-deterministic treatments do NOT have compute_decision ─────────

class TestNonDeterministicTreatments:
    def test_llm_synthesis_no_compute_decision(self):
        t = LLMSynthesisTreatment()
        assert not hasattr(t, "compute_decision")

    def test_ensemble_no_compute_decision(self):
        t = EnsembleTreatment()
        assert not hasattr(t, "compute_decision")


# ── Harness deterministic path ────────────────────────────────────────

class TestHarnessDeterministicPath:
    def test_skips_llm_for_bin_cal(self):
        conn = sqlite3.connect(":memory:")
        try:
            create_tables(conn)
            _seed_db(conn)
            llm = MockLLM(raise_on_call=True)
            harness = Harness(conn, llm, seed=99)
            harness._run_market(
                treatments=[BinCalTreatment()],
                run_id="test-det-1",
                ticker="KXHIGHNY",
                replicate=0,
            )
            assert llm.call_count == 0
        finally:
            conn.close()

    def test_skips_llm_for_logistic_reg(self):
        conn = sqlite3.connect(":memory:")
        try:
            create_tables(conn)
            _seed_db(conn)
            llm = MockLLM(raise_on_call=True)
            harness = Harness(conn, llm, seed=99)
            harness._run_market(
                treatments=[LogisticRegTreatment()],
                run_id="test-det-2",
                ticker="KXHIGHNY",
                replicate=0,
            )
            assert llm.call_count == 0
        finally:
            conn.close()

    def test_still_calls_llm_for_non_deterministic(self):
        conn = sqlite3.connect(":memory:")
        try:
            create_tables(conn)
            _seed_db(conn)
            llm = MockLLM()
            harness = Harness(conn, llm, seed=99)
            harness._run_market(
                treatments=[LLMSynthesisTreatment()],
                run_id="test-nondet-1",
                ticker="KXHIGHNY",
                replicate=0,
            )
            assert llm.call_count > 0
        finally:
            conn.close()


# ── V2 prompt integration ─────────────────────────────────────────────

class TestLLMSynthesisV2Prompt:
    def test_format_prompt_uses_v2_template(self):
        t = LLMSynthesisTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "weather market analyst" in prompt.lower()
        assert "Forecast" in prompt
        assert "Threshold" in prompt
        assert "estimated_prob" in prompt

    def test_format_prompt_includes_question(self):
        t = LLMSynthesisTreatment()
        ctx = _make_context(
            market=MarketData(
                ticker="KXHIGHNY",
                city="New York",
                strike_type="greater",
                threshold=90.0,
                resolution_date="2025-07-01",
            ),
        )
        prompt = t.format_prompt(ctx)
        assert "above 90.0" in prompt
        assert "New York" in prompt

    def test_format_prompt_includes_system_context_when_present(self):
        t = LLMSynthesisTreatment()
        ctx = _make_context(system_context="TEST_SYSTEM_CONTEXT")
        prompt = t.format_prompt(ctx)
        assert "TEST_SYSTEM_CONTEXT" in prompt
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt


class TestEnsembleV2Integration:
    def test_format_prompt_includes_ensemble_section(self):
        t = EnsembleTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "ENSEMBLE" in prompt
        assert "bin_cal" in prompt
        assert "logistic_reg" in prompt
        assert "llm_synthesis" in prompt
        assert "buy_yes" in prompt

    def test_with_custom_weights(self):
        t = EnsembleTreatment(weights={"bin_cal": 0.5, "logistic_reg": 0.3, "llm_synthesis": 0.2})
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "0.5" in prompt
        assert "0.3" in prompt
        assert "0.2" in prompt
