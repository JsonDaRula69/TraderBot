from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, Protocol, Self, override

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.generic import create_category_profile
from traderbot.profiles.injection import (
    WorkspaceInjectionError,
    WorkspaceTemplate,
    validate_workspace_path,
)
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.sysadmin import create_sysadmin_profile


@dataclass(frozen=True, slots=True)
class WizardConfigError(ValueError):
    """Reject unsafe or incomplete wizard input before external mutation."""

    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class StepStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProvisionStatus(StrEnum):
    CREATED = "created"
    EXISTING = "existing"
    FAILED = "failed"


class TokenProvisionResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    agent_id: str
    status: ProvisionStatus
    message: str

    @classmethod
    def created(cls, agent_id: str) -> Self:
        return cls(agent_id=agent_id, status=ProvisionStatus.CREATED, message="identity created")

    @classmethod
    def existing(cls, agent_id: str) -> Self:
        return cls(agent_id=agent_id, status=ProvisionStatus.EXISTING, message="identity reused")

    @classmethod
    def failed(cls, agent_id: str, message: str) -> Self:
        return cls(agent_id=agent_id, status=ProvisionStatus.FAILED, message=message)


class WizardRequest(BaseModel):
    """Validated, mutation-ready input for wizard steps 1 through 3."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    categories: tuple[MarketCategory, ...]
    mode: Literal["backtest"]
    sysadmin_workspace: Path
    category_workspaces: dict[MarketCategory, Path]

    @field_validator("categories")
    @classmethod
    def canonical_categories(
        cls,
        categories: tuple[MarketCategory, ...],
    ) -> tuple[MarketCategory, ...]:
        if not categories or len(set(categories)) != len(categories):
            raise WizardConfigError("select one or more distinct market categories")
        selected = set(categories)
        return tuple(category for category in MarketCategory if category in selected)

    @field_validator("sysadmin_workspace")
    @classmethod
    def absolute_sysadmin_workspace(cls, workspace: Path) -> Path:
        if not workspace.is_absolute():
            raise WizardConfigError("sysadmin workspace must be an absolute path")
        return validate_workspace_path(workspace)

    @model_validator(mode="after")
    def selected_workspaces_are_explicit(self) -> Self:
        selected = set(self.categories)
        if set(self.category_workspaces) != selected:
            raise WizardConfigError("category_workspaces must exactly match selected categories")
        if any(not path.is_absolute() for path in self.category_workspaces.values()):
            raise WizardConfigError("category workspaces must be absolute paths")
        for path in self.category_workspaces.values():
            _ = validate_workspace_path(path)
        return self


class AgentDeployResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    agent_id: str
    status: StepStatus
    message: str


class WizardStepResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    step: Literal[1, 2, 3]
    name: str
    status: StepStatus
    message: str
    agents: tuple[AgentDeployResult, ...] = ()


class DeployResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    success: bool
    categories: tuple[MarketCategory, ...]
    steps: tuple[WizardStepResult, ...]
    completed_steps: tuple[Literal[1, 2, 3], ...]
    deployment_complete: Literal[False] = False
    remaining_steps: tuple[Literal[4, 5, 6, 7, 8], ...] = (4, 5, 6, 7, 8)


class OpenClawPort(Protocol):
    def detect(self) -> str | None: ...
    def install(self) -> bool: ...
    def setup(self) -> bool: ...
    def gateway_status(self) -> bool: ...
    def create_agent(self, agent_id: str, workspace: Path) -> bool: ...
    def configure_secret_ref(self, agent_id: str, secret_id: str) -> bool: ...
    def ensure_bootstrap_cron(self) -> bool: ...


class TokenProvisioner(Protocol):
    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult: ...


class WorkspaceInjector(Protocol):
    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str: ...


@dataclass(frozen=True, slots=True)
class WizardPorts:
    openclaw: OpenClawPort
    tokens: TokenProvisioner
    injector: WorkspaceInjector


class DeployWizard:
    """Run deploy steps in order without rolling back user-owned state."""

    def __init__(self, ports: WizardPorts) -> None:
        self._ports: WizardPorts = ports

    def run(self, request: WizardRequest) -> DeployResult:
        steps: list[WizardStepResult] = []
        first = self._step_openclaw()
        steps.append(first)
        if first.status is StepStatus.FAILED:
            steps.append(self._step(2, "SysAdmin setup", StepStatus.SKIPPED, "blocked"))
            steps.append(self._step(3, "Category selection", StepStatus.SKIPPED, "blocked"))
            return self._result(request, steps)

        second = self._step_sysadmin(request.sysadmin_workspace)
        steps.append(second)
        if second.status is StepStatus.FAILED:
            steps.append(self._step(3, "Category selection", StepStatus.SKIPPED, "blocked"))
            return self._result(request, steps)

        steps.append(self._step_categories(request))
        return self._result(request, steps)

    def _step_openclaw(self) -> WizardStepResult:
        if self._ports.openclaw.detect() is None:
            if not self._ports.openclaw.install() or self._ports.openclaw.detect() is None:
                return self._step(
                    1,
                    "OpenClaw config",
                    StepStatus.FAILED,
                    "OpenClaw install failed",
                )
        if not self._ports.openclaw.setup():
            return self._step(1, "OpenClaw config", StepStatus.FAILED, "baseline setup failed")
        if not self._ports.openclaw.gateway_status():
            return self._step(1, "OpenClaw config", StepStatus.FAILED, "gateway RPC unavailable")
        return self._step(1, "OpenClaw config", StepStatus.COMPLETED, "baseline verified")

    def _step_sysadmin(self, workspace: Path) -> WizardStepResult:
        try:
            _ = self._ports.injector.inject(workspace, WorkspaceTemplate.SYSADMIN)
        except (OSError, WorkspaceInjectionError) as exc:
            return self._step(2, "SysAdmin setup", StepStatus.FAILED, str(exc))
        identity = self._ports.tokens.ensure(create_sysadmin_profile(), "main")
        if identity.status is ProvisionStatus.FAILED:
            return self._step(2, "SysAdmin setup", StepStatus.FAILED, identity.message)
        if not self._ports.openclaw.configure_secret_ref("main", "main_token"):
            return self._step(2, "SysAdmin setup", StepStatus.FAILED, "main SecretRef write failed")
        if not self._ports.openclaw.ensure_bootstrap_cron():
            return self._step(
                2,
                "SysAdmin setup",
                StepStatus.FAILED,
                "bootstrap cron contract conflict or verification failed",
            )
        return self._step(2, "SysAdmin setup", StepStatus.COMPLETED, "main identity ready")

    def _step_categories(self, request: WizardRequest) -> WizardStepResult:
        agents = tuple(self._deploy_category(category, request) for category in request.categories)
        complete = all(agent.status is StepStatus.COMPLETED for agent in agents)
        return WizardStepResult(
            step=3,
            name="Category selection",
            status=StepStatus.COMPLETED if complete else StepStatus.FAILED,
            message="selected agents ready" if complete else "one or more selected agents failed",
            agents=agents,
        )

    def _deploy_category(
        self,
        category: MarketCategory,
        request: WizardRequest,
    ) -> AgentDeployResult:
        agent_id = category.value
        workspace = request.category_workspaces[category]
        if not self._ports.openclaw.create_agent(agent_id, workspace):
            return AgentDeployResult(
                agent_id=agent_id,
                status=StepStatus.FAILED,
                message="agent create failed",
            )
        try:
            _ = self._ports.injector.inject(workspace, WorkspaceTemplate(category.value))
        except (OSError, WorkspaceInjectionError) as exc:
            return AgentDeployResult(agent_id=agent_id, status=StepStatus.FAILED, message=str(exc))
        profile = create_category_profile(agent_id, request.mode, (category,))
        identity = self._ports.tokens.ensure(profile, agent_id)
        if identity.status is ProvisionStatus.FAILED:
            return AgentDeployResult(
                agent_id=agent_id,
                status=StepStatus.FAILED,
                message=identity.message,
            )
        if not self._ports.openclaw.configure_secret_ref(agent_id, f"{agent_id}_token"):
            return AgentDeployResult(
                agent_id=agent_id,
                status=StepStatus.FAILED,
                message="SecretRef write failed",
            )
        return AgentDeployResult(
            agent_id=agent_id,
            status=StepStatus.COMPLETED,
            message="identity ready",
        )

    @staticmethod
    def _step(
        step: Literal[1, 2, 3],
        name: str,
        status: StepStatus,
        message: str,
    ) -> WizardStepResult:
        return WizardStepResult(step=step, name=name, status=status, message=message)

    @staticmethod
    def _result(request: WizardRequest, steps: list[WizardStepResult]) -> DeployResult:
        return DeployResult(
            success=all(step.status is StepStatus.COMPLETED for step in steps),
            categories=request.categories,
            steps=tuple(steps),
            completed_steps=tuple(
                step.step for step in steps if step.status is StepStatus.COMPLETED
            ),
        )
