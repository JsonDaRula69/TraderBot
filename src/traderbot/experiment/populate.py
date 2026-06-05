"""Populate experiment database with market data from Kalshi and forecasts from Open-Meteo."""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import UTC, datetime

import httpx

from traderbot.db.experiment_schema import create_tables
from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.markets import MarketService
from traderbot.kalshi.models import Market

logger = logging.getLogger(__name__)

# City prefix → (city_name, lat, lon, timezone)
# Derived from the KXHIGHT/KXHIGH naming convention used by Kalshi weather markets.
_CITY_MAP: dict[str, tuple[str, float, float, str]] = {
    "KXHIGHNY": ("New York", 40.71, -74.01, "America/New_York"),
    "KXHIGHPHIL": ("Philadelphia", 39.95, -75.16, "America/New_York"),
    "KXHIGHTPHX": ("Phoenix", 33.45, -112.07, "America/Phoenix"),
    "KXHIGHTMIN": ("Minneapolis", 44.98, -93.26, "America/Chicago"),
    "KXHIGHTSEA": ("Seattle", 47.61, -122.33, "America/Los_Angeles"),
    "KXHIGHTCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXHIGHTHOU": ("Houston", 29.76, -95.37, "America/Chicago"),
    "KXHIGHTLA": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXHIGHTMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXHIGHTDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXHIGHTATL": ("Atlanta", 33.75, -84.39, "America/New_York"),
    "KXHIGHTBOS": ("Boston", 42.36, -71.06, "America/New_York"),
    "KXHIGHTDAL": ("Dallas", 32.78, -96.80, "America/Chicago"),
    "KXHIGHTDET": ("Detroit", 42.33, -83.05, "America/Detroit"),
    "KXHIGHTSF": ("San Francisco", 37.77, -122.42, "America/Los_Angeles"),
}

# Station name — override lat/lon for the Kalshi settlement station.
_KALSHI_STATION_MAP: dict[str, str] = {
    "KXHIGHNY": "KLGA",
    "KXHIGHPHIL": "KPHL",
    "KXHIGHTPHX": "KPHX",
    "KXHIGHTMIN": "KMSP",
    "KXHIGHTSEA": "KSEA",
    "KXHIGHTCHI": "KORD",
    "KXHIGHTHOU": "KIAH",
    "KXHIGHTLA": "KLAX",
    "KXHIGHTMIA": "KMIA",
    "KXHIGHTDEN": "KDEN",
    "KXHIGHTATL": "KATL",
    "KXHIGHTBOS": "KBOS",
    "KXHIGHTDAL": "KDAL",
    "KXHIGHTDET": "KDTW",
    "KXHIGHTSF": "KSFO",
}

# Station ICAO → (lat, lon)
_STATION_COORDS: dict[str, tuple[float, float]] = {
    "KLGA": (40.77, -73.87),
    "KJFK": (40.64, -73.78),
    "KLAX": (33.94, -118.41),
    "KORD": (41.98, -87.90),
    "KMDW": (41.79, -87.75),
    "KPHX": (33.43, -112.01),
    "KSEA": (47.44, -122.31),
    "KDAL": (32.85, -96.85),
    "KDFW": (32.90, -97.04),
    "KMIA": (25.79, -80.29),
    "KBOS": (42.36, -71.01),
    "KDEN": (39.86, -104.67),
    "KIAH": (29.98, -95.34),
    "KHOU": (29.65, -95.28),
    "KATL": (33.64, -84.43),
    "KDTW": (42.21, -83.35),
    "KSFO": (37.62, -122.38),
    "KMSP": (44.88, -93.22),
    "KPHL": (39.87, -75.24),
    "KPIT": (40.49, -80.23),
}

# Regex to extract strike value from question text like "Will NYC high be above 72°F?"
_STRIKE_RE = re.compile(r"(\d+)\s*°?\s*F", re.IGNORECASE)


def _city_prefix_from_ticker(ticker: str) -> str | None:
    """Extract the city prefix from a Kalshi ticker (e.g. 'KXHIGHTMIN-25M26' → 'KXHIGHTMIN')."""
    for prefix in _CITY_MAP:
        if ticker.startswith(prefix):
            return prefix
    return None


def _parse_strike_value(question: str) -> float | None:
    """Parse the strike temperature from a market question string."""
    m = _STRIKE_RE.search(question)
    if m:
        return float(m.group(1))
    return None


def _parse_strike_type(question: str) -> str | None:
    """Infer strike type from question text."""
    q = question.lower()
    if "above" in q or "greater" in q or "over" in q:
        return "greater"
    if "below" in q or "less" in q or "under" in q:
        return "less"
    if "between" in q:
        return "between"
    return None


def _yes_price_dollars(market: Market) -> float | None:
    """Extract yes price in dollars from outcome_prices."""
    prices = market.outcome_prices
    if prices and len(prices) > 0:
        try:
            return float(prices[0])
        except (ValueError, TypeError):
            return None
    return None


