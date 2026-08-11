from __future__ import annotations

from typing import Literal

from traderbot.deploy.wizard_contracts import (
    AgentDeployResult,
    DeployResult,
    OpenClawPort,
    Phase45Port,
    Phase45Result,
    ProvisionStatus,
    StepStatus,
    TokenProvisioner,
    TokenProvisionResult,
    WizardPorts,
    WizardRequest,
    WizardStepResult,
    WorkspaceInjector,
)
from traderbot.deploy.wizard_preflight import finalize_preflight, resolve_agent_targets
from traderbot.deploy.wizard_state import (
    AgentReadiness,
    DeploymentPreflight,
    DeploymentPreflightError,
    PreflightErrorCode,
    PreflightInputs,
)
from traderbot.deploy.wizard_transaction import (
    DeploymentTransaction,
    profile_for,
    template_for,
)

__all__ = (
    "AgentDeployResult",
    "DeployResult",
    "DeployWizard",
    "OpenClawPort",
    "Phase45Port",
    "Phase45Result",
    "ProvisionStatus",
    "StepStatus",
    "TokenProvisioner",
    "TokenProvisionResult",
    "WizardPorts",
    "WizardRequest",
    "WizardStepResult",
    "WorkspaceInjector",
)


class DeployWizard:
    """Run deploy steps in order without rolling back user-owned state."""

    def __init__(self, ports: WizardPorts) -> None:
        self._ports: WizardPorts = ports

    def run(self, request: WizardRequest) -> DeployResult:
        if self._ports.openclaw.detect() is None:
            if not request.approvals.install_openclaw:
                return self._preflight_failure(request, "OpenClaw install is not approved")
            if not self._ports.openclaw.install() or self._ports.openclaw.detect() is None:
                return self._preflight_failure(request, "OpenClaw install failed")
        try:
            plan = self._preflight(request)
        except DeploymentPreflightError as exc:
            if (
                exc.code is not PreflightErrorCode.MAIN_MISSING
                or not request.approvals.setup_openclaw
            ):
                return self._preflight_failure(request, str(exc))
            if not self._ports.openclaw.setup():
                return self._preflight_failure(request, "approved baseline setup failed")
            try:
                plan = self._preflight(request)
            except DeploymentPreflightError as restarted:
                return self._preflight_failure(request, str(restarted))
        transaction = DeploymentTransaction(self._ports, request, plan)
        main_result = transaction.apply_main()
        if main_result.status is StepStatus.FAILED:
            steps = [
                self._step(1, "OpenClaw config", StepStatus.COMPLETED, "global preflight complete"),
                self._step(2, "SysAdmin setup", StepStatus.FAILED, main_result.message),
                self._step(3, "Category selection", StepStatus.SKIPPED, "blocked"),
            ]
            return self._result(request, steps, plan)
        agent_results = list(transaction.apply_categories())
        if agent_results and agent_results[-1].status is StepStatus.FAILED:
            steps = [
                self._step(1, "OpenClaw config", StepStatus.COMPLETED, "global preflight complete"),
                self._step(2, "SysAdmin setup", StepStatus.COMPLETED, "main identity ready"),
                WizardStepResult(
                    step=3,
                    name="Category selection",
                    status=StepStatus.FAILED,
                    message="selected-agent reconciliation stopped",
                    agents=tuple(agent_results),
                ),
            ]
            return self._result(request, steps, plan)
        verification = transaction.verify()
        if verification is not None or not self._ports.openclaw.ensure_bootstrap_cron():
            message = verification or "bootstrap cron final verification failed"
            agent_results.append(
                AgentDeployResult(agent_id="main", status=StepStatus.FAILED, message=message)
            )
            status = StepStatus.FAILED
        else:
            status = StepStatus.COMPLETED
        steps = [
            self._step(1, "OpenClaw config", StepStatus.COMPLETED, "global preflight complete"),
            self._step(2, "SysAdmin setup", StepStatus.COMPLETED, "main identity ready"),
            WizardStepResult(
                step=3,
                name="Category selection",
                status=status,
                message=(
                    "selected agents ready; bootstrap reconciled last"
                    if status is StepStatus.COMPLETED
                    else "final postcondition failed"
                ),
                agents=tuple(agent_results),
            ),
        ]
        phase45 = self._ports.phase45
        if phase45 is None or status is StepStatus.FAILED:
            return self._result(request, steps, plan)
        secret_result = phase45.provision_secrets(request)
        steps.append(
            self._step(
                4,
                "Infisical and API tokens",
                secret_result.status,
                secret_result.message,
            )
        )
        if secret_result.status is StepStatus.FAILED:
            steps.append(self._step(5, "Database creation", StepStatus.SKIPPED, "blocked"))
            return self._result(request, steps, plan)
        database_result = phase45.provision_databases(request)
        steps.append(
            self._step(5, "Database creation", database_result.status, database_result.message)
        )
        return self._result(request, steps, plan)

    def _preflight(self, request: WizardRequest) -> DeploymentPreflight:
        inventory = self._ports.openclaw.inventory_agents()
        if inventory is None:
            raise DeploymentPreflightError(
                PreflightErrorCode.INVENTORY_FAILED,
                "OpenClaw agent inventory is unreadable",
            )
        agents = resolve_agent_targets(request, inventory)
        if not self._ports.openclaw.gateway_status():
            raise DeploymentPreflightError(
                PreflightErrorCode.CONFIG_FAILED,
                "OpenClaw Gateway RPC is unavailable",
            )
        agent_ids = tuple(agent.agent_id for agent in agents)
        config = self._ports.openclaw.inspect_config(agent_ids)
        if config is None:
            raise DeploymentPreflightError(
                PreflightErrorCode.CONFIG_FAILED,
                "OpenClaw config inventory is unreadable",
            )
        readiness = tuple(
            AgentReadiness(
                agent.agent_id,
                self._ports.tokens.inspect(profile_for(agent), agent.agent_id),
                self._ports.injector.preflight(
                    agent.workspace,
                    template_for(agent),
                )
                is not None,
            )
            for agent in agents
        )
        return finalize_preflight(
            PreflightInputs(
                request=request,
                agents=agents,
                config=config,
                bootstrap_cron=self._ports.openclaw.inspect_bootstrap_cron(),
                readiness=readiness,
            )
        )

    def _preflight_failure(self, request: WizardRequest, message: str) -> DeployResult:
        steps = [
            self._step(1, "OpenClaw config", StepStatus.FAILED, message),
            self._step(2, "SysAdmin setup", StepStatus.SKIPPED, "blocked"),
            self._step(3, "Category selection", StepStatus.SKIPPED, "blocked"),
        ]
        return self._result(request, steps, None)

    @staticmethod
    def _step(
        step: Literal[1, 2, 3, 4, 5],
        name: str,
        status: StepStatus,
        message: str,
    ) -> WizardStepResult:
        return WizardStepResult(step=step, name=name, status=status, message=message)

    @staticmethod
    def _result(
        request: WizardRequest,
        steps: list[WizardStepResult],
        plan: DeploymentPreflight | None,
    ) -> DeployResult:
        return DeployResult(
            success=all(step.status is StepStatus.COMPLETED for step in steps),
            categories=request.categories,
            steps=tuple(steps),
            completed_steps=tuple(
                step.step for step in steps if step.status is StepStatus.COMPLETED
            ),
            remaining_steps=(6, 7, 8) if len(steps) == 5 else (4, 5, 6, 7, 8),
            required_new_agent_paths=(
                {
                    agent.category: agent.workspace
                    for agent in plan.agents
                    if not agent.existed and agent.category is not None
                }
                if plan is not None
                else dict(request.category_workspaces)
            ),
            approvals=request.approvals,
            heartbeat_every=request.heartbeat_every,
        )
