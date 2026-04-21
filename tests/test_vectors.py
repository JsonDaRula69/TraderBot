"""Tests for db/vectors.py — VectorStore with mocked ChromaDB client."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from traderbot.db.vectors import (
    DEFAULT_COLLECTIONS,
    DEFAULT_PERSIST_DIR,
    EMBEDDING_DIMENSION,
    VectorStore,
)


def _fake_embedding(dim: int = EMBEDDING_DIMENSION) -> list[float]:
    return [0.01] * dim


def _make_mock_collection() -> MagicMock:
    col = MagicMock()
    col.upsert = MagicMock()
    col.delete = MagicMock()
    col.query = MagicMock(return_value={
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    })
    return col


def _make_mock_client(collections: dict[str, MagicMock] | None = None) -> MagicMock:
    client = MagicMock()
    store: dict[str, MagicMock] = collections or {}

    def get_or_create(name: str, **kwargs: Any) -> MagicMock:
        if name not in store:
            col = _make_mock_collection()
            store[name] = col
        return store[name]

    client.get_or_create_collection = MagicMock(side_effect=get_or_create)
    return client


class TestVectorStoreInit:
    def test_default_persist_dir(self) -> None:
        store = VectorStore()
        assert store.persist_dir == DEFAULT_PERSIST_DIR

    def test_custom_persist_dir(self) -> None:
        custom = Path("/tmp/custom_chromadb")
        store = VectorStore(persist_dir=custom)
        assert store.persist_dir == custom

    def test_chromadb_missing_raises(self) -> None:
        store = VectorStore(persist_dir=Path("/tmp/test"))
        with patch("traderbot.db.vectors.chromadb", None), pytest.raises(ImportError, match="chromadb is not installed"):
            _ = store.client


class TestGetCollection:
    def test_get_collection_creates_new(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {}

        col = store.get_collection("decisions")
        assert col is not None
        mock_client.get_or_create_collection.assert_called_once_with(
            name="decisions",
            metadata={"hnsw:space": "cosine", "embedding_dimension": EMBEDDING_DIMENSION},
        )

    def test_get_collection_caches(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {}

        col1 = store.get_collection("news")
        col2 = store.get_collection("news")
        assert col1 is col2
        assert mock_client.get_or_create_collection.call_count == 1

    def test_init_collections_creates_all_defaults(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {}

        store.init_collections()
        for name in DEFAULT_COLLECTIONS:
            assert name in store._collections


class TestAddDocument:
    def test_add_document_without_embedding(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client

        store.add_document("doc1", "test text", {"source": "test"}, collection="decisions")

        col = store._collections["decisions"]
        col.upsert.assert_called_once_with(
            ids=["doc1"],
            documents=["test text"],
            metadatas=[{"source": "test"}],
        )

    def test_add_document_with_embedding(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client

        emb = _fake_embedding()
        store.add_document("doc2", "text with embedding", {"source": "emb"}, embedding=emb, collection="news")

        col = store._collections["news"]
        col.upsert.assert_called_once_with(
            ids=["doc2"],
            documents=["text with embedding"],
            metadatas=[{"source": "emb"}],
            embeddings=[emb],
        )

    def test_add_document_uses_upsert(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client

        store.add_document("doc1", "original", {"v": "1"})
        store.add_document("doc1", "updated", {"v": "2"})

        col = store._collections["decisions"]
        assert col.upsert.call_count == 2

    def test_add_document_different_collections(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client

        store.add_document("d1", "decision text", {"type": "trade"}, collection="decisions")
        store.add_document("n1", "news text", {"type": "article"}, collection="news")
        store.add_document("m1", "pattern text", {"type": "signal"}, collection="market_patterns")

        assert "decisions" in store._collections
        assert "news" in store._collections
        assert "market_patterns" in store._collections


class TestSearch:
    def test_search_returns_results(self) -> None:
        col = _make_mock_collection()
        col.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "documents": [["text1", "text2"]],
            "metadatas": [[{"source": "a"}, {"source": "b"}]],
            "distances": [[0.1, 0.5]],
        }
        mock_client = _make_mock_client({"decisions": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"decisions": col}

        results = store.search(_fake_embedding(), n=2, collection="decisions")

        assert len(results) == 2
        assert results[0] == ("doc1", "text1", {"source": "a"}, 0.1)
        assert results[1] == ("doc2", "text2", {"source": "b"}, 0.5)

    def test_search_with_metadata_filter(self) -> None:
        col = _make_mock_collection()
        col.query.return_value = {
            "ids": [["doc1"]],
            "documents": [["text1"]],
            "metadatas": [[{"category": "economics"}]],
            "distances": [[0.2]],
        }
        mock_client = _make_mock_client({"decisions": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"decisions": col}

        results = store.search(
            _fake_embedding(), n=5, filter_metadata={"category": "economics"}, collection="decisions",
        )

        col.query.assert_called_once_with(
            query_embeddings=[_fake_embedding()],
            n_results=5,
            include=["documents", "metadatas", "distances"],
            where={"category": "economics"},
        )
        assert len(results) == 1

    def test_search_empty_results(self) -> None:
        col = _make_mock_collection()
        col.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_client = _make_mock_client({"decisions": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"decisions": col}

        results = store.search(_fake_embedding(), n=10, collection="decisions")
        assert results == []

    def test_search_result_tuple_format(self) -> None:
        col = _make_mock_collection()
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc text"]],
            "metadatas": [[{"key": "val"}]],
            "distances": [[0.33]],
        }
        mock_client = _make_mock_client({"news": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"news": col}

        results = store.search(_fake_embedding(), n=1, collection="news")

        assert len(results) == 1
        doc_id, text, meta, dist = results[0]
        assert isinstance(doc_id, str)
        assert isinstance(text, str)
        assert isinstance(meta, dict)
        assert isinstance(dist, float)


class TestDeleteDocument:
    def test_delete_document(self) -> None:
        col = _make_mock_collection()
        mock_client = _make_mock_client({"decisions": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"decisions": col}

        store.delete_document("doc1", collection="decisions")

        col.delete.assert_called_once_with(ids=["doc1"])

    def test_delete_from_different_collection(self) -> None:
        col = _make_mock_collection()
        mock_client = _make_mock_client({"news": col})
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {"news": col}

        store.delete_document("news1", collection="news")
        col.delete.assert_called_once_with(ids=["news1"])


class TestChromadbOptional:
    def test_operations_require_chromadb(self) -> None:
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = None
        store._collections = {}

        with patch("traderbot.db.vectors.chromadb", None):
            with pytest.raises(ImportError):
                store.get_collection("test")

            with pytest.raises(ImportError):
                store.add_document("id", "text", {})

            with pytest.raises(ImportError):
                store.search(_fake_embedding())

            with pytest.raises(ImportError):
                store.delete_document("id")

    def test_helpful_error_message(self) -> None:
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = None
        store._collections = {}

        with patch("traderbot.db.vectors.chromadb", None), pytest.raises(ImportError, match="pip install"):
            _ = store.client


class TestEmbeddingDimension:
    def test_dimension_is_1024(self) -> None:
        assert EMBEDDING_DIMENSION == 1024

    def test_collection_metadata_includes_dimension(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {}

        store.get_collection("decisions")

        call_kwargs = mock_client.get_or_create_collection.call_args
        assert call_kwargs.kwargs["metadata"]["embedding_dimension"] == 1024


class TestDefaultCollections:
    def test_default_collections_tuple(self) -> None:
        assert DEFAULT_COLLECTIONS == ("decisions", "news", "market_patterns")

    def test_init_collections_creates_three(self) -> None:
        mock_client = _make_mock_client()
        store = VectorStore(persist_dir=Path("/tmp/test"))
        store._client = mock_client
        store._collections = {}

        store.init_collections()

        assert len(store._collections) == 3
        assert set(store._collections.keys()) == {"decisions", "news", "market_patterns"}
