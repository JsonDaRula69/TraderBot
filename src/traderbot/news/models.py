"""Pydantic models for the news pipeline — items, sentiment, impact, and classification."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — needed at runtime by Pydantic
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import MarketCategory

NewsCategory = MarketCategory
"""Backward-compatible alias — prefer MarketCategory from kalshi.models."""


class NewsSource(StrEnum):
    """Supported news sources."""

    NEWSAPI = "NewsAPI"
    TWITTER = "Twitter"
    REDDIT = "Reddit"


class NewsItem(BaseModel):
    """Raw news item from any source."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    title: str
    body: str
    source: NewsSource
    url: str
    published_at: datetime
    ticker_refs: list[str]
    category: NewsCategory


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
