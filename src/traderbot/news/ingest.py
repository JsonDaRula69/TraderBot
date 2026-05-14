"""Offline news ingestion — fetch, embed, store, and retrieve accumulated news.

No LLM required. Runs as a pure data pipeline.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from traderbot.db.vectors import VectorStore
from traderbot.news.classifier import NewsClassifier
from traderbot.news.embeddings import VoyageClient
from traderbot.news.impact_assessor import ImpactAssessor
from traderbot.news.models import NewsItem
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.news.sources import NewsAggregator

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────

_DEFAULT_INGEST_LIMIT = 50
_DEFAULT_SUMMARY_LIMIT = 30
_NEWS_COLLECTION = "news"
_NEWS_SIGNALS_COLLECTION = "news_signals"
_EMBED_DIMENSION = 1024

# ── Public types ─────────────────────────────────────────────────────────


class IngestReport:
    """Result of a single ingest run."""

    def __init__(self) -> None:
        self.new: int = 0
        self.duplicates: int = 0
        self.skipped: int = 0
        self.signals: int = 0
        self.errors: int = 0
        self.elapsed_seconds: float = 0.0
        self.collection_sizes: dict[str, int] = {}

    def to_dict(self) -> dict[str, object]:
        return {
            "new": self.new,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "signals": self.signals,
            "errors": self.errors,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "collection_sizes": self.collection_sizes,
        }


class NewsSummaryItem:
    """A single news item from the accumulated store, ready for agent consumption."""

    def __init__(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, str],
        distance: float | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.text = text
        self.metadata = metadata
        self.distance = distance

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "id": self.doc_id,
            "text": self.text,
            "source": self.metadata.get("source", ""),
            "category": self.metadata.get("category", ""),
            "published": self.metadata.get("published", ""),
            "title": self.metadata.get("title", ""),
            "sentiment_score": self.metadata.get("sentiment_score", ""),
            "sentiment_label": self.metadata.get("sentiment_label", ""),
            "impact_magnitude": self.metadata.get("impact_magnitude", ""),
            "impact_direction": self.metadata.get("impact_direction", ""),
            "url_hash": self.metadata.get("url_hash", ""),
        }
        if self.distance is not None:
            d["relevance"] = round(1.0 - self.distance, 4)
        return d


# ── Core ingester ────────────────────────────────────────────────────────


def _url_hash(url: str) -> str:
    """Deterministic hash for deduplication."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _build_metadata(
    item: NewsItem,
    sentiment: object | None,
    impact: object | None,
    category_str: str,
) -> dict[str, str]:
    """Build ChromaDB metadata dict from a news item and its enrichments."""
    meta: dict[str, str] = {
        "source": str(item.source.value) if hasattr(item.source, "value") else str(item.source),
        "category": category_str,
        "published": item.published.isoformat() if item.published else "",
        "title": item.title[:200] if item.title else "",
        "url_hash": _url_hash(item.url) if item.url else "",
    }
    # Add sentiment if available
    if sentiment is not None:
        try:
            if hasattr(sentiment, "score"):
                meta["sentiment_score"] = str(sentiment.score)
            if hasattr(sentiment, "label"):
                meta["sentiment_label"] = str(sentiment.label)
        except Exception:
            pass
    # Add impact if available
    if impact is not None:
        try:
            if hasattr(impact, "magnitude"):
                meta["impact_magnitude"] = str(impact.magnitude)
            if hasattr(impact, "direction"):
                meta["impact_direction"] = str(impact.direction)
            if hasattr(impact, "timeframe"):
                meta["impact_timeframe"] = str(impact.timeframe)
            if hasattr(impact, "confidence"):
                meta["impact_confidence"] = str(impact.confidence)
        except Exception:
            pass
    return meta


def _is_signal(
    sentiment: object | None,
    impact: object | None,
) -> bool:
    """Decide if a news item qualifies as a signal."""
    # High-impact events
    if impact is not None:
        try:
            mag = getattr(impact, "magnitude", 0) or 0
            conf = getattr(impact, "confidence", 0) or 0
            if float(mag) >= 0.7 and float(conf) >= 0.5:
                return True
        except (ValueError, TypeError):
            pass
    # Extreme sentiment
    if sentiment is not None:
        try:
            score = getattr(sentiment, "score", 0) or 0
            score_f = float(score)
            if abs(score_f) >= 0.8:
                return True
        except (ValueError, TypeError):
            pass
    return False


