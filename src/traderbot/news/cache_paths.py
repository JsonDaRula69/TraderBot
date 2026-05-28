"""Profile-aware news cache path resolution."""

from __future__ import annotations

import logging

from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

_DEFAULT_NEWS_CACHE = get_data_dir() / "news_cache"


def get_news_cache_path(profile: TradingProfile | None = None) -> Path:
    """Return path to the news cache directory.

    Args:
        profile: Optional TradingProfile for per-profile isolation.

    Returns:
        Path to news_cache directory (profile-specific or default).
    """
    if profile is not None:
        path = Path(profile.base_dir) / "news_cache"
        logger.debug("Cache path (profile): %s", path)
        return path
    logger.debug("Cache path (default): %s", _DEFAULT_NEWS_CACHE)
    return _DEFAULT_NEWS_CACHE


def ensure_news_cache_dir(profile: TradingProfile | None = None) -> Path:
    """Create the news cache directory if it doesn't exist and return it."""
    path = get_news_cache_path(profile)
    path.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured news cache dir: %s", path)
    return path
