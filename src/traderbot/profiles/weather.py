"""Weather agent profile factory (DD-010, DD-035).

Weather agent runs in Docker sandbox with weather-specific tools.
Mode starts as paper (no backtesting engine yet).
"""

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile


def create_weather_profile() -> TradingProfile:
    """Create the weather category agent profile.

    Weather agent has access to:
    - Weather toolkit (traderbot__weather_forecast_prob, weather_accuracy,
      weather_seasonal_context, weather_decision_brief)
    - General tools (health, auth_check, profile_list)
    - Market tools (market_edge, market_prices)
    - Trading tools (trade, positions, performance, heartbeat)
    - Ops tools (audit, learnings, news_context, data_points)

    Weather agent does NOT have access to:
    - SysAdmin-only tools (reference, data_status, ws_status)
    - Legacy generic tools replaced by DD-035 toolkits (scan, analyze)
    - Retired weather tools (weather_historical, weather_alert, weather_analysis)
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
            # Allow weather toolkit (v2docs/09-mcp-tools.md lines 195-308)
            "traderbot__weather_forecast_prob",
            "traderbot__weather_accuracy",
            "traderbot__weather_seasonal_context",
            "traderbot__weather_decision_brief",
            # Allow general tools
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
            # Allow market tools
            "traderbot__market_edge",
            "traderbot__market_prices",
            # Allow trading tools
            "traderbot__trade",
            "traderbot__positions",
            "traderbot__heartbeat",
            # Allow ops tools
            "traderbot__performance",
            "traderbot__audit",
            "traderbot__learnings",
            "traderbot__news_context",
            "traderbot__data_points",
        ],
    )
