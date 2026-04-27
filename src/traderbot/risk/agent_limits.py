"""AgentRiskLimits — per-agent risk limits with HARD_LIMITS ceiling enforcement."""

from __future__ import annotations


from traderbot.risk.limits import HARD_LIMITS


class AgentRiskLimits:
    """Per-agent risk limits that enforce HARD_LIMITS as an absolute ceiling.

    Computes effective limits by taking the minimum of profile limits and HARD_LIMITS
    for maximum thresholds, and the maximum for minimum thresholds (more restrictive wins).

    All properties are read-only to prevent runtime modification.
    """

    def __init__(self, profile: "TradingProfile") -> None:
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

    @property
    def min_liquidity_threshold(self) -> int:
        """Minimum market liquidity (open interest) required.

        Returns the more restrictive (higher) of profile and HARD_LIMITS.
        """
        return max(
            self._profile.min_liquidity_threshold,
            int(HARD_LIMITS["min_liquidity_threshold"]),
        )

    @property
    def min_edge_pct(self) -> float:
        """Minimum edge (probability advantage) required.

        Returns the more restrictive (higher) of profile and HARD_LIMITS.
        """
        return max(
            self._profile.min_edge_pct,
            float(HARD_LIMITS["min_edge_pct"]),
        )

# Made with Bob
