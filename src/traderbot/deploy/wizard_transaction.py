from __future__ import annotations

from typing import final

from traderbot.deploy.wizard_contracts import (
    AgentDeployResult,
    ProvisionStatus,
    StepStatus,
    WizardPorts,
    WizardRequest,
)
from traderbot.deploy.wizard_preflight import resolve_agent_targets
from traderbot.deploy.wizard_state import (
    DeploymentPreflight,
    DeploymentPreflightError,
    PlannedAgent,
    ReconcileAction,
    ResolvedAgent,
    SecretRefConfig,
    TokenMetadataState,
)
from traderbot.profiles.generic import create_category_profile
from traderbot.profiles.injection import WorkspaceInjectionError, WorkspaceTemplate
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.sysadmin import create_sysadmin_profile


def profile_for(agent: PlannedAgent | ResolvedAgent) -> TradingProfile:
    category = agent.category
    if category is None:
        return create_sysadmin_profile()
    return create_category_profile(agent.agent_id, "backtest", (category,))


def template_for(agent: PlannedAgent | ResolvedAgent) -> WorkspaceTemplate:
    return (
        WorkspaceTemplate.SYSADMIN
        if agent.category is None
        else WorkspaceTemplate(agent.category.value)
    )


@final
class DeploymentTransaction:
    def __init__(
        self,
        ports: WizardPorts,
        request: WizardRequest,
        preflight: DeploymentPreflight,
    ) -> None:
        self._ports = ports
        self._request = request
        self._preflight = preflight
        self._agent_ids = tuple(agent.agent_id for agent in preflight.agents)

    def apply_main(self) -> AgentDeployResult:
        return self._apply(self._preflight.agents[0])

    def apply_categories(self) -> tuple[AgentDeployResult, ...]:
        results: list[AgentDeployResult] = []
        for agent in self._preflight.agents[1:]:
            result = self._apply(agent)
            results.append(result)
            if result.status is StepStatus.FAILED:
                break
        return tuple(results)

    def _failed(self, agent_id: str, message: str) -> AgentDeployResult:
        return AgentDeployResult(agent_id=agent_id, status=StepStatus.FAILED, message=message)

    def _apply(self, agent: PlannedAgent) -> AgentDeployResult:
        if not agent.existed:
            _ = self._ports.openclaw.create_agent(agent.agent_id, agent.workspace)
            inventory = self._ports.openclaw.inventory_agents()
            if inventory is None:
                return self._failed(agent.agent_id, "post-create inventory failed")
            try:
                adopted = resolve_agent_targets(self._request, inventory)
            except DeploymentPreflightError as exc:
                return self._failed(agent.agent_id, str(exc))
            match = next((item for item in adopted if item.agent_id == agent.agent_id), None)
            if match is None or not match.existed:
                return self._failed(agent.agent_id, "agent absent after create")
        snapshot = self._ports.openclaw.inspect_config(self._agent_ids)
        config = None if snapshot is None else snapshot.agent(agent.agent_id)
        if config is None:
            return self._failed(agent.agent_id, "agent config unreadable")
        try:
            _ = self._ports.injector.inject(agent.workspace, template_for(agent))
        except (OSError, WorkspaceInjectionError) as exc:
            return self._failed(agent.agent_id, str(exc))
        identity = self._ports.tokens.ensure(profile_for(agent), agent.agent_id)
        if identity.status is ProvisionStatus.FAILED:
            return self._failed(agent.agent_id, identity.message)
        desired_ref = SecretRefConfig(id=f"{agent.agent_id}_token")
        if (
            agent.secret_ref_action is ReconcileAction.SET
            and not self._ports.openclaw.set_secret_ref(agent.agent_id, desired_ref)
        ):
            return self._failed(agent.agent_id, "SecretRef write failed")
        if agent.heartbeat_action is ReconcileAction.SET and not self._ports.openclaw.set_heartbeat(
            config,
            "0m",
        ):
            return self._failed(agent.agent_id, "heartbeat write failed")
        if agent.sandbox_action is ReconcileAction.SET and not self._ports.openclaw.set_sandbox(
            config,
            "all",
        ):
            return self._failed(agent.agent_id, "sandbox write failed")
        return AgentDeployResult(
            agent_id=agent.agent_id,
            status=StepStatus.COMPLETED,
            message="identity ready",
        )

    def verify(self) -> str | None:
        inventory = self._ports.openclaw.inventory_agents()
        if inventory is None:
            return "post-read agent inventory failed"
        try:
            resolved = resolve_agent_targets(self._request, inventory)
        except DeploymentPreflightError as exc:
            return str(exc)
        if any(not agent.existed for agent in resolved):
            return "one or more selected agents remain absent"
        config = self._ports.openclaw.inspect_config(self._agent_ids)
        if config is None:
            return "post-read config failed"
        for agent in self._preflight.agents:
            state = config.agent(agent.agent_id)
            if state is None or config.secret_ref(agent.agent_id) != SecretRefConfig(
                id=f"{agent.agent_id}_token"
            ):
                return f"agent {agent.agent_id} config postcondition failed"
            expected_heartbeat = (
                "0m"
                if self._request.heartbeat_every == "0m"
                else agent.config.heartbeat_every
            )
            if state.heartbeat_every != expected_heartbeat:
                return f"agent {agent.agent_id} heartbeat postcondition failed"
            if not agent.existed and state.sandbox_mode != "all":
                return f"agent {agent.agent_id} sandbox postcondition failed"
            if (
                self._ports.tokens.inspect(profile_for(agent), agent.agent_id)
                is not TokenMetadataState.EXACT
            ):
                return f"agent {agent.agent_id} identity postcondition failed"
        return None
