"""Multi-agent trading profiles — runtime configuration for OpenClaw agents."""

from traderbot.profiles.auth import ProfileAuthManager
from traderbot.profiles.config import resolve_kalshi_credentials
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry

__all__ = ["TradingProfile", "ProfileRegistry", "ProfileAuthManager", "resolve_kalshi_credentials"]

# Made with Bob
