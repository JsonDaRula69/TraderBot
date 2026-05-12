"""Tests for simulation/profiles.py — StrategyProfile model and multi-profile backtesting."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from traderbot.kalshi.models import Market, Trade
from traderbot.simulation.data_loader import DataLoader
from traderbot.simulation.engine import BacktestEngine, Context, Signal
from traderbot.simulation.profiles import (
    AGGRESSIVE,
    CONSERVATIVE,
    StrategyProfile,
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
        last_price_cents=65,
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


class TestProfilesProduceDifferentResults:
    """Conservative positions must be smaller than Aggressive positions."""

    async def test_conservative_smaller_than_aggressive(self, tmp_path: Path) -> None:
        small_bankroll = 200_000  # $2,000 — small enough that risk sizing constrains quantity
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
                initial_bankroll_cents=small_bankroll,
                state_dir=tmp_path,
            ),
            profiles=[CONSERVATIVE, AGGRESSIVE],
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert results["Conservative"].trade_count > 0
        assert results["Aggressive"].trade_count > 0
        assert abs(results["Conservative"].total_pnl_cents) < abs(results["Aggressive"].total_pnl_cents)
