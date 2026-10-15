"""Typed first-party OpenClaw JSON response models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator
from pydantic_core import PydanticCustomError

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type CronJob = dict[str, JsonValue]


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)


class JsonObject(RootModel[dict[str, JsonValue]]):
    pass


class ConfigReadState(StrEnum):
    """Tri-state of one raw ``config get --json`` read (T8 step-7 seam)."""

    FOUND = "found"
    ABSENT = "absent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ConfigValueRead:
    """Untyped JSON value read: scalars/arrays/objects pass through verbatim.

    Step 7's backup/verify loop must record and byte-compare RAW values (the
    typed read models deliberately narrow the shape), so this result carries
    the parsed :data:`JsonValue` without a model, plus the explicit
    ABSENT-vs-FAILED distinction the fail-closed rules require.
    """

    state: ConfigReadState
    value: JsonValue | None = None


class SetupResult(StrictModel):
    ok: Literal[True]
    configPath: str = Field(min_length=1)
    configStatus: str = Field(min_length=1)
    workspaceDir: str = Field(min_length=1)
    sessionsDir: str = Field(min_length=1)


class DoctorFinding(StrictModel):
    checkId: str = Field(min_length=1)
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1)


class DoctorResult(StrictModel):
    ok: Literal[True]
    checksRun: int = Field(ge=0)
    checksSkipped: int = Field(ge=0)
    findings: list[DoctorFinding]


class GatewayRpc(StrictModel):
    ok: Literal[True]


class GatewayResult(StrictModel):
    rpc: GatewayRpc


class ConfigChecks(StrictModel):
    schema_valid: Literal[True] = Field(alias="schema")
    resolvability: Literal[True]
    resolvabilityComplete: Literal[True]


class ConfigDryRun(StrictModel):
    ok: Literal[True]
    operations: int = Field(ge=1)
    configPath: str = Field(min_length=1)
    inputModes: list[Literal["value", "json", "builder", "unset"]] = Field(min_length=1)
    checks: ConfigChecks
    refsChecked: int = Field(ge=0)
    skippedExecRefs: int = Field(ge=0)


class ConfigGetError(StrictModel):
    error: str = Field(min_length=1)


class HeartbeatConfig(StrictModel):
    every: str | None = None


class SandboxDockerConfig(BaseModel):
    """Pinned ``SandboxDockerSchema`` subset: strict and extra-forbid (D4/D9).

    Property names are the pinned schema's verbatim; only the owner-approved D9
    dangerous-* pair exists here, so parsing a config carrying any extra docker
    key (including ``dangerouslyAllowContainerNamespaceJoin``) fails closed.

    A-DCFG-KEYS (todo-8 amendment): the four hardening keys are admitted with
    pinned values. Evidence: the pinned 2026.7.1-2 ``SandboxDockerSchema``
    (re-read from the installed Gateway package for the standing ruling)
    defines ``readOnlyRoot``/``network``/``user``/``capDrop`` as OPTIONAL
    WITHOUT defaults (``default: <undefined>`` on each), and the gateway
    sandbox runtime emits ``--read-only``/``--network``/``--user``/
    ``--cap-drop`` ONLY when the key is truthy — omitting any of them
    silently yields Docker defaults (writable rootfs, bridge network, root
    user, full capabilities). The writer always emits all four pinned values;
    this strict read model admits exactly those values, nothing else.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    image: str
    binds: list[str]
    dangerouslyAllowExternalBindSources: bool
    dangerouslyAllowReservedContainerTargets: bool
    readOnlyRoot: Literal[True] | None = None
    network: Literal["none"] | None = None
    user: Literal["1000:1000"] | None = None
    capDrop: Annotated[list[Literal["ALL"]] | None, Field(min_length=1, max_length=1)] = None


class SandboxConfig(StrictModel):
    """Pinned ``AgentSandboxSchema`` read model; ``workspaceAccess`` is deploy-narrowed to none."""

    mode: str | None = None
    workspaceAccess: Literal["none"] | None = None
    docker: SandboxDockerConfig | None = None


class AgentRuntimeConfig(StrictModel):
    id: str | None = None
    heartbeat: HeartbeatConfig | None = None
    sandbox: SandboxConfig | None = None


class AgentSummary(StrictModel):
    id: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    agentDir: str = Field(min_length=1)
    bindings: int = Field(ge=0)
    isDefault: bool

    @field_validator("workspace")
    @classmethod
    def absolute_lexical_workspace(cls, workspace: str) -> str:
        separators_normalized = (
            workspace.replace(os.altsep, os.sep) if os.altsep is not None else workspace
        )
        has_dot_segment = any(
            segment in {".", ".."} for segment in separators_normalized.split(os.sep)
        )
        if not Path(workspace).is_absolute() or has_dot_segment:
            raise PydanticCustomError(
                "inventory_workspace",
                "inventory workspace must be a canonical absolute lexical path",
            )
        return workspace


class AgentInventory(RootModel[list[AgentSummary]]):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True)


class AgentCreated(StrictModel):
    agentId: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    agentDir: str = Field(min_length=1)
    bindings: AgentBindings


class AgentBindings(StrictModel):
    added: list[str]
    updated: list[str]
    skipped: list[str]
    conflicts: list[str]


class CronAtSchedule(StrictModel):
    kind: Literal["at"]
    at: str = Field(min_length=1)


class CronEverySchedule(StrictModel):
    kind: Literal["every"]
    everyMs: int = Field(gt=0)


class CronExpressionSchedule(StrictModel):
    kind: Literal["cron"]
    expr: str = Field(min_length=1)


class CronOnExitSchedule(StrictModel):
    kind: Literal["on-exit"]
    command: str = Field(min_length=1)


class CronStreamSchedule(StrictModel):
    kind: Literal["stream"]
    command: list[str] = Field(min_length=1)


type CronSchedule = (
    CronAtSchedule
    | CronEverySchedule
    | CronExpressionSchedule
    | CronOnExitSchedule
    | CronStreamSchedule
)


class CronSystemEventPayload(StrictModel):
    kind: Literal["systemEvent"]
    text: str = Field(min_length=1)


class CronAgentTurnPayload(StrictModel):
    kind: Literal["agentTurn"]
    message: str = Field(min_length=1)


class CronCommandPayload(StrictModel):
    kind: Literal["command"]
    argv: list[str] = Field(min_length=1)


class CronScriptPayload(StrictModel):
    kind: Literal["script"]
    script: str = Field(min_length=1)


class CronHeartbeatPayload(StrictModel):
    kind: Literal["heartbeat"]


type CronPayload = (
    CronSystemEventPayload
    | CronAgentTurnPayload
    | CronCommandPayload
    | CronScriptPayload
    | CronHeartbeatPayload
)


class CronJobResult(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    enabled: bool
    createdAtMs: int = Field(ge=0)
    updatedAtMs: int = Field(ge=0)
    schedule: CronSchedule
    sessionTarget: str = Field(pattern=r"^(main|isolated|current|session:.+)$")
    wakeMode: Literal["now", "next-heartbeat"]
    payload: CronPayload
    state: dict[str, JsonValue]
