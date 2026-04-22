"""Unified news source aggregator — NewsAPI, Reddit RSS, Twitter/X stub."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

import feedparser  # noqa: TCH002

logger = logging.getLogger(__name__)


class NewsSource(StrEnum):
    """Supported news source identifiers."""

    NEWSAPI = "newsapi"
    TWITTER = "twitter"
    REDDIT = "reddit"


class NewsItem(BaseModel):
    """Canonical news item normalised from any source."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    title: str
    body: str
    source: NewsSource
    url: str
    published_at: datetime
    ticker_refs: list[str] = Field(default_factory=list)
    category: str = "uncategorized"


class NewsAggregator:
    """Fetch and aggregate news from multiple sources with graceful degradation."""

    # Source fetch priority order (fastest/breaking → slowest/analysis)
    _SOURCE_PRIORITY: list[NewsSource] = [
        NewsSource.TWITTER,
        NewsSource.NEWSAPI,
        NewsSource.REDDIT,
    ]

    def __init__(
        self,
        newsapi_key: str | None = None,
        twitter_api_key: str | None = None,
        reddit_subreddits: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
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

    async def fetch_recent(self, source: NewsSource, limit: int = 20) -> list[NewsItem]:
        """Fetch recent items from a single source."""
        try:
            match source:
                case NewsSource.NEWSAPI:
                    return await self._fetch_newsapi(limit)
                case NewsSource.TWITTER:
                    return await self._fetch_twitter(limit)
                case NewsSource.REDDIT:
                    return await self._fetch_reddit(limit)
        except Exception:
            logger.exception("Source %s failed, returning empty", source.value)
            return []
        return []

    async def fetch_all(self, limit: int = 20) -> list[NewsItem]:
        """Aggregate from all sources in priority order."""
        items: list[NewsItem] = []
        per_source = max(limit, 20)
        for source in self._SOURCE_PRIORITY:
            source_items = await self.fetch_recent(source, limit=per_source)
            items.extend(source_items)
        # Deduplicate by id (first occurrence wins per priority order)
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
            logger.warning("NEWSAPI_KEY not set, skipping NewsAPI")
            return []

        params: dict[str, Any] = {
            "apiKey": self._newsapi_key,
            "pageSize": min(limit, 100),
            "language": "en",
        }

        max_retries = 3
        base_delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await self._client.get(
                    f"{self._newsapi_base}/top-headlines",
                    params=params,
                )

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

                if response.status_code != 200:
                    logger.warning("NewsAPI returned HTTP %d, skipping", response.status_code)
                    return []

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
                                id=f"newsapi-{article.get('source', {}).get('id', 'unknown')}-{idx}",
                                title=article.get("title", "") or "",
                                body=article.get("description", "") or "",
                                source=NewsSource.NEWSAPI,
                                url=article.get("url", "") or "",
                                published_at=published_at,
                                ticker_refs=[],
                                category="uncategorized",
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

    async def _fetch_twitter(self, limit: int) -> list[NewsItem]:
        """Stub — returns empty until Twitter API credentials are configured."""
        if not self._twitter_api_key:
            logger.warning("TWITTER_API_KEY not set, Twitter source unavailable")
            return []
        # Future: implement Twitter/X API v2 integration
        logger.warning("Twitter API integration not yet implemented")
        return []

    async def _fetch_reddit(self, limit: int) -> list[NewsItem]:
        """Fetch recent posts from configured subreddits via RSS."""
        items: list[NewsItem] = []

        for sub in self._reddit_subreddits:
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
                                category=sub,
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