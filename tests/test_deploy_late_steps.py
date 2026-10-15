from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tests.deploy_wizard_fakes import (
    FakeEnvironment,
    FakeOpenClaw,
    FakePhase45,
    FakePhase678,
    fake_workspace,
)
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import load_deploy_state, step7_docker_fingerprint
from traderbot.deploy.sandbox_build import resolve_sandbox_dockerfile
from traderbot.deploy.verify_models import (
    CheckId,
    CheckResult,
    CheckStatus,
    OverallStatus,
    VerificationResult,
)
from traderbot.deploy.wizard import StepStatus, WizardRequest
from traderbot.deploy.wizard_contracts import DeployState, LatePreflightResult
from traderbot.deploy.wizard_late_steps import PHASE5_SANDBOX_ENV
from traderbot.deploy.wizard_state import (
    BootstrapCronState,
    DeployApprovals,
    SandboxTarget,
)
from traderbot.kalshi.order_models import MarketCategory
from traderbot.sandbox import sandbox_image_tag

_CATEGORIES = (MarketCategory.WEATHER,)
_TWO = (MarketCategory.WEATHER, MarketCategory.WORLD)


@pytest.fixture(autouse=True)
def _isolate_phase5_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Phase 5 apply lane is opt-in; tests set it explicitly."""
    monkeypatch.delenv(PHASE5_SANDBOX_ENV, raising=False)


def _enable_phase5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PHASE5_SANDBOX_ENV, "1")


def _request(tmp_path: Path) -> WizardRequest:
    return WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
        approvals=DeployApprovals(create_agents=True),
        data_root=tmp_path / "data",
    )


def _approved_request(
    tmp_path: Path,
    categories: tuple[MarketCategory, ...] = _CATEGORIES,
) -> WizardRequest:
    return WizardRequest(
        categories=categories,
        mode="backtest",
        category_workspaces={category: tmp_path / category.value for category in categories},
        approvals=DeployApprovals(create_agents=True, sandbox_apply=True),
        data_root=tmp_path / "data",
    )


def _sandbox_environment(
    *,
    backfill: BackfillResult | None = None,
    verification: VerificationResult | None = None,
    docker_ready: bool = True,
    build_succeeds: bool = True,
    built_tag: str | None = None,
) -> tuple[FakeEnvironment, FakePhase678]:
    """Environment wired for the real step-7 lane: the build seam is wired to
    the openclaw fake so tests can prove image-build precedes every write."""
    late = FakePhase678(
        backfill=backfill,
        verification=verification,
        docker_ready=docker_ready,
        build_succeeds=build_succeeds,
        built_tag=built_tag,
    )
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=late)
    late.openclaw = environment.openclaw
    return environment, late


def _tag() -> str:
    return sandbox_image_tag(resolve_sandbox_dockerfile())


def _set_events(openclaw: FakeOpenClaw) -> list[str]:
    return [event for event in openclaw.config_events if event.startswith(("set:", "unset:"))]


def test_phase5_env_gate_is_the_dedicated_opt_in(tmp_path: Path) -> None:
    # Given/When/Then: the step-7 lane is keyed to TRADERBOT_PHASE5_SANDBOX
    # only (never overloaded onto an unrelated env var) and defaults to off.
    assert PHASE5_SANDBOX_ENV == "TRADERBOT_PHASE5_SANDBOX"
    import traderbot.deploy.wizard_late_steps as late_steps

    assert PHASE5_SANDBOX_ENV in (late_steps.__doc__ or "")


def test_steps_6_8_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: every composed deploy dependency succeeds and the apply lane is on.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()

    # When: the deploy wizard runs the selected configuration.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: the public workflow records all eight ordered step outcomes.
    assert tuple(step.step for step in result.steps) == tuple(range(1, 9))
    assert result.completed_steps == tuple(range(1, 9))
    assert result.steps[6].action == "docker_sandbox_applied"
    assert result.deployment_complete is True
    assert result.remaining_steps == ()


def test_step7_skips_when_phase5_env_unset(tmp_path: Path) -> None:
    # Given: the apply lane opt-in env var is absent.
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)

    # When: the full deploy workflow runs.
    result = environment.wizard().run(request)

    # Then: step 7 records the typed skip with zero config writes and zero
    # deploy-state mutation; steps 1-6 behave exactly as before (the step-3
    # bootstrap registration is the only cron identity, proving step 7
    # performs no cron mutation).
    assert result.steps[6].status is StepStatus.SKIPPED
    assert result.steps[6].action == "sandbox_apply_disabled"
    assert PHASE5_SANDBOX_ENV in result.steps[6].message
    assert result.steps[7].status is StepStatus.SKIPPED
    assert result.steps[7].name == "Verification"
    assert environment.openclaw.cron_identities == {("traderbot-main-at-5m", "main")}
    assert environment.openclaw.config_events == []
    assert late.docker_checks == 0
    assert late.build_calls == 0
    assert load_deploy_state(request.data_root) is None


def test_step7_docker_unavailable_skips_with_typed_remedy_zero_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the apply lane is enabled but the docker presence gate fails.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment(docker_ready=False)
    request = _approved_request(tmp_path)

    # When: the wizard reaches step 7.
    result = environment.wizard().run(request)

    # Then: typed remedy, zero config writes, deploy state untouched.
    assert result.steps[6].action == "docker_unavailable"
    assert result.steps[6].status is StepStatus.SKIPPED
    assert "systemctl start docker" in result.steps[6].message
    assert result.steps[7].status is StepStatus.SKIPPED
    assert environment.openclaw.config_events == []
    assert late.docker_checks == 1
    assert late.build_calls == 0
    assert load_deploy_state(request.data_root) is None


def test_step7_build_failure_first_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: docker is present but the sandbox image build fails.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment(build_succeeds=False)
    request = _approved_request(tmp_path)

    # When: step 7 runs the build-before-write lane.
    result = environment.wizard().run(request)

    # Then: the build failure aborts BEFORE any config write with a typed remedy.
    assert result.steps[6].status is StepStatus.FAILED
    assert result.steps[6].action == "sandbox_build_failed"
    assert "zero config writes made" in result.steps[6].message
    assert "systemctl start docker" in result.steps[6].message
    assert late.build_calls == 1
    assert environment.openclaw.config_events == []
    assert load_deploy_state(request.data_root) is None


def test_step7_build_failure_on_drifted_posture_preserves_prior_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a prior successful apply, then the live posture drifts.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)
    first = environment.wizard().run(request)
    assert first.steps[6].action == "docker_sandbox_applied"
    prior_state = load_deploy_state(request.data_root)
    assert prior_state is not None
    environment.openclaw.config["weather"]["sandbox"]["docker"]["network"] = "bridge"

    # When: a re-run re-applies because postconditions drifted, and the build fails.
    late.build_succeeds = False
    sets_before = _set_events(environment.openclaw)
    tree_before = deepcopy(environment.openclaw.config)
    second = environment.wizard().run(request)

    # Then: the build failure aborts before any write; prior state persists
    # (the reuse proof's READS are free; there are no NEW write mutations and
    # the tree is untouched).
    assert second.steps[6].action == "sandbox_build_failed"
    assert second.steps[6].status is StepStatus.FAILED
    assert _set_events(environment.openclaw) == sets_before
    assert environment.openclaw.config == tree_before
    assert load_deploy_state(request.data_root) == prior_state


def test_step7_rerun_with_intact_posture_skips_build_and_rewrites_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a completed apply whose postconditions still hold byte-exactly.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)
    _ = environment.wizard().run(request)
    prior_state = load_deploy_state(request.data_root)
    assert prior_state is not None
    sets_after_first = _set_events(environment.openclaw)

    # When: the same request re-runs while docker has become unavailable.
    late.docker_ready = False
    late.build_succeeds = False
    result = environment.wizard().run(request)

    # Then: the completed record is reused by fingerprint + re-read proof —
    # no docker probe, no build, and no config write (IS-8: a skip with the
    # image absent fails closed at spawn, not at deploy).
    assert result.steps[6].action == "docker_sandbox_applied"
    assert result.steps[6].status is StepStatus.COMPLETED
    assert result.success is True
    assert late.docker_checks == 1
    assert late.build_calls == 1
    assert _set_events(environment.openclaw) == sets_after_first
    assert load_deploy_state(request.data_root) == prior_state


def test_step7_requires_operator_approval_and_records_exact_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the apply lane is enabled but sandbox_apply was never approved.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()
    request = _request(tmp_path)

    # When: step 7 reaches the approval gate.
    result = environment.wizard().run(request)

    # Then: the step fails with the exact per-agent write plan recorded and
    # zero writes performed.
    step = result.steps[6]
    assert step.status is StepStatus.FAILED
    assert step.action == "sandbox_approval_required"
    assert "systemctl" not in step.message
    report = step.sandbox_report
    assert report is not None
    assert report.image == _tag()
    assert report.rolled_back is False
    planned = {record.key: record.after for record in report.plan}
    prefix = "agents.list[1]"
    assert planned == {
        f"{prefix}.sandbox.mode": "all",
        f"{prefix}.sandbox.workspaceAccess": "none",
        f"{prefix}.sandbox.docker.image": _tag(),
        f"{prefix}.sandbox.docker.binds": [
            f"{tmp_path / 'weather'}:/workspace:ro",
            f"{tmp_path / 'data' / 'backtest-weather'}:/data:rw",
        ],
        f"{prefix}.sandbox.docker.readOnlyRoot": True,
        f"{prefix}.sandbox.docker.network": "none",
        f"{prefix}.sandbox.docker.user": "1000:1000",
        f"{prefix}.sandbox.docker.capDrop": ["ALL"],
        f"{prefix}.sandbox.docker.dangerouslyAllowExternalBindSources": True,
        f"{prefix}.sandbox.docker.dangerouslyAllowReservedContainerTargets": True,
    }
    assert {record.agent_id for record in report.plan} == {"weather"}
    assert {record.action for record in report.plan} == {"set"}
    assert not _set_events(environment.openclaw)
    assert load_deploy_state(request.data_root) is None


def test_step7_applies_byte_exact_posture_and_persists_fingerprint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the fully-approved apply lane against a fresh target.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)

    # When: the full deploy workflow runs.
    result = environment.wizard().run(request)

    # Then: the deployed-shape bracket grammar carried exactly the emitted
    # object, the re-read matches byte-exactly, and the fingerprint persisted.
    step = result.steps[6]
    assert step.status is StepStatus.COMPLETED
    assert step.action == "docker_sandbox_applied"
    prefix = "agents.list[1]"
    assert _set_events(environment.openclaw) == [
        f"set:{prefix}.sandbox.mode",
        f"set:{prefix}.sandbox.workspaceAccess",
        f"set:{prefix}.sandbox.docker.image",
        f"set:{prefix}.sandbox.docker.binds",
        f"set:{prefix}.sandbox.docker.readOnlyRoot",
        f"set:{prefix}.sandbox.docker.network",
        f"set:{prefix}.sandbox.docker.user",
        f"set:{prefix}.sandbox.docker.capDrop",
        f"set:{prefix}.sandbox.docker.dangerouslyAllowExternalBindSources",
        f"set:{prefix}.sandbox.docker.dangerouslyAllowReservedContainerTargets",
    ]
    assert environment.openclaw.config["weather"]["sandbox"] == {
        "mode": "all",
        "workspaceAccess": "none",
        "docker": {
            "image": _tag(),
            "binds": [
                f"{tmp_path / 'weather'}:/workspace:ro",
                f"{tmp_path / 'data' / 'backtest-weather'}:/data:rw",
            ],
            "readOnlyRoot": True,
            "network": "none",
            "user": "1000:1000",
            "capDrop": ["ALL"],
            "dangerouslyAllowExternalBindSources": True,
            "dangerouslyAllowReservedContainerTargets": True,
        },
    }
    # Ordering proof: the image build happened before ANY config event.
    assert late.config_events_at_build == 0
    assert late.build_calls == 1
    state = load_deploy_state(request.data_root)
    assert state is not None
    target = SandboxTarget(agent_id="weather", workspace=tmp_path / "weather", mode="backtest")
    assert state.step7_docker_fingerprint == step7_docker_fingerprint(request, (target,), _tag())
    assert result.steps[7].status is StepStatus.COMPLETED


def test_step7_image_hash_drift_aborts_before_any_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the build lane reports an image tag that does not match the
    # pinned Dockerfile's deterministic tag.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment(built_tag="traderbot-sandbox:dddddddd")
    request = _approved_request(tmp_path)

    # When: step 7 detects the drift after the build.
    result = environment.wizard().run(request)

    # Then: fail closed with zero writes and a typed remedy.
    assert result.steps[6].action == "sandbox_image_mismatch"
    assert result.steps[6].status is StepStatus.FAILED
    assert not _set_events(environment.openclaw)
    assert load_deploy_state(request.data_root) is None


def test_step7_inventory_unreadable_fails_closed_after_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the live inventory becomes unreadable between preflight (call 1)
    # and the approved step-7 apply (call 2+).
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    environment.openclaw.inventory_budget = 3  # preflight + step-3 verify, no more
    request = _approved_request(tmp_path)

    # When: step 7 cannot resolve bracket indices.
    result = environment.wizard().run(request)

    # Then: the build ran first, zero writes, typed failure.
    assert result.steps[6].action == "sandbox_config_unreadable"
    assert result.steps[6].status is StepStatus.FAILED
    assert late.build_calls == 1
    assert not _set_events(environment.openclaw)
    assert load_deploy_state(request.data_root) is None


def test_step7_write_failure_rolls_back_prior_agents_no_partial_posture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: two targets and a write failure at the second agent's FIRST write.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()
    environment.openclaw.fail_set_keys.add("agents.list[2].sandbox.mode")
    request = _approved_request(tmp_path, _TWO)

    # When: the apply runs weather fully and then fails at world.
    result = environment.wizard().run(request)

    # Then: D8 rollback restores writes 1..K-1 (weather) and aborts; no
    # partial posture remains on either agent, and state was never saved.
    step = result.steps[6]
    assert step.status is StepStatus.FAILED
    assert step.action == "sandbox_write_failed"
    assert "rolled back 2 agent(s)" in step.message
    report = step.sandbox_report
    assert report is not None and report.rolled_back is True
    assert environment.openclaw.config["weather"] == {}
    assert environment.openclaw.config["world"] == {}
    assert load_deploy_state(request.data_root) is None


def test_step7_postcondition_mismatch_rolls_back_every_written_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a re-read at the second agent disagrees with the written object.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()
    environment.openclaw.corrupt_on_read.add("agents.list[2].sandbox")
    request = _approved_request(tmp_path, _TWO)

    # When: both agents were written and the postcondition mismatches at K=2.
    result = environment.wizard().run(request)

    # Then: writes 1..K-1 AND the mismatched agent are restored in reverse
    # order; empty parents are pruned; abort leaves no partial posture.
    step = result.steps[6]
    assert step.status is StepStatus.FAILED
    assert step.action == "sandbox_postcondition_failed"
    report = step.sandbox_report
    assert report is not None and report.rolled_back is True
    rollback = report.rollback
    assert [record.key for record in rollback] == [
        "agents.list[2].sandbox.docker",
        "agents.list[2].sandbox.workspaceAccess",
        "agents.list[2].sandbox.mode",
        "agents.list[2].sandbox",
        "agents.list[1].sandbox.docker",
        "agents.list[1].sandbox.workspaceAccess",
        "agents.list[1].sandbox.mode",
        "agents.list[1].sandbox",
    ]
    assert {record.action for record in rollback} == {"rollback_unset"}
    assert environment.openclaw.config["weather"] == {}
    assert environment.openclaw.config["world"] == {}
    assert load_deploy_state(request.data_root) is None


def test_step7_restores_preexisting_sandbox_values_on_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: weather is ADOPTED with a pre-existing sandbox subtree whose
    # managed keys all differ (extra-key-free so its postcondition can hold).
    _enable_phase5(monkeypatch)
    old_docker = {
        "image": "traderbot-sandbox:old00000",
        "binds": ["/old"],
        "readOnlyRoot": True,
        "network": "none",
        "user": "1000:1000",
        "capDrop": ["ALL"],
        "dangerouslyAllowExternalBindSources": True,
        "dangerouslyAllowReservedContainerTargets": True,
    }
    seed = {"sandbox": {"mode": "off", "workspaceAccess": "rw", "docker": old_docker}}
    openclaw = FakeOpenClaw(
        agents={"main": fake_workspace("main"), "weather": tmp_path / "weather"},
        agent_configs={"weather": seed},
    )
    late = FakePhase678()
    environment = FakeEnvironment(openclaw=openclaw, phase45=FakePhase45(), phase678=late)
    late.openclaw = openclaw
    openclaw.corrupt_on_read.add("agents.list[2].sandbox")  # mismatch at world
    request = _approved_request(tmp_path, _TWO)

    # When: the apply overwrites weather, then aborts at world.
    result = environment.wizard().run(request)

    # Then: D8 SET-restore returned the recorded pre-write VALUES byte-exactly.
    assert result.steps[6].action == "sandbox_postcondition_failed"
    report = result.steps[6].sandbox_report
    assert report is not None
    restores = {
        record.key: record.after for record in report.rollback if record.action == "rollback_set"
    }
    assert restores == {
        "agents.list[1].sandbox.docker": old_docker,
        "agents.list[1].sandbox.workspaceAccess": "rw",
        "agents.list[1].sandbox.mode": "off",
    }
    assert openclaw.config["weather"] == seed  # absence/presence + values preserved
    assert openclaw.config["world"] == {}


def test_step7_rollback_failure_surfaces_rollback_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an induced mismatch whose rollback unset itself fails.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()
    environment.openclaw.corrupt_on_read.add("agents.list[1].sandbox")
    environment.openclaw.fail_unset_keys.add("agents.list[1].sandbox.docker")
    request = _approved_request(tmp_path)

    # When: the single-agent apply mismatches and the restore fails.
    result = environment.wizard().run(request)

    # Then: the typed action escalates and names the unrestored key.
    step = result.steps[6]
    assert step.action == "sandbox_rollback_failed"
    assert "ROLLBACK INCOMPLETE" in step.message
    assert "agents.list[1].sandbox.docker" in step.message


def test_step7_never_writes_main_or_sysadmin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a live inventory that also contains a sysadmin agent.
    _enable_phase5(monkeypatch)
    openclaw = FakeOpenClaw(
        agents={
            "main": fake_workspace("main"),
            "sysadmin": fake_workspace("sysadmin"),
        }
    )
    late = FakePhase678()
    environment = FakeEnvironment(openclaw=openclaw, phase45=FakePhase45(), phase678=late)
    late.openclaw = openclaw
    request = _approved_request(tmp_path)

    # When: the apply completes for the selected category agents.
    result = environment.wizard().run(request)

    # Then: weather (created at index 3 AFTER the seeded main/sysadmin) was
    # written; main and sysadmin have no sandbox writes and no sandbox keys.
    assert result.steps[6].action == "docker_sandbox_applied"
    written_agents: set[str] = set()
    for event in _set_events(openclaw):
        target = openclaw._list_target(event.split(":", 1)[1])  # noqa: SLF001
        assert target is not None, event
        written_agents.add(target[0])
    assert written_agents == {"weather"}
    assert openclaw.config["main"] == {}
    assert openclaw.config["sysadmin"] == {}


def test_step7_dev_liaison_adopted_gets_paper_data_dir_and_selected_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an adopted dev-liaison (GAP-13) alongside the selected category.
    _enable_phase5(monkeypatch)
    openclaw = FakeOpenClaw(
        agents={
            "main": fake_workspace("main"),
            "weather": tmp_path / "weather",
            "dev-liaison": tmp_path / "dev-liaison",
        }
    )
    late = FakePhase678()
    environment = FakeEnvironment(openclaw=openclaw, phase45=FakePhase45(), phase678=late)
    late.openclaw = openclaw
    request = _approved_request(tmp_path)

    # When: the apply and verification run.
    result = environment.wizard().run(request)

    # Then: dev-liaison's posture uses the paper ladder data dir, the
    # fingerprint covers both targets, and step 8 received the selected set.
    assert result.steps[6].action == "docker_sandbox_applied"
    liaison = openclaw.config["dev-liaison"]["sandbox"]
    assert liaison["docker"]["binds"] == [
        f"{tmp_path / 'dev-liaison'}:/workspace:ro",
        f"{tmp_path / 'data' / 'paper-dev-liaison'}:/data:rw",
    ]
    assert liaison["mode"] == "all"
    state = load_deploy_state(request.data_root)
    assert state is not None
    targets = (
        SandboxTarget("weather", tmp_path / "weather", "backtest"),
        SandboxTarget("dev-liaison", tmp_path / "dev-liaison", "paper"),
    )
    assert state.step7_docker_fingerprint == step7_docker_fingerprint(request, targets, _tag())
    assert late.verification_agents == ("weather", "dev-liaison")
    assert openclaw.config["main"] == {}


def test_backfill_failure_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: backfill preserves committed progress while verification remains healthy.
    _enable_phase5(monkeypatch)
    phase678 = FakePhase678(backfill=BackfillResult(status="partial"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the full deploy workflow runs.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: verification still runs and the workflow remains truthfully nonzero.
    assert result.steps[5].status is StepStatus.PARTIAL
    assert result.steps[5].action == "backfill_partial"
    assert result.steps[7].status is StepStatus.COMPLETED
    assert phase678.calls == [6, 8]
    assert result.success is False


def _check(
    check_id: CheckId,
    status: CheckStatus,
    required: bool,
    action: str,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=status,
        required=required,
        action=action,
        message="contract matrix check",
        elapsed_ms=0,
    )


def test_verification_advisory_divergences_complete_deployment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: verification reports only advisory divergences from preserved posture
    _enable_phase5(monkeypatch)
    advisory = VerificationResult(
        overall=OverallStatus.DEGRADED,
        checks=(
            _check(
                CheckId.DAEMON_RUNTIME,
                CheckStatus.FAIL,
                required=False,
                action="daemon_websocket_inactive",
            ),
            _check(
                CheckId.HEARTBEAT,
                CheckStatus.DEGRADED,
                required=False,
                action="heartbeat_posture_reported",
            ),
        ),
    )
    phase678 = FakePhase678(verification=advisory)
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: deploy reaches the verification graph.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: no required check failed, so the step completes and embeds the
    # divergences it does not own.
    assert result.steps[7].status is StepStatus.COMPLETED
    assert result.steps[7].action == "verification_advisories"
    assert result.deployment_complete is True
    assert result.success is True
    embedded = result.steps[7].verification
    assert embedded is not None
    assert {check.action for check in embedded.checks} == {
        "daemon_websocket_inactive",
        "heartbeat_posture_reported",
    }


def test_verification_required_degraded_check_still_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a required check reports sanctioned degraded state (encrypted
    # fallback selected by step 4) with no required failure anywhere.
    _enable_phase5(monkeypatch)
    degraded = VerificationResult(
        overall=OverallStatus.DEGRADED,
        checks=(
            _check(
                CheckId.INFISICAL,
                CheckStatus.DEGRADED,
                required=True,
                action="encrypted_fallback",
            ),
        ),
    )
    phase678 = FakePhase678(verification=degraded)
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: deploy reaches the verification graph.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: a required degraded state is embedded and visible but no longer
    # deadlocks a deploy that legitimately selected the encrypted fallback.
    assert result.steps[7].status is StepStatus.COMPLETED
    assert result.steps[7].action == "verification_advisories"
    assert result.deployment_complete is True
    assert result.success is True


def test_verification_required_failure_fails_deployment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a required check failed outright.
    _enable_phase5(monkeypatch)
    failed = VerificationResult(
        overall=OverallStatus.FAILED,
        checks=(_check(CheckId.TOKENS, CheckStatus.FAIL, required=True, action="tokens_invalid"),),
    )
    phase678 = FakePhase678(verification=failed)
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the wizard runs.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: any required failure keeps the step and the deployment failed.
    assert result.steps[7].status is StepStatus.FAILED
    assert result.steps[7].action == "verification_failed"
    assert result.deployment_complete is False
    assert result.success is False


def test_step_exceptions_are_isolated_and_redacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: ordinary exceptions occur independently in backfill and verification.
    _enable_phase5(monkeypatch)
    phase678 = FakePhase678()
    phase678.raise_backfill = True
    phase678.raise_verification = True
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the wizard runs every safe independent late step.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: both failures are typed, Step 7 still applies, and canaries are absent.
    assert tuple(step.action for step in result.steps[5:]) == (
        "backfill_exception",
        "docker_sandbox_applied",
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


def test_completed_late_steps_rerun_idempotently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the same selected desired state is deployed twice.
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)

    # When: both convergent runs complete.
    first = environment.wizard().run(request)
    second = environment.wizard().run(request)

    # Then: all steps remain complete without duplicate persistent identities,
    # and step 7 was applied exactly once (verified by the absence of fresh
    # probes/builds/writes on the second run).
    assert first.success is True and second.success is True
    assert late.calls == [6, 8]
    assert late.docker_checks == 1
    assert late.build_calls == 1
    assert environment.tokens.created_count == {"main": 1, "weather": 1}
    assert environment.openclaw.cron_identities == {("traderbot-main-at-5m", "main")}


def test_backfill_invalid_input_marks_deploy_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the embedded backfill boundary rejects its input.
    _enable_phase5(monkeypatch)
    phase678 = FakePhase678(backfill=BackfillResult(status="invalid_input"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the wizard records Step 6.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: deploy preserves the typed result and classifies the request invalid.
    assert result.input_valid is False
    assert result.steps[5].action == "backfill_invalid_input"
    assert result.steps[7].status is StepStatus.SKIPPED


def test_partial_rerun_executes_only_incomplete_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: Step 6 is partial while Steps 7 and 8 complete.
    _enable_phase5(monkeypatch)
    phase678 = FakePhase678(backfill=BackfillResult(status="partial"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    phase678.openclaw = environment.openclaw
    request = _approved_request(tmp_path)
    _ = environment.wizard().run(request)
    phase678.backfill = BackfillResult(status="complete")

    # When: unchanged desired state reruns.
    result = environment.wizard().run(request)

    # Then: only incomplete Step 6 executes again.
    assert result.success is True
    assert phase678.calls == [6, 8, 6]


def test_changed_backfill_config_invalidates_step6_and_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: all late steps completed for a six-month request.
    _enable_phase5(monkeypatch)
    phase678 = FakePhase678()
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)
    request = _approved_request(tmp_path)
    _ = environment.wizard().run(request)

    # When: only the historical window changes.
    changed = request.model_copy(update={"months_backfill": 7})
    _ = environment.wizard().run(changed)

    # Then: backfill and downstream verification rerun while the step-7
    # posture fingerprint (image + mounts, months-independent) is reused.
    assert phase678.calls == [6, 8, 6, 8]
    assert late_config_writes_once(environment.openclaw)


def late_config_writes_once(openclaw: object) -> bool:
    from tests.deploy_wizard_fakes import FakeOpenClaw as _Fake

    assert isinstance(openclaw, _Fake)
    return len(_set_events(openclaw)) == 10


def test_deleted_completed_one_shot_is_not_recreated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a completed deployment recorded bootstrap registration, then the
    # canonical one-shot ran and was reaped (deleteAfterRun absence).
    _enable_phase5(monkeypatch)
    environment, late = _sandbox_environment()
    request = _approved_request(tmp_path)
    _ = environment.wizard().run(request)
    environment.openclaw.cron_identities.clear()
    environment.openclaw.bootstrap_state = BootstrapCronState.MISSING

    # When: the post-execution deployment is inspected again.
    result = environment.wizard().run(request)

    # Then: the completed-absent bootstrap is retained (no recreation) and the
    # step-7 docker posture is reused byte-exactly (no rebuild, no rewrite).
    assert result.steps[2].status is StepStatus.COMPLETED
    assert environment.openclaw.cron_identities == set()
    assert result.steps[6].action == "docker_sandbox_applied"
    assert result.steps[6].status is StepStatus.COMPLETED
    assert late.build_calls == 1


def test_completed_retained_bootstrap_completes_docker_sandbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: Gateway retains a completed canonical one-shot.
    _enable_phase5(monkeypatch)
    environment, _ = _sandbox_environment()
    environment.openclaw.bootstrap_state = BootstrapCronState.COMPLETED_RETAINED

    # When: deployment reconciles the lifecycle.
    result = environment.wizard().run(_approved_request(tmp_path))

    # Then: no recreation occurs and step 7 applies its real posture.
    assert result.steps[6].status is StepStatus.COMPLETED
    assert result.steps[6].action == "docker_sandbox_applied"
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
