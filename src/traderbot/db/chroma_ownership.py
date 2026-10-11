"""Exclusive ownership and cleanup errors for embedded Chroma roots."""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self, final, override

from traderbot.db.security import (
    InvalidChromaRootError,
    validate_chroma_lock_file,
    validate_chroma_root,
)


@final
class ChromaOwnershipError(RuntimeError):
    """Raised when another process owns the embedded Chroma root."""

    __slots__: tuple[str, str] = ("lock_path", "reason")
    lock_path: Path
    reason: str

    def __init__(self, lock_path: Path, reason: str) -> None:
        super().__init__(reason)
        self.lock_path = lock_path
        self.reason = reason

    @override
    def __str__(self) -> str:
        return f"cannot own Chroma lock {self.lock_path}: {self.reason}"


class ChromaCleanupError(ExceptionGroup):
    """Aggregates client and ownership-lock cleanup failures."""


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


__all__ = ["ChromaCleanupError", "ChromaOwnershipError", "ChromaOwnershipLock"]
