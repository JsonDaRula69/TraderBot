"""Run backfill, docker-sandbox apply, and verification wizard steps.

Step 7 (Phase 5, todo-8) applies the Docker sandbox posture to every selected
created-or-adopted category agent plus the adopted dev-liaison (GAP-13). The
apply is OPT-IN for this phase: the wizard only writes sandbox config when
``TRADERBOT_PHASE5_SANDBOX=1`` is set in the environment (A-T1-LANE; any other
value or an unset variable records a typed skip with the remedy). The flow:

1. Docker availability gate (D7) — no writes when the binary/daemon is absent.
2. ``build_sandbox_image`` BEFORE any config write on every run that writes.
3. Apply plan computed via ``traderbot.sandbox.sandbox_config_for`` only (D3),
   with the image passed explicitly from
   ``sandbox_image_tag(resolve_sandbox_dockerfile())`` — never the model's
   ``default_factory``.
4. ONE operator approval (``DeployApprovals.sandbox_apply``) listing the exact
   per-agent writes (the plan is recorded in the step's sandbox_report).
5. Per agent, in order: backup the current sandbox keys recording ABSENCE
   explicitly, write the deployed-shape ``agents.list[i].sandbox.*`` leaf
   grammar via T6's strict-JSON seam, then re-read and compare byte-exact. On
   any failure or mismatch, roll back every previously-written agent in
   reverse order (D8 per-key restore: SET recorded values, UNSET keys absent
   pre-write, then UNSET leftover empty parents), then abort.
6. On success, persist the step-7 posture fingerprint (image tag + per-agent
   mount table + modes + dangerous-* set) in deploy state.

Every unexpected state is a typed failure — never a guessed recovery, never a
doctor-style fix-up, never a heuristic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Final

from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import step7_docker_fingerprint, step_fingerprint
from traderbot.deploy.openclaw_models import ConfigReadState, JsonValue
from traderbot.deploy.sandbox_build import SandboxBuildError, resolve_sandbox_dockerfile
from traderbot.deploy.verify_models import (
    CheckStatus,
    OverallStatus,
    VerificationResult,
)
from traderbot.deploy.wizard_contracts import (
    AgentDeployResult,
    DeployState,
    Phase678Port,
    StepStatus,
    WizardPorts,
    WizardRequest,
    WizardStepResult,
)
from traderbot.deploy.wizard_preflight import resolve_sandbox_targets
from traderbot.deploy.wizard_state import (
    DeploymentPreflight,
    SandboxAgentResult,
    SandboxApplyReport,
    SandboxKeyBackup,
    SandboxTarget,
    SandboxWriteRecord,
)
from traderbot.sandbox import sandbox_config_for, sandbox_image_tag

PHASE5_SANDBOX_ENV: Final = "TRADERBOT_PHASE5_SANDBOX"
_SANDBOX_STEP_NAME: Final = "Docker sandbox"
_SANDBOX_STEP: Final = 7

# Deterministic per-agent write order (auditable): posture keys first, then the
# docker object leaves in emission order (A-DCFG-KEYS pinned four in the
# middle, the D9-pinned exactly-two dangerous-* keys last).
_DOCKER_LEAF_ORDER: Final = (
    "image",
    "binds",
    "readOnlyRoot",
    "network",
    "user",
    "capDrop",
    "dangerouslyAllowExternalBindSources",
    "dangerouslyAllowReservedContainerTargets",
)


def append_blocked_late_steps(steps: list[WizardStepResult], first: int) -> None:
    names = (
        "OpenClaw config",
        "SysAdmin setup",
        "Category selection",
        "Infisical and API tokens",
        "Database creation",
        "Backfill",
        "Docker sandbox",
        "Verification",
    )
    for step in range(first, 9):
        steps.append(
            WizardStepResult(
                step=step,
                name=names[step - 1],
                status=StepStatus.SKIPPED,
                action="dependency_unavailable",
                message="blocked by an incomplete prerequisite",
            )
        )


def _backfill_step(result: BackfillResult) -> WizardStepResult:
    mapping = {
        "complete": (StepStatus.COMPLETED, "backfill_complete"),
        "partial": (StepStatus.PARTIAL, "backfill_partial"),
        "failure": (StepStatus.FAILED, "backfill_failed"),
        "invalid_input": (StepStatus.FAILED, "backfill_invalid_input"),
    }
    status, action = mapping[result.status]
    return WizardStepResult(
        step=6,
        name="Backfill",
        status=status,
        action=action,
        message="typed backfill result recorded",
        backfill=result,
    )


def _verification_step(result: VerificationResult) -> WizardStepResult:
    # Step 8 is COMPLETED iff no required check failed. Advisory divergences
    # (preserved posture, daemon liveness the deploy does not own) and
    # required-but-degraded state (sanctioned encrypted fallback) are embedded
    # and visible without blocking the deployment they do not contradict.
    required_failed = any(
        check.required and check.status is CheckStatus.FAIL for check in result.checks
    )
    if required_failed or result.overall is OverallStatus.FAILED:
        status, action = StepStatus.FAILED, "verification_failed"
    elif result.overall is OverallStatus.DEGRADED:
        status, action = StepStatus.COMPLETED, "verification_advisories"
    else:
        status, action = StepStatus.COMPLETED, "verification_ok"
    return WizardStepResult(
        step=8,
        name="Verification",
        status=status,
        action=action,
        message="typed verification graph recorded",
        verification=result,
    )


def _failed_step(step: int, name: str, action: str) -> WizardStepResult:
    return WizardStepResult(
        step=step,
        name=name,
        status=StepStatus.FAILED,
        action=action,
        message="step failed safely",
    )


def _skipped_step(step: int, name: str, action: str, message: str) -> WizardStepResult:
    return WizardStepResult(
        step=step,
        name=name,
        status=StepStatus.SKIPPED,
        action=action,
        message=message,
    )


def _sandbox_opted_in() -> bool:
    """A-T1-LANE opt-in: the Phase 5 apply lane is enabled only by an explicit
    ``TRADERBOT_PHASE5_SANDBOX=1`` (default off; never overloaded onto any
    unrelated env var)."""
    return os.environ.get(PHASE5_SANDBOX_ENV, "0") == "1"


def _expected_sandbox_image() -> str | None:
    """Deterministic image tag from the pinned repo Dockerfile (pure read).

    Returns None when the Dockerfile/provenance pin is missing or drifted —
    the caller fails closed with the typed dockerfile remedy.
    """
    try:
        return sandbox_image_tag(resolve_sandbox_dockerfile())
    except SandboxBuildError:
        return None


def _desired_keys(
    target: SandboxTarget, request: WizardRequest, image: str
) -> dict[str, JsonValue]:
    """The single-source sandbox contract for one target (D3). The image is
    passed EXPLICITLY (never the default_factory)."""
    config = sandbox_config_for(
        target.agent_id,
        request.data_root,
        target.workspace,
        mode=target.mode,
        image=image,
    )
    return config.to_openclaw_keys()


def _planned_writes(prefix: str, desired: dict[str, JsonValue]) -> list[tuple[str, JsonValue]]:
    docker = desired["docker"]
    if not isinstance(docker, dict):  # pragma: no cover - emission is a fixed dict
        raise RuntimeError("sandbox docker payload is not an object")
    writes: list[tuple[str, JsonValue]] = [
        (f"{prefix}.sandbox.mode", desired["mode"]),
        (f"{prefix}.sandbox.workspaceAccess", desired["workspaceAccess"]),
    ]
    writes.extend((f"{prefix}.sandbox.docker.{leaf}", docker[leaf]) for leaf in _DOCKER_LEAF_ORDER)
    return writes


@dataclass(frozen=True, slots=True)
class _AgentBackup:
    """Pre-write snapshot of one agent's sandbox subtree (D8); ABSENCE is
    recorded per key so rollback can UNSET what the apply created."""

    prefix: str
    sandbox_found: bool
    mode_found: bool
    mode: JsonValue | None
    workspace_access_found: bool
    workspace_access: JsonValue | None
    docker_found: bool
    docker: JsonValue | None


def _read_identity(ports: WizardPorts, prefix: str, agent_id: str) -> bool:
    """Fail-closed identity probe: the bracket index must still name the agent
    before AND after its writes (guards against agents.list re-ordering
    between the inventory read and the write)."""
    read = ports.openclaw.read_config_value(f"{prefix}.id")
    return read.state is ConfigReadState.FOUND and read.value == agent_id


def _backup_agent(ports: WizardPorts, prefix: str, agent_id: str) -> _AgentBackup | None:
    """Identity-probe plus whole-subtree backup; None = fail closed
    (unreadable, drifted, or malformed sandbox object)."""
    if not _read_identity(ports, prefix, agent_id):
        return None
    read = ports.openclaw.read_config_value(f"{prefix}.sandbox")
    if read.state is ConfigReadState.FAILED:
        return None
    if read.state is ConfigReadState.ABSENT:
        return _AgentBackup(
            prefix=prefix,
            sandbox_found=False,
            mode_found=False,
            mode=None,
            workspace_access_found=False,
            workspace_access=None,
            docker_found=False,
            docker=None,
        )
    if not isinstance(read.value, dict):
        return None  # malformed config shape — typed failure, no recovery guess
    sandbox = read.value
    docker = sandbox.get("docker")
    if "docker" in sandbox and not isinstance(docker, dict):
        return None  # malformed docker object
    return _AgentBackup(
        prefix=prefix,
        sandbox_found=True,
        mode_found="mode" in sandbox,
        mode=sandbox.get("mode"),
        workspace_access_found="workspaceAccess" in sandbox,
        workspace_access=sandbox.get("workspaceAccess"),
        docker_found="docker" in sandbox,
        docker=docker,
    )


def _backup_records(backup: _AgentBackup) -> tuple[SandboxKeyBackup, ...]:
    prefix = backup.prefix
    return (
        SandboxKeyBackup(
            key=f"{prefix}.sandbox",
            before=(
                {
                    **({"mode": backup.mode} if backup.mode_found else {}),
                    **(
                        {"workspaceAccess": backup.workspace_access}
                        if backup.workspace_access_found
                        else {}
                    ),
                    **({"docker": backup.docker} if backup.docker_found else {}),
                }
                if backup.sandbox_found
                else None
            ),
        ),
        SandboxKeyBackup(
            key=f"{prefix}.sandbox.mode", before=backup.mode if backup.mode_found else None
        ),
        SandboxKeyBackup(
            key=f"{prefix}.sandbox.workspaceAccess",
            before=backup.workspace_access if backup.workspace_access_found else None,
        ),
        SandboxKeyBackup(
            key=f"{prefix}.sandbox.docker",
            before=backup.docker if backup.docker_found else None,
        ),
    )


def _backup_value_for(backup: _AgentBackup, key: str) -> JsonValue | None:
    prefix = backup.prefix
    if key == f"{prefix}.sandbox.mode":
        return backup.mode if backup.mode_found else None
    if key == f"{prefix}.sandbox.workspaceAccess":
        return backup.workspace_access if backup.workspace_access_found else None
    leaf = f"{prefix}.sandbox.docker."
    if key.startswith(leaf) and backup.docker_found and isinstance(backup.docker, dict):
        return backup.docker.get(key[len(leaf) :])
    return None


def _check_postcondition(
    ports: WizardPorts, prefix: str, agent_id: str, desired: dict[str, JsonValue]
) -> tuple[bool, str]:
    """Byte-exact re-read postcondition: mode + workspaceAccess scalars and the
    docker object must equal the written values (extra pre-existing docker
    keys are a mismatch — the posture is exact or the apply aborts)."""
    if not _read_identity(ports, prefix, agent_id):
        return False, f"agents.list identity drifted for {agent_id} during the write"
    read = ports.openclaw.read_config_value(f"{prefix}.sandbox")
    if read.state is not ConfigReadState.FOUND or not isinstance(read.value, dict):
        return False, f"sandbox re-read failed for {agent_id}"
    live = read.value
    if (
        live.get("mode") != desired["mode"]
        or live.get("workspaceAccess") != (desired["workspaceAccess"])
    ):
        return False, f"sandbox posture keys drifted after write for {agent_id}"
    if live.get("docker") != desired["docker"]:
        return False, f"sandbox.docker is not byte-equal to the written object for {agent_id}"
    return True, ""


def _rollback_agent(
    ports: WizardPorts,
    target: SandboxTarget,
    backup: _AgentBackup,
    wrote: frozenset[str],
) -> tuple[list[SandboxWriteRecord], list[str]]:
    """D8 per-agent key-level restore: SET recorded pre-write values, UNSET
    keys absent pre-write, then UNSET leftover empty parents (T1 precedent:
    unset leaves empty objects; a byte-equal postcondition requires pruning).
    The identity probe gates every restore so a re-ordered index never
    scribbles onto a foreign agent."""
    agent_id = target.agent_id
    prefix = backup.prefix
    records: list[SandboxWriteRecord] = []
    failures: list[str] = []
    if not _read_identity(ports, prefix, agent_id):
        return records, [f"{agent_id}: identity drifted; restore refused (fail closed)"]
    # Docker subtree restores at the PARENT level so a pre-existing object is
    # restored byte-equal (including extra keys) and an apply-created object
    # is removed in one unset.
    if any(key.startswith(f"{prefix}.sandbox.docker.") for key in wrote):
        docker_key = f"{prefix}.sandbox.docker"
        if backup.docker_found:
            ok = ports.openclaw.set_config_json(docker_key, json.dumps(backup.docker))
            records.append(
                SandboxWriteRecord(agent_id, docker_key, "rollback_set", None, backup.docker)
            )
        else:
            ok = ports.openclaw.unset_config(docker_key)
            records.append(SandboxWriteRecord(agent_id, docker_key, "rollback_unset", None, None))
        if not ok:
            failures.append(f"{agent_id}: {docker_key} restore failed")
    # Leaf restores in reverse write order.
    for leaf, found, before in (
        ("workspaceAccess", backup.workspace_access_found, backup.workspace_access),
        ("mode", backup.mode_found, backup.mode),
    ):
        key = f"{prefix}.sandbox.{leaf}"
        if key not in wrote:
            continue
        if found:
            ok = ports.openclaw.set_config_json(key, json.dumps(before))
            records.append(SandboxWriteRecord(agent_id, key, "rollback_set", None, before))
        else:
            ok = ports.openclaw.unset_config(key)
            records.append(SandboxWriteRecord(agent_id, key, "rollback_unset", None, None))
        if not ok:
            failures.append(f"{agent_id}: {key} restore failed")
    if not backup.sandbox_found:
        read = ports.openclaw.read_config_value(f"{prefix}.sandbox")
        if read.state is ConfigReadState.FOUND and isinstance(read.value, dict) and not read.value:
            if ports.openclaw.unset_config(f"{prefix}.sandbox"):
                records.append(
                    SandboxWriteRecord(agent_id, f"{prefix}.sandbox", "rollback_unset", None, None)
                )
            else:
                failures.append(f"{agent_id}: sandbox parent prune failed")
    return records, failures


def _rollback_applied(
    ports: WizardPorts,
    applied: list[tuple[SandboxTarget, _AgentBackup, frozenset[str]]],
) -> tuple[list[SandboxWriteRecord], list[str]]:
    """D8: restore ALL previously-written agents in reverse order."""
    records: list[SandboxWriteRecord] = []
    failures: list[str] = []
    for target, backup, wrote in reversed(applied):
        agent_records, agent_failures = _rollback_agent(ports, target, backup, wrote)
        records.extend(agent_records)
        failures.extend(agent_failures)
    return records, failures


def _sandbox_apply(
    request: WizardRequest,
    ports: WizardPorts,
    targets: tuple[SandboxTarget, ...],
    expected_image: str,
) -> tuple[WizardStepResult, str]:
    """The real step-7 apply (D6/D7/D8). Returns the step result and the
    posture fingerprint to persist (empty string when nothing completed —
    the caller keeps any prior fingerprint and skips persistence)."""
    phase678 = ports.phase678
    assert phase678 is not None  # run_late_steps gates this before step 7
    image = phase678.build_sandbox_image()  # build BEFORE any config write (D7)
    if image is None:
        return (
            _failed_sandbox_step(
                "sandbox_build_failed",
                "sandbox image build failed; zero config writes made. Remedy: install/start "
                "Docker (e.g. systemctl start docker) and re-run traderbot deploy",
            ),
            "",
        )
    if image != expected_image:
        # Image-hash drift between the pinned Dockerfile resolve and the build
        # output — fail closed rather than fingerprint the wrong artifact.
        return (
            _failed_sandbox_step(
                "sandbox_image_mismatch",
                f"built image {image} differs from the pinned Dockerfile tag {expected_image}; "
                "zero config writes made. Remedy: restore install/docker/Dockerfile to the "
                "digest pinned by install/docker/build-sandbox.sh and re-run",
            ),
            "",
        )
    inventory = ports.openclaw.inventory_agents()
    if inventory is None:
        return (
            _failed_sandbox_step(
                "sandbox_config_unreadable",
                "OpenClaw agent inventory is unreadable; zero config writes made. Remedy: "
                "restore OpenClaw config readability and re-run traderbot deploy",
            ),
            "",
        )
    index_by_id = {summary.id: index for index, summary in enumerate(inventory.root)}
    missing = [target.agent_id for target in targets if target.agent_id not in index_by_id]
    if missing:
        return (
            _failed_sandbox_step(
                "sandbox_target_missing",
                f"sandbox targets absent from the live inventory: {', '.join(missing)}; zero "
                "config writes made. Remedy: re-run traderbot deploy so preflight re-resolves "
                "the selected agents",
            ),
            "",
        )
    prefixes = {
        target.agent_id: f"agents.list[{index_by_id[target.agent_id]}]" for target in targets
    }
    desired = {target.agent_id: _desired_keys(target, request, image) for target in targets}
    plan_records = tuple(
        SandboxWriteRecord(target.agent_id, key, "set", None, value)
        for target in targets
        for key, value in _planned_writes(prefixes[target.agent_id], desired[target.agent_id])
    )
    if not request.approvals.sandbox_apply:
        # ONE operator approval gates every write; the recorded plan lists the
        # exact per-agent writes the approval would authorize.
        report = SandboxApplyReport(image=image, plan=plan_records, agents=(), rolled_back=False)
        return (
            WizardStepResult(
                step=_SANDBOX_STEP,
                name=_SANDBOX_STEP_NAME,
                status=StepStatus.FAILED,
                action="sandbox_approval_required",
                message=(
                    f"docker sandbox apply needs operator approval for "
                    f"{len(plan_records)} writes across {len(targets)} agent(s) "
                    f"(image {image}); zero config writes made. Remedy: re-run with the "
                    "sandbox apply config approval set"
                ),
                sandbox_report=report,
            ),
            "",
        )
    applied: list[tuple[SandboxTarget, _AgentBackup, frozenset[str]]] = []
    agent_results: list[SandboxAgentResult] = []
    for target in targets:
        agent_id = target.agent_id
        prefix = prefixes[agent_id]
        data_dir = f"{target.mode}-{target.agent_id}"
        writes = _planned_writes(prefix, desired[agent_id])
        backup = _backup_agent(ports, prefix, agent_id)
        if backup is None:
            detail = (
                f"identity probe or sandbox backup failed for {agent_id}; aborting before "
                "any write to it"
            )
            return _abort_apply(
                ports,
                image,
                plan_records,
                agent_results,
                applied,
                failed=(agent_id, data_dir, (), ()),
                action="sandbox_config_unreadable",
                detail=detail,
            )
        backup_rows = _backup_records(backup)
        write_rows: list[SandboxWriteRecord] = []
        wrote: set[str] = set()
        failed_key: str | None = None
        for key, value in writes:
            if not ports.openclaw.set_config_json(key, json.dumps(value)):
                failed_key = key
                break
            wrote.add(key)
            write_rows.append(
                SandboxWriteRecord(agent_id, key, "set", _backup_value_for(backup, key), value)
            )
        abort_action: str | None = None
        detail = ""
        if failed_key is not None:
            abort_action = "sandbox_write_failed"
            detail = f"config write failed at {failed_key}; rolling back"
        else:
            intact, detail = _check_postcondition(ports, prefix, agent_id, desired[agent_id])
            if not intact:
                abort_action = "sandbox_postcondition_failed"
                detail = f"{detail}; rolling back"
        if abort_action is not None:
            applied.append((target, backup, frozenset(wrote)))
            return _abort_apply(
                ports,
                image,
                plan_records,
                agent_results,
                applied,
                failed=(agent_id, data_dir, backup_rows, tuple(write_rows)),
                action=abort_action,
                detail=detail,
            )
        agent_results.append(
            SandboxAgentResult(
                agent_id=agent_id,
                data_dir=data_dir,
                status="completed",
                backups=backup_rows,
                writes=tuple(write_rows),
                message="docker sandbox posture applied",
            )
        )
        applied.append((target, backup, frozenset(wrote)))
    report = SandboxApplyReport(
        image=image, plan=plan_records, agents=tuple(agent_results), rolled_back=False
    )
    return (
        WizardStepResult(
            step=_SANDBOX_STEP,
            name=_SANDBOX_STEP_NAME,
            status=StepStatus.COMPLETED,
            action="docker_sandbox_applied",
            message=(
                f"docker sandbox posture applied for {len(targets)} agent(s) with image "
                f"{image} ({len(plan_records)} writes, all re-reads byte-exact)"
            ),
            agents=tuple(
                AgentDeployResult(
                    agent_id=result.agent_id,
                    status=StepStatus.COMPLETED,
                    message=result.message,
                )
                for result in agent_results
            ),
            sandbox_report=report,
        ),
        step7_docker_fingerprint(request, targets, image),
    )


def _abort_apply(
    ports: WizardPorts,
    image: str,
    plan_records: tuple[SandboxWriteRecord, ...],
    agent_results: list[SandboxAgentResult],
    applied: list[tuple[SandboxTarget, _AgentBackup, frozenset[str]]],
    *,
    failed: tuple[str, str, tuple[SandboxKeyBackup, ...], tuple[SandboxWriteRecord, ...]],
    action: str,
    detail: str,
) -> tuple[WizardStepResult, str]:
    """Rollback every written agent in reverse order, then abort (D8)."""
    agent_id, data_dir, backup_rows, write_rows = failed
    agent_results = [
        *agent_results,
        SandboxAgentResult(
            agent_id=agent_id,
            data_dir=data_dir,
            status="failed",
            backups=backup_rows,
            writes=write_rows,
            message=detail,
        ),
    ]
    rollback_records, failures = _rollback_applied(ports, applied)
    final_action = action if not failures else "sandbox_rollback_failed"
    restored = len(applied)
    suffix = (
        f"; rolled back {restored} agent(s); no partial posture remains"
        if restored
        else "; zero config writes made"
    )
    if failures:
        suffix = f"; ROLLBACK INCOMPLETE ({'; '.join(failures)}) — manual config restore required"
    report = SandboxApplyReport(
        image=image,
        plan=plan_records,
        agents=tuple(agent_results),
        rolled_back=True,
        rollback=tuple(rollback_records),
    )
    return (
        WizardStepResult(
            step=_SANDBOX_STEP,
            name=_SANDBOX_STEP_NAME,
            status=StepStatus.FAILED,
            action=final_action,
            message=f"{detail}{suffix}",
            agents=tuple(
                AgentDeployResult(
                    agent_id=result.agent_id,
                    status=(
                        StepStatus.FAILED if result.status == "failed" else StepStatus.COMPLETED
                    ),
                    message=result.message,
                )
                for result in agent_results
            ),
            sandbox_report=report,
        ),
        "",
    )


def _failed_sandbox_step(action: str, message: str) -> WizardStepResult:
    return WizardStepResult(
        step=_SANDBOX_STEP,
        name=_SANDBOX_STEP_NAME,
        status=StepStatus.FAILED,
        action=action,
        message=message,
    )


def _postconditions_intact(
    request: WizardRequest,
    ports: WizardPorts,
    targets: tuple[SandboxTarget, ...],
    image: str,
) -> bool:
    """Re-run gate: skip step 7 only when every target's live sandbox object
    re-reads byte-equal to the current desired posture (fingerprint equality
    alone is not enough — drift since the successful run re-applies)."""
    inventory = ports.openclaw.inventory_agents()
    if inventory is None:
        return False
    index_by_id = {summary.id: index for index, summary in enumerate(inventory.root)}
    for target in targets:
        index = index_by_id.get(target.agent_id)
        if index is None:
            return False
        prefix = f"agents.list[{index}]"
        desired = _desired_keys(target, request, image)
        intact, _ = _check_postcondition(ports, prefix, target.agent_id, desired)
        if not intact:
            return False
    return True


def run_late_steps(
    request: WizardRequest,
    ports: WizardPorts,
    steps: list[WizardStepResult],
    selected_agents: tuple[str, ...],
    plan: DeploymentPreflight,
) -> None:
    phase678 = ports.phase678
    if phase678 is None:
        append_blocked_late_steps(steps, 6)
        return
    prior = phase678.load_state(request)
    fingerprints = {step: step_fingerprint(request, step) for step in (6, 7, 8)}
    completed = {
        step: None if prior is None else prior.completed(step, fingerprints[step])
        for step in (6, 8)
    }
    backfill_step = completed[6]
    try:
        if backfill_step is None:
            backfill_step = _backfill_step(phase678.run_backfill(request))
        steps.append(backfill_step)
    except (OSError, RuntimeError, ValueError):
        steps.append(_failed_step(6, "Backfill", "backfill_exception"))
    if steps[-1].action == "backfill_invalid_input":
        steps.append(
            _skipped_step(
                7,
                _SANDBOX_STEP_NAME,
                "dependency_unavailable",
                "blocked by an incomplete prerequisite",
            )
        )
        steps.append(
            _skipped_step(
                8, "Verification", "dependency_unavailable", "blocked by an incomplete prerequisite"
            )
        )
        _save_late_state(request, phase678, fingerprints, steps, _prior_docker_fp(prior))
        return
    # --- Step 7: Docker sandbox apply (todo-8) ---
    targets = resolve_sandbox_targets(plan, mode=request.mode)
    expected_image = _expected_sandbox_image()
    docker_step: WizardStepResult | None = None
    docker_fp = _prior_docker_fp(prior)
    if not _sandbox_opted_in():
        docker_step = _skipped_step(
            _SANDBOX_STEP,
            _SANDBOX_STEP_NAME,
            "sandbox_apply_disabled",
            f"docker sandbox apply is opt-in for this phase (A-T1-LANE); set "
            f"{PHASE5_SANDBOX_ENV}=1 to enable it. Zero config writes made.",
        )
    else:
        if prior is not None and expected_image is not None:
            candidate_fp = step7_docker_fingerprint(request, targets, expected_image)
            completed7 = prior.completed(7, fingerprints[7])
            if (
                prior.step7_docker_fingerprint == candidate_fp
                and completed7 is not None
                and _postconditions_intact(request, ports, targets, expected_image)
            ):
                docker_step = completed7
                docker_fp = candidate_fp
        if docker_step is None:
            if not phase678.ensure_docker_available():
                docker_step = _skipped_step(
                    _SANDBOX_STEP,
                    _SANDBOX_STEP_NAME,
                    "docker_unavailable",
                    "Docker is not available (binary or live-daemon probe failed); zero config "
                    "writes made. Remedy: install Docker or start the daemon (e.g. systemctl "
                    "start docker), then re-run traderbot deploy",
                )
            elif expected_image is None:
                docker_step = _failed_sandbox_step(
                    "sandbox_dockerfile_unverified",
                    "install/docker/Dockerfile is missing or its provenance pin drifted; zero "
                    "config writes made. Remedy: restore the pinned Dockerfile (digest pinned "
                    "by install/docker/build-sandbox.sh) and re-run traderbot deploy",
                )
            else:
                try:
                    docker_step, docker_fp = _sandbox_apply(request, ports, targets, expected_image)
                except (OSError, RuntimeError, ValueError):
                    docker_step = _failed_sandbox_step(
                        "sandbox_apply_exception", "step failed safely"
                    )
                    docker_fp = _prior_docker_fp(prior)
    steps.append(docker_step)
    if docker_step.status is not StepStatus.COMPLETED:
        # Step 8 asserts sandbox postures the apply did not complete; skip it
        # rather than pinning a known-incomplete verification, and DO NOT
        # persist state (zero writes — including deploy state — on abort).
        steps.append(
            _skipped_step(
                8, "Verification", "dependency_unavailable", "blocked by an incomplete prerequisite"
            )
        )
        return
    verification_step = completed[8]
    try:
        if verification_step is None:
            verification_step = _verification_step(
                phase678.run_verification(request, selected_agents)
            )
        steps.append(verification_step)
    except (OSError, RuntimeError, ValueError):
        steps.append(_failed_step(8, "Verification", "verification_exception"))
    _save_late_state(request, phase678, fingerprints, steps, docker_fp)


def sandbox_notice(step: WizardStepResult) -> str | None:
    """One-line human summary rendered by the CLI when step 7 prints.

    Emitted for the apply-with-report and opt-in-skip actions only; typed
    failure rows already carry their remedy in the step message."""
    report = step.sandbox_report
    if report is not None:
        tail = "; rollback executed" if report.rolled_back else ""
        return (
            f"Docker sandbox image {report.image}: {len(report.plan)} planned writes "
            f"across {len(report.agents)} agent(s){tail}"
        )
    if step.action == "sandbox_apply_disabled":
        return f"Docker sandbox apply is opt-in this phase (set {PHASE5_SANDBOX_ENV}=1)."
    return None


def _prior_docker_fp(prior: DeployState | None) -> str:
    return "" if prior is None else prior.step7_docker_fingerprint


def _save_late_state(
    request: WizardRequest,
    phase678: Phase678Port,
    fingerprints: dict[int, str],
    steps: list[WizardStepResult],
    docker_fingerprint: str,
) -> None:
    phase678.save_state(
        request,
        DeployState(
            step6_fingerprint=fingerprints[6],
            step7_fingerprint=fingerprints[7],
            step8_fingerprint=fingerprints[8],
            step7_docker_fingerprint=docker_fingerprint,
            steps=tuple(step for step in steps if step.step >= 6),
            bootstrap_registered=True,
        ),
    )


__all__ = ["PHASE5_SANDBOX_ENV", "append_blocked_late_steps", "run_late_steps", "sandbox_notice"]
