"""Unit tests for all data source fetch methods with mocked responses."""

from unittest.mock import patch

import httpx
import pytest

from traderbot.news.models import NewsCategory, NewsSource
from traderbot.news.sources import (
    SOURCE_CATEGORY_COVERAGE,
    SOURCE_REQUIRES_KEY,
    DataSourcesConfig,
    NewsAggregator,
)

# ============================================================
# Helper: build a MockTransport-based client
# ============================================================


def _mock_client(handler):
    """Create an httpx.AsyncClient with a custom transport handler."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


# ============================================================
# Open-Meteo
# ============================================================


@pytest.mark.asyncio
async def test_open_meteo_success() -> None:
    """Open-Meteo returns DataPoints with valid forecast response."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "latitude": 40.71,
            "longitude": -74.01,
            "current": {
                "temperature_2m": 72.5,
                "weather_code": 0,
                "relative_humidity_2m": 55,
                "wind_speed_10m": 8.2,
            },
            "daily": {
                "temperature_2m_max": [78.0],
                "temperature_2m_min": [62.0],
            },
        })

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_open_meteo(limit=2)
    assert len(results) > 0
    dp = results[0]
    assert dp.source == NewsSource.OPEN_METEO
    assert dp.category == "weather"
    assert isinstance(dp.data["temp_f"], int)
    assert dp.data["temp_f"] == 72  # round(72.5) banker's rounding → 72


@pytest.mark.asyncio
async def test_open_meteo_category_filter() -> None:
    """Open-Meteo returns empty when WEATHER not in category filter."""
    na = NewsAggregator()
    results = await na._fetch_open_meteo(
        category_filter=[NewsCategory.CRYPTO], limit=5
    )
    assert results == []


@pytest.mark.asyncio
async def test_open_meteo_http_error() -> None:
    """Open-Meteo handles non-200 gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal error")

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_open_meteo(limit=1)
    assert results == []


# ============================================================
# TheSportsDB
# ============================================================


@pytest.mark.asyncio
async def test_thesportsdb_success() -> None:
    """TheSportsDB returns DataPoints with valid events."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "events": [
                {
                    "idEvent": "12345",
                    "strEvent": "Lakers vs Celtics",
                    "strHomeTeam": "Lakers",
                    "strAwayTeam": "Celtics",
                    "intHomeScore": "110",
                    "intAwayScore": "105",
                    "dateEvent": "2026-05-12",
                    "strTime": "19:30:00",
                    "strLeague": "NBA",
                    "strThumb": "",
                },
            ],
        })

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_thesportsdb(limit=2)
    assert len(results) > 0
    dp = results[0]
    assert dp.source == NewsSource.THESPORTSDB
    assert dp.category == "sports"
    assert dp.data["home_team"] == "Lakers"


@pytest.mark.asyncio
async def test_thesportsdb_empty_events() -> None:
    """TheSportsDB handles null events gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"events": None})

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_thesportsdb(limit=2)
    assert results == []


# ============================================================
# CoinGecko
# ============================================================


@pytest.mark.asyncio
async def test_coingecko_success() -> None:
    """CoinGecko returns DataPoints with valid market data."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {
                "id": "bitcoin",
                "symbol": "btc",
                "name": "Bitcoin",
                "current_price": 67234.50,
                "market_cap": 1300000000000,
                "total_volume": 28000000000,
                "price_change_percentage_24h": 2.3,
                "last_updated": "2026-05-12T12:00:00.000Z",
            },
        ])

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_coingecko(limit=2)
    assert len(results) > 0
    dp = results[0]
    assert dp.source == NewsSource.COINGECKO
    assert dp.category == "crypto"
    assert dp.data["price_cents"] == 6723450
    assert isinstance(dp.data["price_cents"], int)


@pytest.mark.asyncio
async def test_coingecko_rate_limited() -> None:
    """CoinGecko returns empty on 429 rate limit."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"status": {"error_code": 429}})

    na = NewsAggregator(http_client=_mock_client(handler))
    results = await na._fetch_coingecko(limit=2)
    assert results == []


# ============================================================
# OpenWeatherMap
# ============================================================


@pytest.mark.asyncio
async def test_openweathermap_success() -> None:
    """OpenWeatherMap returns DataPoints with valid API key."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "cnt": 1,
            "list": [{
                "coord": {"lat": 40.71, "lon": -74.01},
                "name": "New York",
                "main": {"temp": 72.3, "temp_min": 62.1, "temp_max": 78.5, "humidity": 55},
                "wind": {"speed": 8.2},
                "weather": [{"id": 800, "description": "clear sky"}],
            }],
        })

    with patch("traderbot.news.sources.resolve_openweather_key", return_value="fake-key"):
        na = NewsAggregator(http_client=_mock_client(handler))
        results = await na._fetch_openweathermap(limit=2)
        assert len(results) > 0
        dp = results[0]
        assert dp.source == NewsSource.OPENWEATHERMAP
        assert isinstance(dp.data["temp_f"], int)


