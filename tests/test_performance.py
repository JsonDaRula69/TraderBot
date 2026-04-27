"""Tests for simulation/performance.py — performance metrics and strategy comparison."""

from __future__ import annotations

import pytest

from traderbot.simulation.engine import BacktestResult, BacktestTrade
from traderbot.simulation.performance import (
    StrategyComparison,
    compare_strategies,
    compute_brier_score,
    compute_calmar,
    compute_edge_capture,
    compute_fill_rate,
    compute_max_drawdown,
    compute_metrics,
    compute_sharpe,
    compute_win_rate,
)


def _make_trade(
    ticker: str = "KX-TEST",
    direction: str = "yes",
    entry_price_cents: int = 65,
    exit_price_cents: int = 100,
    quantity: int = 10,
    pnl_cents: int = 350,
    timestamp: str = "2026-03-31T23:59:59+00:00",
) -> BacktestTrade:
    return BacktestTrade(
        ticker=ticker,
        direction=direction,
        entry_price_cents=entry_price_cents,
        exit_price_cents=exit_price_cents,
        quantity=quantity,
        pnl_cents=pnl_cents,
        timestamp=timestamp,
    )


def _make_result(
    trade_count: int = 1,
    total_pnl_cents: int = 350,
    trades: list[BacktestTrade] | None = None,
    winning_trades: int = 1,
    losing_trades: int = 0,
    win_rate: float | None = 1.0,
    sharpe_ratio: float | None = 5.0,
    max_drawdown_pct: float | None = 0.05,
    brier_score: float | None = 0.12,
    edge_capture: float | None = 0.6,
    fill_rate: float | None = 0.8,
) -> BacktestResult:
    if trades is None:
        trades = [_make_trade()]
    return BacktestResult(
        trade_count=trade_count,
        total_pnl_cents=total_pnl_cents,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        sharpe_ratio=sharpe_ratio,
        max_drawdown_pct=max_drawdown_pct,
        brier_score=brier_score,
        edge_capture=edge_capture,
        fill_rate=fill_rate,
        trades=trades,
    )


# --- compute_brier_score ---


class TestBrierScore:
    def test_empty_trades_returns_none(self):
        assert compute_brier_score([]) is None

    def test_perfect_yes_predictions(self):
        trade = _make_trade(direction="yes", entry_price_cents=100, exit_price_cents=100, pnl_cents=0, quantity=1)
        score = compute_brier_score([trade])
        assert score is not None
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_yes_win_at_high_price(self):
        trade = _make_trade(direction="yes", entry_price_cents=95, exit_price_cents=100, pnl_cents=50, quantity=10)
        score = compute_brier_score([trade])
        assert score is not None
        predicted = 0.95
        expected = (predicted - 1.0) ** 2
        assert score == pytest.approx(expected, abs=1e-6)

    def test_wrong_yes_predictions(self):
        trade = _make_trade(direction="yes", entry_price_cents=90, pnl_cents=-900)
        score = compute_brier_score([trade])
        assert score is not None
        assert score == pytest.approx(0.81, abs=1e-6)

    def test_no_direction_uses_inverse_prob(self):
        trade = _make_trade(direction="no", entry_price_cents=90, pnl_cents=100)
        score = compute_brier_score([trade])
        assert score is not None
        predicted_no = 1.0 - 0.9
        actual = 1.0
        expected = (predicted_no - actual) ** 2
        assert score == pytest.approx(expected, abs=1e-6)

    def test_mixed_directions(self):
        yes_win = _make_trade(direction="yes", entry_price_cents=70, pnl_cents=300)
        no_win = _make_trade(
            ticker="KX-NO",
            direction="no",
            entry_price_cents=30,
            pnl_cents=700,
        )
        score = compute_brier_score([yes_win, no_win])
        assert score is not None
        assert 0.0 <= score <= 1.0


# --- compute_fill_rate ---