def _flatten_text(item: NewsItem) -> str:
    """Build a single text block for embedding."""
    parts = [item.title or ""]
    if item.body:
        parts.append(item.body)
    if item.summary:
        parts.append(item.summary)
    return " — ".join(parts)


# ── Public API ───────────────────────────────────────────────────────────


def ingest_news(
    limit: int = _DEFAULT_INGEST_LIMIT,
    max_age_hours: int = 72,
    profile_name: str | None = None,
    vector_store: VectorStore | None = None,
) -> IngestReport:
    """Fetch news from all sources, classify, embed, and store in ChromaDB.

    No LLM required. Gracefully degrades when VoyageAI key is missing.
    Returns an IngestReport with counts.
    """
    report = IngestReport()
    start = time.monotonic()
    vs = vector_store or VectorStore()

    # Ensure collections exist
    vs.init_collections()

    # Count existing docs for reporting
    try:
        news_col = vs.get_collection(_NEWS_COLLECTION)
        sig_col = vs.get_collection(_NEWS_SIGNALS_COLLECTION)
        report.collection_sizes["news"] = news_col.count()
        report.collection_sizes["news_signals"] = sig_col.count()
    except Exception:
        pass

    # Resolve profile for env vars (api keys, sources config)
    profile = get_current_profile() if profile_name is None else None  # noqa: F841

    # Build aggregator, classifier, scorer, assessor
    aggregator = NewsAggregator()
    classifier = NewsClassifier()
    scorer = SentimentScorer()
    assessor = ImpactAssessor()
    voyage = VoyageClient()

    # Fetch news
    try:
        import asyncio

        raw_items = asyncio.run(aggregator.fetch_all(limit=limit))
    except Exception as exc:
        logger.error("fetch_all failed: %s", exc)
        report.errors += 1
        report.elapsed_seconds = time.monotonic() - start
        return report

    if not raw_items:
        report.elapsed_seconds = time.monotonic() - start
        return report

    # Filter for NewsItem instances only (skip DataPoint)
    news_items: list[NewsItem] = [it for it in raw_items if isinstance(it, NewsItem)]
    report.skipped = len(raw_items) - len(news_items)

    # Collect batch embedding texts
    batch_texts: list[str] = []
    batch_items: list[NewsItem] = []
    batch_classified: list[object] = []
    batch_sentiments: list[object | None] = []
    batch_impacts: list[object | None] = []

    for item in news_items:
        classified = classifier.classify(item)
        if classified is None:
            report.skipped += 1
            continue
        category_str = classified.category.value if hasattr(classified.category, "value") else str(classified.category)
        text = _flatten_text(item)
        sentiment = scorer.score(text, item.source, item.id)
        impact = assessor.assess(text, category=category_str)

        batch_texts.append(text)
        batch_items.append(item)
        batch_classified.append(classified)
        batch_sentiments.append(sentiment)
        batch_impacts.append(impact)

    # Embed in batch (graceful if Voyage key missing)
    embeddings: list[list[float]] | None = None
    try:
        embeddings = voyage.embed_batch(batch_texts)
    except Exception as exc:
        logger.warning("Voyage batch embed failed — storing without embeddings: %s", exc)

    # Store each item
    for i, item in enumerate(batch_items):
        classified = batch_classified[i]
        category_str = (
            classified.category.value if hasattr(classified.category, "value") else str(classified.category)  # type: ignore[union-attr]
        )
        sentiment = batch_sentiments[i]
        impact = batch_impacts[i]
        url = item.url or item.id

        doc_id = _url_hash(url)
        text = batch_texts[i]
        metadata = _build_metadata(item, sentiment, impact, category_str)
        embedding = embeddings[i] if embeddings else None

        try:
            vs.add_document(
                doc_id=doc_id,
                text=text,
                metadata=metadata,
                embedding=embedding,
                collection=_NEWS_COLLECTION,
            )
            report.new += 1

            # Store signal items in a separate collection for fast lookup
            if _is_signal(sentiment, impact):
                sig_meta = dict(metadata)
                sig_meta["signal_type"] = "impact" if (impact and getattr(impact, "magnitude", 0) and float(getattr(impact, "magnitude", 0)) >= 0.7) else "sentiment"  # type: ignore[arg-type]
                vs.add_document(
                    doc_id=f"sig-{doc_id}",
                    text=text,
                    metadata=sig_meta,
                    embedding=embedding,
                    collection=_NEWS_SIGNALS_COLLECTION,
                )
                report.signals += 1
        except Exception as exc:
            logger.error("Failed to store item %s: %s", doc_id, exc)
            report.errors += 1

    report.elapsed_seconds = time.monotonic() - start
    try:
        report.collection_sizes["news"] = news_col.count()
        report.collection_sizes["news_signals"] = sig_col.count()
    except Exception:
        pass

    return report


