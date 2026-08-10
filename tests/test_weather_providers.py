"""Tests for the weather data providers (DD-028): OpenMeteoProvider, NwsProvider.

Uses httpx MockTransport so no real network calls are made. Verifies the
fetch/insert round-trip writes rows into a temp SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from traderbot.data.providers import NwsProvider, OpenMeteoProvider
from traderbot.data.providers.weather_cities import CITIES


def _open_meteo_ok_response() -> httpx.Response:
    daily = {
        "time": ["2026-08-04"],
        "temperature_2m_max_gfs_seamless": [90.0],
        "temperature_2m_min_gfs_seamless": [70.0],
        "precipitation_sum_gfs_seamless": [0.0],
        "precipitation_probability_max_gfs_seamless": [10.0],
        "windspeed_10m_max_gfs_seamless": [5.0],
        "windgusts_10m_max_gfs_seamless": [9.0],
        "temperature_2m_max_ecmwf_ifs": [89.0],
        "temperature_2m_min_ecmwf_ifs": [69.0],
        "precipitation_sum_ecmwf_ifs": [0.1],
        "precipitation_probability_max_ecmwf_ifs": [20.0],
        "windspeed_10m_max_ecmwf_ifs": [6.0],
        "windgusts_10m_max_ecmwf_ifs": [10.0],
        "temperature_2m_max_gem_global": [88.0],
        "temperature_2m_min_gem_global": [68.0],
        "precipitation_sum_gem_global": [0.2],
        "precipitation_probability_max_gem_global": [30.0],
        "windspeed_10m_max_gem_global": [7.0],
        "windgusts_10m_max_gem_global": [11.0],
    }
    return httpx.Response(200, json={"daily": daily})


def _nws_points_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "properties": {
                "cwa": "OKX",
                "gridX": 35,
                "gridY": 35,
                "forecast": "https://api.weather.gov/gridpoints/OKX/35,35/forecast",
            }
        },
    )


def _nws_forecast_response() -> httpx.Response:
    periods = [
        {
            "startTime": "2026-08-04T12:00:00-04:00",
            "isDaytime": True,
            "temperature": 88,
            "probabilityOfPrecipitation": {"value": 10},
            "windSpeed": "5 mph",
            "detailedForecast": "Sunny.",
        },
        {
            "startTime": "2026-08-04T18:00:00-04:00",
            "isDaytime": False,
            "temperature": 68,
            "probabilityOfPrecipitation": {"value": 20},
            "windSpeed": "8 mph",
            "detailedForecast": "Clear.",
        },
    ]
    return httpx.Response(200, json={"properties": {"periods": periods}})


@pytest.mark.asyncio
async def test_open_meteo_fetch_and_insert(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.open-meteo.com" in str(request.url)
        return _open_meteo_ok_response()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenMeteoProvider(db_path=tmp_path / "test.db", http_client=client)

    data = await provider.fetch()

    assert "New York" in data
    assert "daily" in data["New York"]

    inserted = await provider.insert(data)
    await client.aclose()

    assert inserted > 0
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        rows = conn.execute("SELECT COUNT(*) FROM weather_forecasts").fetchone()
        assert rows is not None
        assert rows[0] == inserted
        sample = conn.execute(
            "SELECT city, model, variable, value FROM weather_forecasts "
            "WHERE city='New York' AND model='gfs_seamless' "
            "AND variable='temperature_2m_max'"
        ).fetchone()
        assert sample is not None
        assert sample[3] == 90.0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_open_meteo_fetch_error_is_isolated(tmp_path: Path) -> None:
    # Philadelphia coordinates (39.95, -75.16) -> 500; everything else OK.
    def handler(request: httpx.Request) -> httpx.Response:
        if "39.95" in str(request.url) and "-75.16" in str(request.url):
            return httpx.Response(500, text="boom")
        return _open_meteo_ok_response()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenMeteoProvider(db_path=tmp_path / "test.db", http_client=client)

    data = await provider.fetch()

    assert "Philadelphia" not in data
    assert "New York" in data
    assert len(data) == len(CITIES) - 1
    await client.aclose()


@pytest.mark.asyncio
async def test_nws_fetch_and_insert(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/points/" in str(request.url):
            return _nws_points_response()
        if "/forecast" in str(request.url):
            return _nws_forecast_response()
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NwsProvider(db_path=tmp_path / "test.db", http_client=client)

    data = await provider.fetch()

    assert "New York" in data
    assert len(data["New York"]) == 2

    inserted = await provider.insert(data)
    await client.aclose()

    assert inserted > 0
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        rows = conn.execute("SELECT COUNT(*) FROM nws_forecasts").fetchone()
        assert rows is not None
        assert rows[0] == inserted
        sample = conn.execute(
            "SELECT city, high_temp_f, low_temp_f FROM nws_forecasts WHERE city='New York'"
        ).fetchone()
        assert sample is not None
        assert sample[1] == 88.0
        assert sample[2] == 68.0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_nws_fetch_error_is_isolated(tmp_path: Path) -> None:
    # Philadelphia coordinates (39.95, -75.16) -> 500; everything else OK.
    def handler(request: httpx.Request) -> httpx.Response:
        if "39.95" in str(request.url) and "-75.16" in str(request.url):
            return httpx.Response(500, text="boom")
        if "/points/" in str(request.url):
            return _nws_points_response()
        if "/forecast" in str(request.url):
            return _nws_forecast_response()
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NwsProvider(db_path=tmp_path / "test.db", http_client=client)

    data = await provider.fetch()

    assert "Philadelphia" not in data
    assert "New York" in data
    await client.aclose()


def test_provider_metadata() -> None:
    open_meteo = OpenMeteoProvider()
    nws = NwsProvider()

    assert open_meteo.name == "open-meteo"
    assert nws.name == "nws"
    assert open_meteo.interval_seconds == 3600.0
    assert nws.interval_seconds == 3600.0


def test_json_payloads_are_serializable() -> None:
    daily = {"time": ["2026-08-04"]}
    # What insert stores must be JSON-serializable by sqlite3.
    payload = json.dumps({"daily": daily})
    assert isinstance(payload, str)
