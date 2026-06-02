"""Offline news ingestion — fetch, embed, store, and retrieve accumulated news.

No LLM required. Runs as a pure data pipeline.
"""
import hashlib
import logging
import time
from datetime import UTC, datetime

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
    if use_voyage_storage:
        if voyage is None:
            logger.error("Cannot store data_points — collection needs Voyage embeddings but no VoyageClient provided")
            return 0
        try:
            embeddings = voyage.embed_batch(texts)
        except Exception as exc:
            logger.warning("Voyage batch embed failed for data_points: %s", exc)
        if embeddings is None:
            logger.error(
                "Cannot store data_points — Voyage unavailable and collection is %d-dim. "
                "The embedding source is configured at install and does not change.",
                _collection_dim(vs, _DATA_COLLECTION),
            )
            return 0

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
        except Exception as exc:
            logger.warning("Failed to store data point %s: %s", doc_id, exc)
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


def _store_newsapi_backfill(
    items: list[NewsItem],
    vs: VectorStore,
    voyage: VoyageClient | None = None,
) -> int:
    """Store NewsAPI backfill items to the news collection with Voyage embeddings."""
    if not items:
        return 0

    news_dim = _collection_dim(vs, _NEWS_COLLECTION)
    use_voyage = news_dim == 0 or news_dim == 1024

    texts = [f"{item.title}: {item.body[:200]}" for item in items]

    embeddings: list[list[float]] | None = None
    if use_voyage:
        if voyage is None:
            logger.error("Cannot store NewsAPI backfill — collection needs Voyage but no client provided")
            return 0
        try:
            embeddings = voyage.embed_batch(texts)
        except Exception as exc:
            logger.warning("Voyage embed failed for NewsAPI backfill: %s", exc)
        if embeddings is None:
            logger.error("Voyage unavailable — cannot store NewsAPI backfill to %d-dim collection", news_dim)
            return 0

    stored = 0
    for i, item in enumerate(items):
        doc_id = hashlib.sha256((item.url or item.title).encode()).hexdigest()
        category_str = item.category.value if hasattr(item.category, "value") else str(item.category)
        meta: dict[str, str | float] = {
            "source": item.source.value if hasattr(item.source, "value") else str(item.source),
            "category": category_str,
            "published": item.published_at.isoformat() if item.published_at else "",
            "published_epoch": str(int(item.published_at.timestamp())) if item.published_at else "",
            "data_freshness": item.data_freshness,
            "content_truncated": str(item.content_truncated),
            "sentiment_label": "neutral",
            "sentiment_score": "0.0",
            "impact_magnitude": "0.0",
            "impact_confidence": "0.0",
        }
        try:
            vs.add_document(
                doc_id=doc_id,
                text=texts[i],
                metadata=meta,
                embedding=embeddings[i] if embeddings else None,
                collection=_NEWS_COLLECTION,
            )
            stored += 1
        except Exception as exc:
            logger.warning("Failed to store NewsAPI backfill item %s: %s", doc_id[:12], exc)
            continue
    return stored


