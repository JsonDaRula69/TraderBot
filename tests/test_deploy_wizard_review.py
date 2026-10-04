from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from unittest import mock

import pytest
from pydantic import ValidationError

from tests.deploy_safety_fakes import SafetyEnvironment
from traderbot.deploy.config import DeployConfig
from traderbot.deploy.wizard import (
    DeployWizard,
    WizardRequest,
)
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.deploy.wizard_state import BootstrapCronState
from traderbot.kalshi.order_models import MarketCategory


def _documented_payload(
    workspace: Path,
    mode: str = "backtest",
) -> dict[str, str | int | list[str] | dict[str, str] | dict[str, bool]]:
    return {
        "categories": ["weather"],
        "mode": mode,
        "infisical_url": "http://localhost:8080",
        "tokens": {
            "kalshi_api_key_env": "TEST_KALSHI_KEY",
            "kalshi_private_key_pem_env": "TEST_KALSHI_PEM",
        },
        "months_backfill": 6,
        "category_workspaces": {"weather": str(workspace)},
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": True,
            "heartbeat_change": True,
        },
        "heartbeat_every": "0m",
    }


def test_documented_config_uses_explicit_new_agent_path_without_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: explicit categories, new-agent path, and approvals in isolated config mode
    home = tmp_path / "home"
    data_dir = tmp_path / "data"
    config_path = tmp_path / "deploy.json"
    weather = home / "approved" / "weather"
    _ = config_path.write_text(json.dumps(_documented_payload(weather)), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_dir))
    environment = SafetyEnvironment({"main": home / "existing-main"})

    # When: config mode executes with prompts forbidden
    with mock.patch("traderbot.deploy.wizard_command.Prompt.ask", side_effect=AssertionError):
        code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: only the explicit missing category path is created without prompting
    output = capsys.readouterr()
    assert code == 0
    assert output.err == ""
    assert environment.openclaw.agents["main"] == home / "existing-main"
    assert environment.openclaw.agents["weather"] == weather
    assert environment.openclaw.events.count("create:weather") == 1
    assert data_dir.exists() is False


def test_existing_inventory_workspace_is_reused_without_config_assertion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: selected weather already has an arbitrary nested inventory workspace
    nested = tmp_path / "production" / "heterogeneous" / "weather"
    config = _documented_payload(tmp_path / "unused")
    del config["category_workspaces"]
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": nested})
    environment.make_exact("main", "weather")

    # When: config mode selects the existing agent without asserting a path
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: inventory remains authoritative and no add occurs
    _ = capsys.readouterr()
    assert code == 0
    assert environment.openclaw.agents["weather"] == nested
    assert "create:weather" not in environment.openclaw.events


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_lifecycle_mode_fails_actionably_before_mutation(
    mode: Literal["paper", "live"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a later-lifecycle mode in an otherwise documented config
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(
        json.dumps(_documented_payload(tmp_path / "weather", mode)),
        encoding="utf-8",
    )
    environment = SafetyEnvironment({"main": tmp_path / "main"})

    # When: the config crosses the CLI boundary
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: Phase-7 guidance is returned before external or filesystem mutation
    output = capsys.readouterr()
    assert code == 2
    assert json.loads(output.out) == {"error": "invalid_request"}
    assert output.err == ""
    assert environment.mutations == ()


def test_deploy_config_schema_is_backtest_only() -> None:
    # Given/When: the public deploy schema is generated
    schema_json = json.dumps(DeployConfig.model_json_schema(), sort_keys=True)

    # Then: it advertises only the mode restart resolution supports
    assert '"const": "backtest"' in schema_json
    assert '"paper"' not in schema_json
    assert '"live"' not in schema_json
    for mode in ("paper", "live"):
        with pytest.raises(ValidationError, match="Phase 7 lifecycle"):
            _ = DeployConfig.model_validate(_documented_payload(Path("/tmp/weather"), mode))


def test_success_result_reports_partial_eight_step_deployment(tmp_path: Path) -> None:
    # Given: valid isolated workspaces and successful step adapters
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.make_exact("main", "weather")
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={},
    )

    # When: implemented steps complete successfully
    result = DeployWizard(environment.ports()).run(request)

    # Then: current success stays true without claiming all eight steps are complete
    assert result.success is True
    assert result.completed_steps == (1, 2, 3)
    assert result.deployment_complete is False
    assert result.remaining_steps == (4, 5, 6, 7, 8)


def test_bootstrap_contract_conflict_is_actionable_in_step_result(tmp_path: Path) -> None:
    # Given: cron reconciliation reports a managed contract conflict
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.openclaw.bootstrap_state = BootstrapCronState.CONFLICT
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={},
    )

    # When: global preflight reads the conflicting contract
    result = DeployWizard(environment.ports()).run(request)

    # Then: step 1 reports the conflict and no later mutation occurs
    assert result.success is False
    assert result.completed_steps == ()
    assert "cron" in result.steps[0].message
    assert environment.mutations == ()


def test_interactive_report_states_full_deployment_is_incomplete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a documented config and successful adapters
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(
        json.dumps(_documented_payload(tmp_path / "weather")),
        encoding="utf-8",
    )

    # When: human-readable output is requested
    code = execute_deploy(
        config_path,
        json_output=False,
        ports=SafetyEnvironment({"main": tmp_path / "main"}).ports(),
    )

    # Then: the report explicitly distinguishes step success from full deployment
    output = capsys.readouterr()
    assert code == 0
    assert output.out == ""
    assert "full deployment remains incomplete" in output.err.lower()
    assert "steps 4-8" in output.err.lower()


def test_linked_workspace_override_fails_before_openclaw_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: explicit workspace overrides routed through a linked path component
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    config = _documented_payload(linked / "weather")
    config["sysadmin_workspace"] = str(linked / "main")
    config["category_workspaces"] = {"weather": str(linked / "weather")}
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    environment = SafetyEnvironment({"main": tmp_path / "main"})

    # When: config mode validates all paths
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: linked paths fail before OpenClaw setup or workspace writes
    _ = capsys.readouterr()
    assert code == 2
    assert environment.mutations == ()


def test_deploy_docs_publish_machine_readable_complete_state() -> None:
    # Given: user-facing deploy documentation
    docs = (Path(__file__).parents[1] / "docs" / "deploy-wizard.md").read_text()

    # When/Then: its output contract describes all typed eight-step outcomes.
    assert "deployment_complete" in docs
    assert "eight ordered typed step records" in docs
    assert "Exit 0 requires all eight steps complete" in docs