async def _fetch_forecast(lat: float, lon: float) -> list[dict]:
    """Fetch temperature forecast from Open-Meteo Previous Runs API.

    Returns a list of dicts with keys: forecast_temp_f, source, days_before, snapshot_date.
    """
    url = "https://customer.open-meteo.com/api/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "previous_days": 10,
        "hourly": "temperature_2m",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Open-Meteo forecast fetch failed for (%s, %s): %s", lat, lon, exc)
        return []

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])

    if not times or not temps:
        return []

    now = datetime.now(tz=UTC)
    snapshots: list[dict] = []
    today_str = now.strftime("%Y-%m-%d")

    for time_str, temp_val in zip(times, temps, strict=True):
        if temp_val is None:
            continue
        try:
            ts = datetime.fromisoformat(time_str).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            continue
        days_before = (now.date() - ts.date()).days
        if days_before >= 0 and 12 <= ts.hour <= 13:
            snapshots.append(
                {
                    "forecast_temp_f": round(float(temp_val), 1),
                    "source": "open-meteo-previous-runs",
                    "days_before": days_before,
                    "snapshot_date": today_str,
                }
            )

    return snapshots


async def _populate_async(db_path: str, max_markets: int, category: str | None) -> int:
    """Async implementation of populate_cmd."""
    conn = sqlite3.connect(db_path)
    create_tables(conn)

    async with KalshiClient() as client:
        svc = MarketService(client)
        category_str = category or "weather"
        result = await svc.list_markets_by_category(category_str, limit=max_markets)
        markets = result.markets[:max_markets]

    stored = 0
    for market in markets:
        prefix = _city_prefix_from_ticker(market.ticker)
        city_info = _CITY_MAP.get(prefix) if prefix else None
        if city_info is None:
            logger.debug(
                "Skipping market %s — no city mapping for prefix %s", market.ticker, prefix
            )
            continue

        city_name, lat, lon, tz = city_info
        # Override lat/lon with station coordinates for Kalshi settlement accuracy
        station_code = _KALSHI_STATION_MAP.get(prefix)
        if station_code and station_code in _STATION_COORDS:
            lat, lon = _STATION_COORDS[station_code]
        strike_value = _parse_strike_value(market.question)
        strike_type = market.strike_type or _parse_strike_type(market.question)
        yes_price = _yes_price_dollars(market)
        resolution_date = (
            market.close_time.strftime("%Y-%m-%d") if market.close_time else "2099-12-31"
        )
        close_time_str = market.close_time.isoformat() if market.close_time else ""

        try:
            conn.execute(
                """INSERT OR REPLACE INTO markets
                   (ticker, question, city, city_prefix, lat, lon, timezone,
                    resolution_date, close_time, settlement_result, actual_value,
                    strike_value, strike_type, market_type, yes_price_dollars,
                    volume, open_interest, event_ticker, series_ticker)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    market.ticker,
                    market.question,
                    city_name,
                    prefix,
                    lat,
                    lon,
                    tz,
                    resolution_date,
                    close_time_str,
                    None,  # settlement_result
                    None,  # actual_value
                    strike_value,
                    strike_type,
                    None,  # market_type
                    yes_price,
                    float(market.volume),
                    float(market.open_interest),
                    market.event_ticker,
                    market.series_ticker,
                ),
            )
        except sqlite3.Error as exc:
            logger.warning("Failed to insert market %s: %s", market.ticker, exc)
            continue

        try:
            forecast_snapshots = await _fetch_forecast(lat, lon)
            for snap in forecast_snapshots:
                conn.execute(
                    """INSERT INTO forecast_snapshots
                       (ticker, forecast_temp_f, source, days_before, snapshot_date)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        market.ticker,
                        snap["forecast_temp_f"],
                        snap["source"],
                        snap["days_before"],
                        snap["snapshot_date"],
                    ),
                )
        except Exception as exc:
            logger.warning("Forecast insert failed for %s: %s", market.ticker, exc)

        try:
            prices = market.outcome_prices
            yes_cents = int(float(prices[0]) * 100) if prices and len(prices) > 0 else 0
            no_cents = int(float(prices[1]) * 100) if prices and len(prices) > 1 else 0
            conn.execute(
                """INSERT INTO market_prices
                   (ticker, timestep, yes_price_cents, no_price_cents)
                   VALUES (?, ?, ?, ?)""",
                (market.ticker, 0, yes_cents, no_cents),
            )
        except Exception as exc:
            logger.warning("Price insert failed for %s: %s", market.ticker, exc)

        stored += 1

    conn.commit()
    conn.close()
    return stored


def populate_cmd(db_path: str, max_markets: int = 200, category: str | None = None) -> int:
    """Populate the experiment database with market data from Kalshi and forecasts from Open-Meteo.

    Args:
        db_path: Path to the SQLite database file.
        max_markets: Maximum number of markets to fetch and store.
        category: Kalshi market category to filter (e.g. 'weather', 'KXHIGH').
            Defaults to 'weather' if None.

    Returns:
        Count of markets stored in the database.
    """
    return asyncio.run(_populate_async(db_path, max_markets, category))
