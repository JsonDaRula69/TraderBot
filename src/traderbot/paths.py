"""Centralized path constants for TraderBot data directories (v2).

Minimal v2 module — Phase 0 only needs the data directory for profile
state isolation (DD-032). Grows as the service (DD-016) and secrets
store (DD-037) land in later phases.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """Return the TraderBot data directory (default: ~/.traderbot)."""
    return Path.home() / ".traderbot"


def get_db_path() -> Path:
    """Return the global TraderBot SQLite database path.

    All always-on data (WS cache, weather snapshots, collected feeds) shares
    ``~/.traderbot/traderbot.db`` so agents query one local database.
    """
    return get_data_dir() / "traderbot.db"
