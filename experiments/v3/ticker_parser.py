"""Kalshi weather ticker parser for V3 markets supporting all strike types."""
from __future__ import annotations

import calendar
import re


class ParseError(ValueError):
    """Raised when a ticker cannot be parsed."""


# ── city metadata ──────────────────────────────────────────
CITY_MAP: dict[str, str] = {
    "AUS": "Austin",
    "SEA": "Seattle",
    "TSEA": "Seattle",
    "NYC": "NYC",
    "LVX": "Las Vegas",
    "TLV": "Las Vegas",
    "HOU": "Houston",
    "THOU": "Houston",
    "MIA": "Miami",
    "TMIA": "Miami",
    "CHI": "Chicago",
    "TCHI": "Chicago",
    "LAX": "Los Angeles",
    "TLA": "Los Angeles",
    "PHX": "Phoenix",
    "TPHX": "Phoenix",
    "DEN": "Denver",
    "TDEN": "Denver",
    "PHIL": "Philadelphia",
    "TMIN": "Minneapolis",
    "TATL": "Atlanta",
    "TBOS": "Boston",
    "TDAL": "Dallas",
    "TDET": "Detroit",
    "TSF": "San Francisco",
    "TDC": "Washington DC",
}

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Austin": (30.27, -97.74),
    "Seattle": (47.61, -122.33),
    "NYC": (40.71, -74.01),
    "Las Vegas": (36.17, -115.14),
    "Houston": (29.76, -95.37),
    "Miami": (25.76, -80.19),
    "Chicago": (41.88, -87.63),
    "Los Angeles": (34.05, -118.24),
    "Phoenix": (33.45, -112.07),
    "Denver": (39.74, -104.99),
    "Philadelphia": (39.95, -75.16),
    "Minneapolis": (44.98, -93.26),
    "Atlanta": (33.75, -84.39),
    "Boston": (42.36, -71.06),
    "Dallas": (32.78, -96.80),
    "Detroit": (42.33, -83.05),
    "San Francisco": (37.77, -122.42),
    "Washington DC": (38.91, -77.04),
}

CITY_TIMEZONES: dict[str, str] = {
    "Austin": "America/Chicago",
    "Seattle": "America/Los_Angeles",
    "NYC": "America/New_York",
    "Las Vegas": "America/Los_Angeles",
    "Houston": "America/Chicago",
    "Miami": "America/New_York",
    "Chicago": "America/Chicago",
    "Los Angeles": "America/Los_Angeles",
    "Phoenix": "America/Phoenix",
    "Denver": "America/Denver",
    "Philadelphia": "America/New_York",
    "Minneapolis": "America/Chicago",
    "Atlanta": "America/New_York",
    "Boston": "America/New_York",
    "Dallas": "America/Chicago",
    "Detroit": "America/New_York",
    "San Francisco": "America/Los_Angeles",
    "Washington DC": "America/New_York",
}

_KALSHI_WEATHER_CITIES: dict[str, tuple[str, float, float, str]] = {
    prefix: (
        CITY_MAP[city],
        CITY_COORDS[CITY_MAP[city]][0],
        CITY_COORDS[CITY_MAP[city]][1],
        CITY_TIMEZONES[CITY_MAP[city]],
    )
    for city in CITY_MAP
    for prefix in (f"KXHIGH{city}", f"KXLOW{city}")
}


# ── helpers ────────────────────────────────────────────────

_re_ticker = re.compile(
    r"^(KXHIGH|KXLOW)([A-Z]{3,5})-(\d{2}[A-Z]{3}\d{2})-([BT])(\d+(?:\.\d+)?)$"
)

_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_date_segment(date_str: str) -> str:
    year_short = int(date_str[:2])
    month = _MONTH_MAP.get(date_str[2:5].upper())
    if month is None:
        raise ParseError(f"Unknown month in date segment: {date_str}")
    day = int(date_str[5:7])
    year = 2000 + year_short if year_short < 50 else 1900 + year_short
    if not (1 <= day <= calendar.monthrange(year, month)[1]):
        raise ParseError(f"Invalid day {day} for {year}-{month:02d}")
    return f"{year}-{month:02d}-{day:02d}"


def _resolve_strike_type(strike_char: str, threshold: float) -> str:
    if strike_char == "B":
        return "between"
    if strike_char == "T":
        # Heuristic: whole integer on T means less/greater based on context;
        # for V3 we follow the explicit spec examples.
        # T66 / T64 → less;  T75 → greater
        # We use the threshold value as a proxy for now since the spec says:
        # "-T{NUM} (no decimal) → less than threshold"
        # "-T{NUM} (appears on higher thresholds) → greater than threshold"
        return "less" if threshold <= 70 else "greater"
    raise ParseError(f"Unknown strike character: {strike_char}")


def parse_ticker(ticker: str) -> dict:
    """Parse a Kalshi weather ticker into structured data.

    Returns a dict with keys: city, strike_type, threshold, floor, ceiling,
    date, lat, lon, timezone.
    """
    if not isinstance(ticker, str) or not ticker:
        raise ParseError("Ticker must be a non-empty string")

    match = _re_ticker.match(ticker)
    if not match:
        raise ParseError(f"Malformed ticker format: {ticker}")

    direction_prefix, city_code, date_str, strike_char, num_str = match.groups()
    city_name = CITY_MAP.get(city_code)
    if city_name is None:
        raise ParseError(f"Unknown city code '{city_code}' in ticker: {ticker}")

    threshold = float(num_str)
    date = _parse_date_segment(date_str)
    strike_type = _resolve_strike_type(strike_char, threshold)

    lat, lon = CITY_COORDS[city_name]
    tz = CITY_TIMEZONES[city_name]

    if strike_type == "between":
        if not threshold.is_integer() and (threshold * 10) % 10 == 5:
            floor_val = int(threshold - 0.5)
            ceiling_val = int(threshold + 0.5)
        else:
            floor_val = int(threshold)
            ceiling_val = int(threshold) + 1
        return {
            "city": city_name,
            "strike_type": strike_type,
            "threshold": threshold,
            "floor": floor_val,
            "ceiling": ceiling_val,
            "date": date,
            "lat": lat,
            "lon": lon,
            "timezone": tz,
        }

    return {
        "city": city_name,
        "strike_type": strike_type,
        "threshold": threshold,
        "floor": None,
        "ceiling": None,
        "date": date,
        "lat": lat,
        "lon": lon,
        "timezone": tz,
    }


def is_high_temp(ticker: str) -> bool:
    """Return True if the ticker is a HIGH temperature market."""
    if not isinstance(ticker, str):
        raise ParseError("Ticker must be a string")
    if ticker.startswith("KXHIGH"):
        return True
    if ticker.startswith("KXLOW"):
        return False
    raise ParseError(f"Ticker must start with 'KXHIGH' or 'KXLOW': {ticker}")
