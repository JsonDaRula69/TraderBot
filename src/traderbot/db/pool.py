"""Owner-thread SQLite connection pooling with fixed runtime optimizations."""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, final, override

_DEFAULT_MAX_CONNECTIONS_PER_PATH: Final = 4
_DEFAULT_CHECKOUT_TIMEOUT: Final = 5.0
_WRITABLE_PRAGMAS: Final = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA cache_size=-64000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA foreign_keys=ON",
)


@dataclass(frozen=True, slots=True)
class CrossThreadAccessError(RuntimeError):
    """Raised when a thread other than the pool owner accesses the pool."""

    owner_thread_id: int
    access_thread_id: int

    @override
    def __str__(self) -> str:
        return (
            f"SQLite pool belongs to thread {self.owner_thread_id}, "
            f"not thread {self.access_thread_id}"
        )


@dataclass(frozen=True, slots=True)
class ConnectionPoolTimeoutError(RuntimeError):
    """Raised when every handle for a database remains checked out."""

    path: Path
    readonly: bool
    max_connections: int
    timeout: float

    @override
    def __str__(self) -> str:
        mode = "read-only" if self.readonly else "writable"
        return (
            f"timed out after {self.timeout:.3f}s waiting for a {mode} SQLite handle "
            f"to {self.path} (capacity {self.max_connections})"
        )


class ConnectionPoolClosedError(RuntimeError):
    """Raised when a shut down pool receives another operation."""

    @override
    def __str__(self) -> str:
        return "SQLite connection pool is shut down"


@dataclass(frozen=True, slots=True)
class InvalidPoolConfigurationError(ValueError):
    """Raised when pool capacity or timeout configuration is invalid."""

    setting: str
    value: int | float

    @override
    def __str__(self) -> str:
        return f"invalid SQLite pool {self.setting}: {self.value}"


@final
class _PooledHandle:
    __slots__ = ("connection", "in_use", "readonly")

    def __init__(self, connection: sqlite3.Connection, *, readonly: bool) -> None:
        self.connection = connection
        self.readonly = readonly
        self.in_use = True


@final
class SQLiteConnectionPool:
    """Bounded reusable SQLite handles owned by one event-loop thread."""

    def __init__(
        self,
        max_connections_per_path: int = _DEFAULT_MAX_CONNECTIONS_PER_PATH,
        checkout_timeout: float = _DEFAULT_CHECKOUT_TIMEOUT,
    ) -> None:
        if max_connections_per_path <= 0:
            raise InvalidPoolConfigurationError(
                setting="max_connections_per_path",
                value=max_connections_per_path,
            )
        if checkout_timeout < 0:
            raise InvalidPoolConfigurationError(
                setting="checkout_timeout",
                value=checkout_timeout,
            )
        self._max_connections_per_path = max_connections_per_path
        self._checkout_timeout = checkout_timeout
        self._owner_thread_id = threading.get_ident()
        self._handles: dict[Path, list[_PooledHandle]] = {}
        self._closed = False

    @property
    def max_connections_per_path(self) -> int:
        return self._max_connections_per_path

    @property
    def checkout_timeout(self) -> float:
        return self._checkout_timeout

    @contextmanager
    def connection(
        self,
        path: str | Path,
        *,
        readonly: bool = False,
    ) -> Generator[sqlite3.Connection, None, None]:
        """Exclusively check out one handle and return it after transaction finalization."""
        self._validate_access()
        canonical_path = self._canonical_path(path)
        handle = self._checkout(canonical_path, readonly=readonly)
        try:
            yield handle.connection
        finally:
            try:
                if sys.exception() is None:
                    if not readonly:
                        handle.connection.commit()
                else:
                    handle.connection.rollback()
            finally:
                handle.in_use = False

    def checkpoint(self, path: str | Path) -> None:
        """Run a truncating WAL checkpoint for one database."""
        with self.connection(path) as connection:
            _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

    def shutdown(self) -> None:
        """Close every pooled handle and permanently reject further operations."""
        self._validate_owner_thread()
        if self._closed:
            return
        self._closed = True
        for handles in self._handles.values():
            for handle in handles:
                handle.connection.close()
        self._handles.clear()

    def _validate_access(self) -> None:
        self._validate_owner_thread()
        if self._closed:
            raise ConnectionPoolClosedError

    def _validate_owner_thread(self) -> None:
        access_thread_id = threading.get_ident()
        if access_thread_id != self._owner_thread_id:
            raise CrossThreadAccessError(
                owner_thread_id=self._owner_thread_id,
                access_thread_id=access_thread_id,
            )

    @staticmethod
    def _canonical_path(path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    def _checkout(self, path: Path, *, readonly: bool) -> _PooledHandle:
        handles = self._handles.setdefault(path, [])
        for handle in handles:
            if not handle.in_use and handle.readonly is readonly:
                handle.in_use = True
                return handle

        if len(handles) < self._max_connections_per_path:
            return self._create_handle(path, readonly=readonly, handles=handles)

        for handle in handles:
            if not handle.in_use:
                handle.connection.close()
                handles.remove(handle)
                return self._create_handle(path, readonly=readonly, handles=handles)

        time.sleep(self._checkout_timeout)
        raise ConnectionPoolTimeoutError(
            path=path,
            readonly=readonly,
            max_connections=self._max_connections_per_path,
            timeout=self._checkout_timeout,
        )

    @staticmethod
    def _create_handle(
        path: Path,
        *,
        readonly: bool,
        handles: list[_PooledHandle],
    ) -> _PooledHandle:
        if readonly:
            connection = sqlite3.connect(
                f"{path.as_uri()}?mode=ro",
                uri=True,
                check_same_thread=True,
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, check_same_thread=True)
            try:
                for pragma in _WRITABLE_PRAGMAS:
                    _ = connection.execute(pragma)
            except sqlite3.Error:
                connection.close()
                raise
        handle = _PooledHandle(connection, readonly=readonly)
        handles.append(handle)
        return handle


__all__ = [
    "ConnectionPoolClosedError",
    "ConnectionPoolTimeoutError",
    "CrossThreadAccessError",
    "InvalidPoolConfigurationError",
    "SQLiteConnectionPool",
]
