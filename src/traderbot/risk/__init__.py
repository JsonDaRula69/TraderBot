"""Risk enforcement layer — immutable limits, sizing, circuit breaker, and audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk.circuit_breaker import CircuitBreaker
from traderbot.risk.limits import HARD_LIMITS, run_all_checks
from traderbot.risk.sizing import sized_position_for_trade

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

__all__ = [
    "HARD_LIMITS",
    "CircuitBreaker",
    "PortfolioState",
    "TradeRequest",
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
    # Category filtering (profile-aware only)
    if profile is not None and trade_request.market_category is not None and not profile.is_category_enabled(trade_request.market_category):
        return 0

    daily_loss_pct = portfolio.today_realized_loss_cents / max(portfolio.portfolio_value_cents, 1)
    drawdown_pct = (portfolio.peak_value_cents - portfolio.portfolio_value_cents) / max(
        portfolio.peak_value_cents, 1
    )
    breaker.check(daily_loss_pct=daily_loss_pct, drawdown_pct=drawdown_pct)

    if not breaker.get_state().can_trade:
        return 0

    results = run_all_checks(trade_request, portfolio)
    if any(not r.passed for r in results):
        return 0

    # Use profile limits if provided, otherwise use HARD_LIMITS
    if profile is not None:
        from traderbot.risk.agent_limits import AgentRiskLimits

        agent_limits = AgentRiskLimits(profile)
        max_position_pct = agent_limits.max_position_per_market_pct
        risk_multiplier = profile.risk_multiplier
    else:
        max_position_pct = float(HARD_LIMITS["max_position_per_market_pct"])
        risk_multiplier = 1.0

    odds = trade_request.price_cents / max(100 - trade_request.price_cents, 1)
    max_position_cents = int(portfolio.portfolio_value_cents * max_position_pct)
    raw_size = sized_position_for_trade(
        prob=trade_request.estimated_prob,
        odds=odds,
        confidence=trade_request.confidence,
        bankroll_cents=portfolio.portfolio_value_cents,
        max_position_cents=max_position_cents,
    )
    return int(raw_size * breaker.get_state().position_size_multiplier * risk_multiplier)
