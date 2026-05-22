"""Ticker parser for Kalshi weather band tickers."""
from __future__ import annotations

import calendar

# City mapping: ticker prefix -> (city_name, lat, lon, timezone)
_KALSHI_WEATHER_CITIES: dict[str, tuple[str, float, float, str]] = {
    "KXHIGHNY": ("New York", 40.71, -74.01, "America/New_York"),
    "KXLOWNY": ("New York", 40.71, -74.01, "America/New_York"),
    "KXHIGHPHIL": ("Philadelphia", 39.95, -75.16, "America/New_York"),
    "KXLOWPHIL": ("Philadelphia", 39.95, -75.16, "America/New_York"),
    "KXHIGHTPHX": ("Phoenix", 33.45, -112.07, "America/Phoenix"),
    "KXLOWTPHX": ("Phoenix", 33.45, -112.07, "America/Phoenix"),
    "KXHIGHTMIN": ("Minneapolis", 44.98, -93.26, "America/Chicago"),
    "KXLOWTMIN": ("Minneapolis", 44.98, -93.26, "America/Chicago"),
    "KXHIGHTSEA": ("Seattle", 47.61, -122.33, "America/Los_Angeles"),
    "KXLOWTSEA": ("Seattle", 47.61, -122.33, "America/Los_Angeles"),
    "KXHIGHTCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXLOWTCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXHIGHCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXLOWCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXHIGHTHOU": ("Houston", 29.76, -95.37, "America/Chicago"),
    "KXLOWTHOU": ("Houston", 29.76, -95.37, "America/Chicago"),
    "KXHIGHTLA": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXLOWTLA": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXHIGHLAX": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXLOWLAX": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXHIGHTMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXLOWTMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXHIGHMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXLOWMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXHIGHTDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXLOWTDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXHIGHDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXLOWDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXHIGHTATL": ("Atlanta", 33.75, -84.39, "America/New_York"),
    "KXLOWTATL": ("Atlanta", 33.75, -84.39, "America/New_York"),
    "KXHIGHTBOS": ("Boston", 42.36, -71.06, "America/New_York"),
    "KXLOWTBOS": ("Boston", 42.36, -71.06, "America/New_York"),
    "KXHIGHTDAL": ("Dallas", 32.78, -96.80, "America/Chicago"),
    "KXLOWTDAL": ("Dallas", 32.78, -96.80, "America/Chicago"),
    "KXHIGHTDET": ("Detroit", 42.33, -83.05, "America/New_York"),
    "KXLOWTDET": ("Detroit", 42.33, -83.05, "America/New_York"),
    "KXHIGHTSF": ("San Francisco", 37.77, -122.42, "America/Los_Angeles"),
    "KXLOWTSF": ("San Francisco", 37.77, -122.42, "America/Los_Angeles"),
    # Additional cities observed in experiment database
    "KXHIGHAUS": ("Austin", 30.27, -97.74, "America/Chicago"),
    "KXLOWAUS": ("Austin", 30.27, -97.74, "America/Chicago"),
    "KXHIGHTDC": ("Washington DC", 38.91, -77.04, "America/New_York"),
    "KXLOWTDC": ("Washington DC", 38.91, -77.04, "America/New_York"),
    "KXHIGHTLV": ("Las Vegas", 36.17, -115.14, "America/Los_Angeles"),
    "KXLOWTLV": ("Las Vegas", 36.17, -115.14, "America/Los_Angeles"),
}


def _parse_date_segment(ticker: str) -> str:
    """Extract DDMMMYY from ticker and return YYYY-MM-DD format."""
    parts = ticker.split("-")
    if len(parts) < 2:
        raise ValueError(f"Ticker missing date segment: {ticker}")

    date_part = parts[1]
    if len(date_part) != 7:
        raise ValueError(f"Invalid date segment length in ticker: {ticker}")

    day = int(date_part[:2])
    month_str = date_part[2:5].upper()
    year_short = int(date_part[5:7])

    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    month = month_map.get(month_str)
    if month is None:
        raise ValueError(f"Unknown month abbreviation '{month_str}' in ticker: {ticker}")

    # Assume year >= 2000
    year = 2000 + year_short if year_short < 50 else 1900 + year_short

    if not (1 <= day <= calendar.monthrange(year, month)[1]):
        raise ValueError(f"Invalid day {day} for {year}-{month:02d} in ticker: {ticker}")

    return f"{year}-{month:02d}-{day:02d}"


def _parse_band_value(band_part: str) -> float:
    """Convert B84 -> 84.5, B95.5 -> 95.5.

    Rule: if the numeric part is a whole integer (e.g. B84),
    the band centre is the integer + 0.5.  If it already has
    a decimal (e.g. B95.5), use the value as-is.
    """
    if not band_part.upper().startswith("B"):
        raise ValueError(f"Band part must start with 'B': {band_part}")
    number_str = band_part[1:]
    try:
        value = float(number_str)
    except ValueError as exc:
        raise ValueError(f"Invalid band number '{number_str}': {band_part}") from exc
    if value.is_integer():
        value += 0.5
    return value


def parse_weather_ticker(ticker: str) -> dict:
    """Parse a Kalshi weather band ticker into structured data.

    Args:
        ticker: Ticker string of the form KXHIGH{CITY}-{DDMMMYY}-B{VALUE}
                or KXLOW{CITY}-{DDMMMYY}-B{VALUE}

    Returns:
        dict with keys: city_code, city_name, direction, threshold,
                        close_date, lat, lon

    Raises:
        ValueError: If the ticker format is unrecognizable.
    """
    if not isinstance(ticker, str) or not ticker:
        raise ValueError("Ticker must be a non-empty string")

    # Determine direction and city prefix
    if ticker.startswith("KXHIGH"):
        direction = "above"
    elif ticker.startswith("KXLOW"):
        direction = "below"
    else:
        raise ValueError(
            f"Ticker must start with 'KXHIGH' or 'KXLOW': {ticker}"
        )

    prefix = ticker.split("-")[0]

    city_info = _KALSHI_WEATHER_CITIES.get(prefix)
    if city_info is None:
        raise ValueError(f"Unknown city prefix '{prefix}' in ticker: {ticker}")

    city_name, lat, lon, _ = city_info
    close_date = _parse_date_segment(ticker)

    # Parse band (last segment)
    parts = ticker.split("-")
    if len(parts) < 3:
        raise ValueError(f"Ticker missing band segment: {ticker}")
    threshold = _parse_band_value(parts[-1])

    return {
        "city_code": prefix,
        "city_name": city_name,
        "direction": direction,
        "threshold": threshold,
        "close_date": close_date,
        "lat": lat,
        "lon": lon,
    }
