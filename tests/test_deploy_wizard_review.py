from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, final
from unittest import mock

import pytest
from pydantic import ValidationError

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.wizard import (
    DeployWizard,
    TokenProvisionResult,
    WizardPorts,
    WizardRequest,
)
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.injection import WorkspaceTemplate
from traderbot.profiles.models import TradingProfile


@final
class RecordingOpenClaw:
    def __init__(self, *, cron_succeeds: bool = True) -> None:
        self.setup_calls = 0
        self.created_agents: list[tuple[str, Path]] = []
        self.cron_succeeds = cron_succeeds

    def detect(self) -> str | None:
        return "/fake/openclaw"

    def install(self) -> bool:
        raise AssertionError

    def setup(self) -> bool:
        self.setup_calls += 1
        return True

    def gateway_status(self) -> bool:
        return True

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        self.created_agents.append((agent_id, workspace))
        return True

    def configure_secret_ref(self, agent_id: str, secret_id: str) -> bool:
        _ = agent_id, secret_id
        return True

    def ensure_bootstrap_cron(self) -> bool:
        return self.cron_succeeds

    def doctor(self) -> bool:
        return True


@final
class RecordingTokens:
    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        _ = profile
        return TokenProvisionResult.created(agent_id)


@final
class RecordingInjector:
    def __init__(self) -> None:
        self.workspaces: list[Path] = []

    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str:
        _ = template
        self.workspaces.append(workspace)
        return "manifest"


@final
class RecordingEnvironment:
    def __init__(self, *, cron_succeeds: bool = True) -> None:
        self.openclaw = RecordingOpenClaw(cron_succeeds=cron_succeeds)
        self.tokens = RecordingTokens()
        self.injector = RecordingInjector()

    def ports(self) -> WizardPorts:
        return WizardPorts(self.openclaw, self.tokens, self.injector)


def _documented_payload(
    mode: str = "backtest",
) -> dict[str, str | int | list[str] | dict[str, str]]:
    return {
        "categories": ["weather"],
        "mode": mode,
        "infisical_url": "http://localhost:8080",
        "kalshi_environment": "production",
        "tokens": {
            "kalshi_api_key": "example-key",
            "kalshi_private_key_pem": "example-pem",
        },
        "months_backfill": 6,
    }


def test_documented_todo1_config_derives_isolated_home_without_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: exactly the Todo-1 JSON keys and an isolated invocation HOME
    home = tmp_path / "home"
    data_dir = tmp_path / "data"
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(_documented_payload()), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_dir))
    environment = RecordingEnvironment()

    # When: config mode executes with prompts forbidden
    with mock.patch("traderbot.deploy.wizard_command.Prompt.ask", side_effect=AssertionError):
        code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: standard current OpenClaw paths reach orchestration inside isolated HOME
    output = capsys.readouterr()
    assert code == 0
    assert output.err == ""
    assert environment.injector.workspaces == [
        home / ".openclaw" / "workspace",
        home / ".openclaw" / "workspace-weather",
    ]
    assert environment.openclaw.created_agents == [
        ("weather", home / ".openclaw" / "workspace-weather")
    ]
    assert data_dir.exists() is False


def test_partial_workspace_override_preserves_explicit_path_and_derives_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: only the optional SysAdmin workspace extension is explicit
    home = tmp_path / "home"
    explicit_main = tmp_path / "explicit-main"
    config = _documented_payload()
    config["sysadmin_workspace"] = str(explicit_main)
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    environment = RecordingEnvironment()

    # When: config mode resolves selected workspace paths
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: the override is preserved and only the missing category path is derived
    _ = capsys.readouterr()
    assert code == 0
    assert environment.injector.workspaces == [
        explicit_main,
        home / ".openclaw" / "workspace-weather",
    ]


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_lifecycle_mode_fails_actionably_before_mutation(
    mode: Literal["paper", "live"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a later-lifecycle mode in an otherwise documented config
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(_documented_payload(mode)), encoding="utf-8")
    environment = RecordingEnvironment()

    # When: the config crosses the CLI boundary
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: Phase-7 guidance is returned before external or filesystem mutation
    output = capsys.readouterr()
    assert code == 2
    assert "Phase 7 lifecycle" in output.err
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.workspaces == []


def test_deploy_config_schema_is_backtest_only() -> None:
    # Given/When: the public deploy schema is generated
    schema_json = json.dumps(DeployConfig.model_json_schema(), sort_keys=True)

    # Then: it advertises only the mode restart resolution supports
    assert '"const": "backtest"' in schema_json
    assert '"paper"' not in schema_json
    assert '"live"' not in schema_json
    for mode in ("paper", "live"):
        with pytest.raises(ValidationError, match="Phase 7 lifecycle"):
            _ = DeployConfig.model_validate(_documented_payload(mode))


def test_success_result_reports_partial_eight_step_deployment(tmp_path: Path) -> None:
    # Given: valid isolated workspaces and successful step adapters
    environment = RecordingEnvironment()
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        sysadmin_workspace=tmp_path / "main",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
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
    environment = RecordingEnvironment(cron_succeeds=False)
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        sysadmin_workspace=tmp_path / "main",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
    )

    # When: the wizard reaches SysAdmin setup
    result = DeployWizard(environment.ports()).run(request)

    # Then: step 2 names the contract conflict and later mutation remains blocked
    assert result.success is False
    assert result.completed_steps == (1,)
    assert "cron contract conflict" in result.steps[1].message
    assert environment.openclaw.created_agents == []


def test_interactive_report_states_full_deployment_is_incomplete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a documented config and successful adapters
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(_documented_payload()), encoding="utf-8")

    # When: human-readable output is requested
    code = execute_deploy(config_path, json_output=False, ports=RecordingEnvironment().ports())

    # Then: the report explicitly distinguishes step success from full deployment
    output = capsys.readouterr()
    assert code == 0
    assert "full deployment remains incomplete" in output.out.lower()
    assert "steps 4-8" in output.out.lower()


def test_linked_workspace_override_fails_before_openclaw_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: explicit workspace overrides routed through a linked path component
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    config = _documented_payload()
    config["sysadmin_workspace"] = str(linked / "main")
    config["category_workspaces"] = {"weather": str(linked / "weather")}
    config_path = tmp_path / "deploy.json"
    _ = config_path.write_text(json.dumps(config), encoding="utf-8")
    environment = RecordingEnvironment()

    # When: config mode validates all paths
    code = execute_deploy(config_path, json_output=True, ports=environment.ports())

    # Then: linked paths fail before OpenClaw setup or workspace writes
    _ = capsys.readouterr()
    assert code == 2
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.workspaces == []


def test_deploy_docs_publish_machine_readable_incomplete_state() -> None:
    # Given: user-facing deploy documentation
    docs = (Path(__file__).parents[1] / "docs" / "deploy-wizard.md").read_text()

    # When/Then: its output contract cannot imply the full eight-step deploy completed
    assert "deployment_complete" in docs
    assert "false" in docs
    assert "Steps 4-8 remain" in docs
