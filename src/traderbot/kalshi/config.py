"""Extended KalshiConfig with keyring-priority credential lookup."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import SecretStr  # noqa: TC002 - needed at runtime for Pydantic model fields
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _resolve_from_keyring(key: str) -> SecretStr | None:
    """Try to resolve a credential from keyring before falling back to env."""
    from traderbot.auth import AuthManager

    mgr = AuthManager()
    service_map = {
        "api_key": "api_key",
        "private_key_pem": "private_key_pem",
    }
    kalshi_key = service_map.get(key)
    if kalshi_key is None:
        return None
    result = mgr.get_credential("kalshi", kalshi_key)
    if result is None:
        return None
    return result.value


class KeyringKalshiConfig(BaseSettings):
    """Kalshi config that checks keyring first, then falls back to .env."""

    model_config = SettingsConfigDict(
        strict=True,
        extra="ignore",
        env_prefix="KALSHI_",
        env_file=str(Path.home() / ".traderbot" / ".env"),
        env_file_encoding="utf-8",
    )

    api_key: SecretStr | None = None
    private_key_pem: SecretStr | None = None
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    demo_url: str = "https://demo-api.kalshi.co/trade-api/v2"
    demo_mode: bool = False
    rate_limit_rps: float = 20.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @property
    def active_url(self) -> str:
        return self.demo_url if self.demo_mode else self.base_url

    def resolve_api_key(self) -> str | None:
        """Resolve api_key: keyring first, then env/config. Returns raw string or None."""
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        secret = _resolve_from_keyring("api_key")
        if secret is not None:
            return secret.get_secret_value()
        return None

    def resolve_private_key(self) -> SecretStr | None:
        """Resolve private_key_pem: keyring first, then env/config."""
        if self.private_key_pem is not None:
            return self.private_key_pem
        return _resolve_from_keyring("private_key_pem")