@pytest.mark.asyncio
async def test_openweathermap_no_key() -> None:
    """OpenWeatherMap returns empty when no API key."""
    with patch("traderbot.news.sources.resolve_openweather_key", return_value=None):
        na = NewsAggregator()
        results = await na._fetch_openweathermap(limit=2)
        assert results == []


# ============================================================
# FRED
# ============================================================


@pytest.mark.asyncio
async def test_fred_success() -> None:
    """FRED returns DataPoints with valid API key."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "observations": [{"date": "2026-04-01", "value": "314.5"}],
        })

    with patch("traderbot.news.sources.resolve_fred_key", return_value="fake-key"):
        na = NewsAggregator(http_client=_mock_client(handler))
        results = await na._fetch_fred(limit=2)
        assert len(results) > 0
        dp = results[0]
        assert dp.source == NewsSource.FRED


@pytest.mark.asyncio
async def test_fred_no_key() -> None:
    """FRED returns empty when no API key."""
    with patch("traderbot.news.sources.resolve_fred_key", return_value=None):
        na = NewsAggregator()
        results = await na._fetch_fred(limit=2)
        assert results == []


# ============================================================
# Google Trends
# ============================================================


@pytest.mark.asyncio
async def test_google_trends_no_pytrends() -> None:
    """Google Trends returns empty when pytrends not installed."""
    import sys

    with patch.dict(sys.modules, {}, clear=False):
        sys.modules.pop("pytrends", None)
        sys.modules.pop("pytrends.request", None)
        na = NewsAggregator()
        results = await na._fetch_google_trends(limit=5)
        assert results == []


@pytest.mark.asyncio
async def test_google_trends_category_filter() -> None:
    """Google Trends skips when MENTIONS/SOCIAL not in filter."""
    na = NewsAggregator()
    results = await na._fetch_google_trends(
        category_filter=[NewsCategory.CRYPTO], limit=5
    )
    assert results == []


# ============================================================
# DataSourcesConfig backward compatibility
# ============================================================


def test_datasources_config_legacy() -> None:
    """NewsAggregator works with legacy individual params."""
    na = NewsAggregator(newsapi_key="test-key")
    assert na._newsapi_key == "test-key"


def test_datasources_config_object() -> None:
    """NewsAggregator works with DataSourcesConfig object."""
    config = DataSourcesConfig(newsapi_key="test-key", openweather_key="owm-key")
    na = NewsAggregator(config=config)
    assert na._newsapi_key == "test-key"
    assert na._openweather_key == "owm-key"


def test_datasources_config_individual_wins() -> None:
    """Individual params take precedence over config."""
    config = DataSourcesConfig(newsapi_key="config-key")
    na = NewsAggregator(config=config, newsapi_key="explicit-key")
    assert na._newsapi_key == "explicit-key"


# ============================================================
# SOURCE_CATEGORY_COVERAGE
# ============================================================


def test_source_coverage_all_sources_have_entries() -> None:
    """All 11 NewsSource members (except TWITTER is allowed as [] stub) have coverage entries."""
    expected_sources = {
        NewsSource.NEWSAPI, NewsSource.REDDIT, NewsSource.TWITTER,
        NewsSource.OPEN_METEO, NewsSource.COINGECKO, NewsSource.THESPORTSDB,
        NewsSource.OPENWEATHERMAP, NewsSource.FRED, NewsSource.GOOGLE_TRENDS,
    }
    assert set(SOURCE_CATEGORY_COVERAGE.keys()) == expected_sources


# ============================================================
# SOURCE_REQUIRES_KEY
# ============================================================


def test_source_requires_key() -> None:
    """Only OpenWeatherMap and FRED require API keys."""
    assert NewsSource.OPENWEATHERMAP in SOURCE_REQUIRES_KEY
    assert NewsSource.FRED in SOURCE_REQUIRES_KEY
    assert NewsSource.NEWSAPI not in SOURCE_REQUIRES_KEY
    assert NewsSource.OPEN_METEO not in SOURCE_REQUIRES_KEY
