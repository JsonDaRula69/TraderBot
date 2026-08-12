from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.order_models import MarketCategory


class FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class BootstrapCronState(StrEnum):
    EXACT = "exact"
    MISSING = "missing"
    UNKNOWN_ABSENT = "unknown_absent"
    COMPLETED_RETAINED = "completed_retained"
    COMPLETED_ABSENT = "completed_absent"
    CONFLICT = "conflict"
    FAILED = "failed"


class TokenMetadataState(StrEnum):
    EXACT = "exact"
    MISSING = "missing"
    CONFLICT = "conflict"
    FAILED = "failed"


class ReconcileAction(StrEnum):
    PRESERVE = "preserve"
    CREATE = "create"
    SET = "set"


class ConfigLayout(StrEnum):
    ENTRIES = "entries"
    LIST = "list"


class SecretRefConfig(FrozenModel):
    source: Literal["exec"] = "exec"
    provider: Literal["infisical"] = "infisical"
    id: str = Field(min_length=1)


class AgentConfigState(FrozenModel):
    agent_id: str = Field(min_length=1)
    path_prefix: str = Field(min_length=1)
    heartbeat_every: str | None = None
    sandbox_mode: str | None = None


class SecretRefState(FrozenModel):
    agent_id: str = Field(min_length=1)
    ref: SecretRefConfig | None = None


class OpenClawConfigSnapshot(FrozenModel):
    agents: tuple[AgentConfigState, ...]
    secret_refs: tuple[SecretRefState, ...]

    def agent(self, agent_id: str) -> AgentConfigState | None:
        return next((item for item in self.agents if item.agent_id == agent_id), None)

    def secret_ref(self, agent_id: str) -> SecretRefConfig | None:
        state = next((item for item in self.secret_refs if item.agent_id == agent_id), None)
        return None if state is None else state.ref


class DeployApprovals(FrozenModel):
    install_openclaw: bool = False
    setup_openclaw: bool = False
    create_agents: bool = False
    heartbeat_change: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedAgent:
    agent_id: str
    category: MarketCategory | None
    workspace: Path
    existed: bool


@dataclass(frozen=True, slots=True)
class AgentReadiness:
    agent_id: str
    token: TokenMetadataState
    injection_ready: bool


@dataclass(frozen=True, slots=True)
class PreflightInputs:
    request: WizardRequestState
    agents: tuple[ResolvedAgent, ...]
    config: OpenClawConfigSnapshot
    bootstrap_cron: BootstrapCronState
    readiness: tuple[AgentReadiness, ...]


@dataclass(frozen=True, slots=True)
class PlannedAgent:
    agent_id: str
    category: MarketCategory | None
    workspace: Path
    existed: bool
    config: AgentConfigState
    secret_ref_action: ReconcileAction
    heartbeat_action: ReconcileAction
    sandbox_action: ReconcileAction


@dataclass(frozen=True, slots=True)
class DeploymentPreflight:
    agents: tuple[PlannedAgent, ...]
    bootstrap_cron: BootstrapCronState


class PreflightErrorCode(StrEnum):
    OPENCLAW_ABSENT = "openclaw_absent"
    INVENTORY_FAILED = "inventory_failed"
    MAIN_MISSING = "main_missing"
    AGENT_DUPLICATE = "agent_duplicate"
    WORKSPACE_ASSERTION = "workspace_assertion"
    WORKSPACE_OWNERSHIP = "workspace_ownership"
    NEW_AGENT_APPROVAL = "new_agent_approval"
    CONFIG_FAILED = "config_failed"
    SECRET_REF_CONFLICT = "secret_ref_conflict"
    HEARTBEAT_APPROVAL = "heartbeat_approval"
    TOKEN_CONFLICT = "token_conflict"
    INJECTION_FAILED = "injection_failed"
    CRON_CONFLICT = "cron_conflict"


@dataclass(frozen=True, slots=True)
class DeploymentPreflightError(Exception):
    code: PreflightErrorCode
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code.value}: {self.detail}"


class WizardRequestState(FrozenModel):
    categories: tuple[MarketCategory, ...]
    sysadmin_workspace: Path | None
    category_workspaces: dict[MarketCategory, Path]
    approvals: DeployApprovals
    heartbeat_every: Literal["preserve", "0m"]
