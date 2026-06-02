"""Update configuration — persisted to ~/.traderbot/update_config.json."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from traderbot.paths import get_data_dir

CONFIG_PATH = get_data_dir() / "update_config.json"


class UpdateConfig(BaseModel):
    """Auto-update configuration for TraderBot."""

    model_config = ConfigDict(strict=True, extra="forbid")

    enabled: bool = Field(default=True, description="Enable auto-update checking")
    check_on_startup: bool = Field(default=True, description="Check for updates on CLI startup")
    check_interval_minutes: int = Field(
        default=30, ge=1, le=10080, description="Minutes between update checks"
    )
    auto_apply: bool = Field(
        default=False, description="Automatically apply updates without prompting"
    )
    include_prerelease: bool = Field(
        default=False, description="Include pre-release versions in checks"
    )

    @classmethod
    def load(cls) -> UpdateConfig:
        """Load config from disk, or return defaults if not found."""
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                return cls.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                pass
        return cls()

    def save(self) -> None:
        """Persist config to disk."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(self.model_dump_json(indent=2) + "\n")
