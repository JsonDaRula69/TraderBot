"""Define collector validation errors and prepared snapshot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import override


@dataclass(frozen=True, slots=True)
class CollectorPathError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid collector database path: {self.reason}"


@dataclass(frozen=True, slots=True)
class CollectorSchemaError(ValueError):
    table: str

    @override
    def __str__(self) -> str:
        return f"collector table {self.table!r} does not match the required schema"


@dataclass(frozen=True, slots=True)
class PreparedCollector:
    path: Path
    query_only: int
