"""ChromaDB vector store for similarity search over decisions, news, and market patterns."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from chromadb.api.models import Collection

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION: int = 1024
DEFAULT_PERSIST_DIR: Path = Path.home() / ".traderbot" / "chromadb"
DEFAULT_COLLECTIONS: tuple[str, ...] = ("decisions", "news", "market_patterns", "news_signals", "market_conditions")

SearchResult = tuple[str, str, dict[str, str], float]
"""(doc_id, text, metadata, distance)"""

_CHROMADB_MISSING_MSG = (
    "chromadb is not installed. Install it with: pip install traderbot[vectors] or pip install chromadb"
)


class VectorStore(BaseModel):
    """Thin wrapper around ChromaDB for similarity search."""

    model_config = ConfigDict(strict=True, extra="forbid", arbitrary_types_allowed=True)

    persist_dir: Annotated[Path, Field(description="Directory for ChromaDB persistence")]
    _client: object | None = PrivateAttr(default=None)
    _collections: dict[str, Collection] = PrivateAttr(default_factory=dict)

    def __init__(self, persist_dir: Path | None = None, **data: object) -> None:
        if persist_dir is not None:
            data["persist_dir"] = persist_dir
        elif "persist_dir" not in data:
            data["persist_dir"] = DEFAULT_PERSIST_DIR
        super().__init__(**data)
        self._client = None
        self._collections = {}

    @property
    def client(self) -> chromadb.ClientAPI:
        """Lazily initialize and return the ChromaDB client."""
        if self._client is not None:
            return self._client
        if chromadb is None:
            raise ImportError(_CHROMADB_MISSING_MSG)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    def get_collection(self, name: str) -> Collection:
        """Get or create a named collection."""
        if name in self._collections:
            return self._collections[name]
        collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_dimension": EMBEDDING_DIMENSION},
        )
        self._collections[name] = collection
        return collection

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, str],
        *,
        embedding: list[float] | None = None,
        collection: str = "decisions",
    ) -> None:
        """Upsert a document into the specified collection."""
        col = self.get_collection(collection)
        kwargs: dict[str, object] = {
            "ids": [doc_id],
            "documents": [text],
            "metadatas": [metadata],
        }
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        col.upsert(**kwargs)

    def search(
        self,
        query_embedding: list[float],
        *,
        n: int = 10,
        filter_metadata: dict[str, object] | None = None,
        collection: str = "decisions",
    ) -> list[SearchResult]:
        """Search for similar documents using a query embedding."""
        col = self.get_collection(collection)
        kwargs: dict[str, object] = {
            "query_embeddings": [query_embedding],
            "n_results": n,
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata is not None:
            kwargs["where"] = filter_metadata

        results = col.query(**kwargs)

        ids = results["ids"][0] if results["ids"] else []
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        out: list[SearchResult] = []
        for i, doc_id in enumerate(ids):
            text = documents[i] if i < len(documents) else ""
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else 0.0
            out.append((doc_id, text, meta, dist))
        return out

    def delete_document(self, doc_id: str, *, collection: str = "decisions") -> None:
        """Remove a document by its ID from the specified collection."""
        col = self.get_collection(collection)
        col.delete(ids=[doc_id])

    def init_collections(self) -> None:
        """Pre-initialize all default collections."""
        for name in DEFAULT_COLLECTIONS:
            self.get_collection(name)
