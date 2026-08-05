"""Open-Meteo ensemble forecast snapshot provider (DD-028).

Fetches the current ensemble forecast (GFS seamless, ECMWF IFS, GEM Global)
for every weather city and persists a per-model daily forecast snapshot to
the global TraderBot SQLite database. Runs hourly by default.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, override

import httpx

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.providers.weather_cities import (
    CITIES,
    OM_DAILY_VARS,
    OM_MODELS,
    REQUEST_TIMEOUT,
)
from traderbot.paths import get_db_path

logger = logging.getLogger(__name__)

OM_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_HOURLY_INTERVAL_SECONDS: float = 60.0 * 60.0  # one hour


class OpenMeteoProvider(BaseDataProvider):
    """Hourly ensemble forecast snapshot provider.

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

    @property
    @override
    def name(self) -> str:
        return "open-meteo"

    @property
    @override
    def interval_seconds(self) -> float:
        return _HOURLY_INTERVAL_SECONDS

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @override
    async def fetch(self) -> dict[str, Any]:
        """Fetch ensemble forecasts for every configured city.

        Returns:
            A dict keyed by city name with the raw Open-Meteo JSON response
            (``{"daily": {...}}``) per city.
        """
        client = await self._get_client()
        results: dict[str, Any] = {}
        for city, (lat, lon) in CITIES.items():
            params = {
                "latitude": lat,
                "longitude": lon,
                "models": ",".join(OM_MODELS),
                "daily": ",".join(OM_DAILY_VARS),
                "forecast_days": 7,
                "temperature_unit": "fahrenheit",
                "timezone": "America/New_York",
            }
            try:
                resp = await client.get(OM_FORECAST_URL, params=params)
                resp.raise_for_status()
                results[city] = resp.json()
            except httpx.HTTPError:
                logger.warning("open-meteo fetch failed for %s", city, exc_info=True)
        return results

    @override
    async def insert(self, data: dict[str, Any]) -> int:
        """Persist the per-city ensemble snapshots into the SQLite database."""
        snapshot_ts = datetime.now(UTC).isoformat()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            self._create_tables(conn)
            inserted = 0
            for city, payload in data.items():
                lat, lon = CITIES[city]
                daily = payload.get("daily", {})
                times = daily.get("time", [])
                for model in OM_MODELS:
                    for var_name in OM_DAILY_VARS:
                        values = daily.get(f"{var_name}_{model}", [])
                        for i, date in enumerate(times):
                            if i >= len(values) or values[i] is None:
                                continue
                            try:
                                conn.execute(
                                    """INSERT OR IGNORE INTO weather_forecasts
                                       (snapshot_ts, city, latitude, longitude, model,
                                        valid_date, variable, value)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (
                                        snapshot_ts,
                                        city,
                                        lat,
                                        lon,
                                        model,
                                        date,
                                        var_name,
                                        float(values[i]),
                                    ),
                                )
                                inserted += 1
                            except (ValueError, TypeError):
                                continue
            conn.commit()
            logger.info(
                "open-meteo persisted %d forecast rows (snapshot %s)", inserted, snapshot_ts
            )
            return inserted
        finally:
            conn.close()

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS weather_forecasts (
                   snapshot_ts TEXT NOT NULL,
                   city TEXT NOT NULL,
                   latitude REAL NOT NULL,
                   longitude REAL NOT NULL,
                   model TEXT NOT NULL,
                   valid_date TEXT NOT NULL,
                   variable TEXT NOT NULL,
                   value REAL NOT NULL,
                   PRIMARY KEY (snapshot_ts, city, model, valid_date, variable)
               )"""
        )
        conn.commit()


__all__ = ["OpenMeteoProvider"]
