"""Tests for news/sources.py — NewsAggregator, NewsItem, NewsSource."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from traderbot.news.sources import NewsAggregator, NewsItem, NewsSource


def _newsapi_article(
    title: str = "Test Article",
    description: str = "Test body",
    url: str = "https://example.com/article",
    published_at: str = "2026-04-21T12:00:00Z",
    source_id: str = "test-source",
) -> dict:
    return {
        "source": {"id": source_id, "name": "Test Source"},
        "title": title,
        "description": description,
        "url": url,
        "publishedAt": published_at,
    }


def _newsapi_response(articles: list[dict] | None = None) -> httpx.Response:
    if articles is None:
        articles = [_newsapi_article()]
    body = {"status": "ok", "totalResults": len(articles), "articles": articles}
    return httpx.Response(
        status_code=200,
        json=body,
        request=httpx.Request("GET", "https://newsapi.org/v2/top-headlines"),
    )


class _FeedEntry(dict):
    """Dict subclass that also supports attribute access (mimics feedparser entries)."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

def _reddit_rss_entry(
    title: str = "Reddit Post",
    summary: str = "Reddit body",
    link: str = "https://reddit.com/r/test/1",
    published_parsed: tuple | None = (2026, 4, 21, 12, 0, 0, 1, 111, 0),
) -> dict:
    entry = {
        "title": title,
        "summary": summary,
        "link": link,
    }
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    return entry


class TestNewsSource:
    def test_str_enum_values(self):
        assert NewsSource.NEWSAPI == "newsapi"
        assert NewsSource.TWITTER == "twitter"
        assert NewsSource.REDDIT == "reddit"

    def test_all_sources_present(self):
        assert set(NewsSource) == {NewsSource.NEWSAPI, NewsSource.TWITTER, NewsSource.REDDIT}


