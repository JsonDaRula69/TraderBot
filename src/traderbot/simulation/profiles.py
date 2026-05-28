"""Strategy profiles for multi-profile backtesting — risk scaling within HARD_LIMITS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traderbot.risk.limits import HARD_LIMITS
from traderbot.simulation.engine import BacktestEngine, BacktestResult

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)


class StrategyProfile(BaseModel):
    """Defines how a strategy scales risk limits and weights signal sources.

    risk_multiplier is a DOWN-SCALING factor — it can only reduce position
    sizes, never increase them above HARD_LIMITS. A value of 1.0 means the
    profile operates at full hard-limit capacity; 0.5 means all positions are
    halved. "Aggressive" uses 0.8 (not 1.0) because aggressive profiles trade
    more categories (higher concentration risk), offset by slightly smaller
    per-position sizing.
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

    def to_trading_profile(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.profiles.models import TradingProfile

        enabled = [MarketCategory(c) for c in self.category_focus if c in MarketCategory._value2member_map_]
        return TradingProfile(
            name=self.name,
            mode="paper",
            description=self.description,
            enabled_categories=enabled,
            risk_multiplier=self.risk_multiplier,
            max_position_per_market_pct=float(self.risk_multiplier * HARD_LIMITS["max_position_per_market_pct"]),
            max_daily_loss_pct=float(self.risk_multiplier * HARD_LIMITS["max_daily_loss_pct"]),
            max_drawdown_pct=float(self.risk_multiplier * HARD_LIMITS["max_drawdown_pct"]),
            max_open_positions=int(self.risk_multiplier * HARD_LIMITS["max_open_positions"]),
            min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
            min_edge_pct=float(HARD_LIMITS["min_edge_pct"]),
        )


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
    category_focus=["economics", "politics", "science_and_technology"],
    description="Balanced approach; default profile",
)

AGGRESSIVE = StrategyProfile(
    name="Aggressive",
    risk_multiplier=0.8,
    signal_weights={"statistical": 0.3, "sentiment": 0.7},
    category_focus=["economics", "politics", "science_and_technology", "sports", "entertainment"],
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
        result = await profile_engine.run(start, end, profile=profile.to_trading_profile())
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
