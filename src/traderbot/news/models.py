"""Pydantic models for the news pipeline — items, sentiment, impact, and classification."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — needed at runtime by Pydantic
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import MarketCategory


class NewsSource(StrEnum):
    """Supported news source identifiers."""

    NEWSAPI = "newsapi"
    TWITTER = "twitter"
    REDDIT = "reddit"
    OPEN_METEO = "open_meteo"
    COINGECKO = "coingecko"
    THESPORTSDB = "thesportsdb"
    OPENWEATHERMAP = "openweathermap"
    FRED = "fred"
    GOOGLE_TRENDS = "google_trends"


NewsCategory = MarketCategory

__all__ = ["DataPoint", "NewsCategory", "NewsItem", "NewsSource"]


class NewsItem(BaseModel):
    """Canonical news item from any source.

    This is the single source of truth for news item data across all modules.
    Source-specific factory methods handle conversion from raw API responses.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    title: str
    body: str
    source: NewsSource
    url: str
    published_at: datetime
    ticker_refs: list[str] = Field(default_factory=list)
    category: NewsCategory | None = None
    data_freshness: Literal["realtime", "delayed_24h", "unknown"] = "unknown"
    content_truncated: bool = False


class SentimentResult(BaseModel):
    """Sentiment analysis result for a news item."""

    model_config = ConfigDict(strict=True, extra="forbid")

    news_id: str
    score: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    model: str
    timestamp: datetime


class ImpactAssessment(BaseModel):
    """Assessed market impact of a news item on a specific ticker."""

    model_config = ConfigDict(strict=True, extra="forbid")

    news_id: str
    ticker: str
    direction: Literal["bullish", "bearish", "neutral"]
    magnitude: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str
    timeframe: str


class ClassifiedNews(BaseModel):
    """Fully classified news item with optional sentiment and impact."""

    model_config = ConfigDict(strict=True, extra="forbid")

    news_item: NewsItem
    category: NewsCategory
    sentiment: SentimentResult | None = None
    impact: ImpactAssessment | None = None


class DataPoint(BaseModel):
    """Canonical data point from any non-news source (weather, crypto, trends, etc.).

    Holds structured payload data (e.g., temperature, price index, poll score).
    Monetary values inside `data` must be represented as integer cents.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    source: NewsSource
    category: NewsCategory | None = None
    title: str
    data: dict = Field(default_factory=dict)
    timestamp: datetime
    ticker_refs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
