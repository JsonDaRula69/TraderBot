from __future__ import annotations

import logging

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

# DD-036: SysAdmin is unsandboxed with principled restrictions.
# Can manage the fleet, coordinate improvements, check health — but NEVER trade.
SYSADMIN_DENY_TOOLS: list[str] = [
    "deny:traderbot__trade",
    "deny:traderbot__scan",
    "deny:traderbot__analyze",
    "deny:traderbot__market_edge",
    "deny:traderbot__market_prices",
    "deny:traderbot__weather_*",
]


def create_sysadmin_profile() -> TradingProfile:
    return TradingProfile(
        name="sysadmin",
        mode="paper",
        description=(
            "TraderBot system administrator — oversight, evaluation, "
            "and test lab management"
        ),
        enabled_categories=[c for c in MarketCategory],
        risk_multiplier=0.001,
        max_position_per_market_pct=0.001,
        max_daily_loss_pct=0.001,
        max_drawdown_pct=0.001,
        max_open_positions=1,
        min_liquidity_threshold=1,
        min_edge_pct=100.0,
        initial_balance_cents=0,
        permissions=SYSADMIN_DENY_TOOLS,
    )
