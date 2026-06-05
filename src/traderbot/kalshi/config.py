"""KalshiConfig variant for env-file credential resolution."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class EnvKalshiConfig(BaseSettings):
    """Kalshi config that reads credentials from .env file."""

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
    rate_limit_rps: float = 20.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @field_validator("rate_limit_rps", mode="before")
    @classmethod
    def _validate_rate_limit(cls, v: object) -> float:
        if isinstance(v, (int, float)) and v <= 0:
            return 20.0
        return float(v) if isinstance(v, (int, float)) else 20.0

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
