"""NWS point forecast snapshot provider (DD-028).

Fetches the current NWS point forecast for every weather city and persists a
per-city daily high/low snapshot to the global TraderBot SQLite database.
Runs hourly by default; these snapshots record what NWS predicted at each
point in time for backtesting.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, override

import httpx

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.providers.weather_cities import CITIES, REQUEST_TIMEOUT
from traderbot.paths import get_db_path

logger = logging.getLogger(__name__)

NWS_BASE_URL = "https://api.weather.gov"
NWS_USER_AGENT = "TraderBot/2.0 (traderbot-alpha@example.com)"

_HOURLY_INTERVAL_SECONDS: float = 60.0 * 60.0  # one hour


class NwsProvider(BaseDataProvider):
    """Hourly NWS point-forecast snapshot provider.

    Args:
        db_path: SQLite database file. Defaults to
            ``~/.traderbot/traderbot.db`` (see :func:`traderbot.paths.get_db_path`).
        http_client: Optional pre-built ``httpx.AsyncClient`` (tests inject a
            mock transport). Owned by this provider when omitted.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__()
        self._db_path: Path = db_path or get_db_path()
        self._client: httpx.AsyncClient | None = http_client
        self._owns_client: bool = http_client is None
        self._gridpoint_cache: dict[str, dict[str, Any]] = {}

    @property
    @override
    def name(self) -> str:
        return "nws"

    @property
    @override
    def interval_seconds(self) -> float:
        return _HOURLY_INTERVAL_SECONDS

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"},
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _resolve_gridpoint(self, lat: float, lon: float) -> dict[str, Any]:
        key = f"{lat:.4f},{lon:.4f}"
        if key in self._gridpoint_cache:
            return self._gridpoint_cache[key]
        client = await self._get_client()
        resp = await client.get(f"{NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}")
        resp.raise_for_status()
        data = resp.json().get("properties", {})
        result = {
            "wfo": data.get("cwa", ""),
            "gridX": data.get("gridX"),
            "gridY": data.get("gridY"),
            "forecast_url": data.get("forecast", ""),
        }
        self._gridpoint_cache[key] = result
        return result

    @override
    async def fetch(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch the current NWS forecast for every configured city.

        Returns:
            A dict keyed by city name with a list of per-period forecast dicts.
        """
        client = await self._get_client()
        results: dict[str, list[dict[str, Any]]] = {}
        for city, (lat, lon) in CITIES.items():
            try:
                gridpoint = await self._resolve_gridpoint(lat, lon)
                forecast_url = gridpoint.get("forecast_url", "")
                if not forecast_url:
                    wfo = gridpoint["wfo"]
                    gx = gridpoint["gridX"]
                    gy = gridpoint["gridY"]
                    forecast_url = f"{NWS_BASE_URL}/gridpoints/{wfo}/{gx},{gy}/forecast"
                resp = await client.get(forecast_url)
                resp.raise_for_status()
                periods = resp.json().get("properties", {}).get("periods", [])
                city_results: list[dict[str, Any]] = []
                for period in periods:
                    city_results.append(
                        {
                            "city": city,
                            "is_daytime": period.get("isDaytime", True),
                            "date": str(period.get("startTime", ""))[:10],
                            "high_temp_f": (
                                float(period["temperature"]) if period.get("isDaytime") else None
                            ),
                            "low_temp_f": (
                                float(period["temperature"])
                                if not period.get("isDaytime")
                                else None
                            ),
                            "precip_prob": (
                                (period.get("probabilityOfPrecipitation", {}) or {}).get("value", 0)
                            ),
                            "wind_speed": (
                                str(period.get("windSpeed", "0 mph")).split()[0]
                                if period.get("windSpeed")
                                else 0
                            ),
                            "detailed_forecast": str(period.get("detailedForecast", "")),
                        }
                    )
                results[city] = city_results
            except httpx.HTTPError:
                logger.warning("nws fetch failed for %s", city, exc_info=True)
        return results

    @override
    async def insert(self, data: dict[str, list[dict[str, Any]]]) -> int:
        """Persist the per-city NWS forecast snapshots into the SQLite database."""
        snapshot_ts = datetime.now(UTC).isoformat()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            self._create_tables(conn)
            inserted = 0
            for city, periods in data.items():
                # Merge daytime/nighttime periods by date.
                by_date: dict[str, dict[str, Any]] = {}
                for f in periods:
                    if f.get("city") != city:
                        continue
                    date = f["date"]
                    key = f"{city}|{date}"
                    if key not in by_date:
                        by_date[key] = {"city": city, "forecast_date": date}
                    if f["is_daytime"] and f.get("high_temp_f") is not None:
                        by_date[key]["high_temp_f"] = f["high_temp_f"]
                    elif not f["is_daytime"] and f.get("low_temp_f") is not None:
                        by_date[key]["low_temp_f"] = f["low_temp_f"]
                    if f.get("precip_prob"):
                        by_date[key]["precip_prob"] = f["precip_prob"]
                    if f.get("wind_speed"):
                        by_date[key]["wind_speed"] = f["wind_speed"]
                    if f.get("detailed_forecast"):
                        by_date[key]["detailed_forecast"] = f["detailed_forecast"]
                for row in by_date.values():
                    conn.execute(
                        """INSERT OR IGNORE INTO nws_forecasts
                           (snapshot_ts, city, forecast_date, high_temp_f, low_temp_f,
                            precip_prob, wind_speed, detailed_forecast)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            snapshot_ts,
                            row["city"],
                            row["forecast_date"],
                            row.get("high_temp_f"),
                            row.get("low_temp_f"),
                            row.get("precip_prob"),
                            row.get("wind_speed"),
                            row.get("detailed_forecast"),
                        ),
                    )
                    inserted += 1
            conn.commit()
            logger.info("nws persisted %d forecast rows (snapshot %s)", inserted, snapshot_ts)
            return inserted
        finally:
            conn.close()

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS nws_forecasts (
                   snapshot_ts TEXT NOT NULL,
                   city TEXT NOT NULL,
                   forecast_date TEXT NOT NULL,
                   high_temp_f REAL,
                   low_temp_f REAL,
                   precip_prob REAL,
                   wind_speed REAL,
                   detailed_forecast TEXT,
                   PRIMARY KEY (snapshot_ts, city, forecast_date)
               )"""
        )
        conn.commit()


__all__ = ["NwsProvider"]
