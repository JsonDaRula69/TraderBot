"""Unified news source aggregator — NewsAPI, Reddit RSS, Twitter/X stub."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import random
from datetime import UTC, datetime
from dataclasses import dataclass, field
from typing import Any, ClassVar

import feedparser
import httpx

from traderbot.news.models import DataPoint, NewsCategory, NewsItem, NewsSource
from traderbot.profiles.config import resolve_fred_key, resolve_openweather_key

logger = logging.getLogger(__name__)

NEWSAPI_CATEGORY_QUERIES: dict[NewsCategory, str] = {
    NewsCategory.ECONOMICS: "economy OR GDP OR inflation OR \"federal reserve\" OR \"interest rates\"",
    NewsCategory.POLITICS: "politics OR election OR congress OR president OR legislation",
    NewsCategory.WEATHER: "weather OR hurricane OR tornado OR flood OR forecast OR storm",
    NewsCategory.SPORTS: "sports OR NFL OR NBA OR MLB OR NHL OR soccer OR championship",
    NewsCategory.SCIENCE_AND_TECHNOLOGY: "technology OR AI OR software OR \"space research\" OR science",
    NewsCategory.CRYPTO: "cryptocurrency OR bitcoin OR ethereum OR blockchain",
    NewsCategory.COMMODITIES: "commodities OR oil OR gold OR copper OR wheat OR futures",
    NewsCategory.COMPANIES: "\"company earnings\" OR stocks OR IPO OR merger OR acquisition",
    NewsCategory.ELECTIONS: "election OR vote OR polling OR primary OR ballot OR campaign",
    NewsCategory.ENTERTAINMENT: "entertainment OR movie OR music OR Oscar OR Grammy OR \"box office\"",
    NewsCategory.FINANCIALS: "financial OR banking OR markets OR trading OR NASDAQ OR \"S&P\"",
    NewsCategory.HEALTH: "health OR wellness OR psychology OR therapy OR mental health",
    NewsCategory.SOCIAL: "\"breaking news\" OR community OR trending OR viral",
    NewsCategory.MENTIONS: "trending OR celebrity OR mention OR viral",
}

REDDIT_CATEGORY_SUBREDDITS: dict[NewsCategory, list[str]] = {
    NewsCategory.ECONOMICS: ["economics", "Economics", "economy"],
    NewsCategory.POLITICS: ["politics", "PoliticalDiscussion"],
    NewsCategory.WEATHER: ["weather", "meteorology", "stormfront"],
    NewsCategory.SPORTS: ["sports", "nfl", "nba", "mlb", "soccer"],
    NewsCategory.SCIENCE_AND_TECHNOLOGY: ["technology", "science", "artificial", "MachineLearning"],
    NewsCategory.CRYPTO: ["cryptocurrency", "bitcoin", "ethereum"],
    NewsCategory.COMMODITIES: ["commodities", "oil", "gold"],
    NewsCategory.COMPANIES: ["stocks", "investing", "SecurityAnalysis"],
    NewsCategory.ELECTIONS: ["politics", "election"],
    NewsCategory.ENTERTAINMENT: ["entertainment", "movies", "music"],
    NewsCategory.FINANCIALS: ["finance", "investing", "stocks"],
    NewsCategory.HEALTH: ["mentalhealth", "psychology", "health"],
    NewsCategory.SOCIAL: ["news", "worldnews", "AskReddit"],
    NewsCategory.MENTIONS: ["news", "trending"],
}


class NewsAPIError(Exception):
    """Raised when the NewsAPI returns an error response."""


class NewsAPIAuthError(Exception):
    """Raised when NewsAPI returns 401 — permanent auth failure, no retry."""


class NewsAPIBudgetExceeded(Exception):
    """Raised when the client-side daily budget (100 req/day) is exhausted."""


@dataclass
class DataSourcesConfig:
    """Configuration for external data source API keys and settings."""

    newsapi_key: str | None = None
    openweather_key: str | None = None
    fred_key: str | None = None
    reddit_subreddits: list[str] | None = None
    daily_budget: int | None = None


SOURCE_CATEGORY_COVERAGE: dict[NewsSource, list[NewsCategory]] = {
    NewsSource.NEWSAPI: [
        NewsCategory.ECONOMICS,
        NewsCategory.POLITICS,
        NewsCategory.WEATHER,
        NewsCategory.SPORTS,
        NewsCategory.SCIENCE_AND_TECHNOLOGY,
        NewsCategory.CRYPTO,
        NewsCategory.COMMODITIES,
        NewsCategory.COMPANIES,
        NewsCategory.ELECTIONS,
        NewsCategory.ENTERTAINMENT,
        NewsCategory.FINANCIALS,
        NewsCategory.HEALTH,
        NewsCategory.SOCIAL,
        NewsCategory.MENTIONS,
    ],
    NewsSource.REDDIT: [
        NewsCategory.ECONOMICS,
        NewsCategory.POLITICS,
        NewsCategory.WEATHER,
        NewsCategory.SPORTS,
        NewsCategory.SCIENCE_AND_TECHNOLOGY,
        NewsCategory.CRYPTO,
        NewsCategory.COMMODITIES,
        NewsCategory.COMPANIES,
        NewsCategory.ELECTIONS,
        NewsCategory.ENTERTAINMENT,
        NewsCategory.FINANCIALS,
        NewsCategory.HEALTH,
        NewsCategory.SOCIAL,
        NewsCategory.MENTIONS,
    ],
    NewsSource.TWITTER: [],
    NewsSource.OPEN_METEO: [NewsCategory.WEATHER],
    NewsSource.COINGECKO: [NewsCategory.CRYPTO, NewsCategory.MENTIONS],
    NewsSource.THESPORTSDB: [NewsCategory.SPORTS],
    NewsSource.OPENWEATHERMAP: [NewsCategory.WEATHER],
    NewsSource.FRED: [NewsCategory.ECONOMICS, NewsCategory.FINANCIALS],
    NewsSource.GOOGLE_TRENDS: [NewsCategory.MENTIONS, NewsCategory.SOCIAL],
}

SOURCE_REQUIRES_KEY: frozenset[NewsSource] = frozenset({NewsSource.OPENWEATHERMAP, NewsSource.FRED})


class NewsAggregator:
    """Fetch and aggregate news from multiple sources with graceful degradation."""

    _MAX_PAGE_SIZE: ClassVar[int] = 100
    _THESPORTSDB_KEY: ClassVar[str] = "3"
    _THESPORTSDB_SPORTS: ClassVar[list[str]] = [
        "Soccer",
        "Basketball",
        "Baseball",
        "American_Football",
        "Ice_Hockey",
    ]

    _KALSHI_WEATHER_CITIES: ClassVar[dict[str, tuple[float, float]]] = {
        "KXHIGHNY": ("New York", 40.71, -74.01),
        "KXHIGHPHIL": ("Philadelphia", 39.95, -75.16),
        "KXHIGHTPHX": ("Phoenix", 33.45, -112.07),
        "KXHIGHTMIN": ("Minneapolis", 44.98, -93.26),
        "KXHIGHTSEA": ("Seattle", 47.61, -122.33),
        "KXHIGHTCHI": ("Chicago", 41.88, -87.63),
        "KXHIGHTHOU": ("Houston", 29.76, -95.37),
        "KXHIGHTLA": ("Los Angeles", 34.05, -118.24),
        "KXHIGHTMIA": ("Miami", 25.76, -80.19),
        "KXHIGHTDEN": ("Denver", 39.74, -104.99),
        "KXHIGHTATL": ("Atlanta", 33.75, -84.39),
        "KXHIGHTBOS": ("Boston", 42.36, -71.06),
        "KXHIGHTDAL": ("Dallas", 32.78, -96.80),
        "KXHIGHTDET": ("Detroit", 42.33, -83.05),
        "KXHIGHTSF": ("San Francisco", 37.77, -122.42),
    }

    # OWM city IDs for /group batch endpoint, keyed by Kalshi ticker
    _OWM_CITY_IDS: ClassVar[dict[str, int]] = {
        "KXHIGHNY": 5128581,
        "KXHIGHPHIL": 4560349,
        "KXHIGHTPHX": 5308655,
        "KXHIGHTMIN": 5037649,
        "KXHIGHTSEA": 5809844,
        "KXHIGHTCHI": 4887398,
        "KXHIGHTHOU": 4699066,
        "KXHIGHTLA": 5368361,
        "KXHIGHTMIA": 4164138,
        "KXHIGHTDEN": 5419384,
        "KXHIGHTATL": 4180439,
        "KXHIGHTBOS": 4930956,
        "KXHIGHTDAL": 4684888,
        "KXHIGHTDET": 4990729,
        "KXHIGHTSF": 5391959,
    }

    # Source fetch priority order — all active sources (TWITTER is stub)
    _SOURCE_PRIORITY: ClassVar[list[NewsSource]] = [
        NewsSource.NEWSAPI,
        NewsSource.REDDIT,
        NewsSource.OPEN_METEO,
        NewsSource.COINGECKO,
        NewsSource.THESPORTSDB,
        NewsSource.OPENWEATHERMAP,
        NewsSource.FRED,
        NewsSource.GOOGLE_TRENDS,
    ]

    _FRED_SERIES: ClassVar[dict[str, dict[str, str]]] = {
        "CPIAUCSL": {"name": "CPI (All Urban Consumers)", "units": "index", "category": "ECONOMICS"},
        "UNRATE": {"name": "Unemployment Rate", "units": "percent", "category": "ECONOMICS"},
        "FEDFUNDS": {"name": "Federal Funds Rate", "units": "percent", "category": "ECONOMICS"},
        "GDP": {"name": "Gross Domestic Product", "units": "billions", "category": "ECONOMICS"},
        "DFF": {"name": "Daily Fed Funds Rate", "units": "percent", "category": "FINANCIALS"},
        "T10Y2Y": {"name": "10Y-2Y Treasury Spread", "units": "percent", "category": "FINANCIALS"},
    }

    def __init__(
        self,
        config: DataSourcesConfig | None = None,
        newsapi_key: str | None = None,
        twitter_api_key: str | None = None,
        reddit_subreddits: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        daily_budget: int | None = None,
    ) -> None:
        if config is None:
            config = DataSourcesConfig()
        self._newsapi_key = newsapi_key if newsapi_key is not None else config.newsapi_key
        self._twitter_api_key = twitter_api_key
        self._openweather_key = config.openweather_key
        self._fred_key = config.fred_key
        self._reddit_subreddits = reddit_subreddits if reddit_subreddits is not None else (config.reddit_subreddits or ["politics", "economics", "weather"])
        self._client = http_client or httpx.AsyncClient()
        self._newsapi_base = "https://newsapi.org/v2"
        self.rate_limit_limit: int | None = None
        self.rate_limit_remaining: int | None = None
        self._daily_budget: int = daily_budget if daily_budget is not None else (config.daily_budget or int(os.environ.get("NEWSAPI_DAILY_BUDGET", "100")))
        self._newsapi_daily_count: int = 0
        self._budget_reset_date: str = ""
        self._owm_daily_count: int = 0
        self._owm_budget_date: str = ""

    def requires_api_key(self, source: NewsSource) -> bool:
        """Return whether a source requires an API key."""
        return source in SOURCE_REQUIRES_KEY

    def _check_daily_budget(self) -> None:
        """Enforce client-side daily request budget for NewsAPI, resetting at midnight UTC."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if today != self._budget_reset_date:
            self._budget_reset_date = today
            self._newsapi_daily_count = 0
        if self._newsapi_daily_count >= self._daily_budget:
            raise NewsAPIBudgetExceeded(
                f"NewsAPI daily budget exhausted ({self._newsapi_daily_count} requests today)"
            )
        self._newsapi_daily_count += 1

    async def fetch_recent(self, source: NewsSource, limit: int = 20, query: str | None = None, category_filter: list[NewsCategory] | None = None) -> list[NewsItem | DataPoint]:
        """Fetch recent items from a single source."""
        try:
            match source:
                case NewsSource.NEWSAPI:
                    if query:
                        return await self._fetch_everything(query, limit)
                    if category_filter:
                        return await self._fetch_category_news(category_filter, limit)
                    return await self._fetch_newsapi(limit)
                case NewsSource.TWITTER:
                    return await self._fetch_twitter(limit)
                case NewsSource.REDDIT:
                    subs = self._get_reddit_subs(category_filter)
                    return await self._fetch_reddit(limit, subreddits=subs, category_filter=category_filter)
                case NewsSource.OPEN_METEO:
                    return await self._fetch_open_meteo(category_filter, limit)
                case NewsSource.COINGECKO:
                    return await self._fetch_coingecko(category_filter, limit)
                case NewsSource.THESPORTSDB:
                    return await self._fetch_thesportsdb(category_filter, limit)
                case NewsSource.OPENWEATHERMAP:
                    return await self._fetch_openweathermap(category_filter, limit)
                case NewsSource.FRED:
                    return await self._fetch_fred(category_filter, limit)
                case NewsSource.GOOGLE_TRENDS:
                    return await self._fetch_google_trends(category_filter, limit)
        except Exception:
            logger.exception("Source %s failed, returning empty", source.value)
            return []
        return []

    async def fetch_all(
        self,
        limit: int = 20,
        category_filter: list[NewsCategory] | None = None,
        source_filter: NewsSource | None = None,
    ) -> list[NewsItem | DataPoint]:
        """Aggregate from all matching sources in parallel."""
        candidates: list[NewsSource] = [source_filter] if source_filter is not None else list(self._SOURCE_PRIORITY)

        # Filter candidates: exclude stubs, key-missing sources, category mismatches
        qualifying: list[NewsSource] = []
        for src in candidates:
            if src == NewsSource.TWITTER:
                continue
            if self.requires_api_key(src):
                if src == NewsSource.OPENWEATHERMAP and not self._openweather_key:
                    continue
                if src == NewsSource.FRED and not self._fred_key:
                    continue
            if category_filter is not None:
                covered = SOURCE_CATEGORY_COVERAGE.get(src, [])
                if not set(covered).intersection(category_filter):
                    continue
            qualifying.append(src)

        if not qualifying:
            return []

        # Build parallel tasks with source-specific routing
        async def _fetch_one(src: NewsSource) -> list[NewsItem | DataPoint]:
            if src == NewsSource.NEWSAPI:
                if category_filter:
                    return await self._fetch_category_news(category_filter, limit)
                return await self._fetch_newsapi(limit)
            if src == NewsSource.REDDIT:
                subs = self._get_reddit_subs(category_filter)
                return await self._fetch_reddit(limit, subreddits=subs, category_filter=category_filter)
            return await self.fetch_recent(src, limit=limit, category_filter=category_filter)

        tasks = [asyncio.ensure_future(_fetch_one(src)) for src in qualifying]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect, deduplicate, cap
        aggregated: list[NewsItem | DataPoint] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Source task failed: %s", result)
            elif isinstance(result, list):
                aggregated.extend(result)

        seen: set[str] = set()
        unique: list[NewsItem | DataPoint] = []
        for item in aggregated:
            if item.id not in seen:
                seen.add(item.id)
                unique.append(item)
        return unique[:limit]

    async def _fetch_newsapi(self, limit: int) -> list[NewsItem]:
        """Fetch top headlines from NewsAPI with 429 retry/backoff."""
        if not self._newsapi_key:
            logger.warning("NEWSAPI_API_KEY not set, skipping NewsAPI")
            return []

        if self.rate_limit_remaining is not None and self.rate_limit_remaining <= 0:
            logger.warning("NewsAPI rate limit exhausted (%d remaining), skipping", self.rate_limit_remaining)
            return []

        self._check_daily_budget()

        headers: dict[str, str] = {"X-Api-Key": self._newsapi_key}
        params: dict[str, Any] = {
            "pageSize": min(limit, self._MAX_PAGE_SIZE),
            "country": "us",  # required by NewsAPI — at least one of country/category/sources/q
        }

        max_retries = 3
        base_delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await self._client.get(
                    f"{self._newsapi_base}/top-headlines",
                    params=params,
                    headers=headers,
                )
                self._capture_rate_limits(response)

                if response.status_code == 429:
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            "NewsAPI rate limited (429), retry %d/%d in %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error("NewsAPI rate limit exhausted after %d retries", max_retries)
                    return []

                if response.status_code == 401:
                    raise NewsAPIAuthError("NewsAPI auth failed: invalid API key")

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", response.text[:200])
                    except Exception:
                        error_msg = response.text[:200]
                    raise NewsAPIError(f"NewsAPI HTTP {response.status_code}: {error_msg}")

                try:
                    data = response.json()
                except Exception:
                    logger.warning("NewsAPI returned non-JSON response, skipping")
                    return []

                articles = data.get("articles", [])
                items: list[NewsItem] = []
                for idx, article in enumerate(articles[:limit]):
                    try:
                        published = article.get("publishedAt", "")
                        published_at = (
                            datetime.fromisoformat(published.replace("Z", "+00:00"))
                            if published
                            else datetime.now(tz=UTC)
                        )
                        items.append(
                            NewsItem(
                                id=f"newsapi-{hashlib.md5((article.get('url') or '').encode()).hexdigest()[:8]}-{idx}",
                                title=article.get("title", "") or "",
                                body=article.get("description", "") or "",
                                source=NewsSource.NEWSAPI,
                                url=article.get("url", "") or "",
                                published_at=published_at,
                                ticker_refs=[],
                                category=None,
                                data_freshness="delayed_24h",
                                content_truncated=True,
                            )
                        )
                    except Exception:
                        logger.warning("Skipping malformed NewsAPI article at index %d", idx)
                        continue
                return items

            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        if last_exc is not None:
            logger.error("NewsAPI request failed: %s", last_exc)
        return []

    async def _fetch_category_news(self, categories: list[NewsCategory], limit: int = 20) -> list[NewsItem]:
        """Fetch news targeted to specific categories using /everything endpoint."""
        if not self._newsapi_key:
            logger.warning("NEWSAPI_API_KEY not set, skipping category news")
            return []

        per_cat = max(limit // len(categories), 5)

        async def _fetch_one(cat: NewsCategory) -> list[NewsItem]:
            query = NEWSAPI_CATEGORY_QUERIES.get(cat)
            if not query:
                return []
            logger.debug("Fetching category %s with query=%r per_cat=%d", cat.value, query, per_cat)
            try:
                cat_items = await self._fetch_everything(query, per_cat)
            except Exception:
                logger.warning("Category %s fetch failed, returning empty", cat.value)
                return []
            for item in cat_items:
                item.category = cat
            logger.debug("Category %s returned %d items", cat.value, len(cat_items))
            return cat_items

        tasks = [asyncio.ensure_future(_fetch_one(cat)) for cat in categories]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[NewsItem] = []
        for r in results:
            if isinstance(r, list):
                items.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Category news parallel fetch exception: %s", r)

        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                unique.append(item)
        return unique[:limit]

    def _get_reddit_subs(self, category_filter: list[NewsCategory] | None = None) -> list[str] | None:
        """Resolve subreddit list from category filter."""
        if not category_filter:
            return None
        subs: list[str] = []
        for cat in category_filter:
            subs.extend(REDDIT_CATEGORY_SUBREDDITS.get(cat, []))
        return subs if subs else None

    async def _fetch_everything(self, query: str, limit: int = 20) -> list[NewsItem]:
        """Fetch articles matching query via NewsAPI /everything endpoint."""
        if not self._newsapi_key:
            logger.warning("NEWSAPI_API_KEY not set, skipping NewsAPI everything")
            return []

        self._check_daily_budget()

        headers: dict[str, str] = {"X-Api-Key": self._newsapi_key}
        params: dict[str, Any] = {
            "q": query,
            "pageSize": min(limit, 100),
            "sortBy": "publishedAt",
            "language": "en",
        }

        max_retries = 3
        base_delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await self._client.get(
                    f"{self._newsapi_base}/everything",
                    params=params,
                    headers=headers,
                )
                self._capture_rate_limits(response)

                if response.status_code == 429:
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            "NewsAPI everything rate limited (429), retry %d/%d in %.1fs",
                            attempt + 1, max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error("NewsAPI everything rate limit exhausted")
                    return []

                if response.status_code == 401:
                    raise NewsAPIAuthError("NewsAPI auth failed: invalid API key")

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", response.text[:200])
                    except Exception:
                        error_msg = response.text[:200]
                    logger.debug("NewsAPI /everything returned HTTP %d for query=%r: %s", response.status_code, query, error_msg)
                    raise NewsAPIError(f"NewsAPI everything HTTP {response.status_code}: {error_msg}")

                try:
                    data = response.json()
                except Exception:
                    logger.warning("NewsAPI everything returned non-JSON, skipping")
                    return []

                articles = data.get("articles", [])
                items: list[NewsItem] = []
                for idx, article in enumerate(articles[:limit]):
                    try:
                        published = article.get("publishedAt", "")
                        published_at = (
                            datetime.fromisoformat(published.replace("Z", "+00:00"))
                            if published
                            else datetime.now(tz=UTC)
                        )
                        items.append(
                            NewsItem(
                                id=f"newsapi-everything-{idx}-{hashlib.md5(query.encode()).hexdigest()[:8]}",
                                title=article.get("title", "") or "",
                                body=article.get("description", "") or "",
                                source=NewsSource.NEWSAPI,
                                url=article.get("url", "") or "",
                                published_at=published_at,
                                ticker_refs=[],
                                category=None,
                                data_freshness="delayed_24h",
                                content_truncated=True,
                            )
                        )
                    except Exception:
                        logger.warning("Skipping malformed everything article at index %d", idx)
                        continue
                return items

            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        if last_exc is not None:
            logger.error("NewsAPI everything request failed: %s", last_exc)
        return []

    # NOTE: X-RateLimit-* headers are NOT documented by NewsAPI (as of 2026).
    # If NewsAPI doesn't send them, this is a no-op — rate limits are still
    # enforced reactively via 429 responses.

    def _capture_rate_limits(self, response: httpx.Response) -> None:
        """Extract rate-limit headers from NewsAPI response."""
        if "X-RateLimit-Limit" in response.headers:
            with contextlib.suppress(ValueError, TypeError):
                self.rate_limit_limit = int(response.headers["X-RateLimit-Limit"])
        if "X-RateLimit-Remaining" in response.headers:
            with contextlib.suppress(ValueError, TypeError):
                self.rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])

    def is_rate_limited(self) -> bool:
        """Check if rate limit has been exhausted."""
        return self.rate_limit_remaining is not None and self.rate_limit_remaining <= 0

    def remaining_requests(self) -> int | None:
        """Return remaining NewsAPI requests, or None if unknown."""
        return self.rate_limit_remaining

    async def get_everything(
        self,
        query: str,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "publishedAt",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search all articles matching query via NewsAPI /everything endpoint.

        Args:
            query: Search query (required by NewsAPI).
            page: Page number (1-indexed).
            page_size: Results per page (max 100).
            sort_by: Sort order — publishedAt, relevancy, popularity.
            **kwargs: Additional query parameters.

        Returns:
            Raw NewsAPI response dict with "articles", "totalResults", etc.

        Raises:
            NewsAPIError: On non-200 responses with API error message.
        """
        if not self._newsapi_key:
            raise NewsAPIError("NEWSAPI_API_KEY not set")

        if self.is_rate_limited():
            raise NewsAPIError("NewsAPI rate limit exhausted")

        self._check_daily_budget()

        headers: dict[str, str] = {"X-Api-Key": self._newsapi_key}
        params: dict[str, Any] = {
            "q": query,
            "pageSize": min(page_size, self._MAX_PAGE_SIZE),
            "page": page,
            "sortBy": sort_by,
            "language": "en",
            **kwargs,
        }

        for attempt in range(4):
            try:
                response = await self._client.get(
                    f"{self._newsapi_base}/everything",
                    params=params,
                    headers=headers,
                )
                self._capture_rate_limits(response)

                if response.status_code == 429:
                    if attempt < 3:
                        delay = 1.0 * (2**attempt)
                        logger.warning("NewsAPI rate limited, retry %d in %.1fs", attempt + 1, delay)
                        await asyncio.sleep(delay)
                        continue
                    raise NewsAPIError("NewsAPI rate limit exhausted after retries")

                if response.status_code == 401:
                    raise NewsAPIAuthError("NewsAPI auth failed: invalid API key")

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", response.text[:200])
                    except Exception:
                        error_msg = response.text[:200]
                    raise NewsAPIError(f"NewsAPI HTTP {response.status_code}: {error_msg}")

                return response.json()

            except httpx.HTTPError as exc:
                if attempt < 3:
                    await asyncio.sleep(1.0 * (2**attempt))
                    continue
                raise NewsAPIError(f"NewsAPI request failed: {exc}") from exc

        raise NewsAPIError("NewsAPI request failed after retries")

    async def _fetch_twitter(self, limit: int) -> list[NewsItem]:
        """Stub — not yet implemented. Requires Twitter/X API v2 credentials.

        TODO: Implement using Twitter API v2 filtered stream or recent search.
        Will require TWITTER_API_KEY, TWITTER_API_SECRET, and TWITTER_BEARER_TOKEN.
        """
        if not self._twitter_api_key:
            logger.debug("TWITTER_API_KEY not set, Twitter source skipped")
            return []
        logger.warning("Twitter API integration not yet implemented despite TWITTER_API_KEY being set")
        return []

    async def _fetch_google_trends(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch trending search terms from Google Trends via pytrends (best-effort, optional)."""
        if category_filter and not (
            NewsCategory.MENTIONS in category_filter or NewsCategory.SOCIAL in category_filter
        ):
            return []

        try:
            from pytrends.request import TrendReq  # noqa: TCH002
        except ImportError:
            logger.info("pytrends not installed, Google Trends source skipped")
            return []

        try:
            loop = asyncio.get_running_loop()
            try:
                pytrends = await asyncio.wait_for(
                    loop.run_in_executor(None, TrendReq, "en-US", 360, 10),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                logger.warning("Google Trends client init timed out, skipping")
                return []

            try:
                trending = await asyncio.wait_for(
                    loop.run_in_executor(None, pytrends.trending_searches, "united_states"),
                    timeout=10,
                )
            except (asyncio.TimeoutError, Exception):
                logger.warning("Google Trends fetch failed (likely blocked), returning empty")
                return []

            terms: list[str] = trending[0].tolist()[:limit] if not trending.empty else []

            results: list[DataPoint] = []
            for term in terms:
                results.append(
                    DataPoint(
                        id=f"gt-{hashlib.md5(term.encode()).hexdigest()[:12]}",
                        source=NewsSource.GOOGLE_TRENDS,
                        category=NewsCategory.MENTIONS,
                        title=f"Trending: {term}",
                        data={"topic": term},
                        timestamp=datetime.now(tz=UTC),
                        ticker_refs=[],
                        metadata={"geo": "US", "source_type": "trending_searches"},
                    )
                )
            return results
        except Exception:
            logger.warning("Google Trends unexpected failure, returning empty")
            return []

    async def _fetch_open_meteo(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch weather forecast data from Open-Meteo for Kalshi-related cities."""
        if category_filter and NewsCategory.WEATHER not in category_filter:
            return []

        wmo_codes: dict[int, str] = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }

        params_template: dict[str, Any] = {
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "temperature_unit": "fahrenheit",
            "timezone": "America/New_York",
        }

        async def _fetch_city(ticker: str, city_label: str, lat: float, lon: float) -> DataPoint | None:
            try:
                params = {**params_template, "latitude": lat, "longitude": lon}
                response = await self._client.get(
                    "https://api.open-meteo.com/v1/forecast", params=params
                )
                if response.status_code != 200:
                    logger.warning(
                        "Open-Meteo returned HTTP %d for %s, skipping",
                        response.status_code, city_label,
                    )
                    return None

                data = response.json()
                current = data.get("current", {})
                daily = data.get("daily", {})

                temp_f = round(current.get("temperature_2m", 0))
                weather_code = current.get("weather_code", 0)
                humidity_pct = round(current.get("relative_humidity_2m", 0))
                wind_mph = round(current.get("wind_speed_10m", 0))
                precip_mm = float(current.get("precipitation", 0.0))
                temp_high_f = round(daily.get("temperature_2m_max", [0])[0])
                temp_low_f = round(daily.get("temperature_2m_min", [0])[0])

                weather_desc = wmo_codes.get(weather_code, "Unknown")

                return DataPoint(
                    id=f"open-meteo-{city_label.lower().replace(' ', '-')}",
                    source=NewsSource.OPEN_METEO,
                    category=NewsCategory.WEATHER,
                    title=f"{city_label}: {temp_f}°F, {weather_desc}, Wind {wind_mph}mph",
                    data={
                        "temp_f": temp_f,
                        "temp_high_f": temp_high_f,
                        "temp_low_f": temp_low_f,
                        "humidity_pct": humidity_pct,
                        "precip_mm": precip_mm,
                        "wind_mph": wind_mph,
                        "weather_code": weather_code,
                        "weather_desc": weather_desc,
                    },
                    timestamp=datetime.now(tz=UTC),
                    ticker_refs=[ticker],
                    metadata={"city": city_label, "lat": lat, "lon": lon},
                )

            except httpx.HTTPError:
                logger.warning("Open-Meteo HTTP error for %s, skipping", city_label)
                return None
            except Exception:
                logger.warning("Open-Meteo unexpected error for %s, skipping", city_label)
                return None

        sem = asyncio.Semaphore(3)  # Open-Meteo free tier rate-limits burst requests

        async def _rate_limited_fetch(
            ticker: str, label: str, lat: float, lon: float,
        ) -> DataPoint | None:
            async with sem:
                return await _fetch_city(ticker, label, lat, lon)

        tasks = [
            asyncio.ensure_future(_rate_limited_fetch(ticker, label, lat, lon))
            for ticker, (label, lat, lon) in self._KALSHI_WEATHER_CITIES.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        points: list[DataPoint] = []
        for r in results:
            if isinstance(r, DataPoint):
                points.append(r)
                if len(points) >= limit:
                    break
            elif isinstance(r, Exception):
                logger.warning("Open-Meteo parallel fetch exception: %s", r)

        return points

    async def _backfill_open_meteo(
        self,
        past_days: int = 92,
    ) -> list[DataPoint]:
        """Fetch historical daily weather data from Open-Meteo.

        Open-Meteo forecast endpoint supports `past_days` up to 92.
        Call multiple times in chunks for deeper history.
        """
        if past_days > 92:
            logger.warning("Open-Meteo past_days max is 92, clamping")
            past_days = 92

        wmo_codes: dict[int, str] = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }

        params_template: dict[str, Any] = {
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "past_days": past_days,
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
        }

        sem = asyncio.Semaphore(3)

        async def _fetch_city_historical(
            ticker: str, city_label: str, lat: float, lon: float,
        ) -> list[DataPoint]:
            async with sem:
                try:
                    params = {**params_template, "latitude": lat, "longitude": lon}
                    response = await self._client.get(
                        "https://api.open-meteo.com/v1/forecast", params=params
                    )
                    if response.status_code != 200:
                        logger.warning(
                            "Open-Meteo hist HTTP %d for %s", response.status_code, city_label,
                        )
                        return []

                    data = response.json()
                    daily = data.get("daily", {})
                    times: list[str] = daily.get("time", [])
                    highs: list[float] = daily.get("temperature_2m_max", [])
                    lows: list[float] = daily.get("temperature_2m_min", [])
                    precip: list[float] = daily.get("precipitation_sum", [])
                    codes: list[int] = daily.get("weather_code", [])
                    if not times:
                        return []

                    points: list[DataPoint] = []
                    for i, day_str in enumerate(times):
                        high_v = highs[i] if i < len(highs) else None
                        low_v = lows[i] if i < len(lows) else None
                        precip_v = precip[i] if i < len(precip) else None
                        wcode = codes[i] if i < len(codes) else None
                        high = round(high_v) if high_v is not None else 0
                        low = round(low_v) if low_v is not None else 0
                        precip_mm = float(precip_v) if precip_v is not None else 0.0
                        wcode_int = int(wcode) if wcode is not None else 0
                        desc = wmo_codes.get(wcode_int, "Unknown")

                        from datetime import datetime, UTC
                        try:
                            ts = datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=UTC)
                        except ValueError:
                            ts = datetime.now(tz=UTC)

                        points.append(DataPoint(
                            id=f"open-meteo-hist-{city_label.lower().replace(' ', '-')}-{day_str}",
                            source=NewsSource.OPEN_METEO,
                            category=NewsCategory.WEATHER,
                            title=f"{city_label}: {day_str} High {high}°F Low {low}°F, {desc}",
                            data={
                                "temp_high_f": high,
                                "temp_low_f": low,
                                "precip_mm": precip_mm,
                                "weather_code": wcode,
                                "weather_desc": desc,
                            },
                            timestamp=ts,
                            ticker_refs=[ticker],
                            metadata={"city": city_label, "lat": str(lat), "lon": str(lon)},
                        ))

                    return points

                except Exception:
                    import traceback
                    logger.warning("Open-Meteo hist error for %s:\n%s", city_label, traceback.format_exc())
                    return []

        all_points: list[DataPoint] = []
        tasks = [
            asyncio.ensure_future(_fetch_city_historical(ticker, label, lat, lon))
            for ticker, (label, lat, lon) in self._KALSHI_WEATHER_CITIES.items()
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for result in gathered:
            if isinstance(result, list):
                all_points.extend(result)
            elif isinstance(result, BaseException):
                logger.warning("Open-Meteo backfill gather exception: %s", result)

        return all_points

    async def _backfill_fred(
        self,
        observation_start: str,
    ) -> list[DataPoint]:
        """Fetch historical FRED observations for all series since a date."""
        import httpx

        key = resolve_fred_key(None)
        if key is None:
            logger.warning("FRED API key not available, skipping FRED backfill")
            return []

        allowed_categories: set[str] = {"ECONOMICS", "FINANCIALS"}
        filtered_series = {
            sid: info
            for sid, info in self._FRED_SERIES.items()
            if info["category"] in allowed_categories
        }

        sem = asyncio.Semaphore(5)

        async def _fetch_series_range(
            sid: str, info: dict[str, str],
        ) -> list[DataPoint]:
            async with sem:
                try:
                    response = await self._client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={
                            "series_id": sid,
                            "api_key": key,
                            "file_type": "json",
                            "observation_start": observation_start,
                            "sort_order": "asc",
                            "limit": 500,
                        },
                    )
                    if response.status_code != 200:
                        logger.warning("FRED hist series %s HTTP %d", sid, response.status_code)
                        return []

                    data = response.json()
                    observations = data.get("observations", [])
                    if not observations:
                        return []

                    series_desc = info.get("name", sid)
                    category = info.get("category", "ECONOMICS")

                    from datetime import datetime, UTC
                    points: list[DataPoint] = []
                    for obs in observations:
                        date_str = obs.get("date", "")
                        value = obs.get("value", ".")
                        if value == ".":
                            continue  # FRED uses "." for missing values
                        try:
                            ts = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                        except ValueError:
                            continue

                        points.append(DataPoint(
                            id=f"fred-hist-{sid}-{date_str}",
                            source=NewsSource.FRED,
                            category=NewsCategory(category.lower()) if category.lower() in {e.value for e in NewsCategory} else NewsCategory.ECONOMICS,
                            title=f"{series_desc}: {value} ({date_str})",
                            data={"value": value, "series_id": sid},
                            timestamp=ts,
                            ticker_refs=[sid],
                            metadata={"series": series_desc, "units": info.get("units", ""), "frequency": info.get("frequency", "")},
                        ))

                    logger.info("FRED backfill: %s — %d observations", series_desc, len(points))
                    return points

                except httpx.HTTPError:
                    logger.warning("FRED hist HTTP error for %s", sid)
                    return []
                except Exception:
                    logger.warning("FRED hist error for %s", sid)
                    return []

        all_points: list[DataPoint] = []
        tasks = [
            asyncio.ensure_future(_fetch_series_range(sid, info))
            for sid, info in filtered_series.items()
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for result in gathered:
            if isinstance(result, list):
                all_points.extend(result)
            elif isinstance(result, BaseException):
                logger.warning("FRED backfill gather exception: %s", result)

        return all_points

    async def _fetch_openweathermap(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch current weather from OpenWeatherMap for Kalshi-related cities."""
        if category_filter and NewsCategory.WEATHER not in category_filter:
            return []

        key = resolve_openweather_key(None)
        if key is None:
            logger.warning("OpenWeatherMap key not set, skipping")
            return []

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if today != self._owm_budget_date:
            self._owm_budget_date = today
            self._owm_daily_count = 0
        if self._owm_daily_count >= 900:
            logger.warning("OpenWeatherMap daily budget exhausted (%d calls today), skipping", self._owm_daily_count)
            return []

        self._owm_daily_count += 1

        # Try /group batch endpoint first; if unavailable, fall back to parallel /weather calls
        entries: list[dict[str, Any]] | None = None
        try:
            city_ids = [str(cid) for cid in self._OWM_CITY_IDS.values()]
            response = await self._client.get(
                "https://api.openweathermap.org/data/2.5/group",
                params={"id": ",".join(city_ids), "appid": key, "units": "imperial"},
            )
            if response.status_code == 200:
                data = response.json()
                entries = data.get("list", [])
            else:
                logger.warning("OWM /group HTTP %d — falling back to individual calls", response.status_code)
        except Exception:
            logger.warning("OWM /group failed — falling back to individual calls", exc_info=True)

        if entries is None:
            return await self._fetch_openweathermap_fallback(key, limit)

        coord_to_ticker: dict[tuple[float, float], str] = {}
        for ticker, (name, lat, lon) in self._KALSHI_WEATHER_CITIES.items():
            coord_to_ticker[(round(lat, 2), round(lon, 2))] = ticker

        points: list[DataPoint] = []
        for entry in entries:
            if len(points) >= limit:
                break
            try:
                lat = entry.get("coord", {}).get("lat")
                lon = entry.get("coord", {}).get("lon")
                match_key = (round(float(lat), 2), round(float(lon), 2)) if lat is not None and lon is not None else None
                ticker = coord_to_ticker.get(match_key) if match_key else None
                city_name = entry.get("name", "Unknown")
                main = entry.get("main", {})
                wind = entry.get("wind", {})
                weather_list = entry.get("weather", [{}])

                temp_f = int(main.get("temp", 0))
                temp_min_f = int(main.get("temp_min", 0))
                temp_max_f = int(main.get("temp_max", 0))
                humidity_pct = int(main.get("humidity", 0))
                wind_mph = int(wind.get("speed", 0))
                weather_code = int(weather_list[0].get("id", 0))
                weather_desc = str(weather_list[0].get("description", "Unknown"))

                points.append(
                    DataPoint(
                        id=f"owm-{city_name.lower().replace(' ', '-')}",
                        source=NewsSource.OPENWEATHERMAP,
                        category=NewsCategory.WEATHER,
                        title=f"{city_name}: {temp_f}°F, {weather_desc}, Wind {wind_mph}mph",
                        data={
                            "temp_f": temp_f,
                            "temp_min_f": temp_min_f,
                            "temp_max_f": temp_max_f,
                            "humidity_pct": humidity_pct,
                            "wind_mph": wind_mph,
                            "weather_code": weather_code,
                            "description": weather_desc,
                        },
                        timestamp=datetime.now(tz=UTC),
                        ticker_refs=[ticker] if ticker else [],
                        metadata={"city": city_name, "lat": lat, "lon": lon},
                    )
                )
            except Exception:
                logger.warning("Skipping malformed OWM /group entry for %s", entry.get("name", "?"))
                continue

        return points

    async def _fetch_openweathermap_fallback(
        self,
        key: str,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fallback: 15 parallel /weather calls when /group is unavailable."""
        async def _fetch_city(ticker: str, city_name: str, lat: float, lon: float) -> DataPoint | None:
            if self._owm_daily_count >= 900:
                return None
            try:
                response = await self._client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": city_name, "appid": key, "units": "imperial"},
                )
                self._owm_daily_count += 1
                if response.status_code != 200:
                    logger.warning("OWM HTTP %d for %s", response.status_code, city_name)
                    return None
                data = response.json()
                main = data.get("main", {})
                wind = data.get("wind", {})
                weather_list = data.get("weather", [{}])
                return DataPoint(
                    id=f"owm-{city_name.lower().replace(' ', '-')}",
                    source=NewsSource.OPENWEATHERMAP,
                    category=NewsCategory.WEATHER,
                    title=f"{city_name}: {int(main.get('temp', 0))}°F, {weather_list[0].get('description', 'Unknown')}, Wind {int(wind.get('speed', 0))}mph",
                    data={
                        "temp_f": int(main.get("temp", 0)),
                        "temp_min_f": int(main.get("temp_min", 0)),
                        "temp_max_f": int(main.get("temp_max", 0)),
                        "humidity_pct": int(main.get("humidity", 0)),
                        "wind_mph": int(wind.get("speed", 0)),
                        "weather_code": int(weather_list[0].get("id", 0)),
                        "description": str(weather_list[0].get("description", "Unknown")),
                    },
                    timestamp=datetime.now(tz=UTC),
                    ticker_refs=[ticker],
                    metadata={"city": city_name, "lat": lat, "lon": lon},
                )
            except httpx.HTTPError:
                logger.warning("OWM HTTP error for %s", city_name)
                return None
            except Exception:
                logger.warning("OWM unexpected error for %s", city_name)
                return None

        tasks = [
            asyncio.ensure_future(_fetch_city(ticker, name, lat, lon))
            for ticker, (name, lat, lon) in self._KALSHI_WEATHER_CITIES.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        points: list[DataPoint] = []
        for r in results:
            if isinstance(r, DataPoint):
                points.append(r)
                if len(points) >= limit:
                    break
            elif isinstance(r, Exception):
                logger.warning("OWM parallel fetch exception: %s", r)
        return points

    async def _fetch_reddit(self, limit: int, subreddits: list[str] | None = None, category_filter: list[NewsCategory] | None = None) -> list[NewsItem]:
        """Fetch recent posts from configured subreddits via RSS."""
        single_category: NewsCategory | None = None
        if category_filter and len(category_filter) == 1:
            single_category = category_filter[0]

        async def _fetch_sub(sub: str) -> list[NewsItem]:
            try:
                feed_url = f"https://www.reddit.com/r/{sub}/.rss"
                response = await self._client.get(
                    feed_url, headers={"User-Agent": "TraderBot/1.0 (news aggregation)"}
                )
                if response.status_code != 200:
                    logger.warning(
                        "Reddit RSS for r/%s returned HTTP %d, skipping",
                        sub, response.status_code,
                    )
                    return []

                parsed = feedparser.parse(response.text)
                sub_items: list[NewsItem] = []
                for idx, entry in enumerate(parsed.entries[:limit]):
                    try:
                        published_at = datetime.now(tz=UTC)
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            from time import mktime

                            published_at = datetime.fromtimestamp(
                                mktime(entry.published_parsed), tz=UTC
                            )

                        entry_link = entry.get("link", "") or ""
                        entry_hash = hashlib.md5(entry_link.encode()).hexdigest()[:12] if entry_link else str(idx)

                        sub_items.append(
                            NewsItem(
                                id=f"reddit-{sub}-{entry_hash}",
                                title=entry.get("title", "") or "",
                                body=entry.get("summary", "") or "",
                                source=NewsSource.REDDIT,
                                url=entry_link,
                                published_at=published_at,
                                ticker_refs=[],
                                category=single_category,
                                data_freshness="realtime",
                            )
                        )
                    except Exception:
                        logger.warning(
                            "Skipping malformed Reddit entry at r/%s index %d", sub, idx
                        )
                        continue
                return sub_items
            except Exception:
                logger.exception("Reddit RSS for r/%s failed, returning empty", sub)
                return []

        subs = subreddits or self._reddit_subreddits
        tasks = [asyncio.ensure_future(_fetch_sub(sub)) for sub in subs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[NewsItem] = []
        for r in results:
            if isinstance(r, list):
                items.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Reddit parallel fetch exception: %s", r)

        return items[:limit]

    async def _fetch_coingecko(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch crypto market data from CoinGecko /coins/markets.

        Uses x-cg-demo-api-key header when COINGECKO_API_KEY is set for
        higher rate limits. Falls back to unauthenticated (free tier) otherwise.
        Returns DataPoint objects with prices/market caps in integer cents.
        If MENTIONS is in category_filter, also fetches /search/trending.
        """
        if category_filter is not None and NewsCategory.CRYPTO not in category_filter and NewsCategory.MENTIONS not in category_filter:
            return []

        from traderbot.auth import get_credential
        coingecko_key = get_credential("coingecko", "api_key")
        headers: dict[str, str] = {}
        if coingecko_key is not None:
            headers["x-cg-demo-api-key"] = coingecko_key.get_secret_value()

        results: list[DataPoint] = []

        try:
            params: dict[str, Any] = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": min(limit, 50),
                "page": 1,
                "sparkline": "false",
            }

            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = await self._client.get(
                        "https://api.coingecko.com/api/v3/coins/markets",
                        params=params,
                        headers=headers,
                    )

                    if response.status_code == 429:
                        if attempt < max_retries:
                            delay = 2 * (2**attempt)
                            logger.warning(
                                "CoinGecko rate limited (429), retry %d/%d in %ds",
                                attempt + 1,
                                max_retries,
                                delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        logger.error("CoinGecko rate limit exhausted after %d retries", max_retries)
                        return []

                    if response.status_code != 200:
                        logger.warning(
                            "CoinGecko /coins/markets returned HTTP %d, skipping",
                            response.status_code,
                        )
                        return []

                    break

                except httpx.HTTPError as exc:
                    if attempt < max_retries:
                        await asyncio.sleep(2 * (2**attempt))
                        continue
                    logger.error("CoinGecko request failed: %s", exc)
                    return []

            try:
                coins = response.json()
            except Exception:
                logger.warning("CoinGecko returned non-JSON response, skipping")
                return []

            for idx, coin in enumerate(coins[:limit]):
                try:
                    coin_id = coin.get("id", "")
                    symbol = coin.get("symbol", "")
                    name = coin.get("name", "")
                    current_price = coin.get("current_price") or 0
                    market_cap = coin.get("market_cap") or 0
                    total_volume = coin.get("total_volume") or 0
                    price_change_pct = coin.get("price_change_percentage_24h") or 0
                    last_updated = coin.get("last_updated", "")

                    price_cents = int(round(float(current_price) * 100))
                    market_cap_cents = int(round(float(market_cap) * 100))
                    volume_24h_cents = int(round(float(total_volume) * 100))
                    change_24h_pct = round(float(price_change_pct), 2)

                    sign = "+" if change_24h_pct >= 0 else ""
                    title = f"{symbol.upper()}: ${float(current_price):,.2f} ({sign}{change_24h_pct}% 24h)"

                    timestamp = (
                        datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                        if last_updated
                        else datetime.now(tz=UTC)
                    )

                    results.append(
                        DataPoint(
                            id=f"coingecko-{coin_id}",
                            source=NewsSource.COINGECKO,
                            category=NewsCategory.CRYPTO,
                            title=title,
                            data={
                                "price_cents": price_cents,
                                "market_cap_cents": market_cap_cents,
                                "volume_24h_cents": volume_24h_cents,
                                "change_24h_pct": change_24h_pct,
                                "rank": idx + 1,
                            },
                            timestamp=timestamp,
                            ticker_refs=[symbol.upper()],
                            metadata={"name": name, "coin_id": coin_id},
                        )
                    )
                except (ValueError, KeyError, TypeError):
                    logger.warning("Skipping malformed CoinGecko coin at index %d", idx)
                    continue

        except (httpx.HTTPError, ValueError):
            logger.warning("CoinGecko fetch failed, returning partial results")
            return results

        # Fetch trending coins if MENTIONS in filter
        if category_filter is not None and NewsCategory.MENTIONS in category_filter:
            try:
                for attempt in range(max_retries + 1):
                    try:
                        trending_resp = await self._client.get(
                            "https://api.coingecko.com/api/v3/search/trending",
                            headers=headers,
                        )
                        if trending_resp.status_code == 429:
                            if attempt < max_retries:
                                await asyncio.sleep(2 * (2**attempt))
                                continue
                            logger.error("CoinGecko trending rate limit exhausted")
                            break
                        if trending_resp.status_code != 200:
                            logger.warning(
                                "CoinGecko /search/trending returned HTTP %d, skipping",
                                trending_resp.status_code,
                            )
                            break
                        break
                    except httpx.HTTPError:
                        if attempt < max_retries:
                            await asyncio.sleep(2 * (2**attempt))
                            continue
                        break

                try:
                    trending_data = trending_resp.json()
                except Exception:
                    logger.warning("CoinGecko trending returned non-JSON, skipping")
                    trending_data = {}

                for idx, item in enumerate(trending_data.get("coins", [])):
                    try:
                        coin_item = item.get("item", item)
                        coin_id = coin_item.get("id", "")
                        symbol = coin_item.get("symbol", "")
                        name = coin_item.get("name", "")
                        market_cap_rank = int(coin_item.get("market_cap_rank") or 0)
                        score = int(coin_item.get("score") if coin_item.get("score") is not None else idx)

                        results.append(
                            DataPoint(
                                id=f"coingecko-trending-{coin_id}",
                                source=NewsSource.COINGECKO,
                                category=NewsCategory.MENTIONS,
                                title=f"Trending: {symbol.upper()} ({name}) — rank #{market_cap_rank}",
                                data={
                                    "market_cap_rank": market_cap_rank,
                                    "trending_score": score,
                                },
                                timestamp=datetime.now(tz=UTC),
                                ticker_refs=[symbol.upper()],
                                metadata={"name": name, "coin_id": coin_id, "trending": True},
                            )
                        )
                    except (ValueError, KeyError, TypeError):
                        logger.warning("Skipping malformed trending coin at index %d", idx)
                        continue

            except (httpx.HTTPError, ValueError):
                logger.warning("CoinGecko trending fetch failed, skipping")

        return results

    async def _fetch_thesportsdb(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch today's sports events from TheSportsDB free API."""
        if category_filter is not None and NewsCategory.SPORTS not in category_filter:
            return []

        today = datetime.now(tz=UTC).date().isoformat()

        async def _fetch_sport(sport: str) -> list[DataPoint]:
            try:
                response = await self._client.get(
                    "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
                    params={"d": today, "s": sport},
                )
                if response.status_code != 200:
                    logger.warning(
                        "TheSportsDB %s returned HTTP %d, skipping",
                        sport, response.status_code,
                    )
                    return []

                data = response.json()
                events = data.get("events")
                if not events:
                    return []

                sport_points: list[DataPoint] = []
                for event in events:
                    if len(sport_points) >= limit:
                        break
                    try:
                        event_id = event.get("idEvent", "")
                        title = event.get("strEvent") or (
                            f"{event.get('strHomeTeam', '')} vs {event.get('strAwayTeam', '')}"
                        )
                        league = event.get("strLeague", "")
                        home_team = event.get("strHomeTeam", "")
                        away_team = event.get("strAwayTeam", "")
                        date_str = event.get("dateEvent", "")
                        time_str = event.get("strTime", "00:00:00")

                        if date_str:
                            timestamp = datetime.fromisoformat(
                                f"{date_str}T{time_str}+00:00"
                            )
                        else:
                            timestamp = datetime.now(tz=UTC)

                        sport_points.append(
                            DataPoint(
                                id=f"thesportsdb-{event_id}",
                                source=NewsSource.THESPORTSDB,
                                category=NewsCategory.SPORTS,
                                title=f"{title} — {league}",
                                data={
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "home_score": event.get("intHomeScore"),
                                    "away_score": event.get("intAwayScore"),
                                    "league": league,
                                    "sport": sport,
                                },
                                timestamp=timestamp,
                                ticker_refs=[home_team, away_team],
                                metadata={
                                    "event_id": event_id,
                                    "thumb": event.get("strThumb"),
                                },
                            )
                        )
                    except Exception:
                        logger.warning(
                            "Skipping malformed TheSportsDB event %s",
                            event.get("idEvent", "?"),
                        )
                        continue
                return sport_points
            except Exception:
                logger.exception("TheSportsDB %s query failed, returning empty", sport)
                return []

        tasks = [asyncio.ensure_future(_fetch_sport(sport)) for sport in self._THESPORTSDB_SPORTS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        points: list[DataPoint] = []
        for r in results:
            if isinstance(r, list):
                points.extend(r)
                if len(points) >= limit:
                    break
            elif isinstance(r, Exception):
                logger.warning("TheSportsDB parallel fetch exception: %s", r)

        return points[:limit]

    async def _backfill_thesportsdb(
        self,
        start_date: str,
        end_date: str | None = None,
    ) -> list[DataPoint]:
        """Fetch historical sports events from TheSportsDB.

        Iterates day by day through the date range for each tracked sport.
        Free tier returns current season data only.
        """
        from datetime import datetime, timedelta, UTC, date

        end = (datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else datetime.now(tz=UTC).date())
        start = datetime.strptime(start_date, "%Y-%m-%d").date()

        sem = asyncio.Semaphore(3)
        all_points: list[DataPoint] = []
        current = start

        while current <= end:
            day_str = current.isoformat()

            async def _fetch_day(sport: str) -> list[DataPoint]:
                async with sem:
                    try:
                        response = await self._client.get(
                            "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
                            params={"d": day_str, "s": sport},
                        )
                        if response.status_code != 200:
                            return []
                        data = response.json()
                        events = data.get("events")
                        if not events:
                            return []
                        sport_points: list[DataPoint] = []
                        for event in events:
                            try:
                                event_id = event.get("idEvent", "")
                                title = event.get("strEvent") or (
                                    f"{event.get('strHomeTeam', '')} vs {event.get('strAwayTeam', '')}"
                                )
                                league = event.get("strLeague", "")
                                home_team = event.get("strHomeTeam", "")
                                away_team = event.get("strAwayTeam", "")
                                event_date = event.get("dateEvent", day_str)
                                time_str = event.get("strTime", "00:00:00")
                                timestamp = datetime.fromisoformat(f"{event_date}T{time_str}+00:00")

                                sport_points.append(
                                    DataPoint(
                                        id=f"thesportsdb-hist-{event_id}",
                                        source=NewsSource.THESPORTSDB,
                                        category=NewsCategory.SPORTS,
                                        title=f"{title} — {league}",
                                        data={
                                            "home_team": home_team,
                                            "away_team": away_team,
                                            "home_score": event.get("intHomeScore"),
                                            "away_score": event.get("intAwayScore"),
                                            "league": league,
                                            "sport": sport,
                                        },
                                        timestamp=timestamp,
                                        ticker_refs=[home_team, away_team],
                                        metadata={"event_id": event_id},
                                    )
                                )
                            except Exception:
                                continue
                        return sport_points
                    except Exception:
                        return []

            tasks = [asyncio.ensure_future(_fetch_day(sport)) for sport in self._THESPORTSDB_SPORTS]
            day_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in day_results:
                if isinstance(r, list):
                    all_points.extend(r)

            current += timedelta(days=1)

        return all_points

    async def _backfill_coingecko(
        self,
        from_timestamp: int,
        to_timestamp: int | None = None,
    ) -> list[DataPoint]:
        """Fetch historical crypto prices from CoinGecko market_chart/range."""
        import time as _time

        end_ts = to_timestamp or int(_time.time())

        headers: dict[str, str] = {}
        from traderbot.auth import get_credential
        cg_key = get_credential("coingecko", "api_key")
        if cg_key is not None:
            headers["x-cg-demo-api-key"] = cg_key.get_secret_value()

        try:
            response = await self._client.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 30, "page": 1, "sparkline": "false"},
                headers=headers,
            )
            if response.status_code != 200:
                logger.warning("CoinGecko /coins/markets returned HTTP %d, cannot backfill", response.status_code)
                return []
            coins = response.json()
        except Exception as exc:
            logger.warning("CoinGecko top coins fetch failed: %s", exc)
            return []

        coin_ids = [(c.get("id", ""), c.get("symbol", "").upper()) for c in coins if c.get("id")]
        logger.info("CoinGecko backfill: %d coins from %s to %s", len(coin_ids), from_timestamp, end_ts)

        sem = asyncio.Semaphore(3)

        async def _fetch_coin_history(coin_id: str, symbol: str) -> list[DataPoint]:
            async with sem:
                try:
                    response = await self._client.get(
                        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range",
                        params={"vs_currency": "usd", "from": str(from_timestamp), "to": str(end_ts)},
                        headers=headers,
                    )
                    if response.status_code == 429:
                        logger.warning("CoinGecko rate limited on %s, skipping", coin_id)
                        return []
                    if response.status_code != 200:
                        return []
                    data = response.json()
                    prices = data.get("prices", [])
                    if not prices:
                        return []
                    points: list[DataPoint] = []
                    for entry in prices:
                        ts_ms, price = entry
                        ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
                        price_cents = int(round(float(price) * 100))
                        points.append(
                            DataPoint(
                                id=f"coingecko-hist-{coin_id}-{ts.strftime('%Y%m%d')}",
                                source=NewsSource.COINGECKO,
                                category=NewsCategory.CRYPTO,
                                title=f"{symbol}: ${float(price):,.2f} ({ts.strftime('%Y-%m-%d')})",
                                data={"price_cents": price_cents, "symbol": symbol},
                                timestamp=ts,
                                ticker_refs=[symbol],
                                metadata={"coin_id": coin_id},
                            )
                        )
                    return points
                except Exception:
                    logger.warning("CoinGecko hist error for %s", coin_id)
                    return []

        all_points: list[DataPoint] = []
        tasks = [asyncio.ensure_future(_fetch_coin_history(cid, sym)) for cid, sym in coin_ids]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for result in gathered:
            if isinstance(result, list):
                all_points.extend(result)
            elif isinstance(result, BaseException):
                logger.warning("CoinGecko backfill gather exception: %s", result)

        return all_points

    async def _backfill_newsapi(
        self,
        from_date: str,
        to_date: str | None = None,
    ) -> list[NewsItem]:
        """Fetch historical news from NewsAPI /v2/everything.

        Limited to 30-day lookback on free tier. Category-based queries
        for broad coverage. Each query returns up to 100 articles.
        """
        if not self._newsapi_key:
            logger.warning("NEWSAPI_API_KEY not set, skipping NewsAPI backfill")
            return []

        end_date = to_date or datetime.now(tz=UTC).strftime("%Y-%m-%d")
        headers: dict[str, str] = {"X-Api-Key": self._newsapi_key}

        categories = [
            ("business", NewsCategory.ECONOMICS),
            ("politics", NewsCategory.POLITICS),
            ("technology", NewsCategory.SCIENCE_AND_TECHNOLOGY),
            ("science", NewsCategory.SCIENCE_AND_TECHNOLOGY),
            ("health", NewsCategory.HEALTH),
            ("sports", NewsCategory.SPORTS),
            ("entertainment", NewsCategory.ENTERTAINMENT),
        ]

        sem = asyncio.Semaphore(3)

        async def _fetch_category(cat_name: str, news_cat: NewsCategory) -> list[NewsItem]:
            async with sem:
                try:
                    response = await self._client.get(
                        f"{self._newsapi_base}/everything",
                        params={
                            "q": cat_name,
                            "from": from_date,
                            "to": end_date,
                            "language": "en",
                            "sortBy": "publishedAt",
                            "pageSize": 100,
                        },
                        headers=headers,
                    )
                    self._capture_rate_limits(response)
                    if response.status_code != 200:
                        return []
                    data = response.json()
                    articles = data.get("articles", [])
                    if not articles:
                        return []
                    items: list[NewsItem] = []
                    for art in articles:
                        try:
                            title = art.get("title") or ""
                            description = art.get("description") or ""
                            url = art.get("url", "") or ""
                            published = art.get("publishedAt", "")
                            content = art.get("content") or description
                            source_name = art.get("source", {}).get("name", "newsapi")
                            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else datetime.now(tz=UTC)
                            items.append(NewsItem(
                                id=hashlib.sha256(url.encode()).hexdigest(),
                                source=NewsSource.NEWSAPI,
                                title=title,
                                body=content[:5000] if content else title,
                                url=url,
                                published_at=timestamp,
                                category=news_cat,
                                ticker_refs=[],
                                data_freshness="unknown",
                                content_truncated=len(content or "") > 5000,
                            ))
                        except Exception:
                            continue
                    return items
                except Exception:
                    return []

        all_items: list[NewsItem] = []
        tasks = [asyncio.ensure_future(_fetch_category(cn, nc)) for cn, nc in categories]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for result in gathered:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, BaseException):
                logger.warning("NewsAPI backfill gather exception: %s", result)

        return all_items

    async def _fetch_fred(
        self,
        category_filter: list[NewsCategory] | None = None,
        limit: int = 20,
    ) -> list[DataPoint]:
        """Fetch latest economic observations from FRED API.

        Returns DataPoint objects with series values as strings (no float conversion).
        Requires FRED_API_KEY resolved via profile-aware fallback chain.
        """
        if category_filter is not None:
            if (
                NewsCategory.ECONOMICS not in category_filter
                and NewsCategory.FINANCIALS not in category_filter
            ):
                return []

        key = resolve_fred_key(None)
        if key is None:
            logger.warning("FRED API key not available, skipping FRED fetch")
            return []

        allowed_categories: set[str] = set()
        if category_filter is None:
            allowed_categories = {"ECONOMICS", "FINANCIALS"}
        else:
            if NewsCategory.ECONOMICS in category_filter:
                allowed_categories.add("ECONOMICS")
            if NewsCategory.FINANCIALS in category_filter:
                allowed_categories.add("FINANCIALS")

        filtered_series = {
            sid: info
            for sid, info in self._FRED_SERIES.items()
            if info["category"] in allowed_categories
        }

        async def _fetch_series(sid: str, info: dict[str, str]) -> DataPoint | None:
            try:
                response = await self._client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": sid,
                        "api_key": key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "FRED series %s returned HTTP %d, skipping",
                        sid, response.status_code,
                    )
                    return None

                data = response.json()
                observations = data.get("observations", [])
                if not observations:
                    logger.warning("FRED series %s has no observations, skipping", sid)
                    return None

                obs = observations[0]
                date = obs.get("date", "")
                value = obs.get("value", ".")

                series_name = info["name"]
                units = info["units"]
                series_category = info["category"]

                if date:
                    try:
                        timestamp = datetime.fromisoformat(date + "T00:00:00+00:00")
                    except ValueError:
                        timestamp = datetime.now(tz=UTC)
                else:
                    timestamp = datetime.now(tz=UTC)

                category = (
                    NewsCategory.ECONOMICS
                    if series_category == "ECONOMICS"
                    else NewsCategory.FINANCIALS
                )

                freq = "daily" if sid in ("DFF", "T10Y2Y") else "monthly"

                return DataPoint(
                    id=f"fred-{sid.lower()}",
                    source=NewsSource.FRED,
                    category=category,
                    title=f"{series_name}: {value} ({date})",
                    data={
                        "series_id": sid,
                        "value": value,
                        "date": date,
                        "units": units,
                    },
                    timestamp=timestamp,
                    ticker_refs=[],
                    metadata={
                        "series_name": series_name,
                        "freq": freq,
                    },
                )
            except Exception:
                logger.warning("FRED series %s fetch failed, skipping", sid, exc_info=True)
                return None

        tasks = [
            asyncio.ensure_future(_fetch_series(sid, info))
            for sid, info in filtered_series.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        points: list[DataPoint] = []
        for r in results:
            if isinstance(r, DataPoint):
                points.append(r)
                if len(points) >= limit:
                    break
            elif isinstance(r, Exception):
                logger.warning("FRED parallel fetch exception: %s", r)

        return points

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> NewsAggregator:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
