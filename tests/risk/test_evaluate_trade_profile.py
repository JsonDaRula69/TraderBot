from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

from traderbot.kalshi.models import MarketCategory, PortfolioState, TradeRequest
from traderbot.profiles.models import TradingProfile
from traderbot.risk import evaluate_trade
from traderbot.risk.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    ...

PORTFOLIO_VALUE = 100_000_00  # $100k in cents

def _make_portfolio(**overrides) -> PortfolioState:
    defaults = dict(
        portfolio_value_cents=PORTFOLIO_VALUE,
        peak_value_cents=PORTFOLIO_VALUE,
        current_positions_value_cents=1_000_00,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=1,
    )
    defaults.update(overrides)
    return PortfolioState(**defaults)

def _make_trade(**overrides) -> TradeRequest:
    defaults = dict(
        ticker="KX-TEST",
        direction="yes",
        quantity=5,
        price_cents=50,
        estimated_prob=0.6,
        confidence=0.8,
        edge_estimate=10.0,
        market_price_cents=55,
        market_open_interest=1000,
        market_category=MarketCategory.ECONOMICS,
    )
    defaults.update(overrides)
    return TradeRequest(**defaults)

def _make_profile(**overrides) -> TradingProfile:
    defaults = dict(
        name="test-agent",
        mode="paper",
        description="Test profile",
        enabled_categories=[],
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=20,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    defaults.update(overrides)
    return TradingProfile(**defaults)

class TestEvaluateTradeProfile:
    def test_profile_stricter_than_hard_limits(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Profile with lower risk limit (1% vs 5% hard limit)
        profile = _make_profile(max_position_per_market_pct=0.01)
        trade = _make_trade()
        # Use zero existing position so position limit check passes for both
        portfolio = _make_portfolio(current_positions_value_cents=0, open_positions_count=0)

        # Evaluate with profile (stricter limits)
        profile_size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        
        # Evaluate without profile (HARD_LIMITS)
        hard_limits_size = evaluate_trade(trade, portfolio, breaker, profile=None)
        
        # Profile size should be smaller than hard limits size
        assert profile_size > 0
        assert hard_limits_size > 0
        assert profile_size < hard_limits_size

    def test_disabled_category_rejection(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Profile only enables economics
        profile = _make_profile(enabled_categories=[MarketCategory.ECONOMICS])
        # Trade in sports category (disallowed)
        trade = _make_trade(market_category=MarketCategory.SPORTS)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size == 0

    def test_no_profile_uses_hard_limits(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade()
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=None)
        assert size > 0

    def test_profile_without_agent_risk_limits_uses_profile_params(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Profile with specific multiplier
        profile = _make_profile(risk_multiplier=0.5)
        trade = _make_trade()
        portfolio = _make_portfolio()
        
        # Evaluate with profile with multiplier 0.5
        size_with_profile = evaluate_trade(trade, portfolio, breaker, profile=profile)
        
        # Evaluate with full multiplier
        full_multiplier_profile = _make_profile(risk_multiplier=1.0)
        size_full = evaluate_trade(trade, portfolio, breaker, profile=full_multiplier_profile)
        
        # Profile with multiplier 0.5 should be half of full
        assert size_with_profile > 0
        assert size_full > 0
        assert size_with_profile == size_full // 2

    def test_category_filter_before_risk_math(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Profile with some enabled categories
        profile = _make_profile(enabled_categories=[MarketCategory.ECONOMICS])
        # Trade in banned category (SPORTS)
        trade = _make_trade(market_category=MarketCategory.SPORTS)
        portfolio = _make_portfolio()
        
        # Category should be rejected before risk math
        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size == 0