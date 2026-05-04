"""Multi-agent trading profiles — runtime configuration for OpenClaw agents."""

from traderbot.profiles.auth import ProfileAuthStore
from traderbot.profiles.config import resolve_kalshi_credentials
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.runtime import (
    get_current_profile,
    get_runtime_context,
    load_profile_config,
)

__all__ = [
    "ProfileAuthStore",
    "ProfileRegistry",
    "TradingProfile",
    "get_current_profile",
    "get_runtime_context",
    "load_profile_config",
    "resolve_kalshi_credentials",
]

