"""Single source of truth for weather coordinate maps and resolution logic.

Kalshi settles weather markets against airport stations (KLAX, KLGA, KORD)
not city-center coordinates.  The maps in this module keep city-center coords
in ``_CITY_MAP`` for general-purpose forecasting and use station coordinates in
``_KALSHI_CITY_MAP`` so that settlement and backfill queries hit the correct
locations.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
#  City-center coordinates (general-purpose forecast map)
# ---------------------------------------------------------------------------

_CITY_MAP: dict[str, tuple[float, float]] = {
    "New York": (40.71, -74.01),
    "Philadelphia": (39.95, -75.16),
    "Phoenix": (33.45, -112.07),
    "Minneapolis": (44.98, -93.26),
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

# ---------------------------------------------------------------------------
#  ICAO airport-station coordinates
# ---------------------------------------------------------------------------

_STATION_MAP: dict[str, tuple[float, float]] = {
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

# ---------------------------------------------------------------------------
#  Kalshi ticker prefix → ICAO station code
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
#  Kalshi ticker prefix → (city_name, station_lat, station_lon, timezone)
#
#  NOTE: Coordinates are the *airport station* coordinates (from _STATION_MAP),
#  NOT city-center coordinates.  Kalshi settles against these stations.
# ---------------------------------------------------------------------------

_KALSHI_CITY_MAP: dict[str, tuple[str, float, float, str]] = {
    "KXHIGHNY": ("New York", 40.77, -73.87, "America/New_York"),  # KLGA
    "KXHIGHPHIL": ("Philadelphia", 39.87, -75.24, "America/New_York"),  # KPHL
    "KXHIGHTPHX": ("Phoenix", 33.43, -112.01, "America/Phoenix"),  # KPHX
    "KXHIGHTMIN": ("Minneapolis", 44.88, -93.22, "America/Chicago"),  # KMSP
    "KXHIGHTSEA": ("Seattle", 47.44, -122.31, "America/Los_Angeles"),  # KSEA
    "KXHIGHTCHI": ("Chicago", 41.98, -87.90, "America/Chicago"),  # KORD
    "KXHIGHTHOU": ("Houston", 29.98, -95.34, "America/Chicago"),  # KIAH
    "KXHIGHTLA": ("Los Angeles", 33.94, -118.41, "America/Los_Angeles"),  # KLAX
    "KXHIGHTMIA": ("Miami", 25.79, -80.29, "America/New_York"),  # KMIA
    "KXHIGHTDEN": ("Denver", 39.86, -104.67, "America/Denver"),  # KDEN
    "KXHIGHTATL": ("Atlanta", 33.64, -84.43, "America/New_York"),  # KATL
    "KXHIGHTBOS": ("Boston", 42.36, -71.01, "America/New_York"),  # KBOS
    "KXHIGHTDAL": ("Dallas", 32.85, -96.85, "America/Chicago"),  # KDAL
    "KXHIGHTDET": ("Detroit", 42.21, -83.35, "America/Detroit"),  # KDTW
    "KXHIGHTSF": ("San Francisco", 37.62, -122.38, "America/Los_Angeles"),  # KSFO
}

# ---------------------------------------------------------------------------
#  Short-code aliases for CLI convenience
# ---------------------------------------------------------------------------

_CITY_ALIASES: dict[str, str] = {
    "NYC": "New York",
    "NY": "New York",
    "PHIL": "Philadelphia",
    "PHL": "Philadelphia",
    "PHX": "Phoenix",
    "MIN": "Minneapolis",
    "MSP": "Minneapolis",
    "SEA": "Seattle",
    "CHI": "Chicago",
    "HOU": "Houston",
    "LA": "Los Angeles",
    "LAX": "Los Angeles",
    "MIA": "Miami",
    "DEN": "Denver",
    "ATL": "Atlanta",
    "BOS": "Boston",
    "DAL": "Dallas",
    "DFW": "Dallas",
    "DET": "Detroit",
    "SF": "San Francisco",
    "SFO": "San Francisco",
}

# ---------------------------------------------------------------------------
#  Derived: city_name → station coords (fast lookup for forecast resolution)
# ---------------------------------------------------------------------------

_CITY_STATION_COORDS: dict[str, tuple[float, float]] = {}
for _ticker, (_name, _slat, _slon, _tz) in _KALSHI_CITY_MAP.items():
    _station = _KALSHI_STATION_MAP.get(_ticker)
    if _station:
        _coords = _STATION_MAP.get(_station)
        if _coords:
            _CITY_STATION_COORDS[_name] = _coords


# ---------------------------------------------------------------------------
#  Public resolution helpers
# ---------------------------------------------------------------------------


def resolve_city_alias(code: str) -> str | None:
    """Resolve a short code to its canonical city name.

    ``"LA"`` → ``"Los Angeles"``, ``"NYC"`` → ``"New York"``, etc.

    Returns ``None`` for unrecognised codes.
    """
    return _CITY_ALIASES.get(code)


def resolve_city(city_input: str) -> str | None:
    """Resolve city input (full name, short code, or ticker prefix) to a full city name.

    Returns ``None`` when the input cannot be resolved.
    """
    if city_input in _CITY_MAP:
        return city_input
    alias = _CITY_ALIASES.get(city_input)
    if alias:
        return alias
    for prefix, (name, _lat, _lon, _tz) in _KALSHI_CITY_MAP.items():
        if prefix == city_input:
            return name
    return None


def resolve_forecast_coords(city_name: str) -> tuple[float, float]:
    """Return (lat, lon) for a city, preferring station coords when available.

    Kalshi markets settle at airport stations, so forecasts should target
    the same location for consistency.  Falls back to city-center coordinates
    when no station mapping exists for the city.
    """
    coords = _CITY_STATION_COORDS.get(city_name)
    if coords:
        return coords
    return _CITY_MAP[city_name]


def resolve_settlement_coords(ticker_prefix: str) -> tuple[str, float, float, str] | None:
    """Return (city_name, lat, lon, tz) for a Kalshi ticker prefix.

    Coordinates come from ``_KALSHI_CITY_MAP`` which already uses the airport
    station coordinates.  Callers can hit Open-Meteo's archive API directly
    with these values for accurate settlement verification.
    """
    return _KALSHI_CITY_MAP.get(ticker_prefix)
