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
from traderbot.exceptions import DataError, ErrorCodes
from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

_NWS_BASE_URL = "https://api.weather.gov"
_NWS_USER_AGENT = "TraderBot/1.0 (traderbot@example.com)"
_REQUEST_TIMEOUT = 15.0
_CACHE_FILE_NAME = "nws_gridpoints.json"

from traderbot.data.weather.geo import (
    _CITY_MAP,
    _KALSHI_CITY_MAP,
    _STATION_MAP,
)

GridpointCache = dict[str, dict[str, Any]]


class NwsClientError(DataError):
    """Raised when the NWS API returns an error or fails to respond."""

    def __init__(
        self, message: str = "", error_code: int = ErrorCodes.NWS_CLIENT, **kwargs
    ) -> None:
        super().__init__(message, error_code=error_code, **kwargs)


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
            logger.debug("Gridpoint cache HIT for %s", cache_key)
            return cached

        logger.info("Gridpoint cache MISS for %s — resolving via NWS API", cache_key)

        url = f"{_NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}"
        try:
            response = await self._http.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NwsClientError(
                f"NWS points endpoint returned {exc.response.status_code} for {lat:.4f},{lon:.4f}"
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

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        station: str | None = None,
        offset: int = 0,
    ) -> CityForecast:
        """Fetch NWS forecast. If *station* is provided, use its coordinates.

        *offset* selects a non-current forecast period: 0 = today, 1 = tonight,
        2 = tomorrow day, etc.  The NWS response contains ~14 periods (7 days x 2).
        """
        if station is not None:
            coords = _STATION_MAP.get(station)
            if coords is None:
                available = ", ".join(sorted(_STATION_MAP))
                raise NwsClientError(f"Unknown station '{station}'. Available: {available}")
            lat, lon = coords

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
                f"NWS forecast endpoint returned {exc.response.status_code} for {lat:.4f},{lon:.4f}"
            ) from exc
        except httpx.RequestError as exc:
            raise NwsClientError(
                f"Failed to reach NWS forecast endpoint for {lat:.4f},{lon:.4f}: {exc}"
            ) from exc

        data: dict[str, Any] = response.json()
        properties = data.get("properties", {})
        periods: list[dict[str, Any]] = properties.get("periods", [])
        if not periods:
            raise NwsClientError(f"No forecast periods in NWS response for {lat:.4f},{lon:.4f}")

        current = periods[offset] if offset < len(periods) else periods[-1]

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

        generated_at_str = current.get("startTime", properties.get("generatedAt", ""))
        forecast_date = datetime.now(UTC)
        if generated_at_str:
            with suppress(ValueError):
                forecast_date = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))

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

    async def get_forecasts(
        self,
        cities: list[str],
        offset: int = 0,
    ) -> dict[str, CityForecast]:
        results: dict[str, CityForecast] = {}
        for city_name in cities:
            coords = _CITY_MAP.get(city_name)
            if coords is None:
                logger.warning("Unknown city: %s", city_name)
                continue
            try:
                results[city_name] = await self.get_forecast(*coords, offset=offset)
                logger.debug("Forecast fetched for %s", city_name)
            except NwsClientError as exc:
                logger.error("Failed to get NWS forecast for %s: %s", city_name, exc)
        logger.info("get_forecasts: %d/%d cities successful", len(results), len(cities))
        return results

    async def get_all_forecasts(
        self, lat: float, lon: float, station: str | None = None
    ) -> list[CityForecast]:
        """Return all available NWS forecast periods for a location."""
        if station is not None:
            coords = _STATION_MAP.get(station)
            if coords is None:
                available = ", ".join(sorted(_STATION_MAP))
                raise NwsClientError(f"Unknown station '{station}'. Available: {available}")
            lat, lon = coords

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
                f"NWS forecast endpoint returned {exc.response.status_code} for {lat:.4f},{lon:.4f}"
            ) from exc
        except httpx.RequestError as exc:
            raise NwsClientError(
                f"Failed to reach NWS forecast endpoint for {lat:.4f},{lon:.4f}: {exc}"
            ) from exc

        data: dict[str, Any] = response.json()
        properties = data.get("properties", {})
        periods: list[dict[str, Any]] = properties.get("periods", [])
        if not periods:
            raise NwsClientError(f"No forecast periods in NWS response for {lat:.4f},{lon:.4f}")

        city_name = self._lat_lon_to_city(lat, lon)
        ticker = self._city_to_ticker(city_name)
        results: list[CityForecast] = []

        for period in periods:
            high_temp = float(period.get("temperature", 0) or 0)
            low_temp = float(period.get("temperature", 0) or 0)
            if period.get("isDaytime"):
                high_temp = float(period.get("temperature", 0) or 0)
            else:
                low_temp = float(period.get("temperature", 0) or 0)

            precip_prob = 0.0
            pop_raw = period.get("probabilityOfPrecipitation", {})
            if isinstance(pop_raw, dict):
                precip_prob = float(pop_raw.get("value", 0) or 0) / 100.0
            elif pop_raw is not None:
                precip_prob = float(pop_raw) / 100.0

            wind_raw = period.get("windSpeed", "0 mph")
            wind_speed = 0.0
            if isinstance(wind_raw, str) and " " in wind_raw:
                with suppress(ValueError):
                    wind_speed = float(wind_raw.split(" ")[0])

            start_time_str = period.get("startTime", "")
            period_date = datetime.now(UTC)
            if start_time_str:
                with suppress(ValueError):
                    period_date = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))

            results.append(
                CityForecast(
                    ticker=ticker,
                    city=city_name,
                    lat=lat,
                    lon=lon,
                    date=period_date.date(),
                    high_temp_f=high_temp,
                    low_temp_f=low_temp,
                    precip_prob=precip_prob,
                    wind_speed=wind_speed,
                    detailed_forecast=period.get("detailedForecast", ""),
                    source="nws",
                )
            )

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
