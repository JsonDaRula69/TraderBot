"""Regression matrix for the managed bootstrap cron readback contract."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from traderbot.deploy import openclaw
from traderbot.deploy.bootstrap_cron import (
    BOOTSTRAP_NAME,
    BOOTSTRAP_PROMPT,
    SysAdminBootstrapCron,
    classify_bootstrap_crons,
)
from traderbot.deploy.openclaw_models import CronJob, JsonValue
from traderbot.deploy.verify_models import CheckStatus, VerificationRequest
from traderbot.deploy.verify_openclaw import OpenClawVerifier
from traderbot.deploy.wizard_runtime import OpenClawAdapter
from traderbot.deploy.wizard_state import BootstrapCronState
from traderbot.kalshi.order_models import MarketCategory

# Deployed OpenClaw 2026.7.1-2 pending one-shot envelope, byte-derived from the
# on-target receipt (.omo/evidence/f3-a104-r5-receipts/recorded-cron-job.json):
# the gateway populates state {"nextRunAtMs": <positive int>} plus top-level
# nextRunAtMs and status "idle" the moment the job is scheduled.
_RECORDED_DEPLOYED_JOB: CronJob = {
    "id": "f0de970a-afe2-4cdd-9a7b-5267b901a2cd",
    "agentId": "main",
    "name": BOOTSTRAP_NAME,
    "enabled": True,
    "deleteAfterRun": True,
    "createdAtMs": 1_791_125_258_522,
    "updatedAtMs": 1_791_125_258_522,
    "schedule": {"kind": "at", "at": "2026-10-04T14:52:37.823Z"},
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {"kind": "agentTurn", "message": BOOTSTRAP_PROMPT},
    "delivery": {"mode": "announce", "channel": "last"},
    "state": {"nextRunAtMs": 1_791_125_557_823},
    "nextRunAtMs": 1_791_125_557_823,
    "status": "idle",
}

_CREATED_MS: int = 1_700_000_000_000


def _job(state: dict[str, JsonValue], **overrides: JsonValue) -> CronJob:
    """Build the canonical managed contract around one pending state shape."""
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


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"nextRunAtMs": 1_791_125_557_823},
    ],
    ids=["documented-empty", "deployed-pending"],
)
def test_pending_one_shot_readback_classifies_exact_for_both_state_shapes(
    state: dict[str, JsonValue],
) -> None:
    # Given: the managed contract with the documented or deployed pending state
    # When: the inventory is classified
    # Then: the job is an exact pending one-shot, not a conflict
    assert classify_bootstrap_crons([_job(state)]) is BootstrapCronState.EXACT
    assert SysAdminBootstrapCron.is_unique_match([_job(state)]) is True


def test_recorded_deployed_job_validates_as_pending_exact() -> None:
    # Given: the exact deployed job recorded on-target at rerun #5
    # When: the deployed envelope is validated and classified directly
    # Then: the pending contract matches without mutation of the receipt
    assert SysAdminBootstrapCron.model_validate(dict(_RECORDED_DEPLOYED_JOB)) is not None
    assert classify_bootstrap_crons([dict(_RECORDED_DEPLOYED_JOB)]) is (BootstrapCronState.EXACT)


def test_deployed_top_level_extras_are_ignored_with_either_state_shape() -> None:
    # Given: deployed nextRunAtMs/status/delivery top-level extras
    # When: classification reads the pending contract
    # Then: unrelated deployed extras do not turn the readback into a conflict
    documented_with_extras: CronJob = {
        **_job({}),
        "delivery": {"mode": "announce", "channel": "last"},
        "nextRunAtMs": 1_700_000_300_000,
        "status": "idle",
    }
    assert classify_bootstrap_crons([documented_with_extras]) is (BootstrapCronState.EXACT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agentId", "weather"),
        ("enabled", False),
        ("deleteAfterRun", False),
        ("sessionTarget", "main"),
        ("wakeMode", "next-heartbeat"),
        ("schedule", {"kind": "every", "everyMs": 86_400_000}),
        ("schedule", {"kind": "at", "at": "2023-11-14T22:48:20Z"}),
        ("payload", {"kind": "systemEvent", "text": "wrong activation"}),
        (
            "payload",
            {"kind": "agentTurn", "message": "Begin the SysAdmin activation protocol:"},
        ),
    ],
    ids=[
        "wrong-agent",
        "disabled",
        "no-delete-after-run",
        "wrong-session",
        "wrong-wake-mode",
        "recurring-schedule",
        "wrong-delay",
        "wrong-payload-kind",
        "mutated-message",
    ],
)
def test_mutated_identity_fields_still_fail_closed_as_conflict(
    field: str,
    value: JsonValue,
) -> None:
    # Given: one mutated identity field on the deployed pending envelope
    job = {**_job({"nextRunAtMs": 1_791_125_557_823}), field: value}

    # When: the readback is classified
    # Then: the contract fails closed instead of matching
    assert classify_bootstrap_crons([job]) is BootstrapCronState.CONFLICT
    assert SysAdminBootstrapCron.is_unique_match([job]) is False


@pytest.mark.parametrize(
    "state",
    [
        {"nextRunAtMs": "1791125557823"},
        {"nextRunAtMs": 1.5},
        {"nextRunAtMs": True},
        {"nextRunAtMs": None},
        {"nextRunAtMs": 0},
        {"nextRunAtMs": -1},
        {"nextRunAtMs": 123, "lastStatus": "ok"},
        {"lastRunAtMs": 123},
        {"lastStatus": "error", "lastRunAtMs": 123},
    ],
    ids=[
        "string-ms",
        "float-ms",
        "bool-ms",
        "null-ms",
        "zero-ms",
        "negative-ms",
        "extra-state-key",
        "ran-without-status",
        "errored-shape",
    ],
)
def test_non_pending_or_garbage_state_fails_closed_as_conflict(
    state: dict[str, JsonValue],
) -> None:
    # Given: a same-name job whose state is not a pending envelope
    # When: the readback is classified
    # Then: garbage and already-run/errored shapes never satisfy the exact contract
    assert classify_bootstrap_crons([_job(state)]) is BootstrapCronState.CONFLICT
    assert SysAdminBootstrapCron.is_unique_match([_job(state)]) is False


def test_completed_retained_state_stays_distinct_from_pending_exact() -> None:
    # Given: Gateway retains the job with completed runtime state
    completed = _job({"lastStatus": "ok", "lastRunAtMs": _CREATED_MS + 300_000})

    # When: the lifecycle is classified
    # Then: completion remains its own outcome, never a pending exact match
    assert classify_bootstrap_crons([completed]) is BootstrapCronState.COMPLETED_RETAINED
    assert classify_bootstrap_crons([completed]) is not BootstrapCronState.EXACT


def test_duplicate_managed_jobs_remain_a_conflict() -> None:
    # Given: two identical deployed pending jobs under the managed name
    jobs = [_job({"nextRunAtMs": 123}), _job({"nextRunAtMs": 456})]

    # When: classification matches by name
    # Then: duplication still fails closed
    assert classify_bootstrap_crons(jobs) is BootstrapCronState.CONFLICT
    assert SysAdminBootstrapCron.is_unique_match(jobs) is False


def test_classification_boundaries_are_unchanged() -> None:
    # Given: unreadable, empty, and non-managed inventories
    # When: classification reads each
    # Then: the envelope outcomes keep their established meanings
    assert classify_bootstrap_crons(None) is BootstrapCronState.FAILED
    assert classify_bootstrap_crons([]) is BootstrapCronState.MISSING
    non_managed: CronJob = {"name": "other", "agentId": "main"}
    assert classify_bootstrap_crons([non_managed]) is BootstrapCronState.MISSING


def test_deployed_pending_readback_completes_wizard_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a first registration whose readback returns the deployed envelope
    inspect = mock.Mock(return_value=[dict(_RECORDED_DEPLOYED_JOB)])
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", inspect)
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: step 3 verifies the freshly scheduled one-shot
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.MISSING)

    # Then: registration is confirmed exact instead of failing closed (C1)
    assert result is True
    assert register.call_count == 1
    assert inspect.call_count == 1


def test_deployed_pending_readback_passes_verification_cron_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the deployed pending envelope in a readable cron inventory
    monkeypatch.setattr(openclaw, "inspect_crons", lambda: [dict(_RECORDED_DEPLOYED_JOB)])
    request = VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        data_root=tmp_path,
    )

    # When: the standalone verifier probes the managed cron contract
    probe = OpenClawVerifier(request).cron()

    # Then: the check passes exactly instead of reporting a mismatch (C5)
    assert probe.status is CheckStatus.PASS
    assert probe.action == "bootstrap_cron_exact"
