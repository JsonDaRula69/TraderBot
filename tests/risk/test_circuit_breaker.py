"""Tests for CircuitBreaker — FULL_STOP clearance via validated deployment."""

import tempfile
from pathlib import Path

import pytest

from traderbot.risk.circuit_breaker import (
    FULL_STOP_THRESHOLD,
    BreakerLevel,
    CircuitBreaker,
    CircuitBreakerState,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def breaker() -> CircuitBreaker:
    """CircuitBreaker backed by a temp file with HMAC signing disabled."""
    td = Path(tempfile.mkdtemp())
    sf = td / "circuit_breaker_state.json"
    cb = CircuitBreaker(state_file=sf)
    # Remove the secret file so HMAC verification is skipped on reload,
    # otherwise tampering with state file causes fail-secure FULL_STOP.
    secret = sf.parent / ".breaker_secret"
    if secret.exists():
        secret.unlink()
    return cb


def _force_full_stop(cb: CircuitBreaker) -> None:
    """Force the breaker into FULL_STOP state for testing."""
    cb._state = CircuitBreakerState(
        level=BreakerLevel.FULL_STOP,
        daily_loss_pct=0.12,
        drawdown_pct=0.12,
        position_size_multiplier=0.0,
        can_trade=False,
        reason="Test: forced FULL_STOP",
    )


# ── clear_full_stop ──────────────────────────────────────────────


def test_clear_full_stop_raises_when_not_in_full_stop(breaker):
    with pytest.raises(RuntimeError, match="Not in FULL_STOP state"):
        breaker.clear_full_stop()


def test_clear_full_stop_resets_state(breaker):
    _force_full_stop(breaker)
    breaker.clear_full_stop()
    assert breaker._state.level == BreakerLevel.NORMAL
    assert breaker._state.can_trade is True
    assert breaker._state.reason == ""


# ── clear_full_stop_on_deploy (validated deployment) ─────────────


def test_clear_full_stop_on_deploy_meets_all_bars(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=1.34,
        win_rate_improvement_pp=8.2,
        sample_count=87,
        agent_id="test-agent",
    )
    assert result is True
    assert breaker._state.level == BreakerLevel.NORMAL
    assert breaker._state.can_trade is True


def test_clear_full_stop_on_deploy_meets_exact_bars(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=1.0,
        win_rate_improvement_pp=5.0,
        sample_count=30,
    )
    assert result is True
    assert breaker._state.level == BreakerLevel.NORMAL


# ── clear_full_stop_on_deploy (UNABLE to clear) ──────────────────


def test_clear_full_stop_on_deploy_sharpe_too_low(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=0.85,
        win_rate_improvement_pp=10.0,
        sample_count=100,
    )
    assert result is False
    assert breaker._state.level == BreakerLevel.FULL_STOP


def test_clear_full_stop_on_deploy_win_rate_too_low(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=1.5,
        win_rate_improvement_pp=3.0,
        sample_count=100,
    )
    assert result is False
    assert breaker._state.level == BreakerLevel.FULL_STOP


def test_clear_full_stop_on_deploy_samples_too_few(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=1.5,
        win_rate_improvement_pp=10.0,
        sample_count=15,
    )
    assert result is False
    assert breaker._state.level == BreakerLevel.FULL_STOP


def test_clear_full_stop_on_deploy_sharpe_negative(breaker):
    _force_full_stop(breaker)
    result = breaker.clear_full_stop_on_deploy(
        sharpe=-0.5,
        win_rate_improvement_pp=10.0,
        sample_count=100,
    )
    assert result is False
    assert breaker._state.level == BreakerLevel.FULL_STOP


# ── No-op when not in FULL_STOP ──────────────────────────────────


def test_clear_full_stop_on_deploy_not_in_full_stop_returns_false(breaker):
    """When not in FULL_STOP, returns False (no-op)."""
    result = breaker.clear_full_stop_on_deploy(
        sharpe=2.0,
        win_rate_improvement_pp=15.0,
        sample_count=200,
    )
    assert result is False
    assert breaker._state.level == BreakerLevel.NORMAL


# ── Full cycle: check() → FULL_STOP → deploy_clear → NORMAL ─────


def test_full_stop_then_deploy_clear_resumes_trading(breaker):
    """Simulate: tripped by drawdown → cleared by validated deployment."""
    # Trip to FULL_STOP
    result = breaker.check(
        daily_loss_pct=0.0,
        drawdown_pct=FULL_STOP_THRESHOLD,
    )
    assert result.level == BreakerLevel.FULL_STOP

    # Attempt clearance with sub-bar metrics — should fail
    fail = breaker.clear_full_stop_on_deploy(
        sharpe=0.9, win_rate_improvement_pp=3.0, sample_count=10
    )
    assert fail is False
    assert breaker._state.level == BreakerLevel.FULL_STOP

    # Validated deployment clears it
    ok = breaker.clear_full_stop_on_deploy(
        sharpe=1.2, win_rate_improvement_pp=6.0, sample_count=50, agent_id="cycle-agent"
    )
    assert ok is True
    assert breaker._state.level == BreakerLevel.NORMAL
    assert breaker._state.can_trade is True
    assert breaker._state.position_size_multiplier == 1.0
    assert breaker._state.reason == ""
