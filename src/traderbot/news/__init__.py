"""News & social media pipeline — source aggregation, ingestion, and parsing."""

from traderbot.news.classifier import NewsClassifier
from traderbot.news.impact_assessor import ImpactAssessor
from traderbot.news.ingest import ingest_news, get_news_summary
from traderbot.news.models import (
    ClassifiedNews,
    DataPoint,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.news.sources import NewsAggregator

__all__ = [
    "ClassifiedNews",
    "DataPoint",
    "ImpactAssessment",
    "ImpactAssessor",
    "NewsAggregator",
    "NewsCategory",
    "NewsClassifier",
    "NewsItem",
    "NewsSource",
    "SentimentResult",
    "SentimentScorer",
    "get_news_summary",
    "ingest_news",
]
