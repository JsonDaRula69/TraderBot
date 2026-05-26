"""Risk enforcement layer — immutable limits, sizing, circuit breaker, and audit."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk.circuit_breaker import CircuitBreaker
from traderbot.risk.limits import HARD_LIMITS, run_all_checks
from traderbot.risk.sizing import sized_position_for_trade

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile


class TradeResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    sized_position_cents: int
    direction: Literal["yes", "no"]


class RiskCheckError(Exception):
    """Raised when risk checks reject a trade, carrying details about which check failed and why."""

    def __init__(self, ticker: str, failures: list) -> None:
        self.ticker = ticker
        self.failures = failures
        details = "; ".join(f.rejection_reason or f"{f.limit_name} failed (value={f.current_value}, limit={f.limit_value})" for f in failures)
        super().__init__(f"Risk check rejected {ticker}: {details}")
        self.detail = details


__all__ = [
    "HARD_LIMITS",
    "CircuitBreaker",
    "PortfolioState",
    "TradeRequest",
    "TradeResult",
    "evaluate_trade",
    "run_all_checks",
    "sized_position_for_trade",
]


def evaluate_trade(
    trade_request: TradeRequest,
    portfolio: PortfolioState,
    breaker: CircuitBreaker,
    profile: TradingProfile | None = None,
) -> int:
    """Run the full risk gate: circuit breaker → limits → sizing.

    Args:
        trade_request: Trade to evaluate
        portfolio: Current portfolio state
        breaker: Circuit breaker instance
        profile: Optional trading profile for profile-aware risk limits

    Returns the sized position in cents (0 if rejected).
    """
    result = evaluate_trade_full(trade_request, portfolio, breaker, profile)
    return result.sized_position_cents


def evaluate_trade_full(
    trade_request: TradeRequest,
    portfolio: PortfolioState,
    breaker: CircuitBreaker,
    profile: TradingProfile | None = None,
) -> TradeResult:
    """Run the full risk gate and return both sized position and direction.

    Unlike evaluate_trade which returns only the sized position as int,
    this returns a TradeResult preserving the original trade direction.
    """
    # Category filtering (profile-aware only)
    if profile is not None and trade_request.market_category is not None and not profile.is_category_enabled(trade_request.market_category):
        return TradeResult(sized_position_cents=0, direction=trade_request.direction)

    total_today_loss_cents = (
        portfolio.today_realized_loss_cents + portfolio.today_unrealized_loss_cents
    )
    daily_loss_pct = total_today_loss_cents / max(portfolio.portfolio_value_cents, 1)
    drawdown_pct = (portfolio.peak_value_cents - portfolio.portfolio_value_cents) / max(
        portfolio.peak_value_cents, 1
    )
    breaker.check(daily_loss_pct=daily_loss_pct, drawdown_pct=drawdown_pct)

    if not breaker.get_state().can_trade:
        return TradeResult(sized_position_cents=0, direction=trade_request.direction)

    # Compute effective limits: profile-aware if profile is set, otherwise HARD_LIMITS
    if profile is not None:
        from traderbot.risk.agent_limits import AgentRiskLimits

        agent_limits = AgentRiskLimits(profile)
        effective_limits: dict[str, float | int] = {
            "max_position_per_market_pct": agent_limits.max_position_per_market_pct,
            "max_daily_loss_pct": agent_limits.max_daily_loss_pct,
            "max_drawdown_pct": agent_limits.max_drawdown_pct,
            "min_liquidity_threshold": agent_limits.min_liquidity_threshold,
            "max_open_positions": agent_limits.max_open_positions,
            "min_edge_pct": agent_limits.min_edge_pct,
        }
        max_position_pct = agent_limits.max_position_per_market_pct
        risk_multiplier = profile.risk_multiplier
    else:
        effective_limits = dict(HARD_LIMITS)
        max_position_pct = float(HARD_LIMITS["max_position_per_market_pct"])
        risk_multiplier = 1.0

    # Intentionally using unsized quantity for conservative position limit check.
    # This may over-reject trades that would pass with the Kelly-sized quantity.
    # Future: consider two-pass — soft check with original qty, hard check with sized qty.
    results = run_all_checks(trade_request, portfolio, limits=effective_limits)
    failed = [r for r in results if not r.passed]
    if failed:
        for r in failed:
            msg = r.rejection_reason or f"{r.limit_name} check failed (value={r.current_value}, limit={r.limit_value})"
            logger.warning("Trade rejected: %s — %s", trade_request.ticker, msg)
        raise RiskCheckError(trade_request.ticker, failed)

    odds = (100 - trade_request.price_cents) / max(trade_request.price_cents, 1)
    max_position_cents = int(portfolio.portfolio_value_cents * max_position_pct)
    raw_size = sized_position_for_trade(
        prob=trade_request.estimated_prob,
        odds=odds,
        confidence=trade_request.confidence,
        bankroll_cents=portfolio.portfolio_value_cents,
        max_position_cents=max_position_cents,
    )
    sized = int(raw_size * breaker.get_state().position_size_multiplier * risk_multiplier)
    return TradeResult(sized_position_cents=sized, direction=trade_request.direction)
