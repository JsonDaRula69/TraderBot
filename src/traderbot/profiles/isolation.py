"""Per-profile data isolation — path resolution for SQLite, ChromaDB, and audit directories."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile


def get_profile_db_path(profile: TradingProfile, db_name: str) -> Path:
    """Return path to profile-specific SQLite database.
    
    Args:
        profile: The trading profile
        db_name: Name of the database file (e.g., "decisions.db")
        
    Returns:
        Path to the database file (e.g., ".traderbot-paper/db/decisions.db")
    """
    return Path(profile.base_dir) / "db" / db_name


def get_profile_chroma_path(profile: TradingProfile) -> Path:
    """Return path to profile-specific ChromaDB directory.
    
    Args:
        profile: The trading profile
        
    Returns:
        Path to the ChromaDB directory (e.g., ".traderbot-paper/chroma")
    """
    return Path(profile.base_dir) / "chroma"


def get_profile_audit_path(profile: TradingProfile) -> Path:
    """Return path to profile-specific audit directory.
    
    Args:
        profile: The trading profile
        
    Returns:
        Path to the audit directory (e.g., ".traderbot-paper/audit")
    """
    return Path(profile.base_dir) / "audit"


def ensure_profile_dirs(profile: TradingProfile) -> None:
    """Create all profile directories if they don't exist.
    
    Creates:
        - {base_dir}/db/
        - {base_dir}/chroma/
        - {base_dir}/audit/
        
    Args:
        profile: The trading profile
    """
    base = Path(profile.base_dir)
    (base / "db").mkdir(parents=True, exist_ok=True)
    (base / "chroma").mkdir(parents=True, exist_ok=True)
    (base / "audit").mkdir(parents=True, exist_ok=True)

# Made with Bob
