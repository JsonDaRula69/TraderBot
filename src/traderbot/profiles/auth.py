"""Per-profile credential resolution with keyring and .env fallback."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from traderbot.auth import _is_keyring_available, _keyring_username

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def _profile_keyring_service(profile_name: str, service: str) -> str:
    """Build keyring service name for a profile-scoped credential."""
    return f"traderbot.profiles.{profile_name}.{service}"


class ProfileAuthStore:
    """Per-profile credential store with keyring and env fallback.

    Resolution order:
    1. OS keyring (traderbot.profiles.{name}.{service})
    2. Profile-scoped environment variables
    3. Profile-scoped .env entries
    """

    def __init__(self, profile: TradingProfile) -> None:
        self._profile = profile

    def get_credentials(self, service: str) -> tuple[str, str] | None:
        """Retrieve credentials for this profile."""
        if service == "kalshi":
            return self._get_kalshi_credentials()
        return self._get_generic_credentials(service)

    def has_credentials(self, service: str) -> bool:
        return self.get_credentials(service) is not None

    def set_credentials(self, service: str, key: str, value: str) -> bool:
        """Store a profile-scoped credential in keyring."""
        if not _is_keyring_available():
            return False
        import keyring

        service_name = _profile_keyring_service(self._profile.name, service)
        keyring.set_password(service_name, _keyring_username(key), value)
        logger.debug("Stored %s/%s for profile '%s' in keyring", service, key, self._profile.name)
        return True

    def delete_credentials(self, service: str, key: str) -> bool:
        """Delete a profile-scoped credential from keyring."""
        if not _is_keyring_available():
            return False
        import keyring

        service_name = _profile_keyring_service(self._profile.name, service)
        try:
            keyring.delete_password(service_name, _keyring_username(key))
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    def _get_kalshi_credentials(self) -> tuple[str, str] | None:
        prefix = self._profile.name.upper().replace("-", "_").replace(" ", "_")

        # 1. Keyring
        if _is_keyring_available():
            import keyring

            svc = _profile_keyring_service(self._profile.name, "kalshi")
            api_key = keyring.get_password(svc, _keyring_username("api_key"))
            pem = keyring.get_password(svc, _keyring_username("private_key_pem"))
            if api_key and pem:
                logger.info(
                    "Using Kalshi credentials for profile '%s' from keyring",
                    self._profile.name,
                )
                return (api_key, pem)

        # 2. Environment variables
        api_key = os.environ.get(f"KALSHI_API_KEY_PROFILE_{prefix}")
        pem = os.environ.get(f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{prefix}")
        if not pem:
            path = os.environ.get(f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{prefix}")
            if path:
                from pathlib import Path

                p = Path(path)
                if p.is_file():
                    pem = p.read_text()

        # 3. .env file
        if not api_key or not pem:
            from traderbot.paths import get_data_dir

            env_path = get_data_dir() / ".env"
            if env_path.exists():
                api_key = api_key or _env_file_get_value(
                    env_path, f"KALSHI_API_KEY_PROFILE_{prefix}"
                )
                pem = pem or _env_file_get_value(
                    env_path, f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{prefix}"
                )
                if not pem:
                    pem_path = _env_file_get_value(
                        env_path, f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{prefix}"
                    )
                    if pem_path:
                        from pathlib import Path

                        p = Path(pem_path)
                        if p.is_file():
                            pem = p.read_text()

        if api_key and pem:
            return (api_key, pem)
        return None

    def _get_generic_credentials(self, service: str) -> tuple[str, str] | None:
        # 1. Keyring
        if _is_keyring_available():
            import keyring

            svc = _profile_keyring_service(self._profile.name, service)
            val = keyring.get_password(svc, _keyring_username("api_key"))
            if val:
                logger.info("Using %s key for profile '%s' from keyring", service, self._profile.name)
                return (val, "")

        # 2. Environment variables and .env file
        prefix = self._profile.name.upper().replace("-", "_").replace(" ", "_")
        env_name = f"{service.upper()}_API_KEY_PROFILE_{prefix}"
        val = os.environ.get(env_name)
        if not val:
            from traderbot.paths import get_data_dir

            env_path = get_data_dir() / ".env"
            if env_path.exists():
                val = _env_file_get_value(env_path, env_name)
        if val:
            return (val, "")
        return None


def _env_file_get_value(env_path: os.PathLike, key: str) -> str | None:
    from pathlib import Path

    path = Path(env_path)
    if not path.exists():
        return None

    lines = path.read_text().splitlines()
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
