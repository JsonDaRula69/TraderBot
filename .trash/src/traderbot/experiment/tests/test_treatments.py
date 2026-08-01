"""Tests for traderbot.experiment.treatments (control & calibration_bundle)."""

from datetime import datetime

from traderbot.experiment.shared import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    ValidatedDecision,
)
from traderbot.experiment.treatments.calibration_bundle import CalibrationBundleTreatment
from traderbot.experiment.treatments.control import ControlTreatment


def _make_ctx() -> TreatmentContext:
    market = MarketData(
        ticker="NYC-25C",
        strike_type="between",
        threshold=25.0,
        expiration=datetime(2025, 7, 1),
        category="NYC",
    )
    forecast = ForecastData(forecast_temp_f=78.0, source="GFS", days_before=3)
    accuracy = AccuracyData(brier_score=0.15, calibration_error=0.08, sample_size=50)
    prices = PriceData(current_yes_cents=55, current_no_cents=45, history=[50, 55], spread_cents=10)
    technical = TechnicalData(rsi=52.0, bb_upper=60.0, bb_lower=40.0, ema_short=53.0, ema_long=51.0)
    prior = PriorDecisions(decisions=[])
    return TreatmentContext(
        market=market,
        forecast=forecast,
        accuracy=accuracy,
        prices=prices,
        technical=technical,
        prior=prior,
    )


def test_control_treatment() -> None:
    """ControlTreatment: name='control', bypass_llm=True."""
    t = ControlTreatment()
    assert t.name == "control"
    assert t.bypass_llm is True


def test_calibration_bundle_treatment() -> None:
    """CalibrationBundleTreatment: name='calibration_bundle', bypass_llm=False."""
    t = CalibrationBundleTreatment()
    assert t.name == "calibration_bundle"
    assert t.bypass_llm is False


def test_calibration_validate_response() -> None:
    """validate_response: valid JSON -> ValidatedDecision, invalid -> ValueError."""
    t = CalibrationBundleTreatment()
    valid = t.validate_response(
        {
            "decision": "buy_yes",
            "estimated_prob": 0.7,
            "confidence": 0.6,
            "reasoning": "Looks good",
        }
    )
    assert isinstance(valid, ValidatedDecision)
    assert valid.decision == "buy_yes"

    try:
        t.validate_response(
            {
                "decision": "sell_everything",
                "estimated_prob": 0.7,
                "confidence": 0.6,
                "reasoning": "bad",
            }
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
