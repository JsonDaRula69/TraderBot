"""Typed requests and records for category-scoped Chroma operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import override

from traderbot.kalshi.models import MarketCategory

type MetadataValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class ChromaCategoryError(RuntimeError):
    """Raised when caller metadata conflicts with its authorized category."""

    category: MarketCategory
    supplied: MetadataValue

    @override
    def __str__(self) -> str:
        return f"metadata category {self.supplied!r} conflicts with {self.category.value!r}"


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
    "ChromaQueryRequest",
    "ChromaRecord",
    "MetadataValue",
]