class TestFillRate:
    def test_zero_signals_returns_none(self):
        assert compute_fill_rate([], 0) is None

    def test_all_filled(self):
        trades = [_make_trade(), _make_trade(ticker="KX-B")]
        assert compute_fill_rate(trades, 2) == 1.0

    def test_partial_fill(self):
        trades = [_make_trade()]
        assert compute_fill_rate(trades, 4) == 0.25

    def test_no_trades_zero_fill(self):
        assert compute_fill_rate([], 5) == 0.0


# --- compute_edge_capture ---


class TestEdgeCapture:
    def test_empty_trades_returns_none(self):
        assert compute_edge_capture([]) is None

    def test_winning_yes_captures_edge(self):
        trade = _make_trade(direction="yes", entry_price_cents=50, pnl_cents=500, quantity=10)
        result = compute_edge_capture([trade])
        assert result > 0.0

    def test_losing_yes_trade(self):
        trade = _make_trade(direction="yes", entry_price_cents=50, pnl_cents=-500, quantity=10)
        result = compute_edge_capture([trade])
        assert result >= 0.0

    def test_no_direction(self):
        trade = _make_trade(direction="no", entry_price_cents=50, pnl_cents=500, quantity=10)
        result = compute_edge_capture([trade])
        assert result >= 0.0

    def test_zero_pnl_gives_zero_capture(self):
        trade = _make_trade(direction="yes", entry_price_cents=50, pnl_cents=0, quantity=10)
        result = compute_edge_capture([trade])
        assert result == 0.0


# --- compute_win_rate ---


class TestWinRate:
    def test_empty_trades_returns_none(self):
        assert compute_win_rate([]) is None

    def test_all_winners(self):
        trades = [_make_trade(pnl_cents=100), _make_trade(pnl_cents=200)]
        assert compute_win_rate(trades) == 1.0

    def test_half_winners(self):
        trades = [_make_trade(pnl_cents=100), _make_trade(pnl_cents=-100)]
        assert compute_win_rate(trades) == 0.5

    def test_zero_pnl_counts_as_loss(self):
        trades = [_make_trade(pnl_cents=100), _make_trade(pnl_cents=0)]
        assert compute_win_rate(trades) == 0.5


# --- compute_sharpe ---


class TestSharpe:
    def test_empty_trades_returns_none(self):
        assert compute_sharpe([]) is None

    def test_single_trade_returns_none(self):
        assert compute_sharpe([_make_trade()]) is None

    def test_positive_sharpe(self):
        trades = [_make_trade(pnl_cents=500), _make_trade(pnl_cents=300, ticker="KX-B")]
        result = compute_sharpe(trades)
        assert result > 0


# --- compute_max_drawdown ---


class TestMaxDrawdown:
    def test_empty_trades_returns_none(self):
        assert compute_max_drawdown([], 100_000_00) is None

    def test_no_drawdown(self):
        trades = [_make_trade(pnl_cents=100), _make_trade(pnl_cents=200, ticker="KX-B")]
        dd = compute_max_drawdown(trades, 100_000_00)
        assert dd is not None
        assert dd == 0.0

    def test_with_loss(self):
        trade = _make_trade(pnl_cents=-5000)
        dd = compute_max_drawdown([trade], 100_000_00)
        assert dd is not None
        assert dd > 0.0


# --- compute_calmar ---


class TestCalmar:
    def test_empty_trades_returns_none(self):
        assert compute_calmar([], 100_000_00) is None

    def test_zero_drawdown_returns_none(self):
        trades = [_make_trade(pnl_cents=100), _make_trade(pnl_cents=200, ticker="KX-B")]
        assert compute_calmar(trades, 100_000_00) is None

    def test_with_drawdown(self):
        trades = [_make_trade(pnl_cents=-5000)]
        result = compute_calmar(trades, 100_000_00)
        assert result is not None
        assert result < 0


# --- compute_metrics ---


