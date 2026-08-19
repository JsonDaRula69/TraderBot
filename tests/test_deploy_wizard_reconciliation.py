from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.deploy_safety_fakes import SafetyEnvironment
from traderbot.deploy.wizard import DeployWizard, WizardRequest
from traderbot.deploy.wizard_state import (
    BootstrapCronState,
    DeployApprovals,
    SecretRefConfig,
)
from traderbot.kalshi.models import MarketCategory


def _request(
    categories: tuple[MarketCategory, ...],
    *,
    workspaces: dict[MarketCategory, Path] | None = None,
    main_workspace: Path | None = None,
    approvals: DeployApprovals | None = None,
    heartbeat: str = "preserve",
) -> WizardRequest:
    return WizardRequest.model_validate(
        {
            "categories": categories,
            "mode": "backtest",
            "sysadmin_workspace": main_workspace,
            "category_workspaces": workspaces or {},
            "approvals": approvals or DeployApprovals(),
            "heartbeat_every": heartbeat,
        }
    )


def test_existing_nested_workspace_is_adopted_without_add(tmp_path: Path) -> None:
    # Given: main and selected weather already use arbitrary non-overlapping paths
    main = tmp_path / "roles" / "main"
    weather = tmp_path / "teams" / "forecast" / "agent-home"
    environment = SafetyEnvironment({"main": main, "weather": weather})
    environment.make_exact("main", "weather")

    # When: weather is selected without a workspace assertion
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: inventory is authoritative and no agent is added or rebound
    assert result.success is True
    assert not any(event.startswith("create:") for event in environment.mutations)
    assert f"inject:weather:{weather}" in environment.injector.events


def test_existing_workspace_assertion_mismatch_has_zero_mutation(tmp_path: Path) -> None:
    # Given: selected weather has an inventory path different from the user assertion
    environment = SafetyEnvironment(
        {"main": tmp_path / "main", "weather": tmp_path / "actual-weather"}
    )
    asserted = tmp_path / "asserted-weather"

    # When: global preflight compares the explicit assertion
    result = DeployWizard(environment.ports()).run(
        _request(
            (MarketCategory.WEATHER,),
            workspaces={MarketCategory.WEATHER: asserted},
        )
    )

    # Then: the transaction fails before any user-state mutation
    assert result.success is False
    assert environment.mutations == ()


def test_unselected_agent_receives_no_mutation(tmp_path: Path) -> None:
    # Given: sports exists but only weather is selected
    environment = SafetyEnvironment(
        {
            "main": tmp_path / "main",
            "weather": tmp_path / "weather",
            "sports": tmp_path / "sports",
        }
    )
    environment.make_exact("main", "weather", "sports")

    # When: the selected deployment runs
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: read-only global inventory may see sports but no mutation names it
    assert result.success is True
    assert not any("sports" in event for event in environment.mutations)


def test_overlapping_unselected_workspace_blocks_missing_agent_creation(tmp_path: Path) -> None:
    # Given: an unselected sports workspace owns the parent of proposed crypto
    shared = tmp_path / "shared"
    crypto = shared / "crypto"
    environment = SafetyEnvironment({"main": tmp_path / "main", "sports": shared})

    # When: approved crypto creation enters global ownership preflight
    result = DeployWizard(environment.ports()).run(
        _request(
            (MarketCategory.CRYPTO,),
            workspaces={MarketCategory.CRYPTO: crypto},
            approvals=DeployApprovals(create_agents=True),
        )
    )

    # Then: overlap with an unselected owner fails before creation or filesystem writes
    assert result.success is False
    assert environment.mutations == ()
    assert crypto.exists() is False


def test_equal_workspace_ownership_blocks_preflight(tmp_path: Path) -> None:
    # Given: two configured agents claim exactly one path
    shared = tmp_path / "shared"
    environment = SafetyEnvironment(
        {"main": tmp_path / "main", "weather": shared, "sports": shared}
    )

    # When: the global ownership inventory is checked
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: duplicate ownership fails before selected mutation
    assert result.success is False
    assert environment.mutations == ()


def test_missing_main_is_refused_without_creation(tmp_path: Path) -> None:
    # Given: inventory lacks the reserved main agent and setup is not approved
    environment = SafetyEnvironment({"weather": tmp_path / "weather"})

    # When: deployment preflight runs
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: main is never sent through agents add and nothing mutates
    assert result.success is False
    assert "create:main" not in environment.openclaw.events
    assert environment.mutations == ()


