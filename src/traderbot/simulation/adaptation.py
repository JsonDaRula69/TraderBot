"""Bayesian adaptation engine — conjugate prior updates with safety guardrails.

Implements analytical (non-MCMC) Bayesian updates for strategy parameters:
  - Beta-Binomial for edge threshold
  - Dirichlet-Multinomial for signal weights
  - Normal-Normal for mean reversion level
  - Gamma-Exponential for momentum decay rate

Guardrails prevent pathological adaptation:
  - 20% max change per update
  - Minimum 10 observations required
  - Maximum 4 updates per 24 hours
  - Variance reset when posterior < 0.01
  - Drift flag for 3 consecutive >10% changes
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traderbot.kalshi.models import MarketCategory
from traderbot.simulation.adapter_state import AdapterStateStore, resolve_state_path

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UpdateMethod(StrEnum):
    """Conjugate prior update method used."""

    BETA_BINOMIAL = "beta_binomial"
    DIRICHLET_MULTINOMIAL = "dirichlet_multinomial"
    NORMAL_NORMAL = "normal_normal"
    GAMMA_EXPONENTIAL = "gamma_exponential"


# ---------------------------------------------------------------------------
# Distribution parameter models
# ---------------------------------------------------------------------------


class BetaParams(BaseModel):
    """Parameters for a Beta distribution Beta(alpha, beta)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    alpha: Annotated[float, Field(gt=0)]
    beta: Annotated[float, Field(gt=0)]

    @property
    def mean(self) -> float:
        """Expected value of the Beta distribution."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Variance of the Beta distribution."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1))


class DirichletParams(BaseModel):
    """Parameters for a Dirichlet distribution Dir(alpha_1, ..., alpha_k)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    alphas: Annotated[list[float], Field(min_length=2)]

    @model_validator(mode="after")
    def _validate_alphas_positive(self) -> DirichletParams:
        for a in self.alphas:
            if a <= 0:
                msg = f"Alpha values must be positive, got {a}"
                raise ValueError(msg)
        return self

    @property
    def means(self) -> list[float]:
        """Expected values (probabilities) for each component."""
        total = sum(self.alphas)
        return [a / total for a in self.alphas]

    @property
    def concentration(self) -> float:
        """Total concentration parameter (sum of alphas)."""
        return sum(self.alphas)


class NormalParams(BaseModel):
    """Parameters for a Normal distribution N(mu, sigma^2)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    mu: float
    sigma_sq: Annotated[float, Field(gt=0)]

    @property
    def mean(self) -> float:
        """Expected value."""
        return self.mu

    @property
    def variance(self) -> float:
        """Variance (sigma^2)."""
        return self.sigma_sq


class GammaParams(BaseModel):
    """Parameters for a Gamma distribution Gamma(alpha, beta) rate parametrization.

    PDF: f(x) = (beta^alpha / Gamma(alpha)) * x^(alpha-1) * exp(-beta * x)
    Mean = alpha / beta, Variance = alpha / beta^2
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    alpha: Annotated[float, Field(gt=0)]
    beta: Annotated[float, Field(gt=0)]

    @property
    def mean(self) -> float:
        """Expected value (alpha / beta)."""
        return self.alpha / self.beta

    @property
    def variance(self) -> float:
        """Variance (alpha / beta^2)."""
        return self.alpha / (self.beta * self.beta)


# ---------------------------------------------------------------------------
# Observation models
# ---------------------------------------------------------------------------


class BinomialObservations(BaseModel):
    """Observations for Beta-Binomial update: successes and failures."""

    model_config = ConfigDict(strict=True, extra="forbid")

    successes: Annotated[int, Field(ge=0)]
    failures: Annotated[int, Field(ge=0)]

    @property
    def total(self) -> int:
        return self.successes + self.failures


class MultinomialObservations(BaseModel):
    """Observations for Dirichlet-Multinomial update: counts per category."""

    model_config = ConfigDict(strict=True, extra="forbid")

    counts: Annotated[list[int], Field(min_length=2)]

    @property
    def total(self) -> int:
        return sum(self.counts)