def backfill_data(
    months: int = 6,
    vector_store: VectorStore | None = None,
) -> dict[str, int]:
    """One-time historical backfill of data point sources.

    Fetches historical weather (Open-Meteo) and economic (FRED) data
    from the last N months and stores to ChromaDB data_points collection.
    Runs as a standalone kickstart — not part of the regular pipeline.

    Returns a dict with source names and item counts.
    """
    import asyncio
    import os as _os
    from datetime import timedelta, datetime, UTC

    from traderbot.news.sources import DataSourcesConfig, NewsAggregator
    import os as _os
    from traderbot.auth import get_credential

    _fred_cred = get_credential("fred", "api_key")
    fred_key = _fred_cred.get_secret_value() if _fred_cred else None
    newsapi_key = _os.environ.get("NEWSAPI_API_KEY")
    if not newsapi_key:
        _env_path = _os.path.expanduser("~/.traderbot/.env")
        if _os.path.exists(_env_path):
            for _line in open(_env_path):
                _stripped = _line.strip()
                if _stripped.startswith("NEWSAPI_API_KEY="):
                    newsapi_key = _stripped.split("=", 1)[1].strip().strip("\"'")
                    break
    ds_config = DataSourcesConfig(fred_key=fred_key, newsapi_key=newsapi_key)
    vs = vector_store or VectorStore()
    vs.init_collections()

    now = datetime.now(tz=UTC)

    async def _run_all() -> dict[str, int]:
        from traderbot.news.embeddings import VoyageClient
        aggregator = NewsAggregator(config=ds_config)
        voyage = VoyageClient()

        # Check collection dimensionality
        dp_dim = _collection_dim(vs, _DATA_COLLECTION)
        use_voyage_dp = dp_dim == 0 or dp_dim == 1024
        if not use_voyage_dp:
            logger.warning("data_points collection at %d-dim — backfill embeddings may be rejected", dp_dim)

        counts: dict[str, int] = {"open_meteo": 0, "fred": 0, "coingecko": 0, "thesportsdb": 0, "newsapi": 0}

        # Open-Meteo: chunk past_days=92 (max allowed) and remainder
        remaining_days = int(months * 30.44)
        chunks: list[int] = []
        while remaining_days > 0:
            chunk = min(remaining_days, 92)
            chunks.append(chunk)
            remaining_days -= chunk

        open_meteo_total = 0
        for i, past_days in enumerate(chunks):
            logger.info("Open-Meteo backfill chunk %d/%d: past_days=%d", i + 1, len(chunks), past_days)
            try:
                points = await aggregator._backfill_open_meteo(past_days=past_days)
                if points:
                    stored = _store_datapoints(points, vs, voyage=voyage, use_voyage_storage=use_voyage_dp)
                    open_meteo_total += stored
                    logger.info("Open-Meteo chunk stored %d/%d data points", stored, len(points))
            except Exception as exc:
                logger.error("Open-Meteo backfill chunk %d failed: %s", i + 1, exc)

        counts["open_meteo"] = open_meteo_total

        # FRED: single query per series with observation_start
        start_date = (now - timedelta(days=int(months * 30.44))).strftime("%Y-%m-%d")
        logger.info("FRED backfill: observation_start=%s", start_date)
        try:
            points = await aggregator._backfill_fred(observation_start=start_date)
            if points:
                stored = _store_datapoints(points, vs, voyage=voyage, use_voyage_storage=use_voyage_dp)
                counts["fred"] = stored
                logger.info("FRED backfill stored %d/%d data points", stored, len(points))
        except Exception as exc:
            logger.error("FRED backfill failed: %s", exc)

        # CoinGecko: historical crypto prices
        from_timestamp = int((now - timedelta(days=int(months * 30.44))).timestamp())
        logger.info("CoinGecko backfill: from_timestamp=%s", from_timestamp)
        try:
            points = await aggregator._backfill_coingecko(from_timestamp=from_timestamp)
            if points:
                stored = _store_datapoints(points, vs, voyage=voyage, use_voyage_storage=use_voyage_dp)
                counts["coingecko"] = stored
                logger.info("CoinGecko backfill stored %d/%d data points", stored, len(points))
        except Exception as exc:
            logger.error("CoinGecko backfill failed: %s", exc)

        # TheSportsDB: historical sports events
        start_date = (now - timedelta(days=int(months * 30.44))).strftime("%Y-%m-%d")
        logger.info("TheSportsDB backfill: start_date=%s", start_date)
        try:
            points = await aggregator._backfill_thesportsdb(start_date=start_date)
            if points:
                stored = _store_datapoints(points, vs, voyage=voyage, use_voyage_storage=use_voyage_dp)
                counts["thesportsdb"] = stored
                logger.info("TheSportsDB backfill stored %d/%d data points", stored, len(points))
        except Exception as exc:
            logger.error("TheSportsDB backfill failed: %s", exc)

        # NewsAPI: historical news (limited to 30 days on free tier)
        from_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")
        logger.info("NewsAPI backfill: from=%s to=%s", from_date, to_date)
        try:
            items = await aggregator._backfill_newsapi(from_date=from_date, to_date=to_date)
            if items:
                stored = _store_newsapi_backfill(items, vs, voyage=voyage)
                counts["newsapi"] = stored
                logger.info("NewsAPI backfill stored %d/%d news items", stored, len(items))
        except Exception as exc:
            logger.error("NewsAPI backfill failed: %s", exc)

        return counts

    return asyncio.run(_run_all())


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
    if not resolved_newsapi:
        _env_path = _os.path.expanduser("~/.traderbot/.env")
        if _os.path.exists(_env_path):
            for _line in open(_env_path):
                _stripped = _line.strip()
                if _stripped.startswith("NEWSAPI_API_KEY="):
                    resolved_newsapi = _stripped.split("=", 1)[1].strip().strip("\"'")
                    break
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
    if col_dim == 0:
        logger.debug("Collection '%s' is empty — returning empty summary", collection_name)
        return []

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


