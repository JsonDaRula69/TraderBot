"""Weather data provider combining NWS forecasts with Open-Meteo ensemble models.

Fetches structured NWS forecasts and multi-model (GFS, ECMWF, GEM) ensemble
data from Open-Meteo. Computes model consensus statistics and delegates
historical bias queries to the forecast_bias SQLite table.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.models import BiasReport, CityForecast, EnsembleRun, ModelConsensus
from traderbot.data.weather.nws_client import NwsClient
from traderbot.db import get_connection
from traderbot.db.forecast_bias import query_bias as _query_bias

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
#  Open-Meteo ensemble configuration
# ------------------------------------------------------------------

_OPEN_METEO_ENSEMBLE_URL = "https://api.open-meteo.com/v1/forecast"
_OM_MODELS = ("gfs_seamless", "ecmwf_ifs", "gem_global")
_REQUEST_TIMEOUT = 20.0

# ------------------------------------------------------------------
#  City coordinate map (shared with NwsClient)
# ------------------------------------------------------------------

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

# Short-code aliases for CLI convenience
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


def _resolve_city(city_input: str) -> str | None:
    """Resolve a city input (full name, short code, or ticker prefix) to a full city name."""
    if city_input in _CITY_MAP:
        return city_input
    if city_input in _CITY_ALIASES:
        return _CITY_ALIASES[city_input]
    # Check ticker prefix
    for prefix, (name, _, _, _) in _KALSHI_CITY_MAP.items():
        if prefix == city_input:
            return name
    return None


# Kalshi ticker → (city_name, lat, lon, timezone)
_KALSHI_CITY_MAP: dict[str, tuple[str, float, float, str]] = {
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


class WeatherDataProvider(BaseDataProvider):
    """Combined NWS + Open-Meteo ensemble weather data provider.

    Fetches structured forecasts from NWS and multi-model ensemble data
    from Open-Meteo (GFS, ECMWF, GEM). Computes model consensus statistics
    and delegates historical bias queries to the forecast_bias SQLite table.

    Usage::

        async with WeatherDataProvider() as provider:
            forecasts = await provider.get_forecasts(["Minneapolis", "Chicago"])
            consensus = await provider.get_model_consensus("Minneapolis")
            bias = await provider.get_historical_bias("Minneapolis", model="nws")
    """

    def __init__(
        self,
        nws_client: NwsClient | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a WeatherDataProvider.

        Args:
            nws_client: Pre-configured NwsClient; one is created if omitted.
            http_client: Pre-configured httpx.AsyncClient for Open-Meteo calls;
                one is created if omitted.
        """
        self._nws = nws_client or NwsClient()
        self._owns_nws = nws_client is None
        self._http = http_client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        self._owns_http = http_client is None

    async def close(self) -> None:
        """Clean up owned httpx clients."""
        if self._owns_http:
            await self._http.aclose()
        if self._owns_nws:
            await self._nws.close()

    async def __aenter__(self) -> WeatherDataProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    #  BaseDataProvider interface
    # ------------------------------------------------------------------

    async def get_forecasts(
        self, cities: list[str], station: str | None = None
    ) -> dict[str, CityForecast]:
        """Fetch NWS forecasts for a list of cities, warming Open-Meteo ensemble in parallel.

        Args:
            cities: List of city names or short codes (e.g. 'New York', 'NYC', 'KXHIGHNY').
            station: Optional ICAO airport station code (e.g. KLGA, KLAX). When provided,
                overrides the city-center coordinates with airport coordinates.

        Returns:
            Dict mapping resolved city name to its CityForecast (sourced from NWS).
            Cities that fail to resolve are omitted silently.
        """
        resolved: list[str] = []
        for c in cities:
            name = _resolve_city(c)
            if name:
                resolved.append(name)
            else:
                logger.warning("Unknown city input: %s", c)
        if not resolved:
            return {}

        # Launch NWS forecast fetches for every resolved city.
        if station is not None:
            nws_tasks = [self._nws.get_forecast(0, 0, station=station) for c in resolved]
        else:
            nws_tasks = [self._nws.get_forecast(_CITY_MAP[c][0], _CITY_MAP[c][1]) for c in resolved]
        # Fire Open-Meteo ensemble fetches in parallel (warm cache, no return needed).
        om_tasks = [
            self._fetch_open_meteo_ensemble(_CITY_MAP[c][0], _CITY_MAP[c][1]) for c in resolved
        ]

        nws_results = await asyncio.gather(*nws_tasks, return_exceptions=True)
        # Don't block on Open-Meteo failures — fire and forget.
        _ = await asyncio.gather(*om_tasks, return_exceptions=True)

        forecasts: dict[str, CityForecast] = {}
        success_count = 0
        for city, result in zip(resolved, nws_results, strict=True):
            if isinstance(result, Exception):
                logger.error("NWS fetch failed for %s: %s", city, result)
            elif isinstance(result, CityForecast):
                forecasts[city] = result
                success_count += 1

        logger.info("get_forecasts: %d/%d cities succeeded", success_count, len(resolved))
        return forecasts

    async def get_model_consensus(self, city: str) -> ModelConsensus:
        """Query Open-Meteo ensemble (GFS, ECMWF, GEM) and aggregate statistics.

        Args:
            city: City name to get consensus for.

        Returns:
            ModelConsensus with mean_temp, std_dev, spread, agreement_score.

        Raises:
            ValueError: If the city is unknown.
            RuntimeError: If no ensemble data is returned from Open-Meteo.
        """
        coords = _CITY_MAP.get(city)
        if coords is None:
            raise ValueError(f"Unknown city: {city}")

        ensemble_data = await self._fetch_open_meteo_ensemble(*coords)

        runs: list[EnsembleRun] = []
        now = datetime.now()

        for model_name in _OM_MODELS:
            suffix = f"temperature_2m_max_{model_name}"
            temps: list[float] = ensemble_data.get("daily", {}).get(suffix, [])
            if temps:
                runs.append(
                    EnsembleRun(
                        model_name=model_name,
                        forecast_temp_f=float(temps[0]),
                        valid_time=now,
                    )
                )

        if not runs:
            raise RuntimeError(f"No ensemble model data returned for {city}")

        temps = [r.forecast_temp_f for r in runs]
        n = len(temps)
        mean = sum(temps) / n
        variance = sum((t - mean) ** 2 for t in temps) / n
        std = variance**0.5
        spread = max(temps) - min(temps) if n > 1 else 0.0

        # Agreement: 1.0 when std ≈ 0, decays as std grows relative to |mean|.
        agreement = max(0.0, 1.0 - (std / max(abs(mean), 1.0)))
        agreement = min(1.0, agreement)

        logger.info("get_model_consensus: %d models, agreement=%.3f", len(runs), agreement)

        return ModelConsensus(
            mean_temp=round(mean, 2),
            std_dev=round(std, 2),
            spread=round(spread, 2),
            models_used=[r.model_name for r in runs],
            agreement_score=round(agreement, 3),
        )

    async def get_historical_bias(
        self, city: str, model: str = "nws", days: int = 90
    ) -> BiasReport:
        """Query historical forecast bias from the SQLite bias table.

        Args:
            city: City name.
            model: Model identifier (default: "nws").
            days: Lookback window in days (default: 90).

        Returns:
            BiasReport with accuracy statistics. Returns zeros when no data
            exists yet for the city/model combination.
        """
        with get_connection() as conn:
            stats = _query_bias(conn, city, model, days)

        logger.info(
            "get_historical_bias: city=%s model=%s mean_error=%.3f count=%d",
            city,
            model,
            stats["mean_error"],
            stats["count"],
        )

        return BiasReport(
            city=city,
            model=model,
            total_comparisons=stats["count"],
            mean_error=stats["mean_error"],
            mean_abs_error=stats["mean_abs_error"],
            std_error=stats["std_error"],
            last_n_days=stats["last_n_days"],
        )

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_open_meteo_ensemble(self, lat: float, lon: float) -> dict[str, Any]:
        """Hit the Open-Meteo ensemble endpoint for GFS, ECMWF, GEM daily max temps.

        Returns the raw JSON response keyed by model name.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "models": ",".join(_OM_MODELS),
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": "America/New_York",
            "forecast_days": 3,
        }
        try:
            response = await self._http.get(_OPEN_METEO_ENSEMBLE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Open-Meteo returned HTTP {exc.response.status_code} for {lat:.4f},{lon:.4f}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Failed to reach Open-Meteo for {lat:.4f},{lon:.4f}: {exc}"
            ) from exc

        return response.json()
