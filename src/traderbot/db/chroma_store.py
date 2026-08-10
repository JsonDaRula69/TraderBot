"""Embedded ChromaDB client with process and category isolation."""

from __future__ import annotations

import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Protocol, Self, override, runtime_checkable

import chromadb
from chromadb import Collection
from chromadb.api import ClientAPI
from chromadb.api.types import DeleteResult, GetResult, Metadata, PyEmbedding, QueryResult, Where
from chromadb.config import Settings

from traderbot.kalshi.models import MarketCategory

from .models import (
    ChromaCategoryError,
    ChromaDeleteRequest,
    ChromaGetRequest,
    ChromaQueryRequest,
    ChromaRecord,
)
from .security import (
    ChromaBackendError,
    InvalidChromaRootError,
    assert_embedded_backend,
    validate_chroma_lock_file,
    validate_chroma_root,
)


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

    def _collection(self, name: str) -> Collection:
        collection = self._collections.get(name)
        if collection is None:
            collection = self._client.get_or_create_collection(name=name, embedding_function=None)
            self._collections[name] = collection
        return collection

    @staticmethod
    def _internal_id(category: MarketCategory, caller_id: str) -> str:
        return f"{category.value}:{caller_id}"

    @staticmethod
    def _metadata(record: ChromaRecord) -> Metadata:
        supplied = record.metadata.get("category")
        if supplied is not None and supplied != record.category.value:
            raise ChromaCategoryError(record.category, supplied)
        metadata = dict(record.metadata)
        metadata["category"] = record.category.value
        return metadata

    @classmethod
    def _record_values(
        cls, record: ChromaRecord
    ) -> tuple[list[str], list[PyEmbedding], list[Metadata]]:
        return (
            [cls._internal_id(record.category, record.caller_id)],
            [list(record.embedding)],
            [cls._metadata(record)],
        )

    @staticmethod
    def _where(category: MarketCategory) -> Where:
        return {"category": category.value}

    def add(self, collection_name: str, record: ChromaRecord) -> None:
        """Add one record under its canonical category-prefixed ID."""
        collection = self._collection(collection_name)
        ids, embeddings, metadatas = self._record_values(record)
        if record.document is None:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        else:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=[record.document],
            )

    def upsert(self, collection_name: str, record: ChromaRecord) -> None:
        """Upsert one record without allowing cross-category ID collision."""
        collection = self._collection(collection_name)
        ids, embeddings, metadatas = self._record_values(record)
        if record.document is None:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        else:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=[record.document],
            )

    def get(self, collection_name: str, request: ChromaGetRequest) -> GetResult:
        """Get only records in the authorized category."""
        ids = (
            [self._internal_id(request.category, caller_id) for caller_id in request.caller_ids]
            if request.caller_ids is not None
            else None
        )
        return self._collection(collection_name).get(ids=ids, where=self._where(request.category))

    def query(self, collection_name: str, request: ChromaQueryRequest) -> QueryResult:
        """Query only records in the authorized category."""
        return self._collection(collection_name).query(
            query_embeddings=[list(request.embedding)],
            n_results=request.n_results,
            where=self._where(request.category),
        )

    def delete(self, collection_name: str, request: ChromaDeleteRequest) -> DeleteResult:
        """Delete only records in the authorized category."""
        ids = (
            [self._internal_id(request.category, caller_id) for caller_id in request.caller_ids]
            if request.caller_ids is not None
            else None
        )
        return self._collection(collection_name).delete(
            ids=ids, where=self._where(request.category)
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
    "ChromaCategoryError",
    "ChromaDeleteRequest",
    "ChromaGetRequest",
    "ChromaOwnershipError",
    "ChromaOwnershipLock",
    "ChromaQueryRequest",
    "ChromaRecord",
    "ChromaStore",
]