class NormalObservations(BaseModel):
    """Observations for Normal-Normal update: list of observed values."""

    model_config = ConfigDict(strict=True, extra="forbid")

    values: list[float]
    known_variance: Annotated[float, Field(gt=0)]

    @property
    def total(self) -> int:
        return len(self.values)


class ExponentialObservations(BaseModel):
    """Observations for Gamma-Exponential update: list of observed durations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    values: list[float]

    @property
    def total(self) -> int:
        return len(self.values)


# ---------------------------------------------------------------------------
# Legacy models (kept for backward compatibility)
# ---------------------------------------------------------------------------


class Prior(BaseModel):
    """Bayesian prior for a strategy parameter within a market category."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    mean: float
    variance: Annotated[float, Field(gt=0)]
    sample_count: Annotated[int, Field(ge=0)]
    last_updated: datetime


class Posterior(BaseModel):
    """Posterior distribution after Bayesian update with observations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    mean: float
    variance: Annotated[float, Field(gt=0)]
    sample_count: Annotated[int, Field(ge=0)]
    last_updated: datetime
    observations: list[float]
    updated_mean: float
    updated_variance: Annotated[float, Field(gt=0)]


class AdaptationConfig(BaseModel):
    """Configuration for the Bayesian adaptation engine."""

    model_config = ConfigDict(strict=True, extra="forbid")

    learning_rate: Annotated[float, Field(gt=0, le=1.0)]
    min_observations: Annotated[int, Field(ge=1)] = 10
    confidence_threshold: Annotated[float, Field(gt=0, le=1.0)]
    decay_rate: Annotated[float, Field(gt=0, le=1.0)]


class AdaptationResult(BaseModel):
    """Result of a single Bayesian adaptation step."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    direction: Literal["increase", "decrease", "maintain"]
    magnitude: Annotated[float, Field(gt=0)]
    confidence: Annotated[float, Field(ge=0, le=1.0)]
    reasoning: str
    updated_params: dict[str, float] = Field(default_factory=dict)
    method: UpdateMethod | None = None
    human_review: bool = False
    variance_reset: bool = False
    update_count: int = Field(default=0, ge=0)
    cooldown_remaining: timedelta | None = None


