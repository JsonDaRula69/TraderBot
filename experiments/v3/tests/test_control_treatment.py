"""Tests for ControlTreatment — production-mirroring control that calls generate_signal()."""

from unittest.mock import MagicMock, patch

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(**overrides) -> TreatmentContext:
    """Build a TreatmentContext with sensible defaults for testing."""
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


def _mock_signal():
    """Return a CombinedSignal-like object matching production output shape."""
    mock = MagicMock()
    mock.ticker = "KXNYHI"
    mock.direction = "yes"
    mock.confidence = 0.7
    mock.estimated_prob = 0.65
    mock.edge_cents = 5
    mock.sources = [
        MagicMock(name="indicators", weight=0.3, direction="yes", strength=0.55),
        MagicMock(name="odds", weight=0.5, direction="yes", strength=0.45),
        MagicMock(name="momentum", weight=0.2, direction="yes", strength=0.4),
    ]
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestControlTreatmentName:
    def test_name_returns_control(self):
        t = ControlTreatment()
        assert t.name == "control"


class TestControlTreatmentFormatPrompt:
    """format_prompt calls generate_signal and includes production-style data."""

    def test_prompt_contains_ticker(self):
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "KXNYHI" in prompt

    def test_prompt_contains_signal_direction(self):
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "yes" in prompt.lower() or "no" in prompt.lower()

    def test_prompt_contains_technical_indicators(self):
        """Control prompt includes RSI, Bollinger, EMA data."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        # Technical indicators from ctx.technicals should appear
        assert str(int(ctx.technicals.rsi)) in prompt
        assert "RSI" in prompt or "rsi" in prompt.lower()

    def test_prompt_contains_market_details(self):
        """Control prompt includes market city, strike, threshold."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "New York" in prompt
        assert "90" in prompt

    def test_prompt_contains_prices_and_implied_prob(self):
        """Control prompt includes YES/NO prices and implied probability."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "0.65" in prompt  # yes_price as decimal
        assert "0.35" in prompt  # no_price
        assert "implied" in prompt.lower() or "probability" in prompt.lower()

    def test_prompt_contains_confidence(self):
        """Control prompt includes signal confidence from generate_signal."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "0.7" in prompt or "70" in prompt

    def test_prompt_excludes_forecast_temp(self):
        """Control prompt does NOT include forecast_temp_f."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "forecast_temp" not in prompt.lower()

    def test_prompt_excludes_accuracy_data(self):
        """Control prompt does NOT include mae or bias."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "mae" not in prompt.lower()
        assert "bias" not in prompt.lower()

    def test_prompt_excludes_bayesian(self):
        """Control prompt does NOT include Bayesian probability."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "bayesian" not in prompt.lower()

    def test_prompt_contains_ema(self):
        """Control prompt includes EMA5 and EMA20 from technicals."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        # EMA values from technicals context
        assert "EMA" in prompt or "ema" in prompt.lower()

    def test_prompt_contains_bollinger(self):
        """Control prompt includes Bollinger position from technicals."""
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", return_value=_mock_signal()):
            prompt = t.format_prompt(ctx)
        assert "bollinger" in prompt.lower() or "bb" in prompt.lower()


class TestControlTreatmentFallbackPrompt:
    """When generate_signal fails (e.g. ImportError), fallback prompt with market data."""

    def test_fallback_prompt_on_import_error(self):
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", side_effect=ImportError("no module")):
            prompt = t.format_prompt(ctx)
        # Should still contain market data
        assert "KXNYHI" in prompt
        assert "New York" in prompt

    def test_fallback_prompt_on_runtime_error(self):
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", side_effect=RuntimeError("broken")):
            prompt = t.format_prompt(ctx)
        assert "KXNYHI" in prompt
        assert "0.65" in prompt  # yes_price still shown

    def test_fallback_prompt_still_excludes_forecast(self):
        t = ControlTreatment()
        ctx = _make_context()
        with patch("experiments.treatments.control.generate_signal", side_effect=ImportError("no module")):
            prompt = t.format_prompt(ctx)
        assert "forecast_temp" not in prompt.lower()


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
        resp = {"decision": "skip", "estimated_prob": 1.0, "confidence": 0.3}
        assert t.validate_response(resp) is True
