"""Sentiment scorer — VADER + TextBlob fast path, Voyage uplift for ambiguous scores."""

import logging
import math
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, PrivateAttr

from traderbot.news.models import NewsSource, SentimentResult

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _VaderAnalyzer
except ImportError:
    _VaderAnalyzer = None  # type: ignore[assignment,misc]

try:
    from textblob import TextBlob as _TextBlob
except ImportError:
    _TextBlob = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_AMBIGUOUS_LOW = -0.3
_AMBIGUOUS_HIGH = 0.3

_POSITIVE_ANCHOR = "strong bullish optimism excellent growth positive outlook"
_NEGATIVE_ANCHOR = "severe bearish pessimism terrible decline negative outlook"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class SentimentScorer(BaseModel):
    """Multi-model sentiment scorer with Voyage uplift for ambiguous scores.

    Fast path: VADER (<1ms) for social media, TextBlob (~5ms) for articles.
    Slow path: Voyage semantic uplift when compound score is in -0.3..+0.3 range.
    """

    model_config = ConfigDict(strict=True, extra="forbid", arbitrary_types_allowed=True)

    _vader: _VaderAnalyzer | None = PrivateAttr(default=None)
    _voyage_client: object | None = PrivateAttr(default=None)

    def __init__(self, voyage_client: object | None = None, **data: object) -> None:
        super().__init__(**data)
        self._voyage_client = voyage_client
        if _VaderAnalyzer is not None:
            self._vader = _VaderAnalyzer()  # type: ignore[assignment]
        else:
            logger.warning("vaderSentiment not installed — VADER path unavailable")

    def score(self, text: str, source: NewsSource, news_id: str = "") -> SentimentResult:
        """Score text sentiment using source-appropriate model with optional Voyage uplift."""
        if source in (NewsSource.TWITTER, NewsSource.REDDIT):
            raw_score, confidence, model_name = self._score_vader(text)
        else:
            raw_score, confidence, model_name = self._score_textblob(text)

        final_score = raw_score
        final_model = model_name

        if _AMBIGUOUS_LOW < raw_score < _AMBIGUOUS_HIGH:
            uplifted = self._voyage_uplift(text, raw_score)
            if uplifted is not None:
                final_score = uplifted
                final_model = f"{model_name}+voyage"

        return SentimentResult(
            news_id=news_id,
            score=final_score,
            confidence=confidence,
            model=final_model,
            timestamp=datetime.now(tz=UTC),
        )

    def _score_vader(self, text: str) -> tuple[float, float, str]:
        """Return (compound_score, confidence, model_name) via VADER."""
        if self._vader is None:
            logger.warning("VADER unavailable — returning neutral")
            return (0.0, 0.0, "vader")
        scores = self._vader.polarity_scores(text)
        compound = scores["compound"]
        confidence = min(abs(compound), 1.0)
        return (compound, confidence, "vader")

    def _score_textblob(self, text: str) -> tuple[float, float, str]:
        """Return (polarity, confidence, model_name) via TextBlob."""
        if _TextBlob is None:
            logger.warning("TextBlob unavailable — returning neutral")
            return (0.0, 0.0, "textblob")
        blob = _TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        confidence = min(abs(polarity) * (0.5 + 0.5 * subjectivity), 1.0)
        return (polarity, confidence, "textblob")

    def _voyage_uplift(self, text: str, base_score: float) -> float | None:
        """Refine ambiguous sentiment using Voyage semantic embeddings.

        Embeds the text plus positive/negative anchor strings, then adjusts
        the score based on cosine similarity to each anchor.
        """
        if self._voyage_client is None:
            return None

        text_emb = self._voyage_client.embed(text)
        if text_emb is None:
            return None

        pos_emb = self._voyage_client.embed(_POSITIVE_ANCHOR)
        neg_emb = self._voyage_client.embed(_NEGATIVE_ANCHOR)
        if pos_emb is None or neg_emb is None:
            return None

        sim_pos = _cosine_similarity(text_emb, pos_emb)
        sim_neg = _cosine_similarity(text_emb, neg_emb)

        delta = sim_pos - sim_neg
        # Scale delta to ±0.3 max adjustment, blended with base score
        adjustment = delta * 0.3
        refined = max(-1.0, min(1.0, base_score + adjustment))
        return refined
