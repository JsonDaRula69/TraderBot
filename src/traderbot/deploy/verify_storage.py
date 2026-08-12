from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import Final

from traderbot.db.security import InvalidChromaRootError, validate_chroma_lock_file
from traderbot.deploy.verify_models import ProbeResult, VerificationRequest
from traderbot.deploy.verify_schema import (
    DECISIONS_INDEXES,
    DECISIONS_SCHEMA_VERSION,
    DECISIONS_TABLES,
    GLOBAL_INDEXES,
    GLOBAL_SCHEMA_VERSION,
    GLOBAL_TABLES,
)

_READ_ONLY_PRAGMAS: Final = (
    "PRAGMA query_only=ON",
    "PRAGMA quick_check",
    "SELECT MAX(version) FROM schema_version",
)


def _names(connection: sqlite3.Connection, kind: str) -> set[str]:
    cursor = connection.execute(
        "SELECT name FROM sqlite_master WHERE type=? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    )
    rows: list[tuple[str]] = cursor.fetchall()
    return {row[0] for row in rows}


def _secure_file(path: Path, root: Path) -> bool:
    if not path.absolute().is_relative_to(root.absolute()):
        return False
    try:
        root_info = root.lstat()
        info = path.lstat()
        candidate = root
        for part in path.relative_to(root).parts[:-1]:
            candidate /= part
            candidate_info = candidate.lstat()
            if stat.S_ISLNK(candidate_info.st_mode) or not stat.S_ISDIR(candidate_info.st_mode):
                return False
    except OSError:
        return False
    if stat.S_ISLNK(root_info.st_mode) or stat.S_ISLNK(info.st_mode):
        return False
    if not stat.S_ISDIR(root_info.st_mode) or not stat.S_ISREG(info.st_mode):
        return False
    if os.name != "nt" and (root_info.st_uid != os.getuid() or info.st_uid != os.getuid()):
        return False
    return os.name == "nt" or stat.S_IMODE(info.st_mode) & 0o022 == 0


def _sqlite_probe(
    path: Path,
    root: Path,
    latest: int,
    tables: set[str],
    indexes: set[str],
) -> bool:
    if not _secure_file(path, root):
        return False
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as connection:
            _ = connection.execute(_READ_ONLY_PRAGMAS[0])
            if connection.execute(_READ_ONLY_PRAGMAS[1]).fetchone() != ("ok",):
                return False
            if connection.execute(_READ_ONLY_PRAGMAS[2]).fetchone() != (latest,):
                return False
            actual_tables = _names(connection, "table")
            actual_indexes = _names(connection, "index")
            return actual_tables == tables and actual_indexes == indexes
    except sqlite3.Error:
        return False


def global_database(request: VerificationRequest) -> ProbeResult:
    path = request.data_root / "traderbot.db"
    if not _sqlite_probe(
        path, request.data_root, GLOBAL_SCHEMA_VERSION, set(GLOBAL_TABLES), set(GLOBAL_INDEXES)
    ):
        return ProbeResult.failed("global_db_invalid", "Global database contract differs")
    return ProbeResult.passed("global_db_exact")


def decisions_databases(request: VerificationRequest) -> ProbeResult:
    for mode in ("backtest", "paper", "live"):
        forbidden = request.data_root / f"{mode}-sysadmin" / "db" / "decisions.db"
        if os.path.lexists(forbidden):
            return ProbeResult.failed("sysadmin_db_forbidden", "SysAdmin decisions database exists")
    for category in request.categories:
        path = request.data_root / f"{request.mode}-{category.value}" / "db" / "decisions.db"
        if not _sqlite_probe(
            path,
            request.data_root,
            DECISIONS_SCHEMA_VERSION,
            set(DECISIONS_TABLES),
            set(DECISIONS_INDEXES),
        ):
            return ProbeResult.failed("decisions_db_invalid", "A selected decisions DB differs")
    return ProbeResult.passed("decisions_db_exact")


def chroma_offline(request: VerificationRequest) -> ProbeResult:
    root = request.data_root / "chromadb"
    if not os.path.lexists(root):
        return ProbeResult.failed("chroma_root_missing", "Chroma root is absent")
    if not root.absolute().is_relative_to(request.data_root.absolute()):
        return ProbeResult.failed("chroma_root_invalid", "Chroma root is outside data root")
    try:
        root_info = root.lstat()
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise InvalidChromaRootError(root, "root must be a non-symlink directory")
        if os.name != "nt":
            if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
                raise InvalidChromaRootError(root, "root ownership or mode differs")
        validate_chroma_lock_file(root / "chromadb.lock")
        for child in root.rglob("*"):
            child_info = child.lstat()
            if stat.S_ISLNK(child_info.st_mode):
                raise InvalidChromaRootError(child, "linked Chroma entry is forbidden")
            if not (stat.S_ISDIR(child_info.st_mode) or stat.S_ISREG(child_info.st_mode)):
                raise InvalidChromaRootError(child, "unsupported Chroma entry type")
            if os.name != "nt" and child_info.st_uid != os.getuid():
                raise InvalidChromaRootError(child, "Chroma entry owner differs")
            if os.name != "nt" and stat.S_IMODE(child_info.st_mode) & 0o022:
                raise InvalidChromaRootError(child, "Chroma entry mode is unsafe")
    except (InvalidChromaRootError, OSError):
        return ProbeResult.failed("chroma_root_invalid", "Chroma ownership metadata differs")
    return ProbeResult.degraded("chroma_runtime_unverified", "Daemon runtime does not own Chroma")


__all__ = ["chroma_offline", "decisions_databases", "global_database"]
