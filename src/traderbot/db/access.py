"""Identity- and mode-scoped access to per-profile decisions databases."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, final, override

from traderbot.db.decisions import init_decisions_db
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.validation import validate_storage_name
from traderbot.profiles.models import TradingProfile

type DatabaseIdentity = tuple[TradingProfile, str]
type TradingMode = Literal["backtest", "paper", "live"]

_SYSADMIN: Final = "sysadmin"
_MODE_ORDER: Final[tuple[TradingMode, ...]] = ("backtest", "paper", "live")
_READABLE_MODES: Final[dict[TradingMode, tuple[TradingMode, ...]]] = {
    "backtest": ("backtest",),
    "paper": ("backtest", "paper"),
    "live": _MODE_ORDER,
}


@dataclass(frozen=True, slots=True)
class DatabaseAccessDeniedError(RuntimeError):
    """Raised when a resolved identity is not authorized for an access operation."""

    profile: str
    agent_id: str
    operation: str

    @override
    def __str__(self) -> str:
        return (
            f"database access denied for profile={self.profile!r} "
            f"agent_id={self.agent_id!r}: {self.operation}"
        )


@dataclass(frozen=True, slots=True)
class InvalidDatabasePathError(RuntimeError):
    """Raised when a derived database path is unsafe or outside its data root."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid database path {self.path}: {self.reason}"


@final
class DatabaseAccess:
    """Route resolved identities to authorized pooled decisions databases."""

    def __init__(self, pool: SQLiteConnectionPool, data_root: Path) -> None:
        self._pool = pool
        self._data_root = data_root.expanduser().absolute()
        self._resolved_root = self._data_root.resolve()

    @contextmanager
    def writable_decisions(
        self, identity: DatabaseIdentity
    ) -> Generator[sqlite3.Connection, None, None]:
        """Yield the current-mode writable database for a category identity."""
        profile, profile_name = self._category_identity(identity, "write decisions")
        path = self._decisions_path(profile.mode, profile_name)
        init_decisions_db(path)
        with self._pool.connection(path) as connection:
            yield connection

    @contextmanager
    def readable_decisions(
        self, identity: DatabaseIdentity
    ) -> Generator[tuple[sqlite3.Connection, ...], None, None]:
        """Yield existing read-only databases visible from the profile's current mode."""
        profile, profile_name = self._category_identity(identity, "read decisions")
        paths = tuple(
            path
            for mode in self._readable_modes(profile.mode)
            if (path := self._decisions_path(mode, profile_name)).is_file()
        )
        with self._readonly_connections(paths) as connections:
            yield connections

    @contextmanager
    def all_agent_decisions(
        self, identity: DatabaseIdentity
    ) -> Generator[tuple[sqlite3.Connection, ...], None, None]:
        """Yield every existing per-profile decisions database to canonical SysAdmin."""
        profile, agent_id = identity
        if profile.name != _SYSADMIN or agent_id != _SYSADMIN:
            raise DatabaseAccessDeniedError(profile.name, agent_id, "enumerate agent decisions")

        paths = tuple(self._existing_agent_paths())
        with self._readonly_connections(paths) as connections:
            yield connections

    def _category_identity(
        self, identity: DatabaseIdentity, operation: str
    ) -> tuple[TradingProfile, str]:
        profile, agent_id = identity
        if profile.name == _SYSADMIN or agent_id == _SYSADMIN:
            raise DatabaseAccessDeniedError(profile.name, agent_id, operation)
        profile_name = validate_storage_name(profile.name)
        _ = validate_storage_name(agent_id)
        return profile, profile_name

    def _decisions_path(self, mode: TradingMode, profile_name: str) -> Path:
        path = self._data_root / f"{mode}-{profile_name}" / "db" / "decisions.db"
        return self._validated_path(path)

    def _validated_path(self, path: Path) -> Path:
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(self._resolved_root):
            raise InvalidDatabasePathError(path, "resolved path escapes the configured data root")

        candidate = self._data_root
        if candidate.is_symlink():
            raise InvalidDatabasePathError(candidate, "symbolic links are forbidden")
        for part in path.relative_to(self._data_root).parts:
            candidate /= part
            if candidate.is_symlink():
                raise InvalidDatabasePathError(candidate, "symbolic links are forbidden")
        return resolved_path

    @staticmethod
    def _readable_modes(mode: TradingMode) -> tuple[TradingMode, ...]:
        return _READABLE_MODES[mode]

    def _existing_agent_paths(self) -> Generator[Path, None, None]:
        if not self._data_root.exists():
            return
        for mode in _MODE_ORDER:
            prefix = f"{mode}-"
            for path in sorted(self._data_root.glob(f"{prefix}*/db/decisions.db")):
                profile_name = path.parents[1].name.removeprefix(prefix)
                _ = validate_storage_name(profile_name)
                validated_path = self._validated_path(path)
                if validated_path.is_file():
                    yield validated_path

    @contextmanager
    def _readonly_connections(
        self, paths: tuple[Path, ...]
    ) -> Generator[tuple[sqlite3.Connection, ...], None, None]:
        with ExitStack() as stack:
            connections = tuple(
                stack.enter_context(self._pool.connection(path, readonly=True)) for path in paths
            )
            yield connections


__all__ = [
    "DatabaseAccess",
    "DatabaseAccessDeniedError",
    "DatabaseIdentity",
    "InvalidDatabasePathError",
]