def get_news_summary(
    *,
    since: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
    limit: int = _DEFAULT_SUMMARY_LIMIT,
    query: str | None = None,
    signal_only: bool = False,
    vector_store: VectorStore | None = None,
) -> list[NewsSummaryItem]:
    """Retrieve accumulated news from ChromaDB.

    Supports:
    - Time-range filtering (``since``)
    - Category / source filtering (metadata ``where`` clause)
    - Semantic search via Voyage embedding of ``query``
    - Signal-only: only return items from the ``news_signals`` collection

    Falls back to text-based search when no embedding is available.
    """
    vs = vector_store or VectorStore()
    collection_name = _NEWS_SIGNALS_COLLECTION if signal_only else _NEWS_COLLECTION

    try:
        col = vs.get_collection(collection_name)
    except Exception as exc:
        logger.warning("Cannot access collection '%s': %s", collection_name, exc)
        return []

    # Build metadata filter
    where_clause: dict[str, dict[str, str]] | None = None
    filters: dict[str, str] = {}
    if category:
        filters["category"] = category
    if source:
        filters["source"] = source
    if since:
        filters["published"] = since.isoformat()  # ChromaDB won't do range on strings — handled post-filter
    if filters:
        # ChromaDB filter format: {"$and": [{"field": {"$eq": "val"}}, ...]}
        conditions: list[dict[str, dict[str, str]]] = []
        for field, val in filters.items():
            conditions.append({field: {"$eq": val}})
        where_clause = {"$and": conditions} if len(conditions) > 1 else conditions[0]

    # If semantic query, try Voyage embed
    query_embedding: list[float] | None = None
    if query:
        try:
            voyage = VoyageClient()
            query_embedding = voyage.embed(query, model="voyage-finance-2")
        except Exception as exc:
            logger.warning("Voyage embed for summary query failed: %s", exc)
            query_embedding = None

    # Search
    try:
        if query_embedding:
            results = vs.search(
                query_embedding,
                n=limit,
                filter_metadata=where_clause,
                collection=collection_name,
            )
        else:
            # Fallback: use ChromaDB's ability to return all with filter
            # ChromaDB requires an embedding even for filtered "dumb" search.
            # Use zero vector as placeholder.
            zero_embed = [0.0] * _EMBED_DIMENSION
            results = vs.search(
                zero_embed,
                n=limit,
                filter_metadata=where_clause,
                collection=collection_name,
            )
    except Exception as exc:
        logger.warning("ChromaDB search failed: %s", exc)
        return []

    items: list[NewsSummaryItem] = []
    for doc_id, text, metadata, distance in results:
        items.append(NewsSummaryItem(doc_id, text, metadata, distance))

    # Post-filter for time range (ChromaDB doesn't support date comparisons natively)
    if since:
        filtered: list[NewsSummaryItem] = []
        for item in items:
            pub_str = item.metadata.get("published", "")
            if pub_str:
                try:
                    pub_dt = datetime.fromisoformat(pub_str)
                    if pub_dt >= since:
                        filtered.append(item)
                except (ValueError, TypeError):
                    filtered.append(item)  # can't parse, include anyway
            else:
                filtered.append(item)
        items = filtered[:limit]

    # Sort by published time descending (most recent first)
    items.sort(key=lambda x: x.metadata.get("published", ""), reverse=True)

    return items


def get_news_collection_stats(vector_store: VectorStore | None = None) -> dict[str, int]:
    """Return item counts per collection."""
    vs = vector_store or VectorStore()
    stats: dict[str, int] = {}
    for name in (_NEWS_COLLECTION, _NEWS_SIGNALS_COLLECTION):
        try:
            col = vs.get_collection(name)
            stats[name] = col.count()
        except Exception:
            stats[name] = 0
    return stats
