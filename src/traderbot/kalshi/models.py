"""Kalshi market models — v2 minimal types for Phase 0.

Full market data models will be added in Phase 2 (Always-On Service + Data Pipeline).
Phase 0 only needs MarketCategory for profile construction.
"""

from __future__ import annotations

from enum import StrEnum


class MarketCategory(StrEnum):
    """Kalshi market categories.

    Used by TradingProfile.enabled_categories for per-agent
    category isolation (DD-011).
    """

    WEATHER = "weather"
    ECONOMICS = "economics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    POLITICS = "politics"
    ENTERTAINMENT = "entertainment"
    FINANCIAL = "financial"
    WORLD = "world"
    OTHER = "other"
