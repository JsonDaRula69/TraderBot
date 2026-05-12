"""Unified news source aggregator — NewsAPI, Reddit RSS, Twitter/X stub."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import random
from datetime import UTC, datetime
from typing import Any, ClassVar

import feedparser
import httpx

from traderbot.news.models import NewsCategory, NewsItem, NewsSource

logger = logging.getLogger(__name__)

NEWSAPI_CATEGORY_QUERIES: dict[NewsCategory, str] = {
    NewsCategory.ECONOMICS: "economy GDP inflation federal reserve interest rates",
    NewsCategory.POLITICS: "politics election congress president legislation",
    NewsCategory.WEATHER: "weather hurricane tornado flood temperature forecast storm",
    NewsCategory.SPORTS: "sports NFL NBA MLB NHL soccer championship",
    NewsCategory.SCIENCE_AND_TECHNOLOGY: "technology science AI software space research",
    NewsCategory.CRYPTO: "cryptocurrency bitcoin ethereum crypto blockchain",
    NewsCategory.COMMODITIES: "commodities oil gold copper wheat futures",
    NewsCategory.COMPANIES: "company earnings stocks IPO merger acquisition",
    NewsCategory.ELECTIONS: "election vote polling primary ballot campaign",
    NewsCategory.ENTERTAINMENT: "entertainment movie music Oscar Grammy box office",
    NewsCategory.FINANCIALS: "financial banking markets stocks trading NASDAQ S&P",
    NewsCategory.HEALTH: "health mental health wellness psychology therapy",
    NewsCategory.SOCIAL: "social community trending viral breaking news",
    NewsCategory.MENTIONS: "trending viral celebrity mention",
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


class NewsAggregator:
    """Fetch and aggregate news from multiple sources with graceful degradation."""

    _MAX_PAGE_SIZE: ClassVar[int] = 100

    # Source fetch priority order (fastest/breaking → slowest/analysis)
    _SOURCE_PRIORITY: ClassVar[list[NewsSource]] = [
        NewsSource.NEWSAPI,
        NewsSource.REDDIT,
    ]

    def __init__(
        self,
        newsapi_key: str | None = None,
        twitter_api_key: str | None = None,
        reddit_subreddits: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        daily_budget: int | None = None,
    ) -> None:
        self._newsapi_key = newsapi_key
        self._twitter_api_key = twitter_api_key
        self._reddit_subreddits = reddit_subreddits or [
            "politics",
            "economics",
            "weather",
        ]
        self._client = http_client or httpx.AsyncClient()
        self._newsapi_base = "https://newsapi.org/v2"
        self.rate_limit_limit: int | None = None
        self.rate_limit_remaining: int | None = None
        self._daily_budget: int = daily_budget or int(os.environ.get("NEWSAPI_DAILY_BUDGET", "100"))
        self._daily_request_count: int = 0
        self._budget_reset_date: str = ""

    def _check_daily_budget(self) -> None:
        """Enforce client-side daily request budget, resetting at midnight UTC."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if today != self._budget_reset_date:
            self._budget_reset_date = today
            self._daily_request_count = 0
        if self._daily_request_count >= self._daily_budget:
            raise NewsAPIBudgetExceeded(
                f"Daily budget exhausted ({self._daily_request_count} requests today)"
            )
        self._daily_request_count += 1

    async def fetch_recent(self, source: NewsSource, limit: int = 20, query: str | None = None, category_filter: list[NewsCategory] | None = None) -> list[NewsItem]:
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
                    return await self._fetch_reddit(limit, subreddits=subs)
        except Exception:
            logger.exception("Source %s failed, returning empty", source.value)
            return []
        return []

    async def fetch_all(self, limit: int = 20, category_filter: list[NewsCategory] | None = None) -> list[NewsItem]:
        """Aggregate from all sources in priority order."""
        items: list[NewsItem] = []
        per_source = max(limit, 20)
        for source in self._SOURCE_PRIORITY:
            source_items = await self.fetch_recent(source, limit=per_source, category_filter=category_filter)
            items.extend(source_items)
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
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

        items: list[NewsItem] = []
        per_cat = max(limit // len(categories), 5)
        for cat in categories:
            query = NEWSAPI_CATEGORY_QUERIES.get(cat)
            if not query:
                continue
            cat_items = await self._fetch_everything(query, per_cat)
            items.extend(cat_items)

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

    async def _fetch_reddit(self, limit: int, subreddits: list[str] | None = None) -> list[NewsItem]:
        """Fetch recent posts from configured subreddits via RSS."""
        items: list[NewsItem] = []

        for sub in subreddits or self._reddit_subreddits:
            try:
                feed_url = f"https://www.reddit.com/r/{sub}/.rss"
                response = await self._client.get(feed_url)

                if response.status_code != 200:
                    logger.warning(
                        "Reddit RSS for r/%s returned HTTP %d, skipping",
                        sub,
                        response.status_code,
                    )
                    continue

                parsed = feedparser.parse(response.text)

                for idx, entry in enumerate(parsed.entries[:limit]):
                    try:
                        published_at = datetime.now(tz=UTC)
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            from time import mktime

                            published_at = datetime.fromtimestamp(
                                mktime(entry.published_parsed), tz=UTC
                            )

                        items.append(
                            NewsItem(
                                id=f"reddit-{sub}-{idx}",
                                title=entry.get("title", "") or "",
                                body=entry.get("summary", "") or "",
                                source=NewsSource.REDDIT,
                                url=entry.get("link", "") or "",
                                published_at=published_at,
                                ticker_refs=[],
                                category=None,
                                data_freshness="realtime",
                            )
                        )
                    except Exception:
                        logger.warning(
                            "Skipping malformed Reddit entry at r/%s index %d", sub, idx
                        )
                        continue

            except Exception:
                logger.exception("Reddit RSS for r/%s failed, continuing", sub)
                continue

        return items[:limit]

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
