"""Risk enforcement layer — immutable limits, sizing, circuit breaker, and audit."""

from __future__ import annotations

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk.circuit_breaker import CircuitBreaker
from traderbot.risk.limits import HARD_LIMITS, run_all_checks
from traderbot.risk.sizing import sized_position_for_trade

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
) -> int:
    """Run the full risk gate: circuit breaker → limits → sizing.

    Returns the sized position in cents (0 if rejected).
    """
    daily_loss_pct = portfolio.today_realized_loss_cents / max(portfolio.portfolio_value_cents, 1)
    drawdown_pct = (portfolio.peak_value_cents - portfolio.portfolio_value_cents) / max(portfolio.peak_value_cents, 1)
    breaker.check(daily_loss_pct=daily_loss_pct, drawdown_pct=drawdown_pct)

    if not breaker.get_state().can_trade:
        return 0

    results = run_all_checks(trade_request, portfolio)
    if any(not r.passed for r in results):
        return 0

    odds = trade_request.price_cents / max(100 - trade_request.price_cents, 1)
    max_position_cents = int(portfolio.portfolio_value_cents * HARD_LIMITS["max_position_per_market_pct"])
    size = sized_position_for_trade(
        prob=trade_request.estimated_prob,
        odds=odds,
        confidence=trade_request.confidence,
        bankroll_cents=portfolio.portfolio_value_cents,
        max_position_cents=max_position_cents,
    )
    return size