class StrategyAdjustment(BaseModel):
    """A concrete strategy parameter change proposed by adaptation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    field_name: str
    old_value: float
    new_value: float
    justification: str
    confidence: Annotated[float, Field(gt=0, le=1.0)]


# ---------------------------------------------------------------------------
# Guardrail configuration
# ---------------------------------------------------------------------------


class GuardrailConfig(BaseModel):
    """Safety guardrails for the adaptation engine."""

    model_config = ConfigDict(strict=True, extra="forbid")

    max_change_pct: Annotated[float, Field(gt=0, le=1.0)] = 0.20
    min_observations: Annotated[int, Field(ge=1)] = 10
    max_updates_per_day: Annotated[int, Field(ge=1)] = 4
    variance_reset_threshold: Annotated[float, Field(gt=0)] = 0.01
    drift_threshold_pct: Annotated[float, Field(gt=0, le=1.0)] = 0.10
    drift_consecutive_count: Annotated[int, Field(ge=1)] = 3


# ---------------------------------------------------------------------------
# Weak priors (defaults from docs/self-learning.md)
# ---------------------------------------------------------------------------


WEAK_BETA = BetaParams(alpha=2.0, beta=8.0)
WEAK_DIRICHLET = DirichletParams(alphas=[1.0, 1.0, 1.0])
WEAK_NORMAL = NormalParams(mu=0.5, sigma_sq=0.04)
WEAK_GAMMA = GammaParams(alpha=1.0, beta=1.0)


# ---------------------------------------------------------------------------
# Conjugate prior update functions (pure-Python, no scipy)
# ---------------------------------------------------------------------------


def update_beta_binomial(prior: BetaParams, observations: BinomialObservations) -> BetaParams:
    """Beta-Binomial conjugate update for edge threshold.

    Prior: Beta(alpha, beta)
    Likelihood: Binomial(n, p)
    Posterior: Beta(alpha + successes, beta + failures)
    """
    return BetaParams(
        alpha=prior.alpha + observations.successes,
        beta=prior.beta + observations.failures,
    )


def update_dirichlet_multinomial(
    prior: DirichletParams, observations: MultinomialObservations
) -> DirichletParams:
    """Dirichlet-Multinomial conjugate update for signal weights.

    Prior: Dir(alpha_1, ..., alpha_k)
    Likelihood: Multinomial(n, p)
    Posterior: Dir(alpha_1 + n_1, ..., alpha_k + n_k)
    """
    if len(observations.counts) != len(prior.alphas):
        msg = (
            f"Observation dimensions ({len(observations.counts)}) must match "
            f"prior dimensions ({len(prior.alphas)})"
        )
        raise ValueError(msg)
    new_alphas = [a + n for a, n in zip(prior.alphas, observations.counts, strict=True)]
    return DirichletParams(alphas=new_alphas)


def update_normal_normal(prior: NormalParams, observations: NormalObservations) -> NormalParams:
    """Normal-Normal conjugate update for mean reversion level.

    Prior: N(mu_0, sigma_0^2)
    Likelihood: N(mu, sigma^2) — known variance
    Posterior:
      mu_1 = (sigma_0^{-2} * mu_0 + n * sigma^{-2} * x_bar) / (sigma_0^{-2} + n * sigma^{-2})
      sigma_1^2 = 1 / (sigma_0^{-2} + n * sigma^{-2})
    """
    n = len(observations.values)
    if n == 0:
        return prior

    x_bar = sum(observations.values) / n
    prior_precision = 1.0 / prior.sigma_sq
    likelihood_precision = n / observations.known_variance
    posterior_precision = prior_precision + likelihood_precision

    posterior_mu = (prior_precision * prior.mu + likelihood_precision * x_bar) / posterior_precision
    posterior_sigma_sq = 1.0 / posterior_precision

    return NormalParams(mu=posterior_mu, sigma_sq=posterior_sigma_sq)


def update_gamma_exponential(
    prior: GammaParams, observations: ExponentialObservations
) -> GammaParams:
    """Gamma-Exponential conjugate update for momentum decay rate.

    Prior: Gamma(alpha, beta) — rate parametrization
    Likelihood: Exponential(lambda) where lambda is the rate parameter
    Posterior: Gamma(alpha + n, beta + sum(x_i))

    Note: This updates the rate (lambda) of an exponential distribution.
    Mean of Gamma posterior = (alpha + n) / (beta + sum(x_i))
    """
    n = len(observations.values)
    if n == 0:
        return prior

    sum_x = sum(observations.values)
    return GammaParams(
        alpha=prior.alpha + n,
        beta=prior.beta + sum_x,
    )


# ---------------------------------------------------------------------------
# BayesianAdapter — the main engine
# ---------------------------------------------------------------------------

# Type alias for any distribution parameter set
DistributionParams = BetaParams | DirichletParams | NormalParams | GammaParams


class BayesianAdapter:
    """Bayesian adaptation engine with conjugate prior updates and guardrails.

    Tracks update timestamps for cooldown enforcement and records consecutive
    drift changes to flag for human review. When state_path is provided,
    state is loaded on init and persisted after each successful update.
    """

    def __init__(
        self,
        config: GuardrailConfig | None = None,
        state_path: Path | None = None,
        *,
        profile_base_dir: str | None = None,
    ) -> None:
        self.config = config or GuardrailConfig()
        self._state_path: Path | None = None
        if state_path is not None or profile_base_dir is not None:
            self._state_path = resolve_state_path(state_path, profile_base_dir)
        self._update_timestamps: list[datetime] = []
        self._drift_counts: dict[str, int] = {}
        self._distribution_states: dict[str, Any] = {}
        if self._state_path is not None:
            self._load_state()

    def _check_min_observations(self, observation_count: int) -> None:
        """Raise ValueError if observations below minimum threshold."""
        if observation_count < self.config.min_observations:
            msg = (
                f"Insufficient observations: {observation_count} < "
                f"{self.config.min_observations} minimum required"
            )
            raise ValueError(msg)

    def _check_cooldown(self) -> None:
        """Raise ValueError if cooldown has not elapsed."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=24)
        recent = [ts for ts in self._update_timestamps if ts > cutoff]
        if len(recent) >= self.config.max_updates_per_day:
            last_update = max(self._update_timestamps)
            cooldown_end = last_update + timedelta(hours=24)
            remaining = cooldown_end - now
            msg = (
                f"Cooldown active: {len(recent)} updates in last 24h "
                f"(max {self.config.max_updates_per_day}). "
                f"Retry after {remaining}"
            )
            raise ValueError(msg)

    def _clamp_change(self, old_value: float, new_value: float) -> float:
        """Clamp new_value to within max_change_pct of old_value."""
        if old_value == 0:
            return new_value
        max_delta = abs(old_value) * self.config.max_change_pct
        delta = new_value - old_value
        clamped_delta = max(-max_delta, min(max_delta, delta))
        return old_value + clamped_delta

    def _check_variance_reset(self, variance: float) -> bool:
        """Return True if posterior variance is below reset threshold."""
        return variance < self.config.variance_reset_threshold

    def _check_drift(self, param_name: str, old_value: float, new_value: float) -> bool:
        """Track and flag consecutive drifts exceeding threshold.

        Returns True if this update triggers the drift flag (consecutive
        changes > drift_threshold_pct for drift_consecutive_count updates).
        """
        if old_value == 0:
            self._drift_counts[param_name] = 0
            return False

        pct_change = abs((new_value - old_value) / old_value)
        if pct_change > self.config.drift_threshold_pct:
            self._drift_counts[param_name] = self._drift_counts.get(param_name, 0) + 1
        else:
            self._drift_counts[param_name] = 0

        return self._drift_counts[param_name] >= self.config.drift_consecutive_count

    def _record_update(self) -> None:
        """Record the current timestamp as an update."""
        self._update_timestamps.append(datetime.now(UTC))

    def _load_state(self) -> None:
        """Load persisted state from disk if available."""
        loaded = AdapterStateStore.load(self._state_path)
        if loaded is None:
            return
        self._update_timestamps = AdapterStateStore.timestamps_to_datetime(loaded.update_timestamps)
        self._drift_counts = dict(loaded.drift_counts)
        self._distribution_states = dict(loaded.distribution_states)
        logger.debug(
            "Loaded adapter state from %s (%d timestamps)",
            self._state_path,
            len(self._update_timestamps),
        )

    def _persist_state(self) -> None:
        """Write current state to disk via atomic write."""
        if self._state_path is None:
            return
        try:
            AdapterStateStore.save(
                update_timestamps=self._update_timestamps,
                drift_counts=self._drift_counts,
                distribution_states=self._distribution_states,
                path=self._state_path,
            )
        except OSError:
            logger.warning("Failed to persist adapter state to %s", self._state_path, exc_info=True)

    def _store_distribution(self, key: str, params: DistributionParams) -> None:
        """Store distribution parameters for persistence."""
        self._distribution_states[key] = params.model_dump()

    def _cooldown_remaining(self) -> timedelta | None:
        """Return time remaining until next update is allowed, or None."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=24)
        recent = [ts for ts in self._update_timestamps if ts > cutoff]
        if len(recent) >= self.config.max_updates_per_day:
            last_update = max(self._update_timestamps)
            end = last_update + timedelta(hours=24)
            if end > now:
                return end - now
        return None

    def _compute_direction(
        self, old_value: float, new_value: float
    ) -> Literal["increase", "decrease", "maintain"]:
        """Determine adaptation direction."""
        if new_value > old_value:
            return "increase"
        if new_value < old_value:
            return "decrease"
        return "maintain"

    @staticmethod
    def _compute_confidence(
        prior_variance: float, posterior_variance: float, variance_reset: bool
    ) -> float:
        """Confidence from 0 to 1 based on variance reduction. Reset → 0."""
        if variance_reset:
            return 0.0
        return max(0.0, min(1.0, 1.0 - posterior_variance / max(prior_variance, 1e-10)))

    def update_beta(
        self,
        prior: BetaParams,
        observations: BinomialObservations,
        category: MarketCategory = MarketCategory.ECONOMICS,
    ) -> AdaptationResult:
        """Beta-Binomial update for edge threshold with guardrails."""
        self._check_min_observations(observations.total)
        self._check_cooldown()

        old_mean = prior.mean
        raw_posterior = update_beta_binomial(prior, observations)
        new_mean = raw_posterior.mean

        # Apply guardrails
        variance_reset = False
        human_review = False

        if self._check_variance_reset(raw_posterior.variance):
            raw_posterior = WEAK_BETA
            new_mean = raw_posterior.mean
            variance_reset = True

        clamped_mean = self._clamp_change(old_mean, new_mean)
        human_review = self._check_drift("edge_threshold", old_mean, clamped_mean)

        self._record_update()
        self._store_distribution("edge_threshold", raw_posterior)
        self._persist_state()

        magnitude = abs(clamped_mean - old_mean) if clamped_mean != old_mean else 1e-10
        reasoning = f"Beta-Binomial update: Beta({prior.alpha},{prior.beta}) → Beta({raw_posterior.alpha},{raw_posterior.beta})"
        if variance_reset:
            reasoning += " [VARIANCE RESET]"
        if human_review:
            reasoning += " [DRIFT FLAG]"

        confidence = self._compute_confidence(
            prior.variance, raw_posterior.variance, variance_reset
        )

        return AdaptationResult(
            category=category,
            direction=self._compute_direction(old_mean, clamped_mean),
            magnitude=magnitude,
            confidence=confidence,
            reasoning=reasoning,
            updated_params={
                "alpha": raw_posterior.alpha,
                "beta": raw_posterior.beta,
                "mean": clamped_mean,
            },
            method=UpdateMethod.BETA_BINOMIAL,
            human_review=human_review,
            variance_reset=variance_reset,
            update_count=len(self._update_timestamps),
            cooldown_remaining=self._cooldown_remaining(),
        )

    def update_dirichlet(
        self,
        prior: DirichletParams,
        observations: MultinomialObservations,
        category: MarketCategory = MarketCategory.ECONOMICS,
    ) -> AdaptationResult:
        """Dirichlet-Multinomial update for signal weights with guardrails."""
        self._check_min_observations(observations.total)
        self._check_cooldown()

        old_means = prior.means
        raw_posterior = update_dirichlet_multinomial(prior, observations)
        new_means = raw_posterior.means

        variance_reset = False
        human_review = False

        # Check variance reset on each component
        for _i, alpha_i in enumerate(raw_posterior.alphas):
            total = sum(raw_posterior.alphas)
            component_var = (alpha_i * (total - alpha_i)) / (total * total * (total + 1))
            if component_var < self.config.variance_reset_threshold:
                raw_posterior = WEAK_DIRICHLET
                new_means = raw_posterior.means
                variance_reset = True
                break

        # Clamp each weight component
        clamped_means: list[float] = []
        for _i, (old_w, new_w) in enumerate(zip(old_means, new_means, strict=True)):
            clamped = self._clamp_change(old_w, new_w)
            clamped_means.append(clamped)

        # Check drift on each component
        for i, (old_w, new_w) in enumerate(zip(old_means, clamped_means, strict=True)):
            if self._check_drift(f"signal_weight_{i}", old_w, new_w):
                human_review = True

        self._record_update()
        self._store_distribution("signal_weights", raw_posterior)
        self._persist_state()

        max_change = max(abs(n - o) for o, n in zip(old_means, clamped_means, strict=True))
        magnitude = max_change if max_change > 0 else 1e-10

        confidence = (
            0.0
            if variance_reset
            else min(raw_posterior.concentration / (raw_posterior.concentration + 10.0), 1.0)
        )

        reasoning = f"Dirichlet-Multinomial update: weights {old_means} → {clamped_means}"
        if variance_reset:
            reasoning += " [VARIANCE RESET]"
        if human_review:
            reasoning += " [DRIFT FLAG]"

        updated_params: dict[str, float] = {}
        for i, (alpha, mean) in enumerate(zip(raw_posterior.alphas, clamped_means, strict=True)):
            updated_params[f"alpha_{i}"] = alpha
            updated_params[f"weight_{i}"] = mean

        return AdaptationResult(
            category=category,
            direction=self._compute_direction(old_means[0], clamped_means[0]),
            magnitude=magnitude,
            confidence=confidence,
            reasoning=reasoning,
            updated_params=updated_params,
            method=UpdateMethod.DIRICHLET_MULTINOMIAL,
            human_review=human_review,
            variance_reset=variance_reset,
            update_count=len(self._update_timestamps),
            cooldown_remaining=self._cooldown_remaining(),
        )

    def update_normal(
        self,
        prior: NormalParams,
        observations: NormalObservations,
        category: MarketCategory = MarketCategory.ECONOMICS,
    ) -> AdaptationResult:
        """Normal-Normal update for mean reversion level with guardrails."""
        self._check_min_observations(observations.total)
        self._check_cooldown()

        old_mu = prior.mu
        raw_posterior = update_normal_normal(prior, observations)
        new_mu = raw_posterior.mu

        variance_reset = False
        human_review = False

        if self._check_variance_reset(raw_posterior.sigma_sq):
            raw_posterior = WEAK_NORMAL
            new_mu = raw_posterior.mu
            variance_reset = True

        clamped_mu = self._clamp_change(old_mu, new_mu)
        human_review = self._check_drift("mean_reversion", old_mu, clamped_mu)

        self._record_update()
        self._store_distribution("mean_reversion", raw_posterior)
        self._persist_state()

        magnitude = abs(clamped_mu - old_mu) if clamped_mu != old_mu else 1e-10
        confidence = self._compute_confidence(
            prior.sigma_sq, raw_posterior.sigma_sq, variance_reset
        )

        reasoning = f"Normal-Normal update: N({prior.mu},{prior.sigma_sq}) → N({raw_posterior.mu},{raw_posterior.sigma_sq})"
        if variance_reset:
            reasoning += " [VARIANCE RESET]"
        if human_review:
            reasoning += " [DRIFT FLAG]"

        return AdaptationResult(
            category=category,
            direction=self._compute_direction(old_mu, clamped_mu),
            magnitude=magnitude,
            confidence=confidence,
            reasoning=reasoning,
            updated_params={"mu": clamped_mu, "sigma_sq": raw_posterior.sigma_sq},
            method=UpdateMethod.NORMAL_NORMAL,
            human_review=human_review,
            variance_reset=variance_reset,
            update_count=len(self._update_timestamps),
            cooldown_remaining=self._cooldown_remaining(),
        )

    def update_gamma(
        self,
        prior: GammaParams,
        observations: ExponentialObservations,
        category: MarketCategory = MarketCategory.ECONOMICS,
    ) -> AdaptationResult:
        """Gamma-Exponential update for momentum decay rate with guardrails."""
        self._check_min_observations(observations.total)
        self._check_cooldown()

        old_mean = prior.mean
        raw_posterior = update_gamma_exponential(prior, observations)
        new_mean = raw_posterior.mean

        variance_reset = False
        human_review = False

        if self._check_variance_reset(raw_posterior.variance):
            raw_posterior = WEAK_GAMMA
            new_mean = raw_posterior.mean
            variance_reset = True

        clamped_mean = self._clamp_change(old_mean, new_mean)
        human_review = self._check_drift("momentum_decay", old_mean, clamped_mean)

        self._record_update()
        self._store_distribution("momentum_decay", raw_posterior)
        self._persist_state()

        magnitude = abs(clamped_mean - old_mean) if clamped_mean != old_mean else 1e-10
        confidence = self._compute_confidence(
            prior.variance, raw_posterior.variance, variance_reset
        )

        reasoning = f"Gamma-Exponential update: Gamma({prior.alpha},{prior.beta}) → Gamma({raw_posterior.alpha},{raw_posterior.beta})"
        if variance_reset:
            reasoning += " [VARIANCE RESET]"
        if human_review:
            reasoning += " [DRIFT FLAG]"

        return AdaptationResult(
            category=category,
            direction=self._compute_direction(old_mean, clamped_mean),
            magnitude=magnitude,
            confidence=confidence,
            reasoning=reasoning,
            updated_params={
                "alpha": raw_posterior.alpha,
                "beta": raw_posterior.beta,
                "mean": clamped_mean,
            },
            method=UpdateMethod.GAMMA_EXPONENTIAL,
            human_review=human_review,
            variance_reset=variance_reset,
            update_count=len(self._update_timestamps),
            cooldown_remaining=self._cooldown_remaining(),
        )
