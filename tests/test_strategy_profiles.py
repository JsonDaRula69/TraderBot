"""Tests for simulation/profiles.py — StrategyProfile model and multi-profile backtesting."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from traderbot.kalshi.models import Market, PortfolioState, Trade
from traderbot.risk.limits import HARD_LIMITS
from traderbot.simulation.data_loader import DataLoader
from traderbot.simulation.engine import BacktestEngine, BacktestResult, Context, Signal
from traderbot.simulation.performance import MultiStrategyComparison, compare_strategies_multi
from traderbot.simulation.profiles import (
    AGGRESSIVE,
    CONSERVATIVE,
    MODERATE,
    PRESETS,
    StrategyProfile,
    compare_profiles,
    run_profiles,
)

if TYPE_CHECKING:
    from pathlib import Path

PORTFOLIO_VALUE = 100_000_00


def _make_market(
    ticker: str = "KX-TEST",
    status: str = "settled",
    volume: int = 5000,
    open_interest: int = 2000,
    settlement_result: bool | None = True,
    close_time: datetime | None = None,
    category: str = "economics",
) -> Market:
    return Market(
        ticker=ticker,
        question="Test?",
        outcome_prices=["0.65", "0.35"],
        volume=volume,
        open_interest=open_interest,
        close_time=close_time or datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        status=status,
        event_ticker="KX-EVENT",
        category=category,
        settlement_result=settlement_result,
    )


# --- StrategyProfile model tests ---

class TestStrategyProfileModel:
    def test_valid_profile(self) -> None:
        p = StrategyProfile(
            name="Test",
            risk_multiplier=0.7,
            signal_weights={"statistical": 0.6, "sentiment": 0.4},
            category_focus=["economics"],
            description="Test profile",
        )
        assert p.name == "Test"
        assert p.risk_multiplier == 0.7
        assert p.signal_weights == {"statistical": 0.6, "sentiment": 0.4}

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            StrategyProfile(
                name="Bad",
                risk_multiplier=0.5,
                signal_weights={"statistical": 1.0},
                category_focus=["economics"],
                description="Bad",
                extra="nope",
            )

    def test_rejects_risk_multiplier_above_1(self) -> None:
        with pytest.raises(ValidationError):
            StrategyProfile(
                name="OverLimit",
                risk_multiplier=1.1,
                signal_weights={"statistical": 1.0},
                category_focus=["economics"],
                description="Too high",
            )

    def test_rejects_risk_multiplier_zero(self) -> None:
        with pytest.raises(ValidationError):
            StrategyProfile(
                name="Zero",
                risk_multiplier=0.0,
                signal_weights={"statistical": 1.0},
                category_focus=["economics"],
                description="Zero risk",
            )

    def test_rejects_negative_risk_multiplier(self) -> None:
        with pytest.raises(ValidationError):
            StrategyProfile(
                name="Neg",
                risk_multiplier=-0.5,
                signal_weights={"statistical": 1.0},
                category_focus=["economics"],
                description="Negative",
            )

    def test_rejects_empty_signal_weights(self) -> None:
        with pytest.raises(ValidationError, match="at least one entry"):
            StrategyProfile(
                name="Empty",
                risk_multiplier=0.5,
                signal_weights={},
                category_focus=["economics"],
                description="Empty weights",
            )

    def test_rejects_all_zero_weights(self) -> None:
        with pytest.raises(ValidationError, match="non-zero weight"):
            StrategyProfile(
                name="ZeroW",
                risk_multiplier=0.5,
                signal_weights={"statistical": 0.0, "sentiment": 0.0},
                category_focus=["economics"],
                description="All zero",
            )

    def test_rejects_negative_weight(self) -> None:
        with pytest.raises(ValidationError, match="non-negative"):
            StrategyProfile(
                name="NegWeight",
                risk_multiplier=0.5,
                signal_weights={"statistical": -0.5, "sentiment": 1.5},
                category_focus=["economics"],
                description="Negative weight",
            )

    def test_rejects_empty_category_focus(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            StrategyProfile(
                name="NoCat",
                risk_multiplier=0.5,
                signal_weights={"statistical": 1.0},
                category_focus=[],
                description="No categories",
            )

    def test_risk_multiplier_1_is_valid(self) -> None:
        p = StrategyProfile(
            name="Full",
            risk_multiplier=1.0,
            signal_weights={"statistical": 1.0},
            category_focus=["economics"],
            description="Full limit",
        )
        assert p.risk_multiplier == 1.0


# --- effective_limit tests ---

class TestEffectiveLimit:
    def test_conservative_halves_position_limit(self) -> None:
        expected = 0.5 * HARD_LIMITS["max_position_per_market_pct"]
        assert CONSERVATIVE.effective_limit("max_position_per_market_pct") == expected

    def test_moderate_at_full_limits(self) -> None:
        expected = 1.0 * HARD_LIMITS["max_position_per_market_pct"]
        assert MODERATE.effective_limit("max_position_per_market_pct") == expected

    def test_aggressive_at_full_limit_for_ceilings(self) -> None:
        expected = 1.0 * HARD_LIMITS["max_daily_loss_pct"]
        assert AGGRESSIVE.effective_limit("max_daily_loss_pct") == expected

    def test_effective_limit_never_exceeds_hard_limit(self) -> None:
        for key in HARD_LIMITS:
            assert CONSERVATIVE.effective_limit(key) <= HARD_LIMITS[key]
            assert MODERATE.effective_limit(key) <= HARD_LIMITS[key]
            assert AGGRESSIVE.effective_limit(key) <= HARD_LIMITS[key]

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown HARD_LIMITS key"):
            CONSERVATIVE.effective_limit("nonexistent_key")

    def test_conservative_daily_loss_limit(self) -> None:
        expected = 0.5 * HARD_LIMITS["max_daily_loss_pct"]
        assert CONSERVATIVE.effective_limit("max_daily_loss_pct") == expected

    def test_conservative_drawdown_limit(self) -> None:
        expected = 0.5 * HARD_LIMITS["max_drawdown_pct"]
        assert CONSERVATIVE.effective_limit("max_drawdown_pct") == expected


# --- Preset profile tests ---

class TestPresets:
    def test_conservative_preset(self) -> None:
        assert CONSERVATIVE.name == "Conservative"
        assert CONSERVATIVE.risk_multiplier == 0.5
        assert CONSERVATIVE.signal_weights == {"statistical": 0.8, "sentiment": 0.2}
        assert CONSERVATIVE.description == "Capital preservation; minimizes losses"

    def test_moderate_preset(self) -> None:
        assert MODERATE.name == "Moderate"
        assert MODERATE.risk_multiplier == 1.0
        assert MODERATE.signal_weights == {"statistical": 0.5, "sentiment": 0.5}

    def test_aggressive_preset(self) -> None:
        assert AGGRESSIVE.name == "Aggressive"
        assert AGGRESSIVE.risk_multiplier == 1.0
        assert AGGRESSIVE.signal_weights == {"statistical": 0.3, "sentiment": 0.7}

    def test_aggressive_multiplier_equals_or_exceeds_moderate(self) -> None:
        """AGGRESSIVE risk_multiplier must not produce smaller positions than MODERATE."""
        assert AGGRESSIVE.risk_multiplier >= MODERATE.risk_multiplier

    def test_presets_dict_contains_all(self) -> None:
        assert "Conservative" in PRESETS
        assert "Moderate" in PRESETS
        assert "Aggressive" in PRESETS
        assert len(PRESETS) == 3


# --- Multi-profile backtesting tests ---

class TestRunProfiles:
    @pytest.fixture
    def mock_loader(self) -> AsyncMock:
        loader = AsyncMock(spec=DataLoader)
        market = _make_market(
            ticker="KX-MULTI",
            settlement_result=True,
            volume=10000,
            open_interest=5000,
        )
        trade = Trade(
            ticker="KX-MULTI",
            price=55,
            quantity=100,
            side="yes",
            timestamp=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
        )
        loader.get_markets.return_value = [market]
        loader.get_trades.return_value = [trade]
        loader.get_outcomes.return_value = {"KX-MULTI": True}
        return loader

    async def test_run_profiles_returns_all_profiles(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        class PassiveStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return []
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=PassiveStrategy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        results = await engine.run_profiles(
            profiles=[CONSERVATIVE, MODERATE, AGGRESSIVE],
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert "Conservative" in results
        assert "Moderate" in results
        assert "Aggressive" in results
        assert all(isinstance(r, BacktestResult) for r in results.values())

    async def test_run_profiles_isolated_positions(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        class BuyStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [
                    Signal(
                        ticker="KX-MULTI",
                        direction="yes",
                        quantity=5,
                        price_cents=60,
                        estimated_prob=0.70,
                        confidence=0.8,
                    )
                ]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=BuyStrategy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        results = await engine.run_profiles(
            profiles=[CONSERVATIVE, MODERATE],
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert isinstance(results["Conservative"], BacktestResult)
        assert isinstance(results["Moderate"], BacktestResult)

    async def test_run_profiles_standalone_function(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        class PassiveStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return []
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=PassiveStrategy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        results = await run_profiles(
            engine=engine,
            profiles=[CONSERVATIVE, AGGRESSIVE],
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert "Conservative" in results
        assert "Aggressive" in results


# --- compare_profiles tests ---

class TestCompareProfiles:
    def test_compare_profiles_returns_metrics(self) -> None:
        result_a = BacktestResult(
            trade_count=10,
            total_pnl_cents=5000_00,
            winning_trades=7,
            losing_trades=3,
            win_rate=0.7,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.15,
            fill_rate=0.9,
            trades=[],
        )
        result_b = BacktestResult(
            trade_count=5,
            total_pnl_cents=2000_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.0,
            max_drawdown_pct=0.05,
            brier_score=0.25,
            edge_capture=0.10,
            fill_rate=0.8,
            trades=[],
        )

        comparisons = compare_profiles({"Conservative": result_a, "Aggressive": result_b})
        assert len(comparisons) == 2
        names = [c["profile_name"] for c in comparisons]
        assert "Aggressive" in names
        assert "Conservative" in names

    def test_compare_strategies_multi(self) -> None:
        result_a = BacktestResult(
            trade_count=10,
            total_pnl_cents=5000_00,
            winning_trades=7,
            losing_trades=3,
            win_rate=0.7,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.15,
            fill_rate=0.9,
            trades=[],
        )
        result_b = BacktestResult(
            trade_count=5,
            total_pnl_cents=2000_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.0,
            max_drawdown_pct=0.05,
            brier_score=0.25,
            edge_capture=0.10,
            fill_rate=0.8,
            trades=[],
        )
        result_c = BacktestResult(
            trade_count=8,
            total_pnl_cents=3000_00,
            winning_trades=5,
            losing_trades=3,
            win_rate=0.625,
            sharpe_ratio=1.2,
            max_drawdown_pct=0.06,
            brier_score=0.23,
            edge_capture=0.12,
            fill_rate=0.85,
            trades=[],
        )

        comparison = compare_strategies_multi({"A": result_a, "B": result_b, "C": result_c})
        assert isinstance(comparison, MultiStrategyComparison)
        assert len(comparison.profiles) == 3


# --- Risk limit immutability tests ---

class TestRiskImmutability:
    def test_no_profile_can_exceed_hard_limits(self) -> None:
        for profile in PRESETS.values():
            for key in HARD_LIMITS:
                assert profile.effective_limit(key) <= HARD_LIMITS[key]

    def test_conservative_halves_ceilings_floors_at_limit(self) -> None:
        """Conservative: ceilings halved, floors stay at hard limit."""
        _CEILINGS = CONSERVATIVE._CEILING_KEYS
        for key in HARD_LIMITS:
            val = CONSERVATIVE.effective_limit(key)
            if key in _CEILINGS:
                # Ceiling-type: 0.5 * hard limit
                assert val == pytest.approx(0.5 * HARD_LIMITS[key])
            else:
                # Floor-type: max(0.5 * hard, hard) = hard limit
                assert val == HARD_LIMITS[key]

    def test_moderate_equals_hard_limits(self) -> None:
        for key in HARD_LIMITS:
            assert MODERATE.effective_limit(key) == pytest.approx(1.0 * HARD_LIMITS[key])

    def test_aggressive_below_ceilings_at_floors(self) -> None:
        """Aggressive profile: ceilings at full limit, floors stay at hard limit."""
        _CEILINGS = AGGRESSIVE._CEILING_KEYS
        _FLOORS = AGGRESSIVE._FLOOR_KEYS
        for key in HARD_LIMITS:
            val = AGGRESSIVE.effective_limit(key)
            if key in _CEILINGS:
                # Ceiling-type: 1.0 * hard limit (aggressive = full size)
                assert val == pytest.approx(1.0 * HARD_LIMITS[key])
            else:
                # Floor-type (min_*): max(1.0 * hard, hard) = hard limit
                assert val == HARD_LIMITS[key]

    def test_custom_profile_cannot_exceed_hard_limits(self) -> None:
        p = StrategyProfile(
            name="MaxSafe",
            risk_multiplier=1.0,
            signal_weights={"statistical": 1.0},
            category_focus=["economics"],
            description="At the ceiling",
        )
        for key in HARD_LIMITS:
            assert p.effective_limit(key) <= HARD_LIMITS[key]


class TestProfilesProduceDifferentResults:
    """Conservative positions must be smaller than Aggressive positions."""

    async def test_conservative_smaller_than_aggressive(self, tmp_path: Path) -> None:
        SMALL_BANKROLL = 100_000  # $1,000 — small enough that risk sizing constrains quantity
        market = _make_market(
            ticker="KX-DIFF",
            settlement_result=True,
            volume=10000,
            open_interest=5000,
        )
        trade = Trade(
            ticker="KX-DIFF",
            price=55,
            quantity=100,
            side="yes",
            timestamp=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
        )

        class BuyStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [
                    Signal(
                        ticker="KX-DIFF",
                        direction="yes",
                        quantity=100,
                        price_cents=55,
                        estimated_prob=0.70,
                        confidence=0.8,
                    )
                ]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        loader = AsyncMock(spec=DataLoader)
        loader.get_markets.return_value = [market]
        loader.get_trades.return_value = [trade]
        loader.get_outcomes.return_value = {"KX-DIFF": True}

        results = await run_profiles(
            engine=BacktestEngine(
                data_loader=loader,
                strategy=BuyStrategy(),
                initial_bankroll_cents=SMALL_BANKROLL,
                state_dir=tmp_path,
            ),
            profiles=[CONSERVATIVE, AGGRESSIVE],
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert results["Conservative"].trade_count > 0
        assert results["Aggressive"].trade_count > 0
        assert abs(results["Conservative"].total_pnl_cents) < abs(results["Aggressive"].total_pnl_cents)