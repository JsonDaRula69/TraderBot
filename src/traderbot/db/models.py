"""Typed requests and records for category-scoped Chroma operations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Final, override

from chromadb.api.types import Metadata, Where

from traderbot.kalshi.models import MarketCategory

type MetadataValue = str | int | float | bool

_SOURCE_NAME_PATTERN: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_COLLECTION_NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]")
_AGENT_MODES: Final = frozenset({"backtest", "paper", "live"})
_AGENT_COLLECTION_KINDS: Final = frozenset({"decisions", "learnings"})
EXPLICIT_EMBEDDING_MODEL: Final = "explicit"
GLOBAL_CHROMA_COLLECTIONS: Final = frozenset({"market_conditions"})
SHARED_CHROMA_COLLECTIONS: Final = frozenset(
    {"news", "data_points", "market_patterns", "news_signals", "market_conditions"}
)


@dataclass(frozen=True, slots=True)
class ChromaCategoryError(RuntimeError):
    """Raised when caller metadata conflicts with its authorized category."""

    category: MarketCategory
    supplied: MetadataValue

    @override
    def __str__(self) -> str:
        return f"metadata category {self.supplied!r} conflicts with {self.category.value!r}"


@dataclass(frozen=True, slots=True)
class InvalidCollectionNameError(RuntimeError):
    """Raised when a source or collection name violates the storage contract."""

    name: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid Chroma collection name {self.name!r}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ChromaMetadataMismatchError(RuntimeError):
    """Raised when persisted collection metadata is not exactly compatible."""

    collection_name: str
    expected: Metadata
    actual: Metadata

    @override
    def __str__(self) -> str:
        return (
            f"Chroma collection {self.collection_name!r} metadata mismatch: "
            f"expected {dict(self.expected)!r}, got {dict(self.actual)!r}"
        )


def validate_collection_name(name: str) -> None:
    """Validate Chroma's selected-release collection naming contract."""
    if not 3 <= len(name) <= 512:
        raise InvalidCollectionNameError(name, "length must be between 3 and 512 characters")
    if _COLLECTION_NAME_PATTERN.fullmatch(name) is None:
        raise InvalidCollectionNameError(name, "must start and end with alphanumeric characters")
    if ".." in name:
        raise InvalidCollectionNameError(name, "consecutive periods are forbidden")
    try:
        _ = ip_address(name)
    except ValueError:
        return
    raise InvalidCollectionNameError(name, "IP addresses are forbidden")


def agent_collection_name(source_name: str, mode: str | None, kind: str) -> str:
    """Build a collision-free per-agent collection name."""
    if kind not in _AGENT_COLLECTION_KINDS:
        raise InvalidCollectionNameError(kind, "kind must be decisions or learnings")
    if source_name == "sysadmin":
        if mode is not None:
            raise InvalidCollectionNameError(source_name, "canonical sysadmin must be mode-less")
        name = f"sysadmin_{kind}"
    else:
        if len(source_name) > 44 or _SOURCE_NAME_PATTERN.fullmatch(source_name) is None:
            raise InvalidCollectionNameError(
                source_name,
                "source must be lowercase hyphenated alphanumeric text of at most 44 characters",
            )
        if mode not in _AGENT_MODES:
            raise InvalidCollectionNameError(
                source_name, "non-sysadmin collections require a valid mode"
            )
        name = f"{source_name.replace('-', '_')}_{mode}_{kind}"
    validate_collection_name(name)
    return name


def scoped_ids(category: MarketCategory, collection_name: str, ids: list[str]) -> list[str]:
    """Map caller IDs into the mandatory collection scope."""
    if collection_name in GLOBAL_CHROMA_COLLECTIONS:
        return list(ids)
    return [f"{category.value}:{caller_id}" for caller_id in ids]


def scoped_where(
    category: MarketCategory, collection_name: str, caller_where: Where | None
) -> Where | None:
    """Compose the mandatory category predicate with an optional caller predicate."""
    if collection_name in GLOBAL_CHROMA_COLLECTIONS:
        return caller_where
    category_where: Where = {"category": category.value}
    if caller_where is None:
        return category_where
    return {"$and": [category_where, caller_where]}


def scoped_metadatas(
    category: MarketCategory,
    collection_name: str,
    ids: list[str],
    metadatas: list[dict[str, MetadataValue]] | None,
) -> list[Metadata] | None:
    """Copy metadata while enforcing the canonical category value."""
    if collection_name in GLOBAL_CHROMA_COLLECTIONS:
        if metadatas is None:
            return None
        global_metadatas: list[Metadata] = []
        global_metadatas.extend(dict(metadata) for metadata in metadatas)
        return global_metadatas
    if metadatas is None:
        supplied_metadatas: list[dict[str, MetadataValue]] = [dict() for _ in ids]
    else:
        supplied_metadatas = metadatas
    scoped: list[Metadata] = []
    for supplied_metadata in supplied_metadatas:
        supplied_category = supplied_metadata.get("category")
        if supplied_category is not None and supplied_category != category.value:
            raise ChromaCategoryError(category, supplied_category)
        metadata: Metadata = dict(supplied_metadata)
        metadata["category"] = category.value
        scoped.append(metadata)
    return scoped


@dataclass(frozen=True, slots=True)
class ChromaRecord:
    """One explicitly embedded record at the category boundary."""

    category: MarketCategory
    caller_id: str
    embedding: tuple[float, ...]
    document: str | None = None
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict[str, MetadataValue])


@dataclass(frozen=True, slots=True)
class ChromaGetRequest:
    """A category-scoped retrieval request."""

    category: MarketCategory
    caller_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ChromaQueryRequest:
    """A category-scoped vector query."""

    category: MarketCategory
    embedding: tuple[float, ...]
    n_results: int = 10


@dataclass(frozen=True, slots=True)
class ChromaDeleteRequest:
    """A category-scoped deletion request."""

    category: MarketCategory
    caller_ids: tuple[str, ...] | None = None


__all__ = [
    "ChromaCategoryError",
    "ChromaDeleteRequest",
    "ChromaGetRequest",
    "ChromaMetadataMismatchError",
    "ChromaQueryRequest",
    "ChromaRecord",
    "EXPLICIT_EMBEDDING_MODEL",
    "GLOBAL_CHROMA_COLLECTIONS",
    "InvalidCollectionNameError",
    "MetadataValue",
    "SHARED_CHROMA_COLLECTIONS",
    "agent_collection_name",
    "scoped_ids",
    "scoped_metadatas",
    "scoped_where",
    "validate_collection_name",
]
