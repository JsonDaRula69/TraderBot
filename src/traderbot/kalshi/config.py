"""KalshiConfig variant for env-file credential resolution."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class EnvKalshiConfig(BaseSettings):
    """Lenient Kalshi config variant for multi-stage credential resolution.

    Unlike :class:`KalshiConfig` (which requires ``api_key``), this class
    allows ``api_key=None`` so callers can attempt env-file resolution first
    and fall back to keyring or interactive prompts when no key is found.
    Uses ``extra="ignore"`` for the same reason as :class:`KalshiConfig`:
    the ``KALSHI_*`` env prefix often captures unrelated variables.
    """

    model_config = SettingsConfigDict(
        strict=True,
        extra="ignore",
        env_prefix="KALSHI_",
        env_file=str(Path.home() / ".traderbot" / ".env"),
        env_file_encoding="utf-8",
    )

    api_key: SecretStr | None = None
    private_key_pem: SecretStr | None = None
    private_key_path: Path | None = None
    base_url: str = "https://external-api.kalshi.com/trade-api/v2"

    # Per-second token budgets from the Kalshi API `GET /account/limits` endpoint.
    # Effective request rate = budget / endpoint_cost (default 10 tokens per request).
    # On Basic tier: read = 200 tokens/sec (20 RPS), write = 100 tokens/sec (10 RPS).
    # Configurable via KALSHI_READ_BUDGET_TOKENS and KALSHI_WRITE_BUDGET_TOKENS env vars.
    read_budget_tokens: float = 200.0
    write_budget_tokens: float = 100.0
    read_burst_capacity: float = 200.0
    write_burst_capacity: float = 100.0
    endpoint_cost: float = 10.0

    max_retries: int = 3
    retry_base_delay: float = 1.0

    def resolve_api_key(self) -> str | None:
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        return None

    def resolve_private_key(self) -> SecretStr | None:
        if self.private_key_pem is not None:
            return self.private_key_pem
        if self.private_key_path is not None:
            try:
                pem = self.private_key_path.read_text()
                return SecretStr(pem)
            except (FileNotFoundError, OSError):
                from traderbot.paths import get_data_dir

                alt = get_data_dir() / self.private_key_path.name
                if alt.exists():
                    return SecretStr(alt.read_text())
        return None
