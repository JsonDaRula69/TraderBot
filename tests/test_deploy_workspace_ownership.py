from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.deploy_safety_fakes import SafetyEnvironment
from traderbot.deploy.wizard import DeployWizard, WizardRequest
from traderbot.deploy.wizard_preflight import resolve_agent_targets
from traderbot.deploy.wizard_state import (
    DeployApprovals,
    DeploymentPreflightError,
    PreflightErrorCode,
)
from traderbot.kalshi.order_models import MarketCategory


def test_samefile_alias_across_agent_ids_fails_global_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: distinct lexical roots that the filesystem identifies as one directory
    main = tmp_path / "main"
    weather = tmp_path / "weather"
    main.mkdir()
    weather.mkdir()
    original = os.path.samefile

    def samefile(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
        if {Path(left), Path(right)} == {main, weather}:
            return True
        return original(left, right)

    monkeypatch.setattr(os.path, "samefile", samefile)
    environment = SafetyEnvironment({"main": main, "weather": weather})

    # When: all configured workspace identities are compared
    result = DeployWizard(environment.ports()).run(
        WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest")
    )

    # Then: alias ownership fails before any selected mutation
    assert result.success is False
    assert environment.mutations == ()


@pytest.mark.parametrize("main_first", [True, False])
def test_global_preflight_accepts_main_container(tmp_path: Path, main_first: bool) -> None:
    # Given: selected and unselected agents occupy distinct children of main
    main = tmp_path / "workspace"
    agents = {"main": main, "dev-liaison": main / "dev-liaison", "weather": main / "weather"}
    environment = SafetyEnvironment(agents if main_first else dict(reversed(agents.items())))
    # When: ownership is checked across the complete inventory
    result = DeployWizard(environment.ports()).run(
        WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest")
    )

    # Then: canonical nesting reaches successful deployment past global preflight
    assert result.success is True


@pytest.mark.parametrize("weather_exists", [True, False])
def test_resolve_targets_accepts_main_container(tmp_path: Path, weather_exists: bool) -> None:
    # Given: an existing or explicitly approved new weather child of main
    main = tmp_path / "workspace"
    weather = main / "weather"
    agents = {"main": main, "dev-liaison": main / "dev-liaison"}
    if weather_exists:
        agents["weather"] = weather
    inventory = SafetyEnvironment(agents).openclaw.inventory_agents()
    assert inventory is not None
    request = WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: weather},
        approvals=DeployApprovals(create_agents=True),
    )

    # When: configured-owner and selected-target checks run
    targets = resolve_agent_targets(request, inventory)

    # Then: inventory main and its selected child are resolved unchanged
    assert tuple((target.agent_id, target.workspace, target.existed) for target in targets) == (
        ("main", main, True),
        ("weather", weather, weather_exists),
    )


@pytest.mark.parametrize("crypto_exists", [True, False])
@pytest.mark.parametrize("ancestor_id", ["main", "weather"])
def test_same_workspace_fails_when_nested_or_equal(
    tmp_path: Path, crypto_exists: bool, ancestor_id: str
) -> None:
    # Given: a different owner already owns the requested category's exact root
    main = tmp_path / "workspace"
    shared = main if ancestor_id == "main" else main / "weather"
    agents = {"main": main, ancestor_id: shared}
    if crypto_exists:
        agents["crypto"] = shared
    inventory = SafetyEnvironment(agents).openclaw.inventory_agents()
    assert inventory is not None
    request = WizardRequest(
        categories=(MarketCategory.CRYPTO,),
        mode="backtest",
        category_workspaces={MarketCategory.CRYPTO: shared},
        approvals=DeployApprovals(create_agents=True),
    )

    # When: configured or proposed ownership is compared
    with pytest.raises(DeploymentPreflightError) as caught:
        _ = resolve_agent_targets(request, inventory)

    # Then: main-container permission never permits equality
    assert caught.value.code is PreflightErrorCode.WORKSPACE_OWNERSHIP


