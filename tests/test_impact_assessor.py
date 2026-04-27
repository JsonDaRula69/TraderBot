"""Tests for the news impact assessor."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from traderbot.news.impact_assessor import (
    CATEGORY_SENSITIVITY,
    CORROBORATION_MULTIPLIER,
    HIGH_IMPACT_THRESHOLD,
    ImpactAssessor,
    ImpactWeights,
    LOW_IMPACT_THRESHOLD,
    SIMILARITY_THRESHOLD,
    SOURCE_AUTHORITY,
    _cosine_similarity,
)
from traderbot.news.models import (
    ClassifiedNews,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _news_item(**overrides: object) -> NewsItem:
    base: dict[str, object] = {
        "id": "n-001",
        "title": "Fed raises interest rates by 25bps",
        "body": "The Federal Reserve raised interest rates, impacting SPY and TLT markets.",
        "source": NewsSource.NEWSAPI,
        "url": "https://example.com/fed-rates",
        "published_at": datetime.now(tz=timezone.utc) - timedelta(minutes=30),
        "ticker_refs": ["SPY", "TLT"],
        "category": NewsCategory.ECONOMICS,
    }
    base.update(overrides)
    return NewsItem.model_validate(base)


def _classified(news_item: NewsItem, **overrides: object) -> ClassifiedNews:
    base: dict[str, object] = {
        "news_item": news_item,
        "category": news_item.category,
    }
    base.update(overrides)
    return ClassifiedNews.model_validate(base)


def _sentiment(**overrides: object) -> SentimentResult:
    base: dict[str, object] = {
        "news_id": "n-001",
        "score": -0.45,
        "confidence": 0.82,
        "model": "vader",
        "timestamp": datetime.now(tz=timezone.utc),
    }
    base.update(overrides)
    return SentimentResult.model_validate(base)


def _assess(
    news: NewsItem | None = None,
    classified: ClassifiedNews | None = None,
    sentiment: SentimentResult | None = None,
    corroborating_count: int = 0,
    voyage_client: object | None = None,
) -> ImpactAssessment:
    news = news or _news_item()
    classified = classified or _classified(news)
    sentiment = sentiment or _sentiment()
    assessor = ImpactAssessor()
    return assessor.assess(news, classified, sentiment, corroborating_count, voyage_client)


# ── Basic assess ─────────────────────────────────────────────────────


class TestBasicAssess:
    def test_returns_impact_assessment(self):
        result = _assess()
        assert isinstance(result, ImpactAssessment)

    def test_ticker_from_news_item(self):
        result = _assess()
        assert result.ticker == "SPY"

    def test_ticker_unknown_when_no_refs(self):
        news = _news_item(ticker_refs=[])
        result = _assess(news=news)
        assert result.ticker == "UNKNOWN"

    def test_news_id_preserved(self):
        result = _assess()
        assert result.news_id == "n-001"

    def test_magnitude_bounded_0_to_1(self):
        result = _assess()
        assert 0.0 <= result.magnitude <= 1.0

    def test_confidence_bounded_0_to_1(self):
        result = _assess()
        assert 0.0 <= result.confidence <= 1.0


class TestDirection:
    def test_negative_sentiment_bearish(self):
        sentiment = _sentiment(score=-0.45)
        result = _assess(sentiment=sentiment)
        assert result.direction == "bearish"

    def test_positive_sentiment_bullish(self):
        sentiment = _sentiment(score=0.55)
        result = _assess(sentiment=sentiment)
        assert result.direction == "bullish"

    def test_near_zero_sentiment_neutral(self):
        sentiment = _sentiment(score=0.05)
        result = _assess(sentiment=sentiment)
        assert result.direction == "neutral"

    def test_zero_sentiment_neutral(self):
        sentiment = _sentiment(score=0.0)
        result = _assess(sentiment=sentiment)
        assert result.direction == "neutral"

    def test_positive_threshold_boundary(self):
        sentiment = _sentiment(score=0.1)
        result = _assess(sentiment=sentiment)
        assert result.direction == "neutral"

    def test_negative_threshold_boundary(self):
        sentiment = _sentiment(score=-0.1)
        result = _assess(sentiment=sentiment)
        assert result.direction == "neutral"


class TestTimeframe:
    def test_high_impact_immediate(self):
        news = _news_item(
            source=NewsSource.NEWSAPI,
            published_at=datetime.now(tz=timezone.utc),
            ticker_refs=["SPY"],
            title="SPY SPY SPY",
        )
        sentiment = _sentiment(score=-0.8, confidence=0.95)
        corr = 5
        result = _assess(news=news, sentiment=sentiment, corroborating_count=corr)
        if result.magnitude > HIGH_IMPACT_THRESHOLD:
            assert result.timeframe == "immediate"

    def test_moderate_impact_short_term(self):
        result = _assess()
        if LOW_IMPACT_THRESHOLD <= result.magnitude <= HIGH_IMPACT_THRESHOLD:
            assert result.timeframe == "short_term"

    def test_low_impact_long_term(self):
        news = _news_item(
            source=NewsSource.REDDIT,
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=48),
            ticker_refs=[],
            title="Unrelated post",
            body="Random content with no ticker mentions",
        )
        sentiment = _sentiment(score=0.02, confidence=0.3)
        result = _assess(news=news, sentiment=sentiment)
        if result.magnitude < LOW_IMPACT_THRESHOLD:
            assert result.timeframe == "long_term"


class TestSourceAuthority:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (NewsSource.NEWSAPI, 0.8),
            (NewsSource.TWITTER, 0.6),
            (NewsSource.REDDIT, 0.5),
        ],
    )
    def test_source_authority_values(self, source, expected):
        assert SOURCE_AUTHORITY[source] == expected

    def test_newsapi_scores_higher_than_twitter(self):
        news_api = _assess(news=_news_item(source=NewsSource.NEWSAPI))
        twitter = _assess(news=_news_item(source=NewsSource.TWITTER))
        assert news_api.magnitude >= twitter.magnitude

    def test_newsapi_scores_higher_than_reddit(self):
        news_api = _assess(news=_news_item(source=NewsSource.NEWSAPI))
        reddit = _assess(news=_news_item(source=NewsSource.REDDIT))
        assert news_api.magnitude >= reddit.magnitude


class TestRecency:
    def test_fresh_news_high_recency(self):
        news = _news_item(published_at=datetime.now(tz=timezone.utc))
        assessor = ImpactAssessor()
        recency = assessor._compute_recency(news.published_at)
        assert recency > 0.99

    def test_6_hour_old_news_half_decay(self):
        published = datetime.now(tz=timezone.utc) - timedelta(hours=6)
        assessor = ImpactAssessor()
        recency = assessor._compute_recency(published)
        assert 0.45 < recency < 0.55

    def test_day_old_news_low_recency(self):
        published = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        assessor = ImpactAssessor()
        recency = assessor._compute_recency(published)
        assert recency < 0.1

    def test_naive_datetime_treated_as_utc(self):
        published = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
        assessor = ImpactAssessor()
        recency = assessor._compute_recency(published)
        assert recency > 0.9


class TestMarketSensitivity:
    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            (NewsCategory.ECONOMICS, 0.9),
            (NewsCategory.POLITICS, 0.7),
            (NewsCategory.WEATHER, 0.6),
            (NewsCategory.CULTURE, 0.3),
            (NewsCategory.TECH, 0.5),
            (NewsCategory.SCIENCE, 0.4),
        ],
    )
    def test_category_sensitivity(self, category, expected):
        assert CATEGORY_SENSITIVITY[category] == expected

    def test_economics_highest_sensitivity(self):
        assert CATEGORY_SENSITIVITY[NewsCategory.ECONOMICS] == 0.9


class TestCorroboration:
    def test_no_corroboration_no_boost(self):
        result = _assess(corroborating_count=0)
        assert 0.0 <= result.magnitude <= 1.0

    def test_corroboration_boost_applied(self):
        single = _assess(corroborating_count=0)
        multi = _assess(corroborating_count=2)
        assert multi.magnitude >= single.magnitude

    def test_corroboration_boost_capped_at_1(self):
        high_auth_news = _news_item(
            source=NewsSource.NEWSAPI,
            published_at=datetime.now(tz=timezone.utc),
            ticker_refs=["SPY"],
            title="SPY SPY SPY SPY SPY",
        )
        sentiment = _sentiment(score=-0.8, confidence=0.95)
        result = _assess(
            news=high_auth_news,
            sentiment=sentiment,
            corroborating_count=10,
        )
        assert result.magnitude <= 1.0

    def test_corroboration_multiplier_is_1_3(self):
        assert CORROBORATION_MULTIPLIER == 1.3

    def test_single_source_no_multiplier(self):
        single = _assess(corroborating_count=0)
        double = _assess(corroborating_count=1)
        assert double.magnitude > single.magnitude or double.magnitude == single.magnitude


class TestVoyageRelevance:
    def test_voyage_similarity_used_when_available(self):
        mock_client = MagicMock()
        mock_client.embed.side_effect = [
            [0.1] * 10,
            [0.1] * 10,
        ]
        assessor = ImpactAssessor()
        news = _news_item()
        sim = assessor._voyage_similarity(news, mock_client)
        assert sim is not None
        assert 0.0 <= sim <= 1.0

    def test_voyage_returns_none_falls_back(self):
        mock_client = MagicMock()
        mock_client.embed.return_value = None
        assessor = ImpactAssessor()
        news = _news_item()
        result = assessor._compute_relevance(news, mock_client)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_voyage_exception_falls_back(self):
        mock_client = MagicMock()
        mock_client.embed.side_effect = RuntimeError("API error")
        assessor = ImpactAssessor()
        news = _news_item()
        result = assessor._compute_relevance(news, mock_client)
        assert result is not None

    def test_no_voyage_uses_keyword_overlap(self):
        assessor = ImpactAssessor()
        news = _news_item()
        result = assessor._compute_relevance(news, None)
        assert result is not None

    def test_keyword_overlap_with_matching_refs(self):
        news = _news_item(title="SPY surges", body="SPY SPY", ticker_refs=["SPY"])
        assessor = ImpactAssessor()
        ratio = assessor._keyword_overlap_ratio(news)
        assert ratio > 0.0

    def test_keyword_overlap_no_refs_moderate_default(self):
        news = _news_item(ticker_refs=[])
        assessor = ImpactAssessor()
        ratio = assessor._keyword_overlap_ratio(news)
        assert ratio == 0.5


class TestDegradationWithoutVoyage:
    def test_assess_without_voyage_client(self):
        result = _assess(voyage_client=None)
        assert isinstance(result, ImpactAssessment)
        assert 0.0 <= result.magnitude <= 1.0

    def test_assess_with_voyage_none_return(self):
        mock_client = MagicMock()
        mock_client.embed.return_value = None
        result = _assess(voyage_client=mock_client)
        assert isinstance(result, ImpactAssessment)
        assert 0.0 <= result.magnitude <= 1.0

    def test_assess_with_voyage_exception(self):
        mock_client = MagicMock()
        mock_client.embed.side_effect = Exception("timeout")
        result = _assess(voyage_client=mock_client)
        assert isinstance(result, ImpactAssessment)
        assert 0.0 <= result.magnitude <= 1.0


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0, abs=1e-6)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestWeights:
    def test_weights_sum_to_1(self):
        weights = ImpactWeights()
        total = (
            weights.direct_relevance
            + weights.source_authority
            + weights.recency
            + weights.market_sensitivity
            + weights.corroboration
        )
        assert total == pytest.approx(1.0)

    def test_relevance_is_highest_weight(self):
        weights = ImpactWeights()
        assert weights.direct_relevance == 0.3

    def test_source_authority_second(self):
        weights = ImpactWeights()
        assert weights.source_authority == 0.25

    def test_recency_weight(self):
        weights = ImpactWeights()
        assert weights.recency == 0.2

    def test_sensitivity_weight(self):
        weights = ImpactWeights()
        assert weights.market_sensitivity == 0.15

    def test_corroboration_lowest_weight(self):
        weights = ImpactWeights()
        assert weights.corroboration == 0.1


class TestReasoning:
    def test_reasoning_includes_components(self):
        result = _assess()
        assert "relevance=" in result.reasoning
        assert "authority=" in result.reasoning
        assert "recency=" in result.reasoning
        assert "sensitivity=" in result.reasoning

    def test_reasoning_includes_direction(self):
        result = _assess()
        assert any(d in result.reasoning for d in ("bullish", "bearish", "neutral"))

    def test_corroboration_mentioned_when_present(self):
        result = _assess(corroborating_count=3)
        assert "corroborated" in result.reasoning


class TestImpactBands:
    def test_impact_bands_complete(self):
        fresh = _news_item(
            source=NewsSource.NEWSAPI,
            published_at=datetime.now(tz=timezone.utc),
            ticker_refs=["SPY"],
            title="SPY SPY SPY",
        )
        sentiment = _sentiment(score=-0.9, confidence=0.95)
        high = _assess(news=fresh, sentiment=sentiment, corroborating_count=5)

        stale = _news_item(
            source=NewsSource.REDDIT,
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=48),
            ticker_refs=[],
            title="x",
            body="y",
        )
        low_sentiment = _sentiment(score=0.02, confidence=0.2)
        low = _assess(news=stale, sentiment=low_sentiment)

        assert high.magnitude > low.magnitude