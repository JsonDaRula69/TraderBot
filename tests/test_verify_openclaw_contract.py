"""Required-vs-advisory contract for the OpenClaw verification probes.

Locks the deploy/verify ownership boundary: a required check fails only on
state the deployment asserted; posture the deployment never wrote is
reported as advisory divergence with actual values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from traderbot.deploy import openclaw, verify_openclaw
from traderbot.deploy.bootstrap_cron import BOOTSTRAP_NAME, BOOTSTRAP_PROMPT
from traderbot.deploy.deploy_state import save_deploy_state
from traderbot.deploy.openclaw_models import (
    AgentInventory,
    AgentSummary,
    CronJob,
    JsonValue,
)
from traderbot.deploy.verify_models import (
    CheckStatus,
    VerificationRequest,
)
from traderbot.deploy.verify_openclaw import OpenClawVerifier
from traderbot.deploy.wizard_contracts import DeployState
from traderbot.deploy.wizard_state import (
    AgentConfigState,
    OpenClawConfigSnapshot,
    SecretRefConfig,
    SecretRefState,
)
from traderbot.kalshi.order_models import MarketCategory

_CREATED_MS: int = 1_700_000_000_000
_IDS: tuple[str, ...] = ("main", "weather")


def _job(state: dict[str, JsonValue], **overrides: JsonValue) -> CronJob:
    """Build the canonical managed one-shot around one pending state shape."""
    job: CronJob = {
        "id": "bootstrap-id",
        "agentId": "main",
        "name": BOOTSTRAP_NAME,
        "enabled": True,
        "deleteAfterRun": True,
        "createdAtMs": _CREATED_MS,
        "updatedAtMs": _CREATED_MS,
        "schedule": {"kind": "at", "at": "2023-11-14T22:18:20Z"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": BOOTSTRAP_PROMPT},
        "state": state,
    }
    job.update(overrides)
    return job


def _inventory(*ids: str) -> AgentInventory:
    return AgentInventory(
        root=[
            AgentSummary(
                id=agent_id,
                workspace=f"/deploy/{agent_id}",
                agentDir=f"/deploy/{agent_id}",
                bindings=0,
                isDefault=agent_id == "main",
            )
            for agent_id in ids
        ]
    )


def _snapshot(
    *,
    sandbox: dict[str, str | None] | None = None,
    heartbeat: dict[str, str | None] | None = None,
    missing_ref: tuple[str, ...] = (),
) -> OpenClawConfigSnapshot:
    agents = tuple(
        AgentConfigState(
            agent_id=agent_id,
            path_prefix=f"agents.entries.{agent_id}",
            heartbeat_every=None if heartbeat is None else heartbeat.get(agent_id),
            sandbox_mode=None if sandbox is None else sandbox.get(agent_id),
        )
        for agent_id in _IDS
    )
    refs = tuple(
        SecretRefState(
            agent_id=agent_id,
            ref=None if agent_id in missing_ref else SecretRefConfig(id=f"{agent_id}_token"),
        )
        for agent_id in _IDS
    )
    return OpenClawConfigSnapshot(agents=agents, secret_refs=refs)


def _request(
    tmp_path: Path,
    *,
    created_agents: tuple[str, ...] = (),
    heartbeat_policy: Literal["preserve", "require_0m"] = "preserve",
    daemon_required: bool = True,
) -> VerificationRequest:
    return VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        data_root=tmp_path,
        created_agents=created_agents,
        heartbeat_policy=heartbeat_policy,
        daemon_required=daemon_required,
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: OpenClawConfigSnapshot,
    *,
    inventory: AgentInventory | None = None,
    jobs: list[CronJob] | None = None,
) -> None:
    monkeypatch.setattr(
        openclaw, "inspect_agents", lambda: _inventory(*_IDS) if inventory is None else inventory
    )
    monkeypatch.setattr(openclaw, "inspect_crons", lambda: jobs if jobs is not None else [])

    def _snapshot(ids: tuple[str, ...], inventory: AgentInventory) -> OpenClawConfigSnapshot:
        del ids, inventory
        return snapshot

    monkeypatch.setattr(verify_openclaw, "inspect_config", _snapshot)


def _wire_crons(
    monkeypatch: pytest.MonkeyPatch,
    jobs: list[CronJob] | None,
) -> None:
    monkeypatch.setattr(openclaw, "inspect_crons", lambda: jobs)


# --- agents(): sandbox posture is required only for agents the deploy created ---


def test_preserved_agents_with_divergent_sandbox_report_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a preserved fleet whose sandbox posture the deploy never wrote
    _wire(monkeypatch, _snapshot(sandbox={"main": None, "weather": None}))

    # When: the agents probe inspects posture the deployment does not own
    probe = OpenClawVerifier(_request(tmp_path)).agents()

    # Then: divergence is reported with actual values, not required failure
    assert probe.status is CheckStatus.DEGRADED
    assert probe.action == "sandbox_posture_reported"
    assert "main=unset" in probe.message
    assert "weather=unset" in probe.message


def test_preserved_agents_with_converged_posture_pass_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a preserved fleet that already converged to the canonical posture
    _wire(monkeypatch, _snapshot(sandbox={"main": "off", "weather": "all"}))

    # When: no required or advisory divergence exists
    probe = OpenClawVerifier(_request(tmp_path)).agents()

    # Then: the selected agents check passes exactly
    assert probe.status is CheckStatus.PASS
    assert probe.action == "selected_agents_exact"


def test_created_agents_must_match_the_written_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the deploy created weather and wrote the canonical sandbox mode
    _wire(monkeypatch, _snapshot(sandbox={"main": "off", "weather": None}))

    # When: a created agent's sandbox postcondition diverges
    probe = OpenClawVerifier(_request(tmp_path, created_agents=("weather",))).agents()

    # Then: the deploy's own postcondition still fails closed
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "agent_config_mismatch"


def test_created_agents_with_written_sandbox_pass_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the deploy created weather with the canonical sandbox written
    _wire(monkeypatch, _snapshot(sandbox={"main": "off", "weather": "all"}))

    # When: the created agent's postcondition is verified
    probe = OpenClawVerifier(_request(tmp_path, created_agents=("weather",))).agents()

    # Then: required postconditions hold and the probe passes
    assert probe.status is CheckStatus.PASS
    assert probe.action == "selected_agents_exact"


def test_secret_ref_mismatch_stays_a_required_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a converged posture but a missing weather SecretRef
    _wire(
        monkeypatch,
        _snapshot(sandbox={"main": "off", "weather": "all"}, missing_ref=("weather",)),
    )

    # When: the agents probe reads the injector mapping
    probe = OpenClawVerifier(_request(tmp_path)).agents()

    # Then: the deploy-owned SecretRef contract fails closed
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "secret_ref_mismatch"


def test_missing_selected_agent_stays_a_required_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the selected weather agent is absent from the inventory
    _wire(monkeypatch, _snapshot(), inventory=_inventory("main"))

    # When: target resolution reconciles the selected fleet
    probe = OpenClawVerifier(_request(tmp_path)).agents()

    # Then: presence remains required
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "agent_contract_mismatch"


# --- heartbeat(): dormancy is required only when the deploy approved it ---


def test_preserve_policy_reports_divergent_cadence_as_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a preserved fleet with active and unset heartbeat cadences
    _wire(monkeypatch, _snapshot(heartbeat={"main": "30m", "weather": None}))

    # When: the default preserve policy inspects cadence the deploy did not set
    probe = OpenClawVerifier(_request(tmp_path)).heartbeat()

    # Then: the divergence is advisory and states actual values
    assert probe.status is CheckStatus.DEGRADED
    assert probe.action == "heartbeat_posture_reported"
    assert "main=30m" in probe.message
    assert "weather=unset" in probe.message


def test_preserve_policy_dormant_fleet_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: every selected agent happens to be dormant
    _wire(monkeypatch, _snapshot(heartbeat={"main": "0m", "weather": "0m"}))

    # When: the preserve policy reports cadence
    probe = OpenClawVerifier(_request(tmp_path)).heartbeat()

    # Then: a converged fleet has nothing to report
    assert probe.status is CheckStatus.PASS
    assert probe.action == "heartbeat_dormant"


def test_require_0m_policy_fails_non_dormant_cadence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the deploy approved dormancy for the whole selected fleet
    _wire(monkeypatch, _snapshot(heartbeat={"main": "30m", "weather": "0m"}))

    # When: the approved postcondition is required
    probe = OpenClawVerifier(_request(tmp_path, heartbeat_policy="require_0m")).heartbeat()

    # Then: divergence from the approved state fails closed
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "heartbeat_mismatch"


def test_require_0m_policy_passes_dormant_fleet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the approved dormant postcondition holds everywhere
    _wire(monkeypatch, _snapshot(heartbeat={"main": "0m", "weather": "0m"}))

    # When: the approved postcondition is required
    probe = OpenClawVerifier(_request(tmp_path, heartbeat_policy="require_0m")).heartbeat()

    # Then: the required check passes exactly
    assert probe.status is CheckStatus.PASS
    assert probe.action == "heartbeat_dormant"


# --- cron(): lifecycle-aware probe against the one-shot contract ---


def test_completed_retained_one_shot_passes_with_distinct_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: Gateway retained the completed managed one-shot
    completed = _job({"lastStatus": "ok", "lastRunAtMs": _CREATED_MS + 300_000})
    _wire_crons(monkeypatch, [completed])

    # When: the probe classifies the completed lifecycle
    probe = OpenClawVerifier(_request(tmp_path)).cron()

    # Then: completion is a pass with its own action, not a mismatch
    assert probe.status is CheckStatus.PASS
    assert probe.action == "bootstrap_cron_completed_retained"


def test_fired_one_shot_absent_with_recorded_registration_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the one-shot fired, self-deleted, and deploy state records registration
    _wire_crons(monkeypatch, [])
    save_deploy_state(
        tmp_path,
        DeployState(
            step6_fingerprint="",
            step7_fingerprint="",
            step8_fingerprint="",
            steps=(),
            bootstrap_registered=True,
        ),
    )

    # When: the probe reconciles absence against recorded registration
    probe = OpenClawVerifier(_request(tmp_path)).cron()

    # Then: absence after firing is honest degraded state, not a failure
    assert probe.status is CheckStatus.DEGRADED
    assert probe.action == "bootstrap_cron_completed_absent"


def test_absent_one_shot_without_recorded_registration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: no managed job exists and no deploy state records registration
    _wire_crons(monkeypatch, [])

    # When: the probe classifies the empty inventory
    probe = OpenClawVerifier(_request(tmp_path)).cron()

    # Then: a never-registered contract fails closed
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "bootstrap_cron_mismatch"


def test_conflicting_cron_inventory_fails_with_conflict_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: one mutated identity field on the managed contract
    _wire_crons(monkeypatch, [_job({}, agentId="weather")])

    # When: the probe classifies the mutated readback
    probe = OpenClawVerifier(_request(tmp_path)).cron()

    # Then: the conflict is named distinctly from a plain mismatch
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "bootstrap_cron_conflict"


def test_unreadable_cron_inventory_stays_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the cron inventory cannot be read
    _wire_crons(monkeypatch, None)

    # When: the probe attempts the read
    probe = OpenClawVerifier(_request(tmp_path)).cron()

    # Then: an unreadable inventory fails closed
    assert probe.status is CheckStatus.FAIL
    assert probe.action == "cron_inventory_unreadable"
