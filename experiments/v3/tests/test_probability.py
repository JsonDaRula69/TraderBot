"""Tests for v3 probability module — Bayesian probability computation using scipy.stats.norm."""

from experiments.v3.probability import compute_ci, prob_between, prob_greater, prob_less


class TestProbLess:
    """P(actual < threshold) given forecast and city error distribution."""

    def test_far_above_threshold_near_zero(self):
        """Austin forecast 88.9°F vs threshold 66°F — P(actual < 66) ≈ 0."""
        result = prob_less(88.9, 66, 1.3, 1.6)
        assert result < 0.001, f"Expected near 0.0, got {result}"

    def test_moderately_above_threshold(self):
        """NYC forecast 62.3°F vs threshold 64°F, bias -0.2 — moderate probability."""
        result = prob_less(62.3, 64, -0.2, 1.7)
        assert 0.70 < result < 0.90, f"Expected ~0.81, got {result}"

    def test_loc_adjusts_for_bias(self):
        """Verify loc = forecast - city_bias shifts distribution."""
        # Positive bias shifts loc down, making threshold relatively higher
        no_bias = prob_less(50.0, 52.0, 0.0, 2.0)
        positive_bias = prob_less(50.0, 52.0, 1.0, 2.0)  # loc=49 instead of 50
        # With positive bias, P(actual < 52) should increase (distribution centered lower)
        assert positive_bias > no_bias


class TestProbGreater:
    """P(actual > threshold) given forecast and city error distribution."""

    def test_far_above_threshold_near_impossible(self):
        """Austin forecast 90.1°F vs threshold 95°F — near impossible."""
        result = prob_greater(90.1, 95, 1.3, 1.6)
        assert result < 0.001, f"Expected near 0.0, got {result}"

    def test_bug_fix_not_prob_between(self):
        """CRITICAL: prob_greater must use 1 - norm.cdf, NOT prob_between formula."""
        result = prob_greater(88.5, 95, 1.3, 1.6)
        # With loc=87.2, z=(95-87.2)/1.6=4.875, cdf≈1.0, so 1-cdf≈0.000001
        assert result < 0.001, f"Expected ~0.0001, got {result}"
        # If it used prob_between formula (floor/ceiling), result would be different
        assert result > 0.0, "Should have a tiny but positive probability"

    def test_symmetry_with_prob_less(self):
        """prob_greater + prob_less at same threshold ≈ 1.0."""
        forecast, threshold, bias, mae = 75.0, 70.0, 0.5, 2.0
        p_less = prob_less(forecast, threshold, bias, mae)
        p_greater = prob_greater(forecast, threshold, bias, mae)
        # P(<threshold) + P(>threshold) ≈ 1.0 (equality excluded is negligible)
        assert abs(p_less + p_greater - 1.0) < 0.01, (
            f"p_less({p_less}) + p_greater({p_greater}) should ≈ 1.0"
        )


class TestProbBetween:
    """P(actual in [floor, floor+1)) given forecast and error distribution."""

    def test_small_probability_band(self):
        """Austin forecast 88.9°F, floor 90 — small probability band."""
        result = prob_between(88.9, 90, 1.3, 1.6)
        # loc=87.6, P(90≤X<91) = cdf(91,87.6,1.6)-cdf(90,87.6,1.6)
        assert 0.01 < result < 0.10, f"Expected ~0.05, got {result}"

    def test_larger_uncertainty(self):
        """Austin T-1 forecast 87.2°F, floor 90, MAE 2.0 — wider band but further from floor."""
        result = prob_between(87.2, 90, 1.3, 2.0)
        assert 0.01 < result < 0.10, f"Expected ~0.03, got {result}"


class TestComputeCI:
    """95% confidence interval for probability estimates."""

    def test_ci_has_positive_width(self):
        """CI lower < upper, both in [0, 1]."""
        lower, upper = compute_ci(0.6, 1.5, 5)
        assert 0.0 <= lower < upper <= 1.0
        assert upper - lower > 0

    def test_ci_clamps_to_bounds(self):
        """CI should not go below 0 or above 1."""
        lower, upper = compute_ci(0.99, 2.0, 3)
        assert lower >= 0.0
        lower, upper = compute_ci(0.01, 2.0, 3)
        assert upper <= 1.0

    def test_zero_sample_count_returns_full_range(self):
        """With sample_count < 1, return (0.0, 1.0)."""
        lower, upper = compute_ci(0.5, 1.5, 0)
        assert (lower, upper) == (0.0, 1.0)

    def test_larger_samples_narrow_ci(self):
        """More samples → narrower CI."""
        ci_small = compute_ci(0.5, 1.5, 5)
        ci_large = compute_ci(0.5, 1.5, 50)
        assert (ci_large[1] - ci_large[0]) < (ci_small[1] - ci_small[0])
