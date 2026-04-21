"""Three-tier circuit breaker enforcing loss and drawdown limits."""

from __future__ import annotations

import enum
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BreakerLevel(enum.IntEnum):
    NORMAL = 0
    SLOW = 1
    HALT = 2
    FULL_STOP = 3


SLOW_THRESHOLD = 0.01
HALT_THRESHOLD = 0.02
FULL_STOP_THRESHOLD = 0.10


class CircuitBreakerState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    level: BreakerLevel = BreakerLevel.NORMAL
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    position_size_multiplier: float = 1.0
    can_trade: bool = True
    reason: str = ""


class CircuitBreaker:
    def __init__(self, state_file: Path | None = None) -> None:
        self._state_file = state_file or Path.home() / ".traderbot" / "circuit_breaker_state.json"
        self._state = CircuitBreakerState()
        self._load_state()

    def check(self, daily_loss_pct: float, drawdown_pct: float) -> CircuitBreakerState:
        if self._state.level == BreakerLevel.FULL_STOP:
            self._state.daily_loss_pct = daily_loss_pct
            self._state.drawdown_pct = drawdown_pct
            self._persist_state()
            return self._state.model_copy()

        if drawdown_pct >= FULL_STOP_THRESHOLD:
            self._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.0,
                can_trade=False,
                reason=f"Drawdown {drawdown_pct:.2%} exceeds {FULL_STOP_THRESHOLD:.0%}",
            )
        elif daily_loss_pct >= HALT_THRESHOLD:
            self._state = CircuitBreakerState(
                level=BreakerLevel.HALT,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.0,
                can_trade=False,
                reason=f"Daily loss {daily_loss_pct:.2%} exceeds {HALT_THRESHOLD:.0%}",
            )
        elif daily_loss_pct >= SLOW_THRESHOLD:
            self._state = CircuitBreakerState(
                level=BreakerLevel.SLOW,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                position_size_multiplier=0.5,
                can_trade=True,
                reason=f"Daily loss {daily_loss_pct:.2%} exceeds {SLOW_THRESHOLD:.0%}",
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
        self._state_file.write_text(self._state.model_dump_json() + "\n")

    def _load_state(self) -> None:
        if self._state_file.exists():
            data = json.loads(self._state_file.read_text())
            if isinstance(data.get("level"), int):
                data["level"] = BreakerLevel(data["level"])
            self._state = CircuitBreakerState.model_validate(data)
