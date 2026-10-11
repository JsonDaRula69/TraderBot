from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationBackupError(RuntimeError):
    pass


def _backup_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _reserve_backup_path(db_path: Path) -> Path:
    for _attempt in range(100):
        candidate = db_path.with_name(
            f"{db_path.name}.bak.{_backup_timestamp()}-{secrets.token_hex(4)}"
        )
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return candidate
    raise MigrationBackupError(f"could not reserve a backup name for {db_path}")


def _fsync_path(path: Path, *, best_effort: bool) -> None:
    flags = os.O_RDWR if sys.platform == "win32" else os.O_RDONLY
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if not best_effort:
            raise
        logger.warning(
            "migration.backup_directory_fsync_best_effort",
            extra={"directory": str(path), "error": str(exc)},
        )
        return
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if not best_effort:
            raise
        logger.warning(
            "migration.backup_directory_fsync_best_effort",
            extra={"directory": str(path), "error": str(exc)},
        )
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if not best_effort:
                raise
            logger.warning(
                "migration.backup_directory_fsync_best_effort",
                extra={"directory": str(path), "error": str(exc)},
            )


def backup_legacy_database(db_path: Path) -> Path:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{db_path.name}.backup-", dir=db_path.parent)
    os.close(descriptor)
    temp_path = Path(temp_name)
    backup_path: Path | None = None
    published = False
    try:
        with (
            closing(sqlite3.connect(db_path)) as source,
            closing(sqlite3.connect(temp_path)) as target,
        ):
            source.backup(target)
        _fsync_path(temp_path, best_effort=False)
        backup_path = _reserve_backup_path(db_path)
        os.replace(temp_path, backup_path)
        published = True
        _fsync_path(db_path.parent, best_effort=sys.platform == "win32")
        return backup_path
    finally:
        if not published:
            _ = temp_path.unlink(missing_ok=True)
            if backup_path is not None:
                _ = backup_path.unlink(missing_ok=True)
