"""Offline news ingestion — fetch, embed, store, and retrieve accumulated news.

No LLM required. Runs as a pure data pipeline.
"""
import hashlib
import logging
import time
from datetime import datetime

from traderbot.db.vectors import VectorStore
from traderbot.news.classifier import NewsClassifier
from traderbot.news.embeddings import VoyageClient
from traderbot.news.impact_assessor import ImpactAssessor
from traderbot.news.models import DataPoint, NewsItem
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.news.sources import NewsAggregator

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────

_DEFAULT_INGEST_LIMIT = 50
_DEFAULT_SUMMARY_LIMIT = 30
_NEWS_COLLECTION = "news"
_NEWS_SIGNALS_COLLECTION = "news_signals"
_DATA_COLLECTION = "data_points"

# ── Public types ─────────────────────────────────────────────────────────


class IngestReport:
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
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _build_metadata(
    item: NewsItem,
    sentiment: object | None,
    impact: object | None,
    category_str: str,
) -> dict[str, str | float]:
    """Build ChromaDB metadata dict from a news item and its enrichments."""
    meta: dict[str, str | float] = {
        "source": str(item.source.value) if hasattr(item.source, "value") else str(item.source),
        "category": category_str,
        "published": item.published_at.isoformat() if item.published_at else "",
        "published_epoch": item.published_at.timestamp() if item.published_at else 0.0,
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


def _build_datapoint_metadata(dp: DataPoint) -> dict[str, str | float]:
    meta: dict[str, str | float] = {
        "source": str(dp.source.value) if hasattr(dp.source, "value") else str(dp.source),
        "category": dp.category.value if dp.category else "",
        "timestamp": dp.timestamp.isoformat() if dp.timestamp else "",
        "timestamp_epoch": dp.timestamp.timestamp() if dp.timestamp else 0.0,
        "ticker_refs": ",".join(dp.ticker_refs) if dp.ticker_refs else "",
    }
    for key, value in dp.data.items():
        if isinstance(value, (str, int, float, bool)):
            meta[f"data_{key}"] = str(value)
    for key, value in dp.metadata.items():
        if isinstance(value, (str, int, float, bool)):
            meta[f"meta_{key}"] = str(value)
    return meta


def _store_datapoints(
    dp_items: list[DataPoint],
    vs: VectorStore,
    voyage: VoyageClient | None = None,
    use_voyage_storage: bool = False,
) -> int:
    if not dp_items:
        return 0

    texts: list[str] = []
    metadatas: list[dict[str, str | float]] = []
    for dp in dp_items:
        texts.append(dp.title or f"{dp.source.value}: {dp.timestamp.isoformat()}")
        metadatas.append(_build_datapoint_metadata(dp))

    embeddings: list[list[float]] | None = None
    if use_voyage_storage and voyage is not None:
        try:
            embeddings = voyage.embed_batch(texts)
        except Exception as exc:
            logger.warning("Voyage batch embed failed for data_points: %s", exc)

    stored = 0
    for i, dp in enumerate(dp_items):
        doc_id = f"datapoint-{dp.source.value}-{dp.id}"
        try:
            vs.add_document(
                doc_id=doc_id,
                text=texts[i],
                metadata=metadatas[i],
                embedding=embeddings[i] if embeddings else None,
                collection=_DATA_COLLECTION,
            )
            stored += 1
        except Exception:
            logger.warning("Failed to store data point %s, skipping", doc_id)
            continue
    return stored


def _is_signal(
    sentiment: object | None,
    impact: object | None,
) -> bool:
    if impact is not None:
        try:
            mag = getattr(impact, "magnitude", 0) or 0
            conf = getattr(impact, "confidence", 0) or 0
            if float(mag) >= 0.7 and float(conf) >= 0.5:
                return True
        except (ValueError, TypeError):
            pass
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
    parts = [item.title or ""]
    if item.body:
        parts.append(item.body)
    return " — ".join(parts)


# ── Public API ───────────────────────────────────────────────────────────


def _collection_dim(vs: VectorStore, name: str) -> int:
    """Collection embedding dimension, or 0 if collection doesn't exist or is empty."""
    try:
        col = vs.get_collection(name)
        count = col.count()
        if count > 0:
            sample = col.get(limit=1, include=["embeddings"])
            embs = sample.get("embeddings")
            if embs is not None and len(embs) > 0:
                emb = embs[0]
                if emb is not None:
                    return len(emb) if not hasattr(emb, "shape") else emb.shape[0]
        return 0
    except Exception:
        return 0


def ingest_news(
    limit: int = _DEFAULT_INGEST_LIMIT,
    max_age_hours: int = 72,
    profile_name: str | None = None,
    vector_store: VectorStore | None = None,
    newsapi_key: str | None = None,
    openweather_key: str | None = None,
    fred_key: str | None = None,
) -> IngestReport:
    """Fetch news from all sources, classify, embed, and store in ChromaDB.

    No LLM required. Gracefully degrades when VoyageAI key is missing.
    Accepts optional API keys; falls back to env vars.
    Returns an IngestReport with counts.
    """
    report = IngestReport()
    start = time.monotonic()

    import os as _os
    from traderbot.news.sources import DataSourcesConfig

    resolved_newsapi = newsapi_key or _os.environ.get("NEWSAPI_API_KEY")
    resolved_ow = openweather_key or _os.environ.get("OPENWEATHER_API_KEY")
    resolved_fred = fred_key or _os.environ.get("FRED_API_KEY")

    ds_config = DataSourcesConfig(
        newsapi_key=resolved_newsapi,
        openweather_key=resolved_ow,
        fred_key=resolved_fred,
    )
    vs = vector_store or VectorStore()

    vs.init_collections()

    try:
        news_col = vs.get_collection(_NEWS_COLLECTION)
        sig_col = vs.get_collection(_NEWS_SIGNALS_COLLECTION)
        report.collection_sizes["news"] = news_col.count()
        report.collection_sizes["news_signals"] = sig_col.count()
    except Exception:
        pass

    news_dim = _collection_dim(vs, _NEWS_COLLECTION)
    sig_dim = _collection_dim(vs, _NEWS_SIGNALS_COLLECTION)
    dp_dim = _collection_dim(vs, _DATA_COLLECTION)
    existing_dim = news_dim or sig_dim or 0
    use_voyage_storage = existing_dim == 0 or existing_dim == 1024
    use_voyage_dp = dp_dim == 0 or dp_dim == 1024

    aggregator = NewsAggregator(config=ds_config)
    classifier = NewsClassifier()
    scorer = SentimentScorer()
    assessor = ImpactAssessor()
    voyage = VoyageClient()

    try:
        import asyncio

        raw_items = asyncio.run(aggregator.fetch_all(limit=limit + 200))
    except Exception as exc:
        logger.error("fetch_all failed: %s", exc)
        report.errors += 1
        report.elapsed_seconds = time.monotonic() - start
        return report

    if not raw_items:
        report.elapsed_seconds = time.monotonic() - start
        return report

    data_points: list[DataPoint] = [it for it in raw_items if isinstance(it, DataPoint)]
    news_items: list[NewsItem] = [it for it in raw_items if isinstance(it, NewsItem)]

    if data_points:
        dp_stored = _store_datapoints(
            data_points, vs, voyage=voyage, use_voyage_storage=use_voyage_dp
        )
        report.skipped = len(raw_items) - len(news_items) - dp_stored

    if not news_items:
        report.collection_sizes[_DATA_COLLECTION] = vs.get_collection(_DATA_COLLECTION).count()
        report.elapsed_seconds = time.monotonic() - start
        return report

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
        impact = assessor.assess(
            news_item=item,
            classified_news=classified,
            sentiment_result=sentiment,
        )

        batch_texts.append(text)
        batch_items.append(item)
        batch_classified.append(classified)
        batch_sentiments.append(sentiment)
        batch_impacts.append(impact)

    # Embed in batch — use Voyage for new/1024-dim collections,
    # let ChromaDB auto-embed for legacy 384-dim collections
    embeddings: list[list[float]] | None = None
    if use_voyage_storage:
        try:
            embeddings = voyage.embed_batch(batch_texts)
        except Exception as exc:
            logger.warning("Voyage batch embed failed — storing without embeddings: %s", exc)
    else:
        logger.info(
            "Legacy 384-dim collection — ChromaDB auto-embedding with all-MiniLM-L6-v2"
        )

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
        report.collection_sizes[_DATA_COLLECTION] = vs.get_collection(_DATA_COLLECTION).count()
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
    where_clause: dict[str, dict[str, str | float] | list[dict]] | None = None
    conditions: list[dict[str, dict[str, str | float]]] = []
    if category:
        conditions.append({"category": {"$eq": category}})
    if source:
        conditions.append({"source": {"$eq": source}})
    if since:
        conditions.append({"published_epoch": {"$gte": since.timestamp()}})
    if len(conditions) == 1:
        where_clause = conditions[0]
    elif len(conditions) > 1:
        where_clause = {"$and": conditions}

    col_dim = _collection_dim(vs, collection_name)

    # If semantic query, try Voyage embed
    query_embedding: list[float] | None = None
    if query and col_dim == 1024:
        try:
            voyage = VoyageClient()
            query_embedding = voyage.embed(query, model="voyage-4-large")
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
            results = vs.search(
                [0.0] * col_dim,
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
    vs = vector_store or VectorStore()
    stats: dict[str, int] = {}
    for name in (_NEWS_COLLECTION, _NEWS_SIGNALS_COLLECTION):
        try:
            col = vs.get_collection(name)
            stats[name] = col.count()
        except Exception:
            stats[name] = 0
    return stats
