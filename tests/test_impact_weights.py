"""Tests for ImpactWeights model constraints and defaults."""

import pytest
from pydantic import ValidationError

from traderbot.news.impact_assessor import DEFAULT_IMPACT_WEIGHTS, ImpactWeights


class TestImpactWeightsDefaults:
    """Default ImpactWeights values sum to 1.0 and match DEFAULT_IMPACT_WEIGHTS."""

    def test_defaults_sum_to_one(self) -> None:
        w = ImpactWeights()
        total = w.direct_relevance + w.source_authority + w.recency + w.market_sensitivity + w.corroboration
        assert abs(total - 1.0) < 1e-6

    def test_default_impact_weights_matches(self) -> None:
        w = ImpactWeights()
        assert w.direct_relevance == DEFAULT_IMPACT_WEIGHTS.direct_relevance
        assert w.source_authority == DEFAULT_IMPACT_WEIGHTS.source_authority
        assert w.recency == DEFAULT_IMPACT_WEIGHTS.recency
        assert w.market_sensitivity == DEFAULT_IMPACT_WEIGHTS.market_sensitivity
        assert w.corroboration == DEFAULT_IMPACT_WEIGHTS.corroboration


class TestImpactWeightsSumValidation:
    """ImpactWeights rejects values that don't sum to 1.0."""

    def test_non_unit_sum_raises(self) -> None:
        with pytest.raises(ValidationError, match="Sum of impact weights must equal 1.0"):
            ImpactWeights(
                direct_relevance=0.5,
                source_authority=0.3,
                recency=0.1,
                market_sensitivity=0.05,
                corroboration=0.03,
            )

    def test_unit_sum_accepted(self) -> None:
        w = ImpactWeights(
            direct_relevance=0.4,
            source_authority=0.3,
            recency=0.15,
            market_sensitivity=0.1,
            corroboration=0.05,
        )
        assert abs(
            w.direct_relevance + w.source_authority + w.recency
            + w.market_sensitivity + w.corroboration - 1.0
        ) < 1e-6


class TestImpactWeightsFieldConstraints:
    """Individual field constraints: gt=0, lt=1."""

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImpactWeights(
                direct_relevance=0.0,
                source_authority=0.25,
                recency=0.2,
                market_sensitivity=0.2,
                corroboration=0.35,
            )

    def test_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImpactWeights(
                direct_relevance=1.0,
                source_authority=0.0,
                recency=0.0,
                market_sensitivity=0.0,
                corroboration=0.0,
            )

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImpactWeights(
                direct_relevance=-0.1,
                source_authority=0.35,
                recency=0.25,
                market_sensitivity=0.2,
                corroboration=0.3,
            )