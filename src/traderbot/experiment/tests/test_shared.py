"""Tests for traderbot.experiment.shared."""

import dataclasses
from datetime import datetime

import pytest

from traderbot.experiment.shared import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    TreatmentInterface,
    ValidatedDecision,
)


def _make_ctx() -> TreatmentContext:
    """Build a minimal TreatmentContext for tests."""
    market = MarketData(
        ticker="NYC-25C",
        strike_type="between",
        threshold=25.0,
        expiration=datetime(2025, 7, 1),
        category="NYC",
    )
    forecast = ForecastData(forecast_temp_f=78.0, source="GFS", days_before=3)
    accuracy = AccuracyData(brier_score=None, calibration_error=None, sample_size=0)
    prices = PriceData(current_yes_cents=55, current_no_cents=45, history=[55], spread_cents=10)
    technical = TechnicalData(rsi=None, bb_upper=None, bb_lower=None, ema_short=None, ema_long=None)
    prior = PriorDecisions(decisions=[])
    return TreatmentContext(
        market=market,
        forecast=forecast,
        accuracy=accuracy,
        prices=prices,
        technical=technical,
        prior=prior,
    )


def test_treatment_context_frozen() -> None:
    """TreatmentContext is frozen — attribute mutation must raise FrozenInstanceError."""
    ctx = _make_ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.system_context = "mutated"


def test_validated_decision_accepts_valid() -> None:
    """ValidatedDecision should accept all 3 valid decision types."""
    for decision_type in ("buy_yes", "buy_no", "skip"):
        vd = ValidatedDecision(
            decision=decision_type,
            estimated_prob=0.5,
            confidence=0.5,
            reasoning="test",
        )
        assert vd.decision == decision_type


def test_validated_decision_rejects_bad_decision() -> None:
    """ValidatedDecision must reject invalid decision values."""
    with pytest.raises(ValueError, match="decision must be"):
        ValidatedDecision(decision="sell", estimated_prob=0.5, confidence=0.5, reasoning="bad")


def test_validated_decision_rejects_bad_prob() -> None:
    """ValidatedDecision must reject estimated_prob outside [0, 1]."""
    with pytest.raises(ValueError, match="estimated_prob"):
        ValidatedDecision(decision="skip", estimated_prob=1.5, confidence=0.5, reasoning="bad")


def test_treatment_interface_is_abc() -> None:
    """TreatmentInterface is abstract — cannot instantiate directly."""
    with pytest.raises(TypeError):
        TreatmentInterface()