"""Regression tests for the independently verified Todo-3 defects."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

import traderbot.deploy.openclaw as openclaw
import traderbot.deploy.openclaw_config as openclaw_config


def _dry_run_json(*, ok: bool = True) -> str:
    return json.dumps(
        {
            "ok": ok,
            "operations": 1,
            "configPath": "/home/tester/.openclaw/openclaw.json",
            "inputModes": ["value"],
            "checks": {"schema": ok, "resolvability": ok, "resolvabilityComplete": ok},
            "refsChecked": 0,
            "skippedExecRefs": 0,
        }
    )


def _cron_job_json(*, wrapped: bool = False) -> str:
    job = {
        "id": "job-1",
        "name": "traderbot-weather-every-1h",
        "enabled": True,
        "createdAtMs": 1,
        "updatedAtMs": 1,
        "schedule": {"kind": "every", "everyMs": 3_600_000},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": "run"},
        "state": {},
    }
    return json.dumps({"created": True, "job": job} if wrapped else job)


def _completed(
    argv: list[str],
    *,
    returncode: int = 0,
    stdout: str = "{}",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def test_create_agent_nonzero_is_reported_without_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the bounded explicit-path add exits nonzero
    calls: list[list[str]] = []

    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        calls.append(argv)
        return _completed(argv, returncode=1, stdout="")

    monkeypatch.setattr(openclaw, "_run", run)

    # When: one creation request is issued
    workspace = Path(Path.cwd().anchor) / "srv" / "weather"
    result = openclaw.create_agent("weather", workspace)

    # Then: the wrapper reports failure without any rollback/delete request
    assert result is False
    argv = calls[0]
    assert argv[1:3] == ["agents", "add"]
    assert "delete" not in argv


def test_inspect_agents_preserves_existing_inventory_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: inventory contains an arbitrary configured weather workspace
    workspace = Path(Path.cwd().anchor) / "other" / "workspace"
    inventory = json.dumps(
        [{"id": "weather", "workspace": str(workspace), "agentDir": "/state/agent",
          "bindings": 0, "isDefault": False}]
    )
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=inventory))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: the strict read-only inventory wrapper executes
    result = openclaw.inspect_agents()

    # Then: the exact path crosses the typed boundary without mutation
    assert result is not None
    assert result.root[0].workspace == str(workspace)
    run.assert_called_once_with(["openclaw", "agents", "list", "--json"], timeout=30.0)


@pytest.mark.parametrize(
    ("session", "target", "payload_flag"),
    [
        ("main", "main", "--system-event"),
        ("isolated", "isolated", "--message"),
        ("current", "current", "--message"),
        ("session:weather-123", "session:weather-123", "--message"),
        ("SESSION:  Case-ID  ", "session:Case-ID", "--message"),
    ],
)
def test_register_cron_maps_current_session_payload(
    monkeypatch: pytest.MonkeyPatch,
    session: str,
    target: str,
    payload_flag: str,
) -> None:
    # Given: cron add returns a documented created-job id
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=_cron_job_json()))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: each current session target is registered
    result = openclaw.register_cron("weather", "run", every="1h", session=session)

    # Then: main uses a system event while agent-turn targets use a message
    assert result is True
    expected = [
        "openclaw", "cron", "add", "--name", "traderbot-weather-every-1h",
        "--agent", "weather", "--session", target, "--every", "1h",
        payload_flag, "run", "--json",
    ]
    run.assert_called_once_with(expected, timeout=60.0)


@pytest.mark.parametrize("session", ["session:", "session:   ", "shared"])
def test_register_cron_rejects_malformed_session_target(
    monkeypatch: pytest.MonkeyPatch,
    session: str,
) -> None:
    # Given: a target outside current session syntax
    run = mock.Mock()
    monkeypatch.setattr(openclaw, "_run", run)

    # When: cron registration is requested
    result = openclaw.register_cron("weather", "run", every="1h", session=session)

    # Then: no mutation is launched
    assert result is False
    run.assert_not_called()


def test_list_crons_filters_invalid_members_without_losing_valid_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: current output mixes dictionary jobs with malformed members
    payload = '{"jobs":[{"id":"one"},"invalid",3,null,{"id":"two"}]}'
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=payload))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: cron jobs are listed
    result = openclaw.list_crons()

    # Then: every valid dictionary job is preserved in source order
    assert result == [{"id": "one"}, {"id": "two"}]


@pytest.mark.parametrize(
    ("function", "payload"),
    [
        (openclaw.openclaw_setup, '{"ok":false,"configStatus":"error"}'),
        (openclaw.openclaw_doctor, '{"ok":false,"findings":[]}'),
        (openclaw.gateway_status, '{"rpc":{"ok":false}}'),
    ],
)
def test_json_health_commands_reject_semantic_failure(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[[], bool],
    payload: str,
) -> None:
    # Given: a documented exit-zero semantic failure envelope
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=payload))
    monkeypatch.setattr(openclaw, "_run", run)

    # When/Then: command-specific validation rejects it
    assert function() is False


@pytest.mark.parametrize(
    "payload",
    ["{}", '{"ok":false,"id":"job-1"}', '{"ok":"false","id":"job-1"}', '{"id":""}'],
)
def test_register_cron_requires_created_job_id(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    # Given: cron add exits zero without a created job id
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=payload))
    monkeypatch.setattr(openclaw, "_run", run)

    # When/Then: mutation is not reported as successful
    assert openclaw.register_cron("weather", "run", every="1h") is False


@pytest.mark.parametrize("payload", [_cron_job_json(), _cron_job_json(wrapped=True)])
def test_register_cron_accepts_documented_job_shapes(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    # Given: cron add returns either documented job response shape
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=payload))
    monkeypatch.setattr(openclaw, "_run", run)

    # When/Then: a nonempty created job id establishes success
    assert openclaw.register_cron("weather", "run", every="1h") is True


def test_gateway_status_accepts_current_top_level_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: current daemon status reports RPC health at the top level
    run = mock.Mock(return_value=_completed(["openclaw"], stdout='{"rpc":{"ok":true}}'))
    monkeypatch.setattr(openclaw, "_run", run)

    # When/Then: current healthy output is accepted
    assert openclaw.gateway_status() is True


@pytest.mark.parametrize(
    "payload",
    [
        '{"ok":true,"checksRun":1,"checksSkipped":0,"findings":[null]}',
        '{"ok":true,"checksRun":1,"checksSkipped":0,"findings":[{"checkId":"x"}]}',
    ],
)
def test_doctor_rejects_malformed_findings(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    # Given: a nominally successful report has malformed finding members
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=payload))
    monkeypatch.setattr(openclaw, "_run", run)

    # When/Then: required finding fields are enforced
    assert openclaw.openclaw_doctor() is False


def test_set_config_rejects_failed_dry_run_without_write(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: strict JSON dry-run exits zero with a documented failure report
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=_dry_run_json(ok=False)))
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: a configuration write is requested
    result = openclaw.set_config("agents.defaults.model", "provider/model")

    # Then: no non-dry-run mutation is attempted
    assert result is False
    run.assert_called_once_with(
        [
            "openclaw", "config", "set", "agents.defaults.model", '"provider/model"',
            "--strict-json", "--dry-run", "--json",
        ],
        timeout=60.0,
    )


def test_set_config_rejects_partial_success_dry_run_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: dry-run claims success but omits the documented report fields
    run = mock.Mock(return_value=_completed(["openclaw"], stdout='{"ok":true}'))
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: a configuration write is requested
    result = openclaw.set_config("agents.defaults.model", "provider/model")

    # Then: malformed validation output cannot trigger the real write
    assert result is False
    assert run.call_count == 1
