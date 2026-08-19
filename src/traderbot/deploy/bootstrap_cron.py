"""Inspect and reconcile the OpenClaw bootstrap cron contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy.openclaw_models import (
    CronAgentTurnPayload,
    CronAtSchedule,
    CronJob,
    JsonValue,
)
from traderbot.deploy.wizard_state import BootstrapCronState

BOOTSTRAP_NAME: Final = "traderbot-main-at-5m"
BOOTSTRAP_PROMPT: Final = (
    "Begin the SysAdmin activation protocol: remove this bootstrap job, verify the "
    "TraderBot service and data freshness, register essential jobs, enable the SysAdmin "
    "heartbeat, then activate selected categories one at a time."
)
_DELAY_SECONDS: Final = 300.0
_DELAY_TOLERANCE_SECONDS: Final = 5.0


class SysAdminBootstrapCron(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    id: str = Field(min_length=1)
    name: Literal["traderbot-main-at-5m"]
    agentId: Literal["main"]
    enabled: Literal[True]
    createdAtMs: int = Field(ge=0)
    updatedAtMs: int = Field(ge=0)
    schedule: CronAtSchedule
    sessionTarget: Literal["isolated"]
    wakeMode: Literal["now"]
    payload: CronAgentTurnPayload
    deleteAfterRun: Literal[True]
    state: dict[str, JsonValue]

    @field_validator("state")
    @classmethod
    def pending_state(cls, state: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if state:
            raise PydanticCustomError("bootstrap_state", "one-shot must be active and pending")
        return state

    @model_validator(mode="after")
    def exact_schedule_and_payload(self) -> Self:
        if self.payload.message != BOOTSTRAP_PROMPT:
            raise PydanticCustomError("bootstrap_payload", "activation payload differs")
        scheduled_at = self.schedule.at
        if scheduled_at == "5m":
            return self
        try:
            scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PydanticCustomError(
                "bootstrap_schedule", "one-shot schedule must be a valid absolute timestamp"
            ) from exc
        if scheduled.tzinfo is None:
            raise PydanticCustomError(
                "bootstrap_schedule", "one-shot schedule timestamp must include a timezone"
            )
        created = datetime.fromtimestamp(self.createdAtMs / 1000, tz=UTC)
        if abs((scheduled - created).total_seconds() - _DELAY_SECONDS) > _DELAY_TOLERANCE_SECONDS:
            raise PydanticCustomError(
                "bootstrap_schedule",
                "one-shot schedule must represent the managed five-minute delay",
            )
        return self

    @classmethod
    def is_unique_match(cls, jobs: list[CronJob]) -> bool:
        matches = [job for job in jobs if job.get("name") == BOOTSTRAP_NAME]
        if len(matches) != 1:
            return False
        try:
            _ = cls.model_validate(matches[0])
        except ValidationError:
            return False
        return True

    @classmethod
    def is_completed_match(cls, jobs: list[CronJob]) -> bool:
        if len(jobs) != 1:
            return False
        state = jobs[0].get("state")
        if not isinstance(state, dict) or not state:
            return False
        pending = dict(jobs[0])
        pending["state"] = {}
        try:
            _ = cls.model_validate(pending)
        except ValidationError:
            return False
        return state.get("lastStatus") == "ok" and isinstance(state.get("lastRunAtMs"), int)


def classify_bootstrap_crons(jobs: list[CronJob] | None) -> BootstrapCronState:
    if jobs is None:
        return BootstrapCronState.FAILED
    matches = [job for job in jobs if job.get("name") == BOOTSTRAP_NAME]
    if not matches:
        return BootstrapCronState.MISSING
    if SysAdminBootstrapCron.is_completed_match(matches):
        return BootstrapCronState.COMPLETED_RETAINED
    return (
        BootstrapCronState.EXACT
        if SysAdminBootstrapCron.is_unique_match(matches)
        else BootstrapCronState.CONFLICT
    )


__all__ = [
    "BOOTSTRAP_NAME",
    "BOOTSTRAP_PROMPT",
    "SysAdminBootstrapCron",
    "classify_bootstrap_crons",
]
