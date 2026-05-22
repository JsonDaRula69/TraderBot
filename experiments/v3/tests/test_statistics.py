"""Tests for statistics.py — paired t-tests, Cohen's d, confidence intervals, treatment comparison."""

import numpy as np
import pytest
from scipy import stats

from experiments.v3.statistics import (
    cohens_d,
    compare_treatments,
    confidence_interval,
    paired_t_test,
)

# ---------------------------------------------------------------------------
# paired_t_test
# ---------------------------------------------------------------------------


class TestPairedTTest:
    """Verify paired_t_test matches scipy.stats.ttest_rel."""

    TREATMENT = [10, 5, -3, 8, 2]
    CONTROL = [2, -1, -5, 1, -3]

    def test_delta_values(self):
        """Mean delta should be mean(treatment - control)."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        expected_delta = float(np.mean(np.array(self.TREATMENT) - np.array(self.CONTROL)))
        assert result["mean_delta"] == pytest.approx(expected_delta, rel=1e-10)

    def test_n_value(self):
        """n should equal the length of the input lists."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        assert result["n"] == 5

    def test_t_statistic_matches_scipy(self):
        """t_statistic should match scipy.stats.ttest_rel exactly."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        scipy_result = stats.ttest_rel(self.TREATMENT, self.CONTROL)
        assert result["t_statistic"] == pytest.approx(float(scipy_result.statistic), rel=1e-10)

    def test_p_value_matches_scipy(self):
        """p_value should match scipy.stats.ttest_rel exactly."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        scipy_result = stats.ttest_rel(self.TREATMENT, self.CONTROL)
        assert result["p_value"] == pytest.approx(float(scipy_result.pvalue), rel=1e-10)

    def test_expected_approximate_values(self):
        """delta=[8,6,2,7,5], mean=5.6, t≈5.44 (scipy), p<0.01."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        assert result["mean_delta"] == pytest.approx(5.6, rel=1e-10)
        assert result["t_statistic"] == pytest.approx(5.44, abs=0.01)
        assert result["p_value"] < 0.01

    def test_output_keys(self):
        """Output dict must contain t_statistic, p_value, mean_delta, n."""
        result = paired_t_test(self.TREATMENT, self.CONTROL)
        assert set(result.keys()) == {"t_statistic", "p_value", "mean_delta", "n"}


# ---------------------------------------------------------------------------
# cohens_d
# ---------------------------------------------------------------------------


class TestCohensD:
    """Verify Cohen's d for paired samples."""

    TREATMENT = [10, 5, -3, 8, 2]
    CONTROL = [2, -1, -5, 1, -3]

    def test_paired_cohens_d_value(self):
        """d = mean(diffs)/sd(diffs). For our data, d ≈ 2.6."""
        d = cohens_d(self.TREATMENT, self.CONTROL)
        diffs = np.array(self.TREATMENT) - np.array(self.CONTROL)
        expected = float(np.mean(diffs) / np.std(diffs, ddof=1))
        assert d == pytest.approx(expected, rel=1e-10)

    def test_cohens_d_magnitude(self):
        """Large effect size: |d| should be > 2 for this data."""
        d = cohens_d(self.TREATMENT, self.CONTROL)
        assert abs(d) > 2.0

    def test_identical_data_returns_zero(self):
        """Identical treatment and control → d = 0.0."""
        same = [5.0, 3.0, 7.0, 2.0]
        assert cohens_d(same, same) == 0.0

    def test_zero_sd_returns_zero(self):
        """Constant differences (all same) → sd=0 → return 0.0 (avoid div/0)."""
        treatment = [5, 5, 5]
        control = [3, 3, 3]
        assert cohens_d(treatment, control) == 0.0


# ---------------------------------------------------------------------------
# confidence_interval
# ---------------------------------------------------------------------------


