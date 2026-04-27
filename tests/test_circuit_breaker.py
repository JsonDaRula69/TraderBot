from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "circuit_breaker_state.json"


@pytest.fixture
def cb(state_file: Path) -> CircuitBreaker:
    return CircuitBreaker(state_file=state_file)


class TestNormalState:
    def test_no_thresholds_crossed(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.03)
        assert state.level == BreakerLevel.NORMAL
        assert state.position_size_multiplier == 1.0
        assert state.can_trade is True
        assert state.reason == ""

    def test_zero_loss(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL


class TestSlowActivation:
    def test_at_exactly_1pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        assert state.position_size_multiplier == 0.5
        assert state.can_trade is True

    def test_above_1pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW


class TestHaltActivation:
    def test_at_exactly_2pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        assert state.level == BreakerLevel.HALT
        assert state.position_size_multiplier == 0.0
        assert state.can_trade is False

    def test_above_2pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.025, drawdown_pct=0.0)
        assert state.level == BreakerLevel.HALT


class TestFullStopActivation:
    def test_at_exactly_10pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert state.level == BreakerLevel.FULL_STOP
        assert state.position_size_multiplier == 0.0
        assert state.can_trade is False

    def test_above_10pct(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.15)
        assert state.level == BreakerLevel.FULL_STOP


class TestPositionSizeMultiplier:
    def test_normal(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.01)
        assert state.position_size_multiplier == 1.0

    def test_slow(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.01)
        assert state.position_size_multiplier == 0.5

    def test_halt(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.01)
        assert state.position_size_multiplier == 0.0

    def test_full_stop(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert state.position_size_multiplier == 0.0


class TestCanTrade:
    def test_normal(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.01)
        assert state.can_trade is True

    def test_slow(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.01)
        assert state.can_trade is True

    def test_halt(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.01)
        assert state.can_trade is False

    def test_full_stop(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert state.can_trade is False


class TestFullStopPersists:
    def test_drawdown_improves(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.level == BreakerLevel.FULL_STOP

    def test_daily_loss_improves(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.05, drawdown_pct=0.10)
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.level == BreakerLevel.FULL_STOP


class TestClearFullStop:
    def test_resets_to_normal(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        cb.clear_full_stop()
        state = cb.get_state()
        assert state.level == BreakerLevel.NORMAL
        assert state.position_size_multiplier == 1.0
        assert state.can_trade is True

    def test_raises_when_not_in_full_stop(self, cb: CircuitBreaker) -> None:
        with pytest.raises(RuntimeError, match="Not in FULL_STOP state"):
            cb.clear_full_stop()

    def test_raises_in_slow(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        with pytest.raises(RuntimeError, match="Not in FULL_STOP state"):
            cb.clear_full_stop()

    def test_raises_in_halt(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        with pytest.raises(RuntimeError, match="Not in FULL_STOP state"):
            cb.clear_full_stop()


class TestStatePersistence:
    def test_writes_json_to_file(self, cb: CircuitBreaker, state_file: Path) -> None:
        cb.check(daily_loss_pct=0.01, drawdown_pct=0.02)
        data = json.loads(state_file.read_text())
        assert data["level"] == 1
        assert data["daily_loss_pct"] == 0.01
        assert data["drawdown_pct"] == 0.02
        assert data["position_size_multiplier"] == 0.5

    def test_loads_state_on_init(self, state_file: Path) -> None:
        cb1 = CircuitBreaker(state_file=state_file)
        cb1.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        cb2 = CircuitBreaker(state_file=state_file)
        state = cb2.get_state()
        assert state.level == BreakerLevel.FULL_STOP

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        state_file = tmp_path / "subdir" / "state.json"
        cb = CircuitBreaker(state_file=state_file)
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.0)
        assert state_file.exists()


class TestAutoRecovery:
    def test_slow_to_normal(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        assert cb.get_state().level == BreakerLevel.SLOW
        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL
        assert state.position_size_multiplier == 1.0
        assert state.can_trade is True

    def test_halt_to_normal_via_slow(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        assert cb.get_state().level == BreakerLevel.HALT
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL


class TestGetState:
    def test_returns_copy(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        s1 = cb.get_state()
        s1.level = BreakerLevel.NORMAL
        s2 = cb.get_state()
        assert s2.level == BreakerLevel.SLOW


class TestExactThresholds:
    """Verify circuit breaker triggers at EXACT threshold values from limits.py."""

    def test_slow_at_exactly_1pct_daily_loss(self, cb: CircuitBreaker) -> None:
        """Circuit breaker SLOW triggers at exactly 1% daily loss."""
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        assert state.can_trade is True
        assert state.position_size_multiplier == 0.5

    def test_below_1pct_daily_loss_is_normal(self, cb: CircuitBreaker) -> None:
        """0.99% daily loss does NOT trigger SLOW — must be at or above exactly 1%."""
        state = cb.check(daily_loss_pct=0.0099, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True
        assert state.position_size_multiplier == 1.0

    def test_halt_at_exactly_2pct_daily_loss(self, cb: CircuitBreaker) -> None:
        """Circuit breaker HALT triggers at exactly 2% daily loss."""
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        assert state.level == BreakerLevel.HALT
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

    def test_below_2pct_daily_loss_is_slow(self, cb: CircuitBreaker) -> None:
        """1.99% daily loss triggers SLOW, not HALT."""
        state = cb.check(daily_loss_pct=0.0199, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        assert state.can_trade is True

    def test_full_stop_at_exactly_10pct_drawdown(self, cb: CircuitBreaker) -> None:
        """Circuit breaker FULL_STOP triggers at exactly 10% drawdown."""
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert state.level == BreakerLevel.FULL_STOP
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

    def test_below_10pct_drawdown_is_not_full_stop(self, cb: CircuitBreaker) -> None:
        """9.99% drawdown does NOT trigger FULL_STOP."""
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.0999)
        assert state.level != BreakerLevel.FULL_STOP

    def test_thresholds_match_hard_limits(self) -> None:
        """Verify circuit breaker thresholds match HARD_LIMITS in limits.py."""
        from traderbot.risk.circuit_breaker import FULL_STOP_THRESHOLD, HALT_THRESHOLD, SLOW_THRESHOLD
        from traderbot.risk.limits import HARD_LIMITS

        # SLOW_THRESHOLD = 1% matches daily_loss_pct guard
        assert SLOW_THRESHOLD == 0.01
        # HALT_THRESHOLD = 2% matches max_daily_loss_pct
        assert HALT_THRESHOLD == HARD_LIMITS["max_daily_loss_pct"]
        # FULL_STOP_THRESHOLD = 10% matches max_drawdown_pct
        assert FULL_STOP_THRESHOLD == HARD_LIMITS["max_drawdown_pct"]


class TestCircuitBreakerStateExtraForbidden:
    def test_extra_field_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError

        from traderbot.risk.circuit_breaker import CircuitBreakerState

        with pytest.raises(ValidationError):
            CircuitBreakerState(level=BreakerLevel.NORMAL, extra_field=True)
