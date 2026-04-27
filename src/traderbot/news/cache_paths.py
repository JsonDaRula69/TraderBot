"""Profile-aware news cache path resolution."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

_DEFAULT_NEWS_CACHE = Path(".traderbot") / "news_cache"


def get_news_cache_path(profile: TradingProfile | None = None) -> Path:
    """Return path to the news cache directory.

    Args:
        profile: Optional TradingProfile for per-profile isolation.

    Returns:
        Path to news_cache directory (profile-specific or default).
    """
    if profile is not None:
        return Path(profile.base_dir) / "news_cache"
    return _DEFAULT_NEWS_CACHE


def ensure_news_cache_dir(profile: TradingProfile | None = None) -> Path:
    """Create the news cache directory if it doesn't exist and return it."""
    path = get_news_cache_path(profile)
    path.mkdir(parents=True, exist_ok=True)
    return path
