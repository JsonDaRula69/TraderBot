"""Immutable hard-limits enforcement — the guardrail layer."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from traderbot.kalshi.models import PortfolioState, RiskCheckResult, TradeRequest

HARD_LIMITS: Final[dict[str, float | int]] = MappingProxyType(
    {
        "max_position_per_market_pct": 0.05,
        "max_daily_loss_pct": 0.02,
        "max_drawdown_pct": 0.10,
        "min_liquidity_threshold": 1000,
        "max_open_positions": 20,
        "min_edge_pct": 0.03,
    }
)


def check_position_limit(
    current_position_value_cents: int,
    order_value_cents: int,
    portfolio_value_cents: int,
) -> RiskCheckResult:
    total = current_position_value_cents + order_value_cents
    limit_value = portfolio_value_cents * HARD_LIMITS["max_position_per_market_pct"]
    passed = total <= limit_value
    return RiskCheckResult(
        passed=passed,
        limit_name="position_limit",
        current_value=total,
        limit_value=limit_value,
        rejection_reason=None if passed else "Position would exceed 5% portfolio limit",
    )


def check_daily_loss(today_loss_cents: int, portfolio_value_cents: int) -> RiskCheckResult:
    limit_value = portfolio_value_cents * HARD_LIMITS["max_daily_loss_pct"]
    passed = today_loss_cents <= limit_value
    return RiskCheckResult(
        passed=passed,
        limit_name="daily_loss",
        current_value=today_loss_cents,
        limit_value=limit_value,
        rejection_reason=None if passed else "Daily loss exceeds 2% limit",
    )


def check_drawdown(peak_value_cents: int, current_value_cents: int) -> RiskCheckResult:
    if peak_value_cents <= 0:
        return RiskCheckResult(
            passed=True,
            limit_name="drawdown",
            current_value=0.0,
            limit_value=HARD_LIMITS["max_drawdown_pct"],
        )
    drawdown = (peak_value_cents - current_value_cents) / peak_value_cents
    passed = drawdown <= HARD_LIMITS["max_drawdown_pct"]
    return RiskCheckResult(
        passed=passed,
        limit_name="drawdown",
        current_value=drawdown,
        limit_value=HARD_LIMITS["max_drawdown_pct"],
        rejection_reason=None if passed else "Drawdown exceeds 10% limit",
    )


def check_liquidity(open_interest: int) -> RiskCheckResult:
    threshold = HARD_LIMITS["min_liquidity_threshold"]
    passed = open_interest >= threshold
    return RiskCheckResult(
        passed=passed,
        limit_name="liquidity",
        current_value=open_interest,
        limit_value=threshold,
        rejection_reason=None if passed else "Market liquidity below 1,000 threshold",
    )


def check_max_positions(current_positions: int) -> RiskCheckResult:
    max_pos = HARD_LIMITS["max_open_positions"]
    passed = current_positions < max_pos
    return RiskCheckResult(
        passed=passed,
        limit_name="max_positions",
        current_value=current_positions,
        limit_value=max_pos,
        rejection_reason=None if passed else "Open positions exceed 20 limit",
    )


def check_min_edge(estimated_prob: float, market_price: float) -> RiskCheckResult:
    edge = abs(estimated_prob - market_price)
    min_edge = HARD_LIMITS["min_edge_pct"]
    passed = edge >= min_edge
    return RiskCheckResult(
        passed=passed,
        limit_name="min_edge",
        current_value=edge,
        limit_value=min_edge,
        rejection_reason=None if passed else "Edge below 3% minimum",
    )


def run_all_checks(trade_request: TradeRequest, portfolio: PortfolioState) -> list[RiskCheckResult]:
    order_value_cents = trade_request.quantity * trade_request.price_cents
    today_loss = portfolio.today_realized_loss_cents + portfolio.today_unrealized_loss_cents
    market_price = trade_request.market_price_cents / 100.0
    return [
        check_position_limit(
            portfolio.current_positions_value_cents,
            order_value_cents,
            portfolio.portfolio_value_cents,
        ),
        check_daily_loss(today_loss, portfolio.portfolio_value_cents),
        check_drawdown(portfolio.peak_value_cents, portfolio.portfolio_value_cents),
        check_liquidity(trade_request.market_open_interest),
        check_max_positions(portfolio.open_positions_count),
        check_min_edge(trade_request.estimated_prob, market_price),
    ]
