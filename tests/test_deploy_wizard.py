from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError
from rich.console import Console

from tests.deploy_wizard_fakes import (
    FakeEnvironment,
    FakeOpenClaw,
    FakePhase45,
    FakePhase678,
    FakeTokens,
    fake_workspace,
)
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.wizard import DeployResult, StepStatus, WizardRequest
from traderbot.deploy.wizard_command import collect_interactive_request, execute_deploy
from traderbot.deploy.wizard_late_steps import PHASE5_SANDBOX_ENV
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.order_models import MarketCategory


def _request(
    tmp_path: Path,
    *categories: MarketCategory,
    approvals: DeployApprovals | None = None,
) -> WizardRequest:
    return WizardRequest(
        categories=categories,
        mode="backtest",
        sysadmin_workspace=None,
        category_workspaces={category: tmp_path / category.value for category in categories},
        approvals=approvals or DeployApprovals(create_agents=True),
        data_root=tmp_path / "data",
    )


def _assert_failed_at(result: DeployResult, step: int) -> None:
    assert result.success is False
    assert result.steps[step - 1].status is StepStatus.FAILED
    assert all(item.status is StepStatus.SKIPPED for item in result.steps[step:])


def test_steps_1_3_create_agents(tmp_path: Path) -> None:
    # Given: two explicitly selected categories and isolated workspaces
    environment = FakeEnvironment()
    request = _request(tmp_path, MarketCategory.WEATHER, MarketCategory.CRYPTO)

    # When: steps 1 through 3 run twice
    first = environment.wizard().run(request)
    second = environment.wizard().run(request)

    # Then: only selected agents exist and every persistent identity is singular
    assert first.success is True and second.success is True
    assert environment.openclaw.created_agents == {"weather", "crypto"}
    assert environment.openclaw.secret_refs == {
        "main": "main_token",
        "weather": "weather_token",
        "crypto": "crypto_token",
    }
    assert environment.openclaw.cron_identities == {("traderbot-main-at-5m", "main")}
    assert environment.tokens.created_count == {"main": 1, "weather": 1, "crypto": 1}
    assert set(environment.tokens.profiles) == {"main", "weather", "crypto"}
    assert "token" not in first.model_dump_json().lower()


def test_steps_4_5_advance_result_and_leave_steps_6_8(tmp_path: Path) -> None:
    # Given: steps 1-3 and both new deployment adapters succeed.
    phase45 = FakePhase45()
    environment = FakeEnvironment(phase45=phase45)

    # When: the complete implemented wizard prefix runs.
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

    # Then: the result advances through step 5 without claiming full deployment.
    assert result.success is True
    assert result.completed_steps == (1, 2, 3, 4, 5)
    assert result.remaining_steps == (6, 7, 8)
    assert result.deployment_complete is False
    assert phase45.calls == [4, 5]


def test_steps_6_8_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: every composed deploy dependency succeeds and the apply lane is on.
    monkeypatch.setenv(PHASE5_SANDBOX_ENV, "1")
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: the full wizard runs.
    result = environment.wizard().run(
        _request(
            tmp_path,
            MarketCategory.WEATHER,
            approvals=DeployApprovals(create_agents=True, sandbox_apply=True),
        )
    )

    # Then: all eight stable step identifiers complete.
    assert result.completed_steps == tuple(range(1, 9))


def test_backfill_failure_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: backfill commits partial progress and the apply lane is on.
    monkeypatch.setenv(PHASE5_SANDBOX_ENV, "1")
    phase678 = FakePhase678(backfill=BackfillResult(status="partial"))
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=phase678)

    # When: the full wizard runs.
    result = environment.wizard().run(
        _request(
            tmp_path,
            MarketCategory.WEATHER,
            approvals=DeployApprovals(create_agents=True, sandbox_apply=True),
        )
    )

    # Then: Step 6 is partial and independent verification still completes.
    assert result.steps[5].status is StepStatus.PARTIAL
    assert result.steps[7].status is StepStatus.COMPLETED


def test_step_4_failure_skips_step_5(tmp_path: Path) -> None:
    # Given: steps 1-3 succeed but secure secret provisioning fails.
    phase45 = FakePhase45(fail_step=4)
    environment = FakeEnvironment(phase45=phase45)

    # When: deployment reaches step 4.
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

    # Then: step 5 is explicitly skipped and no database adapter call occurs.
    assert result.success is False
    assert result.steps[3].status is StepStatus.FAILED
    assert result.steps[4].status is StepStatus.SKIPPED
    assert phase45.calls == [4]


def test_openclaw_not_installed(tmp_path: Path) -> None:
    # Given: OpenClaw is absent and installation cannot complete
    environment = FakeEnvironment(openclaw=FakeOpenClaw(installed=False, install_succeeds=False))

    # When: deployment starts
    result = environment.wizard().run(
        _request(
            tmp_path,
            MarketCategory.WEATHER,
            approvals=DeployApprovals(install_openclaw=True, create_agents=True),
        )
    )

    # Then: step 1 fails actionably and no later external state is touched
    _assert_failed_at(result, 1)
    assert "install" in result.steps[0].message.lower()
    assert environment.openclaw.created_agents == set()
    assert environment.tokens.profiles == {}
    assert environment.injector.injected == set()


