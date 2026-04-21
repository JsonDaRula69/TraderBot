"""Tests for risk/sizing.py — Kelly criterion position sizing."""

from __future__ import annotations

from traderbot.risk.sizing import (
    confidence_scaled_size,
    fractional_kelly,
    kelly_criterion,
    sized_position_for_trade,
)


class TestKellyCriterion:
    def test_known_value(self):
        result = kelly_criterion(0.6, 1.5)
        expected = (1.5 * 0.6 - 0.4) / 1.5
        assert abs(result - expected) < 1e-10

    def test_zero_prob(self):
        assert kelly_criterion(0.0, 1.5) == 0.0

    def test_one_prob(self):
        assert kelly_criterion(1.0, 1.5) == 0.0

    def test_zero_odds(self):
        assert kelly_criterion(0.6, 0.0) == 0.0

    def test_negative_kelly_returns_zero(self):
        assert kelly_criterion(0.3, 1.5) == 0.0

    def test_symmetric_fifty_fifty(self):
        result = kelly_criterion(0.5, 1.0)
        assert result == 0.0


class TestFractionalKelly:
    def test_default_half_kelly(self):
        full = kelly_criterion(0.6, 1.5)
        half = fractional_kelly(0.6, 1.5)
        assert abs(half - full * 0.5) < 1e-10

    def test_fraction_clamped_low(self):
        result = fractional_kelly(0.6, 1.5, fraction=0.05)
        full = kelly_criterion(0.6, 1.5)
        assert abs(result - full * 0.1) < 1e-10

    def test_fraction_clamped_high(self):
        result = fractional_kelly(0.6, 1.5, fraction=0.8)
        full = kelly_criterion(0.6, 1.5)
        assert abs(result - full * 0.5) < 1e-10

    def test_negative_kelly_returns_zero(self):
        assert fractional_kelly(0.3, 1.5) == 0.0

    def test_custom_fraction(self):
        full = kelly_criterion(0.6, 1.5)
        result = fractional_kelly(0.6, 1.5, fraction=0.25)
        assert abs(result - full * 0.25) < 1e-10


class TestConfidenceScaledSize:
    def test_typical_values(self):
        kelly_frac = fractional_kelly(0.6, 1.5)
        result = confidence_scaled_size(kelly_frac, 0.8, 100_000_00)
        expected = int(kelly_frac * 0.8 * 100_000_00)
        assert result == expected

    def test_zero_bankroll(self):
        assert confidence_scaled_size(0.1, 0.8, 0) == 0

    def test_negative_bankroll(self):
        assert confidence_scaled_size(0.1, 0.8, -1000) == 0

    def test_zero_kelly(self):
        assert confidence_scaled_size(0.0, 0.8, 100_000_00) == 0

    def test_negative_kelly(self):
        assert confidence_scaled_size(-0.1, 0.8, 100_000_00) == 0

    def test_zero_confidence(self):
        assert confidence_scaled_size(0.1, 0.0, 100_000_00) == 0

    def test_confidence_clamped_above_one(self):
        kelly_frac = 0.1
        result = confidence_scaled_size(kelly_frac, 1.5, 100_000_00)
        expected = int(kelly_frac * 1.0 * 100_000_00)
        assert result == expected

    def test_confidence_clamped_negative(self):
        kelly_frac = 0.1
        result = confidence_scaled_size(kelly_frac, -0.5, 100_000_00)
        assert result == 0


class TestSizedPositionForTrade:
    def test_caps_at_max_position(self):
        result = sized_position_for_trade(0.6, 1.5, 0.9, 100_000_00, 100_00)
        assert result <= 100_00

    def test_full_pipeline(self):
        fk = fractional_kelly(0.6, 1.5, 0.5)
        expected_unclamped = confidence_scaled_size(fk, 0.8, 100_000_00)
        max_pos = 1_000_000_00
        result = sized_position_for_trade(0.6, 1.5, 0.8, 100_000_00, max_pos)
        assert result == expected_unclamped

    def test_no_edge_returns_zero(self):
        assert sized_position_for_trade(0.3, 1.5, 0.8, 100_000_00, 500_00) == 0

    def test_zero_confidence(self):
        assert sized_position_for_trade(0.6, 1.5, 0.0, 100_000_00, 500_00) == 0
