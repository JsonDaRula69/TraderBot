"""AgentRiskLimits — per-agent risk limits with HARD_LIMITS ceiling enforcement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.risk.limits import HARD_LIMITS

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile


class AgentRiskLimits:
    """Per-agent risk limits that enforce HARD_LIMITS as an absolute ceiling.

    Computes effective limits by taking the minimum of profile limits and HARD_LIMITS
    for maximum thresholds, and the maximum for minimum thresholds (more restrictive wins).

    All properties are read-only to prevent runtime modification.
    """

    def __init__(self, profile: TradingProfile) -> None:
        """Initialize agent limits from a trading profile.

        Args:
            profile: TradingProfile with risk parameters
        """
        self._profile = profile

    @property
    def max_position_per_market_pct(self) -> float:
        """Maximum position size per market as percentage of portfolio.

        Returns the more restrictive (lower) of profile and HARD_LIMITS.
        """
        return min(
            self._profile.max_position_per_market_pct,
            float(HARD_LIMITS["max_position_per_market_pct"]),
        )

    @property
    def max_daily_loss_pct(self) -> float:
        """Maximum daily loss as percentage of portfolio.

        Returns the more restrictive (lower) of profile and HARD_LIMITS.
        """
        return min(
            self._profile.max_daily_loss_pct,
            float(HARD_LIMITS["max_daily_loss_pct"]),
        )

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum drawdown as percentage from peak.

        Returns the more restrictive (lower) of profile and HARD_LIMITS.
        """
        return min(
            self._profile.max_drawdown_pct,
            float(HARD_LIMITS["max_drawdown_pct"]),
        )

    @property
    def max_open_positions(self) -> int:
        """Maximum number of open positions.

        Returns the more restrictive (lower) of profile and HARD_LIMITS.
        """
        return min(
            self._profile.max_open_positions,
            int(HARD_LIMITS["max_open_positions"]),
        )

    def min_liquidity_threshold(self, market_age_hours: float | None = None) -> int:
        """Minimum market liquidity (open interest) required.

        Returns the more restrictive (higher) of profile and the effective threshold.
        Effective threshold time-decays for newly listed markets:
        - < 24h old → 100
        - 24h-72h -> linear ramp from 100 to 500
        - >= 72h → 500 (HARD_LIMITS default)
        When market_age_hours is None, defaults to HARD_LIMITS value.

        Args:
            market_age_hours: Age of the market in hours, or None for default behavior.
        """
        profile_val = self._profile.min_liquidity_threshold
        if market_age_hours is None:
            effective = int(HARD_LIMITS["min_liquidity_threshold"])
        elif market_age_hours < 24:
            effective = 100
        elif market_age_hours < 72:
            effective = int(100 + (400 * (market_age_hours - 24) / 48))
        else:
            effective = 500
        return max(profile_val, effective)

    @property
    def min_edge_pct(self) -> float:
        """Minimum edge (probability advantage) required.

        Returns the more restrictive (higher) of profile and HARD_LIMITS.
        """
        return max(
            self._profile.min_edge_pct,
            float(HARD_LIMITS["min_edge_pct"]),
        )
