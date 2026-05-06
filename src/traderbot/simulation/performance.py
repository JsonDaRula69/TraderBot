"""Performance metrics for backtest results and strategy comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from traderbot.analysis.portfolio import (
    brier_score as _portfolio_brier,
)
from traderbot.analysis.portfolio import (
    calmar_ratio,
    max_drawdown,
    sharpe_ratio,
)

if TYPE_CHECKING:
    from traderbot.simulation.engine import BacktestResult, BacktestTrade


class StrategyComparison(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    strategy_a_name: str
    strategy_b_name: str
    total_pnl_cents_a: int
    total_pnl_cents_b: int
    trade_count_a: int
    trade_count_b: int
    win_rate_a: float | None
    win_rate_b: float | None
    sharpe_ratio_a: float | None
    sharpe_ratio_b: float | None
    max_drawdown_a: float | None
    max_drawdown_b: float | None
    brier_score_a: float | None
    brier_score_b: float | None
    edge_capture_a: float | None
    edge_capture_b: float | None
    fill_rate_a: float | None
    fill_rate_b: float | None
    calmar_ratio_a: float | None
    calmar_ratio_b: float | None
    pnl_winner: str


def compute_brier_score(trades: list[BacktestTrade]) -> float | None:
    """Brier score from backtest trades using predicted vs actual outcomes.

    Uses entry price as the implied predicted probability (price/100 = prob YES).
    For YES trades: predicted = entry_price/100, actual = 1 if pnl > 0 else 0.
    For NO trades: predicted = 1 - entry_price/100, actual = 1 if pnl > 0 else 0.
    """
    if not trades:
        return None

    predictions: list[tuple[float, bool]] = []
    for t in trades:
        if t.direction == "yes":
            predicted = t.entry_price_cents / 100.0
        else:
            predicted = 1.0 - (t.entry_price_cents / 100.0)
        actual = t.pnl_cents > 0
        predictions.append((predicted, actual))

    return _portfolio_brier(predictions)


def compute_fill_rate(trades: list[BacktestTrade], total_signals: int) -> float | None:
    if total_signals <= 0:
        return None
    return len(trades) / total_signals


def compute_edge_capture(trades: list[BacktestTrade]) -> float | None:
    """Average edge captured per trade as fraction of theoretical edge.

    Edge capture = actual edge realized / maximum possible edge per trade.
    For a YES trade at price p with outcome: actual edge = (pnl/100) vs max edge = |prob - p/100|.
    """
    if not trades:
        return None

    captured: list[float] = []
    for t in trades:
        market_prob = t.entry_price_cents / 100.0
        if t.direction == "yes":
            theoretical_edge = abs(1.0 - market_prob) if t.pnl_cents > 0 else abs(0.0 - market_prob)
        else:
            theoretical_edge = abs(0.0 - (1.0 - market_prob)) if t.pnl_cents > 0 else abs(1.0 - (1.0 - market_prob))

        if theoretical_edge < 1e-9:
            continue

        actual_edge = abs(t.pnl_cents) / (100.0 * t.quantity)
        captured.append(actual_edge / theoretical_edge)

    if not captured:
        return None
    return sum(captured) / len(captured)


def compute_win_rate(trades: list[BacktestTrade]) -> float | None:
    if not trades:
        return None
    wins = sum(1 for t in trades if t.pnl_cents > 0)
    return wins / len(trades)


def compute_sharpe(
    trades: list[BacktestTrade], risk_free: float = 0.0
) -> float | None:
    if len(trades) < 2:
        return None
    returns = [float(t.pnl_cents) for t in trades]
    return sharpe_ratio(returns, risk_free)


def compute_max_drawdown(trades: list[BacktestTrade], initial_bankroll_cents: int) -> float | None:
    if not trades:
        return None
    cumulative_values: list[int] = [initial_bankroll_cents]
    for t in trades:
        cumulative_values.append(cumulative_values[-1] + t.pnl_cents)
    return max_drawdown(cumulative_values)


def compute_calmar(
    trades: list[BacktestTrade], initial_bankroll_cents: int
) -> float | None:
    if not trades:
        return None
    total_pnl = sum(t.pnl_cents for t in trades)
    if initial_bankroll_cents <= 0:
        return None
    annualized_return = (total_pnl / initial_bankroll_cents) * (252 / max(len(trades), 1))
    dd = compute_max_drawdown(trades, initial_bankroll_cents)
    if dd is None or dd == 0.0:
        return None
    return calmar_ratio(annualized_return, dd)


def compute_metrics(
    result: BacktestResult, initial_bankroll_cents: int = 100_000_00, total_signals: int = 0
) -> dict[str, Any]:
    trades = result.trades
    return {
        "total_pnl_cents": result.total_pnl_cents,
        "trade_count": result.trade_count,
        "win_rate": compute_win_rate(trades),
        "sharpe_ratio": compute_sharpe(trades),
        "max_drawdown": compute_max_drawdown(trades, initial_bankroll_cents),
        "brier_score": compute_brier_score(trades),
        "edge_capture": compute_edge_capture(trades),
        "fill_rate": compute_fill_rate(trades, total_signals) if total_signals > 0 else result.fill_rate,
        "calmar_ratio": compute_calmar(trades, initial_bankroll_cents),
    }


def compare_strategies(
    result_a: BacktestResult,
    result_b: BacktestResult,
    name_a: str = "Strategy A",
    name_b: str = "Strategy B",
    initial_bankroll_cents: int = 100_000_00,
) -> StrategyComparison:
    metrics_a = compute_metrics(result_a, initial_bankroll_cents)
    metrics_b = compute_metrics(result_b, initial_bankroll_cents)

    pnl_a = result_a.total_pnl_cents
    pnl_b = result_b.total_pnl_cents
    if pnl_a > pnl_b:
        pnl_winner = name_a
    elif pnl_b > pnl_a:
        pnl_winner = name_b
    else:
        pnl_winner = "tie"

    return StrategyComparison(
        strategy_a_name=name_a,
        strategy_b_name=name_b,
        total_pnl_cents_a=pnl_a,
        total_pnl_cents_b=pnl_b,
        trade_count_a=result_a.trade_count,
        trade_count_b=result_b.trade_count,
        win_rate_a=metrics_a["win_rate"],
        win_rate_b=metrics_b["win_rate"],
        sharpe_ratio_a=metrics_a["sharpe_ratio"],
        sharpe_ratio_b=metrics_b["sharpe_ratio"],
        max_drawdown_a=metrics_a["max_drawdown"],
        max_drawdown_b=metrics_b["max_drawdown"],
        brier_score_a=metrics_a["brier_score"],
        brier_score_b=metrics_b["brier_score"],
        edge_capture_a=metrics_a["edge_capture"],
        edge_capture_b=metrics_b["edge_capture"],
        fill_rate_a=metrics_a["fill_rate"],
        fill_rate_b=metrics_b["fill_rate"],
        calmar_ratio_a=metrics_a["calmar_ratio"],
        calmar_ratio_b=metrics_b["calmar_ratio"],
        pnl_winner=pnl_winner,
    )


class MultiStrategyComparison(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    profiles: list[StrategyComparison]


def compare_strategies_multi(
    results: dict[str, BacktestResult],
    initial_bankroll_cents: int = 100_000_00,
) -> MultiStrategyComparison:
    """Compare N named strategies (e.g. profiles) pairwise against each other."""
    names = sorted(results.keys())
    pairwise: list[StrategyComparison] = []
    for i, name_a in enumerate(names):
        for name_b in names[i + 1:]:
            pairwise.append(
                compare_strategies(
                    results[name_a],
                    results[name_b],
                    name_a=name_a,
                    name_b=name_b,
                    initial_bankroll_cents=initial_bankroll_cents,
                )
            )
    return MultiStrategyComparison(profiles=pairwise)
