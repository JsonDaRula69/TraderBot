from __future__ import annotations

from typing import Final

GLOBAL_SCHEMA_VERSION: Final = 2
GLOBAL_TABLES: Final = frozenset(
    {
        "config",
        "kalshi_candlesticks",
        "kalshi_forecast_history",
        "kalshi_markets",
        "market_data",
        "nws_forecasts",
        "orderbook",
        "profiles",
        "schema_version",
        "settlement_cache",
        "weather_forecasts",
        "weather_observations",
    }
)
GLOBAL_INDEXES: Final = frozenset(
    {
        "idx_kalshi_candlesticks_ticker_ts",
        "idx_kalshi_forecast_event_ts",
        "idx_kalshi_markets_category_status",
        "idx_kalshi_markets_event",
        "idx_kalshi_markets_series",
        "idx_kalshi_markets_status_close",
        "idx_weather_observations_city_date",
    }
)
DECISIONS_SCHEMA_VERSION: Final = 1
DECISIONS_TABLES: Final = frozenset(
    {
        "bias_tracking",
        "circuit_breaker",
        "decisions",
        "forecast_snapshots",
        "learnings",
        "portfolio_summary",
        "positions",
        "schema_version",
    }
)
DECISIONS_INDEXES: Final = frozenset(
    {
        "idx_bias_tracking_category_source",
        "idx_bias_tracking_metric",
        "idx_decisions_category",
        "idx_decisions_mode",
        "idx_decisions_profile",
        "idx_decisions_profile_mode",
        "idx_decisions_ticker",
        "idx_decisions_ticker_timestamp",
        "idx_decisions_timestamp",
        "idx_forecast_snapshots_category",
        "idx_forecast_snapshots_lookup",
        "idx_forecast_snapshots_source_lead",
        "idx_learnings_category",
        "idx_learnings_priority",
        "idx_learnings_status",
        "idx_positions_category",
        "idx_positions_mode",
        "idx_positions_profile",
        "idx_positions_profile_mode",
        "idx_positions_status",
    }
)

__all__ = [
    "DECISIONS_INDEXES",
    "DECISIONS_SCHEMA_VERSION",
    "DECISIONS_TABLES",
    "GLOBAL_INDEXES",
    "GLOBAL_SCHEMA_VERSION",
    "GLOBAL_TABLES",
]
