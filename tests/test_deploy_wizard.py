from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError
from rich.console import Console

from traderbot.deploy.wizard import (
    DeployResult,
    DeployWizard,
    StepStatus,
    TokenProvisionResult,
    WizardPorts,
    WizardRequest,
)
from traderbot.deploy.wizard_command import collect_interactive_request, execute_deploy
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.injection import WorkspaceTemplate
from traderbot.profiles.models import TradingProfile


@dataclass(slots=True)
class FakeOpenClaw:
    installed: bool = True
    install_succeeds: bool = True
    setup_succeeds: bool = True
    gateway_succeeds: bool = True
    doctor_succeeds: bool = True
    fail_secret_ref_for: set[str] = field(default_factory=set)
    created_agents: set[str] = field(default_factory=set)
    secret_refs: dict[str, str] = field(default_factory=dict)
    cron_identities: set[tuple[str, str]] = field(default_factory=set)
    setup_calls: int = 0
    install_calls: int = 0

    def detect(self) -> str | None:
        return "/fake/openclaw" if self.installed else None

    def install(self) -> bool:
        self.install_calls += 1
        if self.install_succeeds:
            self.installed = True
        return self.install_succeeds

    def setup(self) -> bool:
        self.setup_calls += 1
        return self.setup_succeeds

    def gateway_status(self) -> bool:
        return self.gateway_succeeds

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        _ = workspace
        self.created_agents.add(agent_id)
        return True

    def configure_secret_ref(self, agent_id: str, secret_id: str) -> bool:
        if agent_id in self.fail_secret_ref_for:
            return False
        self.secret_refs[agent_id] = secret_id
        return True

    def ensure_bootstrap_cron(self) -> bool:
        self.cron_identities.add(("traderbot-main-at-5m", "main"))
        return True

    def doctor(self) -> bool:
        return self.doctor_succeeds


@dataclass(slots=True)
class FakeTokens:
    fail_for: set[str] = field(default_factory=set)
    profiles: dict[str, str] = field(default_factory=dict)
    created_count: dict[str, int] = field(default_factory=dict)

    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        if agent_id in self.fail_for:
            return TokenProvisionResult.failed(agent_id, "encrypted token storage failed")
        existing = self.profiles.get(agent_id)
        if existing is not None:
            return TokenProvisionResult.existing(agent_id)
        self.profiles[agent_id] = profile.name
        self.created_count[agent_id] = self.created_count.get(agent_id, 0) + 1
        return TokenProvisionResult.created(agent_id)


@dataclass(slots=True)
class FakeInjector:
    injected: set[tuple[Path, WorkspaceTemplate]] = field(default_factory=set)

    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str:
        self.injected.add((workspace, template))
        return f"manifest-{template.value}"


@dataclass(slots=True)
class FakeEnvironment:
    openclaw: FakeOpenClaw = field(default_factory=FakeOpenClaw)
    tokens: FakeTokens = field(default_factory=FakeTokens)
    injector: FakeInjector = field(default_factory=FakeInjector)

    def ports(self) -> WizardPorts:
        return WizardPorts(self.openclaw, self.tokens, self.injector)

    def wizard(self) -> DeployWizard:
        return DeployWizard(self.ports())


def _request(tmp_path: Path, *categories: MarketCategory) -> WizardRequest:
    return WizardRequest(
        categories=categories,
        mode="backtest",
        sysadmin_workspace=tmp_path / "main",
        category_workspaces={category: tmp_path / category.value for category in categories},
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


def test_openclaw_not_installed(tmp_path: Path) -> None:
    # Given: OpenClaw is absent and installation cannot complete
    environment = FakeEnvironment(openclaw=FakeOpenClaw(installed=False, install_succeeds=False))

    # When: deployment starts
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

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
    )
    environment = FakeEnvironment(openclaw=openclaw)

    # When: deployment starts
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

    # Then: no SysAdmin or category mutation follows the failure
    _assert_failed_at(result, 1)
    assert environment.tokens.profiles == {}
    assert environment.injector.injected == set()


def test_storage_failure_reports_partial_without_category_mutation(tmp_path: Path) -> None:
    # Given: encrypted SysAdmin token storage fails after workspace injection
    environment = FakeEnvironment(tokens=FakeTokens(fail_for={"main"}))

    # When: deployment runs
    result = environment.wizard().run(_request(tmp_path, MarketCategory.WEATHER))

    # Then: step 2 reports failure and step 3 does not create agents
    _assert_failed_at(result, 2)
    assert environment.openclaw.created_agents == set()
    assert environment.openclaw.secret_refs == {}


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


def test_doctor_failure_does_not_claim_success(tmp_path: Path) -> None:
    # Given: provisioning works but read-only doctor rejects the final state
    environment = FakeEnvironment(openclaw=FakeOpenClaw(doctor_succeeds=False))

    # When: deployment runs
    result = environment.wizard().run(_request(tmp_path, MarketCategory.SPORTS))

    # Then: provisioned agent status is retained but step 3 is failed
    assert result.success is False
    assert result.steps[2].status is StepStatus.FAILED
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


def test_missing_selected_workspace_is_rejected_before_mutation(tmp_path: Path) -> None:
    # Given: a selected category without its explicit workspace
    environment = FakeEnvironment()

    # When/Then: the request is invalid before any OpenClaw call
    with pytest.raises(ValidationError):
        request = WizardRequest(
            categories=(MarketCategory.WEATHER,),
            mode="backtest",
            sysadmin_workspace=tmp_path / "main",
            category_workspaces={},
        )
        _ = environment.wizard().run(request)
    assert environment.openclaw.setup_calls == 0


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
                "sysadmin_workspace": str(tmp_path / "main"),
                "category_workspaces": {"weather": str(tmp_path / "weather")},
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
    assert '"success": true' in output.out
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
    assert "invalid deploy config" in output.err
    assert environment.openclaw.setup_calls == 0
    assert environment.injector.injected == set()


def test_interactive_selection_is_explicit_and_ordered(tmp_path: Path) -> None:
    # Given: explicit Rich answers in reverse category order
    answers = iter(
        [
            "crypto, weather",
            str(tmp_path / "main"),
            str(tmp_path / "weather"),
            str(tmp_path / "crypto"),
        ]
    )
    console = Console(file=mock.Mock(), force_terminal=False)

    # When: the interactive presenter collects the selection
    with mock.patch("traderbot.deploy.wizard_command.Prompt.ask", side_effect=answers):
        request = collect_interactive_request(console)

    # Then: domain order is deterministic and every workspace was explicitly supplied
    assert request.categories == (MarketCategory.WEATHER, MarketCategory.CRYPTO)
    assert request.sysadmin_workspace == tmp_path / "main"
    assert request.category_workspaces == {
        MarketCategory.WEATHER: tmp_path / "weather",
        MarketCategory.CRYPTO: tmp_path / "crypto",
    }
