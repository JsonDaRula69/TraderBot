"""Tests for portfolio analytics: calibration, risk metrics, and edge realization."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from traderbot.analysis.portfolio import (
    PortfolioMetrics,
    brier_score,
    calibration_curve,
    calmar_ratio,
    edge_realization,
    max_drawdown,
    sharpe_ratio,
    win_rate,
)
from traderbot.kalshi.models import Decision


def _make_decision(
    direction: str = "yes",
    quantity: int = 10,
    price: int = 50,
    actual_result: bool | None = None,
    outcome: str = "executed",
    edge_estimate: float = 0.1,
    **overrides,
) -> Decision:
    defaults = dict(
        timestamp=datetime.now(UTC),
        ticker="KX-TEST",
        direction=direction,
        quantity=quantity,
        price=price,
        signal_strength=0.7,
        confidence=0.8,
        edge_estimate=edge_estimate,
        risk_checks={"max_position": True},
        outcome=outcome,
        rejection_reason=None,
        actual_result=actual_result,
    )
    defaults.update(overrides)
    return Decision(**defaults)


# --- brier_score ---


@pytest.mark.unit
def test_brier_score_perfect() -> None:
    assert brier_score([(1.0, True), (0.0, False)]) == 0.0


@pytest.mark.unit
def test_brier_score_worst() -> None:
    assert brier_score([(1.0, False), (0.0, True)]) == 1.0


@pytest.mark.unit
def test_brier_score_empty() -> None:
    assert brier_score([]) == 0.0


@pytest.mark.unit
def test_brier_score_mixed() -> None:
    # (0.7, True) -> (0.7-1)^2 = 0.09
    # (0.3, False) -> (0.3-0)^2 = 0.09
    # mean = 0.09
    assert brier_score([(0.7, True), (0.3, False)]) == pytest.approx(0.09)


# --- win_rate ---


@pytest.mark.unit
def test_win_rate_mixed() -> None:
    decisions = [
        _make_decision(direction="yes", actual_result=True),
        _make_decision(direction="yes", actual_result=False),
        _make_decision(direction="no", actual_result=False),
        _make_decision(direction="no", actual_result=True),
    ]
    # yes+True=win, yes+False=loss, no+False=win, no+True=loss => 2/4 = 0.5
    assert win_rate(decisions) == pytest.approx(0.5)


@pytest.mark.unit
def test_win_rate_no_qualifying() -> None:
    decisions = [
        _make_decision(outcome="held"),
        _make_decision(outcome="rejected"),
    ]
    assert win_rate(decisions) == 0.0


@pytest.mark.unit
def test_win_rate_all_wins() -> None:
    decisions = [
        _make_decision(direction="yes", actual_result=True),
        _make_decision(direction="no", actual_result=False),
    ]
    assert win_rate(decisions) == 1.0


@pytest.mark.unit
def test_win_rate_skips_none_result() -> None:
    decisions = [
        _make_decision(actual_result=None),
    ]
    assert win_rate(decisions) == 0.0


# --- sharpe_ratio ---


@pytest.mark.unit
def test_sharpe_ratio_known() -> None:
    returns = [0.01, 0.02, -0.01, 0.03]
    result = sharpe_ratio(returns)
    assert result is not None
    mean_r = sum(returns) / len(returns)
    var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    expected = (mean_r / math.sqrt(var_r)) * math.sqrt(252)
    assert result == pytest.approx(expected)


@pytest.mark.unit
def test_sharpe_ratio_insufficient() -> None:
    assert sharpe_ratio([0.01]) is None
    assert sharpe_ratio([]) is None


@pytest.mark.unit
def test_sharpe_ratio_zero_std() -> None:
    assert sharpe_ratio([0.05, 0.05, 0.05]) is None


# --- max_drawdown ---


@pytest.mark.unit
def test_max_drawdown_typical() -> None:
    values = [100, 120, 110, 130, 90]
    # peak=130, trough=90, dd=(130-90)/130 ≈ 0.3077
    assert max_drawdown(values) == pytest.approx((130 - 90) / 130)


@pytest.mark.unit
def test_max_drawdown_always_increasing() -> None:
    values = [100, 110, 120, 130]
    assert max_drawdown(values) == 0.0


@pytest.mark.unit
def test_max_drawdown_empty() -> None:
    assert max_drawdown([]) == 0.0


@pytest.mark.unit
def test_max_drawdown_single() -> None:
    assert max_drawdown([500]) == 0.0


@pytest.mark.unit
def test_max_drawdown_with_zero_peak() -> None:
    # Leading zero should be skipped (peak stays 0 until first positive)
    values = [0, 0, 100, 80]
    # peak=100, dd=(100-80)/100 = 0.2
    assert max_drawdown(values) == pytest.approx(0.2)


# --- calmar_ratio ---


@pytest.mark.unit
def test_calmar_ratio_zero_drawdown() -> None:
    assert calmar_ratio(0.15, 0.0) is None


@pytest.mark.unit
def test_calmar_ratio_normal() -> None:
    assert calmar_ratio(0.3, 0.1) == pytest.approx(3.0)


# --- calibration_curve ---


@pytest.mark.unit
def test_calibration_curve_uniform() -> None:
    # 10 predictions, one per 0.05-wide range within each bucket
    predictions = [
        (0.05, True),  # bucket 0
        (0.15, False),  # bucket 1
        (0.25, True),  # bucket 2
        (0.35, True),  # bucket 3
        (0.45, False),  # bucket 4
        (0.55, True),  # bucket 5
        (0.65, True),  # bucket 6
        (0.75, False),  # bucket 7
        (0.85, True),  # bucket 8
        (0.95, True),  # bucket 9
    ]
    curve = calibration_curve(predictions)
    assert len(curve) == 10
    # Each bucket has one prediction
    for _mean_pred, obs_freq in curve:
        assert obs_freq in (0.0, 1.0)


@pytest.mark.unit
def test_calibration_curve_empty() -> None:
    assert calibration_curve([]) == []


@pytest.mark.unit
def test_calibration_curve_bucket_aggregation() -> None:
    # Two predictions in same bucket (0-0.1)
    predictions = [(0.03, True), (0.07, False)]
    curve = calibration_curve(predictions)
    assert len(curve) == 1
    mean_pred, obs_freq = curve[0]
    assert mean_pred == pytest.approx(0.05)
    assert obs_freq == pytest.approx(0.5)


# --- edge_realization ---


@pytest.mark.unit
def test_edge_realization_winning_yes() -> None:
    # direction=yes, actual_result=True, price=50, qty=10, edge_estimate=0.1
    # actual_pnl = (100 - 50) * 10 = 500
    # expected_pnl = 0.1 * 10 * 50 = 50
    # realization = (500 - 50) / 50 = 9.0
    d = _make_decision(
        direction="yes", actual_result=True, price=50, quantity=10, edge_estimate=0.1
    )
    result = edge_realization([d])
    assert result == pytest.approx(9.0)


@pytest.mark.unit
def test_edge_realization_losing_yes() -> None:
    # direction=yes, actual_result=False, price=60, qty=5, edge_estimate=0.2
    # actual_pnl = -60 * 5 = -300
    # expected_pnl = 0.2 * 5 * 60 = 60
    # realization = (-300 - 60) / 60 = -6.0
    d = _make_decision(
        direction="yes", actual_result=False, price=60, quantity=5, edge_estimate=0.2
    )
    result = edge_realization([d])
    assert result == pytest.approx(-6.0)


@pytest.mark.unit
def test_edge_realization_no_direction() -> None:
    # direction=no, actual_result=False (win for no), price=40, qty=10, edge_estimate=0.15
    # actual_pnl = (100 - 40) * 10 = 600
    # expected_pnl = 0.15 * 10 * 40 = 60
    # realization = (600 - 60) / 60 = 9.0
    d = _make_decision(
        direction="no", actual_result=False, price=40, quantity=10, edge_estimate=0.15
    )
    result = edge_realization([d])
    assert result == pytest.approx(9.0)


@pytest.mark.unit
def test_edge_realization_no_qualifying() -> None:
    assert edge_realization([]) == 0.0
    assert edge_realization([_make_decision(outcome="held")]) == 0.0


@pytest.mark.unit
def test_edge_realization_zero_edge_skipped() -> None:
    d = _make_decision(direction="yes", actual_result=True, edge_estimate=0.0)
    assert edge_realization([d]) == 0.0


# --- PortfolioMetrics model ---


@pytest.mark.unit
def test_portfolio_metrics_model() -> None:
    m = PortfolioMetrics(
        total_trades=10,
        win_rate=0.6,
        brier_score=0.15,
        sharpe_ratio=1.5,
        max_drawdown_pct=0.1,
        calmar_ratio=3.0,
        total_pnl_cents=5000,
        avg_edge_realization=0.8,
    )
    assert m.total_trades == 10
    assert m.win_rate == 0.6
    assert m.sharpe_ratio == 1.5
    assert m.total_pnl_cents == 5000
