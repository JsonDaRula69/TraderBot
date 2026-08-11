from __future__ import annotations

from pathlib import Path

from tests.deploy_safety_fakes import SafetyEnvironment
from traderbot.deploy.wizard import DeployWizard, WizardRequest
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.models import MarketCategory


def test_approved_setup_restarts_complete_preflight_without_adding_main(tmp_path: Path) -> None:
    # Given: installed OpenClaw lacks main and approved setup will create it
    environment = SafetyEnvironment({})
    environment.openclaw.setup_workspace = tmp_path / "main"
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
        approvals=DeployApprovals(setup_openclaw=True, create_agents=True),
    )

    # When: prerequisite setup completes and transaction preflight restarts
    result = DeployWizard(environment.ports()).run(request)

    # Then: setup occurs once, inventory is reread, and main never reaches agents add
    assert result.success is True
    assert environment.openclaw.events.count("setup") == 1
    assert environment.openclaw.events.count("read:agents") >= 3
    assert "create:main" not in environment.openclaw.events


def test_absent_openclaw_requires_install_approval(tmp_path: Path) -> None:
    # Given: OpenClaw is absent and installation is not approved
    environment = SafetyEnvironment({})
    environment.openclaw.installed = False
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
        approvals=DeployApprovals(create_agents=True),
    )

    # When: deployment reaches the prerequisite gate
    result = DeployWizard(environment.ports()).run(request)

    # Then: no install, setup, agent, config, token, injection, or cron mutation occurs
    assert result.success is False
    assert environment.mutations == ()


def test_user_heartbeat_is_preserved_when_desired_state_is_preserve(tmp_path: Path) -> None:
    # Given: existing main and weather have heterogeneous user heartbeat cadences
    environment = SafetyEnvironment(
        {"main": tmp_path / "main", "weather": tmp_path / "weather"}
    )
    environment.openclaw.heartbeats = {"main": "30m", "weather": "2h"}
    environment.make_exact("main", "weather")
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        heartbeat_every="preserve",
    )

    # When: selected state is reconciled without a heartbeat change request
    result = DeployWizard(environment.ports()).run(request)

    # Then: both values remain unchanged and no heartbeat write occurs
    assert result.success is True
    assert environment.openclaw.heartbeats == {"main": "30m", "weather": "2h"}
    assert not any(event.startswith("heartbeat:") for event in environment.mutations)
