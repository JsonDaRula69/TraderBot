from __future__ import annotations

from typing import Final

GLOBAL_V2_UP_SQL: Final = (
    """CREATE TABLE weather_observations (
        date TEXT NOT NULL CHECK (length(date) = 10),
        city TEXT NOT NULL CHECK (city <> ''),
        latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
        longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
        variable TEXT NOT NULL CHECK (variable <> ''),
        value REAL NOT NULL,
        PRIMARY KEY (date, city, variable)
    )""",
    "CREATE INDEX idx_weather_observations_city_date ON weather_observations(city, date)",
    """CREATE TABLE kalshi_markets (
        ticker TEXT PRIMARY KEY CHECK (ticker <> ''),
        event_ticker TEXT NOT NULL CHECK (event_ticker <> ''),
        series_ticker TEXT CHECK (series_ticker IS NULL OR series_ticker <> ''),
        category TEXT CHECK (category IS NULL OR category <> ''),
        status TEXT NOT NULL
            CHECK (status IN ('initialized', 'inactive', 'active', 'closed', 'determined',
                              'disputed', 'amended', 'finalized')),
        result TEXT NOT NULL CHECK (result IN ('yes', 'no', 'scalar', '')),
        title TEXT,
        subtitle TEXT,
        yes_sub_title TEXT NOT NULL,
        no_sub_title TEXT NOT NULL,
        market_type TEXT NOT NULL CHECK (market_type IN ('binary', 'scalar')),
        volume_fp TEXT NOT NULL CHECK (volume_fp <> ''),
        open_interest_fp TEXT NOT NULL CHECK (open_interest_fp <> ''),
        created_ts INTEGER NOT NULL CHECK (created_ts >= 0),
        updated_ts INTEGER NOT NULL CHECK (updated_ts >= 0),
        open_ts INTEGER NOT NULL CHECK (open_ts >= 0),
        close_ts INTEGER NOT NULL CHECK (close_ts >= 0),
        settled_ts INTEGER CHECK (settled_ts IS NULL OR settled_ts >= 0)
    )""",
    "CREATE INDEX idx_kalshi_markets_event ON kalshi_markets(event_ticker)",
    "CREATE INDEX idx_kalshi_markets_series ON kalshi_markets(series_ticker)",
    "CREATE INDEX idx_kalshi_markets_category_status ON kalshi_markets(category, status)",
    "CREATE INDEX idx_kalshi_markets_status_close ON kalshi_markets(status, close_ts)",
    """CREATE TABLE kalshi_candlesticks (
        ticker TEXT NOT NULL CHECK (ticker <> ''),
        period_interval INTEGER NOT NULL CHECK (period_interval IN (1, 60, 1440)),
        end_period_ts INTEGER NOT NULL CHECK (end_period_ts >= 0),
        source TEXT NOT NULL CHECK (source IN ('live', 'historical')),
        yes_bid_open TEXT NOT NULL CHECK (yes_bid_open <> ''),
        yes_bid_low TEXT NOT NULL CHECK (yes_bid_low <> ''),
        yes_bid_high TEXT NOT NULL CHECK (yes_bid_high <> ''),
        yes_bid_close TEXT NOT NULL CHECK (yes_bid_close <> ''),
        yes_ask_open TEXT NOT NULL CHECK (yes_ask_open <> ''),
        yes_ask_low TEXT NOT NULL CHECK (yes_ask_low <> ''),
        yes_ask_high TEXT NOT NULL CHECK (yes_ask_high <> ''),
        yes_ask_close TEXT NOT NULL CHECK (yes_ask_close <> ''),
        price_open TEXT,
        price_low TEXT,
        price_high TEXT,
        price_close TEXT,
        price_mean TEXT,
        price_previous TEXT,
        price_min TEXT,
        price_max TEXT,
        volume_fp TEXT NOT NULL CHECK (volume_fp <> ''),
        open_interest_fp TEXT NOT NULL CHECK (open_interest_fp <> ''),
        PRIMARY KEY (ticker, period_interval, end_period_ts, source)
    )""",
    """CREATE INDEX idx_kalshi_candlesticks_ticker_ts
       ON kalshi_candlesticks(ticker, end_period_ts)""",
    """CREATE TABLE kalshi_forecast_history (
        event_ticker TEXT NOT NULL CHECK (event_ticker <> ''),
        series_ticker TEXT NOT NULL CHECK (series_ticker <> ''),
        end_period_ts INTEGER NOT NULL CHECK (end_period_ts >= 0),
        period_interval INTEGER NOT NULL CHECK (period_interval IN (0, 1, 60, 1440)),
        percentile INTEGER NOT NULL CHECK (percentile BETWEEN 0 AND 9999),
        raw_numerical_forecast TEXT NOT NULL CHECK (raw_numerical_forecast <> ''),
        numerical_forecast TEXT NOT NULL CHECK (numerical_forecast <> ''),
        formatted_forecast TEXT NOT NULL,
        PRIMARY KEY (event_ticker, series_ticker, end_period_ts, period_interval, percentile)
    )""",
    """CREATE INDEX idx_kalshi_forecast_event_ts
       ON kalshi_forecast_history(event_ticker, end_period_ts)""",
)

GLOBAL_V2_DOWN_SQL: Final = (
    "DROP INDEX idx_kalshi_forecast_event_ts",
    "DROP TABLE kalshi_forecast_history",
    "DROP INDEX idx_kalshi_candlesticks_ticker_ts",
    "DROP TABLE kalshi_candlesticks",
    "DROP INDEX idx_kalshi_markets_status_close",
    "DROP INDEX idx_kalshi_markets_category_status",
    "DROP INDEX idx_kalshi_markets_series",
    "DROP INDEX idx_kalshi_markets_event",
    "DROP TABLE kalshi_markets",
    "DROP INDEX idx_weather_observations_city_date",
    "DROP TABLE weather_observations",
)
