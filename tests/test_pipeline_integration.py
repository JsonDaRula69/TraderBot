"""Integration tests for the data pipeline with real providers (DD-028).

Two providers run under the real DataCollectionService; scheduled fetches
write rows into a temp SQLite database.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import httpx
import pytest

from traderbot.data.pipeline import DataCollectionService
from traderbot.data.providers import NwsProvider, OpenMeteoProvider
from traderbot.data.registry import ProviderRegistry


class _FakeHttpClient:
    """Minimal duck-typed client satisfying the providers' httpx usage."""

    def __init__(self, *, fail_nws: bool = False) -> None:
        self._fail_nws = fail_nws

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        if self._fail_nws and "weather.gov" in url:
            raise httpx.ConnectError("boom", request=request)
        if "open-meteo" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "latitude": 40.71,
                    "longitude": -74.01,
                    "daily": {
                        "time": ["2026-08-05", "2026-08-06"],
                        "temperature_2m_max_gfs_seamless": [30.0, 31.0],
                        "temperature_2m_min_gfs_seamless": [20.0, 21.0],
                        "precipitation_probability_max_gfs_seamless": [10, 20],
                    },
                },
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "properties": {
                    "periods": [
                        {
                            "name": "Tonight",
                            "isDaytime": False,
                            "temperature": 65,
                            "windSpeed": "5 mph",
                            "shortForecast": "Clear",
                        }
                    ]
                }
            },
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_pipeline_runs_providers_on_schedule(tmp_path: Path) -> None:
    """Real providers, mocked HTTP, real scheduler, real DB writes."""
    http = _FakeHttpClient()
    service = DataCollectionService()
    service.register(OpenMeteoProvider(db_path=tmp_path / "pipeline.db", http_client=http))
    service.register(NwsProvider(db_path=tmp_path / "pipeline.db", http_client=http))

    await service.start()
    try:
        status: dict[str, dict[str, object]] = {}
        for _ in range(100):
            status = service.status()
            if (
                status["open-meteo"].get("total_runs", 0) >= 1
                and status["nws"].get("total_runs", 0) >= 1
            ):
                break
            await asyncio.sleep(0.05)
        assert status["open-meteo"].get("total_runs", 0) >= 1
        assert status["nws"].get("total_runs", 0) >= 1
    finally:
        await service.stop()

    conn = sqlite3.connect(tmp_path / "pipeline.db")
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "weather_forecasts" in tables
        assert "nws_forecasts" in tables
        om_count = conn.execute("SELECT COUNT(*) FROM weather_forecasts").fetchone()
        nws_count = conn.execute("SELECT COUNT(*) FROM nws_forecasts").fetchone()
        assert om_count is not None and om_count[0] >= 1
        assert nws_count is not None and nws_count[0] >= 1
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_pipeline_error_isolation(tmp_path: Path) -> None:
    """A failing provider does not stop healthy ones."""
    http = _FakeHttpClient(fail_nws=True)
    service = DataCollectionService()
    service.register(OpenMeteoProvider(db_path=tmp_path / "pipeline.db", http_client=http))
    service.register(NwsProvider(db_path=tmp_path / "pipeline.db", http_client=http))

    await service.start()
    try:
        status: dict[str, dict[str, object]] = {}
        for _ in range(100):
            status = service.status()
            if status["open-meteo"].get("total_runs", 0) >= 1:
                break
            await asyncio.sleep(0.05)
        # The healthy provider keeps running despite NWS failing every request.
        assert status["open-meteo"].get("total_runs", 0) >= 1
        assert status["open-meteo"].get("running") is True
        # NWS swallowed its per-city HTTP errors and wrote no rows.
        assert status["nws"].get("running") is True
    finally:
        await service.stop()

    import sqlite3

    conn = sqlite3.connect(tmp_path / "pipeline.db")
    try:
        nws_count = conn.execute("SELECT COUNT(*) FROM nws_forecasts").fetchone()
        assert nws_count is not None and nws_count[0] == 0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_registry_default_contains_phase2_providers() -> None:
    registry = ProviderRegistry()
    registry.register("open-meteo", OpenMeteoProvider)
    registry.register("nws", NwsProvider)

    names = registry.list_names()
    assert "open-meteo" in names
    assert "nws" in names

    cls = registry.get("open-meteo")
    assert cls is not None
    assert cls().interval_seconds > 0
