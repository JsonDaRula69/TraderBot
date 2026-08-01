"""Validation tests for news pipeline Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from traderbot.news.models import (
    ClassifiedNews,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)


def _make_news_item(**overrides: object) -> dict[str, object]:
    """Factory for valid NewsItem kwargs."""
    base = {
        "id": "n-001",
        "title": "Fed raises rates",
        "body": "The Federal Reserve raised interest rates by 25bps.",
        "source": NewsSource.NEWSAPI,
        "url": "https://example.com/fed-rates",
        "published_at": datetime(2025, 1, 15, 14, 30, tzinfo=UTC),
        "ticker_refs": ["SPY", "TLT"],
        "category": NewsCategory.ECONOMICS,
    }
    base.update(overrides)
    return base


def _make_sentiment(**overrides: object) -> dict[str, object]:
    base = {
        "news_id": "n-001",
        "score": -0.45,
        "confidence": 0.82,
        "model": "gpt-4o",
        "timestamp": datetime(2025, 1, 15, 14, 35, tzinfo=UTC),
    }
    base.update(overrides)
    return base


def _make_impact(**overrides: object) -> dict[str, object]:
    base = {
        "news_id": "n-001",
        "ticker": "SPY",
        "direction": "bearish",
        "magnitude": 0.6,
        "confidence": 0.75,
        "reasoning": "Rate hikes pressure equities",
        "timeframe": "1w",
    }
    base.update(overrides)
    return base


# --- NewsSource enum ---

class TestNewsSource:
    def test_values(self):
        assert NewsSource.NEWSAPI == 'newsapi'
        assert NewsSource.TWITTER == 'twitter'
        assert NewsSource.REDDIT == 'reddit'

    def test_from_string(self):
        assert NewsSource('newsapi') is NewsSource.NEWSAPI


# --- NewsCategory enum ---

class TestNewsCategory:
    def test_matches_market_category_values(self):
        from traderbot.kalshi.models import MarketCategory as KalshiMarketCategory

        for cat in NewsCategory:
            assert cat.value == KalshiMarketCategory[cat.name].value

    def test_all_categories_present(self):
        names = {c.name for c in NewsCategory}
        assert names == {
            "ECONOMICS", "POLITICS", "SCIENCE_AND_TECHNOLOGY", "SPORTS", "CRYPTO",
            "WEATHER",
            "COMMODITIES", "COMPANIES", "ELECTIONS", "ENTERTAINMENT",
            "FINANCIALS", "HEALTH", "MENTIONS", "SOCIAL",
        }


# --- NewsItem ---

class TestNewsItem:
    def test_valid(self):
        item = NewsItem(**_make_news_item())
        assert item.id == "n-001"
        assert item.source is NewsSource.NEWSAPI
        assert item.ticker_refs == ["SPY", "TLT"]

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            NewsItem(**_make_news_item(), unexpected=42)

    def test_strict_type_enforcement(self):
        with pytest.raises(ValidationError):
            NewsItem(**_make_news_item(id=123))


# --- SentimentResult ---

class TestSentimentResult:
    def test_valid(self):
        s = SentimentResult(**_make_sentiment())
        assert s.score == -0.45
        assert s.confidence == 0.82

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            SentimentResult(**_make_sentiment(score=-1.5))
        with pytest.raises(ValidationError):
            SentimentResult(**_make_sentiment(score=1.5))

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            SentimentResult(**_make_sentiment(confidence=-0.1))
        with pytest.raises(ValidationError):
            SentimentResult(**_make_sentiment(confidence=1.5))

    def test_boundary_values(self):
        SentimentResult(**_make_sentiment(score=-1.0, confidence=0.0))
        SentimentResult(**_make_sentiment(score=1.0, confidence=1.0))

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            SentimentResult(**_make_sentiment(foo="bar"))


# --- ImpactAssessment ---

class TestImpactAssessment:
    def test_valid(self):
        imp = ImpactAssessment(**_make_impact())
        assert imp.direction == "bearish"
        assert imp.magnitude == 0.6

    def test_direction_literal(self):
        ImpactAssessment(**_make_impact(direction="bullish"))
        ImpactAssessment(**_make_impact(direction="neutral"))
        with pytest.raises(ValidationError):
            ImpactAssessment(**_make_impact(direction="sideways"))

    def test_magnitude_bounds(self):
        with pytest.raises(ValidationError):
            ImpactAssessment(**_make_impact(magnitude=-0.1))
        with pytest.raises(ValidationError):
            ImpactAssessment(**_make_impact(magnitude=1.5))

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ImpactAssessment(**_make_impact(confidence=-0.01))
        with pytest.raises(ValidationError):
            ImpactAssessment(**_make_impact(confidence=1.01))

    def test_boundary_values(self):
        ImpactAssessment(**_make_impact(magnitude=0.0, confidence=0.0))
        ImpactAssessment(**_make_impact(magnitude=1.0, confidence=1.0))

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            ImpactAssessment(**_make_impact(extra=True))


# --- ClassifiedNews ---

class TestClassifiedNews:
    def test_minimal(self):
        cn = ClassifiedNews(
            news_item=NewsItem(**_make_news_item()),
            category=NewsCategory.ECONOMICS,
        )
        assert cn.sentiment is None
        assert cn.impact is None

    def test_with_sentiment_and_impact(self):
        cn = ClassifiedNews(
            news_item=NewsItem(**_make_news_item()),
            category=NewsCategory.ECONOMICS,
            sentiment=SentimentResult(**_make_sentiment()),
            impact=ImpactAssessment(**_make_impact()),
        )
        assert cn.sentiment.score == -0.45
        assert cn.impact.direction == "bearish"

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            ClassifiedNews(
                news_item=NewsItem(**_make_news_item()),
                category=NewsCategory.ECONOMICS,
                rogue="value",
            )
