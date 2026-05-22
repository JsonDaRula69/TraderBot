"""Tests for all 5 treatments: control, bin_cal, logistic_reg, llm_synthesis, ensemble."""

from experiments.treatments.bin_cal import BinCalTreatment, compute_delta as bin_cal_compute_delta
from experiments.treatments.control import ControlTreatment
from experiments.treatments.ensemble import EnsembleTreatment
from experiments.treatments.llm_synthesis import LLMSynthesisTreatment
from experiments.treatments.logistic_reg import LogisticRegTreatment
from experiments.v3.treatment_interface import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
)


def _make_context(**overrides) -> TreatmentContext:
    defaults = dict(
        market=MarketData(
            ticker="KXNYHI",
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


def _make_less_context(**overrides) -> TreatmentContext:
    defaults = dict(
        market=MarketData(
            ticker="KXNYLO",
            city="Chicago",
            strike_type="less",
            threshold=32.0,
            resolution_date="2025-01-15",
        ),
        forecast=ForecastData(
            forecast_temp_f=28.0,
            source="NWS",
            days_before=3,
            timestep=1,
        ),
        accuracy=AccuracyData(
            city="Chicago",
            lead_time=3,
            mae=3.0,
            bias=-0.5,
            sample_count=80,
        ),
        prices=PriceData(
            yes_price=0.70,
            no_price=0.30,
            trade_count=200,
            open_interest=600,
            implied_prob=0.70,
        ),
        technicals=TechnicalData(
            rsi=35.0,
            bollinger_position=0.40,
            ema5=32.0,
            ema20=34.0,
            signal_direction="yes",
            signal_confidence=0.6,
        ),
        prior=PriorDecisions(decisions=[]),
        timestep=1,
        remaining=3,
    )
    defaults.update(overrides)
    return TreatmentContext(**defaults)


def _make_between_context(**overrides) -> TreatmentContext:
    defaults = dict(
        market=MarketData(
            ticker="KXNYBTW",
            city="Boston",
            strike_type="between",
            threshold=65.0,
            resolution_date="2025-06-01",
            floor_strike=60.0,
            ceiling_strike=70.0,
        ),
        forecast=ForecastData(
            forecast_temp_f=63.0,
            source="NWS",
            days_before=3,
            timestep=1,
        ),
        accuracy=AccuracyData(
            city="Boston",
            lead_time=3,
            mae=2.0,
            bias=0.2,
            sample_count=60,
        ),
        prices=PriceData(
            yes_price=0.45,
            no_price=0.55,
            trade_count=100,
            open_interest=300,
            implied_prob=0.45,
        ),
        technicals=TechnicalData(
            rsi=50.0,
            bollinger_position=0.50,
            ema5=64.0,
            ema20=63.0,
            signal_direction="no",
            signal_confidence=0.5,
        ),
        prior=PriorDecisions(decisions=[]),
        timestep=1,
        remaining=3,
    )
    defaults.update(overrides)
    return TreatmentContext(**defaults)


# === BinCalTreatment ===

class TestBinCalName:
    def test_name(self):
        assert BinCalTreatment().name == "bin_cal"


class TestBinCalComputeDelta:
    def test_greater_strike(self):
        ctx = _make_context()
        delta = bin_cal_compute_delta(ctx)
        assert delta == pytest.approx(88.5 - 90.0)

    def test_less_strike(self):
        ctx = _make_less_context()
        delta = bin_cal_compute_delta(ctx)
        assert delta == pytest.approx(32.0 - 28.0)

    def test_between_strike_closer_to_floor(self):
        ctx = _make_between_context()
        delta = bin_cal_compute_delta(ctx)
        assert delta == pytest.approx(-(63.0 - 60.0))

    def test_between_strike_closer_to_ceiling(self):
        ctx = _make_between_context(
            forecast=ForecastData(forecast_temp_f=68.0, source="NWS", days_before=3, timestep=1)
        )
        delta = bin_cal_compute_delta(ctx)
        assert delta == pytest.approx(70.0 - 68.0)


class TestBinCalFormatPrompt:
    def test_contains_market_data(self):
        t = BinCalTreatment()
        prompt = t.format_prompt(_make_context())
        assert "KXNYHI" in prompt
        assert "New York" in prompt

    def test_contains_forecast(self):
        t = BinCalTreatment()
        prompt = t.format_prompt(_make_context())
        assert "88.5" in prompt
        assert "NWS" in prompt

    def test_contains_bin_calibration_section(self):
        t = BinCalTreatment()
        prompt = t.format_prompt(_make_context())
        assert "BIN CALIBRATION" in prompt
        assert "Forecast delta" in prompt
        assert "Delta bin" in prompt

    def test_contains_decision_instruction(self):
        t = BinCalTreatment()
        prompt = t.format_prompt(_make_context())
        assert "buy_yes" in prompt
        assert "estimated_prob" in prompt

    def test_default_calibration_shows_uniform_prior(self):
        t = BinCalTreatment()
        prompt = t.format_prompt(_make_context())
        assert "uniform" in prompt.lower()
        assert "0.5000" in prompt

    def test_with_calibration_data(self):
        cal_data = {"count": 50, "actual_rate": 0.72}
        t = BinCalTreatment(calibration_data=cal_data)
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "calibrated" in prompt.lower()
        assert "0.7200" in prompt

    def test_low_sample_calibration_shows_uniform(self):
        cal_data = {"count": 5, "actual_rate": 0.6}
        t = BinCalTreatment(calibration_data=cal_data)
        prompt = t.format_prompt(_make_context())
        assert "uniform" in prompt.lower()

    def test_with_system_context(self):
        t = BinCalTreatment()
        ctx = _make_context(system_context="Agent rules here")
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt


class TestBinCalValidateResponse:
    def test_valid_buy_yes(self):
        t = BinCalTreatment()
        assert t.validate_response({"decision": "buy_yes", "estimated_prob": 0.7, "confidence": 0.8})

    def test_valid_skip(self):
        t = BinCalTreatment()
        assert t.validate_response({"decision": "skip", "estimated_prob": 0.5, "confidence": 0.3})

    def test_invalid_decision(self):
        t = BinCalTreatment()
        assert not t.validate_response({"decision": "hold", "estimated_prob": 0.5, "confidence": 0.5})

    def test_prob_out_of_range(self):
        t = BinCalTreatment()
        assert not t.validate_response({"decision": "buy_yes", "estimated_prob": 1.5, "confidence": 0.5})

    def test_confidence_string(self):
        t = BinCalTreatment()
        assert not t.validate_response({"decision": "buy_yes", "estimated_prob": 0.5, "confidence": "high"})


# === LogisticRegTreatment ===

class TestLogisticRegName:
    def test_name(self):
        assert LogisticRegTreatment().name == "logistic_reg"


class TestLogisticRegFormatPrompt:
    def test_contains_market_data(self):
        t = LogisticRegTreatment()
        prompt = t.format_prompt(_make_context())
        assert "KXNYHI" in prompt
        assert "New York" in prompt

    def test_contains_logistic_section(self):
        t = LogisticRegTreatment()
        prompt = t.format_prompt(_make_context())
        assert "LOGISTIC REGRESSION" in prompt
        assert "Forecast delta" in prompt

    def test_contains_probability_estimate(self):
        t = LogisticRegTreatment()
        prompt = t.format_prompt(_make_context())
        assert "probability estimate" in prompt.lower()

    def test_contains_decision_instruction(self):
        t = LogisticRegTreatment()
        prompt = t.format_prompt(_make_context())
        assert "buy_yes" in prompt
        assert "estimated_prob" in prompt

    def test_heuristic_mode_note(self):
        t = LogisticRegTreatment()
        prompt = t.format_prompt(_make_context())
        assert "delta-based heuristic" in prompt.lower()

    def test_with_weights(self):
        weights = {"forecast_delta": 0.3, "forecast_delta_squared": -0.01, "timestep": 0.05}
        t = LogisticRegTreatment(weights=weights, intercept=-0.5)
        prompt = t.format_prompt(_make_context())
        assert "provided_weights" in prompt

    def test_with_system_context(self):
        t = LogisticRegTreatment()
        ctx = _make_context(system_context="Agent context")
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt

    def test_accuracy_shows_low_confidence(self):
        t = LogisticRegTreatment()
        ctx = _make_context(accuracy=AccuracyData(
            city="New York", lead_time=3, mae=2.5, bias=0.3, sample_count=5, low_confidence=True
        ))
        prompt = t.format_prompt(ctx)
        assert "LOW CONFIDENCE" in prompt


class TestLogisticRegValidateResponse:
    def test_valid_buy_no(self):
        t = LogisticRegTreatment()
        assert t.validate_response({"decision": "buy_no", "estimated_prob": 0.4, "confidence": 0.6})

    def test_invalid_prob_negative(self):
        t = LogisticRegTreatment()
        assert not t.validate_response({"decision": "buy_yes", "estimated_prob": -0.1, "confidence": 0.5})

    def test_prob_boundary_zero(self):
        t = LogisticRegTreatment()
        assert t.validate_response({"decision": "skip", "estimated_prob": 0.0, "confidence": 0.3})


# === LLMSynthesisTreatment ===

class TestLLMSynthesisName:
    def test_name(self):
        assert LLMSynthesisTreatment().name == "llm_synthesis"


class TestLLMSynthesisFormatPrompt:
    def test_contains_market_data(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "New York" in prompt
        assert "90.0" in prompt

    def test_contains_weather_analyst_prompt(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "weather market analyst" in prompt.lower()

    def test_asks_llm_to_estimate(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "estimate" in prompt.lower() or "Estimate" in prompt

    def test_contains_json_output_format(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "estimated_prob" in prompt
        assert "confidence" in prompt
        assert "reasoning" in prompt

    def test_mentions_threshold(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "Threshold" in prompt

    def test_with_system_context(self):
        t = LLMSynthesisTreatment()
        ctx = _make_context(system_context="You are a trading agent")
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt

    def test_forecast_details_in_prompt(self):
        t = LLMSynthesisTreatment()
        prompt = t.format_prompt(_make_context())
        assert "Forecast" in prompt
        assert "High temp" in prompt


class TestLLMSynthesisValidateResponse:
    def test_valid_buy_yes(self):
        t = LLMSynthesisTreatment()
        assert t.validate_response({"decision": "buy_yes", "estimated_prob": 0.7, "confidence": 0.8})

    def test_prob_boundary_one(self):
        t = LLMSynthesisTreatment()
        assert t.validate_response({"decision": "buy_yes", "estimated_prob": 1.0, "confidence": 0.3})

    def test_missing_decision(self):
        t = LLMSynthesisTreatment()
        assert not t.validate_response({"estimated_prob": 0.5, "confidence": 0.5})


# === EnsembleTreatment ===

class TestEnsembleName:
    def test_name(self):
        assert EnsembleTreatment().name == "ensemble"


class TestEnsembleFormatPrompt:
    def test_contains_market_data(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "KXNYHI" in prompt
        assert "New York" in prompt

    def test_contains_ensemble_section(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "ENSEMBLE METHODOLOGY" in prompt

    def test_contains_individual_estimates(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "bin_cal" in prompt
        assert "logistic_reg" in prompt
        assert "llm_synthesis" in prompt

    def test_contains_default_weights(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "0.3" in prompt
        assert "0.4" in prompt

    def test_contains_weighted_estimate(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "weighted probability" in prompt.lower() or "Ensemble weighted" in prompt

    def test_contains_decision_instruction(self):
        t = EnsembleTreatment()
        prompt = t.format_prompt(_make_context())
        assert "buy_yes" in prompt
        assert "estimated_prob" in prompt

    def test_custom_weights(self):
        weights = {"bin_cal": 0.5, "logistic_reg": 0.3, "llm_synthesis": 0.2}
        t = EnsembleTreatment(weights=weights)
        prompt = t.format_prompt(_make_context())
        assert "0.5" in prompt

    def test_with_calibration_data(self):
        cal_data = {"count": 50, "actual_rate": 0.72}
        t = EnsembleTreatment(bin_cal_data=cal_data)
        prompt = t.format_prompt(_make_context())
        assert "✓" in prompt

    def test_with_system_context(self):
        t = EnsembleTreatment()
        ctx = _make_context(system_context="Agent rules")
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt

    def test_low_confidence_warning(self):
        t = EnsembleTreatment()
        ctx = _make_context(accuracy=AccuracyData(
            city="New York", lead_time=3, mae=2.5, bias=0.3, sample_count=5, low_confidence=True
        ))
        prompt = t.format_prompt(ctx)
        assert "LOW CONFIDENCE" in prompt


class TestEnsembleValidateResponse:
    def test_valid_buy_yes(self):
        t = EnsembleTreatment()
        assert t.validate_response({"decision": "buy_yes", "estimated_prob": 0.7, "confidence": 0.8})

    def test_valid_skip(self):
        t = EnsembleTreatment()
        assert t.validate_response({"decision": "skip", "estimated_prob": 0.5, "confidence": 0.3})

    def test_invalid_decision(self):
        t = EnsembleTreatment()
        assert not t.validate_response({"decision": "hold", "estimated_prob": 0.5, "confidence": 0.5})

    def test_prob_out_of_range(self):
        t = EnsembleTreatment()
        assert not t.validate_response({"decision": "buy_yes", "estimated_prob": -0.1, "confidence": 0.5})


# === __init__.py exports ===

class TestTreatmentsInit:
    def test_all_treatments_importable(self):
        from experiments.treatments import (
            BinCalTreatment,
            ControlTreatment,
            EnsembleTreatment,
            LLMSynthesisTreatment,
            LogisticRegTreatment,
        )
        assert ControlTreatment.name.fget(ControlTreatment()) == "control"
        assert BinCalTreatment.name.fget(BinCalTreatment()) == "bin_cal"
        assert LogisticRegTreatment.name.fget(LogisticRegTreatment()) == "logistic_reg"
        assert LLMSynthesisTreatment.name.fget(LLMSynthesisTreatment()) == "llm_synthesis"
        assert EnsembleTreatment.name.fget(EnsembleTreatment()) == "ensemble"

    def test_all_in___all__(self):
        from experiments import treatments
        assert "ControlTreatment" in treatments.__all__
        assert "BinCalTreatment" in treatments.__all__
        assert "LogisticRegTreatment" in treatments.__all__
        assert "LLMSynthesisTreatment" in treatments.__all__
        assert "EnsembleTreatment" in treatments.__all__

    def test_treatment_count(self):
        from experiments import treatments
        assert len(treatments.__all__) == 5


import pytest