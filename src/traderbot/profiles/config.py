"""Credential resolution chain for profile-aware authentication."""

from __future__ import annotations

import logging
import os
from pathlib import Path
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
    1. Profile keyring credentials (traderbot.profiles.{name}.kalshi)
    2. Profile-scoped .env vars (KALSHI_API_KEY_PROFILE_{NAME}, etc.)
    3. Global AuthManager credentials (keyring then .env)
    4. raise ValueError
    """
    if profile is not None:
        profile_auth = ProfileAuthStore(profile, keyring_module=profile_keyring)
        profile_creds = profile_auth.get_credentials("kalshi")
        if profile_creds is not None:
            logger.info("Using Kalshi credentials from profile '%s'", profile.name)
            return profile_creds

        profile_prefix = profile.name.upper().replace("-", "_").replace(" ", "_")
        profile_api_key = os.environ.get(f"KALSHI_API_KEY_PROFILE_{profile_prefix}")
        profile_pem = os.environ.get(f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{profile_prefix}")
        if not profile_pem:
            profile_path = os.environ.get(f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{profile_prefix}")
            if profile_path:
                from pathlib import Path
                p = Path(profile_path)
                if p.is_file():
                    profile_pem = p.read_text()

        if not profile_api_key or not profile_pem:
            from traderbot.paths import get_data_dir
            env_path = get_data_dir() / ".env"
            if env_path.exists():
                profile_api_key = profile_api_key or _env_file_get_value(env_path, f"KALSHI_API_KEY_PROFILE_{profile_prefix}")
                profile_pem = profile_pem or _env_file_get_value(env_path, f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{profile_prefix}")
                if not profile_pem:
                    profile_path = _env_file_get_value(env_path, f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{profile_prefix}")
                    if profile_path:
                        from pathlib import Path
                        p = Path(profile_path)
                        if p.is_file():
                            profile_pem = p.read_text()

        if profile_api_key and profile_pem:
            logger.info("Using Kalshi credentials from profile '%s' .env", profile.name)
            return (profile_api_key, profile_pem)

    global_auth = AuthManager(keyring_module=global_keyring)
    key_result = global_auth.get_credential("kalshi", "api_key")
    private_key_result = global_auth.get_credential("kalshi", "private_key_pem")

    if key_result is not None and private_key_result is not None:
        if profile is not None:
            logger.info(
                "Profile '%s' has no Kalshi credentials, using global credentials",
                profile.name,
            )
        else:
            logger.info("Using global Kalshi credentials")
        return (key_result.value.get_secret_value(), private_key_result.value.get_secret_value())

    raise ValueError(
        "No Kalshi credentials configured. "
        "Set credentials via 'traderbot auth login', profile-specific credentials, "
        "or KALSHI_API_KEY_PROFILE_{NAME} env vars."
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
    3. Else → fall back to global .env file (~/.traderbot/.env)
    4. Else → fall back to NEWSAPI_API_KEY environment variable
    5. Else → return None

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

    from traderbot.paths import get_data_dir

    env_path = get_data_dir() / ".env"
    if env_path.exists():
        for env_name in ("NEWSAPI_API_KEY", "NEWSAPI_KEY"):
            env_value = _env_file_get_value(env_path, env_name)
            if env_value is not None:
                logger.debug("Using NewsAPI key from %s in %s", env_name, env_path)
                return env_value

    for env_name in ("NEWSAPI_API_KEY", "NEWSAPI_KEY"):
        env_key = os.environ.get(env_name)
        if env_key is not None:
            logger.debug("Using NewsAPI key from %s environment variable", env_name)
            return env_key

    logger.warning("No NewsAPI key found in profile, global, or environment")
    return None


def _env_file_get_value(env_path: Path, key: str) -> str | None:
    """Read a specific key from a .env file (without loading into os.environ).

    Args:
        env_path: Path to the .env file
        key: The key to look up (e.g. 'KALSHI_API_KEY_PROFILE_MENTIONS')

    Returns:
        The value string if found, None otherwise
    """
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip("'\"")
    return None


