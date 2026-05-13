"""Per-agent data isolation — path resolution for SQLite, ChromaDB, and audit directories.

Each profile gets its own directory tree under ~/.traderbot/{mode}-{name}/
so that multiple agents running in the same mode don't share state.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.paths import get_data_dir

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def get_profile_db_path(profile: TradingProfile, db_name: str) -> Path:
    """Return path to profile-specific SQLite database.

    Args:
        profile: The trading profile
        db_name: Name of the database file (e.g., "decisions.db")

    Returns:
        Path to the database file (e.g., "~/.traderbot/paper-weather/db/decisions.db")
    """
    return Path(profile.base_dir) / "db" / db_name


def get_profile_chroma_path(profile: TradingProfile) -> Path:
    """Return path to profile-specific ChromaDB directory.

    Args:
        profile: The trading profile

    Returns:
        Path to the ChromaDB directory (e.g., "~/.traderbot/paper-weather/chroma")
    """
    return Path(profile.base_dir) / "chroma"


def get_profile_audit_path(profile: TradingProfile) -> Path:
    """Return path to profile-specific audit directory.

    Args:
        profile: The trading profile

    Returns:
        Path to the audit directory (e.g., "~/.traderbot/paper-weather/audit")
    """
    return Path(profile.base_dir) / "audit"


def _migrate_legacy_db(profile: TradingProfile) -> None:
    """One-time migration from pre-isolation DB to per-agent DB.

    Migrates data from the legacy path (~/.traderbot/{mode}/db/decisions.db
    or ~/.traderbot/traderbot.db) into the per-agent path if the per-agent
    DB is empty and a legacy DB exists.
    """
    new_db = get_profile_db_path(profile, "decisions.db")
    if new_db.exists() and new_db.stat().st_size > 0:
        return

    legacy_paths = [
        get_data_dir() / profile.mode / "db" / "decisions.db",
        get_data_dir() / "traderbot.db",
    ]

    for legacy_db in legacy_paths:
        if not legacy_db.exists() or legacy_db.stat().st_size == 0:
            continue

        new_db.parent.mkdir(parents=True, exist_ok=True)
        try:
            src = sqlite3.connect(str(legacy_db))
            dst = sqlite3.connect(str(new_db))
            for line in src.iterdump():
                dst.execute(line)
            dst.commit()
            dst.close()
            src.close()
            logger.info("Migrated %d bytes from %s to %s", legacy_db.stat().st_size, legacy_db, new_db)
            return
        except Exception:
            logger.warning("DB migration from %s failed (non-fatal)", legacy_db, exc_info=True)
            if new_db.exists():
                new_db.unlink(missing_ok=True)
            return


def ensure_profile_dirs(profile: TradingProfile) -> None:
    """Create all profile directories if they don't exist.

    Creates:
        - {base_dir}/db/
        - {base_dir}/chroma/
        - {base_dir}/audit/

    Also performs one-time DB migration from legacy paths.

    Args:
        profile: The trading profile
    """
    base = Path(profile.base_dir)
    (base / "db").mkdir(parents=True, exist_ok=True)
    (base / "chroma").mkdir(parents=True, exist_ok=True)
    (base / "audit").mkdir(parents=True, exist_ok=True)

    _migrate_legacy_db(profile)