class TestConfidenceInterval:
    """Verify confidence intervals for mean delta."""

    DELTAS = [8, 6, 2, 7, 5]  # treatment - control from above

    def test_ci_contains_mean(self):
        """95% CI must contain the sample mean."""
        result = confidence_interval(self.DELTAS)
        mean_delta = float(np.mean(self.DELTAS))
        assert result["lower"] <= mean_delta <= result["upper"]

    def test_ci_mean_matches_sample(self):
        """Reported mean should equal sample mean."""
        result = confidence_interval(self.DELTAS)
        assert result["mean"] == pytest.approx(float(np.mean(self.DELTAS)), rel=1e-10)

    def test_ci_n_matches(self):
        """Reported n should equal input length."""
        result = confidence_interval(self.DELTAS)
        assert result["n"] == 5

    def test_ci_matches_scipy(self):
        """CI bounds should match scipy.stats.t.interval."""
        mean = float(np.mean(self.DELTAS))
        sem = float(stats.sem(self.DELTAS))
        ci = stats.t.interval(0.95, df=len(self.DELTAS) - 1, loc=mean, scale=sem)
        result = confidence_interval(self.DELTAS, confidence=0.95)
        assert result["lower"] == pytest.approx(float(ci[0]), rel=1e-10)
        assert result["upper"] == pytest.approx(float(ci[1]), rel=1e-10)

    def test_single_value_returns_zero_n(self):
        """Single value: not enough data for CI, returns n=0, lower=upper=0."""
        result = confidence_interval([5.0])
        assert result["n"] == 0
        assert result["lower"] == 0.0
        assert result["upper"] == 0.0

    def test_empty_list_returns_zero_n(self):
        """Empty list: returns n=0, lower=upper=0."""
        result = confidence_interval([])
        assert result["n"] == 0
        assert result["lower"] == 0.0
        assert result["upper"] == 0.0

    def test_custom_confidence(self):
        """99% CI should be wider than 95% CI."""
        ci_95 = confidence_interval(self.DELTAS, confidence=0.95)
        ci_99 = confidence_interval(self.DELTAS, confidence=0.99)
        width_95 = ci_95["upper"] - ci_95["lower"]
        width_99 = ci_99["upper"] - ci_99["lower"]
        assert width_99 > width_95


# ---------------------------------------------------------------------------
# compare_treatments
# ---------------------------------------------------------------------------


class TestCompareTreatments:
    """Verify full treatment comparison output structure."""

    TREATMENT_PNL = {
        "treatment_a": [10, 5, -3, 8, 2],
        "treatment_b": [3, 4, 1, 2, 5],
        "control": [2, -1, -5, 1, -3],
    }
    METRICS = {
        "treatment_a": {"brier": [0.1, 0.2, 0.15, 0.12, 0.18], "skip_rate": [0.05, 0.10, 0.03, 0.08, 0.06]},
        "treatment_b": {"brier": [0.2, 0.25, 0.18, 0.22, 0.19], "skip_rate": [0.15, 0.20, 0.12, 0.18, 0.14]},
        "control": {"brier": [0.3, 0.28, 0.32, 0.27, 0.35], "skip_rate": [0.25, 0.30, 0.22, 0.28, 0.26]},
    }

    def test_control_mean_pnl_present(self):
        """Output contains control_mean_pnl."""
        result = compare_treatments(self.TREATMENT_PNL, self.METRICS)
        assert "control_mean_pnl" in result
        expected = float(np.mean(self.TREATMENT_PNL["control"]))
        assert result["control_mean_pnl"] == pytest.approx(expected, rel=1e-10)

    def test_treatment_keys_present(self):
        """Both treatments should have entries with all required sub-keys."""
        result = compare_treatments(self.TREATMENT_PNL, self.METRICS)
        for name in ("treatment_a", "treatment_b"):
            assert name in result
            entry = result[name]
            required = {"mean_pnl", "t_statistic", "p_value", "mean_delta", "n", "cohens_d", "ci_95"}
            assert required <= set(entry.keys()), f"{name} missing keys: {required - set(entry.keys())}"

    def test_metric_ttest_present(self):
        """Metric comparisons (brier_ttest, skip_rate_ttest) should be present."""
        result = compare_treatments(self.TREATMENT_PNL, self.METRICS)
        for name in ("treatment_a", "treatment_b"):
            assert "brier_ttest" in result[name]
            assert "skip_rate_ttest" in result[name]
            # Each metric ttest should have standard t-test output keys
            mt = result[name]["brier_ttest"]
            assert "t_statistic" in mt
            assert "p_value" in mt

    def test_no_control_returns_error(self):
        """Missing control data should return error dict."""
        result = compare_treatments({"treatment_a": [1, 2, 3]}, {})
        assert "error" in result

    def test_empty_control_returns_error(self):
        """Empty control list should return error dict."""
        result = compare_treatments({"treatment_a": [1, 2, 3], "control": []}, {})
        assert "error" in result

    def test_json_serializable(self):
        """All output values must be JSON-serializable (float, int, str — no numpy types)."""
        import json

        result = compare_treatments(self.TREATMENT_PNL, self.METRICS)
        serialized = json.dumps(result)  # should not raise
        assert isinstance(serialized, str)

    def test_ci_95_nested_structure(self):
        """ci_95 should be a dict with lower, upper, mean, n."""
        result = compare_treatments(self.TREATMENT_PNL, self.METRICS)
        ci = result["treatment_a"]["ci_95"]
        assert set(ci.keys()) == {"lower", "upper", "mean", "n"}
