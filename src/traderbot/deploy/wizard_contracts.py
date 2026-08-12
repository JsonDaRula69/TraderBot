from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.validation import (
    SecretReconciliationApprovals,
    validate_infisical_origin,
    validate_secret_references,
)
from traderbot.deploy.verify_models import VerificationResult
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
from traderbot.kalshi.order_models import MarketCategory
from traderbot.paths import get_data_dir
from traderbot.profiles.injection import WorkspaceTemplate, validate_workspace_path
from traderbot.profiles.models import TradingProfile


class StepStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
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
    step: int = Field(ge=1, le=8)
    name: str
    status: StepStatus
    action: str = Field(default="step_recorded", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str
    agents: tuple[AgentDeployResult, ...] = ()
    backfill: BackfillResult | None = None
    verification: VerificationResult | None = None


class DeployState(FrozenModel):
    schema_version: Literal[1] = 1
    step6_fingerprint: str
    step7_fingerprint: str
    step8_fingerprint: str
    steps: tuple[WizardStepResult, ...]
    bootstrap_registered: bool = False

    def completed(self, step: int, fingerprint: str) -> WizardStepResult | None:
        expected = {
            6: self.step6_fingerprint,
            7: self.step7_fingerprint,
            8: self.step8_fingerprint,
        }.get(step)
        if expected != fingerprint:
            return None
        return next(
            (
                result
                for result in self.steps
                if result.step == step and result.status is StepStatus.COMPLETED
            ),
            None,
        )


class DeployResult(FrozenModel):
    success: bool
    input_valid: bool = True
    categories: tuple[MarketCategory, ...]
    steps: tuple[WizardStepResult, ...]
    completed_steps: tuple[int, ...]
    deployment_complete: bool = False
    remaining_steps: tuple[int, ...] = ()
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
    infisical_url: str = "http://localhost:8080"
    kalshi_api_key_env: str | None = None
    kalshi_private_key_pem_env: str | None = None
    secret_approvals: SecretReconciliationApprovals = Field(
        default_factory=SecretReconciliationApprovals
    )
    months_backfill: int = Field(default=6, ge=1, le=60)
    collector_db: Path | None = None
    data_root: Path = Field(default_factory=get_data_dir)
    daemon_mcp_url: str = "http://127.0.0.1:8765/mcp"
    kalshi_environment: Literal["production", "demo"] = "production"

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
        _ = validate_infisical_origin(self.infisical_url)
        _ = validate_secret_references(
            self.kalshi_api_key_env,
            self.kalshi_private_key_pem_env,
        )
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
    def ensure_bootstrap_cron(self, state: BootstrapCronState) -> bool: ...


class TokenProvisioner(Protocol):
    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState: ...
    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult: ...


class WorkspaceInjector(Protocol):
    def preflight(self, workspace: Path, template: WorkspaceTemplate) -> str | None: ...
    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str: ...


class Phase45Result(FrozenModel):
    status: StepStatus
    message: str

    @classmethod
    def completed(cls, message: str) -> Phase45Result:
        return cls(status=StepStatus.COMPLETED, message=message)

    @classmethod
    def failed(cls, message: str) -> Phase45Result:
        return cls(status=StepStatus.FAILED, message=message)


class Phase45Port(Protocol):
    def provision_secrets(self, request: WizardRequest) -> Phase45Result: ...

    def provision_databases(self, request: WizardRequest) -> Phase45Result: ...


class LatePreflightResult(FrozenModel):
    valid: bool
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class Phase678Port(Protocol):
    def preflight(self, request: WizardRequest) -> LatePreflightResult: ...
    def run_backfill(self, request: WizardRequest) -> BackfillResult: ...
    def run_verification(self, request: WizardRequest) -> VerificationResult: ...
    def load_state(self, request: WizardRequest) -> DeployState | None: ...
    def save_state(self, request: WizardRequest, state: DeployState) -> None: ...


@dataclass(frozen=True, slots=True)
class WizardPorts:
    openclaw: OpenClawPort
    tokens: TokenProvisioner
    injector: WorkspaceInjector
    phase45: Phase45Port | None = None
    phase678: Phase678Port | None = None
