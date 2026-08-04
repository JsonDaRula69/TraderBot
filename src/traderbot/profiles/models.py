"""TradingProfile model — runtime profile for multi-agent trading."""

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from traderbot.kalshi.models import MarketCategory

logger = logging.getLogger(__name__)


class TradingProfile(BaseModel):
    """Runtime trading profile for OpenClaw agents.

    Defines risk parameters, category filters, permissions, and authentication
    overrides for a single trading agent instance. All risk params MUST be <= HARD_LIMITS.

    v2 additions:
    - ``mode`` now includes "backtest" (DD-013, DD-017)
    - ``permissions`` controls which MCP tools the agent may call (DD-025, DD-036)
    - ``is_tool_permitted()`` enforces tool-level access control
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    mode: Literal["backtest", "paper", "live"]
    suspended: bool = False
    description: str
    enabled_categories: list[MarketCategory] = Field(default_factory=list)
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0)]
    max_position_per_market_pct: Annotated[float, Field(gt=0)]
    max_daily_loss_pct: Annotated[float, Field(gt=0)]
    max_drawdown_pct: Annotated[float, Field(gt=0)]
    max_open_positions: Annotated[int, Field(gt=0)]
    min_liquidity_threshold: Annotated[int, Field(gt=0)]
    min_edge_pct: Annotated[float, Field(gt=0)]

    # MCP tool permissions (DD-025, DD-036). Prefix with "deny:" to block.
    # Empty list = all tools permitted. Examples: "deny:traderbot__trade", "traderbot__*"
    permissions: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object, /) -> None:
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
        """Environment file path for this profile (absolute, under the data dir)."""
        from traderbot.paths import get_data_dir

        return str(get_data_dir() / f".env.{self.mode}")

    def is_category_enabled(self, category: MarketCategory) -> bool:
        """Check if a market category is enabled for this profile.

        Empty enabled_categories list means all categories are permitted.
        """
        if not self.enabled_categories:
            return True
        return category in self.enabled_categories

    def is_tool_permitted(self, tool_name: str) -> bool:
        """Check if an MCP tool is permitted for this profile.

        Rules (evaluated in order):
        1. Empty permissions → all tools permitted
        2. "deny:" rules block matching tools (take precedence)
        3. Allow rules permit matching tools
        4. If allow rules exist but none match → denied by default
        5. If only deny rules exist and none match → permitted
        """
        if not self.permissions:
            return True

        for rule in self.permissions:
            if rule.startswith("deny:"):
                pattern = rule[5:]
                if self._matches_tool_pattern(tool_name, pattern):
                    return False

        has_allow_rules = any(not r.startswith("deny:") for r in self.permissions)
        if has_allow_rules:
            return any(
                self._matches_tool_pattern(tool_name, rule)
                for rule in self.permissions
                if not rule.startswith("deny:")
            )

        return True

    @staticmethod
    def _matches_tool_pattern(tool_name: str, pattern: str) -> bool:
        """Match tool name against pattern. Supports wildcard suffix: 'traderbot__*'."""
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return tool_name.startswith(prefix)
        return tool_name == pattern