@pytest.mark.parametrize("existing_ids", [("weather", "crypto"), ("weather",), ()])
def test_non_main_containment_fails(tmp_path: Path, existing_ids: tuple[str, ...]) -> None:
    # Given: crypto is nested under weather, even though both are under main
    main = tmp_path / "workspace"
    weather = main / "weather"
    crypto = weather / "crypto"
    agents = {"main": main}
    agents.update((agent_id, main / agent_id) for agent_id in existing_ids)
    if "crypto" in existing_ids:
        agents["crypto"] = crypto
    inventory = SafetyEnvironment(agents).openclaw.inventory_agents()
    assert inventory is not None
    request = WizardRequest(
        categories=(MarketCategory.WEATHER, MarketCategory.CRYPTO),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: weather, MarketCategory.CRYPTO: crypto},
        approvals=DeployApprovals(create_agents=True),
    )

    # When: global, configured-owner, or selected-target checks encounter containment
    with pytest.raises(DeploymentPreflightError) as caught:
        _ = resolve_agent_targets(request, inventory)

    # Then: non-main containers remain forbidden
    assert caught.value.code is PreflightErrorCode.WORKSPACE_OWNERSHIP


@pytest.mark.parametrize("alias_main", [True, False])
def test_symlink_alias_accepts_distinct_child_of_main(tmp_path: Path, alias_main: bool) -> None:
    # Given: either main or its child has a symlink alias
    root = tmp_path / "workspace"
    child = root / "weather"
    child.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(root if alias_main else child, target_is_directory=True)
    main = alias if alias_main else root
    weather = child if alias_main else alias
    inventory = SafetyEnvironment({"weather": weather, "main": main}).openclaw.inventory_agents()
    assert inventory is not None

    # When: ownership comparison resolves symlink containment before selection
    targets = resolve_agent_targets(
        WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest"), inventory
    )

    # Then: distinct ownership is permitted without rewriting inventory paths
    assert tuple(target.workspace for target in targets) == (main, weather)


@pytest.mark.parametrize("alias_owner", ["main", "weather"])
def test_unselected_symlink_alias_fails_global_preflight(tmp_path: Path, alias_owner: str) -> None:
    # Given: an unselected agent aliases main or weather's exact filesystem root
    main = tmp_path / "workspace"
    weather = main / "weather"
    weather.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(main if alias_owner == "main" else weather, target_is_directory=True)
    inventory = SafetyEnvironment(
        {"main": main, "weather": weather, "dev-liaison": alias}
    ).openclaw.inventory_agents()
    assert inventory is not None

    # When: only main and weather are selected
    with pytest.raises(DeploymentPreflightError) as caught:
        _ = resolve_agent_targets(
            WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest"), inventory
        )

    # Then: unselected same-workspace aliases still block preflight
    assert caught.value.code is PreflightErrorCode.WORKSPACE_OWNERSHIP


def test_raw_samefile_alias_overrides_main_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: raw aliased roots share identity despite distinct resolved ancestor paths
    main = tmp_path / "workspace"
    weather = main / "weather"
    weather.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(main, target_is_directory=True)
    original = os.path.samefile

    def samefile(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
        return {Path(left), Path(right)} == {alias, weather} or original(left, right)

    monkeypatch.setattr(os.path, "samefile", samefile)
    inventory = SafetyEnvironment({"main": alias, "weather": weather}).openclaw.inventory_agents()
    assert inventory is not None

    # When: containment would otherwise permit the main container
    with pytest.raises(DeploymentPreflightError) as caught:
        _ = resolve_agent_targets(
            WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest"), inventory
        )

    # Then: raw filesystem identity always wins over the allowance
    assert caught.value.code is PreflightErrorCode.WORKSPACE_OWNERSHIP


def test_main_descendant_of_non_main_fails(tmp_path: Path) -> None:
    # Given: a non-main agent is the container, not main
    weather = tmp_path / "workspace"
    main = weather / "main"
    inventory = SafetyEnvironment({"main": main, "weather": weather}).openclaw.inventory_agents()
    assert inventory is not None

    # When: both agents are selected
    with pytest.raises(DeploymentPreflightError) as caught:
        _ = resolve_agent_targets(
            WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest"), inventory
        )

    # Then: the ancestor's identity, not mere main membership, controls permission
    assert caught.value.code is PreflightErrorCode.WORKSPACE_OWNERSHIP
