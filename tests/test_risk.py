from __future__ import annotations

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk import CircuitBreaker, evaluate_trade
from traderbot.risk.limits import (
    HARD_LIMITS,
    check_daily_loss,
    check_drawdown,
    check_liquidity,
    check_max_positions,
    check_min_edge,
    check_position_limit,
    run_all_checks,
)

# ---------------------------------------------------------------------------
# check_position_limit
# ---------------------------------------------------------------------------


class TestCheckPositionLimit:
    def test_passes_when_within_limit(self) -> None:
        result = check_position_limit(
            current_position_value_cents=100_00,
            order_value_cents=50_00,
            portfolio_value_cents=100_000_00,
        )
        assert result.passed is True
        assert result.limit_name == "position_limit"

    def test_fails_when_exceeding_limit(self) -> None:
        result = check_position_limit(
            current_position_value_cents=4_000_00,
            order_value_cents=1_500_00,
            portfolio_value_cents=100_000_00,
        )
        max_allowed = 100_000_00 * HARD_LIMITS["max_position_per_market_pct"]
        assert result.passed is False
        assert result.current_value == 5_500_00
        assert result.limit_value == max_allowed

    def test_custom_limits(self) -> None:
        custom = {"max_position_per_market_pct": 0.10, "max_daily_loss_pct": 0.02, "max_drawdown_pct": 0.10, "min_liquidity_threshold": 500, "max_open_positions": 20, "min_edge_pct": 0.03}
        result = check_position_limit(
            current_position_value_cents=8_000_00,
            order_value_cents=1_000_00,
            portfolio_value_cents=100_000_00,
            limits=custom,
        )
        assert result.passed is True
        assert result.limit_value == 10_000_00

    def test_zero_portfolio_value_rejects(self) -> None:
        """Portfolio value of 0 means 5% of 0 = 0, any order exceeds."""
        result = check_position_limit(
            current_position_value_cents=0,
            order_value_cents=1_00,
            portfolio_value_cents=0,
        )
        assert result.passed is False


# ---------------------------------------------------------------------------
# check_daily_loss
# ---------------------------------------------------------------------------


class TestCheckDailyLoss:
    def test_passes_when_within_limit(self) -> None:
        result = check_daily_loss(
            today_loss_cents=1_000_00,
            portfolio_value_cents=100_000_00,
        )
        assert result.passed is True

    def test_fails_when_exceeding_limit(self) -> None:
        result = check_daily_loss(
            today_loss_cents=3_000_00,
            portfolio_value_cents=100_000_00,
        )
        assert result.passed is False
        assert result.limit_name == "daily_loss"

    def test_zero_loss_always_passes(self) -> None:
        result = check_daily_loss(today_loss_cents=0, portfolio_value_cents=1_000_00)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_drawdown
# ---------------------------------------------------------------------------


class TestCheckDrawdown:
    def test_passes_when_within_limit(self) -> None:
        result = check_drawdown(
            peak_value_cents=110_000_00,
            current_value_cents=105_000_00,
        )
        assert result.passed is True

    def test_fails_when_exceeding_limit(self) -> None:
        result = check_drawdown(
            peak_value_cents=110_000_00,
            current_value_cents=95_000_00,
        )
        assert result.passed is False

    def test_zero_peak_passes(self) -> None:
        result = check_drawdown(peak_value_cents=0, current_value_cents=0)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_liquidity
# ---------------------------------------------------------------------------


class TestCheckLiquidity:
    def test_passes_when_above_threshold(self) -> None:
        result = check_liquidity(open_interest=1000)
        assert result.passed is True

    def test_fails_when_below_threshold(self) -> None:
        result = check_liquidity(open_interest=100)
        assert result.passed is False
        assert result.limit_name == "liquidity"

    def test_exact_threshold_passes(self) -> None:
        result = check_liquidity(open_interest=500)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_max_positions
# ---------------------------------------------------------------------------


class TestCheckMaxPositions:
    def test_passes_when_below_limit(self) -> None:
        result = check_max_positions(current_positions=10)
        assert result.passed is True

    def test_fails_when_at_limit(self) -> None:
        result = check_max_positions(current_positions=20)
        assert result.passed is False

    def test_custom_limit(self) -> None:
        custom = {"max_position_per_market_pct": 0.05, "max_daily_loss_pct": 0.02, "max_drawdown_pct": 0.10, "min_liquidity_threshold": 500, "max_open_positions": 5, "min_edge_pct": 0.03}
        result = check_max_positions(current_positions=4, limits=custom)
        assert result.passed is True
        result2 = check_max_positions(current_positions=5, limits=custom)
        assert result2.passed is False


