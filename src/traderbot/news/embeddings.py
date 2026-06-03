"""Voyage AI client for embeddings and reranking — slow-path semantic layer only."""

from __future__ import annotations

import json
import logging
import os
import time

from pydantic import BaseModel, ConfigDict, PrivateAttr

try:
    import voyageai
except ImportError:
    voyageai = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

EMBED_DIMENSION: int = 1024
"""voyage-4-large output dimension (default)."""

_DEFAULT_EMBED_MODEL = "voyage-4-large"
_DEFAULT_RERANK_MODEL = "rerank-2.5"

_RATE_LIMIT_WINDOW_SECS = 60
_RATE_LIMIT_MAX_CALLS = 60
_EMBED_TIMEOUT_SECS = 30.0
_RERANK_TIMEOUT_SECS = 0.3
_EMBED_BATCH_SIZE = 128  # Voyage max inputs per request


class VoyageClient(BaseModel):
    """Voyage AI client with lazy init, graceful degradation, and rate limiting.

    All methods return None when VOYAGE_API_KEY is unset or when rate-limited,
    enabling the fast path (VADER/TextBlob) to operate without disruption.
    """

    model_config = ConfigDict(strict=True, extra="forbid", arbitrary_types_allowed=True)

    _client: object | None = PrivateAttr(default=None)
    _call_timestamps: list[float] = PrivateAttr(default_factory=list)
    _key_available: bool = PrivateAttr(default=True)

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        api_key = os.environ.get("VOYAGE_API_KEY")
        if not api_key:
            from traderbot.paths import get_data_dir

            env_path = get_data_dir() / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("VOYAGE_API_KEY="):
                        api_key = stripped.split("=", 1)[1].strip().strip("\"'")
                        os.environ["VOYAGE_API_KEY"] = api_key
                        break
        if not api_key:
            self._key_available = False
            logger.warning("VOYAGE_API_KEY not set — Voyage AI calls will return None")
        self._client = None
        self._call_timestamps = []

    @property
    def client(self) -> voyageai.Client:
        if self._client is not None:
            return self._client  # type: ignore[return-value]
        if voyageai is None:
            raise ImportError(
                "voyageai is not installed. Install it with: pip install traderbot[voyage]"
            )
        if not self._key_available:
            raise RuntimeError("VOYAGE_API_KEY not set")
        self._client = voyageai.Client(
            timeout=max(_EMBED_TIMEOUT_SECS, _RERANK_TIMEOUT_SECS),
            max_retries=1,
        )
        return self._client  # type: ignore[return-value]

    def _check_rate_limit(self) -> bool:
        now = time.monotonic()
        cutoff = now - _RATE_LIMIT_WINDOW_SECS
        self._call_timestamps = [t for t in self._call_timestamps if t > cutoff]
        if len(self._call_timestamps) >= _RATE_LIMIT_MAX_CALLS:
            logger.warning(
                "Voyage rate limit reached (%d calls/%ds) — falling back to fast path",
                _RATE_LIMIT_MAX_CALLS,
                _RATE_LIMIT_WINDOW_SECS,
            )
            return False
        self._call_timestamps.append(now)
        return True

    def _is_available(self) -> bool:
        if not self._key_available:
            return False
        if voyageai is None:
            logger.warning("voyageai package not installed — returning None")
            return False
        return True

    def embed(
        self,
        text: str,
        model: str = _DEFAULT_EMBED_MODEL,
    ) -> list[float] | None:
        """Returns embedding or None on failure/timeout/key-unset."""
        if not self._is_available():
            return None
        if not self._check_rate_limit():
            return None
        try:
            result = self.client.embed(
                [text],
                model=model,
                input_type="document",
            )
            return result.embeddings[0]  # type: ignore[no-any-return]
        except Exception:
            logger.warning("Voyage embed() failed", exc_info=True)
            return None

    def embed_batch(
        self,
        texts: list[str],
        model: str = _DEFAULT_EMBED_MODEL,
    ) -> list[list[float]] | None:
        """Returns embeddings or None on failure/timeout/key-unset.

        Splits large payloads into batches of _EMBED_BATCH_SIZE (Voyage API limit).
        """
        if not texts:
            return []
        if not self._is_available():
            return None
        if not self._check_rate_limit():
            return None

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            chunk = texts[i : i + _EMBED_BATCH_SIZE]
            try:
                result = self.client.embed(
                    chunk,
                    model=model,
                    input_type="document",
                )
                if result and result.embeddings:
                    all_embeddings.extend(result.embeddings)
                else:
                    logger.warning("Voyage embed chunk returned no embeddings")
                    return None
            except Exception:
                logger.warning(
                    "Voyage embed_batch() failed at chunk %d/%d",
                    i // _EMBED_BATCH_SIZE + 1,
                    (len(texts) + _EMBED_BATCH_SIZE - 1) // _EMBED_BATCH_SIZE,
                )
                return None

        return all_embeddings

    def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = _DEFAULT_RERANK_MODEL,
        top_k: int | None = None,
    ) -> list[tuple[int, float]] | None:
        """Returns (doc_index, relevance_score) sorted desc, or None on failure."""
        if not documents:
            return []
        if not self._is_available():
            return None
        if not self._check_rate_limit():
            return None
        try:
            kwargs: dict[str, object] = {
                "query": query,
                "documents": documents,
                "model": model,
                "timeout": _RERANK_TIMEOUT_SECS,
            }
            if top_k is not None:
                kwargs["top_k"] = top_k
            result = self.client.rerank(**kwargs)
            return [
                (r.index, r.relevance_score)
                for r in sorted(result.results, key=lambda r: r.relevance_score, reverse=True)
            ]
        except Exception:
            logger.warning("Voyage rerank() failed", exc_info=True)
            return None

    # ── Batch API (historical backfill ONLY) ─────────────────────────────
    # NEVER use batch API on the hot path. The 12-hour completion window
    # makes it unsuitable for real-time embeddings. These methods exist
    # exclusively for deferred operations: initial ChromaDB population,
    # re-embedding on model upgrade, heartbeat clustering, etc.

    def embed_batch_submit(
        self,
        texts: list[str],
        model: str = _DEFAULT_EMBED_MODEL,
    ) -> str | None:
        """Submit a batch embedding job. Returns job_id or None on failure.

        ⚠ Batch API only — 33% cost discount, ~12h completion window.
        Never use on the hot path.
        """
        if not texts:
            logger.warning("embed_batch_submit called with empty texts")
            return None
        if not self._is_available():
            return None
        if not self._check_rate_limit():
            return None
        try:
            batch = self.client.batches.create(
                endpoint="/v1/embeddings",
                completion_window="12h",
                input=texts,
                request_params={"model": model},
            )
            return batch.id  # type: ignore[no-any-return]
        except Exception:
            logger.warning("Voyage embed_batch_submit() failed", exc_info=True)
            return None

    def embed_batch_retrieve(
        self,
        job_id: str,
    ) -> list[list[float]] | None:
        """Retrieve results from a batch job. Returns None if not ready yet.

        ⚠ Batch API only — poll periodically until results are available.
        Never use on the hot path.
        """
        if not self._is_available():
            return None
        if not self._check_rate_limit():
            return None
        try:
            batch = self.client.batches.retrieve(job_id)
            if batch.status not in ("completed", "succeeded"):
                return None

            output_file_id = batch.output_file_id
            if not output_file_id:
                return None

            content = self.client.files.retrieve_content(output_file_id)
            embeddings: list[list[float]] = []
            for line in content.strip().split("\n"):
                if line:
                    obj = json.loads(line)
                    embeddings.append(obj.get("data", {}).get("embedding", []))
            return embeddings if embeddings else None
        except Exception:
            logger.warning("Voyage embed_batch_retrieve() failed", exc_info=True)
            return None
