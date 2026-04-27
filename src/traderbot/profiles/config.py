"""Credential resolution chain for profile-aware authentication."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from traderbot.auth import AuthManager
from traderbot.profiles.auth import ProfileAuthStore

if TYPE_CHECKING:
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
        profile_keyring: Optional keyring module for ProfileAuthStore (testing)

    Returns:
        Tuple of (api_key, api_secret)

    Raises:
        ValueError: If no credentials found in either profile or global
    """
    if profile is not None:
        profile_auth = ProfileAuthStore(profile, keyring_module=profile_keyring)
        profile_creds = profile_auth.get_credentials("kalshi")
        if profile_creds is not None:
            logger.info("Using Kalshi credentials from profile '%s'", profile.name)
            return profile_creds

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

    raise ValueError(
        "No Kalshi credentials configured. "
        "Set credentials via 'traderbot auth set kalshi' or profile-specific credentials."
    )


def resolve_newsapi_key(
    profile: TradingProfile | None,
    global_keyring: Any = None,
    profile_keyring: Any = None,
) -> str | None:
    """Resolve NewsAPI key using profile-aware fallback chain.

    Resolution order:
    1. If profile provided and has credentials → use profile keyring key
    2. Else → fall back to global AuthManager credentials
    3. Else → fall back to NEWSAPI_KEY environment variable
    4. Else → return None

    Args:
        profile: TradingProfile to check for credentials (optional)
        global_keyring: Optional keyring module for global AuthManager (testing)
        profile_keyring: Optional keyring module for ProfileAuthStore (testing)

    Returns:
        API key string if found, None otherwise
    """
    if profile is not None:
        profile_auth = ProfileAuthStore(profile, keyring_module=profile_keyring)
        profile_creds = profile_auth.get_credentials("newsapi")
        if profile_creds is not None:
            logger.info("Using NewsAPI key from profile '%s'", profile.name)
            return profile_creds[0]

    global_auth = AuthManager(keyring_module=global_keyring)
    key_result = global_auth.get_credential("newsapi", "api_key")
    if key_result is not None:
        if profile is not None:
            logger.info(
                "Profile '%s' has no NewsAPI key, using global credentials",
                profile.name,
            )
        else:
            logger.info("Using global NewsAPI credentials")
        return key_result.value.get_secret_value()

    env_key = os.environ.get("NEWSAPI_KEY")
    if env_key is not None:
        logger.debug("Using NewsAPI key from NEWSAPI_KEY environment variable")
        return env_key

    logger.warning("No NewsAPI key found in profile, global, or environment")
    return None


# Made with Bob
