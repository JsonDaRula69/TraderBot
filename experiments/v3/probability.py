"""Bayesian probability computation using scipy.stats.norm with city-specific error distributions."""

from scipy.stats import norm


def prob_less(forecast: float, threshold: float, city_bias: float, city_mae: float) -> float:
    """P(actual < threshold) given forecast and city-specific error distribution."""
    loc = forecast - city_bias
    return norm.cdf(threshold, loc=loc, scale=city_mae)


def prob_greater(forecast: float, threshold: float, city_bias: float, city_mae: float) -> float:
    """P(actual > threshold) — uses 1 - norm.cdf, NOT prob_between formula."""
    loc = forecast - city_bias
    return 1.0 - norm.cdf(threshold, loc=loc, scale=city_mae)


def prob_between(forecast: float, floor: float, city_bias: float, city_mae: float) -> float:
    """P(actual in [floor, floor+1)) given forecast and city-specific error distribution."""
    loc = forecast - city_bias
    return norm.cdf(floor + 1.0, loc=loc, scale=city_mae) - norm.cdf(floor, loc=loc, scale=city_mae)


def compute_ci(prob: float, city_mae: float, sample_count: int) -> tuple[float, float]:
    """95% confidence interval via Wilson score interval approximation."""
    if sample_count < 1:
        return (0.0, 1.0)
    z = 1.96
    se = city_mae / (sample_count**0.5)
    lower = max(0.0, prob - z * se / 10.0)
    upper = min(1.0, prob + z * se / 10.0)
    return (lower, upper)
