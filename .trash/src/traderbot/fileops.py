"""Cross-platform file operations for Windows/Linux/macOS parity."""

from __future__ import annotations

import sys
from typing import IO, TYPE_CHECKING

import portalocker

if TYPE_CHECKING:
    from pathlib import Path

LOCK_SHARED = portalocker.LockFlags.SHARED
LOCK_EXCLUSIVE = portalocker.LockFlags.EXCLUSIVE
LOCK_NON_BLOCKING = portalocker.LockFlags.NON_BLOCKING


def lock_file(fh: IO[str], flags: int) -> None:
    """Acquire a file lock using portalocker (cross-platform)."""
    portalocker.lock(fh, flags)


def unlock_file(fh: IO[str]) -> None:
    """Release a file lock using portalocker (cross-platform)."""
    portalocker.unlock(fh)


def set_file_owner_only(path: Path) -> None:
    """Restrict file permissions to owner-only (0o600).

    On Windows, this is a no-op because NTFS ACLs handle security differently
    and the chmod call would raise or be silently ignored. On Unix, it sets 0o600.
    """
    if sys.platform == "win32":
        return
    path.chmod(0o600)


def set_dir_owner_only(path: Path) -> None:
    """Restrict directory permissions to owner-only (0o700).

    On Windows, this is a no-op. On Unix, it sets 0o700.
    """
    if sys.platform == "win32":
        return
    path.chmod(0o700)
