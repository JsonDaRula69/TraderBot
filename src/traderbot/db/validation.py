"""Storage-name validation for isolated TraderBot data paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, override

from traderbot.paths import get_data_dir

_STORAGE_NAME_PATTERN: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MAX_STORAGE_NAME_LENGTH: Final = 44
_RESERVED_STORAGE_NAMES: Final = frozenset({"sysadmin"})


@dataclass(frozen=True, slots=True)
class InvalidStorageNameError(RuntimeError):
    """Raised when a storage name cannot safely identify an isolated path."""

    name: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid storage name {self.name!r}: {self.reason}"


def validate_storage_name(name: str) -> str:
    """Return a canonical storage name whose resolved path stays in the data root."""
    if not name:
        raise InvalidStorageNameError(name, "name must not be empty")
    if len(name) > _MAX_STORAGE_NAME_LENGTH:
        raise InvalidStorageNameError(name, "name must be at most 44 characters")
    if ".." in name or "/" in name or "\\" in name:
        raise InvalidStorageNameError(name, "path traversal and separators are forbidden")
    if any(character in name for character in "*?["):
        raise InvalidStorageNameError(name, "glob characters are forbidden")
    if name != name.lower():
        raise InvalidStorageNameError(name, "uppercase characters are forbidden")
    if "_" in name:
        raise InvalidStorageNameError(name, "underscores are forbidden; use hyphens")
    if name in _RESERVED_STORAGE_NAMES:
        raise InvalidStorageNameError(name, "name is reserved for a canonical identity")
    if _STORAGE_NAME_PATTERN.fullmatch(name) is None:
        raise InvalidStorageNameError(name, "name must be lowercase hyphenated alphanumeric text")

    data_root = get_data_dir().resolve()
    resolved_path = (data_root / name).resolve()
    if not resolved_path.is_relative_to(data_root):
        raise InvalidStorageNameError(name, "resolved path is outside the TraderBot data directory")
    return name
