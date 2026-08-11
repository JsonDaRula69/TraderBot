from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.wizard_state import (
    AgentConfigState,
    BootstrapCronState,
    DeployApprovals,
    FrozenModel,
    OpenClawConfigSnapshot,
    SecretRefConfig,
    TokenMetadataState,
    WizardRequestState,
)
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.injection import WorkspaceTemplate, validate_workspace_path
from traderbot.profiles.models import TradingProfile


class StepStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProvisionStatus(StrEnum):
    CREATED = "created"
    EXISTING = "existing"
    FAILED = "failed"


class TokenProvisionResult(FrozenModel):
    agent_id: str
    status: ProvisionStatus
    message: str

    @classmethod
    def created(cls, agent_id: str) -> TokenProvisionResult:
        return cls(agent_id=agent_id, status=ProvisionStatus.CREATED, message="identity created")

    @classmethod
    def existing(cls, agent_id: str) -> TokenProvisionResult:
        return cls(agent_id=agent_id, status=ProvisionStatus.EXISTING, message="identity reused")

    @classmethod
    def failed(cls, agent_id: str, message: str) -> TokenProvisionResult:
        return cls(agent_id=agent_id, status=ProvisionStatus.FAILED, message=message)


class AgentDeployResult(FrozenModel):
    agent_id: str
    status: StepStatus
    message: str


class WizardStepResult(FrozenModel):
    step: Literal[1, 2, 3]
    name: str
    status: StepStatus
    message: str
    agents: tuple[AgentDeployResult, ...] = ()


class DeployResult(FrozenModel):
    success: bool
    categories: tuple[MarketCategory, ...]
    steps: tuple[WizardStepResult, ...]
    completed_steps: tuple[Literal[1, 2, 3], ...]
    deployment_complete: Literal[False] = False
    remaining_steps: tuple[Literal[4, 5, 6, 7, 8], ...] = (4, 5, 6, 7, 8)
    required_new_agent_paths: dict[MarketCategory, Path]
    approvals: DeployApprovals
    heartbeat_every: Literal["preserve", "0m"]


class WizardRequest(WizardRequestState):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["backtest"]
    categories: tuple[MarketCategory, ...] = Field(min_length=1)
    sysadmin_workspace: Path | None = None
    category_workspaces: dict[MarketCategory, Path] = Field(default_factory=dict)
    approvals: DeployApprovals = Field(default_factory=DeployApprovals)
    heartbeat_every: Literal["preserve", "0m"] = "preserve"

    @field_validator("categories")
    @classmethod
    def unique_ordered_categories(
        cls,
        categories: tuple[MarketCategory, ...],
    ) -> tuple[MarketCategory, ...]:
        if len(set(categories)) != len(categories):
            raise PydanticCustomError(
                "duplicate_category",
                "categories must not contain duplicates",
            )
        order = {category: index for index, category in enumerate(MarketCategory)}
        return tuple(sorted(categories, key=order.__getitem__))

    @field_validator("sysadmin_workspace")
    @classmethod
    def safe_sysadmin_workspace(cls, workspace: Path | None) -> Path | None:
        if workspace is None:
            return None
        if not workspace.is_absolute():
            raise PydanticCustomError("workspace_path", "sysadmin workspace must be absolute")
        return validate_workspace_path(workspace)

    @model_validator(mode="after")
    def safe_category_workspaces(self) -> WizardRequest:
        if not set(self.category_workspaces).issubset(self.categories):
            raise PydanticCustomError(
                "workspace_mapping",
                "category workspace keys must be selected categories",
            )
        for path in self.category_workspaces.values():
            if not path.is_absolute():
                raise PydanticCustomError("workspace_path", "category workspaces must be absolute")
            _ = validate_workspace_path(path)
        if self.heartbeat_every == "0m" and not self.approvals.heartbeat_change:
            raise PydanticCustomError(
                "heartbeat_approval",
                "heartbeat_every 0m requires heartbeat change approval",
            )
        return self


class OpenClawPort(Protocol):
    def detect(self) -> str | None: ...
    def install(self) -> bool: ...
    def setup(self) -> bool: ...
    def gateway_status(self) -> bool: ...
    def inventory_agents(self) -> AgentInventory | None: ...
    def inspect_config(self, agent_ids: tuple[str, ...]) -> OpenClawConfigSnapshot | None: ...
    def inspect_bootstrap_cron(self) -> BootstrapCronState: ...
    def create_agent(self, agent_id: str, workspace: Path) -> bool: ...
    def set_secret_ref(self, agent_id: str, secret_ref: SecretRefConfig) -> bool: ...
    def set_heartbeat(self, agent: AgentConfigState, value: str) -> bool: ...
    def set_sandbox(self, agent: AgentConfigState, value: str) -> bool: ...
    def ensure_bootstrap_cron(self) -> bool: ...


class TokenProvisioner(Protocol):
    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState: ...
    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult: ...


class WorkspaceInjector(Protocol):
    def preflight(self, workspace: Path, template: WorkspaceTemplate) -> str | None: ...
    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str: ...


@dataclass(frozen=True, slots=True)
class WizardPorts:
    openclaw: OpenClawPort
    tokens: TokenProvisioner
    injector: WorkspaceInjector
