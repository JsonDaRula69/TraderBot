"""Portfolio analytics: calibration, risk metrics, and edge realization."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import math

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from traderbot.kalshi.models import Decision


class PortfolioMetrics(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total_trades: int
    win_rate: float
    brier_score: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    calmar_ratio: float | None
    total_pnl_cents: int
    avg_edge_realization: float


def win_rate(decisions: list[Decision]) -> float:
    """Fraction of executed decisions that predicted correctly."""
    qualifying = [d for d in decisions if d.outcome == "executed" and d.actual_result is not None]
    if not qualifying:
        return 0.0
    wins = sum(
        1
        for d in qualifying
        if (d.direction == "yes" and d.actual_result is True)
        or (d.direction == "no" and d.actual_result is False)
    )
    return wins / len(qualifying)


def brier_score(predictions: list[tuple[float, bool]]) -> float:
    """Mean squared error of probabilistic predictions."""
    if not predictions:
        return 0.0
    total = sum((prob - float(actual)) ** 2 for prob, actual in predictions)
    return total / len(predictions)


def calibration_curve(
    predictions: list[tuple[float, bool]], buckets: int = 10
) -> list[tuple[float, float]]:
    """Observed frequency per predicted-probability bucket."""
    bin_sums: dict[int, list[tuple[float, bool]]] = {}
    for prob, actual in predictions:
        idx = min(int(prob * buckets), buckets - 1)
        bin_sums.setdefault(idx, []).append((prob, actual))

    result: list[tuple[float, float]] = []
    for i in range(buckets):
        if i not in bin_sums:
            continue
        items = bin_sums[i]
        mean_pred = sum(p for p, _ in items) / len(items)
        obs_freq = sum(1 for _, a in items if a) / len(items)
        result.append((mean_pred, obs_freq))
    return result


def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float | None:
    """Annualized Sharpe ratio from periodic returns."""
    if len(returns) < 2:
        return None
    excess = [r - risk_free for r in returns]
    mean_excess = sum(excess) / len(excess)
    variance = sum((e - mean_excess) ** 2 for e in excess) / (len(excess) - 1)
    if variance < 1e-15:
        return None
    return mean_excess / math.sqrt(variance) * math.sqrt(252)


def max_drawdown(values: list[int]) -> float:
    """Maximum fractional drawdown from running peak."""
    if not values:
        return 0.0
    peak = 0
    max_dd = 0.0
    for val in values:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def calmar_ratio(annualized_return: float, max_dd: float) -> float | None:
    """Annualized return divided by maximum drawdown."""
    if max_dd == 0.0:
        return None
    return annualized_return / max_dd


def edge_realization(decisions: list[Decision]) -> float:
    """Average ratio of actual-vs-expected PnL per executed decision."""
    qualifying: list[tuple[int, int]] = []
    for d in decisions:
        if d.outcome != "executed" or d.actual_result is None:
            continue
        # actual PnL in cents
        if d.direction == "yes":
            if d.actual_result is True:
                actual_pnl = (100 - d.price) * d.quantity
            else:
                actual_pnl = -d.price * d.quantity
        elif d.direction == "no":
            if d.actual_result is False:
                actual_pnl = (100 - d.price) * d.quantity
            else:
                actual_pnl = -d.price * d.quantity
        else:
            continue

        expected_pnl = abs(d.edge_estimate) * d.quantity * d.price
        if expected_pnl == 0:
            continue
        qualifying.append((actual_pnl, expected_pnl))

    if not qualifying:
        return 0.0
    realization_sum = sum((actual - expected) / abs(expected) for actual, expected in qualifying)
    return realization_sum / len(qualifying)
