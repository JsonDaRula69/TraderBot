"""Tests for simulation/adaptation.py — Bayesian adaptation data models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from traderbot.simulation.adaptation import (
    AdaptationConfig,
    AdaptationResult,
    MarketCategory,
    Posterior,
    Prior,
    StrategyAdjustment,
)

NOW = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)


class TestMarketCategory:
    def test_all_categories(self):
        expected = {"Politics", "Economics", "Science", "Sports", "Crypto", "Culture", "Tech", "Weather"}
        assert set(MarketCategory) == expected

    def test_str_enum_values(self):
        assert MarketCategory.POLITICS == "Politics"
        assert MarketCategory.ECONOMICS == "Economics"
        assert MarketCategory.CRYPTO == "Crypto"

    def test_from_string(self):
        assert MarketCategory("Sports") is MarketCategory.SPORTS


class TestPrior:
    def test_valid(self):
        p = Prior(category=MarketCategory.ECONOMICS, mean=0.5, variance=0.04, sample_count=10, last_updated=NOW)
        assert p.category is MarketCategory.ECONOMICS
        assert p.mean == 0.5
        assert p.variance == 0.04
        assert p.sample_count == 10

    def test_variance_must_be_positive(self):
        with pytest.raises(ValidationError):
            Prior(category=MarketCategory.POLITICS, mean=0.5, variance=0, sample_count=5, last_updated=NOW)
        with pytest.raises(ValidationError):
            Prior(category=MarketCategory.POLITICS, mean=0.5, variance=-0.1, sample_count=5, last_updated=NOW)

    def test_sample_count_non_negative(self):
        Prior(category=MarketCategory.TECH, mean=0.3, variance=0.1, sample_count=0, last_updated=NOW)
        with pytest.raises(ValidationError):
            Prior(category=MarketCategory.TECH, mean=0.3, variance=0.1, sample_count=-1, last_updated=NOW)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            Prior(category=MarketCategory.SPORTS, mean=0.5, variance=0.1, sample_count=3, last_updated=NOW, extra=42)

    def test_strict_mode_rejects_wrong_types(self):
        with pytest.raises(ValidationError):
            Prior(category="not_a_category", mean=0.5, variance=0.1, sample_count=3, last_updated=NOW)


class TestPosterior:
    def test_valid(self):
        p = Posterior(
            category=MarketCategory.SCIENCE,
            mean=0.5,
            variance=0.04,
            sample_count=12,
            last_updated=NOW,
            observations=[0.6, 0.55, 0.7],
            updated_mean=0.617,
            updated_variance=0.035,
        )
        assert p.observations == [0.6, 0.55, 0.7]
        assert p.updated_mean == 0.617
        assert p.updated_variance == 0.035

    def test_updated_variance_must_be_positive(self):
        with pytest.raises(ValidationError):
            Posterior(
                category=MarketCategory.CULTURE,
                mean=0.5,
                variance=0.04,
                sample_count=5,
                last_updated=NOW,
                observations=[],
                updated_mean=0.5,
                updated_variance=0,
            )

    def test_empty_observations(self):
        p = Posterior(
            category=MarketCategory.WEATHER,
            mean=0.5,
            variance=0.04,
            sample_count=0,
            last_updated=NOW,
            observations=[],
            updated_mean=0.5,
            updated_variance=0.04,
        )
        assert p.observations == []

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            Posterior(
                category=MarketCategory.CRYPTO,
                mean=0.5,
                variance=0.04,
                sample_count=5,
                last_updated=NOW,
                observations=[],
                updated_mean=0.5,
                updated_variance=0.03,
                surprise=0.1,
            )


class TestAdaptationConfig:
    def test_valid(self):
        c = AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0.6, decay_rate=0.05)
        assert c.learning_rate == 0.1
        assert c.min_observations == 10
        assert c.confidence_threshold == 0.6
        assert c.decay_rate == 0.05

    def test_learning_rate_bounds(self):
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0, min_observations=10, confidence_threshold=0.6, decay_rate=0.05)
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=1.1, min_observations=10, confidence_threshold=0.6, decay_rate=0.05)

    def test_learning_rate_one_is_valid(self):
        AdaptationConfig(learning_rate=1.0, min_observations=10, confidence_threshold=0.6, decay_rate=0.05)

    def test_min_observations_at_least_one(self):
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=0, confidence_threshold=0.6, decay_rate=0.05)

    def test_confidence_threshold_bounds(self):
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0, decay_rate=0.05)
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=1.1, decay_rate=0.05)

    def test_confidence_threshold_one_is_valid(self):
        AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=1.0, decay_rate=0.05)

    def test_decay_rate_bounds(self):
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0.6, decay_rate=0)
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0.6, decay_rate=1.1)

    def test_decay_rate_one_is_valid(self):
        AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0.6, decay_rate=1.0)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            AdaptationConfig(learning_rate=0.1, min_observations=10, confidence_threshold=0.6, decay_rate=0.05, bonus=True)


class TestAdaptationResult:
    def test_valid(self):
        r = AdaptationResult(
            category=MarketCategory.ECONOMICS,
            direction="increase",
            magnitude=0.05,
            confidence=0.8,
            reasoning="Statistical signals outperforming sentiment",
        )
        assert r.direction == "increase"
        assert r.magnitude == 0.05
        assert r.confidence == 0.8

    def test_all_directions(self):
        for d in ("increase", "decrease", "maintain"):
            AdaptationResult(
                category=MarketCategory.POLITICS, direction=d, magnitude=0.01, confidence=0.5, reasoning=f"test {d}"
            )

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.SPORTS, direction="grow", magnitude=0.01, confidence=0.5, reasoning="bad"
            )

    def test_magnitude_must_be_positive(self):
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.CRYPTO, direction="increase", magnitude=0, confidence=0.5, reasoning="zero"
            )
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.CRYPTO, direction="decrease", magnitude=-0.1, confidence=0.5, reasoning="neg"
            )

    def test_confidence_bounds(self):
        AdaptationResult(
            category=MarketCategory.TECH, direction="maintain", magnitude=0.01, confidence=0, reasoning="zero"
        )
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.TECH, direction="maintain", magnitude=0.01, confidence=-0.1, reasoning="neg"
            )
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.TECH, direction="maintain", magnitude=0.01, confidence=1.1, reasoning="over"
            )

    def test_confidence_one_is_valid(self):
        AdaptationResult(
            category=MarketCategory.WEATHER, direction="increase", magnitude=0.01, confidence=1.0, reasoning="certain"
        )

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            AdaptationResult(
                category=MarketCategory.SCIENCE,
                direction="maintain",
                magnitude=0.01,
                confidence=0.5,
                reasoning="test",
                bonus=True,
            )


class TestStrategyAdjustment:
    def test_valid(self):
        a = StrategyAdjustment(field_name="edge_threshold", old_value=0.2, new_value=0.25, justification="Win rate above expected", confidence=0.72)
        assert a.field_name == "edge_threshold"
        assert a.old_value == 0.2
        assert a.new_value == 0.25

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            StrategyAdjustment(field_name="x", old_value=0, new_value=1, justification="t", confidence=0)
        with pytest.raises(ValidationError):
            StrategyAdjustment(field_name="x", old_value=0, new_value=1, justification="t", confidence=1.1)

    def test_confidence_one_is_valid(self):
        StrategyAdjustment(field_name="x", old_value=0, new_value=1, justification="t", confidence=1.0)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            StrategyAdjustment(field_name="x", old_value=0, new_value=1, justification="t", confidence=0.5, extra="no")
