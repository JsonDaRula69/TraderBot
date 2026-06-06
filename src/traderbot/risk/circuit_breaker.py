"""Three-tier circuit breaker enforcing loss and drawdown limits."""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import os
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from traderbot.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


class BreakerLevel(enum.IntEnum):
    NORMAL = 0
    SLOW = 1
    HALT = 2
    FULL_STOP = 3


SLOW_THRESHOLD = 0.01
HALT_THRESHOLD = 0.02
FULL_STOP_THRESHOLD = 0.10

FULL_STOP_RECOVERY_COOLDOWN_SECS = 86400  # 24 hours


class CircuitBreakerState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    level: BreakerLevel = BreakerLevel.NORMAL
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    position_size_multiplier: float = 1.0
    can_trade: bool = True
    reason: str = ""
    last_recovery_ts: float = 0.0


class CircuitBreaker:
    def __init__(self, state_file: Path | None = None) -> None:
        self._state_file = state_file or get_data_dir() / "circuit_breaker_state.json"
        self._secret_file = self._state_file.parent / ".breaker_secret"
        self._state = CircuitBreakerState()
        self._load_state()

    def check(
        self,
        daily_loss_pct: float,
        drawdown_pct: float,
        profile: TradingProfile | None = None,
    ) -> CircuitBreakerState:
        if profile is not None:
            slow_threshold = profile.max_daily_loss_pct * 0.5
            halt_threshold = profile.max_daily_loss_pct
            full_stop_threshold = profile.max_drawdown_pct
        else:
            slow_threshold = SLOW_THRESHOLD
            halt_threshold = HALT_THRESHOLD
            full_stop_threshold = FULL_STOP_THRESHOLD

        previous_level = self._state.level
        in_cooldown = (
            self._state.last_recovery_ts > 0
            and 0 < (time.monotonic() - self._state.last_recovery_ts) < FULL_STOP_RECOVERY_COOLDOWN_SECS
        )

        if drawdown_pct >= full_stop_threshold and not in_cooldown:
            self._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.0,
                can_trade=False,
                reason=f"Drawdown {drawdown_pct:.2%} exceeds {full_stop_threshold:.0%}",
            )
        elif daily_loss_pct >= halt_threshold:
            self._state = CircuitBreakerState(
                level=BreakerLevel.HALT,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.0,
                can_trade=False,
                reason=f"Daily loss {daily_loss_pct:.2%} exceeds {halt_threshold:.0%}",
            )
        elif daily_loss_pct >= slow_threshold:
            self._state = CircuitBreakerState(
                level=BreakerLevel.SLOW,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.5,
                can_trade=True,
                reason=f"Daily loss {daily_loss_pct:.2%} exceeds {slow_threshold:.0%}",
            )
        else:
            self._state = CircuitBreakerState(
                level=BreakerLevel.NORMAL,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=1.0,
                can_trade=True,
                reason="",
            )

        # Record recovery timestamp when transitioning from FULL_STOP to a lower level
        if previous_level == BreakerLevel.FULL_STOP and self._state.level != BreakerLevel.FULL_STOP:
            self._state = self._state.model_copy(update={"last_recovery_ts": time.monotonic()})
            logger.info(
                "Circuit breaker auto-recovered from FULL_STOP to %s",
                self._state.level.name,
            )

        self._persist_state()
        return self._state.model_copy()

    def clear_full_stop(self) -> None:
        if self._state.level != BreakerLevel.FULL_STOP:
            raise RuntimeError("Not in FULL_STOP state")
        self._state = CircuitBreakerState()
        self._persist_state()

    def get_state(self) -> CircuitBreakerState:
        return self._state.model_copy()

    def _persist_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = self._state.model_dump_json() + "\n"
        secret = self._get_or_create_secret()
        signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        signed = {"payload": payload, "signature": signature}
        self._state_file.write_text(json.dumps(signed) + "\n")
        self._state_file.chmod(0o600)

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Circuit breaker state file corrupt — defaulting to FULL_STOP (fail-secure)"
            )
            self._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                reason="State file corrupt — manual clearance required",
                can_trade=False,
                position_size_multiplier=0.0,
            )
            return
        if "payload" not in raw or "signature" not in raw:
            logger.warning("Circuit breaker state unsigned — defaulting to FULL_STOP (fail-secure)")
            self._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                reason="State file unsigned — manual clearance required",
                can_trade=False,
                position_size_multiplier=0.0,
            )
            return
        payload = raw["payload"]
        signature = raw["signature"]
        secret = self._get_or_create_secret()
        expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning(
                "Circuit breaker HMAC verification failed — defaulting to FULL_STOP (fail-secure)"
            )
            self._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                reason="HMAC verification failed — manual clearance required",
                can_trade=False,
                position_size_multiplier=0.0,
            )
            return
        data = json.loads(payload)
        if isinstance(data.get("level"), int):
            data["level"] = BreakerLevel(data["level"])
        self._state = CircuitBreakerState.model_validate(data)

    def _get_or_create_secret(self) -> bytes:
        """Load or generate the HMAC signing key for state file integrity."""
        if self._secret_file.exists():
            return self._secret_file.read_bytes().strip()
        secret = os.urandom(32)
        self._secret_file.parent.mkdir(parents=True, exist_ok=True)
        self._secret_file.write_bytes(secret)
        self._secret_file.chmod(0o600)
        return secret
