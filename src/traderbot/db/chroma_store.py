"""Embedded ChromaDB client with process and category isolation."""

from __future__ import annotations

import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, ClassVar, Protocol, Self, override, runtime_checkable

import chromadb
from chromadb import Collection
from chromadb.api import ClientAPI
from chromadb.api.types import GetResult, Metadata, PyEmbedding, QueryResult, Where
from chromadb.config import Settings

from traderbot.kalshi.models import MarketCategory

from .models import (
    EXPLICIT_EMBEDDING_MODEL,
    SHARED_CHROMA_COLLECTIONS,
    ChromaMetadataMismatchError,
    MetadataValue,
    scoped_ids,
    scoped_metadatas,
    scoped_where,
    validate_collection_name,
)
from .security import (
    ChromaBackendError,
    InvalidChromaRootError,
    assert_embedded_backend,
    validate_chroma_lock_file,
    validate_chroma_root,
)

type ChromaGetResult = GetResult
type ChromaQueryResult = QueryResult


@runtime_checkable
class _ClosableClient(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ChromaOwnershipError(RuntimeError):
    """Raised when another process owns the embedded Chroma root."""

    lock_path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"cannot own Chroma lock {self.lock_path}: {self.reason}"


class ChromaOwnershipLock:
    """Mutable lifetime guard for exclusive Chroma root ownership."""

    def __init__(self, data_root: Path) -> None:
        self._lock_path: Path = data_root / "chromadb.lock"
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        validate_chroma_root(self._lock_path.parent)
        validate_chroma_lock_file(self._lock_path)
        lock_file = self._lock_path.open("r+b", buffering=0)
        try:
            if sys.platform == "win32":
                import msvcrt

                _ = lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            lock_file.close()
            raise ChromaOwnershipError(self._lock_path, "already locked or unavailable") from exc
        try:
            validate_chroma_root(self._lock_path.parent)
            validate_chroma_lock_file(self._lock_path)
        except InvalidChromaRootError:
            lock_file.close()
            raise
        self._file = lock_file

    def release(self) -> None:
        if self._file is None:
            return
        if sys.platform == "win32":
            import msvcrt

            _ = self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


class ChromaStore:
    """Category-safe facade over one embedded persistent Chroma client."""

    SHARED_COLLECTIONS: ClassVar[frozenset[str]] = SHARED_CHROMA_COLLECTIONS

    def __init__(self, data_root: Path) -> None:
        validate_chroma_root(data_root)
        with ExitStack() as startup:
            lock = startup.enter_context(ChromaOwnershipLock(data_root))
            client = chromadb.PersistentClient(
                path=data_root,
                settings=Settings(
                    chroma_api_impl="chromadb.api.rust.RustBindingsAPI",
                    anonymized_telemetry=False,
                ),
            )
            if not isinstance(client, _ClosableClient):
                settings = client.get_settings()
                raise ChromaBackendError(
                    settings.chroma_api_impl,
                    settings.anonymized_telemetry,
                    "client has no public close method",
                )
            _ = startup.callback(client.close)
            assert_embedded_backend(client)
            _ = startup.pop_all()
        self._lock: ChromaOwnershipLock = lock
        self._client: ClientAPI = client
        self._closer: _ClosableClient = client
        self._collections: dict[str, Collection] = {}
        self._closed: bool = False

    @staticmethod
    def _verify_metadata(collection: Collection, expected: Metadata) -> None:
        if collection.metadata != expected:
            raise ChromaMetadataMismatchError(collection.name, expected, collection.metadata)

    def _get_or_create_collection(self, name: str, dimension: int) -> Collection:
        validate_collection_name(name)
        expected: Metadata = {"dimension": dimension, "model": EXPLICIT_EMBEDDING_MODEL}
        collection = self._collections.get(name)
        if collection is None:
            collection = self._client.get_or_create_collection(
                name=name,
                metadata=dict(expected),
                embedding_function=None,
            )
        self._verify_metadata(collection, expected)
        self._collections[name] = collection
        return collection

    def _existing_collection(self, name: str) -> Collection:
        validate_collection_name(name)
        collection = self._collections.get(name)
        if collection is None:
            collection = self._client.get_collection(name=name, embedding_function=None)
            actual = collection.metadata
            dimension = actual.get("dimension")
            expected: Metadata = {"dimension": dimension, "model": EXPLICIT_EMBEDDING_MODEL}
            self._verify_metadata(collection, expected)
            self._collections[name] = collection
        return collection

    def get_or_create_collection(self, name: str, dimension: int) -> None:
        _ = self._get_or_create_collection(name, dimension)

    def list_collections(self) -> list[str]:
        return sorted(collection.name for collection in self._client.list_collections())

    def add(
        self,
        category: MarketCategory,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str] | None,
        metadatas: list[dict[str, MetadataValue]] | None,
    ) -> None:
        metadatas_with_scope = scoped_metadatas(category, collection_name, ids, metadatas)
        collection = self._get_or_create_collection(collection_name, len(embeddings[0]))
        embedding_values: list[PyEmbedding] = [list(embedding) for embedding in embeddings]
        collection.add(
            ids=scoped_ids(category, collection_name, ids),
            embeddings=embedding_values,
            documents=documents,
            metadatas=metadatas_with_scope,
        )

    def upsert(
        self,
        category: MarketCategory,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str] | None,
        metadatas: list[dict[str, MetadataValue]] | None,
    ) -> None:
        metadatas_with_scope = scoped_metadatas(category, collection_name, ids, metadatas)
        collection = self._get_or_create_collection(collection_name, len(embeddings[0]))
        embedding_values: list[PyEmbedding] = [list(embedding) for embedding in embeddings]
        collection.upsert(
            ids=scoped_ids(category, collection_name, ids),
            embeddings=embedding_values,
            documents=documents,
            metadatas=metadatas_with_scope,
        )

    def get(
        self,
        category: MarketCategory,
        collection_name: str,
        ids: list[str] | None,
        where: Where | None,
        limit: int | None,
    ) -> ChromaGetResult:
        internal_ids = None if ids is None else scoped_ids(category, collection_name, ids)
        return self._existing_collection(collection_name).get(
            ids=internal_ids,
            where=scoped_where(category, collection_name, where),
            limit=limit,
        )

    def query(
        self,
        category: MarketCategory,
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int,
        where: Where | None,
    ) -> ChromaQueryResult:
        collection = self._get_or_create_collection(collection_name, len(query_embeddings[0]))
        embedding_values: list[PyEmbedding] = [list(embedding) for embedding in query_embeddings]
        return collection.query(
            query_embeddings=embedding_values,
            n_results=n_results,
            where=scoped_where(category, collection_name, where),
        )

    def delete(
        self,
        category: MarketCategory,
        collection_name: str,
        ids: list[str] | None,
        where: Where | None,
    ) -> None:
        internal_ids = None if ids is None else scoped_ids(category, collection_name, ids)
        _ = self._existing_collection(collection_name).delete(
            ids=internal_ids,
            where=scoped_where(category, collection_name, where),
        )

    def close(self) -> None:
        """Close Chroma before releasing exclusive path ownership."""
        if self._closed:
            return
        self._closer.close()
        self._lock.release()
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = [
    "ChromaGetResult",
    "ChromaMetadataMismatchError",
    "ChromaOwnershipError",
    "ChromaOwnershipLock",
    "ChromaQueryResult",
    "ChromaStore",
]
