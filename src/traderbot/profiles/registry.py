"""ProfileRegistry — loads trading profiles from factory functions (DD-025)."""

from __future__ import annotations

import logging

from traderbot.profiles.dev_liaison import create_dev_liaison_profile
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.profiles.weather import create_weather_profile

logger = logging.getLogger(__name__)


class ProfileRegistry:
    """Registry of trading profiles, each loaded from its factory function.

    A fresh instance is built on every instantiation; it is not a singleton.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, TradingProfile] = {
            p.name: p
            for p in (
                create_sysadmin_profile(),
                create_dev_liaison_profile(),
                create_weather_profile(),
            )
        }

    def get_profile(self, name: str) -> TradingProfile | None:
        """Return the profile with ``name``, or None if not found."""
        return self._profiles.get(name)

    def list_profiles(self) -> dict[str, dict[str, object]]:
        """Return a summary of every profile for the profile_list MCP tool."""
        summary: dict[str, dict[str, object]] = {}
        for name, profile in self._profiles.items():
            categories = [c.value for c in profile.enabled_categories] or ["all"]
            summary[name] = {
                "mode": profile.mode,
                "categories": categories,
                "permissions": profile.permissions or ["all"],
            }
        return summary
