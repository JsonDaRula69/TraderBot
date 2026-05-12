"""TradingProfile model — runtime profile for multi-agent trading."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from traderbot.kalshi.models import MarketCategory
from traderbot.risk.limits import HARD_LIMITS


class TradingProfile(BaseModel):
    """Runtime trading profile for OpenClaw agents.

    Defines risk parameters, category filters, and authentication overrides
    for a single trading agent instance. All risk params MUST be <= HARD_LIMITS.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    mode: Literal["paper", "live"]
    description: str
    enabled_categories: list[MarketCategory] = Field(default_factory=list)
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0)]
    max_position_per_market_pct: Annotated[float, Field(gt=0)]
    max_daily_loss_pct: Annotated[float, Field(gt=0)]
    max_drawdown_pct: Annotated[float, Field(gt=0)]
    max_open_positions: Annotated[int, Field(gt=0)]
    min_liquidity_threshold: Annotated[int, Field(gt=0)]
    min_edge_pct: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def _validate_risk_params(self) -> TradingProfile:
        """Ensure all risk params are within HARD_LIMITS ceiling."""
        violations: list[str] = []

        if self.max_position_per_market_pct > HARD_LIMITS["max_position_per_market_pct"]:
            violations.append(
                f"max_position_per_market_pct ({self.max_position_per_market_pct}) "
                f"exceeds HARD_LIMITS ceiling ({HARD_LIMITS['max_position_per_market_pct']})"
            )

        if self.max_daily_loss_pct > HARD_LIMITS["max_daily_loss_pct"]:
            violations.append(
                f"max_daily_loss_pct ({self.max_daily_loss_pct}) "
                f"exceeds HARD_LIMITS ceiling ({HARD_LIMITS['max_daily_loss_pct']})"
            )

        if self.max_drawdown_pct > HARD_LIMITS["max_drawdown_pct"]:
            violations.append(
                f"max_drawdown_pct ({self.max_drawdown_pct}) "
                f"exceeds HARD_LIMITS ceiling ({HARD_LIMITS['max_drawdown_pct']})"
            )

        if self.max_open_positions > HARD_LIMITS["max_open_positions"]:
            violations.append(
                f"max_open_positions ({self.max_open_positions}) "
                f"exceeds HARD_LIMITS ceiling ({HARD_LIMITS['max_open_positions']})"
            )

        if self.min_liquidity_threshold < HARD_LIMITS["min_liquidity_threshold"]:
            violations.append(
                f"min_liquidity_threshold ({self.min_liquidity_threshold}) "
                f"below HARD_LIMITS floor ({HARD_LIMITS['min_liquidity_threshold']})"
            )

        if self.min_edge_pct < HARD_LIMITS["min_edge_pct"]:
            violations.append(
                f"min_edge_pct ({self.min_edge_pct}) "
                f"below HARD_LIMITS floor ({HARD_LIMITS['min_edge_pct']})"
            )

        if violations:
            raise ValueError("; ".join(violations))

        return self

    @computed_field
    @property
    def demo_mode(self) -> bool:
        """True if mode is 'paper', False if 'live'."""
        return self.mode == "paper"

    @computed_field
    @property
    def base_dir(self) -> str:
        """Base directory for profile state files.

        Per-agent isolation: each profile gets its own directory under
        ~/.traderbot/{mode}-{name}/ so that multiple agents running in
        the same mode (paper/live) don't share databases, ChromaDB, or audit logs.
        """
        from traderbot.paths import get_data_dir
        return str(get_data_dir() / f"{self.mode}-{self.name}")

    @computed_field
    @property
    def keyring_prefix(self) -> str:
        """Keyring service name prefix for this profile."""
        return f"traderbot-{self.mode}-{self.name}"

    @computed_field
    @property
    def env_file(self) -> str:
        """Environment file path for this profile."""
        return f".env.{self.mode}"

    def is_category_enabled(self, category: MarketCategory) -> bool:
        """Check if a market category is enabled for this profile.

        Empty enabled_categories list means all categories are permitted.
        """
        if not self.enabled_categories:
            return True
        return category in self.enabled_categories

