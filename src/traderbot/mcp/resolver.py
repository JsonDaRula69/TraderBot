"""Token resolution for MCP tool calls (DD-025).

Phase 0: Hardcoded token-to-profile mapping.
Phase 1: Swaps to real auth via tokens.resolve_token() + ProfileRegistry.get_profile()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.profiles.dev_liaison import create_dev_liaison_profile
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.profiles.weather import create_weather_profile

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

# Profiles administratively suspended from real-auth resolution (Phase 1.5).
# Populated by the secret/security layer; resolution returns (None, None) for
# any profile in this set, so a suspended profile is indistinguishable from an
# invalid token.
_SUSPENDED_PROFILES: set[str] = set()

# Phase 0: Hardcoded token-to-profile mapping.
# Phase 1 will replace this with tokens.resolve_token().
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

    Phase 0: Hardcoded mapping. Phase 1: delegates to tokens.resolve_token().

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
    # Lazy init: install the SecretsStore-backed adapter on first real-auth
    # call. Guard: only install when the active store is the default
    # LocalTokenStore at ~/.traderbot — a test-injected store (different
    # path) is left untouched.
    from traderbot.profiles.tokens import (
        LocalTokenStore as _LocalTokenStore,
    )
    from traderbot.profiles.tokens import (
        get_store as _get_store,
    )
    from traderbot.profiles.tokens import (
        resolve_token as _real_resolve,
    )

    _active = _get_store()
    if isinstance(_active, _LocalTokenStore) and _active.base_path == Path.home() / ".traderbot":
        from traderbot.secrets.resolver import get_resolver as _get_resolver

        _ = _get_resolver()

    result = _real_resolve(token)
    if result is None:
        logger.warning(
            "Token resolution failed: %s", token[:4] + "..." if len(token) > 4 else token
        )
        return None, None

    profile_name, agent_id = result
    if profile_name is not None and profile_name in _SUSPENDED_PROFILES:
        return None, None

    from traderbot.profiles import ProfileRegistry

    registry = ProfileRegistry()
    profile = registry.get_profile(profile_name)
    if profile is None:
        logger.error("Profile not found: %s", profile_name)
        return None, None

    logger.info("Resolved token to profile=%s agent=%s (real auth)", profile_name, agent_id)
    return profile, agent_id
