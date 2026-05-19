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
    from traderbot.profiles.isolation import get_profile_audit_path
    from traderbot.profiles.runtime import get_current_profile

    profile = get_current_profile()
    if profile is not None:
        return get_profile_audit_path(profile)
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


def list_all_data_paths() -> list[Path]:
    """Return all well-known paths that TraderBot creates at runtime.

    Used by the uninstall command to enumerate files for removal.
    Does NOT include the repo/install directory or venv — only runtime data.
    """
    base = get_data_dir()
    paths: list[Path] = [
        base / ".env",
        base / ".profile_key",
        base / "profiles.enc",
        base / "profiles.json",  # legacy
        base / "update_config.json",
        base / ".update_check_cache.json",
        base / "circuit_breaker_state.json",
        base / ".breaker_secret",
        base / "traderbot.db",  # legacy global DB
        base / "audit",
        base / "chromadb",
        base / "logs",
    ]
    # Per-profile directories: {mode}-{name}/db, chroma, audit
    if base.exists():
        for child in base.iterdir():
            if child.is_dir() and "-" in child.name:
                for subdir in ("db", "chroma", "audit"):
                    candidate = child / subdir
                    if candidate.exists():
                        paths.append(candidate)
    return paths
