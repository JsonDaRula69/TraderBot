"""Generic profile factory for category agents."""

from collections.abc import Sequence

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile


def create_category_profile(
    name: str,
    mode: str = "backtest",
    categories: Sequence[MarketCategory] = (),
) -> TradingProfile:
    """Create a category-scoped profile with standard trading risk limits."""
    return TradingProfile.model_validate(
        {
            "name": name,
            "mode": mode,
            "description": f"{name} category agent",
            "enabled_categories": list(categories),
            "risk_multiplier": 0.8,
            "max_position_per_market_pct": 0.15,
            "max_daily_loss_pct": 0.05,
            "max_drawdown_pct": 0.10,
            "max_open_positions": 3,
            "min_liquidity_threshold": 500,
            "min_edge_pct": 3.0,
        }
    )