class TestComputeMetrics:
    def test_empty_result(self):
        result = BacktestResult(
            trade_count=0, total_pnl_cents=0, winning_trades=0, losing_trades=0,
            win_rate=None, sharpe_ratio=None, max_drawdown_pct=None,
            brier_score=None, edge_capture=None, fill_rate=None, trades=[],
        )
        metrics = compute_metrics(result)
        assert metrics["total_pnl_cents"] == 0
        assert metrics["trade_count"] == 0
        assert metrics["win_rate"] is None
        assert metrics["brier_score"] is None
        assert metrics["edge_capture"] is None

    def test_with_trades(self):
        result = _make_result()
        metrics = compute_metrics(result)
        assert metrics["total_pnl_cents"] == 350
        assert metrics["trade_count"] == 1
        assert metrics["win_rate"] == 1.0

    def test_total_signals_provides_fill_rate(self):
        result = _make_result()
        metrics = compute_metrics(result, total_signals=2)
        assert metrics["fill_rate"] == 0.5


# --- compare_strategies ---


class TestCompareStrategies:
    def test_basic_comparison(self):
        a = _make_result(total_pnl_cents=1000, winning_trades=2, losing_trades=0)
        b = _make_result(total_pnl_cents=500, winning_trades=1, losing_trades=0)
        comp = compare_strategies(a, b, "Alpha", "Beta")
        assert isinstance(comp, StrategyComparison)
        assert comp.strategy_a_name == "Alpha"
        assert comp.strategy_b_name == "Beta"
        assert comp.total_pnl_cents_a == 1000
        assert comp.total_pnl_cents_b == 500
        assert comp.pnl_winner == "Alpha"

    def test_tie_pnl(self):
        a = _make_result(total_pnl_cents=500)
        b = _make_result(total_pnl_cents=500)
        comp = compare_strategies(a, b)
        assert comp.pnl_winner == "tie"

    def test_b_wins(self):
        a = _make_result(total_pnl_cents=100)
        b = _make_result(total_pnl_cents=900)
        comp = compare_strategies(a, b, "A", "B")
        assert comp.pnl_winner == "B"

    def test_all_metrics_populated(self):
        trades = [_make_trade(pnl_cents=500), _make_trade(pnl_cents=-200, ticker="KX-B")]
        result = BacktestResult(
            trade_count=2, total_pnl_cents=300, winning_trades=1, losing_trades=1,
            win_rate=0.5, sharpe_ratio=2.0, max_drawdown_pct=0.02,
            brier_score=0.25, edge_capture=0.5, fill_rate=0.8, trades=trades,
        )
        comp = compare_strategies(result, result)
        assert comp.win_rate_a == 0.5
        assert comp.sharpe_ratio_a is not None
        assert comp.brier_score_a is not None
        assert comp.edge_capture_a is not None

    def test_none_metrics_with_zero_trades(self):
        empty = BacktestResult(
            trade_count=0, total_pnl_cents=0, winning_trades=0, losing_trades=0,
            win_rate=None, sharpe_ratio=None, max_drawdown_pct=None,
            brier_score=None, edge_capture=None, fill_rate=None, trades=[],
        )
        comp = compare_strategies(empty, empty)
        assert comp.win_rate_a is None
        assert comp.sharpe_ratio_a is None
        assert comp.brier_score_a is None


# --- StrategyComparison model validation ---


class TestStrategyComparisonModel:
    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            StrategyComparison(
                strategy_a_name="A", strategy_b_name="B",
                total_pnl_cents_a=0, total_pnl_cents_b=0,
                trade_count_a=0, trade_count_b=0,
                win_rate_a=None, win_rate_b=None,
                sharpe_ratio_a=None, sharpe_ratio_b=None,
                max_drawdown_a=None, max_drawdown_b=None,
                brier_score_a=None, brier_score_b=None,
                edge_capture_a=None, edge_capture_b=None,
                fill_rate_a=None, fill_rate_b=None,
                calmar_ratio_a=None, calmar_ratio_b=None,
                pnl_winner="tie",
                extra_field="bad",
            )