def test_stable_partial_agent_creation_is_adopted_after_nonzero_exit(tmp_path: Path) -> None:
    # Given: stable OpenClaw will persist crypto inventory but report create failure
    crypto = tmp_path / "crypto"
    environment = SafetyEnvironment({"main": tmp_path / "main"})
    environment.openclaw.partial_create.add("crypto")

    # When: explicitly approved creation reconciles from post-exit inventory
    result = DeployWizard(environment.ports()).run(
        _request(
            (MarketCategory.CRYPTO,),
            workspaces={MarketCategory.CRYPTO: crypto},
            approvals=DeployApprovals(create_agents=True),
        )
    )

    # Then: the exact persisted row is adopted and no destructive rollback occurs
    assert result.success is True
    assert environment.openclaw.agents["crypto"] == crypto
    assert environment.openclaw.events.count("create:crypto") == 1


def test_conflicting_secret_ref_fails_global_preflight(tmp_path: Path) -> None:
    # Given: selected weather has a user-owned nonmatching SecretRef
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.make_exact("main")
    environment.openclaw.secret_refs["weather"] = SecretRefConfig(id="user_owned")

    # When: preflight compares the exact desired reference
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: the conflict is preserved and no token/config/workspace state mutates
    assert result.success is False
    assert environment.openclaw.secret_refs["weather"].id == "user_owned"
    assert environment.mutations == ()


def test_approved_dormant_heartbeat_uses_config_and_bootstrap_is_last(tmp_path: Path) -> None:
    # Given: selected existing agents approve dormant Gateway-owned heartbeat state
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.make_exact("main", "weather")

    # When: the approved 0m desired state is reconciled
    result = DeployWizard(environment.ports()).run(
        _request(
            (MarketCategory.WEATHER,),
            approvals=DeployApprovals(heartbeat_change=True),
            heartbeat="0m",
        )
    )

    # Then: config owns heartbeat and the one-shot Gateway bootstrap is the final mutation
    assert result.success is True
    assert environment.openclaw.heartbeats == {"main": "0m", "weather": "0m"}
    assert environment.mutations[-1] == "cron:ensure"
    assert all("doctor" not in event for event in environment.openclaw.events)


def test_heartbeat_change_without_approval_fails_before_mutation(tmp_path: Path) -> None:
    # Given: main has a user cadence and the request asks for 0m without approval
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.openclaw.heartbeats["main"] = "30m"

    # When: the unapproved desired state crosses preflight
    with pytest.raises(ValidationError, match="heartbeat change approval"):
        _ = _request((MarketCategory.WEATHER,), heartbeat="0m")

    # Then: user heartbeat state is preserved with zero mutation
    assert environment.openclaw.heartbeats["main"] == "30m"
    assert environment.mutations == ()


def test_bootstrap_conflict_is_detected_before_workspace_mutation(tmp_path: Path) -> None:
    # Given: the managed cron identity conflicts before deployment starts
    environment = SafetyEnvironment({"main": tmp_path / "main", "weather": tmp_path / "weather"})
    environment.openclaw.bootstrap_state = BootstrapCronState.CONFLICT

    # When: global preflight inspects Gateway automation
    result = DeployWizard(environment.ports()).run(_request((MarketCategory.WEATHER,)))

    # Then: no selected user state is touched
    assert result.success is False
    assert environment.mutations == ()


def test_rerun_reconciles_without_duplicate_creation_or_identity(tmp_path: Path) -> None:
    # Given: one approved missing crypto agent
    crypto = tmp_path / "crypto"
    environment = SafetyEnvironment({"main": tmp_path / "main"})
    request = _request(
        (MarketCategory.CRYPTO,),
        workspaces={MarketCategory.CRYPTO: crypto},
        approvals=DeployApprovals(create_agents=True, heartbeat_change=True),
        heartbeat="0m",
    )

    # When: the same request is run twice
    first = DeployWizard(environment.ports()).run(request)
    second = DeployWizard(environment.ports()).run(request)

    # Then: forward reconciliation converges all persistent identities once
    assert first.success is True and second.success is True
    assert environment.openclaw.events.count("create:crypto") == 1
    assert environment.tokens.created == {"main": 1, "crypto": 1}
    assert environment.openclaw.events.count("cron:ensure") == 2
