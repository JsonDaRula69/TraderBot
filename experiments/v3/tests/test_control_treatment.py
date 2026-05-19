"""Tests for ControlTreatment — production-mirroring control with OpenClaw workspace context."""

from experiments.treatments.control import ControlTreatment
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
            strike_type="high",
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


class TestControlTreatmentName:
    def test_name_returns_control(self):
        t = ControlTreatment()
        assert t.name == "control"


class TestControlTreatmentFormatPrompt:
    def test_prompt_contains_ticker(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "KXNYHI" in prompt

    def test_prompt_contains_signal_direction(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "yes" in prompt.lower() or "no" in prompt.lower()

    def test_prompt_contains_technical_indicators(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert str(int(ctx.technicals.rsi)) in prompt
        assert "RSI" in prompt or "rsi" in prompt.lower()

    def test_prompt_contains_market_details(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "New York" in prompt
        assert "90" in prompt

    def test_prompt_contains_prices_and_implied_prob(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "0.65" in prompt
        assert "0.35" in prompt
        assert "implied" in prompt.lower() or "probability" in prompt.lower()

    def test_prompt_contains_confidence(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "0.7" in prompt or "0.70" in prompt

    def test_prompt_contains_forecast_data(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "88.5" in prompt
        assert "NWS" in prompt
        assert "Forecast" in prompt

    def test_prompt_contains_accuracy_data(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "2.5" in prompt
        assert "MAE" in prompt

    def test_prompt_contains_decision_instruction(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "decision" in prompt.lower()
        assert "buy_yes" in prompt
        assert "estimated_prob" in prompt

    def test_prompt_without_system_context(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" not in prompt

    def test_prompt_with_system_context(self):
        t = ControlTreatment()
        ctx = _make_context(system_context="You are a trading agent. Risk discipline: 5% max.")
        prompt = t.format_prompt(ctx)
        assert "PRODUCTION AGENT SYSTEM CONTEXT" in prompt
        assert "You are a trading agent" in prompt
        assert "END PRODUCTION AGENT SYSTEM CONTEXT" in prompt

    def test_prompt_system_context_includes_traderbot_tools(self):
        t = ControlTreatment()
        workspace_content = "traderbot scan --json\ntraderbot analyze TICKER --json"
        ctx = _make_context(system_context=workspace_content)
        prompt = t.format_prompt(ctx)
        assert "traderbot scan" in prompt


class TestControlTreatmentValidateResponse:
    def test_valid_buy_yes(self):
        t = ControlTreatment()
        resp = {"decision": "buy_yes", "estimated_prob": 0.7, "confidence": 0.8}
        assert t.validate_response(resp) is True

    def test_valid_buy_no(self):
        t = ControlTreatment()
        resp = {"decision": "buy_no", "estimated_prob": 0.4, "confidence": 0.6}
        assert t.validate_response(resp) is True

    def test_valid_skip(self):
        t = ControlTreatment()
        resp = {"decision": "skip", "estimated_prob": 0.5, "confidence": 0.3}
        assert t.validate_response(resp) is True

    def test_invalid_decision(self):
        t = ControlTreatment()
        resp = {"decision": "hold", "estimated_prob": 0.5, "confidence": 0.5}
        assert t.validate_response(resp) is False

    def test_prob_out_of_range_high(self):
        t = ControlTreatment()
        resp = {"decision": "buy_yes", "estimated_prob": 2.0, "confidence": 0.5}
        assert t.validate_response(resp) is False

    def test_prob_out_of_range_negative(self):
        t = ControlTreatment()
        resp = {"decision": "buy_yes", "estimated_prob": -0.1, "confidence": 0.5}
        assert t.validate_response(resp) is False

    def test_confidence_not_numeric(self):
        t = ControlTreatment()
        resp = {"decision": "buy_yes", "estimated_prob": 0.5, "confidence": "high"}
        assert t.validate_response(resp) is False

    def test_missing_decision_key(self):
        t = ControlTreatment()
        resp = {"estimated_prob": 0.5, "confidence": 0.5}
        assert t.validate_response(resp) is False

    def test_prob_boundary_zero(self):
        t = ControlTreatment()
        resp = {"decision": "skip", "estimated_prob": 0.0, "confidence": 0.3}
        assert t.validate_response(resp) is True

    def test_prob_boundary_one(self):
        t = ControlTreatment()
        resp = {"decision": "buy_yes", "estimated_prob": 1.0, "confidence": 0.3}
        assert t.validate_response(resp) is True


class TestControlTreatmentPriorDecisions:
    def test_prompt_shows_prior_decisions(self):
        t = ControlTreatment()
        ctx = _make_context(
            prior=PriorDecisions(decisions=[
                {"timestep": 0, "decision": "buy_yes", "estimated_prob": 0.65, "confidence": 0.7},
            ])
        )
        prompt = t.format_prompt(ctx)
        assert "Prior decisions" in prompt
        assert "buy_yes" in prompt

    def test_prompt_shows_no_prior_message(self):
        t = ControlTreatment()
        ctx = _make_context(prior=PriorDecisions(decisions=[]))
        prompt = t.format_prompt(ctx)
        assert "No prior decisions" in prompt


class TestControlTreatmentAccuracyLowConfidence:
    def test_low_confidence_flag_appears(self):
        t = ControlTreatment()
        ctx = _make_context(
            accuracy=AccuracyData(
                city="New York", lead_time=3, mae=5.0, bias=1.0,
                sample_count=10, low_confidence=True,
            )
        )
        prompt = t.format_prompt(ctx)
        assert "LOW CONFIDENCE" in prompt

    def test_normal_accuracy_no_warning(self):
        t = ControlTreatment()
        ctx = _make_context()
        prompt = t.format_prompt(ctx)
        assert "LOW CONFIDENCE" not in prompt
