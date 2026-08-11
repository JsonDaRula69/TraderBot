"""Focused tests for the OpenClaw CLI deployment boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

import traderbot.deploy.openclaw as openclaw
from traderbot.deploy.openclaw_models import JsonObject
from traderbot.services import deploy as service_deploy
from traderbot.services.paths import BinPaths


def _completed(
    argv: list[str],
    *,
    returncode: int = 0,
    stdout: str = "{}",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def _assert_run(run: mock.Mock, argv: list[str], timeout: float) -> None:
    run.assert_called_once_with(argv, timeout=timeout)


def test_existing_subprocess_convention_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the established service wrapper's subprocess boundary is intercepted
    run = mock.Mock(return_value=_completed(["systemctl", "is-active"]))
    destination = tmp_path / "traderbot.service"
    destination.touch()
    paths = BinPaths(tmp_path / "traderbot", tmp_path / "python", tmp_path, "tester")
    monkeypatch.setattr(service_deploy, "detect_service_manager", mock.Mock(return_value="systemd"))
    monkeypatch.setattr(service_deploy, "_destination", mock.Mock(return_value=destination))
    monkeypatch.setattr(subprocess, "run", run)

    # When: the existing wrapper executes a system command
    result = service_deploy.service_status(paths)

    # Then: it captures text, disables check, and applies its existing timeout
    assert result == "active"
    run.assert_called_once_with(
        ["systemctl", "is-active", "traderbot.service"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_detect_openclaw_uses_path_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: OpenClaw is installed at a resolved path
    which = mock.Mock(return_value="/opt/openclaw/bin/openclaw")
    monkeypatch.setattr(shutil, "which", which)

    # When: the wrapper detects OpenClaw
    result = openclaw.detect_openclaw()

    # Then: the trusted PATH lookup result is returned without execution
    assert result == "/opt/openclaw/bin/openclaw"
    which.assert_called_once_with("openclaw")


def test_install_openclaw_uses_current_package(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: npm is available and installation succeeds
    monkeypatch.setattr(shutil, "which", mock.Mock(return_value="/usr/bin/npm"))
    run = mock.Mock(return_value=_completed(["/usr/bin/npm"]))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: OpenClaw installation is explicitly invoked
    result = openclaw.install_openclaw()

    # Then: the first-party package and npm script allowlist are used
    assert result is True
    _assert_run(
        run,
        ["/usr/bin/npm", "install", "-g", "openclaw@latest", "--allow-scripts", "openclaw"],
        300.0,
    )


def test_install_openclaw_no_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: npm is absent and subprocess execution is forbidden
    monkeypatch.setattr(shutil, "which", mock.Mock(return_value=None))
    run = mock.Mock()
    monkeypatch.setattr(openclaw, "_run", run)

    # When: installation is requested
    result = openclaw.install_openclaw()

    # Then: the wrapper fails closed without launching anything
    assert result is False and run.call_count == 0


def test_openclaw_setup_uses_noninteractive_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: baseline setup emits current JSON
    payload = {
        "ok": True, "configPath": "/tmp/openclaw.json", "configStatus": "unchanged",
        "workspaceDir": "/tmp/workspace", "sessionsDir": "/tmp/sessions",
    }
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=json.dumps(payload)))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: setup is invoked
    result = openclaw.openclaw_setup()

    # Then: no interactive onboarding path is reachable
    assert result is True
    _assert_run(run, ["openclaw", "setup", "--baseline", "--json"], 120.0)


def test_create_agent_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: explicit arbitrary workspace creation succeeds
    workspace = Path(Path.cwd().anchor) / "srv" / "openclaw" / "teams" / "weather"
    run = mock.Mock(
        return_value=_completed(
            ["openclaw"],
            stdout=json.dumps(
                {
                    "agentId": "weather-agent",
                    "workspace": str(workspace),
                    "agentDir": "/state/agents/weather-agent/agent",
                    "bindings": {"added": [], "updated": [], "skipped": [], "conflicts": []},
                }
            ),
        )
    )
    monkeypatch.setattr(openclaw, "_run", run)

    # When: an unnormalized weather agent is explicitly created
    result = openclaw.create_agent(" Weather Agent ", workspace)

    # Then: one bounded request carries the canonical ID and approved path
    assert result is True
    add_argv = [
        "openclaw", "agents", "add", "weather-agent", "--workspace",
        str(workspace),
        "--non-interactive", "--json",
    ]
    _assert_run(run, add_argv, 120.0)


@pytest.mark.parametrize(
    ("agent_id", "workspace"),
    [
        ("", Path("/tmp/weather")),
        ("---", Path("/tmp/weather")),
        ("main", Path("/tmp/main")),
        ("OPENCLAW", Path("/tmp/openclaw")),
        ("crestodian", Path("/tmp/crestodian")),
        ("weather", Path("relative")),
    ],
)
def test_create_agent_rejects_invalid_or_reserved_id(
    monkeypatch: pytest.MonkeyPatch,
    agent_id: str,
    workspace: Path,
) -> None:
    # Given: an identifier that cannot name a user-created agent
    run = mock.Mock()
    monkeypatch.setattr(openclaw, "_run", run)

    # When: creation is requested
    result = openclaw.create_agent(agent_id, workspace)

    # Then: no OpenClaw state mutation is attempted
    assert result is False
    run.assert_not_called()


def test_register_cron_maps_prompt_to_message_atom(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a hostile prompt that would be shell syntax if interpolated
    prompt = "review $(touch /tmp/never) ; echo injected"
    stdout = (
        '{"id":"job-1","name":"traderbot-main-at-5m","enabled":true,'
        '"createdAtMs":1,"updatedAtMs":1,"schedule":{"kind":"at","at":"5m"},'
        '"sessionTarget":"isolated","wakeMode":"now",'
        '"payload":{"kind":"agentTurn","message":"run"},"state":{}}'
    )
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=stdout))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: a one-shot isolated cron is registered
    result = openclaw.register_cron(
        "Main",
        prompt,
        at="5m",
        session="isolated",
        delete_after_run=True,
    )

    # Then: prompt text remains one argv atom and obsolete --prompt is absent
    assert result is True
    argv = [
        "openclaw", "cron", "add",
        "--name", "traderbot-main-at-5m",
        "--agent",
        "main",
        "--session",
        "isolated",
        "--at",
        "5m",
        "--message",
        prompt,
        "--delete-after-run",
        "--json",
    ]
    _assert_run(run, argv, 60.0)


@pytest.mark.parametrize(
    ("at", "every", "session"),
    [(None, None, "isolated"), ("5m", "1h", "isolated"), ("", "1h", "isolated"),
     ("5m", None, "shared")],
)
def test_register_cron_rejects_invalid_schedule_or_session(
    monkeypatch: pytest.MonkeyPatch,
    at: str | None,
    every: str | None,
    session: str,
) -> None:
    # Given: a schedule or session outside the current CLI contract
    run = mock.Mock()
    monkeypatch.setattr(openclaw, "_run", run)

    # When: registration is requested
    result = openclaw.register_cron("weather", "run", at=at, every=every, session=session)

    # Then: the invalid request cannot mutate cron state
    assert result is False
    run.assert_not_called()


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ('{"jobs":[{"id":"one","enabled":true}]}', [{"id": "one", "enabled": True}]),
        ('[{"id":"legacy"}]', []),
        ('{"jobs":"not-a-list"}', []),
        ('{"jobs":["not-an-object"]}', []),
        ("not-json", []),
    ],
)
def test_list_crons_validates_current_object_shape(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    expected: list[dict[str, str | bool]],
) -> None:
    # Given: controlled current or malformed CLI output
    run = mock.Mock(return_value=_completed(["openclaw"], stdout=stdout))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: cron jobs are listed
    result = openclaw.list_crons()

    # Then: only the current top-level object with dictionary jobs is accepted
    assert result == expected
    _assert_run(run, ["openclaw", "cron", "list", "--json"], 30.0)


def test_inspect_crons_distinguishes_empty_inventory_from_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one valid empty inventory followed by mixed and malformed output
    run = mock.Mock(
        side_effect=[
            _completed(["openclaw"], stdout='{"jobs":[]}'),
            _completed(["openclaw"], stdout='{"jobs":[{"id":"one"},"hidden"]}'),
            _completed(["openclaw"], stdout="not-json"),
        ]
    )
    monkeypatch.setattr(openclaw, "_run", run)

    # When: the checked inventory boundary reads both responses
    empty = openclaw.inspect_crons()
    mixed = openclaw.inspect_crons()
    failed = openclaw.inspect_crons()

    # Then: callers can avoid mutating after an unreadable inventory
    assert empty == []
    assert mixed is None
    assert failed is None


@pytest.mark.parametrize(
    ("function", "argv", "payload"),
    [
        (
            openclaw.openclaw_doctor,
            ["openclaw", "doctor", "--lint", "--json"],
            {"ok": True, "checksRun": 1, "checksSkipped": 0, "findings": []},
        ),
        (
            openclaw.gateway_status,
            ["openclaw", "gateway", "status", "--json", "--require-rpc"],
            {"rpc": {"ok": True}},
        ),
    ],
)
def test_readonly_health_wrappers_use_strict_current_flags(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[[], bool],
    argv: list[str],
    payload: JsonObject,
) -> None:
    # Given: a current JSON response from a read-only health command
    run = mock.Mock(return_value=_completed(argv, stdout=json.dumps(payload)))
    monkeypatch.setattr(openclaw, "_run", run)

    # When: the selected health wrapper runs
    result = function()

    # Then: it succeeds only through the prompt-free current command
    assert result is True
    _assert_run(run, argv, 30.0)
