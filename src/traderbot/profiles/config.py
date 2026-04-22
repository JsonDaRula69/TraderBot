"""Credential resolution chain for profile-aware authentication."""

from __future__ import annotations

import logging
from typing import Any

from traderbot.auth import AuthManager
from traderbot.profiles.auth import ProfileAuthManager
from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def resolve_kalshi_credentials(
    profile: TradingProfile | None,
    global_keyring: Any = None,
    profile_keyring: Any = None,
) -> tuple[str, str]:
    """Resolve Kalshi credentials using profile-aware fallback chain.
    
    Resolution order:
    1. If profile provided and has credentials → use profile credentials
    2. Else → fall back to global AuthManager credentials
    3. Else → raise ValueError
    
    Args:
        profile: TradingProfile to check for credentials (optional)
        global_keyring: Optional keyring module for global AuthManager (testing)
        profile_keyring: Optional keyring module for ProfileAuthManager (testing)
        
    Returns:
        Tuple of (api_key, api_secret)
        
    Raises:
        ValueError: If no credentials found in either profile or global
    """
    # Try profile credentials first
    if profile is not None:
        profile_auth = ProfileAuthManager(profile, keyring_module=profile_keyring)
        profile_creds = profile_auth.get_credentials("kalshi")
        if profile_creds is not None:
            logger.info("Using Kalshi credentials from profile '%s'", profile.name)
            return profile_creds
    
    # Fall back to global credentials
    global_auth = AuthManager(keyring_module=global_keyring)
    key_result = global_auth.get_credential("kalshi", "api_key")
    secret_result = global_auth.get_credential("kalshi", "api_secret")
    
    if key_result is not None and secret_result is not None:
        if profile is not None:
            logger.info(
                "Profile '%s' has no Kalshi credentials, using global credentials",
                profile.name,
            )
        else:
            logger.info("Using global Kalshi credentials")
        return (key_result.value.get_secret_value(), secret_result.value.get_secret_value())
    
    # No credentials found anywhere
    raise ValueError(
        "No Kalshi credentials configured. "
        "Set credentials via 'traderbot auth set kalshi' or profile-specific credentials."
    )


# Made with Bob