# ---------------------------------------------------------------------------
# check_min_edge
# ---------------------------------------------------------------------------


class TestCheckMinEdge:
    def test_passes_when_edge_sufficient(self) -> None:
        result = check_min_edge(estimated_prob=0.65, market_price=0.50)
        assert result.passed is True

    def test_fails_when_edge_too_small(self) -> None:
        result = check_min_edge(estimated_prob=0.52, market_price=0.50)
        assert result.passed is False

    def test_exact_threshold_passes(self) -> None:
        result = check_min_edge(estimated_prob=0.53, market_price=0.50)
        assert result.passed is True


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    def test_all_pass_for_conservative_trade(self) -> None:
        trade = TradeRequest(
            ticker="TEST",
            direction="yes",
            quantity=10,
            price_cents=50,
            estimated_prob=0.65,
            confidence=0.8,
            edge_estimate=0.15,
            market_price_cents=50,
            market_open_interest=5000,
        )
        portfolio = PortfolioState(
            portfolio_value_cents=100_000_00,
            peak_value_cents=110_000_00,
            current_positions_value_cents=1_000_00,
            today_realized_loss_cents=100_00,
            today_unrealized_loss_cents=50_00,
            open_positions_count=5,
        )
        results = run_all_checks(trade, portfolio)
        assert all(r.passed for r in results)

    def test_fails_on_low_liquidity(self) -> None:
        trade = TradeRequest(
            ticker="TEST",
            direction="yes",
            quantity=10,
            price_cents=50,
            estimated_prob=0.65,
            confidence=0.8,
            edge_estimate=0.15,
            market_price_cents=50,
            market_open_interest=100,
        )
        portfolio = PortfolioState(
            portfolio_value_cents=100_000_00,
            peak_value_cents=110_000_00,
            current_positions_value_cents=1_000_00,
            today_realized_loss_cents=0,
            today_unrealized_loss_cents=0,
            open_positions_count=5,
        )
        results = run_all_checks(trade, portfolio)
        liquidity_check = [r for r in results if r.limit_name == "liquidity"]
        assert len(liquidity_check) == 1
        assert liquidity_check[0].passed is False


# ---------------------------------------------------------------------------
# evaluate_trade
# ---------------------------------------------------------------------------


class TestEvaluateTrade:
    def test_returns_zero_when_circuit_breaker_halted(self) -> None:
        """evaluate_trade returns 0 when daily loss exceeds HALT_THRESHOLD (2%)."""
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            breaker = CircuitBreaker(state_file=pathlib.Path(td) / "cb.json")
            trade = TradeRequest(
                ticker="TEST",
                direction="yes",
                quantity=10,
                price_cents=50,
                estimated_prob=0.65,
                confidence=0.8,
                edge_estimate=0.15,
                market_price_cents=50,
                market_open_interest=5000,
            )
            portfolio = PortfolioState(
                portfolio_value_cents=100_000_00,
                peak_value_cents=110_000_00,
                current_positions_value_cents=1_000_00,
                today_realized_loss_cents=2_500_00,
                today_unrealized_loss_cents=1_000_00,
                open_positions_count=5,
            )
            sized = evaluate_trade(trade, portfolio, breaker)
            assert sized == 0

    def test_returns_nonzero_for_valid_trade(self) -> None:
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            breaker = CircuitBreaker(state_file=pathlib.Path(td) / "cb.json")
            trade = TradeRequest(
                ticker="TEST",
                direction="yes",
                quantity=10,
                price_cents=50,
                estimated_prob=0.65,
                confidence=0.8,
                edge_estimate=0.15,
                market_price_cents=50,
                market_open_interest=5000,
            )
            portfolio = PortfolioState(
                portfolio_value_cents=100_000_00,
                peak_value_cents=110_000_00,
                current_positions_value_cents=1_000_00,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=5,
            )
            sized = evaluate_trade(trade, portfolio, breaker)
            assert sized > 0
