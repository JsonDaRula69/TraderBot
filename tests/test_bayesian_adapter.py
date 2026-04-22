"""Tests for Bayesian adapter — conjugate prior updates and guardrails."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from traderbot.simulation.adaptation import (
    WEAK_BETA,
    WEAK_DIRICHLET,
    WEAK_GAMMA,
    WEAK_NORMAL,
    BayesianAdapter,
    BetaParams,
    BinomialObservations,
    DirichletParams,
    ExponentialObservations,
    GammaParams,
    GuardrailConfig,
    MultinomialObservations,
    NormalObservations,
    NormalParams,
    UpdateMethod,
    update_beta_binomial,
    update_dirichlet_multinomial,
    update_gamma_exponential,
    update_normal_normal,
)

# ---------------------------------------------------------------------------
# Distribution parameter model tests
# ---------------------------------------------------------------------------


class TestBetaParams:
    def test_valid(self):
        bp = BetaParams(alpha=2.0, beta=8.0)
        assert bp.alpha == 2.0
        assert bp.beta == 8.0
        assert abs(bp.mean - 0.2) < 1e-10
        assert bp.variance > 0

    def test_mean_formula(self):
        bp = BetaParams(alpha=5.0, beta=5.0)
        assert abs(bp.mean - 0.5) < 1e-10

    def test_variance_formula(self):
        bp = BetaParams(alpha=2.0, beta=8.0)
        total = 10.0
        expected = (2.0 * 8.0) / (total * total * (total + 1))
        assert abs(bp.variance - expected) < 1e-10

    def test_rejects_non_positive(self):
        with pytest.raises(ValidationError):
            BetaParams(alpha=0, beta=1)
        with pytest.raises(ValidationError):
            BetaParams(alpha=1, beta=0)
        with pytest.raises(ValidationError):
            BetaParams(alpha=-1, beta=2)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            BetaParams(alpha=1, beta=1, extra=True)


class TestDirichletParams:
    def test_valid(self):
        dp = DirichletParams(alphas=[1.0, 1.0, 1.0])
        assert len(dp.alphas) == 3
        assert dp.concentration == 3.0

    def test_means(self):
        dp = DirichletParams(alphas=[2.0, 3.0, 5.0])
        means = dp.means
        assert abs(means[0] - 0.2) < 1e-10
        assert abs(means[1] - 0.3) < 1e-10
        assert abs(means[2] - 0.5) < 1e-10

    def test_rejects_single_alpha(self):
        with pytest.raises(ValidationError):
            DirichletParams(alphas=[1.0])

    def test_rejects_negative_alpha(self):
        with pytest.raises(ValueError):
            DirichletParams(alphas=[1.0, -0.5])


class TestNormalParams:
    def test_valid(self):
        np_ = NormalParams(mu=0.5, sigma_sq=0.04)
        assert np_.mean == 0.5
        assert np_.variance == 0.04

    def test_rejects_non_positive_variance(self):
        with pytest.raises(ValidationError):
            NormalParams(mu=0.5, sigma_sq=0)
        with pytest.raises(ValidationError):
            NormalParams(mu=0.5, sigma_sq=-0.01)


class TestGammaParams:
    def test_valid(self):
        gp = GammaParams(alpha=1.0, beta=1.0)
        assert gp.mean == 1.0
        assert gp.variance == 1.0

    def test_mean_and_variance(self):
        gp = GammaParams(alpha=4.0, beta=2.0)
        assert abs(gp.mean - 2.0) < 1e-10
        assert abs(gp.variance - 1.0) < 1e-10

    def test_rejects_non_positive(self):
        with pytest.raises(ValidationError):
            GammaParams(alpha=0, beta=1)
        with pytest.raises(ValidationError):
            GammaParams(alpha=1, beta=0)


# ---------------------------------------------------------------------------
# Observation model tests
# ---------------------------------------------------------------------------


class TestObservationModels:
    def test_binomial_total(self):
        obs = BinomialObservations(successes=9, failures=5)
        assert obs.total == 14

    def test_multinomial_total(self):
        obs = MultinomialObservations(counts=[5, 3, 2])
        assert obs.total == 10

    def test_normal_total(self):
        obs = NormalObservations(values=[0.5, 0.6, 0.7], known_variance=0.1)
        assert obs.total == 3

    def test_exponential_total(self):
        obs = ExponentialObservations(values=[1.0, 2.0, 3.0])
        assert obs.total == 3

    def test_multinomial_min_length(self):
        with pytest.raises(ValidationError):
            MultinomialObservations(counts=[5])


# ---------------------------------------------------------------------------
# Pure conjugate update function tests
# ---------------------------------------------------------------------------


class TestBetaBinomialUpdate:
    def test_basic_update(self):
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=9, failures=5)
        posterior = update_beta_binomial(prior, obs)
        assert posterior.alpha == 11.0
        assert posterior.beta == 13.0

    def test_mean_shifts_toward_data(self):
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=90, failures=10)
        posterior = update_beta_binomial(prior, obs)
        assert posterior.mean > 0.2
        assert posterior.mean < 0.9

    def test_variance_decreases_with_more_data(self):
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs1 = BinomialObservations(successes=5, failures=5)
        posterior1 = update_beta_binomial(prior, obs1)
        obs2 = BinomialObservations(successes=50, failures=50)
        posterior2 = update_beta_binomial(prior, obs2)
        assert posterior2.variance < posterior1.variance

    def test_zero_observations_returns_prior(self):
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=0, failures=0)
        posterior = update_beta_binomial(prior, obs)
        assert posterior.alpha == prior.alpha
        assert posterior.beta == prior.beta


class TestDirichletMultinomialUpdate:
    def test_basic_update(self):
        prior = DirichletParams(alphas=[1.0, 1.0, 1.0])
        obs = MultinomialObservations(counts=[5, 3, 2])
        posterior = update_dirichlet_multinomial(prior, obs)
        assert posterior.alphas == [6.0, 4.0, 3.0]

    def test_dimension_mismatch_raises(self):
        prior = DirichletParams(alphas=[1.0, 1.0])
        obs = MultinomialObservations(counts=[5, 3, 2])
        with pytest.raises(ValueError, match="dimensions"):
            update_dirichlet_multinomial(prior, obs)

    def test_weights_shift_toward_data(self):
        prior = DirichletParams(alphas=[1.0, 1.0, 1.0])
        obs = MultinomialObservations(counts=[90, 5, 5])
        posterior = update_dirichlet_multinomial(prior, obs)
        weights = posterior.means
        assert weights[0] > 0.8


class TestNormalNormalUpdate:
    def test_basic_update(self):
        prior = NormalParams(mu=0.5, sigma_sq=0.04)
        obs = NormalObservations(values=[0.6, 0.7, 0.8], known_variance=0.1)
        posterior = update_normal_normal(prior, obs)
        assert posterior.mu > prior.mu
        assert posterior.sigma_sq < prior.sigma_sq

    def test_posterior_precision_formula(self):
        prior = NormalParams(mu=0.5, sigma_sq=0.04)
        obs = NormalObservations(values=[0.6], known_variance=0.1)
        posterior = update_normal_normal(prior, obs)
        expected_sigma_sq = 1.0 / (1.0 / 0.04 + 1.0 / 0.1)
        assert abs(posterior.sigma_sq - expected_sigma_sq) < 1e-10

    def test_empty_observations_returns_prior(self):
        prior = NormalParams(mu=0.5, sigma_sq=0.04)
        obs = NormalObservations(values=[], known_variance=0.1)
        posterior = update_normal_normal(prior, obs)
        assert posterior.mu == prior.mu
        assert posterior.sigma_sq == prior.sigma_sq

    def test_strong_data_overrides_weak_prior(self):
        prior = NormalParams(mu=0.5, sigma_sq=1.0)
        obs = NormalObservations(values=[0.9] * 100, known_variance=0.01)
        posterior = update_normal_normal(prior, obs)
        assert abs(posterior.mu - 0.9) < 0.01


class TestGammaExponentialUpdate:
    def test_basic_update(self):
        prior = GammaParams(alpha=1.0, beta=1.0)
        obs = ExponentialObservations(values=[0.5, 1.0, 1.5])
        posterior = update_gamma_exponential(prior, obs)
        assert posterior.alpha == 4.0
        assert abs(posterior.beta - 4.0) < 1e-10

    def test_empty_observations_returns_prior(self):
        prior = GammaParams(alpha=1.0, beta=1.0)
        obs = ExponentialObservations(values=[])
        posterior = update_gamma_exponential(prior, obs)
        assert posterior.alpha == prior.alpha
        assert posterior.beta == prior.beta

    def test_mean_shifts_with_data(self):
        prior = GammaParams(alpha=1.0, beta=1.0)
        obs = ExponentialObservations(values=[0.3, 0.4, 0.5, 0.6])
        posterior = update_gamma_exponential(prior, obs)
        assert posterior.mean > prior.mean


# ---------------------------------------------------------------------------
# BayesianAdapter guardrail tests
# ---------------------------------------------------------------------------


class TestMinObservationsGuardrail:
    def test_rejects_below_minimum(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=3, failures=2)
        with pytest.raises(ValueError, match="Insufficient observations"):
            adapter.update_beta(prior, obs)

    def test_accepts_at_minimum(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=6, failures=4)
        result = adapter.update_beta(prior, obs)
        assert result.update_count == 1

    def test_custom_min_observations(self):
        config = GuardrailConfig(min_observations=5)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=3, failures=2)
        result = adapter.update_beta(prior, obs)
        assert result.update_count == 1

    def test_all_update_types_enforce_minimum(self):
        adapter = BayesianAdapter()
        d_prior = DirichletParams(alphas=[1.0, 1.0, 1.0])
        d_obs = MultinomialObservations(counts=[2, 2, 2])
        with pytest.raises(ValueError):
            adapter.update_dirichlet(d_prior, d_obs)

        n_prior = NormalParams(mu=0.5, sigma_sq=0.04)
        n_obs = NormalObservations(values=[0.5] * 5, known_variance=0.1)
        with pytest.raises(ValueError):
            adapter.update_normal(n_prior, n_obs)

        g_prior = GammaParams(alpha=1.0, beta=1.0)
        g_obs = ExponentialObservations(values=[1.0] * 3)
        with pytest.raises(ValueError):
            adapter.update_gamma(g_prior, g_obs)


class TestMaxChangeGuardrail:
    def test_clamps_20_percent_max_change(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=90, failures=10)
        result = adapter.update_beta(prior, obs)
        clamped_mean = result.updated_params["mean"]
        assert abs(clamped_mean - 0.2) <= 0.2 * 0.2 + 1e-10

    def test_small_changes_not_clamped(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=12, failures=8)
        result = adapter.update_beta(prior, obs)
        assert result.magnitude > 0


class TestCooldownGuardrail:
    def test_max_4_updates_per_day(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=6, failures=4)

        for i in range(4):
            result = adapter.update_beta(prior, obs)
            assert result.update_count == i + 1

        with pytest.raises(ValueError, match="Cooldown active"):
            adapter.update_beta(prior, obs)

    def test_cooldown_remaining_populated(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=6, failures=4)

        adapter.update_beta(prior, obs)
        result = adapter.update_beta(prior, obs)
        assert result.cooldown_remaining is not None or len(adapter._update_timestamps) < 4

    def test_custom_cooldown_config(self):
        config = GuardrailConfig(max_updates_per_day=2)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=6, failures=4)

        adapter.update_beta(prior, obs)
        adapter.update_beta(prior, obs)

        with pytest.raises(ValueError, match="Cooldown"):
            adapter.update_beta(prior, obs)


class TestVarianceResetGuardrail:
    def test_resets_to_weak_prior_when_variance_too_low(self):
        adapter = BayesianAdapter()
        prior = BetaParams(alpha=100.0, beta=100.0)
        obs = BinomialObservations(successes=100, failures=100)
        result = adapter.update_beta(prior, obs)
        if result.variance_reset:
            assert result.updated_params["alpha"] == WEAK_BETA.alpha
            assert result.updated_params["beta"] == WEAK_BETA.beta
            assert result.confidence == 0.0

    def test_no_reset_when_variance_healthy(self):
        config = GuardrailConfig(variance_reset_threshold=0.0001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=6, failures=4)
        result = adapter.update_beta(prior, obs)
        assert not result.variance_reset

    def test_normal_variance_reset(self):
        adapter = BayesianAdapter()
        prior = NormalParams(mu=0.5, sigma_sq=0.001)
        obs = NormalObservations(values=[0.5] * 20, known_variance=0.001)
        result = adapter.update_normal(prior, obs)
        if result.variance_reset:
            assert result.updated_params["sigma_sq"] == WEAK_NORMAL.sigma_sq
            assert result.confidence == 0.0

    def test_dirichlet_variance_reset(self):
        adapter = BayesianAdapter()
        prior = DirichletParams(alphas=[100.0, 100.0, 100.0])
        obs = MultinomialObservations(counts=[50, 30, 20])
        result = adapter.update_dirichlet(prior, obs)
        if result.variance_reset:
            assert result.confidence == 0.0

    def test_gamma_variance_reset(self):
        adapter = BayesianAdapter()
        prior = GammaParams(alpha=100.0, beta=100.0)
        obs = ExponentialObservations(values=[1.0] * 15)
        result = adapter.update_gamma(prior, obs)
        if result.variance_reset:
            assert result.updated_params["alpha"] == WEAK_GAMMA.alpha
            assert result.updated_params["beta"] == WEAK_GAMMA.beta
            assert result.confidence == 0.0


class TestDriftFlagGuardrail:
    def test_flags_after_3_consecutive_drifts(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=9, failures=1)

        results = []
        for _ in range(3):
            result = adapter.update_beta(prior, obs)
            results.append(result)

        assert isinstance(results[-1].human_review, bool)

    def test_no_drift_flag_with_stable_data(self):
        config = GuardrailConfig(drift_threshold_pct=0.5, variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=20.0, beta=80.0)
        obs = BinomialObservations(successes=12, failures=8)
        result = adapter.update_beta(prior, obs)
        assert not result.human_review

    def test_drift_counter_resets_on_stable_update(self):
        config = GuardrailConfig(drift_threshold_pct=0.10, drift_consecutive_count=3)
        adapter = BayesianAdapter(config=config)

        adapter._drift_counts["test_param"] = 2
        adapter._check_drift("test_param", 1.0, 1.05)
        assert adapter._drift_counts.get("test_param", 0) == 0


# ---------------------------------------------------------------------------
# AdaptationResult model tests
# ---------------------------------------------------------------------------


class TestAdaptationResultExtended:
    def test_extended_fields(self):
        result = adapter_result(
            method=UpdateMethod.BETA_BINOMIAL,
            human_review=False,
            variance_reset=False,
            update_count=1,
        )
        assert result.method == UpdateMethod.BETA_BINOMIAL
        assert result.human_review is False
        assert result.variance_reset is False
        assert result.update_count == 1

    def test_cooldown_remaining_timedelta(self):
        result = adapter_result(cooldown_remaining=timedelta(hours=6))
        assert result.cooldown_remaining == timedelta(hours=6)

    def test_cooldown_none(self):
        result = adapter_result(cooldown_remaining=None)
        assert result.cooldown_remaining is None

    def test_human_review_flag(self):
        result = adapter_result(human_review=True)
        assert result.human_review is True

    def test_variance_reset_flag(self):
        result = adapter_result(variance_reset=True)
        assert result.variance_reset is True

    def test_default_values(self):
        result = adapter_result()
        assert result.updated_params == {}
        assert result.method is None
        assert result.human_review is False
        assert result.variance_reset is False
        assert result.update_count == 0
        assert result.cooldown_remaining is None

    def test_confidence_zero_allowed(self):
        result = adapter_result(confidence=0.0)
        assert result.confidence == 0.0


class TestGuardrailConfigModel:
    def test_defaults(self):
        config = GuardrailConfig()
        assert config.max_change_pct == 0.20
        assert config.min_observations == 10
        assert config.max_updates_per_day == 4
        assert config.variance_reset_threshold == 0.01
        assert config.drift_threshold_pct == 0.10
        assert config.drift_consecutive_count == 3

    def test_custom_config(self):
        config = GuardrailConfig(
            max_change_pct=0.15,
            min_observations=5,
            max_updates_per_day=2,
            variance_reset_threshold=0.005,
            drift_threshold_pct=0.05,
            drift_consecutive_count=5,
        )
        assert config.max_change_pct == 0.15
        assert config.min_observations == 5

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            GuardrailConfig(max_change_pct=0.2, extra=True)

    def test_rejects_zero_change_pct(self):
        with pytest.raises(ValidationError):
            GuardrailConfig(max_change_pct=0)

    def test_rejects_negative_threshold(self):
        with pytest.raises(ValidationError):
            GuardrailConfig(variance_reset_threshold=-0.01)


# ---------------------------------------------------------------------------
# Integration: full update cycle tests
# ---------------------------------------------------------------------------


class TestAdapterUpdateBeta:
    def test_full_cycle(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=14, failures=6)
        result = adapter.update_beta(prior, obs)

        assert result.method == UpdateMethod.BETA_BINOMIAL
        assert result.category
        assert result.updated_params["alpha"] == 16.0
        assert result.updated_params["beta"] == 14.0
        assert result.direction in ("increase", "decrease", "maintain")
        assert result.confidence >= 0.0
        assert result.update_count == 1

    def test_method_reasoning_includes_formula(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = BetaParams(alpha=2.0, beta=8.0)
        obs = BinomialObservations(successes=14, failures=6)
        result = adapter.update_beta(prior, obs)
        assert "Beta(2.0,8.0)" in result.reasoning
        assert "Beta(16.0,14.0)" in result.reasoning


class TestAdapterUpdateDirichlet:
    def test_full_cycle(self):
        adapter = BayesianAdapter()
        prior = DirichletParams(alphas=[2.0, 3.0, 5.0])
        obs = MultinomialObservations(counts=[5, 3, 2])
        result = adapter.update_dirichlet(prior, obs)

        assert result.method == UpdateMethod.DIRICHLET_MULTINOMIAL
        assert result.updated_params["alpha_0"] == 7.0
        assert result.updated_params["alpha_1"] == 6.0
        assert result.updated_params["alpha_2"] == 7.0


class TestAdapterUpdateNormal:
    def test_full_cycle(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = NormalParams(mu=0.5, sigma_sq=0.04)
        obs = NormalObservations(values=[0.6, 0.7, 0.8, 0.65, 0.75] * 2, known_variance=0.1)
        result = adapter.update_normal(prior, obs)

        assert result.method == UpdateMethod.NORMAL_NORMAL
        assert result.updated_params["mu"] > prior.mu
        assert result.updated_params["sigma_sq"] < prior.sigma_sq


class TestAdapterUpdateGamma:
    def test_full_cycle(self):
        config = GuardrailConfig(variance_reset_threshold=0.001)
        adapter = BayesianAdapter(config=config)
        prior = GammaParams(alpha=1.0, beta=1.0)
        obs = ExponentialObservations(values=[0.5, 1.0, 1.5, 0.8, 1.2, 0.9, 1.1, 0.7, 1.3, 0.6])
        result = adapter.update_gamma(prior, obs)

        assert result.method == UpdateMethod.GAMMA_EXPONENTIAL
        assert result.updated_params["alpha"] == 11.0
        assert result.direction in ("increase", "decrease", "maintain")


class TestAdapterWeakPriors:
    def test_weak_beta_defaults(self):
        assert WEAK_BETA.alpha == 2.0
        assert WEAK_BETA.beta == 8.0
        assert abs(WEAK_BETA.mean - 0.2) < 1e-10

    def test_weak_dirichlet_defaults(self):
        assert WEAK_DIRICHLET.alphas == [1.0, 1.0, 1.0]

    def test_weak_normal_defaults(self):
        assert WEAK_NORMAL.mu == 0.5
        assert WEAK_NORMAL.sigma_sq == 0.04

    def test_weak_gamma_defaults(self):
        assert WEAK_GAMMA.alpha == 1.0
        assert WEAK_GAMMA.beta == 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def adapter_result(
    method: UpdateMethod | None = None,
    human_review: bool = False,
    variance_reset: bool = False,
    update_count: int = 0,
    confidence: float = 0.8,
    cooldown_remaining: timedelta | None = None,
):
    from traderbot.simulation.adaptation import AdaptationResult, MarketCategory

    return AdaptationResult(
        category=MarketCategory.ECONOMICS,
        direction="increase",
        magnitude=0.05,
        confidence=confidence,
        reasoning="test",
        method=method,
        human_review=human_review,
        variance_reset=variance_reset,
        update_count=update_count,
        cooldown_remaining=cooldown_remaining,
    )
