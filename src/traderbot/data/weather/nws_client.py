from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from pathlib import Path

from traderbot.data.models import CityForecast
from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

_NWS_BASE_URL = "https://api.weather.gov"
_NWS_USER_AGENT = "TraderBot/1.0 (traderbot@example.com)"
_REQUEST_TIMEOUT = 15.0
_CACHE_FILE_NAME = "nws_gridpoints.json"

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

GridpointCache = dict[str, dict[str, Any]]


class NwsClientError(Exception):
    """Raised when the NWS API returns an error or fails to respond."""


class NwsClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._http = client or httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _NWS_USER_AGENT, "Accept": "application/geo+json"},
        )
        self._owns_client = client is None
        self._cache_path = cache_path or (get_data_dir() / _CACHE_FILE_NAME)
        self._cache: GridpointCache = {}
        self._cache_dirty = False
        self._load_cache()

    def _load_cache(self) -> None:
        if self._cache_path.exists():
            try:
                self._cache = json.loads(self._cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load gridpoint cache, starting fresh")
                self._cache = {}

    def _save_cache(self) -> None:
        if not self._cache_dirty:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))
        self._cache_dirty = False

    async def close(self) -> None:
        self._save_cache()
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> NwsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def resolve_gridpoint(self, lat: float, lon: float) -> dict[str, Any]:
        cache_key = f"{lat:.4f},{lon:.4f}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{_NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}"
        try:
            response = await self._http.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NwsClientError(
                f"NWS points endpoint returned {exc.response.status_code} "
                f"for {lat:.4f},{lon:.4f}"
            ) from exc
        except httpx.RequestError as exc:
            raise NwsClientError(
                f"Failed to reach NWS points endpoint for {lat:.4f},{lon:.4f}: {exc}"
            ) from exc

        data: dict[str, Any] = response.json()
        properties = data.get("properties", {})
        result = {
            "wfo": properties.get("cwa", ""),
            "gridX": properties.get("gridX"),
            "gridY": properties.get("gridY"),
            "forecast_url": properties.get("forecast", ""),
            "relative_location": properties.get("relativeLocation", {}),
        }

        if not result["wfo"] or result["gridX"] is None or result["gridY"] is None:
            raise NwsClientError(
                f"Gridpoint resolution failed: incomplete data in NWS response "
                f"for {lat:.4f},{lon:.4f}"
            )

        self._cache[cache_key] = result
        self._cache_dirty = True
        return result

    async def get_forecast(self, lat: float, lon: float) -> CityForecast:
        gridpoint = await self.resolve_gridpoint(lat, lon)
        forecast_url = gridpoint.get("forecast_url", "")
        if not forecast_url:
            forecast_url = (
                f"{_NWS_BASE_URL}/gridpoints/"
                f"{gridpoint['wfo']}/{gridpoint['gridX']},{gridpoint['gridY']}/forecast"
            )

        try:
            response = await self._http.get(forecast_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NwsClientError(
                f"NWS forecast endpoint returned {exc.response.status_code} "
                f"for {lat:.4f},{lon:.4f}"
            ) from exc
        except httpx.RequestError as exc:
            raise NwsClientError(
                f"Failed to reach NWS forecast endpoint for {lat:.4f},{lon:.4f}: {exc}"
            ) from exc

        data: dict[str, Any] = response.json()
        properties = data.get("properties", {})
        periods: list[dict[str, Any]] = properties.get("periods", [])
        if not periods:
            raise NwsClientError(
                f"No forecast periods in NWS response for {lat:.4f},{lon:.4f}"
            )

        current = periods[0]

        city_name = self._lat_lon_to_city(lat, lon)
        ticker = self._city_to_ticker(city_name)

        high_temp = float(current.get("temperature", 0) or 0)
        low_temp = float(current.get("temperature", 0) or 0)
        if current.get("isDaytime"):
            for p in periods[1:]:
                if not p.get("isDaytime"):
                    low_temp = float(p.get("temperature", 0) or 0)
                    break
        else:
            for p in periods[1:]:
                if p.get("isDaytime"):
                    high_temp = float(p.get("temperature", 0) or 0)
                    break

        precip_prob = 0.0
        pop_raw = current.get("probabilityOfPrecipitation", {})
        if isinstance(pop_raw, dict):
            precip_prob = float(pop_raw.get("value", 0) or 0) / 100.0
        elif pop_raw is not None:
            precip_prob = float(pop_raw) / 100.0

        wind_raw = current.get("windSpeed", "0 mph")
        wind_speed = 0.0
        if isinstance(wind_raw, str) and " " in wind_raw:
            with suppress(ValueError):
                wind_speed = float(wind_raw.split(" ")[0])

        generated_at_str = properties.get("generatedAt", "")
        forecast_date = datetime.now(UTC)
        if generated_at_str:
            with suppress(ValueError):
                forecast_date = datetime.fromisoformat(
                    generated_at_str.replace("Z", "+00:00")
                )

        return CityForecast(
            ticker=ticker,
            city=city_name,
            lat=lat,
            lon=lon,
            date=forecast_date.date(),
            high_temp_f=high_temp,
            low_temp_f=low_temp,
            precip_prob=precip_prob,
            wind_speed=wind_speed,
            detailed_forecast=current.get("detailedForecast", ""),
            source="nws",
        )

    async def get_forecasts(self, cities: list[str]) -> dict[str, CityForecast]:
        results: dict[str, CityForecast] = {}
        for city_name in cities:
            coords = _CITY_MAP.get(city_name)
            if coords is None:
                logger.warning("Unknown city: %s", city_name)
                continue
            try:
                results[city_name] = await self.get_forecast(*coords)
            except NwsClientError as exc:
                logger.error("Failed to get NWS forecast for %s: %s", city_name, exc)
        return results

    @staticmethod
    def _lat_lon_to_city(lat: float, lon: float) -> str:
        best: str | None = None
        best_dist = float("inf")
        for name, (clat, clon) in _CITY_MAP.items():
            dist = (lat - clat) ** 2 + (lon - clon) ** 2
            if dist < best_dist:
                best_dist = dist
                best = name
        return best or "Unknown"

    @staticmethod
    def _city_to_ticker(city_name: str) -> str:
        for prefix, (name, _lat, _lon, _tz) in _KALSHI_CITY_MAP.items():
            if name == city_name:
                return prefix
        return f"KXHIGH{city_name[:4].upper()}"


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
