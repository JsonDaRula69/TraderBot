"""Hybrid Kalshi category classifier — keyword fast path, Voyage semantic slow path."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict

from traderbot.news.embeddings import VoyageClient
from traderbot.news.models import ClassifiedNews, NewsCategory, NewsItem

# ── Confidence thresholds ───────────────────────────────────────────────
_CONFIDENCE_HIGH = 0.8
_CONFIDENCE_RERANK_LOW = 0.5
_CONFIDENCE_RERANK_HIGH = 0.7

# ── Classification method tags ──────────────────────────────────────────
_KEYWORD = "keyword"
_EMBED = "voyage_embed"
_RERANK = "voyage_rerank"
_AGENT_LLM = "agent_llm_flagged"


class ClassificationResult(BaseModel):
    """Internal classification result with method and confidence metadata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: NewsCategory
    confidence: float
    method: str
    flagged_for_llm: bool = False


# ── Keyword maps ────────────────────────────────────────────────────────
# Each keyword maps to a set of candidate categories. Unique → high confidence.
# Multiple matches → ambiguous → Voyage path.

_KEYWORD_CATEGORIES: dict[str, set[NewsCategory]] = {
    # Economics
    "fed": {NewsCategory.ECONOMICS},
    "inflation": {NewsCategory.ECONOMICS},
    "gdp": {NewsCategory.ECONOMICS},
    "unemployment": {NewsCategory.ECONOMICS},
    "jobs": {NewsCategory.ECONOMICS},
    "rate": {NewsCategory.ECONOMICS},
    "treasury": {NewsCategory.ECONOMICS},
    "interest": {NewsCategory.ECONOMICS},
    "cpi": {NewsCategory.ECONOMICS},
    "fomc": {NewsCategory.ECONOMICS},
    "recession": {NewsCategory.ECONOMICS},
    "fiscal": {NewsCategory.ECONOMICS},
    # Politics
    "election": {NewsCategory.POLITICS},
    "senate": {NewsCategory.POLITICS},
    "congress": {NewsCategory.POLITICS},
    "president": {NewsCategory.POLITICS},
    "bill": {NewsCategory.POLITICS},
    "law": {NewsCategory.POLITICS},
    "vote": {NewsCategory.POLITICS},
    "legislation": {NewsCategory.POLITICS},
    "governor": {NewsCategory.POLITICS},
    "supreme court": {NewsCategory.POLITICS},
    "white house": {NewsCategory.POLITICS},
    # Weather
    "hurricane": {NewsCategory.WEATHER},
    "tornado": {NewsCategory.WEATHER},
    "storm": {NewsCategory.WEATHER},
    "drought": {NewsCategory.WEATHER},
    "flood": {NewsCategory.WEATHER},
    "temperature": {NewsCategory.WEATHER},
    "blizzard": {NewsCategory.WEATHER},
    "cyclone": {NewsCategory.WEATHER},
    "monsoon": {NewsCategory.WEATHER},
    "wildfire": {NewsCategory.WEATHER},
    # Culture
    "oscar": {NewsCategory.CULTURE},
    "grammy": {NewsCategory.CULTURE},
    "movie": {NewsCategory.CULTURE},
    "music": {NewsCategory.CULTURE},
    "entertainment": {NewsCategory.CULTURE},
    "emmy": {NewsCategory.CULTURE},
    "box office": {NewsCategory.CULTURE},
    "celebrity": {NewsCategory.CULTURE},
    "album": {NewsCategory.CULTURE},
    # Technology
    "ai": {NewsCategory.TECH},
    "tech": {NewsCategory.TECH},
    "software": {NewsCategory.TECH},
    "chip": {NewsCategory.TECH},
    "semiconductor": {NewsCategory.TECH},
    "cyber": {NewsCategory.TECH},
    "startup": {NewsCategory.TECH},
    "app": {NewsCategory.TECH},
    "algorithm": {NewsCategory.TECH},
    # Science
    "nasa": {NewsCategory.SCIENCE},
    "space": {NewsCategory.SCIENCE},
    "research": {NewsCategory.SCIENCE},
    "discovery": {NewsCategory.SCIENCE},
    "experiment": {NewsCategory.SCIENCE},
    "laboratory": {NewsCategory.SCIENCE},
    "quantum": {NewsCategory.SCIENCE},
    "genome": {NewsCategory.SCIENCE},
}

# Kalshi-relevant categories only (no SPORTS, no CRYPTO per spec)
_KALSHI_CATEGORIES: list[NewsCategory] = [
    NewsCategory.ECONOMICS,
    NewsCategory.POLITICS,
    NewsCategory.WEATHER,
    NewsCategory.CULTURE,
    NewsCategory.TECH,
    NewsCategory.SCIENCE,
]

