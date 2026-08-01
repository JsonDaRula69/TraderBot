"""Token resolution for MCP tool calls (DD-025).

Phase 0: Hardcoded token-to-profile mapping.
Phase 1: Swaps to real ProfileRegistry.resolve_token() with zero tool code changes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from traderbot.profiles.dev_liaison import create_dev_liaison_profile
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.profiles.weather import create_weather_profile

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

# Phase 0: Hardcoded token-to-profile mapping.
# Phase 1 will replace this with ProfileRegistry.resolve_token().
_HARDCODED_TOKENS: dict[str, tuple[str, str]] = {
    "sysadmin-test-token": ("sysadmin", "sysadmin"),
    "dev-liaison-test-token": ("dev-liaison", "dev-liaison"),
    "weather-test-token": ("weather", "weather"),
}

_HARDCODED_PROFILES: dict[str, TradingProfile] = {
    "sysadmin": create_sysadmin_profile(),
    "dev-liaison": create_dev_liaison_profile(),
    "weather": create_weather_profile(),
}


def resolve_token_adapter(token: str) -> tuple[TradingProfile | None, str | None]:
    """Resolve a profile token to (TradingProfile, agent_id).

    Phase 0: Hardcoded mapping. Phase 1: delegates to ProfileRegistry.resolve_token().

    Args:
        token: The profile token from the MCP tool call.

    Returns:
        Tuple of (TradingProfile or None, agent_id or None).
        None values indicate an invalid/expired token.
    """
    import os

    use_hardcoded = os.environ.get("TRADERBOT_USE_HARDCODED_AUTH", "1")

    if use_hardcoded != "0":
        # Phase 0: hardcoded auth
        entry = _HARDCODED_TOKENS.get(token)
        if entry is None:
            logger.warning("Invalid token: %s", token[:4] + "..." if len(token) > 4 else token)
            return None, None
        profile_name, agent_id = entry
        profile = _HARDCODED_PROFILES.get(profile_name)
        if profile is None:
            logger.error("No hardcoded profile for: %s", profile_name)
            return None, None
        logger.info("Resolved token to profile=%s agent=%s (hardcoded)", profile_name, agent_id)
        return profile, agent_id

    # Phase 1: real auth via ProfileRegistry
    from traderbot.profiles.tokens import resolve_token as _real_resolve

    result = _real_resolve(token)
    if result is None:
        logger.warning(
            "Token resolution failed: %s", token[:4] + "..." if len(token) > 4 else token
        )
        return None, None

    profile_name, agent_id = result
    from traderbot.profiles import ProfileRegistry

    registry = ProfileRegistry()
    profile = registry.get_profile(profile_name)
    if profile is None:
        logger.error("Profile not found: %s", profile_name)
        return None, None

    logger.info("Resolved token to profile=%s agent=%s (real auth)", profile_name, agent_id)
    return profile, agent_id
