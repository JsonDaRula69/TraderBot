"""Plan todo 9 (GAP-6, IS-4/D2/D4/D9/D10): the sandbox posture probe family.

Lives on LIVE-config reads only (agents.list[i] grammar, T1), derives desired
state only from sandbox_config_for with the image passed explicitly, and
dependency-SKIPs with a typed reason when no step-7 apply is recorded.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from traderbot.deploy import verify_sandbox
from traderbot.deploy.openclaw_models import (
    AgentInventory,
    ConfigReadState,
    ConfigValueRead,
    JsonValue,
)
from traderbot.deploy.sandbox_build import SandboxBuildError
from traderbot.deploy.verify_models import CheckStatus, ProbeResult, VerificationRequest
from traderbot.deploy.verify_sandbox import ImageInspection, ImageState, SandboxVerifier
from traderbot.deploy.wizard_contracts import DeployState
from traderbot.deploy.wizard_state import SandboxLadderMode
from traderbot.kalshi.order_models import MarketCategory
from traderbot.sandbox import sandbox_config_for, sandbox_image_tag


def _request(
    tmp_path: Path,
    *,
    created: tuple[str, ...] = (),
    categories: tuple[MarketCategory, ...] = (MarketCategory.WEATHER,),
) -> VerificationRequest:
    return VerificationRequest.model_validate(
        {
            "categories": categories,
            "mode": "backtest",
            "sysadmin_workspace": tmp_path / "main",
            "category_workspaces": {},
            "data_root": tmp_path / "state",
            "infisical_origin": "http://localhost:8080",
            "daemon_mcp_url": "http://127.0.0.1:8765/mcp",
            "timeout_seconds": 5.0,
            "heartbeat_policy": "require_0m",
            "created_agents": created,
        }
    )


def _inventory(tmp_path: Path, ids: tuple[str, ...]) -> AgentInventory:
    return AgentInventory.model_validate(
        [
            {
                "id": agent_id,
                "workspace": str(tmp_path / "ws" / agent_id),
                "isDefault": agent_id == "main",
                "agentDir": str(tmp_path / "agentdir" / agent_id),
                "bindings": 0,
            }
            for agent_id in ids
        ]
    )


def _workspace(tmp_path: Path, agent_id: str) -> Path:
    return tmp_path / "ws" / agent_id


def _block(
    request: VerificationRequest,
    tmp_path: Path,
    agent_id: str,
    ladder: SandboxLadderMode,
    image: str,
) -> dict[str, JsonValue]:
    return sandbox_config_for(
        agent_id,
        request.data_root,
        _workspace(tmp_path, agent_id),
        mode=ladder,
        image=image,
    ).to_openclaw_keys()


def _deploy_state(*, fingerprint: str) -> DeployState:
    return DeployState.model_validate(
        {
            "step6_fingerprint": "a",
            "step7_fingerprint": "b",
            "step8_fingerprint": "c",
            "step7_docker_fingerprint": fingerprint,
            "steps": [],
        }
    )


def _fake_reads(
    live: dict[str, JsonValue],
) -> Callable[[str], ConfigValueRead]:
    def read(key: str) -> ConfigValueRead:
        if key in live:
            return ConfigValueRead(state=ConfigReadState.FOUND, value=live[key])
        return ConfigValueRead(state=ConfigReadState.ABSENT)

    return read


def _mount(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    inventory: AgentInventory | None,
    live: dict[str, JsonValue],
    deploy_state: DeployState | None = None,
) -> str:
    """Wire the T6/T7 seams to test doubles; returns the pinned image tag."""
    monkeypatch.setattr(verify_sandbox, "inspect_agents", lambda: inventory)
    monkeypatch.setattr(verify_sandbox, "read_config_value", _fake_reads(live))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    monkeypatch.setattr(verify_sandbox, "resolve_sandbox_dockerfile", lambda: dockerfile)

    def _load_state(_root: Path) -> DeployState | None:
        return deploy_state

    monkeypatch.setattr(verify_sandbox, "load_deploy_state", _load_state)
    return sandbox_image_tag(dockerfile)


# --- evidence gate: no apply recorded -> typed dependency skips ---------------


def test_apply_absent_skips_every_probe_with_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live={"agents.list[0].id": "main"},
        deploy_state=None,
    )
    verifier = SandboxVerifier(request)

    for probe in (
        verifier.mode_readback,
        verifier.posture_config,
        verifier.off_negative,
        verifier.image_presence,
    ):
        result = probe()
        assert result.status is CheckStatus.SKIP
        assert result.action == "sandbox_apply_absent"
        assert "apply approval" in result.message


def test_empty_fingerprint_is_also_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live={"agents.list[0].id": "main"},
        deploy_state=_deploy_state(fingerprint=""),
    )
    verifier = SandboxVerifier(request)
    assert verifier.posture_config().status is CheckStatus.SKIP


# --- exact posture passes ------------------------------------------------------


def test_exact_posture_passes_all_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, created=("weather", "dev-liaison"))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)
    live: dict[str, JsonValue] = {
        "agents.list[0].id": "main",
        "agents.list[0].sandbox": {"mode": "off"},
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": _block(request, tmp_path, "weather", "backtest", image),
        "agents.list[2].id": "dev-liaison",
        "agents.list[2].sandbox": _block(request, tmp_path, "dev-liaison", "paper", image),
    }
    image = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather", "dev-liaison")),
        live=live,
        deploy_state=None,
    )
    def _present(_tag: str, **_kwargs: object) -> ImageInspection:
        return ImageInspection(ImageState.PRESENT)

    monkeypatch.setattr(verify_sandbox, "inspect_sandbox_image", _present)
    verifier = SandboxVerifier(request)

    mode = verifier.mode_readback()
    assert mode.status is CheckStatus.PASS and mode.action == "sandbox_mode_exact"
    assert "2 sandboxed" in mode.message
    posture = verifier.posture_config()
    assert posture.status is CheckStatus.PASS and posture.action == "sandbox_posture_exact"
    off = verifier.off_negative()
    assert off.status is CheckStatus.PASS and off.action == "sandbox_off_exact"
    presence = verifier.image_presence()
    assert presence.status is CheckStatus.PASS
    assert presence.action == "sandbox_image_present"
    assert image in presence.message


# --- R2 class: unsandboxed selected agent fails required, actionable -----------


def test_unsandboxed_selected_agent_fails_required_and_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    verifier = SandboxVerifier(request)

    mode = verifier.mode_readback()
    assert mode.status is CheckStatus.FAIL
    assert mode.action == "sandbox_mode_mismatch"
    assert "weather=unset" in mode.message
    assert "TRADERBOT_PHASE5_SANDBOX=1" in mode.message

    posture = verifier.posture_config()
    assert posture.status is CheckStatus.FAIL
    assert posture.action == "sandbox_posture_missing"
    assert "weather" in posture.message
    assert "unsandboxed" in posture.message
    assert "TRADERBOT_PHASE5_SANDBOX=1" in posture.message


def test_mode_drift_names_agent_and_keeps_posture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)
    block = _block(request, tmp_path, "weather", "backtest", image)
    block["mode"] = "non-main"
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": block,
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    verifier = SandboxVerifier(request)

    mode = verifier.mode_readback()
    assert mode.status is CheckStatus.FAIL
    assert "weather=non-main" in mode.message
    # Mode drift is the readback probe's surface; the posture probe compares
    # workspaceAccess + docker only and still passes on its own terms.
    assert verifier.posture_config().status is CheckStatus.PASS


# --- single-field drift fails the posture check with the field named -----------


def _drifted_block(
    request: VerificationRequest,
    tmp_path: Path,
    image: str,
    mutate: Callable[[dict[str, JsonValue]], None],
) -> dict[str, JsonValue]:
    block = copy.deepcopy(_block(request, tmp_path, "weather", "backtest", image))
    mutate(block)
    return block


def test_single_leaf_drift_fails_with_field_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)

    def drop_one_bind(block: dict[str, JsonValue]) -> None:
        docker = block["docker"]
        assert isinstance(docker, dict)
        binds = docker["binds"]
        assert isinstance(binds, list)
        docker["binds"] = binds[:1]

    block = _drifted_block(request, tmp_path, image, drop_one_bind)
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": block,
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_posture_mismatch"
    assert "docker.binds differs" in result.message
    assert "TRADERBOT_PHASE5_SANDBOX=1" in result.message


def test_missing_required_docker_leaf_fails_with_field_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)

    def drop_read_only_root(block: dict[str, JsonValue]) -> None:
        docker = block["docker"]
        assert isinstance(docker, dict)
        del docker["readOnlyRoot"]

    block = _drifted_block(request, tmp_path, image, drop_read_only_root)
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": block,
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert "docker.readOnlyRoot missing" in result.message


def test_image_drift_fails_with_field_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Image-drift false-negative guard: a stale container image tag MUST fail,
    # never blur into a pass because the other seven leaves match.
    request = _request(tmp_path, created=("weather",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)

    def stale_image(block: dict[str, JsonValue]) -> None:
        docker = block["docker"]
        assert isinstance(docker, dict)
        docker["image"] = "traderbot-sandbox:d00000000"

    block = _drifted_block(request, tmp_path, image, stale_image)
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": block,
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_posture_mismatch"
    assert "docker.image differs" in result.message


def test_foreign_dangerous_key_is_named_drift_never_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D9 guard: exactly-two dangerous-* is a CLOSED set. An extra dangerous key
    # on top of a byte-exact block is admitted as named drift (reader tolerant),
    # never crashed on and never silently accepted.
    request = _request(tmp_path, created=("weather",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)

    def add_foreign(block: dict[str, JsonValue]) -> None:
        docker = block["docker"]
        assert isinstance(docker, dict)
        docker["dangerouslyAllowContainerNamespaceJoin"] = True

    block = _drifted_block(request, tmp_path, image, add_foreign)
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": block,
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_posture_drift"
    assert "docker.dangerouslyAllowContainerNamespaceJoin" in result.message
    assert "Remedy" in result.message


def test_malformed_blocks_fail_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Legacy/foreign shapes (a string where the object belongs) are reader-
    # tolerated: typed FAIL, never an exception leaking out of the probe.
    request = _request(tmp_path, created=("weather",))
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": {"mode": "all", "workspaceAccess": "none", "docker": "legacy"},
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_posture_malformed"

    live["agents.list[1].sandbox"] = "not-an-object"
    result = SandboxVerifier(request).mode_readback()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_posture_malformed"


# --- off-negative (main/sysadmin) ----------------------------------------------


def _off_request_and_mount(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ids: tuple[str, ...],
    live: dict[str, JsonValue],
) -> SandboxVerifier:
    request = _request(tmp_path, created=("weather",))
    _ = _mount(monkeypatch, tmp_path, inventory=_inventory(tmp_path, ids), live=live)
    return SandboxVerifier(request)


def test_off_negative_accepts_unset_or_off_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live: dict[str, JsonValue] = {"agents.list[0].id": "main"}
    # main with NO sandbox block (the deploy never writes one) passes.
    assert (
        _off_request_and_mount(tmp_path, monkeypatch, ("main",), live)
        .off_negative()
        .status
        is CheckStatus.PASS
    )

    live["agents.list[0].sandbox"] = {"mode": "off"}
    assert (
        _off_request_and_mount(tmp_path, monkeypatch, ("main",), live)
        .off_negative()
        .status
        is CheckStatus.PASS
    )


def test_off_negative_rejects_sandboxed_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live: dict[str, JsonValue] = {
        "agents.list[0].id": "main",
        "agents.list[0].sandbox": {"mode": "all"},
    }
    result = _off_request_and_mount(tmp_path, monkeypatch, ("main",), live).off_negative()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_off_violation"
    assert "main" in result.message
    assert "Remedy" in result.message


def test_off_negative_rejects_any_docker_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live: dict[str, JsonValue] = {
        "agents.list[0].id": "main",
        "agents.list[0].sandbox": {"mode": "off"},
        "agents.list[1].id": "sysadmin",
        "agents.list[1].sandbox": {"mode": "off", "docker": {"image": "x"}},
    }
    result = _off_request_and_mount(
        tmp_path, monkeypatch, ("main", "sysadmin"), live
    ).off_negative()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_off_violation"
    assert "sysadmin" in result.message
    assert "docker" in result.message


# --- identity / readability fail-closed ----------------------------------------


def test_identity_drift_refuses_posture_attribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    live: dict[str, JsonValue] = {
        "agents.list[1].id": "crypto",  # a re-order attributed the wrong agent
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
    )
    result = SandboxVerifier(request).mode_readback()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_identity_drift"


def test_unreadable_inventory_or_config_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    _ = _mount(monkeypatch, tmp_path, inventory=None, live={})
    verifier = SandboxVerifier(request)
    assert verifier.mode_readback().action == "inventory_unreadable"
    assert verifier.off_negative().action == "inventory_unreadable"

    def _failed_read(_key: str) -> ConfigValueRead:
        return ConfigValueRead(state=ConfigReadState.FAILED)

    monkeypatch.setattr(verify_sandbox, "read_config_value", _failed_read)
    monkeypatch.setattr(
        verify_sandbox,
        "inspect_agents",
        lambda: _inventory(tmp_path, ("main", "weather")),
    )
    verifier = SandboxVerifier(request)
    assert verifier.mode_readback().action == "sandbox_identity_drift"


def test_missing_selected_agent_fails_not_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Standalone re-verification (persisted fingerprint) against an inventory
    # that lost the agent: required failure, distinct from a dependency skip.
    request = _request(tmp_path)
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "sports")),
        live={},
        deploy_state=_deploy_state(fingerprint="abc123"),
    )
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_target_missing"
    assert "weather" in result.message


def test_standalone_fingerprint_makes_posture_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No threaded selection (standalone run), but the persisted step-7
    # fingerprint makes the posture REQUIRED for the request's categories.
    request = _request(tmp_path)
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)
    live: dict[str, JsonValue] = {
        "agents.list[0].id": "main",
        "agents.list[1].id": "weather",
        "agents.list[1].sandbox": _block(request, tmp_path, "weather", "backtest", image),
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live=live,
        deploy_state=_deploy_state(fingerprint="abc123"),
    )
    verifier = SandboxVerifier(request)
    assert verifier.mode_readback().status is CheckStatus.PASS
    assert verifier.posture_config().status is CheckStatus.PASS


def test_dev_liaison_is_proven_on_the_paper_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GAP-13/T9: dev-liaison always runs paper (never the request's ladder) —
    # binds must name the paper- data dir, byte-exactly.
    request = _request(tmp_path, created=("dev-liaison",))
    dockerfile = tmp_path / "Dockerfile"
    _ = dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = sandbox_image_tag(dockerfile)
    live: dict[str, JsonValue] = {
        "agents.list[0].id": "main",
        "agents.list[1].id": "dev-liaison",
        "agents.list[1].sandbox": _block(request, tmp_path, "dev-liaison", "paper", image),
    }
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "dev-liaison")),
        live=live,
    )
    assert SandboxVerifier(request).posture_config().status is CheckStatus.PASS

    backtest = _block(request, tmp_path, "dev-liaison", "backtest", image)
    live["agents.list[1].sandbox"] = backtest
    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert "docker.binds differs" in result.message


# --- image presence --------------------------------------------------------------


def _presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    inspection: ImageInspection,
) -> tuple[str, ProbeResult]:
    request = _request(tmp_path, created=("weather",))
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live={},
    )
    dockerfile = tmp_path / "Dockerfile"
    tag = sandbox_image_tag(dockerfile)
    def _fixed(_tag: str, **_kwargs: object) -> ImageInspection:
        return inspection

    monkeypatch.setattr(verify_sandbox, "inspect_sandbox_image", _fixed)
    return tag, SandboxVerifier(request).image_presence()


def test_image_present_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tag, result = _presence(tmp_path, monkeypatch, ImageInspection(ImageState.PRESENT))
    assert result.status is CheckStatus.PASS
    assert tag in result.message


def test_image_absent_fails_with_build_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag, result = _presence(tmp_path, monkeypatch, ImageInspection(ImageState.ABSENT))
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_image_absent"
    assert tag in result.message
    assert "build-sandbox.sh" in result.message


def test_docker_absent_skips_with_typed_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tag, result = _presence(tmp_path, monkeypatch, ImageInspection(ImageState.DOCKER_ABSENT))
    assert result.status is CheckStatus.SKIP
    assert result.action == "docker_unavailable"
    assert "not on PATH" in result.message


def test_dead_daemon_fails_with_distinct_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tag, result = _presence(
        tmp_path, monkeypatch, ImageInspection(ImageState.DAEMON_UNAVAILABLE)
    )
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_image_probe_failed"
    assert "daemon" in result.message


def test_unresolvable_dockerfile_fails_with_restore_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path, created=("weather",))
    _ = _mount(
        monkeypatch,
        tmp_path,
        inventory=_inventory(tmp_path, ("main", "weather")),
        live={},
    )

    def _drifted() -> Path:
        raise SandboxBuildError("pinned Dockerfile digest drifted")

    monkeypatch.setattr(verify_sandbox, "resolve_sandbox_dockerfile", _drifted)
    result = SandboxVerifier(request).image_presence()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_image_unverifiable"
    assert "Dockerfile" in result.message

    result = SandboxVerifier(request).posture_config()
    assert result.status is CheckStatus.FAIL
    assert result.action == "sandbox_image_unverifiable"
