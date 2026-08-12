from __future__ import annotations

from typing import final

from traderbot.deploy import openclaw
from traderbot.deploy.bootstrap_cron import SysAdminBootstrapCron
from traderbot.deploy.openclaw_config import inspect_config
from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.verify_models import ProbeResult, VerificationRequest
from traderbot.deploy.wizard_preflight import resolve_agent_targets
from traderbot.deploy.wizard_state import (
    DeployApprovals,
    DeploymentPreflightError,
    WizardRequestState,
)


@final
class OpenClawVerifier:
    __slots__ = ("inventory", "request")

    def __init__(self, request: VerificationRequest) -> None:
        self.request = request
        self.inventory: AgentInventory | None = None

    def gateway(self) -> ProbeResult:
        return (
            ProbeResult.passed("gateway_rpc_healthy")
            if openclaw.gateway_status()
            else ProbeResult.failed("gateway_unavailable", "Gateway RPC is unavailable")
        )

    def agents(self) -> ProbeResult:
        inventory = openclaw.inspect_agents()
        if inventory is None:
            return ProbeResult.failed("inventory_unreadable", "Agent inventory is unreadable")
        state = WizardRequestState(
            categories=self.request.categories,
            sysadmin_workspace=self.request.sysadmin_workspace,
            category_workspaces=self.request.category_workspaces,
            approvals=DeployApprovals(),
            heartbeat_every="preserve",
        )
        try:
            targets = resolve_agent_targets(state, inventory)
        except (DeploymentPreflightError, OSError, ValueError):
            return ProbeResult.failed("agent_contract_mismatch", "Selected agent state conflicts")
        if any(not target.existed for target in targets):
            return ProbeResult.failed("selected_agent_missing", "A selected agent is missing")
        snapshot = inspect_config(tuple(target.agent_id for target in targets), inventory)
        if snapshot is None:
            return ProbeResult.failed("config_unreadable", "Selected agent config is unreadable")
        for target in targets:
            config = snapshot.agent(target.agent_id)
            expected_sandbox = "off" if target.agent_id == "main" else "all"
            expected_ref = f"{target.agent_id}_token"
            secret_ref = snapshot.secret_ref(target.agent_id)
            if config is None or config.sandbox_mode != expected_sandbox:
                return ProbeResult.failed("agent_config_mismatch", "Selected config differs")
            if secret_ref is None or secret_ref.id != expected_ref:
                return ProbeResult.failed("secret_ref_mismatch", "Selected SecretRef differs")
        self.inventory = inventory
        return ProbeResult.passed("selected_agents_exact")

    def cron(self) -> ProbeResult:
        jobs = openclaw.inspect_crons()
        if jobs is None:
            return ProbeResult.failed("cron_inventory_unreadable", "Cron inventory is unreadable")
        if not SysAdminBootstrapCron.is_unique_match(jobs):
            return ProbeResult.failed("bootstrap_cron_mismatch", "Managed cron contract differs")
        return ProbeResult.passed("bootstrap_cron_exact")

    def heartbeat(self) -> ProbeResult:
        inventory = self.inventory or openclaw.inspect_agents()
        if inventory is None:
            return ProbeResult.failed("config_unreadable", "Heartbeat config is unreadable")
        ids = ("main", *(category.value for category in self.request.categories))
        snapshot = inspect_config(ids, inventory)
        if snapshot is None:
            return ProbeResult.failed("config_unreadable", "Heartbeat config is unreadable")
        for agent_id in ids:
            agent = snapshot.agent(agent_id)
            if agent is None or agent.heartbeat_every != "0m":
                return ProbeResult.failed("heartbeat_mismatch", "Selected heartbeat is not dormant")
        return ProbeResult.passed("heartbeat_dormant")


__all__ = ["OpenClawVerifier"]
