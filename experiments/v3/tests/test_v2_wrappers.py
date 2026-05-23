"""Tests for V2 treatment wrappers — instantiation and basic delegation."""

from __future__ import annotations

from experiments.v3.treatment_interface import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
)


def _make_ctx(**overrides: float | str | int) -> TreatmentContext:
    defaults = {
        "market": MarketData(
            ticker="KXHIGHNY_25_32",
            city="New York",
            strike_type="greater",
            threshold=80.0,
            resolution_date="2024-07-15",
        ),
        "forecast": ForecastData(
            forecast_temp_f=85.0,
            source="test",
            days_before=5,
            timestep=6,
        ),
        "accuracy": AccuracyData(
            city="New York",
            lead_time=5,
            mae=3.0,
            bias=0.5,
            sample_count=100,
        ),
        "prices": PriceData(
            yes_price=0.6,
            no_price=0.4,
            trade_count=50,
            open_interest=200,
            implied_prob=0.6,
        ),
        "technicals": TechnicalData(
            rsi=55.0,
            bollinger_position=0.5,
            ema5=0.6,
            ema20=0.55,
            signal_direction="bullish",
            signal_confidence=0.7,
        ),
        "prior": PriorDecisions(decisions=[]),
        "timestep": 6,
        "remaining": 4,
    }
    for k, v in overrides.items():
        if isinstance(defaults.get(k), object):
            object.__setattr__(defaults[k], k, v)
    return TreatmentContext(**defaults)


class TestV2BinCalInstantiation:
    def test_instantiates_with_default_db_path(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        treatment = V2BinCalTreatment()
        assert treatment.name == "v2_bin_cal"

    def test_format_prompt_returns_string(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        treatment = V2BinCalTreatment()
        ctx = _make_ctx()
        prompt = treatment.format_prompt(ctx)
        assert isinstance(prompt, str)
        assert "BinCal" in prompt

    def test_validate_response_always_true(self):
        from experiments.treatments.v2_bin_cal import V2BinCalTreatment
        treatment = V2BinCalTreatment()
        assert treatment.validate_response("anything") is True
        assert treatment.validate_response({}) is True


class TestV2LogisticRegInstantiation:
    def test_instantiates_with_default_db_path(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        treatment = V2LogisticRegTreatment()
        assert treatment.name == "v2_logistic_reg"

    def test_format_prompt_returns_string(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        treatment = V2LogisticRegTreatment()
        ctx = _make_ctx()
        prompt = treatment.format_prompt(ctx)
        assert isinstance(prompt, str)
        assert "LogisticReg" in prompt

    def test_validate_response_always_true(self):
        from experiments.treatments.v2_logistic_reg import V2LogisticRegTreatment
        treatment = V2LogisticRegTreatment()
        assert treatment.validate_response("anything") is True


class TestV2LlmSynthesisInstantiation:
    def test_instantiates_with_default_db_path(self):
        from experiments.treatments.v2_llm_synthesis import V2LlmSynthesisTreatment
        treatment = V2LlmSynthesisTreatment()
        assert treatment.name == "v2_llm_synthesis"

    def test_format_prompt_returns_string(self):
        from experiments.treatments.v2_llm_synthesis import V2LlmSynthesisTreatment
        treatment = V2LlmSynthesisTreatment()
        ctx = _make_ctx()
        prompt = treatment.format_prompt(ctx)
        assert isinstance(prompt, str)
        assert "LLM Synthesis" in prompt

    def test_validate_response_always_true(self):
        from experiments.treatments.v2_llm_synthesis import V2LlmSynthesisTreatment
        treatment = V2LlmSynthesisTreatment()
        assert treatment.validate_response("anything") is True


class TestV2EnsembleInstantiation:
    def test_instantiates_with_default_db_path(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        treatment = V2EnsembleTreatment()
        assert treatment.name == "v2_ensemble"

    def test_format_prompt_returns_string(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        treatment = V2EnsembleTreatment()
        ctx = _make_ctx()
        prompt = treatment.format_prompt(ctx)
        assert isinstance(prompt, str)
        assert "Ensemble" in prompt

    def test_validate_response_always_true(self):
        from experiments.treatments.v2_ensemble import V2EnsembleTreatment
        treatment = V2EnsembleTreatment()
        assert treatment.validate_response("anything") is True


class TestContextTranslation:
    """Verify _context_to_forecast produces correct V2 dict keys."""

    def test_forecast_dict_has_required_keys(self):
        from experiments.treatments.v2_bin_cal import _context_to_forecast
        ctx = _make_ctx()
        forecast = _context_to_forecast(ctx)
        for key in ("temp_max_f", "temp_min_f", "humidity_max_pct",
                     "wind_speed_max_kmh", "precip_mm", "weather_code",
                     "forecast_date", "source", "days_before", "timestep"):
            assert key in forecast, f"Missing key: {key}"

    def test_forecast_dict_dummy_defaults(self):
        from experiments.treatments.v2_bin_cal import _context_to_forecast
        ctx = _make_ctx()
        forecast = _context_to_forecast(ctx)
        assert forecast["temp_min_f"] == ctx.forecast.forecast_temp_f - 15
        assert forecast["humidity_max_pct"] == 50
        assert forecast["wind_speed_max_kmh"] == 10
        assert forecast["precip_mm"] == 0
        assert forecast["weather_code"] == 0


class TestDecisionLogic:
    """Verify _result_to_response decision threshold logic."""

    def test_buy_yes_when_estimated_prob_above_threshold(self):
        from experiments.treatments.v2_bin_cal import _result_to_response
        from experiments.v2.methodologies.base import MethodologyResult
        result = MethodologyResult(estimated_prob=0.75, confidence=0.8)
        response = _result_to_response(result, yes_price=0.6)
        assert response.decision == "buy_yes"
        assert response.estimated_prob == 0.75

    def test_buy_no_when_estimated_prob_below_threshold(self):
        from experiments.treatments.v2_bin_cal import _result_to_response
        from experiments.v2.methodologies.base import MethodologyResult
        result = MethodologyResult(estimated_prob=0.3, confidence=0.7)
        response = _result_to_response(result, yes_price=0.6)
        assert response.decision == "buy_no"

    def test_skip_when_within_threshold(self):
        from experiments.treatments.v2_bin_cal import _result_to_response
        from experiments.v2.methodologies.base import MethodologyResult
        result = MethodologyResult(estimated_prob=0.62, confidence=0.5)
        response = _result_to_response(result, yes_price=0.6)
        assert response.decision == "skip"