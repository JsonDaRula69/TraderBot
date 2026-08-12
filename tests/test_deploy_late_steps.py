from __future__ import annotations

from pathlib import Path

import pytest

from tests.deploy_wizard_fakes import FakeEnvironment, FakePhase45, FakePhase678
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.verify_models import OverallStatus, VerificationResult
from traderbot.deploy.wizard import StepStatus, WizardRequest
from traderbot.deploy.wizard_contracts import DeployState, LatePreflightResult
from traderbot.deploy.wizard_state import BootstrapCronState, DeployApprovals
from traderbot.kalshi.order_models import MarketCategory


def _request(tmp_path: Path) -> WizardRequest:
    return WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
        approvals=DeployApprovals(create_agents=True),
        data_root=tmp_path / "data",
    )


def test_steps_6_8_complete(tmp_path: Path) -> None:
    # Given: every currently composed deploy dependency succeeds.
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: the deploy wizard runs the selected configuration.
    result = environment.wizard().run(_request(tmp_path))

    # Then: the public workflow records all eight ordered step outcomes.
    assert tuple(step.step for step in result.steps) == tuple(range(1, 9))
    assert result.completed_steps == tuple(range(1, 9))
    assert result.deployment_complete is True
    assert result.remaining_steps == ()


def test_backfill_failure_partial(tmp_path: Path) -> None:
    # Given: backfill preserves committed progress while verification remains healthy.
    phase678 = FakePhase678(backfill=BackfillResult(status="partial"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the full deploy workflow runs.
    result = environment.wizard().run(_request(tmp_path))

    # Then: verification still runs and the workflow remains truthfully nonzero.
    assert result.steps[5].status is StepStatus.PARTIAL
    assert result.steps[5].action == "backfill_partial"
    assert result.steps[7].status is StepStatus.COMPLETED
    assert phase678.calls == [6, 8]
    assert result.success is False


def test_verification_degraded_is_partial(tmp_path: Path) -> None:
    # Given: all mutation steps and backfill complete but verification is degraded.
    phase678 = FakePhase678(
        verification=VerificationResult(overall=OverallStatus.DEGRADED, checks=())
    )
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: deploy reaches the verification graph.
    result = environment.wizard().run(_request(tmp_path))

    # Then: the typed verification result maps to a nonzero partial step.
    assert result.steps[7].status is StepStatus.PARTIAL
    assert result.steps[7].action == "verification_degraded"
    assert result.success is False


@pytest.mark.parametrize(
    ("cron_state", "status", "action"),
    [
        (BootstrapCronState.EXACT, StepStatus.COMPLETED, "phase5_sandbox_stub_cron_exact"),
        (BootstrapCronState.MISSING, StepStatus.PARTIAL, "phase5_sandbox_stub_cron_absent"),
        (BootstrapCronState.CONFLICT, StepStatus.FAILED, "phase5_sandbox_stub_cron_conflict"),
        (BootstrapCronState.FAILED, StepStatus.FAILED, "phase5_sandbox_stub_cron_unreadable"),
    ],
)
def test_step7_cron_states_are_read_only(
    tmp_path: Path,
    cron_state: BootstrapCronState,
    status: StepStatus,
    action: str,
) -> None:
    # Given: a persisted Gateway cron inventory state after steps 1-6.
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())
    request = _request(tmp_path)
    observed_states = iter((BootstrapCronState.EXACT, cron_state))
    environment.openclaw.inspect_bootstrap_cron = lambda: next(observed_states)
    cron_before = set(environment.openclaw.cron_identities)

    # When: the deployment reaches the read-only Phase 5 stub check.
    result = environment.wizard().run(request)

    # Then: machine status is stable and Step 7 performs no cron mutation.
    assert result.steps[6].status is status
    assert result.steps[6].action == action
    assert environment.openclaw.cron_identities == cron_before


def test_step_exceptions_are_isolated_and_redacted(tmp_path: Path) -> None:
    # Given: ordinary exceptions occur independently in backfill and verification.
    phase678 = FakePhase678()
    phase678.raise_backfill = True
    phase678.raise_verification = True
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the wizard runs every safe independent late step.
    result = environment.wizard().run(_request(tmp_path))

    # Then: both failures are typed, Step 7 still runs, and canaries are absent.
    assert tuple(step.action for step in result.steps[5:]) == (
        "backfill_exception",
        "phase5_sandbox_stub_cron_exact",
        "verification_exception",
    )
    assert "CANARY" not in result.model_dump_json()


def test_late_preflight_failure_prevents_all_mutation(tmp_path: Path) -> None:
    # Given: Step 6-8 configuration fails the global read-only preflight.
    phase678 = FakePhase678()
    phase678.preflight_result = LatePreflightResult(valid=False, action="late_request_invalid")
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the deploy wizard starts.
    result = environment.wizard().run(_request(tmp_path))

    # Then: exit classification is invalid input and no stateful port mutates.
    assert result.input_valid is False
    assert result.steps[0].action == "late_request_invalid"
    assert environment.openclaw.created_agents == set()
    assert environment.openclaw.secret_refs == {}
    assert environment.tokens.profiles == {}
    assert environment.injector.injected == set()


def test_completed_late_steps_rerun_idempotently(tmp_path: Path) -> None:
    # Given: the same selected desired state is deployed twice.
    phase678 = FakePhase678()
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    request = _request(tmp_path)

    # When: both convergent runs complete.
    first = environment.wizard().run(request)
    second = environment.wizard().run(request)

    # Then: all steps remain complete without duplicate persistent identities.
    assert first.success is True and second.success is True
    assert phase678.calls == [6, 8]
    assert environment.tokens.created_count == {"main": 1, "weather": 1}
    assert environment.openclaw.cron_identities == {("traderbot-main-at-5m", "main")}


def test_backfill_invalid_input_marks_deploy_invalid(tmp_path: Path) -> None:
    # Given: the embedded backfill boundary rejects its input.
    phase678 = FakePhase678(backfill=BackfillResult(status="invalid_input"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the wizard records Step 6.
    result = environment.wizard().run(_request(tmp_path))

    # Then: deploy preserves the typed result and classifies the request invalid.
    assert result.input_valid is False
    assert result.steps[5].action == "backfill_invalid_input"
    assert result.steps[7].status is StepStatus.SKIPPED


def test_partial_rerun_executes_only_incomplete_step(tmp_path: Path) -> None:
    # Given: Step 6 is partial while Steps 7 and 8 complete.
    phase678 = FakePhase678(backfill=BackfillResult(status="partial"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    request = _request(tmp_path)
    _ = environment.wizard().run(request)
    phase678.backfill = BackfillResult(status="complete")

    # When: unchanged desired state reruns.
    result = environment.wizard().run(request)

    # Then: only incomplete Step 6 executes again.
    assert result.success is True
    assert phase678.calls == [6, 8, 6]


def test_changed_backfill_config_invalidates_step6_and_verification(tmp_path: Path) -> None:
    # Given: all late steps completed for a six-month request.
    phase678 = FakePhase678()
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    request = _request(tmp_path)
    _ = environment.wizard().run(request)

    # When: only the historical window changes.
    changed = request.model_copy(update={"months_backfill": 7})
    _ = environment.wizard().run(changed)

    # Then: backfill and downstream verification rerun while the cron stub is reused.
    assert phase678.calls == [6, 8, 6, 8]


def test_deleted_completed_one_shot_is_not_recreated(tmp_path: Path) -> None:
    # Given: a completed deployment recorded bootstrap registration.
    phase678 = FakePhase678()
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    request = _request(tmp_path)
    _ = environment.wizard().run(request)
    environment.openclaw.cron_identities.clear()
    environment.openclaw.bootstrap_state = BootstrapCronState.MISSING

    # When: the post-execution deployment is inspected again.
    result = environment.wizard().run(request)

    # Then: absence is action-required partial and no cron is recreated.
    assert result.steps[6].action == "phase5_sandbox_stub_cron_completed_absent"
    assert result.steps[6].status is StepStatus.PARTIAL
    assert environment.openclaw.cron_identities == set()


def test_completed_retained_bootstrap_reaches_step7_partial(tmp_path: Path) -> None:
    # Given: Gateway retains a completed canonical one-shot.
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())
    environment.openclaw.bootstrap_state = BootstrapCronState.COMPLETED_RETAINED

    # When: deployment reconciles the lifecycle.
    result = environment.wizard().run(_request(tmp_path))

    # Then: no recreation occurs and Step 7 reports action-required partial.
    assert result.steps[6].status is StepStatus.PARTIAL
    assert result.steps[6].action == "phase5_sandbox_stub_cron_completed_retained"
    assert environment.openclaw.cron_identities == set()


def test_persisted_unregistered_missing_bootstrap_is_not_created(tmp_path: Path) -> None:
    # Given: persisted deploy state explicitly says bootstrap was never registered.
    phase678 = FakePhase678()
    request = _request(tmp_path)
    phase678.state = DeployState(
        step6_fingerprint="",
        step7_fingerprint="",
        step8_fingerprint="",
        steps=(),
        bootstrap_registered=False,
    )
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: missing Gateway inventory is reconciled.
    result = environment.wizard().run(request)

    # Then: absence is unknown, deployment fails closed, and no cron is registered.
    assert result.steps[2].status is StepStatus.FAILED
    assert environment.openclaw.cron_identities == set()
