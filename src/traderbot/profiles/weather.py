"""Weather agent profile factory (DD-010, DD-035).

Weather agent runs in Docker sandbox with weather-specific tools.
Mode starts as paper (no backtesting engine yet).
"""

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile


def create_weather_profile() -> TradingProfile:
    """Create the weather category agent profile.

    Weather agent has access to:
    - Weather analysis tools (traderbot__weather_*)
    - General tools (health, auth_check, profile_list, reference)
    - Market tools (scan, analyze, market_edge, market_prices)
    - Trading tools (trade, positions, performance)

    Weather agent does NOT have access to:
    - SysAdmin-only tools (profile_update, experiment, cron_setup)
    """
    return TradingProfile(
        name="weather",
        mode="paper",
        description="Weather category agent — weather market specialist",
        enabled_categories=[MarketCategory.WEATHER],
        risk_multiplier=0.8,
        max_position_per_market_pct=0.15,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.10,
        max_open_positions=3,
        min_liquidity_threshold=500,
        min_edge_pct=3.0,
        permissions=[
            # Allow weather-specific tools
            "traderbot__weather_forecast_prob",
            "traderbot__weather_historical",
            "traderbot__weather_alert",
            "traderbot__weather_analysis",
            # Allow general tools
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
            "traderbot__reference",
            "traderbot__data_status",
            "traderbot__ws_status",
            # Allow market tools
            "traderbot__scan",
            "traderbot__analyze",
            "traderbot__market_edge",
            "traderbot__market_prices",
            # Allow trading tools
            "traderbot__trade",
            "traderbot__positions",
            "traderbot__performance",
        ],
    )