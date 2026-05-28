"""Immutable hard-limits enforcement — the guardrail layer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from types import MappingProxyType
from typing import Final

from traderbot.kalshi.models import PortfolioState, RiskCheckResult, TradeRequest

# MappingProxyType wraps the dict to make it immutable at runtime.
# The type annotation must be dict (not MappingProxyType) because
# MappingProxyType is not itself a generic type usable in annotations.
HARD_LIMITS: Final[dict[str, float | int]] = MappingProxyType(
    {
        "max_position_per_market_pct": 0.05,
        "max_daily_loss_pct": 0.02,
        "max_drawdown_pct": 0.10,
        "min_liquidity_threshold": 500,
        "max_open_positions": 20,
        "min_edge_pct": 0.03,
    }
)


def check_position_limit(
    current_position_value_cents: int,
    order_value_cents: int,
    portfolio_value_cents: int,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    total = current_position_value_cents + order_value_cents
    limit_value = portfolio_value_cents * effective["max_position_per_market_pct"]
    limit_pct = effective["max_position_per_market_pct"]
    passed = total <= limit_value
    return RiskCheckResult(
        passed=passed,
        limit_name="position_limit",
        current_value=total,
        limit_value=limit_value,
        rejection_reason=None if passed else f"Position would exceed {limit_pct:.0%} portfolio limit",
    )


def check_daily_loss(
    today_loss_cents: int,
    portfolio_value_cents: int,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    limit_value = portfolio_value_cents * effective["max_daily_loss_pct"]
    limit_pct = effective["max_daily_loss_pct"]
    passed = today_loss_cents <= limit_value
    return RiskCheckResult(
        passed=passed,
        limit_name="daily_loss",
        current_value=today_loss_cents,
        limit_value=limit_value,
        rejection_reason=None if passed else f"Daily loss exceeds {limit_pct:.0%} limit",
    )


def check_drawdown(
    peak_value_cents: int,
    current_value_cents: int,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    if peak_value_cents <= 0:
        return RiskCheckResult(
            passed=True,
            limit_name="drawdown",
            current_value=0.0,
            limit_value=effective["max_drawdown_pct"],
        )
    drawdown = (peak_value_cents - current_value_cents) / peak_value_cents
    limit_pct = effective["max_drawdown_pct"]
    passed = drawdown <= limit_pct
    return RiskCheckResult(
        passed=passed,
        limit_name="drawdown",
        current_value=drawdown,
        limit_value=limit_pct,
        rejection_reason=None if passed else f"Drawdown exceeds {limit_pct:.0%} limit",
    )


def check_liquidity(
    open_interest: int,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    threshold = effective["min_liquidity_threshold"]
    passed = open_interest >= threshold
    return RiskCheckResult(
        passed=passed,
        limit_name="liquidity",
        current_value=open_interest,
        limit_value=threshold,
        rejection_reason=None if passed else f"Market liquidity below {int(threshold)} threshold",
    )


def check_max_positions(
    current_positions: int,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    max_pos = effective["max_open_positions"]
    passed = current_positions < max_pos
    return RiskCheckResult(
        passed=passed,
        limit_name="max_positions",
        current_value=current_positions,
        limit_value=max_pos,
        rejection_reason=None if passed else f"Open positions exceed {int(max_pos)} limit",
    )


def check_min_edge(
    estimated_prob: float,
    market_price: float,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> RiskCheckResult:
    effective = limits if limits is not None else HARD_LIMITS
    edge = abs(estimated_prob - market_price)
    min_edge = effective["min_edge_pct"]
    passed = edge >= min_edge
    return RiskCheckResult(
        passed=passed,
        limit_name="min_edge",
        current_value=edge,
        limit_value=min_edge,
        rejection_reason=None if passed else f"Edge below {min_edge:.0%} minimum",
    )


def run_all_checks(
    trade_request: TradeRequest,
    portfolio: PortfolioState,
    *,
    limits: dict[str, float | int] | MappingProxyType | None = None,
) -> list[RiskCheckResult]:
    order_value_cents = trade_request.quantity * trade_request.price_cents
    today_loss = portfolio.today_realized_loss_cents + portfolio.today_unrealized_loss_cents
    market_price = trade_request.market_price_cents / 100.0
    return [
        check_position_limit(
            portfolio.current_positions_value_cents,
            order_value_cents,
            portfolio.portfolio_value_cents,
            limits=limits,
        ),
        check_daily_loss(today_loss, portfolio.portfolio_value_cents, limits=limits),
        check_drawdown(portfolio.peak_value_cents, portfolio.portfolio_value_cents, limits=limits),
        check_liquidity(trade_request.market_open_interest, limits=limits),
        check_max_positions(portfolio.open_positions_count, limits=limits),
        check_min_edge(trade_request.estimated_prob, market_price, limits=limits),
    ]