@pytest.mark.parametrize("failure", ["setup", "gateway"])
def test_step_1_failure_stops_later_mutation(tmp_path: Path, failure: str) -> None:
    # Given: one baseline OpenClaw operation fails
    openclaw = FakeOpenClaw(
        setup_succeeds=failure != "setup",
        gateway_succeeds=failure != "gateway",
        agents={} if failure == "setup" else {"main": fake_workspace("main")},
    )
    environment = FakeEnvironment(openclaw=openclaw)

    # When: deployment starts
    result = environment.wizard().run(
        _request(
            tmp_path,
            MarketCategory.WEATHER,
            approvals=DeployApprovals(
                setup_openclaw=failure == "setup",
                create_agents=True,
            ),
        )
    )

    # Then: no SysAdmin or category mutation follows the failure
    _assert_failed_at(result, 1)
    assert environment.tokens.profiles == {}
    assert environment.injector.injected == set()


def test_storage_failure_reports_partial_without_category_mutation(tmp_path: Path) -> None:
    # Given: encrypted SysAdmin token metadata cannot be inspected safely
    environment = FakeEnvironment(tokens=FakeTokens(fail_for={"main"}))

    # When: deployment runs
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

    # Then: global preflight reports failure before workspace or category mutation
    _assert_failed_at(result, 1)
    assert environment.openclaw.created_agents == set()
    assert environment.openclaw.secret_refs == {}
    assert environment.injector.injected == set()


def test_partial_category_rerun_reuses_tokens_and_heals_mapping(tmp_path: Path) -> None:
    # Given: the crypto SecretRef write fails after its token is persisted
    environment = FakeEnvironment()
    environment.openclaw.fail_secret_ref_for.add("crypto")
    request = _request(tmp_path, MarketCategory.WEATHER, MarketCategory.CRYPTO)

    # When: a first partial run is followed by a healthy rerun
    first = environment.wizard().run(request)
    environment.openclaw.fail_secret_ref_for.clear()
    second = environment.wizard().run(request)

    # Then: the rerun heals config without rotating identities or duplicating resources
    assert first.success is False and first.steps[2].status is StepStatus.FAILED
    assert second.success is True
    assert environment.tokens.created_count == {"main": 1, "weather": 1, "crypto": 1}
    assert environment.openclaw.cron_identities == {("traderbot-main-at-5m", "main")}
    assert environment.openclaw.secret_refs["crypto"] == "crypto_token"


def test_deploy_never_invokes_doctor(tmp_path: Path) -> None:
    # Given: provisioning works and the adapter raises if doctor is invoked
    environment = FakeEnvironment()

    # When: deployment runs
    result = environment.wizard().run(_request(tmp_path, MarketCategory.SPORTS))

    # Then: step 3 succeeds without crossing the forbidden doctor boundary
    assert result.success is True
    assert result.steps[2].status is StepStatus.COMPLETED
    assert result.steps[2].agents[0].agent_id == "sports"
    assert environment.openclaw.created_agents == {"sports"}


@pytest.mark.parametrize(
    "categories",
    [(), (MarketCategory.WEATHER, MarketCategory.WEATHER)],
)
def test_invalid_selection_is_rejected_before_mutation(
    tmp_path: Path,
    categories: tuple[MarketCategory, ...],
) -> None:
    # Given: an empty or duplicate category selection
    environment = FakeEnvironment()

    # When/Then: the request boundary rejects it before orchestration can run
    with pytest.raises(ValidationError):
        request = _request(tmp_path, *categories)
        _ = environment.wizard().run(request)
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.injected == set()


def test_missing_selected_workspace_is_rejected_before_mutation() -> None:
    # Given: a selected category without its explicit workspace
    environment = FakeEnvironment()

    # When: global preflight sees no approved path for the missing selected agent
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={},
        approvals=DeployApprovals(create_agents=True),
    )
    result = environment.wizard().run(request)

    # Then: it fails before mutation
    _assert_failed_at(result, 1)
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.injected == set()


def test_config_mode_performs_no_prompts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a complete deploy document and prompt execution forbidden
    environment = FakeEnvironment()
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "category_workspaces": {"weather": str(tmp_path / "weather")},
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": True,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        ),
        encoding="utf-8",
    )

    # When: the machine-readable config path executes
    with mock.patch("traderbot.deploy.wizard_command.Prompt.ask", side_effect=AssertionError):
        code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: one deterministic JSON document reports success without prompting
    output = capsys.readouterr()
    assert code == 0
    assert json.loads(output.out)["success"] is True
    assert output.err == ""


def test_malformed_config_fails_before_external_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: malformed deploy JSON and a stateful external fake
    environment = FakeEnvironment()
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text("{not-json", encoding="utf-8")

    # When: config mode parses the trust boundary
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: it exits with usage failure and performs no external mutation
    output = capsys.readouterr()
    assert code == 2
    assert json.loads(output.out) == {"error": "invalid_request"}
    assert output.err == ""
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.injected == set()


def test_interactive_selection_is_explicit_and_ordered(tmp_path: Path) -> None:
    # Given: explicit Rich answers in reverse category order
    answers = iter(
        [
            "crypto, weather",
            str(tmp_path / "weather"),
            str(tmp_path / "crypto"),
        ]
    )
    console = Console(file=mock.Mock(), force_terminal=False)

    # When: the interactive presenter collects the selection
    environment = FakeEnvironment()
    with (
        mock.patch("traderbot.deploy.wizard_command.Prompt.ask", side_effect=answers),
        mock.patch(
            "traderbot.deploy.wizard_command.Confirm.ask",
            side_effect=[True, False, False, False],
        ),
    ):
        request = collect_interactive_request(console, environment.ports())

    # Then: domain order is deterministic and every workspace was explicitly supplied
    assert request.categories == (MarketCategory.WEATHER, MarketCategory.CRYPTO)
    assert request.sysadmin_workspace is None
    assert request.category_workspaces == {
        MarketCategory.WEATHER: tmp_path / "weather",
        MarketCategory.CRYPTO: tmp_path / "crypto",
    }