# Canonical descriptions for embedding similarity
_CATEGORY_DESCRIPTIONS: dict[NewsCategory, str] = {
    NewsCategory.ECONOMICS: (
        "Economics and financial markets: Federal Reserve, inflation, GDP, unemployment, "
        "interest rates, monetary policy, fiscal policy, treasury bonds, recession, CPI."
    ),
    NewsCategory.POLITICS: (
        "Politics and government: elections, senate, congress, legislation, presidential "
        "policy, voting, supreme court decisions, political campaigns, governance."
    ),
    NewsCategory.WEATHER: (
        "Weather and natural disasters: hurricanes, tornadoes, storms, floods, droughts, "
        "extreme temperatures, blizzards, cyclones, wildfires, monsoons."
    ),
    NewsCategory.CULTURE: (
        "Culture and entertainment: Academy Awards, Grammy Awards, movies, music, "
        "celebrity news, television, Emmy Awards, box office, albums, pop culture."
    ),
    NewsCategory.TECH: (
        "Technology and computing: artificial intelligence, software, semiconductors, "
        "cybersecurity, startups, apps, algorithms, chips, tech companies, innovation."
    ),
    NewsCategory.SCIENCE: (
        "Science and space: NASA missions, space exploration, scientific research, "
        "discoveries, experiments, quantum physics, genomics, laboratory findings."
    ),
}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class NewsClassifier:
    """Hybrid Kalshi category classifier.

    Pipeline: keyword → Voyage embed → Voyage rerank → flag for Agent LLM.

    Keyword fast path: decisive unique match → high confidence (>0.8).
    Ambiguous: multiple keyword matches or no match → Voyage embedding similarity.
    Rerank: if similarity in 0.5-0.7 → Voyage reranker for disambiguation.
    Agent LLM: if confidence <0.5 → flag for future LLM (not implemented).
    Graceful degradation: keyword-only when Voyage unavailable.
    """

    def __init__(self, voyage: VoyageClient | None = None) -> None:
        self._voyage = voyage
        self._category_embeddings: dict[NewsCategory, list[float]] | None = None

    def _keyword_match(self, text: str) -> tuple[set[NewsCategory], int]:
        """Match keywords against text using word boundaries to avoid substring false positives."""
        text_lower = text.lower()
        matched: set[NewsCategory] = set()
        hits = 0
        for keyword, categories in _KEYWORD_CATEGORIES.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                matched.update(categories)
                hits += 1
        return matched, hits

    def _keyword_cat_hits(self, text: str) -> dict[NewsCategory, int]:
        """Count keyword hits per category using word-boundary matching."""
        text_lower = text.lower()
        cat_hits: dict[NewsCategory, int] = {}
        for keyword, categories in _KEYWORD_CATEGORIES.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                for cat in categories:
                    if cat in _KALSHI_CATEGORIES:
                        cat_hits[cat] = cat_hits.get(cat, 0) + 1
        return cat_hits

    def _keyword_classify(self, text: str) -> ClassificationResult | None:
        """Fast path: keyword matching. Returns None if ambiguous or no match."""
        matched, hits = self._keyword_match(text)

        if not matched:
            return None

        # Decisive: all hits point to exactly one category → high confidence
        if len(matched) == 1:
            category = next(iter(matched))
            # More keyword hits → higher confidence (capped at 0.95)
            confidence = min(0.82 + 0.04 * (hits - 1), 0.95)
            return ClassificationResult(
                category=category,
                confidence=confidence,
                method=_KEYWORD,
            )

        # Multiple categories matched → ambiguous, let Voyage decide
        return None

    def _embed_classify(self, text: str) -> ClassificationResult | None:
        """Semantic path: embed text + category descriptions → cosine similarity."""
        if self._voyage is None:
            return None

        text_embedding = self._voyage.embed(text)
        if text_embedding is None:
            return None

        # Lazy-init category embeddings
        if self._category_embeddings is None:
            self._category_embeddings = {}
            for cat in _KALSHI_CATEGORIES:
                desc = _CATEGORY_DESCRIPTIONS[cat]
                emb = self._voyage.embed(desc)
                if emb is None:
                    # Can't build category embeddings — degrade
                    self._category_embeddings = None
                    return None
                self._category_embeddings[cat] = emb

        # Compute similarities
        best_cat: NewsCategory | None = None
        best_sim: float = -1.0
        second_sim: float = -1.0

        for cat, cat_emb in self._category_embeddings.items():
            sim = _cosine_similarity(text_embedding, cat_emb)
            if sim > best_sim:
                second_sim = best_sim
                best_sim = sim
                best_cat = cat
            elif sim > second_sim:
                second_sim = sim

        if best_cat is None or best_sim <= 0.0:
            return None

        # Confidence = similarity scaled, but consider margin over 2nd place
        margin = best_sim - second_sim if second_sim > 0 else best_sim
        confidence = min(best_sim, 1.0) * (0.5 + 0.5 * min(margin / 0.3, 1.0))

        return ClassificationResult(
            category=best_cat,
            confidence=round(confidence, 4),
            method=_EMBED,
        )

    def _rerank_classify(self, text: str) -> ClassificationResult | None:
        """Reranker path: use Voyage rerank to disambiguate ambiguous categories."""
        if self._voyage is None:
            return None

        documents = [_CATEGORY_DESCRIPTIONS[cat] for cat in _KALSHI_CATEGORIES]
        results = self._voyage.rerank(
            query=text,
            documents=documents,
            top_k=2,
        )

        if results is None or len(results) < 2:
            return None

        top_idx, top_score = results[0]
        _, second_score = results[1]

        # Reranker relevance_score is already a confidence-like metric
        margin = top_score - second_score
        confidence = min(top_score, 1.0) * (0.5 + 0.5 * min(margin / 0.2, 1.0))

        category = _KALSHI_CATEGORIES[top_idx]

        return ClassificationResult(
            category=category,
            confidence=round(confidence, 4),
            method=_RERANK,
        )

    def classify(self, news_item: NewsItem) -> ClassifiedNews:
        """Classify a news item into a Kalshi market category.

        Pipeline:
        1. Keyword fast path — decisive match → return with high confidence
        2. Voyage embed — ambiguous or no keyword match → cosine similarity
        3. Voyage rerank — if embed confidence in 0.5-0.7 → disambiguate
        4. Agent LLM flag — if confidence <0.5 → flag for future processing
        """
        text = f"{news_item.title} {news_item.body}"

        # Step 1: Keyword fast path
        kw_result = self._keyword_classify(text)
        if kw_result is not None:
            return ClassifiedNews(
                news_item=news_item,
                category=kw_result.category,
            )

        # Step 2: Voyage embedding
        emb_result = self._embed_classify(text)
        if emb_result is not None and emb_result.confidence >= _CONFIDENCE_RERANK_HIGH:
            # High enough confidence from embedding — done
            return ClassifiedNews(
                news_item=news_item,
                category=emb_result.category,
            )

        if emb_result is not None and _CONFIDENCE_RERANK_LOW <= emb_result.confidence < _CONFIDENCE_RERANK_HIGH:
            # Step 3: Use reranker for disambiguation
            rr_result = self._rerank_classify(text)
            if rr_result is not None:
                return ClassifiedNews(
                    news_item=news_item,
                    category=rr_result.category,
                )
            # Rerank failed — use embed result as-is
            return ClassifiedNews(
                news_item=news_item,
                category=emb_result.category,
            )

        # Step 4: Low confidence or no Voyage — best guess + flag for LLM
        if emb_result is not None:
            # Embed gave something but confidence <0.5
            return ClassifiedNews(
                news_item=news_item,
                category=emb_result.category,
            )

        # No Voyage available at all — keyword-only fallback
        cat_hits = self._keyword_cat_hits(text)
        if cat_hits:
            best_cat = max(cat_hits, key=lambda c: cat_hits[c])
            confidence = min(0.3 + 0.05 * cat_hits[best_cat], 0.45)
            return ClassifiedNews(
                news_item=news_item,
                category=best_cat,
            )

        # No matches at all — default to Economics with very low confidence
        return ClassifiedNews(
            news_item=news_item,
            category=NewsCategory.ECONOMICS,
        )

    def classify_with_metadata(self, news_item: NewsItem) -> ClassificationResult:
        """Classify and return full metadata including method and confidence.

        Useful for debugging and audit trails.
        """
        text = f"{news_item.title} {news_item.body}"

        # Step 1: Keyword fast path
        kw_result = self._keyword_classify(text)
        if kw_result is not None:
            return kw_result

        # Step 2: Voyage embedding
        emb_result = self._embed_classify(text)
        if emb_result is not None and emb_result.confidence >= _CONFIDENCE_RERANK_HIGH:
            return emb_result

        if emb_result is not None and _CONFIDENCE_RERANK_LOW <= emb_result.confidence < _CONFIDENCE_RERANK_HIGH:
            # Step 3: Reranker
            rr_result = self._rerank_classify(text)
            if rr_result is not None:
                return rr_result
            return emb_result

        # Step 4: Low confidence → flag for Agent LLM
        if emb_result is not None:
            emb_result.flagged_for_llm = True
            return emb_result

        # Keyword-only fallback (ambiguous)
        cat_hits = self._keyword_cat_hits(text)
        if cat_hits:
            best_cat = max(cat_hits, key=lambda c: cat_hits[c])
            confidence = min(0.3 + 0.05 * cat_hits[best_cat], 0.45)
            return ClassificationResult(
                category=best_cat,
                confidence=confidence,
                method=_KEYWORD,
                flagged_for_llm=True,
            )

        # No matches — default to Economics
        return ClassificationResult(
            category=NewsCategory.ECONOMICS,
            confidence=0.1,
            method="default_fallback",
            flagged_for_llm=True,
        )