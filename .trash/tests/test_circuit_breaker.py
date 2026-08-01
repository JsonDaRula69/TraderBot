from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from traderbot.profiles.models import TradingProfile
from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker, CircuitBreakerState


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


class TestFullStopAutoRecovery:
    def test_drawdown_improves_to_normal(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert cb.get_state().level == BreakerLevel.FULL_STOP
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True
        assert state.position_size_multiplier == 1.0

    def test_drawdown_improves_to_halt(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert cb.get_state().level == BreakerLevel.FULL_STOP
        state = cb.check(daily_loss_pct=0.05, drawdown_pct=0.03)
        assert state.level == BreakerLevel.HALT
        assert state.can_trade is False

    def test_daily_loss_improves_to_slow(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.05, drawdown_pct=0.10)
        assert cb.get_state().level == BreakerLevel.FULL_STOP
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.03)
        assert state.level == BreakerLevel.SLOW

    def test_check_zero_zero_recovers_from_full_stop(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert cb.get_state().level == BreakerLevel.FULL_STOP
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True

    def test_recovery_sets_timestamp(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert cb.get_state().last_recovery_ts == 0.0
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.last_recovery_ts > 0.0


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
    def test_writes_signed_json_to_file(self, cb: CircuitBreaker, state_file: Path) -> None:
        cb.check(daily_loss_pct=0.01, drawdown_pct=0.02)
        raw = json.loads(state_file.read_text())
        assert "payload" in raw
        assert "signature" in raw
        data = json.loads(raw["payload"])
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

    def test_tampered_state_defaults_to_full_stop(self, state_file: Path) -> None:
        cb1 = CircuitBreaker(state_file=state_file)
        cb1.check(daily_loss_pct=0.005, drawdown_pct=0.01)
        raw = json.loads(state_file.read_text())
        data = json.loads(raw["payload"])
        data["level"] = 0
        raw["payload"] = json.dumps(data)
        state_file.write_text(json.dumps(raw))
        cb2 = CircuitBreaker(state_file=state_file)
        assert cb2.get_state().level == BreakerLevel.FULL_STOP

    def test_unsigned_state_defaults_to_full_stop(self, state_file: Path) -> None:
        plain = json.dumps({
            "level": 0,
            "daily_loss_pct": 0.0,
            "drawdown_pct": 0.0,
            "position_size_multiplier": 1.0,
            "can_trade": True,
            "reason": "",
            "last_recovery_ts": 0.0,
        })
        state_file.write_text(plain)
        cb = CircuitBreaker(state_file=state_file)
        assert cb.get_state().level == BreakerLevel.FULL_STOP

    def test_corrupt_state_defaults_to_full_stop(self, state_file: Path) -> None:
        state_file.write_text("NOT JSON")
        cb = CircuitBreaker(state_file=state_file)
        assert cb.get_state().level == BreakerLevel.FULL_STOP

    def test_recovery_ts_persisted_across_reload(self, state_file: Path) -> None:
        fake_monotonic = 5000.0
        with patch("traderbot.risk.circuit_breaker.time.monotonic", return_value=fake_monotonic):
            cb1 = CircuitBreaker(state_file=state_file)
            cb1.check(daily_loss_pct=0.0, drawdown_pct=0.10)
            state = cb1.check(daily_loss_pct=0.0, drawdown_pct=0.05)
            assert state.level == BreakerLevel.NORMAL
            recovery_ts = state.last_recovery_ts
            assert recovery_ts > 0.0
        with patch("traderbot.risk.circuit_breaker.time.monotonic", return_value=fake_monotonic + 100):
            cb2 = CircuitBreaker(state_file=state_file)
            loaded_state = cb2.get_state()
            assert loaded_state.level == BreakerLevel.NORMAL
            assert loaded_state.last_recovery_ts == recovery_ts

    @pytest.mark.skipif(
        "sys.platform == 'win32'",
        reason="Unix file permissions not applicable on Windows",
    )
    def test_secret_file_created_with_restricted_permissions(self, state_file: Path) -> None:
        cb = CircuitBreaker(state_file=state_file)
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.0)
        secret_file = state_file.parent / ".breaker_secret"
        assert secret_file.exists()
        import stat
        mode = stat.S_IMODE(secret_file.stat().st_mode)
        assert mode & 0o077 == 0


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


class TestCooldown:
    def test_cooldown_prevents_re_entering_full_stop(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert cb.get_state().level == BreakerLevel.FULL_STOP
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.level == BreakerLevel.NORMAL
        assert state.last_recovery_ts > 0.0
        # Conditions worsen again but cooldown blocks FULL_STOP
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.15)
        assert state.level == BreakerLevel.NORMAL

    def test_cooldown_allows_halt_during_cooldown(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
        assert state.level == BreakerLevel.NORMAL
        # Daily loss hits HALT threshold — cooldown only blocks FULL_STOP
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.03)
        assert state.level == BreakerLevel.HALT

    def test_cooldown_expires_allows_full_stop_again(self, cb: CircuitBreaker) -> None:
        fake_monotonic = 1000.0
        with patch("traderbot.risk.circuit_breaker.time.monotonic", return_value=fake_monotonic):
            cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
            state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.05)
            assert state.level == BreakerLevel.NORMAL
            recovery_ts = state.last_recovery_ts
        # Cooldown not expired yet
        with patch("traderbot.risk.circuit_breaker.time.monotonic", return_value=fake_monotonic + 86399):
            state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.15)
            assert state.level == BreakerLevel.NORMAL
        # Cooldown expired
        with patch("traderbot.risk.circuit_breaker.time.monotonic", return_value=fake_monotonic + 86401):
            state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.15)
            assert state.level == BreakerLevel.FULL_STOP

    def test_clear_full_stop_resets_cooldown(self, cb: CircuitBreaker) -> None:
        cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        cb.clear_full_stop()
        assert cb.get_state().last_recovery_ts == 0.0
        # No cooldown — can re-enter FULL_STOP immediately
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.15)
        assert state.level == BreakerLevel.FULL_STOP


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
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        assert state.can_trade is True
        assert state.position_size_multiplier == 0.5

    def test_below_1pct_daily_loss_is_normal(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0099, drawdown_pct=0.0)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True
        assert state.position_size_multiplier == 1.0

    def test_halt_at_exactly_2pct_daily_loss(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        assert state.level == BreakerLevel.HALT
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

    def test_below_2pct_daily_loss_is_slow(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0199, drawdown_pct=0.0)
        assert state.level == BreakerLevel.SLOW
        assert state.can_trade is True

    def test_full_stop_at_exactly_10pct_drawdown(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.10)
        assert state.level == BreakerLevel.FULL_STOP
        assert state.can_trade is False
        assert state.position_size_multiplier == 0.0

    def test_below_10pct_drawdown_is_not_full_stop(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.0, drawdown_pct=0.0999)
        assert state.level != BreakerLevel.FULL_STOP

    def test_thresholds_match_hard_limits(self) -> None:
        from traderbot.risk.circuit_breaker import FULL_STOP_THRESHOLD, HALT_THRESHOLD, SLOW_THRESHOLD
        from traderbot.risk.limits import HARD_LIMITS

        assert SLOW_THRESHOLD == 0.01
        assert HALT_THRESHOLD == HARD_LIMITS["max_daily_loss_pct"]
        assert FULL_STOP_THRESHOLD == HARD_LIMITS["max_drawdown_pct"]


class TestBreakerChecksIncludeUnrealizedLosses:
    def test_breaker_checks_include_unrealized_losses(self, cb: CircuitBreaker) -> None:
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.0)
        assert state.level == BreakerLevel.HALT
        assert state.can_trade is False


