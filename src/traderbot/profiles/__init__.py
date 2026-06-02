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
from traderbot.profiles.sysadmin import create_sysadmin_profile

__all__ = [
    "ProfileAuthStore",
    "ProfileRegistry",
    "TradingProfile",
    "create_sysadmin_profile",
    "get_current_profile",
    "get_runtime_context",
    "load_profile_config",
    "resolve_kalshi_credentials",
]
