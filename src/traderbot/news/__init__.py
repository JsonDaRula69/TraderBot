"""News & social media pipeline — source aggregation and parsing."""

from traderbot.news.models import (
    NewsItem,
    NewsSource,
    NewsCategory,
    ClassifiedNews,
    SentimentResult,
    ImpactAssessment
)
from traderbot.news.classifier import NewsClassifier
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.news.impact_assessor import ImpactAssessor
from traderbot.news.sources import NewsAggregator

__all__ = [
    "NewsAggregator",
    "NewsItem",
    "NewsSource",
    "NewsCategory",
    "ClassifiedNews",
    "SentimentResult",
    "ImpactAssessment",
    "NewsClassifier",
    "SentimentScorer",
    "ImpactAssessor"
]
