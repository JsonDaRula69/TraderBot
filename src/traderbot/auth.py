"""Keyring-based credential management for TraderBot."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal

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
}

_ALL_SERVICES: dict[str, list[str]] = {**_REQUIRED_SERVICES, **_OPTIONAL_SERVICES}


class KeyringUnavailableError(Exception):
    """Raised when the OS keyring backend is not available."""


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


class AuthManager:
    """Manage credentials via OS keyring with .env fallback."""

    def __init__(self, keyring_module: Any = None, keyring_available: bool | None = None) -> None:
        self._keyring = keyring_module
        self._keyring_available: bool | None = keyring_available

    @property
    def keyring_available(self) -> bool:
        if self._keyring_available is None:
            self._keyring_available = self._check_keyring()
        return self._keyring_available

    def _check_keyring(self) -> bool:
        try:
            kr = self._keyring or __import__("keyring")
            if hasattr(kr, "get_keyring"):
                backend = kr.get_keyring()
                backend_name = type(backend).__name__
                if "Fail" in backend_name or "Null" in backend_name:
                    logger.warning(
                        "Keyring backend '%s' is not usable; falling back to .env",
                        backend_name,
                    )
                    return False
                try:
                    kr.set_password("__traderbot_probe__", "test", "probe")
                    kr.delete_password("__traderbot_probe__", "test")
                except Exception:
                    logger.warning("Keyring write probe failed; falling back to .env")
                    return False
            return True
        except Exception:
            logger.warning("Keyring not available; falling back to .env")
            return False

    def _full_service(self, service: str) -> str:
        if service.startswith(_SERVICE_PREFIX):
            return service
        return f"{_SERVICE_PREFIX}{service}"

    def set_credential(self, service: str, key: str, value: str) -> None:
        """Store a credential in the OS keyring."""
        if not self.keyring_available:
            raise KeyringUnavailableError(
                "Cannot store credential: keyring backend unavailable. "
                "Set credentials via .env file instead."
            )
        kr = self._keyring or __import__("keyring")
        full_service = self._full_service(service)
        kr.set_password(full_service, key, value)

    def get_credential(self, service: str, key: str) -> CredentialResult | None:
        """Retrieve a credential, trying keyring first then .env fallback.

        For KALSHI_PRIVATE_KEY_PATH, reads the file and returns PEM content
        rather than the path string.
        """
        full_service = self._full_service(service)

        if self.keyring_available:
            kr = self._keyring or __import__("keyring")
            try:
                val = kr.get_password(full_service, key)
                if val is not None:
                    return CredentialResult(
                        service=service, key=key, value=SecretStr(val), source="keyring"
                    )
            except Exception:
                logger.warning(
                    "Keyring lookup failed for %s/%s; trying .env fallback",
                    full_service,
                    key,
                )

        env_keys = self._service_key_to_env(service, key)
        env_val = None
        used_env_key = None
        for env_key in env_keys:
            env_val = os.environ.get(env_key)
            if env_val is not None:
                used_env_key = env_key
                break
        if env_val is None:
            env_val = self._env_file_get(env_keys)
            if env_val is not None:
                used_env_key = env_keys[0]

        if env_val is not None:
            if service == "kalshi" and key == "private_key_pem" and used_env_key == "KALSHI_PRIVATE_KEY_PATH":
                key_path = env_val.strip()
                p = Path(key_path)
                if p.is_file():
                    env_val = p.read_text()
                else:
                    logger.warning("KALSHI_PRIVATE_KEY_PATH points to non-existent file: %s", key_path)
                    return None

            assert used_env_key is not None
            if self.keyring_available:
                logger.warning(
                    "Credential %s/%s not in keyring; using .env fallback (%s)",
                    service,
                    key,
                    used_env_key,
                )
            else:
                logger.warning(
                    "Keyring unavailable; reading %s from environment", used_env_key
                )
            return CredentialResult(
                service=service, key=key, value=SecretStr(env_val), source="env"
            )

        return None

    def delete_credential(self, service: str, key: str) -> bool:
        """Remove a credential from the OS keyring. Returns True if deleted."""
        if not self.keyring_available:
            return False
        kr = self._keyring or __import__("keyring")
        full_service = self._full_service(service)
        try:
            existing = kr.get_password(full_service, key)
            if existing is None:
                return False
            kr.delete_password(full_service, key)
            return True
        except Exception:
            return False

    def list_services(self) -> list[ServiceInfo]:
        """List all configured traderbot services (keys only, never values)."""
        services: list[ServiceInfo] = []
        if self.keyring_available:
            kr = self._keyring or __import__("keyring")
            for service_name, keys in _ALL_SERVICES.items():
                full_service = self._full_service(service_name)
                found_keys: list[str] = []
                for key in keys:
                    try:
                        if kr.get_password(full_service, key) is not None:
                            found_keys.append(key)
                    except Exception:
                        pass
                if found_keys:
                    services.append(ServiceInfo(name=service_name, keys=found_keys))

        for service_name, keys in _ALL_SERVICES.items():
            already = next((s for s in services if s.name == service_name), None)
            existing_keys = set(already.keys) if already else set()
            found_keys: list[str] = list(existing_keys)
            for key in keys:
                env_keys = self._service_key_to_env(service_name, key)
                if any(os.environ.get(ek) is not None for ek in env_keys) and key not in found_keys:
                    found_keys.append(key)
            if found_keys:
                already_entry = next((s for s in services if s.name == service_name), None)
                if already_entry:
                    already_entry.keys = found_keys
                else:
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

    def _env_file_get(self, env_keys: list[str]) -> str | None:
        """Read a value from .env file when not in process environment."""
        env_path = Path.home() / ".traderbot" / ".env"
        if not env_path.is_file():
            return None
        for env_key in env_keys:
            prefix = f"{env_key}="
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith(prefix) and not line.lstrip().startswith("#"):
                        return line[len(prefix):].strip()
            except Exception:
                continue
        return None

    @staticmethod
    def _service_key_to_env(service: str, key: str) -> list[str]:
        """Map service/key to environment variable name(s) in priority order.

        Returns a list where the first element is the canonical env var name
        and subsequent elements are fallback aliases.
        """
        if service == "kalshi" and key == "api_key":
            return ["KALSHI_API_KEY"]
        if service == "kalshi" and key == "private_key_pem":
            return ["KALSHI_PRIVATE_KEY_PEM", "KALSHI_PRIVATE_KEY_PATH"]
        if service == "kalshi" and key == "demo_mode":
            return ["KALSHI_DEMO_MODE"]
        if service == "newsapi" and key == "api_key":
            return ["NEWSAPI_API_KEY", "NEWSAPI_KEY"]
        service_prefix = service.upper()
        return [f"{service_prefix}_{key.upper()}"]


def get_credential(service: str, key: str) -> SecretStr | None:
    """Convenience function: retrieve a credential as SecretStr."""
    mgr = AuthManager()
    result = mgr.get_credential(service, key)
    if result is None:
        return None
    return result.value
