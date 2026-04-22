"""Impact assessor — scores news items for market impact potential."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from traderbot.news.models import (
    ClassifiedNews,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)

if TYPE_CHECKING:
    from traderbot.news.embeddings import VoyageClient

logger = logging.getLogger(__name__)

# ── Weight configuration ──────────────────────────────────────────────
WEIGHT_DIRECT_RELEVANCE: float = 0.3
WEIGHT_SOURCE_AUTHORITY: float = 0.25
WEIGHT_RECENCY: float = 0.2
WEIGHT_MARKET_SENSITIVITY: float = 0.15
WEIGHT_CORROBORATION: float = 0.1

# ── Impact bands ──────────────────────────────────────────────────────
HIGH_IMPACT_THRESHOLD: float = 0.7
LOW_IMPACT_THRESHOLD: float = 0.3

# ── Voyage similarity threshold ─────────────────────────────────────
SIMILARITY_THRESHOLD: float = 0.65

# ── Recency decay ────────────────────────────────────────────────────
RECENCY_HALF_LIFE_HOURS: float = 6.0

# ── Corroboration boost ──────────────────────────────────────────────
CORROBORATION_MULTIPLIER: float = 1.3

# ── Source authority: flat per-source weight ──────────────────────────
SOURCE_AUTHORITY: dict[NewsSource, float] = {
    NewsSource.NEWSAPI: 0.8,
    NewsSource.TWITTER: 0.6,
    NewsSource.REDDIT: 0.5,
}

# ── Per-category market sensitivity ───────────────────────────────────
CATEGORY_SENSITIVITY: dict[NewsCategory, float] = {
    NewsCategory.ECONOMICS: 0.9,
    NewsCategory.POLITICS: 0.7,
    NewsCategory.WEATHER: 0.6,
    NewsCategory.CULTURE: 0.3,
    NewsCategory.TECH: 0.5,
    NewsCategory.SCIENCE: 0.4,
    NewsCategory.SPORTS: 0.4,
    NewsCategory.CRYPTO: 0.8,
}

# ── Timeframe labels ─────────────────────────────────────────────────
TIMEFRAME_IMMEDIATE: str = "immediate"
TIMEFRAME_SHORT_TERM: str = "short_term"
TIMEFRAME_LONG_TERM: str = "long_term"

# ── Direction thresholds ─────────────────────────────────────────────
DIRECTION_POSITIVE_THRESHOLD: float = 0.1
DIRECTION_NEGATIVE_THRESHOLD: float = -0.1


class ImpactAssessor(BaseModel):
    """Scores news items for potential market impact.

    Uses a weighted combination of direct relevance, source authority,
    recency, market sensitivity, and corroboration. Voyage AI semantic
    similarity is used for relevance when available, falling back to
    keyword overlap otherwise.
    """

    model_config = ConfigDict(strict=True, extra="forbid", arbitrary_types_allowed=True)

    def assess(
        self,
        news_item: NewsItem,
        classified_news: ClassifiedNews,
        sentiment_result: SentimentResult,
        corroborating_count: int = 0,
        voyage_client: VoyageClient | None = None,
    ) -> ImpactAssessment:
        """Compute impact assessment for a news item on a ticker.

        Args:
            news_item: Raw news item with source, timestamp, etc.
            classified_news: Classified news with category.
            sentiment_result: Sentiment analysis result with score.
            corroborating_count: Number of additional sources reporting same event.
            voyage_client: Optional Voyage client for semantic relevance.

        Returns:
            ImpactAssessment with direction, magnitude, confidence, reasoning, timeframe.
        """
        relevance = self._compute_relevance(news_item, voyage_client)
        authority = self._compute_authority(news_item.source)
        recency = self._compute_recency(news_item.published_at)
        sensitivity = self._compute_sensitivity(classified_news.category)

        raw_impact = (
            WEIGHT_DIRECT_RELEVANCE * relevance
            + WEIGHT_SOURCE_AUTHORITY * authority
            + WEIGHT_RECENCY * recency
            + WEIGHT_MARKET_SENSITIVITY * sensitivity
            + WEIGHT_CORROBORATION * min(corroborating_count / 5.0, 1.0)
        )

        # Apply corroboration boost when 2+ sources report the same event
        total_sources = 1 + corroborating_count
        if total_sources >= 2:
            raw_impact *= CORROBORATION_MULTIPLIER
        magnitude = min(raw_impact, 1.0)

        direction = self._determine_direction(sentiment_result.score)
        timeframe = self._determine_timeframe(magnitude)
        confidence = self._compute_confidence(
            relevance, authority, recency, sentiment_result.confidence
        )
        reasoning = self._build_reasoning(
            relevance, authority, recency, sensitivity, corroborating_count, magnitude, direction
        )

        ticker = news_item.ticker_refs[0] if news_item.ticker_refs else "UNKNOWN"

        return ImpactAssessment(
            news_id=news_item.id,
            ticker=ticker,
            direction=direction,
            magnitude=magnitude,
            confidence=confidence,
            reasoning=reasoning,
            timeframe=timeframe,
        )

    def _compute_relevance(
        self,
        news_item: NewsItem,
        voyage_client: VoyageClient | None,
    ) -> float:
        """Compute direct relevance score via Voyage similarity or keyword overlap."""
        if voyage_client is not None:
            sim = self._voyage_similarity(news_item, voyage_client)
            if sim is not None:
                return sim

        # Fallback: keyword overlap ratio
        return self._keyword_overlap_ratio(news_item)

    def _voyage_similarity(
        self,
        news_item: NewsItem,
        voyage_client: VoyageClient,
    ) -> float | None:
        """Attempt Voyage semantic similarity; returns None on failure."""
        text = f"{news_item.title} {news_item.body}"
        query_text = " ".join(news_item.ticker_refs) if news_item.ticker_refs else news_item.title

        try:
            text_emb = voyage_client.embed(text)
            query_emb = voyage_client.embed(query_text)
            if text_emb is None or query_emb is None:
                logger.warning("Voyage embedding returned None — falling back to keyword overlap")
                return None
            sim = _cosine_similarity(text_emb, query_emb)
            return max(0.0, min(1.0, sim))
        except Exception:
            logger.warning("Voyage similarity failed — falling back to keyword overlap", exc_info=True)
            return None

    def _keyword_overlap_ratio(self, news_item: NewsItem) -> float:
        """Simple keyword overlap between title+body and ticker refs."""
        text_words = set((news_item.title + " " + news_item.body).lower().split())
        ref_words = set(
            " ".join(news_item.ticker_refs).lower().split()
        ) if news_item.ticker_refs else set()

        if not ref_words:
            # No ticker refs — moderate default
            return 0.5

        overlap = text_words & ref_words
        ratio = len(overlap) / len(ref_words) if ref_words else 0.0
        return min(ratio, 1.0)

    def _compute_authority(self, source: NewsSource) -> float:
        """Return flat source authority weight."""
        return SOURCE_AUTHORITY.get(source, 0.5)

    def _compute_recency(self, published_at: datetime) -> float:
        """Exponential decay with 6-hour half-life."""
        now = datetime.now(tz=timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        decay = math.exp(-0.693 * age_hours / RECENCY_HALF_LIFE_HOURS)
        return min(decay, 1.0)

    def _compute_sensitivity(self, category: NewsCategory) -> float:
        """Return per-category market sensitivity."""
        return CATEGORY_SENSITIVITY.get(category, 0.4)

    def _determine_direction(self, sentiment_score: float) -> str:
        """Map sentiment score to directional label."""
        if sentiment_score > DIRECTION_POSITIVE_THRESHOLD:
            return "bullish"
        if sentiment_score < DIRECTION_NEGATIVE_THRESHOLD:
            return "bearish"
        return "neutral"

    def _determine_timeframe(self, magnitude: float) -> str:
        """Map impact magnitude to timeframe label."""
        if magnitude > HIGH_IMPACT_THRESHOLD:
            return TIMEFRAME_IMMEDIATE
        if magnitude >= LOW_IMPACT_THRESHOLD:
            return TIMEFRAME_SHORT_TERM
        return TIMEFRAME_LONG_TERM

    def _compute_confidence(
        self,
        relevance: float,
        authority: float,
        recency: float,
        sentiment_confidence: float,
    ) -> float:
        """Aggregate confidence from component scores and sentiment confidence."""
        raw = (relevance + authority + recency + sentiment_confidence) / 4.0
        return min(raw, 1.0)

    def _build_reasoning(
        self,
        relevance: float,
        authority: float,
        recency: float,
        sensitivity: float,
        corroborating_count: int,
        magnitude: float,
        direction: str,
    ) -> str:
        """Produce human-readable reasoning summary."""
        corr_text = f", corroborated by {corroborating_count} additional source(s)" if corroborating_count > 0 else ""
        return (
            f"impact={magnitude:.2f} ({direction}): "
            f"relevance={relevance:.2f}, authority={authority:.2f}, "
            f"recency={recency:.2f}, sensitivity={sensitivity:.2f}"
            f"{corr_text}"
        )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)