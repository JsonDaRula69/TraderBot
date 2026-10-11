"""Run OpenClaw-specific deployment verification checks."""

from __future__ import annotations

from typing import final

from traderbot.deploy import openclaw
from traderbot.deploy.bootstrap_cron import classify_bootstrap_crons
from traderbot.deploy.deploy_state import DeployStateError, load_deploy_state
from traderbot.deploy.openclaw_config import inspect_config
from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.verify_models import ProbeResult, VerificationRequest
from traderbot.deploy.wizard_preflight import resolve_agent_targets
from traderbot.deploy.wizard_state import (
    BootstrapCronState,
    DeployApprovals,
    DeploymentPreflightError,
    WizardRequestState,
)


def _canonical_sandbox(agent_id: str) -> str:
    """Sandbox mode the deploy writes for agents it creates ("off" for main)."""
    return "off" if agent_id == "main" else "all"


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
        """Require deploy-owned contracts; report preserved sandbox as advisory."""
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
        self.inventory = inventory
        preserved: list[str] = []
        for target in targets:
            agent_id = target.agent_id
            config = snapshot.agent(agent_id)
            expected_ref = f"{agent_id}_token"
            secret_ref = snapshot.secret_ref(agent_id)
            if config is None:
                return ProbeResult.failed("agent_config_mismatch", "Selected config differs")
            if secret_ref is None or secret_ref.id != expected_ref:
                return ProbeResult.failed("secret_ref_mismatch", "Selected SecretRef differs")
            if agent_id in self.request.created_agents:
                if config.sandbox_mode != _canonical_sandbox(agent_id):
                    return ProbeResult.failed(
                        "agent_config_mismatch", "Created agent sandbox differs"
                    )
            elif config.sandbox_mode != _canonical_sandbox(agent_id):
                preserved.append(f"{agent_id}={config.sandbox_mode or 'unset'}")
        if preserved:
            return ProbeResult.degraded(
                "sandbox_posture_reported",
                f"Preserved sandbox differs: {','.join(preserved)}",
            )
        return ProbeResult.passed("selected_agents_exact")

    def cron(self) -> ProbeResult:
        """Classify the one-shot lifecycle; absence after firing stays honest."""
        jobs = openclaw.inspect_crons()
        if jobs is None:
            return ProbeResult.failed("cron_inventory_unreadable", "Cron inventory is unreadable")
        state = classify_bootstrap_crons(jobs)
        if state is BootstrapCronState.EXACT:
            return ProbeResult.passed("bootstrap_cron_exact")
        if state is BootstrapCronState.COMPLETED_RETAINED:
            return ProbeResult.passed(
                "bootstrap_cron_completed_retained",
                "Managed bootstrap one-shot completed and was retained",
            )
        if state is BootstrapCronState.MISSING:
            if self._bootstrap_registered():
                return ProbeResult.degraded(
                    "bootstrap_cron_completed_absent",
                    "Bootstrap one-shot fired per deploy state and is absent",
                )
            return ProbeResult.failed("bootstrap_cron_mismatch", "Managed cron contract differs")
        return ProbeResult.failed("bootstrap_cron_conflict", "Managed cron contract differs")

    def heartbeat(self) -> ProbeResult:
        """Require dormancy only when the deploy approved it; else report it."""
        inventory = self.inventory or openclaw.inspect_agents()
        if inventory is None:
            return ProbeResult.failed("config_unreadable", "Heartbeat config is unreadable")
        ids = ("main", *(category.value for category in self.request.categories))
        snapshot = inspect_config(ids, inventory)
        if snapshot is None:
            return ProbeResult.failed("config_unreadable", "Heartbeat config is unreadable")
        dormant_required = self.request.heartbeat_policy == "require_0m"
        divergent: list[str] = []
        for agent_id in ids:
            agent = snapshot.agent(agent_id)
            cadence = None if agent is None else agent.heartbeat_every
            if cadence == "0m":
                continue
            if dormant_required:
                return ProbeResult.failed("heartbeat_mismatch", "Selected heartbeat is not dormant")
            divergent.append(f"{agent_id}={cadence or 'unset'}")
        if divergent:
            return ProbeResult.degraded(
                "heartbeat_posture_reported",
                f"Heartbeat posture differs from dormant: {','.join(divergent)}",
            )
        return ProbeResult.passed("heartbeat_dormant")

    def _bootstrap_registered(self) -> bool:
        try:
            state = load_deploy_state(self.request.data_root)
        except DeployStateError:
            return False
        return state is not None and state.bootstrap_registered


__all__ = ["OpenClawVerifier"]
