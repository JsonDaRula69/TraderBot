"""Credential management with OS keyring and .env fallback."""

from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

logger = logging.getLogger(__name__)

_SERVICE_PREFIX = "traderbot."

_REQUIRED_SERVICES: dict[str, list[str]] = {
    "kalshi": ["api_key", "private_key_pem"],
}
_OPTIONAL_SERVICES: dict[str, list[str]] = {
    "voyage": ["api_key"],
    "newsapi": ["api_key"],
    "twitter": ["api_key"],
    "reddit": ["client_id", "client_secret"],
    "coingecko": ["api_key"],
    "openweathermap": ["api_key"],
    "fred": ["api_key"],
}

_ALL_SERVICES: dict[str, list[str]] = {**_REQUIRED_SERVICES, **_OPTIONAL_SERVICES}


class CredentialResult(BaseModel):
    """Result of a credential lookup, always wrapping value as SecretStr."""

    model_config = ConfigDict(strict=True, extra="forbid")

    service: str
    key: str
    value: SecretStr
    source: Literal["keyring", "env"]


class ServiceInfo(BaseModel):
    """Summary of a configured service."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    keys: list[str]


def _is_keyring_available() -> bool:
    """Check if keyring backend is functional (not headless/missing)."""
    try:
        import keyring

        backend = keyring.get_keyring()
        # keyring.backends.fail.Keyring is the sentinel for "no backend"
        if type(backend).__module__ == "keyring.backends.fail":
            logger.debug("Keyring unavailable: no suitable backend found")
            return False
        return True
    except ImportError:
        logger.debug("Keyring unavailable: keyring package not installed")
        return False
    except Exception:
        logger.debug("Keyring unavailable: error initializing", exc_info=True)
        return False


def _keyring_service_name(service: str) -> str:
    """Build keyring service name from TraderBot service identifier."""
    return f"{_SERVICE_PREFIX}{service}"


def _keyring_username(key: str) -> str:
    """Build keyring username from credential key name."""
    return key


class AuthManager:
    """Manage credentials via OS keyring with .env fallback.

    Resolution order for reads:
    1. OS keyring (macOS Keychain / Windows Credential Locker / Linux Secret Service)
    2. Process environment variables
    3. .env file on disk
    """

    def get_credential(self, service: str, key: str) -> CredentialResult | None:
        """Retrieve a credential; keyring first, then .env and environment variables."""
        if _is_keyring_available():
            keyring_val = self._get_from_keyring(service, key)
            if keyring_val is not None:
                return CredentialResult(
                    service=service, key=key, value=SecretStr(keyring_val), source="keyring"
                )

        env_keys = self._service_key_to_env(service, key)
        for env_key in env_keys:
            env_val = os.environ.get(env_key)
            if env_val is not None:
                logger.debug("Using %s from environment", env_key)
                return CredentialResult(
                    service=service, key=key, value=SecretStr(env_val), source="env"
                )

        from traderbot.paths import get_data_dir

        env_path = get_data_dir() / ".env"
        if env_path.exists():
            for env_key in env_keys:
                file_val = _env_file_get_value(env_path, env_key)
                if file_val is not None:
                    logger.debug("Using %s from %s", env_key, env_path)
                    return CredentialResult(
                        service=service, key=key, value=SecretStr(file_val), source="env"
                    )

        return None

    def set_credential(self, service: str, key: str, value: str) -> Literal["keyring", "env"]:
        """Store a credential. Prefers keyring; falls back to .env file.

        Returns the storage source actually used.
        """
        if _is_keyring_available():
            self._set_in_keyring(service, key, value)
            return "keyring"

        from traderbot.paths import ensure_data_dir

        env_path = ensure_data_dir() / ".env"
        env_key = self._service_key_to_env(service, key)[0]
        _env_file_set_value(env_path, env_key, value)
        logger.info("Keyring unavailable; stored %s in %s", env_key, env_path)
        return "env"

    def delete_credential(self, service: str, key: str) -> bool:
        """Delete a credential from keyring. Returns True if deleted."""
        if not _is_keyring_available():
            return False
        return self._delete_from_keyring(service, key)

    def migrate_to_keyring(self, service: str | None = None) -> dict[str, int]:
        """Migrate credentials from .env to keyring.

        Args:
            service: Specific service to migrate, or None for all.

        Returns:
            Dict with 'migrated' and 'skipped' counts.
        """
        if not _is_keyring_available():
            logger.warning("Keyring unavailable; migration skipped")
            return {"migrated": 0, "skipped": 0}

        services_to_migrate = {service: _ALL_SERVICES[service]} if service else _ALL_SERVICES
        migrated = 0
        skipped = 0

        for svc, keys in services_to_migrate.items():
            for k in keys:
                existing = self._get_from_keyring(svc, k)
                if existing is not None:
                    skipped += 1
                    continue
                cred = self._get_from_env_only(svc, k)
                if cred is not None:
                    self._set_in_keyring(svc, k, cred)
                    migrated += 1
                    logger.info("Migrated %s/%s to keyring", svc, k)
                else:
                    skipped += 1

        return {"migrated": migrated, "skipped": skipped}

    def list_services(self) -> list[ServiceInfo]:
        """List all configured traderbot services (keys only, never values)."""
        services: list[ServiceInfo] = []
        for service_name, keys in _ALL_SERVICES.items():
            found_keys: list[str] = []
            for key in keys:
                if self._keyring_has(service_name, key):
                    found_keys.append(key)
                else:
                    env_keys = self._service_key_to_env(service_name, key)
                    if any(os.environ.get(ek) is not None for ek in env_keys):
                        found_keys.append(key)
                    else:
                        from traderbot.paths import get_data_dir

                        env_path = get_data_dir() / ".env"
                        if env_path.exists():
                            for ek in env_keys:
                                if _env_file_get_value(env_path, ek) is not None:
                                    found_keys.append(key)
                                    break
            if found_keys:
                services.append(ServiceInfo(name=service_name, keys=found_keys))
        return sorted(services, key=lambda s: s.name)

    def check_credentials(self) -> dict[str, dict[str, bool]]:
        """Verify all required credentials are configured somewhere."""
        result: dict[str, dict[str, bool]] = {}
        for service_name, keys in _ALL_SERVICES.items():
            result[service_name] = {}
            for key in keys:
                cred = self.get_credential(service_name, key)
                result[service_name][key] = cred is not None
        return result

    @staticmethod
    def _service_key_to_env(service: str, key: str) -> list[str]:
        """Map service/key to environment variable name(s) in priority order."""
        if service == "kalshi" and key == "api_key":
            return ["KALSHI_API_KEY"]
        if service == "kalshi" and key == "private_key_pem":
            return ["KALSHI_PRIVATE_KEY_PEM", "KALSHI_PRIVATE_KEY_PATH"]
        if service == "newsapi" and key == "api_key":
            return ["NEWSAPI_API_KEY", "NEWSAPI_KEY"]
        if service == "coingecko" and key == "api_key":
            return ["COINGECKO_API_KEY"]
        service_prefix = service.upper()
        return [f"{service_prefix}_{key.upper()}"]

    @staticmethod
    def _get_from_keyring(service: str, key: str) -> str | None:
        """Read a credential from OS keyring."""
        import keyring

        return keyring.get_password(_keyring_service_name(service), _keyring_username(key))

    @staticmethod
    def _set_in_keyring(service: str, key: str, value: str) -> None:
        """Write a credential to OS keyring."""
        import keyring

        keyring.set_password(_keyring_service_name(service), _keyring_username(key), value)
        logger.debug("Stored %s/%s in keyring", service, key)

    @staticmethod
    def _delete_from_keyring(service: str, key: str) -> bool:
        """Delete a credential from OS keyring."""
        import keyring

        try:
            keyring.delete_password(_keyring_service_name(service), _keyring_username(key))
            logger.debug("Deleted %s/%s from keyring", service, key)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    @staticmethod
    def _keyring_has(service: str, key: str) -> bool:
        """Check whether keyring holds a credential without reading its value."""
        if not _is_keyring_available():
            return False
        import keyring

        return keyring.get_password(_keyring_service_name(service), _keyring_username(key)) is not None

    def _get_from_env_only(self, service: str, key: str) -> str | None:
        """Retrieve credential value from env/.env only (no keyring)."""
        env_keys = self._service_key_to_env(service, key)
        for env_key in env_keys:
            env_val = os.environ.get(env_key)
            if env_val is not None:
                return env_val

        from traderbot.paths import get_data_dir

        env_path = get_data_dir() / ".env"
        if env_path.exists():
            for env_key in env_keys:
                file_val = _env_file_get_value(env_path, env_key)
                if file_val is not None:
                    return file_val
        return None


def _env_file_get_value(env_path: os.PathLike, key: str) -> str | None:
    """Read a specific key from a .env file (without loading into os.environ)."""
    from pathlib import Path

    path = Path(env_path)
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip("'\"")
    return None


def _env_file_set_value(env_path: os.PathLike, key: str, value: str) -> None:
    """Write or update a key in a .env file."""
    from pathlib import Path

    path = Path(env_path)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text().splitlines()

    found = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k, _, _ = stripped.partition("=")
        if k.strip() == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n")


def get_credential(service: str, key: str) -> SecretStr | None:
    """Convenience function: retrieve a credential as SecretStr."""
    mgr = AuthManager()
    result = mgr.get_credential(service, key)
    if result is None:
        return None
    return result.value