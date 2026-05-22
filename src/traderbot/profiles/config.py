"""Credential resolution via .env file and environment variables."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.auth import AuthManager

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def resolve_kalshi_credentials(
    profile: TradingProfile | None,
) -> tuple[str, str]:
    """Resolve Kalshi credentials using env fallback chain.

    Resolution order:
    1. Profile-scoped env vars (KALSHI_API_KEY_PROFILE_{NAME}, etc.)
    2. Global AuthManager credentials (.env then env vars)
    3. raise ValueError
    """
    if profile is not None:
        from traderbot.profiles.auth import ProfileAuthStore
        profile_auth = ProfileAuthStore(profile)
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
                        p = Path(profile_path)
                        if p.is_file():
                            profile_pem = p.read_text()

        if profile_api_key and profile_pem:
            logger.info("Using Kalshi credentials from profile '%s' .env", profile.name)
            return (profile_api_key, profile_pem)

    global_auth = AuthManager()
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
        "Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PEM in .env or environment."
    )


def resolve_newsapi_key(
    profile: TradingProfile | None,
) -> str | None:
    """Resolve NewsAPI key using env fallback chain.

    Resolution order:
    1. Profile-scoped env vars
    2. Global AuthManager credentials (.env then env vars)
    3. Global .env file
    4. Environment variable
    5. return None
    """
    if profile is not None:
        from traderbot.profiles.auth import ProfileAuthStore
        profile_auth = ProfileAuthStore(profile)
        profile_creds = profile_auth.get_credentials("newsapi")
        if profile_creds is not None:
            logger.info("Using NewsAPI key from profile '%s'", profile.name)
            return profile_creds[0]

    global_auth = AuthManager()
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


def resolve_openweather_key(
    profile: TradingProfile | None,
) -> str | None:
    """Resolve OpenWeather API key using env fallback chain."""
    if profile is not None:
        from traderbot.profiles.auth import ProfileAuthStore
        profile_auth = ProfileAuthStore(profile)
        profile_creds = profile_auth.get_credentials("openweathermap")
        if profile_creds is not None:
            logger.info("Using OpenWeather key from profile '%s'", profile.name)
            return profile_creds[0]

    global_auth = AuthManager()
    key_result = global_auth.get_credential("openweathermap", "api_key")
    if key_result is not None:
        if profile is not None:
            logger.info(
                "Profile '%s' has no OpenWeather key, using global credentials",
                profile.name,
            )
        else:
            logger.info("Using global OpenWeather credentials")
        return key_result.value.get_secret_value()

    from traderbot.paths import get_data_dir

    env_path = get_data_dir() / ".env"
    if env_path.exists():
        env_value = _env_file_get_value(env_path, "OPENWEATHER_API_KEY")
        if env_value is not None:
            logger.debug("Using OpenWeather key from %s", env_path)
            return env_value

    env_key = os.environ.get("OPENWEATHER_API_KEY")
    if env_key is not None:
        logger.debug("Using OpenWeather key from OPENWEATHER_API_KEY environment variable")
        return env_key

    logger.warning("No OpenWeather key found in profile, global, or environment")
    return None


def resolve_fred_key(
    profile: TradingProfile | None,
) -> str | None:
    """Resolve FRED API key using env fallback chain."""
    if profile is not None:
        from traderbot.profiles.auth import ProfileAuthStore
        profile_auth = ProfileAuthStore(profile)
        profile_creds = profile_auth.get_credentials("fred")
        if profile_creds is not None:
            logger.info("Using FRED key from profile '%s'", profile.name)
            return profile_creds[0]

    global_auth = AuthManager()
    key_result = global_auth.get_credential("fred", "api_key")
    if key_result is not None:
        if profile is not None:
            logger.info(
                "Profile '%s' has no FRED key, using global credentials",
                profile.name,
            )
        else:
            logger.info("Using global FRED credentials")
        return key_result.value.get_secret_value()

    from traderbot.paths import get_data_dir

    env_path = get_data_dir() / ".env"
    if env_path.exists():
        env_value = _env_file_get_value(env_path, "FRED_API_KEY")
        if env_value is not None:
            logger.debug("Using FRED key from %s", env_path)
            return env_value

    env_key = os.environ.get("FRED_API_KEY")
    if env_key is not None:
        logger.debug("Using FRED key from FRED_API_KEY environment variable")
        return env_key

    logger.warning("No FRED key found in profile, global, or environment")
    return None


def _check_env_permissions(env_path: Path) -> None:
    """Warn if .env file has overly permissive access (group/other readable)."""
    if not env_path.exists():
        return
    try:
        mode = env_path.stat().st_mode
        if mode & 0o077:
            logger.warning(
                "SECURITY: %s has overly permissive mode %o — "
                "credentials may be readable by other users. Run: chmod 600 %s",
                env_path, mode & 0o777, env_path,
            )
    except OSError:
        pass


def _env_file_get_value(env_path: Path, key: str) -> str | None:
    """Read a specific key from a .env file (without loading into os.environ).

    Supports multi-line values enclosed in double quotes (standard .env format
    for PEM keys and other credentials that span multiple lines).
    """
    if not env_path.exists():
        return None

    lines = env_path.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            i += 1
            continue
        k, _, v = stripped.partition("=")
        if k.strip() != key:
            i += 1
            continue
        v = v.strip()
        if v.startswith('"') and not v.endswith('"'):
            # Multi-line value: accumulate until closing quote
            parts = [v[1:]]
            i += 1
            while i < len(lines):
                parts.append(lines[i])
                if lines[i].rstrip().endswith('"'):
                    break
                i += 1
            value = "\n".join(parts)
            if value.endswith('"'):
                value = value[:-1]
            return value
        return v.strip().strip("'\"")
    return None
