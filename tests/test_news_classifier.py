"""Tests for news/classifier.py — hybrid keyword/Voyage classification pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from traderbot.news.classifier import (
    _CATEGORY_DESCRIPTIONS,
    _EMBED,
    _KALSHI_CATEGORIES,
    _KEYWORD,
    _RERANK,
    ClassificationResult,
    NewsClassifier,
    _cosine_similarity,
)
from traderbot.news.models import ClassifiedNews, NewsCategory, NewsItem, NewsSource


def _item(title: str, body: str = "", category: NewsCategory = NewsCategory.ECONOMICS) -> NewsItem:
    return NewsItem(
        id="test-1",
        title=title,
        body=body,
        source=NewsSource.NEWSAPI,
        url="https://example.com/test",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        ticker_refs=[],
        category=category,
    )


class TestKeywordFastPath:
    """Keyword-only classification — no Voyage needed."""

    def test_single_economics_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Fed raises interest rates"))
        assert result.category == NewsCategory.ECONOMICS

    def test_multiple_economics_keywords_higher_confidence(self):
        cls = NewsClassifier()
        meta = cls.classify_with_metadata(_item("Fed inflation CPI data released"))
        assert meta.category == NewsCategory.ECONOMICS
        assert meta.confidence > 0.85
        assert meta.method == _KEYWORD

    def test_single_politics_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Senate passes new legislation"))
        assert result.category == NewsCategory.POLITICS

    def test_single_weather_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Hurricane approaching the coast"))
        assert result.category == NewsCategory.WEATHER

    def test_single_culture_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Oscar nominations announced"))
        assert result.category == NewsCategory.ENTERTAINMENT

    def test_single_tech_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("New AI software released"))
        assert result.category == NewsCategory.SCIENCE_AND_TECHNOLOGY

    def test_single_science_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("NASA space discovery announced"))
        assert result.category == NewsCategory.SCIENCE_AND_TECHNOLOGY

    def test_keyword_in_body(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Breaking news", body="The Federal Reserve announced inflation data"))
        assert result.category == NewsCategory.ECONOMICS

    def test_no_keyword_hit_defaults_to_economics(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Something completely unrelated"))
        assert result.category == NewsCategory.ECONOMICS

    def test_keyword_confidence_capped(self):
        cls = NewsClassifier()
        meta = cls.classify_with_metadata(
            _item("Fed inflation GDP unemployment recession treasury CPI FOMC")
        )
        assert meta.confidence <= 0.95


class TestAmbiguousKeywords:
    """Multiple categories from keywords → ambiguous path."""

    def test_ambiguous_keyword_triggers_fallback(self):
        cls = NewsClassifier()
        # "rate" is economics, "vote" is politics → ambiguous
        meta = cls.classify_with_metadata(_item("Vote on rate hike delayed"))
        assert meta.flagged_for_llm is True

    def test_ambiguous_keyword_best_guess_without_voyage(self):
        cls = NewsClassifier()
        # Economics has more keyword matches than politics here
        result = cls.classify(_item("Fed inflation vote on rate"))
        # Should pick the category with most hits
        assert result.category in _KALSHI_CATEGORIES


class TestVoyageUnavailable:
    """Full pipeline with Voyage returning None (graceful degradation)."""

    def _mock_voyage_unavailable(self):
        voyage = MagicMock()
        voyage.embed.return_value = None
        voyage.rerank.return_value = None
        return voyage

    def test_keyword_fast_path_skips_voyage(self):
        """Decisive keyword match should never call Voyage."""
        voyage = self._mock_voyage_unavailable()
        cls = NewsClassifier(voyage=voyage)
        result = cls.classify(_item("Fed raises interest rates"))
        assert result.category == NewsCategory.ECONOMICS
        voyage.embed.assert_not_called()

    def test_ambiguous_without_voyage(self):
        voyage = self._mock_voyage_unavailable()
        cls = NewsClassifier(voyage=voyage)
        meta = cls.classify_with_metadata(_item("Vote on rate hike"))
        assert meta.flagged_for_llm is True
        # Still returns a category (best keyword guess)
        assert meta.category in _KALSHI_CATEGORIES

    def test_no_keywords_no_voyage(self):
        voyage = self._mock_voyage_unavailable()
        cls = NewsClassifier(voyage=voyage)
        meta = cls.classify_with_metadata(_item("Unfamiliar topic discussed"))
        assert meta.category == NewsCategory.ECONOMICS
        assert meta.flagged_for_llm is True
        assert meta.confidence < 0.5

    def test_none_voyage_degrades(self):
        cls = NewsClassifier(voyage=None)
        result = cls.classify(_item("Fed raises rates"))
        assert result.category == NewsCategory.ECONOMICS


class TestVoyageEmbedPath:
    """Voyage embedding similarity classification."""

    def _make_orthogonal_embeddings(self) -> dict[NewsCategory, list[float]]:
        dim = len(_KALSHI_CATEGORIES)
        embs: dict[NewsCategory, list[float]] = {}
        for i, cat in enumerate(_KALSHI_CATEGORIES):
            vec = [0.0] * dim
            vec[i] = 1.0
            embs[cat] = vec
        return embs

    def _mock_voyage_embed(self, news_emb: list[float], cat_embs: dict[NewsCategory, list[float]]):
        voyage = MagicMock()
        desc_to_emb: dict[str, list[float]] = {}
        for cat, desc in _CATEGORY_DESCRIPTIONS.items():
            desc_to_emb[desc] = cat_embs[cat]

        def embed_side_effect(text: str, **kwargs):
            if text in desc_to_emb:
                return desc_to_emb[text]
            return news_emb

        voyage.embed.side_effect = embed_side_effect
        voyage.rerank.return_value = None
        return voyage

    def test_embed_high_confidence(self):
        cat_embs = self._make_orthogonal_embeddings()
        dim = len(_KALSHI_CATEGORIES)
        news_emb = [0.9] + [0.05] * (dim - 1)
        voyage = self._mock_voyage_embed(news_emb, cat_embs)
        cls = NewsClassifier(voyage=voyage)
        meta = cls.classify_with_metadata(_item("Market outlook for q3 financials"))
        assert meta.method == _EMBED
        assert meta.confidence >= 0.7
        assert meta.category == NewsCategory.ECONOMICS

    def test_embed_no_keyword_match(self):
        cat_embs = self._make_orthogonal_embeddings()
        dim = len(_KALSHI_CATEGORIES)
        news_emb = [0.9] + [0.05] * (dim - 1)
        voyage = self._mock_voyage_embed(news_emb, cat_embs)
        cls = NewsClassifier(voyage=voyage)
        result = cls.classify(_item("Market outlook for q3"))
        assert result.category in _KALSHI_CATEGORIES
        assert voyage.embed.called


class TestVoyageRerankPath:
    """Voyage reranker for disambiguation when confidence is 0.5-0.7."""

    def _make_close_embeddings(self) -> dict[NewsCategory, list[float]]:
        dim = len(_KALSHI_CATEGORIES)
        embs: dict[NewsCategory, list[float]] = {}
        for i, cat in enumerate(_KALSHI_CATEGORIES):
            vec = [0.3] * dim
            vec[i] = 0.7
            embs[cat] = vec
        return embs

    def _mock_voyage_rerank(self, rerank_result: list[tuple[int, float]]):
        voyage = MagicMock()
        cat_embs = self._make_close_embeddings()
        dim = len(_KALSHI_CATEGORIES)
        news_emb = [0.55, 0.35] + [0.3] * (dim - 2)
        desc_to_emb: dict[str, list[float]] = {}
        for cat, desc in _CATEGORY_DESCRIPTIONS.items():
            desc_to_emb[desc] = cat_embs[cat]

        def embed_side_effect(text: str, **kwargs):
            if text in desc_to_emb:
                return desc_to_emb[text]
            return news_emb

        voyage.embed.side_effect = embed_side_effect
        voyage.rerank.return_value = rerank_result
        return voyage

    def test_rerank_resolves_ambiguity(self):
        voyage = self._mock_voyage_rerank([(0, 0.85), (1, 0.4)])
        cls = NewsClassifier(voyage=voyage)
        meta = cls.classify_with_metadata(_item("Traders weigh outlook for q3"))
        assert meta.method == _RERANK
        assert meta.category == NewsCategory.ECONOMICS

    def test_rerank_failure_falls_back_to_embed(self):
        voyage = MagicMock()
        cat_embs = self._make_close_embeddings()
        dim = len(_KALSHI_CATEGORIES)
        news_emb = [0.6, 0.35] + [0.3] * (dim - 2)
        desc_to_emb: dict[str, list[float]] = {}
        for cat, desc in _CATEGORY_DESCRIPTIONS.items():
            desc_to_emb[desc] = cat_embs[cat]

        def embed_side_effect(text: str, **kwargs):
            if text in desc_to_emb:
                return desc_to_emb[text]
            return news_emb

        voyage.embed.side_effect = embed_side_effect
        voyage.rerank.return_value = None

        cls = NewsClassifier(voyage=voyage)
        meta = cls.classify_with_metadata(_item("Traders weigh outlook for q3"))
        assert meta.method == _EMBED


class TestLLMFlagging:
    """Low confidence results flagged for future Agent LLM."""

    def test_low_confidence_flagged(self):
        cls = NewsClassifier(voyage=None)
        meta = cls.classify_with_metadata(_item("Something mysterious"))
        assert meta.flagged_for_llm is True
        assert meta.confidence < 0.5

    def test_keyword_high_confidence_not_flagged(self):
        cls = NewsClassifier(voyage=None)
        meta = cls.classify_with_metadata(_item("Fed raises inflation target"))
        assert meta.flagged_for_llm is False


class TestCosineSimilarity:
    """Unit tests for the cosine similarity helper."""

    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)


class TestKalshiCategories:
    """Only Kalshi-relevant categories are used."""

    def test_no_sports_in_kalshi_categories(self):
        assert NewsCategory.SPORTS not in _KALSHI_CATEGORIES

    def test_crypto_in_market_category(self):
        from traderbot.kalshi.models import MarketCategory
        assert "crypto" in {c.value for c in MarketCategory}

    def test_five_kalshi_categories(self):
        assert len(_KALSHI_CATEGORIES) == 5

    def test_all_five_present(self):
        expected = {
            NewsCategory.ECONOMICS,
            NewsCategory.POLITICS,
            NewsCategory.WEATHER,
            NewsCategory.ENTERTAINMENT,
            NewsCategory.SCIENCE_AND_TECHNOLOGY,
        }
        assert set(_KALSHI_CATEGORIES) == expected


class TestClassificationResult:
    """ClassificationResult Pydantic model."""

    def test_model_config_strict(self):
        result = ClassificationResult(
            category=NewsCategory.ECONOMICS,
            confidence=0.9,
            method="keyword",
        )
        assert result.category == NewsCategory.ECONOMICS

    def test_model_config_forbids_extra(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                category=NewsCategory.ECONOMICS,
                confidence=0.9,
                method="keyword",
                unknown_field="bad",
            )

    def test_flagged_for_llm_default(self):
        result = ClassificationResult(
            category=NewsCategory.ECONOMICS,
            confidence=0.3,
            method="keyword",
        )
        assert result.flagged_for_llm is False


class TestClassifiedNewsOutput:
    """Classify returns ClassifiedNews with correct structure."""

    def test_classify_returns_classified_news(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Fed raises rates"))
        assert isinstance(result, ClassifiedNews)
        assert isinstance(result.category, NewsCategory)
        assert result.category == NewsCategory.ECONOMICS

    def test_classify_preserves_news_item(self):
        cls = NewsClassifier()
        item = _item("Hurricane warning issued")
        result = cls.classify(item)
        assert result.news_item.id == item.id
        assert result.news_item.url == item.url


class TestCaseInsensitive:
    """Keywords match regardless of case."""

    def test_uppercase_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("FED ANNOUNCES RATE DECISION"))
        assert result.category == NewsCategory.ECONOMICS

    def test_mixed_case_keyword(self):
        cls = NewsClassifier()
        result = cls.classify(_item("Nasa Space Discovery"))
        assert result.category == NewsCategory.SCIENCE_AND_TECHNOLOGY


class TestMultiwordKeywords:
    """Multi-word keywords like 'supreme court' and 'white house'."""

    def test_supreme_court(self):
        cls = NewsClassifier()
        meta = cls.classify_with_metadata(_item("Supreme court ruling expected"))
        assert meta.category == NewsCategory.POLITICS
        assert meta.method == _KEYWORD

    def test_white_house(self):
        cls = NewsClassifier()
        meta = cls.classify_with_metadata(_item("White house press briefing"))
        assert meta.category == NewsCategory.POLITICS

    def test_box_office(self):
        cls = NewsClassifier()
        meta = cls.classify_with_metadata(_item("Box office results this weekend"))
        assert meta.category == NewsCategory.ENTERTAINMENT