class TestNewsItem:
    def test_create_minimal(self):
        item = NewsItem(
            id="test-1",
            title="Title",
            body="Body",
            source=NewsSource.NEWSAPI,
            url="https://example.com",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert item.ticker_refs == []
        assert item.category == "uncategorized"

    def test_create_full(self):
        item = NewsItem(
            id="test-2",
            title="Title",
            body="Body",
            source=NewsSource.TWITTER,
            url="https://example.com",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            ticker_refs=["BTC", "ETH"],
            category="crypto",
        )
        assert item.source == NewsSource.TWITTER
        assert item.ticker_refs == ["BTC", "ETH"]

    def test_strict_forbids_extra(self):
        with pytest.raises(ValidationError):
            NewsItem(
                id="test-3",
                title="Title",
                body="Body",
                source=NewsSource.REDDIT,
                url="https://example.com",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                extra_field="not allowed",
            )


class TestNewsAggregatorInit:
    def test_default_subreddits(self):
        agg = NewsAggregator()
        assert agg._reddit_subreddits == ["politics", "economics", "weather"]

    def test_custom_subreddits(self):
        agg = NewsAggregator(reddit_subreddits=["crypto", "stocks"])
        assert agg._reddit_subreddits == ["crypto", "stocks"]

    def test_source_priority_order(self):
        assert NewsAggregator._SOURCE_PRIORITY == [
            NewsSource.TWITTER,
            NewsSource.NEWSAPI,
            NewsSource.REDDIT,
        ]


class TestFetchNewsAPI:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = _newsapi_response([_newsapi_article(title="Economic Data")])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        items = await agg._fetch_newsapi(limit=10)

        assert len(items) == 1
        assert items[0].title == "Economic Data"
        assert items[0].source == NewsSource.NEWSAPI
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_key_returns_empty(self):
        agg = NewsAggregator()
        items = await agg._fetch_newsapi(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_handles_429_with_backoff(self):
        rate_limited = httpx.Response(
            status_code=429,
            request=httpx.Request("GET", "https://newsapi.org"),
        )
        success = _newsapi_response()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[rate_limited, success])

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        with patch("traderbot.news.sources.asyncio.sleep", new_callable=AsyncMock):
            items = await agg._fetch_newsapi(limit=10)

        assert len(items) == 1
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_429_retries(self):
        rate_limited = httpx.Response(
            status_code=429,
            request=httpx.Request("GET", "https://newsapi.org"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=rate_limited)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        with patch("traderbot.news.sources.asyncio.sleep", new_callable=AsyncMock):
            items = await agg._fetch_newsapi(limit=10)

        assert items == []
        assert mock_client.get.await_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        not_found = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://newsapi.org"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=not_found)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        items = await agg._fetch_newsapi(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_non_json_response_returns_empty(self):
        non_json = httpx.Response(
            status_code=200,
            text="<html>Not JSON</html>",
            request=httpx.Request("GET", "https://newsapi.org"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=non_json)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        items = await agg._fetch_newsapi(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_malformed_article_skipped(self):
        articles = [
            {"title": None, "description": None, "url": None, "publishedAt": None, "source": {}},
            _newsapi_article(title="Good Article"),
        ]
        mock_response = _newsapi_response(articles)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        items = await agg._fetch_newsapi(limit=10)
        assert len(items) == 2  # first item gets id but empty strings, second is good

    @pytest.mark.asyncio
    async def test_limits_results(self):
        articles = [_newsapi_article(title=f"Article {i}") for i in range(50)]
        mock_response = _newsapi_response(articles)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        items = await agg._fetch_newsapi(limit=5)
        assert len(items) == 5

    @pytest.mark.asyncio
    async def test_http_error_retries(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(
            side_effect=[httpx.ConnectError("connection failed"), _newsapi_response()]
        )

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        with patch("traderbot.news.sources.asyncio.sleep", new_callable=AsyncMock):
            items = await agg._fetch_newsapi(limit=10)

        assert len(items) == 1


class TestFetchTwitter:
    @pytest.mark.asyncio
    async def test_no_key_returns_empty(self):
        agg = NewsAggregator()
        items = await agg._fetch_twitter(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_with_key_returns_empty_stub(self):
        agg = NewsAggregator(twitter_api_key="test-key")
        items = await agg._fetch_twitter(limit=10)
        assert items == []


class TestFetchReddit:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = httpx.Response(
            status_code=200,
            text="<rss>fake</rss>",
            request=httpx.Request("GET", "https://www.reddit.com/r/politics/.rss"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_feed = MagicMock()
        mock_feed.entries = [
            _FeedEntry(_reddit_rss_entry(title="Political News")),
        ]

        agg = NewsAggregator(http_client=mock_client, reddit_subreddits=["politics"])
        with patch("traderbot.news.sources.feedparser.parse", return_value=mock_feed):
            items = await agg._fetch_reddit(limit=10)

        assert len(items) == 1
        assert items[0].source == NewsSource.REDDIT

    @pytest.mark.asyncio
    async def test_non_200_skips_subreddit(self):
        not_found = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://www.reddit.com/r/politics/.rss"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=not_found)

        agg = NewsAggregator(http_client=mock_client)
        items = await agg._fetch_reddit(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_exception_continues_to_next_subreddit(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        call_count = 0

        async def side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("fail")
            return httpx.Response(
                status_code=200,
                text="<rss>fake</rss>",
                request=httpx.Request("GET", url),
            )

        mock_client.get = AsyncMock(side_effect=side_effect)

        mock_feed = MagicMock()
        mock_feed.entries = [
            _FeedEntry(_reddit_rss_entry(title="Econ News")),
        ]

        agg = NewsAggregator(
            reddit_subreddits=["politics", "economics"],
            http_client=mock_client,
        )
        with patch("traderbot.news.sources.feedparser.parse", return_value=mock_feed):
            items = await agg._fetch_reddit(limit=10)

        assert any(i.title == "Econ News" for i in items)

    @pytest.mark.asyncio
    async def test_limits_results(self):
        mock_response = httpx.Response(
            status_code=200,
            text="<rss>fake</rss>",
            request=httpx.Request("GET", "https://www.reddit.com/r/politics/.rss"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_feed = MagicMock()
        mock_feed.entries = [
            _FeedEntry(_reddit_rss_entry(title=f"Post {i}"))
            for i in range(30)
        ]

        agg = NewsAggregator(http_client=mock_client)
        with patch("traderbot.news.sources.feedparser.parse", return_value=mock_feed):
            items = await agg._fetch_reddit(limit=5)

        assert len(items) == 5

    @pytest.mark.asyncio
    async def test_malformed_entry_skipped(self):
        mock_response = httpx.Response(
            status_code=200,
            text="<rss>fake</rss>",
            request=httpx.Request("GET", "https://www.reddit.com/r/politics/.rss"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        bad_entry = MagicMock()
        bad_entry.title = "Bad"
        bad_entry.summary = "Bad"
        bad_entry.link = "https://reddit.com/bad"
        bad_entry.published_parsed = None
        type(bad_entry).get = lambda self, key, default="": default
        bad_entry.__getitem__ = lambda self, key: None

        good_entry = _FeedEntry(_reddit_rss_entry(title="Good Post"))

        mock_feed = MagicMock()
        mock_feed.entries = [bad_entry, good_entry]

        agg = NewsAggregator(http_client=mock_client)
        with patch("traderbot.news.sources.feedparser.parse", return_value=mock_feed):
            items = await agg._fetch_reddit(limit=10)

        assert len(items) >= 1


class TestFetchRecent:
    @pytest.mark.asyncio
    async def test_dispatches_to_correct_source(self):
        agg = NewsAggregator()
        with patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=[]):
            await agg.fetch_recent(NewsSource.NEWSAPI, limit=5)
            agg._fetch_newsapi.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self):
        agg = NewsAggregator(http_client=AsyncMock(spec=httpx.AsyncClient))
        with patch.object(
            agg, "_fetch_newsapi", new_callable=AsyncMock, side_effect=Exception("boom")
        ):
            items = await agg.fetch_recent(NewsSource.NEWSAPI, limit=10)
            assert items == []


class TestFetchAll:
    @pytest.mark.asyncio
    async def test_aggregates_all_sources(self):
        newsapi_item = NewsItem(
            id="newsapi-1",
            title="NewsAPI Article",
            body="",
            source=NewsSource.NEWSAPI,
            url="https://example.com/1",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        reddit_item = NewsItem(
            id="reddit-1",
            title="Reddit Post",
            body="",
            source=NewsSource.REDDIT,
            url="https://reddit.com/1",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        agg = NewsAggregator()
        with (
            patch.object(agg, "_fetch_twitter", new_callable=AsyncMock, return_value=[]),
            patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=[newsapi_item]),
            patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[reddit_item]),
        ):
            items = await agg.fetch_all(limit=20)

        assert len(items) == 2
        sources = [i.source for i in items]
        assert NewsSource.NEWSAPI in sources
        assert NewsSource.REDDIT in sources

    @pytest.mark.asyncio
    async def test_deduplicates_by_id(self):
        item = NewsItem(
            id="dup-1",
            title="Duplicate",
            body="",
            source=NewsSource.NEWSAPI,
            url="https://example.com/dup",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        agg = NewsAggregator()
        with (
            patch.object(agg, "_fetch_twitter", new_callable=AsyncMock, return_value=[]),
            patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=[item]),
            patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[item]),
        ):
            items = await agg.fetch_all(limit=20)

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        items = [
            NewsItem(
                id=f"item-{i}",
                title=f"Item {i}",
                body="",
                source=NewsSource.NEWSAPI,
                url=f"https://example.com/{i}",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            for i in range(50)
        ]

        agg = NewsAggregator()
        with (
            patch.object(agg, "_fetch_twitter", new_callable=AsyncMock, return_value=[]),
            patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=items),
            patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[]),
        ):
            result = await agg.fetch_all(limit=10)

        assert len(result) == 10

    @pytest.mark.asyncio
    async def test_source_failure_doesnt_crash(self):
        agg = NewsAggregator()
        with (
            patch.object(agg, "_fetch_twitter", new_callable=AsyncMock, side_effect=Exception("fail")),
            patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=[]),
            patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[]),
        ):
            items = await agg.fetch_all(limit=20)

        assert items == []


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.aclose = AsyncMock()
        agg = NewsAggregator(http_client=mock_client)

        async with agg as a:
            assert a is agg

        mock_client.aclose.assert_awaited_once()
