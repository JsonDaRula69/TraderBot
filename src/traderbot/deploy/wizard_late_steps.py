"""Run backfill, sandbox-stub, and verification wizard steps."""

from __future__ import annotations

from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import step_fingerprint
from traderbot.deploy.verify_models import (
    CheckStatus,
    OverallStatus,
    VerificationResult,
)
from traderbot.deploy.wizard_contracts import (
    DeployState,
    Phase678Port,
    StepStatus,
    WizardPorts,
    WizardRequest,
    WizardStepResult,
)
from traderbot.deploy.wizard_state import BootstrapCronState

STUB_MESSAGE = (
    "Docker sandbox configuration is Phase 5 (#169). "
    "Agents will run unsandboxed until Phase 5 is implemented."
)


def append_blocked_late_steps(steps: list[WizardStepResult], first: int) -> None:
    names = (
        "OpenClaw config",
        "SysAdmin setup",
        "Category selection",
        "Infisical and API tokens",
        "Database creation",
        "Backfill",
        "Simulation start",
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


def _cron_step(state: BootstrapCronState) -> WizardStepResult:
    mapping = {
        BootstrapCronState.EXACT: (StepStatus.COMPLETED, "phase5_sandbox_stub_cron_exact"),
        BootstrapCronState.MISSING: (StepStatus.PARTIAL, "phase5_sandbox_stub_cron_absent"),
        BootstrapCronState.UNKNOWN_ABSENT: (
            StepStatus.FAILED,
            "phase5_sandbox_stub_cron_unknown_absent",
        ),
        BootstrapCronState.COMPLETED_RETAINED: (
            StepStatus.PARTIAL,
            "phase5_sandbox_stub_cron_completed_retained",
        ),
        BootstrapCronState.COMPLETED_ABSENT: (
            StepStatus.PARTIAL,
            "phase5_sandbox_stub_cron_completed_absent",
        ),
        BootstrapCronState.CONFLICT: (StepStatus.FAILED, "phase5_sandbox_stub_cron_conflict"),
        BootstrapCronState.FAILED: (StepStatus.FAILED, "phase5_sandbox_stub_cron_unreadable"),
    }
    status, action = mapping[state]
    return WizardStepResult(
        step=7,
        name="Simulation start",
        status=status,
        action=action,
        message="Phase 5 sandbox stub and Gateway bootstrap cron inspected",
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


def run_late_steps(
    request: WizardRequest,
    ports: WizardPorts,
    steps: list[WizardStepResult],
    bootstrap_state: BootstrapCronState,
    created_agents: tuple[str, ...],
) -> None:
    phase678 = ports.phase678
    if phase678 is None:
        append_blocked_late_steps(steps, 6)
        return
    prior = phase678.load_state(request)
    fingerprints = {step: step_fingerprint(request, step) for step in (6, 7, 8)}
    completed = {
        step: None if prior is None else prior.completed(step, fingerprints[step])
        for step in (6, 7, 8)
    }
    backfill_step = completed[6]
    try:
        if backfill_step is None:
            backfill_step = _backfill_step(phase678.run_backfill(request))
        steps.append(backfill_step)
    except (OSError, RuntimeError, ValueError):
        steps.append(_failed_step(6, "Backfill", "backfill_exception"))
    if steps[-1].action == "backfill_invalid_input":
        steps.append(_failed_step(7, "Simulation start", "dependency_unavailable"))
        steps[-1] = steps[-1].model_copy(update={"status": StepStatus.SKIPPED})
        steps.append(_failed_step(8, "Verification", "dependency_unavailable"))
        steps[-1] = steps[-1].model_copy(update={"status": StepStatus.SKIPPED})
        _save_late_state(request, phase678, fingerprints, steps)
        return
    cron_step = (
        None
        if bootstrap_state
        in {BootstrapCronState.COMPLETED_RETAINED, BootstrapCronState.COMPLETED_ABSENT}
        else completed[7]
    )
    try:
        if cron_step is None:
            cron_step = _cron_step(
                bootstrap_state
                if bootstrap_state
                in {BootstrapCronState.COMPLETED_RETAINED, BootstrapCronState.COMPLETED_ABSENT}
                else ports.openclaw.inspect_bootstrap_cron()
            )
        steps.append(cron_step)
    except (OSError, RuntimeError, ValueError):
        steps.append(_failed_step(7, "Simulation start", "phase5_sandbox_stub_cron_exception"))
    verification_step = completed[8]
    try:
        if verification_step is None:
            verification_step = _verification_step(
                phase678.run_verification(request, created_agents)
            )
        steps.append(verification_step)
    except (OSError, RuntimeError, ValueError):
        steps.append(_failed_step(8, "Verification", "verification_exception"))
    _save_late_state(request, phase678, fingerprints, steps)


def _save_late_state(
    request: WizardRequest,
    phase678: Phase678Port,
    fingerprints: dict[int, str],
    steps: list[WizardStepResult],
) -> None:
    phase678.save_state(
        request,
        DeployState(
            step6_fingerprint=fingerprints[6],
            step7_fingerprint=fingerprints[7],
            step8_fingerprint=fingerprints[8],
            steps=tuple(step for step in steps if step.step >= 6),
            bootstrap_registered=True,
        ),
    )


def _failed_step(step: int, name: str, action: str) -> WizardStepResult:
    return WizardStepResult(
        step=step,
        name=name,
        status=StepStatus.FAILED,
        action=action,
        message="step failed safely",
    )


__all__ = ["STUB_MESSAGE", "append_blocked_late_steps", "run_late_steps"]
