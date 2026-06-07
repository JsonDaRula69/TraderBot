"""TradingProfile model — runtime profile for multi-agent trading."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

if TYPE_CHECKING:
    from traderbot.kalshi.models import MarketCategory

logger = logging.getLogger(__name__)


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

    def model_post_init(self, __context) -> None:
        logger.debug(
            "Profile %s: mode=%s risk_mult=%.2f", self.name, self.mode, self.risk_multiplier
        )

    @computed_field
    @property
    def paper_mode(self) -> bool:
        return self.mode == "paper"

    initial_balance_cents: int | None = 10_000  # $100 default; None allowed for backward compat

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
