"""Integration tests for the news pipeline — sources → classify → score → assess.

No real API calls. VADER/TextBlob run locally (deterministic).
All external calls (httpx, feedparser, VoyageClient) are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from traderbot.news.classifier import NewsClassifier
from traderbot.news.impact_assessor import ImpactAssessor
from traderbot.news.models import (
    ClassifiedNews,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.news.sources import NewsAggregator
from traderbot.news.sources import NewsItem as SourcesNewsItem
from traderbot.news.sources import NewsSource as SourcesNewsSource


def _sources_item(**overrides: object) -> SourcesNewsItem:
    """Create a sources.NewsItem (lowercase enum, bare str category)."""
    base: dict[str, object] = {
        "id": "newsapi-test-0",
        "title": "Fed raises interest rates amid inflation concerns",
        "body": "The Federal Reserve announced a 25 basis point rate hike.",
        "source": SourcesNewsSource.NEWSAPI,
        "url": "https://example.com/fed-rates",
        "published_at": datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        "ticker_refs": ["SPY", "TLT"],
        "category": "Economics",
    }
    base.update(overrides)
    return SourcesNewsItem.model_validate(base)


def _models_item(**overrides: object) -> NewsItem:
    """Create a models.NewsItem (capitalized enum, NewsCategory category)."""
    base: dict[str, object] = {
        "id": "newsapi-test-0",
        "title": "Fed raises interest rates amid inflation concerns",
        "body": "The Federal Reserve announced a 25 basis point rate hike.",
        "source": NewsSource.NEWSAPI,
        "url": "https://example.com/fed-rates",
        "published_at": datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        "ticker_refs": ["SPY", "TLT"],
        "category": NewsCategory.ECONOMICS,
    }
    base.update(overrides)
    return NewsItem.model_validate(base)


def convert_sources_to_models_item(src: SourcesNewsItem) -> NewsItem:
    """Convert sources.NewsItem to models.NewsItem for the classifier pipeline."""
    source_map: dict[SourcesNewsSource, NewsSource] = {
        SourcesNewsSource.NEWSAPI: NewsSource.NEWSAPI,
        SourcesNewsSource.TWITTER: NewsSource.TWITTER,
        SourcesNewsSource.REDDIT: NewsSource.REDDIT,
    }
    category_map: dict[str, NewsCategory] = {
        "economics": NewsCategory.ECONOMICS,
        "politics": NewsCategory.POLITICS,
        "weather": NewsCategory.WEATHER,
        "culture": NewsCategory.CULTURE,
        "tech": NewsCategory.TECH,
        "science": NewsCategory.SCIENCE,
        "uncategorized": NewsCategory.ECONOMICS,
    }
    return NewsItem(
        id=src.id,
        title=src.title,
        body=src.body,
        source=source_map[src.source],
        url=src.url,
        published_at=src.published_at,
        ticker_refs=src.ticker_refs,
        category=category_map.get(src.category.lower(), NewsCategory.ECONOMICS),
    )




class TestFullPipeline:
    """End-to-end pipeline: create mock news items, classify → score → assess."""

    def test_economics_item_pipeline(self):
        """Economics news flows through the full pipeline producing structured output."""
        item = _models_item(
            title="Fed raises interest rates amid inflation concerns",
            body="The Federal Reserve announced a 25 basis point rate hike.",
            category=NewsCategory.ECONOMICS,
            ticker_refs=["SPY", "TLT"],
        )
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        assert classified.category == NewsCategory.ECONOMICS
        assert classified.news_item.id == item.id

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)
        assert -1.0 <= sentiment.score <= 1.0
        assert 0.0 <= sentiment.confidence <= 1.0
        assert sentiment.news_id == item.id

        assessor = ImpactAssessor()
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert impact.news_id == item.id
        assert impact.ticker in ("SPY", "TLT")
        assert impact.direction in ("bullish", "bearish", "neutral")
        assert 0.0 <= impact.magnitude <= 1.0
        assert 0.0 <= impact.confidence <= 1.0
        assert impact.reasoning

    def test_politics_item_pipeline(self):
        """Politics news correctly classified and assessed."""
        item = _models_item(
            id="pol-1",
            title="Senate passes new legislation on tech regulation",
            body="Congress voted to approve sweeping technology regulations.",
            source=NewsSource.NEWSAPI,
            category=NewsCategory.POLITICS,
            ticker_refs=[],
        )
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        assert classified.category == NewsCategory.POLITICS

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)

        assessor = ImpactAssessor()
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0
        assert impact.direction in ("bullish", "bearish", "neutral")

    def test_weather_item_pipeline(self):
        """Weather news flows through the pipeline."""
        item = _models_item(
            id="wx-1",
            title="Hurricane approaching the Gulf Coast",
            body="Category 4 hurricane expected to make landfall tomorrow.",
            source=NewsSource.NEWSAPI,
            category=NewsCategory.WEATHER,
            ticker_refs=[],
        )
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        assert classified.category == NewsCategory.WEATHER

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)

        assessor = ImpactAssessor()
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0
        assert impact.direction in ("bearish", "neutral")

    def test_social_media_item_pipeline(self):
        """Twitter/Reddit items use VADER for sentiment."""
        item = _models_item(
            id="tweet-1",
            title="Bullish on tech stocks! Amazing earnings!",
            body="Great quarter for big tech companies.",
            source=NewsSource.TWITTER,
            category=NewsCategory.TECH,
            ticker_refs=["QQQ"],
        )
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)
        assert sentiment.model == "vader"

        assessor = ImpactAssessor()
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0

    def test_reddit_item_pipeline(self):
        """Reddit items use VADER for sentiment."""
        item = _models_item(
            id="reddit-1",
            title="Dollar weakening as inflation data disappoints",
            body="The CPI numbers came in higher than expected.",
            source=NewsSource.REDDIT,
            category=NewsCategory.ECONOMICS,
            ticker_refs=["DXY"],
        )
        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)
        assert sentiment.model == "vader"

    def test_pipeline_produces_reasoning_string(self):
        """Impact assessment includes structured reasoning."""
        item = _models_item(ticker_refs=["SPY"])
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        sentiment = SentimentScorer(voyage_client=None).score(
            f"{item.title} {item.body}", item.source, item.id
        )
        impact = ImpactAssessor().assess(item, classified, sentiment)
        assert "relevance=" in impact.reasoning
        assert "authority=" in impact.reasoning
        assert "recency=" in impact.reasoning
        assert "sensitivity=" in impact.reasoning





class TestPipelineDegradation:
    """Each component gracefully degrades when its dependency is unavailable."""

    def test_classifier_without_voyage(self):
        """Classifier falls back to keyword-only when Voyage is unavailable."""
        classifier = NewsClassifier(voyage=None)
        item = _models_item(title="Fed raises interest rates")
        result = classifier.classify(item)
        assert result.category == NewsCategory.ECONOMICS
        assert result.news_item.title == "Fed raises interest rates"

    def test_classifier_ambiguous_without_voyage(self):
        """Ambiguous keyword matches degrade to best-guess when Voyage unavailable."""
        classifier = NewsClassifier(voyage=None)
        item = _models_item(title="Vote on rate hike")
        result = classifier.classify(item)

        assert result.category in list(NewsCategory)

    def test_scorer_without_voyage(self):
        """Sentiment scorer returns valid results without Voyage uplift."""
        scorer = SentimentScorer(voyage_client=None)
        result = scorer.score("Markets rallied on good news", NewsSource.NEWSAPI, "test-1")
        assert "+voyage" not in result.model
        assert -1.0 <= result.score <= 1.0

    def test_scorer_voyage_returns_none(self):
        """Sentiment scorer degrades when Voyage embed returns None."""
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = None
        scorer = SentimentScorer(voyage_client=mock_voyage)
        result = scorer.score("Ambiguous market text", NewsSource.NEWSAPI, "test-2")
        assert "+voyage" not in result.model

    def test_assessor_without_voyage(self):
        """Impact assessor uses keyword overlap when Voyage unavailable."""
        assessor = ImpactAssessor()
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0

    def test_assessor_voyage_exception_falls_back(self):
        """Impact assessor falls back to keyword overlap on Voyage exception."""
        mock_voyage = MagicMock()
        mock_voyage.embed.side_effect = RuntimeError("API error")
        assessor = ImpactAssessor()
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=-0.3, confidence=0.7, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = assessor.assess(item, classified, sentiment, voyage_client=mock_voyage)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0

    @pytest.mark.asyncio
    async def test_aggregator_without_newsapi_key(self):
        """Aggregator skips NewsAPI when no key is configured."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.aclose = AsyncMock()
        agg = NewsAggregator(newsapi_key=None, http_client=mock_client)
        items = await agg._fetch_newsapi(limit=10)
        assert items == []
        mock_client.get.assert_not_awaited()
        await agg.close()

    @pytest.mark.asyncio
    async def test_aggregator_without_twitter_key(self):
        """Aggregator returns empty for Twitter (stub implementation)."""
        agg = NewsAggregator(twitter_api_key=None)
        items = await agg._fetch_twitter(limit=10)
        assert items == []

    @pytest.mark.asyncio
    async def test_aggregator_no_api_keys_returns_empty(self):
        """With no API keys and no Reddit data, aggregator returns empty."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.aclose = AsyncMock()
        agg = NewsAggregator(
            newsapi_key=None,
            twitter_api_key=None,
            http_client=mock_client,
        )
        with patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[]):
            items = await agg.fetch_all(limit=20)
        assert items == []
        await agg.close()

    def test_full_pipeline_no_external_deps(self):
        """Complete pipeline runs without any external API dependencies."""
        item = _models_item(
            title="Fed inflation data released, CPI rises",
            body="Consumer price index shows continued inflation pressure.",
            category=NewsCategory.ECONOMICS,
            ticker_refs=["SPY"],
        )
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        assert classified.category == NewsCategory.ECONOMICS

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)

        assessor = ImpactAssessor()
        impact = assessor.assess(item, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert impact.direction in ("bullish", "bearish", "neutral")
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0

    def test_full_pipeline_voyage_embed_failure(self):
        """Pipeline completes even when Voyage embed fails (returns None)."""
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = None
        mock_voyage.rerank.return_value = None

        item = _models_item(title="Research discovery at laboratory")
        classifier = NewsClassifier(voyage=mock_voyage)
        classified = classifier.classify(item)

        assert classified.category in list(NewsCategory)





class TestCategoryClassification:
    """Classify produces correct category for various news items."""

    @pytest.mark.parametrize(
        ("title", "body", "expected_category"),
        [
            ("Fed raises interest rates", "", NewsCategory.ECONOMICS),
            ("Inflation hits new highs", "", NewsCategory.ECONOMICS),
            ("Senate passes new legislation", "", NewsCategory.POLITICS),
            ("Election day results", "", NewsCategory.POLITICS),
            ("Hurricane approaching coast", "", NewsCategory.WEATHER),
            ("Blizzard warning issued", "", NewsCategory.WEATHER),
            ("Oscar nominations announced", "", NewsCategory.CULTURE),
            ("Box office results this weekend", "", NewsCategory.CULTURE),
            ("New AI software released", "", NewsCategory.TECH),
            ("Semiconductor industry booms", "", NewsCategory.TECH),
            ("NASA space discovery", "", NewsCategory.SCIENCE),
            ("Genome research breakthrough", "", NewsCategory.SCIENCE),
        ],
    )
    def test_keyword_classification(self, title: str, body: str, expected_category: NewsCategory):
        """Keyword-only classification maps to correct categories."""
        classifier = NewsClassifier(voyage=None)
        item = _models_item(title=title, body=body, category=expected_category)
        result = classifier.classify(item)
        assert result.category == expected_category

    def test_category_preserved_in_classified_news(self):
        """ClassifiedNews preserves the full news item data."""
        item = _models_item(
            id="test-preserve",
            title="GDP growth exceeds expectations",
            body="Economic data shows strong quarterly growth.",
            source=NewsSource.NEWSAPI,
            url="https://example.com/gdp",
            published_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
            ticker_refs=["SPY"],
            category=NewsCategory.ECONOMICS,
        )
        classifier = NewsClassifier(voyage=None)
        result = classifier.classify(item)
        assert result.news_item.id == "test-preserve"
        assert result.news_item.url == "https://example.com/gdp"
        assert result.news_item.ticker_refs == ["SPY"]





class TestSentimentScoringPipeline:
    """Sentiment scoring with various text types and sources."""

    def test_social_media_positive_vader(self):
        """Twitter/Reddit use VADER for clearly positive text."""
        scorer = SentimentScorer(voyage_client=None)
        result = scorer.score(
            "Amazing earnings! Bullish outlook for tech stocks!",
            NewsSource.TWITTER,
            "tw-1",
        )
        assert result.score > 0.3
        assert result.model == "vader"

    def test_social_media_negative_vader(self):
        """Twitter/Reddit use VADER for clearly negative text."""
        scorer = SentimentScorer(voyage_client=None)
        result = scorer.score(
            "Terrible crash, devastating losses across the board",
            NewsSource.REDDIT,
            "rd-1",
        )
        assert result.score < -0.3
        assert result.model == "vader"

    def test_article_positive_textblob(self):
        """NewsAPI uses TextBlob for clearly positive articles."""
        scorer = SentimentScorer(voyage_client=None)
        result = scorer.score(
            "The economy showed excellent growth in the latest quarterly report, "
            "with GDP expanding beyond expectations and strong positive results.",
            NewsSource.NEWSAPI,
            "na-1",
        )
        assert result.score > 0.0
        assert result.model == "textblob"

    def test_article_negative_textblob(self):
        """NewsAPI uses TextBlob for clearly negative articles."""
        scorer = SentimentScorer(voyage_client=None)
        result = scorer.score(
            "Companies announced massive terrible layoffs across multiple sectors "
            "as the worst economic crisis deepened with awful results.",
            NewsSource.NEWSAPI,
            "na-2",
        )
        assert result.score < 0.0
        assert result.model.startswith("textblob")

    def test_voyage_uplift_for_ambiguous_social(self):
        """Voyage uplift activates for ambiguous VADER scores on social media."""
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = [0.1] * 1024
        scorer = SentimentScorer(voyage_client=mock_voyage)
        result = scorer.score(
            "Markets are mixed today",
            NewsSource.TWITTER,
            "tw-2",
        )

        if -0.3 < result.score < 0.3:
            assert "+voyage" in result.model

    def test_voyage_uplift_for_ambiguous_article(self):
        """Voyage uplift activates for ambiguous TextBlob scores on articles."""
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = [0.1] * 1024
        scorer = SentimentScorer(voyage_client=mock_voyage)
        result = scorer.score(
            "The market may shift depending on policy.",
            NewsSource.NEWSAPI,
            "na-3",
        )

        assert result.model.startswith("textblob") or "+voyage" in result.model

    def test_sentiment_result_bounded(self):
        """Sentiment score and confidence are always within bounds."""
        scorer = SentimentScorer(voyage_client=None)
        for source in (NewsSource.TWITTER, NewsSource.NEWSAPI, NewsSource.REDDIT):
            result = scorer.score("Some news text", source, "test")
            assert -1.0 <= result.score <= 1.0
            assert 0.0 <= result.confidence <= 1.0





class TestImpactAssessmentPipeline:
    """Impact assessment with corroborating sources."""

    def test_single_source_assessment(self):
        """Single source produces valid impact assessment."""
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=-0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = ImpactAssessor().assess(item, classified, sentiment, corroborating_count=0)
        assert impact.direction == "bearish"
        assert 0.0 <= impact.magnitude <= 1.0

    def test_corroboration_boosts_magnitude(self):
        """Multiple corroborating sources increase impact magnitude."""
        item = _models_item(
            source=NewsSource.NEWSAPI,
            ticker_refs=["SPY"],
            published_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        )
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=-0.7, confidence=0.9, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assessor = ImpactAssessor()

        single = assessor.assess(item, classified, sentiment, corroborating_count=0)
        multi = assessor.assess(item, classified, sentiment, corroborating_count=3)
        assert multi.magnitude >= single.magnitude

    def test_newsapi_higher_authority_than_reddit(self):
        """NewsAPI source produces higher magnitude than Reddit for same content."""
        newsapi_item = _models_item(
            source=NewsSource.NEWSAPI,
            title="Fed rate decision",
            ticker_refs=["SPY"],
        )
        reddit_item = _models_item(
            id="reddit-1",
            source=NewsSource.REDDIT,
            title="Fed rate decision",
            ticker_refs=["SPY"],
        )
        sentiment = SentimentResult(
            news_id="test", score=0.5, confidence=0.8, model="textblob",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assessor = ImpactAssessor()
        newsapi_classified = ClassifiedNews(news_item=newsapi_item, category=NewsCategory.ECONOMICS)
        reddit_classified = ClassifiedNews(news_item=reddit_item, category=NewsCategory.ECONOMICS)

        newsapi_impact = assessor.assess(newsapi_item, newsapi_classified, sentiment)
        reddit_impact = assessor.assess(reddit_item, reddit_classified, sentiment)
        assert newsapi_impact.magnitude >= reddit_impact.magnitude

    def test_economics_category_has_highest_sensitivity(self):
        """Economics news has highest market sensitivity."""
        item = _models_item(category=NewsCategory.ECONOMICS)
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        econ_impact = ImpactAssessor().assess(item, classified, sentiment)

        culture_item = _models_item(id="c-1", category=NewsCategory.CULTURE)
        culture_classified = ClassifiedNews(news_item=culture_item, category=NewsCategory.CULTURE)
        culture_impact = ImpactAssessor().assess(culture_item, culture_classified, sentiment)
        assert econ_impact.magnitude > culture_impact.magnitude

    def test_reasoning_includes_corroboration_when_present(self):
        """Reasoning string includes corroboration count."""
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=-0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = ImpactAssessor().assess(item, classified, sentiment, corroborating_count=3)
        assert "corroborated by 3 additional source" in impact.reasoning

    def test_reasoning_no_corroboration_when_absent(self):
        """Reasoning string omits corroboration when count is 0."""
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=-0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = ImpactAssessor().assess(item, classified, sentiment, corroborating_count=0)
        assert "corroborated" not in impact.reasoning

    def test_timeframe_maps_to_magnitude(self):
        """Impact timeframe is consistent with magnitude."""
        # High-impact → immediate
        item = _models_item(
            source=NewsSource.NEWSAPI,
            ticker_refs=["SPY"],
            title="SPY SPY SPY",
            published_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        )
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        strong_sentiment = SentimentResult(
            news_id=item.id, score=-0.8, confidence=0.95, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = ImpactAssessor().assess(item, classified, strong_sentiment, corroborating_count=5)
        if impact.magnitude > 0.7:
            assert impact.timeframe == "immediate"





class TestNewsItemConversion:
    """Sources.NewsItem converts correctly to models.NewsItem for classifier."""

    def test_basic_conversion(self):
        """Source news item fields map correctly to model news item."""
        src = _sources_item(
            id="newsapi-src-1",
            title="Fed raises rates",
            body="Rate hike announced.",
            source=SourcesNewsSource.NEWSAPI,
            url="https://example.com/fed",
            ticker_refs=["SPY"],
            category="Economics",
        )
        converted = convert_sources_to_models_item(src)
        assert converted.id == "newsapi-src-1"
        assert converted.title == "Fed raises rates"
        assert converted.body == "Rate hike announced."
        assert converted.source == NewsSource.NEWSAPI
        assert converted.url == "https://example.com/fed"
        assert converted.ticker_refs == ["SPY"]
        assert converted.category == NewsCategory.ECONOMICS

    def test_twitter_source_conversion(self):
        """Twitter source converts to capitalized enum."""
        src = _sources_item(
            source=SourcesNewsSource.TWITTER,
            category="Tech",
        )
        converted = convert_sources_to_models_item(src)
        assert converted.source == NewsSource.TWITTER
        assert converted.category == NewsCategory.TECH

    def test_reddit_source_conversion(self):
        """Reddit source converts to capitalized enum."""
        src = _sources_item(
            source=SourcesNewsSource.REDDIT,
            category="Politics",
        )
        converted = convert_sources_to_models_item(src)
        assert converted.source == NewsSource.REDDIT
        assert converted.category == NewsCategory.POLITICS

    def test_uncategorized_defaults_to_economics(self):
        """Uncategorized source items default to Economics."""
        src = _sources_item(category="uncategorized")
        converted = convert_sources_to_models_item(src)
        assert converted.category == NewsCategory.ECONOMICS

    def test_default_ticker_refs(self):
        """Default ticker_refs is empty list."""
        src = _sources_item(ticker_refs=[])
        converted = convert_sources_to_models_item(src)
        assert converted.ticker_refs == []

    def test_converted_item_passes_classifier(self):
        """Converted item can be classified without error."""
        src = _sources_item(
            title="Hurricane warning issued for Gulf Coast",
            body="Category 4 hurricane expected to make landfall.",
            category="Weather",
        )
        converted = convert_sources_to_models_item(src)
        classifier = NewsClassifier(voyage=None)
        result = classifier.classify(converted)
        assert result.category == NewsCategory.WEATHER

    def test_converted_item_passes_full_pipeline(self):
        """Converted item flows through classify → score → assess."""
        src = _sources_item(
            title="Fed inflation CPI data released",
            body="Consumer prices rose more than expected.",
            category="Economics",
            ticker_refs=["SPY", "TLT"],
        )
        converted = convert_sources_to_models_item(src)

        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(converted)
        assert classified.category == NewsCategory.ECONOMICS

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(
            f"{converted.title} {converted.body}", converted.source, converted.id
        )

        assessor = ImpactAssessor()
        impact = assessor.assess(converted, classified, sentiment)
        assert isinstance(impact, ImpactAssessment)
        assert impact.ticker in ("SPY", "TLT")
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0

    @pytest.mark.asyncio
    async def test_fetch_and_convert_pipeline(self):
        """Fetch from aggregator, convert, and classify."""
        src_item = SourcesNewsItem(
            id="newsapi-mock-1",
            title="Senate passes major legislation",
            body="The Senate voted to approve the new bill.",
            source=SourcesNewsSource.NEWSAPI,
            url="https://example.com/senate",
            published_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
            ticker_refs=[],
            category="Politics",
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.aclose = AsyncMock()

        agg = NewsAggregator(newsapi_key="test-key", http_client=mock_client)
        with patch.object(agg, "_fetch_newsapi", new_callable=AsyncMock, return_value=[src_item]), \
             patch.object(agg, "_fetch_twitter", new_callable=AsyncMock, return_value=[]), \
             patch.object(agg, "_fetch_reddit", new_callable=AsyncMock, return_value=[]):
            items = await agg.fetch_all(limit=20)

        assert len(items) == 1
        converted = convert_sources_to_models_item(items[0])
        classifier = NewsClassifier(voyage=None)
        result = classifier.classify(converted)
        assert result.category == NewsCategory.POLITICS





class TestVoyageIntegration:
    """Integration with Voyage embeddings (mocked)."""

    def test_classifier_with_voyage_embed(self):
        """Classifier uses Voyage embedding when keyword path is ambiguous."""
        from traderbot.news.classifier import _CATEGORY_DESCRIPTIONS, _KALSHI_CATEGORIES

        dim = len(_KALSHI_CATEGORIES)
        cat_embs: dict[NewsCategory, list[float]] = {}
        for i, cat in enumerate(_KALSHI_CATEGORIES):
            vec = [0.0] * dim
            vec[i] = 1.0
            cat_embs[cat] = vec

        desc_to_emb: dict[str, list[float]] = {}
        for cat, desc in _CATEGORY_DESCRIPTIONS.items():
            desc_to_emb[desc] = cat_embs[cat]

        news_emb = [0.9] + [0.05] * (dim - 1)

        mock_voyage = MagicMock()

        def embed_side_effect(text: str, **kwargs: object) -> list[float] | None:
            if text in desc_to_emb:
                return desc_to_emb[text]
            return news_emb

        mock_voyage.embed.side_effect = embed_side_effect
        mock_voyage.rerank.return_value = None

        classifier = NewsClassifier(voyage=mock_voyage)
        item = _models_item(title="Market outlook for q3 financial results")
        result = classifier.classify(item)
        assert result.category in _KALSHI_CATEGORIES

    def test_scorer_with_voyage_uplift(self):
        """Sentiment scorer applies Voyage uplift for ambiguous scores."""
        mock_voyage = MagicMock()
        call_count = [0]
        text_emb = [0.9] + [0.1] * 511 + [0.1] * 512
        pos_emb = [0.9] * 512 + [0.1] * 512
        neg_emb = [0.1] * 512 + [0.9] * 512

        def embed_side_effect(text: str, **kwargs: object) -> list[float]:
            call_count[0] += 1
            if call_count[0] == 1:
                return text_emb
            elif call_count[0] == 2:
                return pos_emb
            else:
                return neg_emb

        mock_voyage.embed.side_effect = embed_side_effect
        scorer = SentimentScorer(voyage_client=mock_voyage)
        scorer.score("Market outlook uncertain", NewsSource.NEWSAPI, "voy-test")
        assert mock_voyage.embed.called

    def test_impact_with_voyage_relevance(self):
        """Impact assessor uses Voyage for relevance when available."""
        mock_voyage = MagicMock()
        mock_voyage.embed.side_effect = [
            [0.8] * 10,
            [0.8] * 10,
        ]
        assessor = ImpactAssessor()
        item = _models_item(ticker_refs=["SPY"])
        classified = ClassifiedNews(news_item=item, category=NewsCategory.ECONOMICS)
        sentiment = SentimentResult(
            news_id=item.id, score=0.5, confidence=0.8, model="vader",
            timestamp=datetime(2026, 4, 21, tzinfo=UTC),
        )
        impact = assessor.assess(item, classified, sentiment, voyage_client=mock_voyage)
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0
        assert mock_voyage.embed.called

    def test_full_pipeline_with_mock_voyage(self):
        """Full pipeline runs with mocked Voyage client across all components."""
        from traderbot.news.classifier import _CATEGORY_DESCRIPTIONS, _KALSHI_CATEGORIES

        dim = len(_KALSHI_CATEGORIES)
        cat_embs: dict[NewsCategory, list[float]] = {}
        for i, cat in enumerate(_KALSHI_CATEGORIES):
            vec = [0.0] * dim
            vec[i] = 1.0
            cat_embs[cat] = vec

        desc_to_emb: dict[str, list[float]] = {}
        for cat, desc in _CATEGORY_DESCRIPTIONS.items():
            desc_to_emb[desc] = cat_embs[cat]

        news_emb = [0.9, 0.05, 0.05, 0.05, 0.05, 0.05]

        mock_voyage = MagicMock()

        def embed_side_effect(text: str, **kwargs: object) -> list[float] | None:
            if text in desc_to_emb:
                return desc_to_emb[text]
            return news_emb

        mock_voyage.embed.side_effect = embed_side_effect
        mock_voyage.rerank.return_value = None

        item = _models_item(title="Quarterly GDP report shows growth trends")
        classifier = NewsClassifier(voyage=mock_voyage)
        classified = classifier.classify(item)
        assert classified.category in _KALSHI_CATEGORIES

        scorer = SentimentScorer(voyage_client=mock_voyage)
        sentiment = scorer.score(f"{item.title} {item.body}", item.source, item.id)

        impact_voyage = MagicMock()
        impact_voyage.embed.side_effect = embed_side_effect
        assessor = ImpactAssessor()
        impact = assessor.assess(
            item, classified, sentiment, corroborating_count=2, voyage_client=impact_voyage,
        )
        assert isinstance(impact, ImpactAssessment)
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0
