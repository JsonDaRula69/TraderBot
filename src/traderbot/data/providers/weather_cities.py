"""Shared configuration for weather data providers.

Coordinates, model set, and daily variables mirror the standalone data
collector so weather snapshots stay comparable across both tools.
"""

from __future__ import annotations

# Kalshi weather cities with (latitude, longitude). Retired from the
# data-collector config so both tools agree on the same city set.
CITIES: dict[str, tuple[float, float]] = {
    "New York": (40.71, -74.01),
    "Philadelphia": (39.95, -75.16),
    "Phoenix": (33.45, -112.07),
    "Minneapolis": (44.98, -93.27),
    "Seattle": (47.61, -122.33),
    "Chicago": (41.88, -87.63),
    "Houston": (29.76, -95.37),
    "Los Angeles": (34.05, -118.24),
    "Miami": (25.76, -80.19),
    "Denver": (39.74, -104.99),
    "Atlanta": (33.75, -84.39),
    "Boston": (42.36, -71.06),
    "Dallas": (32.78, -96.80),
    "Detroit": (42.33, -83.05),
    "San Francisco": (37.77, -122.42),
}

# Open-Meteo ensemble models and the daily variables collected for weather
# trading.
OM_MODELS = ("gfs_seamless", "ecmwf_ifs", "gem_global")

OM_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "windspeed_10m_max",
    "windgusts_10m_max",
]

# Request timeout for external weather APIs.
REQUEST_TIMEOUT = 30.0
