from __future__ import annotations

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile


def create_sysadmin_profile() -> TradingProfile:
    return TradingProfile(
        name="sysadmin",
        mode="paper",
        description="TraderBot system administrator — oversight, evaluation, and test lab management",
        enabled_categories=[c for c in MarketCategory],
        risk_multiplier=0.001,
        max_position_per_market_pct=0.001,
        max_daily_loss_pct=0.001,
        max_drawdown_pct=0.001,
        max_open_positions=1,
        min_liquidity_threshold=1,
        min_edge_pct=100.0,
        initial_balance_cents=0,
    )