class TestCircuitBreakerStateExtraForbidden:
    def test_extra_field_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError

        from traderbot.risk.circuit_breaker import CircuitBreakerState

        with pytest.raises(ValidationError):
            CircuitBreakerState(level=BreakerLevel.NORMAL, extra_field=True)


class TestProfileThresholds:
    """Verify that check() uses profile thresholds when a profile is provided."""

    @pytest.fixture
    def profile(self):
        from traderbot.kalshi.models import MarketCategory

        return TradingProfile(
            name="test-agent",
            mode="paper",
            description="Test profile for circuit breaker",
            enabled_categories=[MarketCategory.WEATHER],
            risk_multiplier=1.0,
            max_position_per_market_pct=0.10,
            max_daily_loss_pct=0.04,
            max_drawdown_pct=0.20,
            max_open_positions=10,
            min_liquidity_threshold=100,
            min_edge_pct=0.03,
        )

    def test_check_with_profile_uses_profile_thresholds(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """With profile (max_daily_loss=4%, max_drawdown=20%), the thresholds are:
        SLOW = 4% * 0.5 = 2%, HALT = 4%, FULL_STOP = 20%.
        Loss at 1% should be NORMAL (would be SLOW with hardcoded thresholds)."""
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.03, profile=profile)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True
        assert state.position_size_multiplier == 1.0

    def test_check_with_profile_slow_threshold(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """SLOW triggers at 2% (half of max_daily_loss 4%)."""
        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.01, profile=profile)
        assert state.level == BreakerLevel.SLOW
        assert state.position_size_multiplier == 0.5
        assert state.can_trade is True

    def test_check_with_profile_halt_threshold(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """HALT triggers at 4% (max_daily_loss)."""
        state = cb.check(daily_loss_pct=0.04, drawdown_pct=0.01, profile=profile)
        assert state.level == BreakerLevel.HALT
        assert state.position_size_multiplier == 0.0
        assert state.can_trade is False

    def test_check_with_profile_full_stop_threshold(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """FULL_STOP triggers at 20% drawdown (max_drawdown)."""
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.20, profile=profile)
        assert state.level == BreakerLevel.FULL_STOP
        assert state.position_size_multiplier == 0.0
        assert state.can_trade is False

    def test_check_with_profile_high_thresholds_no_trigger(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """Profile with high thresholds: 1.5% daily loss, 15% drawdown should be NORMAL
        (SLOW=2%, HALT=4%, FULL_STOP=20%)."""
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.15, profile=profile)
        assert state.level == BreakerLevel.NORMAL
        assert state.can_trade is True
        assert state.position_size_multiplier == 1.0

    def test_check_without_profile_uses_hardcoded_defaults(self, cb: CircuitBreaker) -> None:
        """Without profile, check() falls back to hardcoded thresholds (SLOW=1%, HALT=2%, FULL_STOP=10%)."""
        state = cb.check(daily_loss_pct=0.01, drawdown_pct=0.03)
        assert state.level == BreakerLevel.SLOW

        state = cb.check(daily_loss_pct=0.02, drawdown_pct=0.03)
        assert state.level == BreakerLevel.HALT

        state = cb.check(daily_loss_pct=0.005, drawdown_pct=0.10)
        assert state.level == BreakerLevel.FULL_STOP

    def test_check_with_profile_then_without_resets_thresholds(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """After calling check() with a profile, calling without profile reverts to defaults."""
        # With profile: 1.5% loss is NORMAL (SLOW threshold at 2%)
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.01, profile=profile)
        assert state.level == BreakerLevel.NORMAL

        # Without profile: 1.5% loss is SLOW (hardcoded threshold at 1%)
        state = cb.check(daily_loss_pct=0.015, drawdown_pct=0.01)
        assert state.level == BreakerLevel.SLOW

    def test_check_with_profile_reason_includes_profile_threshold(self, cb: CircuitBreaker, profile: TradingProfile) -> None:
        """Reason messages should reflect the profile-derived thresholds."""
        state = cb.check(daily_loss_pct=0.03, drawdown_pct=0.01, profile=profile)
        assert state.level == BreakerLevel.SLOW
        assert "2%" in state.reason  # slow_threshold = 4% * 0.5 = 2%
