"""Environment-based credential management for TraderBot."""

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
    source: Literal["env"]


class ServiceInfo(BaseModel):
    """Summary of a configured service."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    keys: list[str]


class AuthManager:
    """Manage credentials via .env file and environment variables."""

    def get_credential(self, service: str, key: str) -> CredentialResult | None:
        """Retrieve a credential from .env file then environment variables."""
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

    def list_services(self) -> list[ServiceInfo]:
        """List all configured traderbot services (keys only, never values)."""
        services: list[ServiceInfo] = []
        for service_name, keys in _ALL_SERVICES.items():
            found_keys: list[str] = []
            for key in keys:
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


def get_credential(service: str, key: str) -> SecretStr | None:
    """Convenience function: retrieve a credential as SecretStr."""
    mgr = AuthManager()
    result = mgr.get_credential(service, key)
    if result is None:
        return None
    return result.value
