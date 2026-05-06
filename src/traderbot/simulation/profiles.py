"""Strategy profiles for multi-profile backtesting — risk scaling within HARD_LIMITS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traderbot.risk.limits import HARD_LIMITS
from traderbot.simulation.engine import BacktestEngine, BacktestResult

if TYPE_CHECKING:
    from datetime import date


class StrategyProfile(BaseModel):
    """Defines how a strategy scales risk limits and weights signal sources.

    risk_multiplier is a DOWN-SCALING factor — it can only reduce position
    sizes, never increase them above HARD_LIMITS. A value of 1.0 means the
    profile operates at full hard-limit capacity; 0.5 means all positions are
    halved. Aggressive profiles use 1.0, trading all categories at full size
    within HARD_LIMITS.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0, description="Down-scaling factor: 1.0=full hard limits, 0.5=half")]
    signal_weights: dict[str, float]
    category_focus: list[str]
    description: str

    @model_validator(mode="after")
    def _validate_weights(self) -> StrategyProfile:
        if not self.signal_weights:
            raise ValueError("signal_weights must have at least one entry")
        if all(w <= 0 for w in self.signal_weights.values()):
            raise ValueError("signal_weights must have at least one non-zero weight")
        if any(w < 0 for w in self.signal_weights.values()):
            raise ValueError("signal_weights values must be non-negative")
        if not self.category_focus:
            raise ValueError("category_focus must be non-empty")
        return self

    # Ceiling-type limits: lower is more restrictive (use min)
    _CEILING_KEYS = frozenset({
        "max_position_per_market_pct",
        "max_daily_loss_pct",
        "max_drawdown_pct",
        "max_open_positions",
    })
    # Floor-type limits: higher is more restrictive (use max)
    _FLOOR_KEYS = frozenset({
        "min_liquidity_threshold",
        "min_edge_pct",
    })

    def effective_limit(self, key: str) -> float | int:
        """Compute profile-scoped limit within HARD_LIMITS.

        For ceiling-type limits (max_*), uses min(profile_scaled, HARD_LIMITS)
        — lower is more restrictive.

        For floor-type limits (min_*), uses max(profile_scaled, HARD_LIMITS)
        — higher is more restrictive (a floor means "at least this much").
        """
        if key not in HARD_LIMITS:
            raise KeyError(f"Unknown HARD_LIMITS key: {key!r}")
        scaled = self.risk_multiplier * HARD_LIMITS[key]
        if key in self._FLOOR_KEYS:
            return max(scaled, HARD_LIMITS[key])
        return min(scaled, HARD_LIMITS[key])


CONSERVATIVE = StrategyProfile(
    name="Conservative",
    risk_multiplier=0.5,
    signal_weights={"statistical": 0.8, "sentiment": 0.2},
    category_focus=["economics", "politics"],
    description="Capital preservation; minimizes losses",
)

MODERATE = StrategyProfile(
    name="Moderate",
    risk_multiplier=1.0,
    signal_weights={"statistical": 0.5, "sentiment": 0.5},
    category_focus=["economics", "politics", "technology"],
    description="Balanced approach; default profile",
)

AGGRESSIVE = StrategyProfile(
    name="Aggressive",
    risk_multiplier=1.0,
    signal_weights={"statistical": 0.3, "sentiment": 0.7},
    category_focus=["economics", "politics", "technology", "science", "sports", "culture"],
    description="Seeks higher returns; tolerates more volatility",
)

PRESETS: dict[str, StrategyProfile] = {
    "Conservative": CONSERVATIVE,
    "Moderate": MODERATE,
    "Aggressive": AGGRESSIVE,
}


async def run_profiles(
    engine: BacktestEngine,
    profiles: list[StrategyProfile],
    start: date,
    end: date,
) -> dict[str, BacktestResult]:
    """Run multiple profiles on the same historical data for comparison.

    Each profile gets its own BacktestEngine with isolated position tracking.
    HARD_LIMITS remain immutable — profiles only scale within them.
    """
    results: dict[str, BacktestResult] = {}
    for profile in profiles:
        profile_engine = BacktestEngine(
            data_loader=engine._data_loader,
            strategy=engine._strategy,
            initial_bankroll_cents=engine._initial_bankroll_cents,
            slippage_model=engine._slippage,
            state_dir=engine._state_dir,
        )
        result = await profile_engine.run(start, end)
        results[profile.name] = result
    return results


def compare_profiles(
    profile_results: dict[str, BacktestResult],
    initial_bankroll_cents: int = 100_000_00,
) -> list[dict[str, Any]]:
    """Compare backtest results across multiple profiles.

    Returns a list of dicts keyed by profile name with computed metrics.
    """
    from traderbot.simulation.performance import compute_metrics

    comparisons: list[dict[str, Any]] = []
    for name, result in sorted(profile_results.items()):
        metrics = compute_metrics(result, initial_bankroll_cents)
        metrics["profile_name"] = name
        comparisons.append(metrics)
    return comparisons


def compare_strategies_extended(
    results: dict[str, BacktestResult],
    initial_bankroll_cents: int = 100_000_00,
) -> list[dict[str, Any]]:
    """Compare strategies from a dict of named results (supports profiles).

    Extends the two-strategy comparison to handle N named results.
    """
    from traderbot.simulation.performance import compute_metrics

    rows: list[dict[str, Any]] = []
    for name, result in sorted(results.items()):
        metrics = compute_metrics(result, initial_bankroll_cents)
        metrics["name"] = name
        rows.append(metrics)
    return rows
