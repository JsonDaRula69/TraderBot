"""Resolve global OpenClaw inventory and workspace ownership preflight."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Never

from traderbot.deploy.openclaw_models import AgentInventory, AgentSummary
from traderbot.deploy.wizard_state import (
    DEV_LIAISON_AGENT_ID,
    AgentConfigState,
    AgentReadiness,
    BootstrapCronState,
    DeploymentPreflight,
    DeploymentPreflightError,
    PlannedAgent,
    PreflightErrorCode,
    PreflightInputs,
    ReconcileAction,
    ResolvedAgent,
    SandboxLadderMode,
    SandboxTarget,
    SecretRefConfig,
    TokenMetadataState,
    WizardRequestState,
)
from traderbot.profiles.injection import validate_workspace_path


def _fail(code: PreflightErrorCode, detail: str) -> Never:
    raise DeploymentPreflightError(code, detail)


def _normalized(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        _ = validate_workspace_path(path)
    checked = validate_workspace_path(Path(os.path.realpath(os.path.expanduser(path))))
    return Path(os.path.normcase(os.path.abspath(os.path.expanduser(checked))))


def _same_workspace(first: Path, second: Path) -> bool:
    normalized_first = _normalized(first)
    normalized_second = _normalized(second)
    if normalized_first == normalized_second:
        return True
    if os.path.realpath(normalized_first) == os.path.realpath(normalized_second):
        return True
    for left, right in ((normalized_first, normalized_second), (first, second)):
        if left.exists() and right.exists():
            try:
                if os.path.samefile(left, right):
                    return True
            except OSError as exc:
                _fail(PreflightErrorCode.WORKSPACE_OWNERSHIP, str(exc))
    return False


def _overlaps(first: Path, second: Path) -> bool:
    left = _normalized(first)
    right = _normalized(second)
    return _same_workspace(first, second) or left in right.parents or right in left.parents


def _is_allowed_main_container(first: tuple[str, Path], second: tuple[str, Path]) -> bool:
    if _same_workspace(first[1], second[1]):
        return False
    left = _normalized(first[1])
    right = _normalized(second[1])
    return (first[0] == "main" and left in right.parents) or (
        second[0] == "main" and right in left.parents
    )


def _inventory_by_id(inventory: AgentInventory) -> dict[str, AgentSummary]:
    indexed: dict[str, AgentSummary] = {}
    for agent in inventory.root:
        if agent.id in indexed:
            _fail(PreflightErrorCode.AGENT_DUPLICATE, f"duplicate agent id {agent.id}")
        indexed[agent.id] = agent
    return indexed


def _assert_global_ownership(inventory: AgentInventory) -> None:
    agents = inventory.root
    for index, agent in enumerate(agents):
        for other in agents[index + 1 :]:
            if _overlaps(Path(agent.workspace), Path(other.workspace)) and not (
                _is_allowed_main_container(
                    (agent.id, Path(agent.workspace)), (other.id, Path(other.workspace))
                )
            ):
                _fail(
                    PreflightErrorCode.WORKSPACE_OWNERSHIP,
                    f"agents {agent.id} and {other.id} have overlapping workspaces",
                )


def _assert_requested_workspace(agent_id: str, actual: Path, asserted: Path | None) -> None:
    if asserted is not None and not _same_workspace(actual, asserted):
        _fail(
            PreflightErrorCode.WORKSPACE_ASSERTION,
            f"agent {agent_id} inventory workspace differs from explicit assertion",
        )


def resolve_agent_targets(
    request: WizardRequestState,
    inventory: AgentInventory,
) -> tuple[ResolvedAgent, ...]:
    _assert_global_ownership(inventory)
    indexed = _inventory_by_id(inventory)
    main = indexed.get("main")
    if main is None:
        _fail(PreflightErrorCode.MAIN_MISSING, "OpenClaw inventory has no main agent")
    main_workspace = Path(main.workspace)
    _assert_requested_workspace("main", main_workspace, request.sysadmin_workspace)
    targets = [ResolvedAgent("main", None, main_workspace, True)]
    for category in request.categories:
        agent = indexed.get(category.value)
        asserted = request.category_workspaces.get(category)
        if agent is not None:
            workspace = Path(agent.workspace)
            _assert_requested_workspace(category.value, workspace, asserted)
            targets.append(ResolvedAgent(category.value, category, workspace, True))
            continue
        if not request.approvals.create_agents or asserted is None:
            _fail(
                PreflightErrorCode.NEW_AGENT_APPROVAL,
                f"missing agent {category.value} needs an approved absolute workspace",
            )
        targets.append(ResolvedAgent(category.value, category, asserted, False))
    # GAP-13/#356: dev-liaison is ADOPTED, never created — it enters the
    # resolved surface only when already present in the inventory.
    dev_liaison = indexed.get(DEV_LIAISON_AGENT_ID)
    if dev_liaison is not None:
        targets.append(ResolvedAgent(DEV_LIAISON_AGENT_ID, None, Path(dev_liaison.workspace), True))
    for target in targets:
        for owner in inventory.root:
            if (
                owner.id != target.agent_id
                and _overlaps(target.workspace, Path(owner.workspace))
                and not _is_allowed_main_container(
                    (target.agent_id, target.workspace), (owner.id, Path(owner.workspace))
                )
            ):
                _fail(
                    PreflightErrorCode.WORKSPACE_OWNERSHIP,
                    f"agent {target.agent_id} overlaps configured owner {owner.id}",
                )
    for index, target in enumerate(targets):
        for other in targets[index + 1 :]:
            if (
                target.agent_id != other.agent_id
                and _overlaps(target.workspace, other.workspace)
                and not _is_allowed_main_container(
                    (target.agent_id, target.workspace), (other.agent_id, other.workspace)
                )
            ):
                _fail(
                    PreflightErrorCode.WORKSPACE_OWNERSHIP,
                    f"selected agents {target.agent_id} and {other.agent_id} overlap",
                )
    return tuple(targets)


def resolve_sandbox_targets(
    plan: DeploymentPreflight,
    *,
    mode: SandboxLadderMode,
) -> tuple[SandboxTarget, ...]:
    """Todo-8 step-7 apply surface: every selected created-or-adopted
    category agent (ladder data mode) plus the ADOPTED dev-liaison (GAP-13:
    its profile mode is ``paper`` -> data dir ``paper-dev-liaison``, evidence
    #356). ``main``/``sysadmin`` keep sandbox mode ``off`` and are never
    written (D2 note 2); absent dev-liaison inventories yield no target
    (dev-liaison is adopted-only, never created by the deploy)."""
    targets: list[SandboxTarget] = []
    for agent in plan.agents:
        if agent.agent_id == DEV_LIAISON_AGENT_ID:
            targets.append(SandboxTarget(agent.agent_id, agent.workspace, "paper"))
        elif agent.category is not None:
            targets.append(SandboxTarget(agent.agent_id, agent.workspace, mode))
    return tuple(targets)


def _token_action(readiness: AgentReadiness) -> ReconcileAction:
    if readiness.token in {TokenMetadataState.CONFLICT, TokenMetadataState.FAILED}:
        _fail(
            PreflightErrorCode.TOKEN_CONFLICT,
            f"agent {readiness.agent_id} identity metadata is not reconcilable",
        )
    return (
        ReconcileAction.PRESERVE
        if readiness.token is TokenMetadataState.EXACT
        else ReconcileAction.CREATE
    )


def finalize_preflight(inputs: PreflightInputs) -> DeploymentPreflight:
    if inputs.bootstrap_cron in {
        BootstrapCronState.UNKNOWN_ABSENT,
        BootstrapCronState.CONFLICT,
        BootstrapCronState.FAILED,
    }:
        _fail(PreflightErrorCode.CRON_CONFLICT, "bootstrap cron inventory conflicts")
    if inputs.request.heartbeat_every == "0m" and not inputs.request.approvals.heartbeat_change:
        _fail(PreflightErrorCode.HEARTBEAT_APPROVAL, "0m heartbeat change is not approved")
    plans: list[PlannedAgent] = []
    for target in inputs.agents:
        readiness = next(
            (item for item in inputs.readiness if item.agent_id == target.agent_id),
            None,
        )
        if readiness is None or not readiness.injection_ready:
            _fail(
                PreflightErrorCode.INJECTION_FAILED,
                f"agent {target.agent_id} workspace injection preflight failed",
            )
        _ = _token_action(readiness)
        config = inputs.config.agent(target.agent_id)
        if target.existed and config is None:
            _fail(
                PreflightErrorCode.CONFIG_FAILED,
                f"agent {target.agent_id} config state is unreadable",
            )
        desired_ref = SecretRefConfig(id=f"{target.agent_id}_token")
        existing_ref = inputs.config.secret_ref(target.agent_id)
        if existing_ref is not None and existing_ref != desired_ref:
            _fail(
                PreflightErrorCode.SECRET_REF_CONFLICT,
                f"agent {target.agent_id} has a conflicting SecretRef",
            )
        heartbeat_action = ReconcileAction.PRESERVE
        if inputs.request.heartbeat_every == "0m" and (
            config is None or config.heartbeat_every != "0m"
        ):
            heartbeat_action = ReconcileAction.SET
        planned_config = config or AgentConfigState(
            agent_id=target.agent_id,
            path_prefix=f"agents.entries.{target.agent_id}",
        )
        plans.append(
            PlannedAgent(
                agent_id=target.agent_id,
                category=target.category,
                workspace=target.workspace,
                existed=target.existed,
                config=planned_config,
                secret_ref_action=(
                    ReconcileAction.SET if existing_ref is None else ReconcileAction.PRESERVE
                ),
                heartbeat_action=heartbeat_action,
                sandbox_action=(
                    ReconcileAction.PRESERVE if target.existed else ReconcileAction.SET
                ),
            )
        )
    return DeploymentPreflight(tuple(plans), inputs.bootstrap_cron)
