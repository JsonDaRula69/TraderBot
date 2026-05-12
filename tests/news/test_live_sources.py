"""Live integration tests for all 8 new data sources.

These tests make real API calls. Marked @pytest.mark.live.
Skip gracefully when API keys are missing or network is unavailable.
"""

import os

import httpx
import pytest

from traderbot.news.models import DataPoint, NewsCategory, NewsSource
from traderbot.news.sources import NewsAggregator

pytestmark = pytest.mark.live


def _requires_internet() -> None:
    try:
        httpx.get("https://api.open-meteo.com", timeout=5)
    except Exception:
        pytest.skip("No internet access")


def _requires_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"Environment variable {name} not set")
    return value


def _assert_datapoint(dp: DataPoint, expected_source: NewsSource) -> None:
    assert isinstance(dp, DataPoint), f"Expected DataPoint, got {type(dp)}"
    assert dp.id, "DataPoint id is empty"
    assert dp.source == expected_source, f"Expected {expected_source}, got {dp.source}"
    assert dp.title, "DataPoint title is empty"
    assert isinstance(dp.data, dict), f"data is {type(dp.data)}, expected dict"
    assert dp.timestamp, "DataPoint timestamp is empty"
    assert isinstance(dp.ticker_refs, list), "ticker_refs should be a list"
    assert isinstance(dp.metadata, dict), "metadata should be a dict"


@pytest.mark.asyncio
async def test_open_meteo_weather_forecast() -> None:
    _requires_internet()
    na = NewsAggregator()
    results = await na._fetch_open_meteo(limit=3)
    assert len(results) > 0, "Should return at least 1 weather DataPoint"
    _assert_datapoint(results[0], NewsSource.OPEN_METEO)
    assert results[0].category == NewsCategory.WEATHER
    assert "temp_f" in results[0].data, "Weather data should contain temp_f"
    assert isinstance(results[0].data["temp_f"], int), "temp_f should be int (Fahrenheit)"


@pytest.mark.asyncio
async def test_thesportsdb_events() -> None:
    _requires_internet()
    na = NewsAggregator()
    results = await na._fetch_thesportsdb(limit=5)
    if not results:
        pytest.skip("No sports events found for today")
    _assert_datapoint(results[0], NewsSource.THESPORTSDB)
    assert results[0].category == NewsCategory.SPORTS
    assert "home_team" in results[0].data or "away_team" in results[0].data


@pytest.mark.asyncio
async def test_coincap_crypto_assets() -> None:
    _requires_internet()
    na = NewsAggregator()
    results = await na._fetch_coincap(limit=5)
    assert len(results) > 0, "Should return at least 1 crypto DataPoint"
    _assert_datapoint(results[0], NewsSource.COINCAP)
    assert results[0].category == NewsCategory.CRYPTO
    assert "price_cents" in results[0].data, "Should contain price_cents"
    assert isinstance(results[0].data["price_cents"], int), "price_cents should be int"


@pytest.mark.asyncio
async def test_ballotpedia_deprecated() -> None:
    _requires_internet()
    na = NewsAggregator()
    results = await na._fetch_ballotpedia(limit=5)
    assert results == [], "Ballotpedia RSS is deprecated and should return empty"


@pytest.mark.asyncio
async def test_openweathermap_weather() -> None:
    _requires_internet()
    _requires_env("OPENWEATHER_API_KEY")
    na = NewsAggregator()
    results = await na._fetch_openweathermap(limit=3)
    if not results:
        pytest.skip("OpenWeatherMap returned no results (key may be invalid)")
    _assert_datapoint(results[0], NewsSource.OPENWEATHERMAP)
    assert results[0].category == NewsCategory.WEATHER
    assert "temp_f" in results[0].data, "Should contain temp_f"
    assert isinstance(results[0].data["temp_f"], int), "temp_f should be int"


@pytest.mark.asyncio
async def test_fred_economic_data() -> None:
    _requires_internet()
    _requires_env("FRED_API_KEY")
    na = NewsAggregator()
    results = await na._fetch_fred(limit=3)
    if not results:
        pytest.skip("FRED returned no results (key may be invalid)")
    _assert_datapoint(results[0], NewsSource.FRED)
    assert results[0].category in (NewsCategory.ECONOMICS, NewsCategory.FINANCIALS)
    assert "series_id" in results[0].data, "Should contain series_id"
    assert "value" in results[0].data, "Should contain value"


@pytest.mark.asyncio
async def test_google_trends_graceful() -> None:
    _requires_internet()
    na = NewsAggregator()
    results = await na._fetch_google_trends(limit=5)
    assert isinstance(results, list), "Should return a list, not an exception"
    if results:
        _assert_datapoint(results[0], NewsSource.GOOGLE_TRENDS)