from __future__ import annotations

import logging

from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

# DD-034: Dev-Liaison is architecture expert and AutoDev bridge. Does NOT trade.
# Reference-only tools, health checks, and session management.
DEV_LIAISON_ALLOW_TOOLS: list[str] = [
    "traderbot__reference",
    "traderbot__health",
    "traderbot__auth_check",
    "traderbot__profile_list",
]


def create_dev_liaison_profile() -> TradingProfile:
    return TradingProfile(
        name="dev-liaison",
        mode="paper",
        description=(
            "Architecture expert and AutoDev liaison — reference, health, and coordination only"
        ),
        enabled_categories=[],
        risk_multiplier=0.001,
        max_position_per_market_pct=0.001,
        max_daily_loss_pct=0.001,
        max_drawdown_pct=0.001,
        max_open_positions=1,
        min_liquidity_threshold=1,
        min_edge_pct=100.0,
        initial_balance_cents=0,
        permissions=DEV_LIAISON_ALLOW_TOOLS,
    )
