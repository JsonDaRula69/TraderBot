"""Centralized path constants for TraderBot data directories."""

from __future__ import annotations

from pathlib import Path


def get_data_dir() -> Path:
    """Return the TraderBot data directory (default: ~/.traderbot)."""
    return Path.home() / ".traderbot"


def get_db_path() -> Path:
    """Return the TraderBot database path."""
    return get_data_dir() / "traderbot.db"


def get_audit_dir() -> Path:
    """Return the audit log directory."""
    return get_data_dir() / "audit"


def get_chromadb_dir() -> Path:
    """Return the ChromaDB directory."""
    return get_data_dir() / "chromadb"


def get_logs_dir() -> Path:
    """Return the logs directory."""
    return get_data_dir() / "logs"


def get_workspace_dir() -> Path:
    """Return the OpenClaw workspace directory (relative to CWD)."""
    return Path.cwd() / ".openclaw" / "workspace"


def ensure_data_dir() -> Path:
    """Create data directory if it doesn't exist and return it."""
    path = get_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