def get_data_points(
    category: str,
    since_hours: int = 48,
    max_items: int = 20,
    vector_store: VectorStore | None = None,
) -> dict:
    """Query ChromaDB for data point readings relevant to a market category.

    Returns structured readings (weather, economics, crypto, etc.) stored
    by the offline ingestion pipeline. Useful for temperature, humidity,
    economic indicators, and other quantitative data.

    Args:
        category: Market category (e.g. 'weather', 'economics')
        since_hours: Look back window in hours
        max_items: Max data points to return
        vector_store: Optional VectorStore instance

    Returns a dict with keys: count, data_points (list of dicts with
    source, title, timestamp, and data_* fields).
    """
    from datetime import timedelta

    vs = vector_store or VectorStore()
    cutoff = (datetime.now(tz=UTC) - timedelta(hours=since_hours)).timestamp()

    try:
        col = vs.get_collection(_DATA_COLLECTION)
    except Exception:
        return {"count": 0, "data_points": []}

    try:
        results = col.get(
            where={"$and": [
                {"category": {"$eq": category}},
                {"timestamp_epoch": {"$gte": cutoff}},
            ]},
            include=["metadatas", "documents"],
            limit=max_items * 2,
        )
    except Exception:
        results = col.get(
            where={"category": {"$eq": category}},
            include=["metadatas", "documents"],
            limit=max_items * 2,
        )

    if not results["ids"]:
        results = col.get(
            where={"category": {"$eq": category}},
            include=["metadatas", "documents"],
            limit=max_items * 2,
        )

    if not results["ids"]:
        return {"count": 0, "data_points": []}

    points: list[dict] = []
    for i, doc_id in enumerate(results["ids"]):
        meta = results["metadatas"][i]
        doc = results["documents"][i]

        # Collect all data_* and meta_* fields into structured dicts
        data_fields: dict[str, str] = {}
        meta_fields: dict[str, str] = {}
        for key, value in meta.items():
            if key.startswith("data_"):
                data_fields[key[5:]] = str(value)
            elif key.startswith("meta_"):
                meta_fields[key[5:]] = str(value)

        points.append({
            "id": doc_id,
            "title": (doc or "")[:120],
            "source": meta.get("source", ""),
            "timestamp": meta.get("timestamp", ""),
            "data": data_fields,
            "_meta": meta_fields,
        })

    points.sort(key=lambda p: p["timestamp"], reverse=True)
    points = points[:max_items]

    return {
        "count": len(points),
        "data_points": points,
    }


def get_news_context(
    category: str,
    since_hours: int = 24,
    max_articles: int = 10,
    vector_store: VectorStore | None = None,
    include_data_points: bool = False,
) -> dict:
    """Query ChromaDB for news relevant to a market category.

    Returns aggregate sentiment, article count, and top articles
    for the given category within the time window.

    Args:
        category: News/market category (e.g. 'economics', 'weather')
        since_hours: Look back window in hours
        max_articles: Max articles to include in the returned list
        vector_store: Optional VectorStore instance

    Returns a dict with keys: sentiment (aggregate), article_count,
    positive_count, negative_count, neutral_count, articles (list).
    When include_data_points=True, also returns data_points with readings.
    Returns empty result on any error.
    """
    from datetime import timedelta

    vs = vector_store or VectorStore()
    cutoff = (datetime.now(tz=UTC) - timedelta(hours=since_hours)).timestamp()

    # Optionally fetch data points for this category
    data_points_result: dict | None = None
    if include_data_points:
        data_points_result = get_data_points(
            category=category, since_hours=since_hours, max_items=20, vector_store=vs,
        )

    try:
        col = vs.get_collection(_NEWS_COLLECTION)
    except Exception:
        base: dict = {"sentiment": None, "article_count": 0, "articles": []}
        if data_points_result is not None:
            base["data_points"] = data_points_result
        return base

    try:
        results = col.get(
            where={"$and": [
                {"category": {"$eq": category}},
                {"published_epoch": {"$gte": cutoff}},
            ]},
            include=["metadatas", "documents"],
            limit=max_articles * 3,
        )
    except Exception:
        results = col.get(
            where={"category": {"$eq": category}},
            include=["metadatas", "documents"],
            limit=max_articles * 3,
        )

    if not results["ids"]:
        results = col.get(
            where={"category": {"$eq": category}},
            include=["metadatas", "documents"],
            limit=max_articles * 3,
        )

    if not results["ids"]:
        empty: dict = {"sentiment": None, "article_count": 0, "articles": []}
        if data_points_result is not None:
            empty["data_points"] = data_points_result
        return empty

    sentiment_scores: list[float] = []
    articles: list[dict] = []
    for i, doc_id in enumerate(results["ids"]):
        meta = results["metadatas"][i]
        doc = results["documents"][i]
        score_str = meta.get("sentiment_score")
        score: float | None = None
        if score_str:
            try:
                score = float(score_str)
                sentiment_scores.append(score)
            except (ValueError, TypeError):
                pass
        articles.append({
            "id": doc_id,
            "title": meta.get("title", "")[:120],
            "source": meta.get("source", ""),
            "published": meta.get("published", ""),
            "sentiment_score": score,
        })

    articles.sort(key=lambda a: a["published"], reverse=True)
    articles = articles[:max_articles]

    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else None
    positive = sum(1 for s in sentiment_scores if s > 0.1)
    negative = sum(1 for s in sentiment_scores if s < -0.1)
    neutral = len(sentiment_scores) - positive - negative

    result: dict = {
        "sentiment": round(avg_sentiment, 4) if avg_sentiment is not None else None,
        "article_count": len(sentiment_scores),
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "articles": articles,
    }
    if data_points_result is not None:
        result["data_points"] = data_points_result
    return result
