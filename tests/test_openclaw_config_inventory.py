from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from traderbot.deploy import openclaw, openclaw_config
from traderbot.deploy.openclaw_models import AgentInventory, AgentSummary
from traderbot.deploy.wizard_state import SecretRefConfig


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["openclaw"], returncode, stdout, "")


def _streams(stdout: str, stderr: str, returncode: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["openclaw"], returncode, stdout, stderr)


def _inventory() -> AgentInventory:
    workspace = Path(Path.cwd().anchor) / "srv" / "main"
    return AgentInventory(
        [
            AgentSummary(
                id="main",
                workspace=str(workspace),
                agentDir="/state/main",
                bindings=0,
                isDefault=True,
            )
        ]
    )


def _absolute_with_segment(segment: str) -> str:
    root = Path(Path.cwd().anchor) / "openclaw" / "agents"
    return f"{root}{os.sep}{segment}{os.sep}main"


@pytest.mark.parametrize(
    "workspace",
    [
        "relative-main",
        "",
        "~/.openclaw/workspace",
        _absolute_with_segment("."),
        _absolute_with_segment(".."),
    ],
)
def test_agent_inventory_rejects_noncanonical_workspace_at_parse_boundary(
    workspace: str,
) -> None:
    # Given: untrusted inventory with a relative, empty, tilde, or dot-segment path
    payload = {
        "id": "main",
        "workspace": workspace,
        "agentDir": "/state/main",
        "bindings": 0,
        "isDefault": True,
    }

    # When/Then: strict inventory parsing fails before path normalization
    with pytest.raises(ValidationError):
        _ = AgentSummary.model_validate(payload)


def test_agent_inventory_preserves_canonical_platform_absolute_workspace() -> None:
    # Given: a lexical absolute path under the current platform's path semantics
    workspace = str(Path(Path.cwd().anchor) / "openclaw" / "agents" / "main")

    # When: the inventory row crosses the typed boundary
    summary = AgentSummary(
        id="main",
        workspace=workspace,
        agentDir="/state/main",
        bindings=0,
        isDefault=True,
    )

    # Then: the exact lexical value is retained without realpath/link resolution
    assert summary.workspace == workspace


def test_current_entries_config_and_absent_secret_ref_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: current entries config and a machine-readable missing SecretRef
    run = mock.Mock(
        side_effect=[
            _completed('{"heartbeat":{"every":"30m"},"sandbox":{"mode":"off"}}'),
            _completed('{"error":"Config path not found: plugins.entry"}', returncode=1),
        ]
    )
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: selected config state is inspected
    snapshot = openclaw.inspect_config(("main",), _inventory())

    # Then: no secret is resolved and current config location is retained
    assert snapshot is not None
    agent = snapshot.agent("main")
    assert agent is not None
    assert agent.path_prefix == "agents.entries.main"
    assert agent.heartbeat_every == "30m"
    assert snapshot.secret_ref("main") is None


def test_stable_list_config_and_exact_secret_ref_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: entries is absent while stable list index and SecretRef are present
    secret_ref = SecretRefConfig(id="main_token")
    run = mock.Mock(
        side_effect=[
            _completed('{"error":"Config path not found: agents.entries.main"}', returncode=1),
            _completed('{"id":"main","heartbeat":{"every":"0m"}}'),
            _completed(secret_ref.model_dump_json()),
        ]
    )
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: cross-version config state is inspected
    snapshot = openclaw.inspect_config(("main",), _inventory())

    # Then: the stable array location and exact reference survive parsing
    assert snapshot is not None
    agent = snapshot.agent("main")
    assert agent is not None
    assert agent.path_prefix == "agents.list[0]"
    assert agent.heartbeat_every == "0m"
    assert snapshot.secret_ref("main") == secret_ref


def test_deployed_stderr_missing_path_reaches_agents_list_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the deployed OpenClaw 2026.7.1-2 CLI prints missing-path errors to
    # STDERR with EMPTY stdout and serves the agents.list[] config shape
    secret_path = "plugins.entries.traderbot-token-injector.config.agentTokenMap.main"
    run = mock.Mock(
        side_effect=[
            _streams("", "Config path not found: agents.entries.main\n", 1),
            _streams('{"id":"main","heartbeat":{"every":"0m"}}', "", 0),
            _streams("", f"Config path not found: {secret_path}\n", 1),
        ]
    )
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: selected config state is inspected against the deployed shape
    snapshot = openclaw.inspect_config(("main",), _inventory())

    # Then: the agents.list[index] fallback is reached and state is typed
    assert snapshot is not None
    agent = snapshot.agent("main")
    assert agent is not None
    assert agent.path_prefix == "agents.list[0]"
    assert agent.heartbeat_every == "0m"
    assert snapshot.secret_ref("main") is None


def test_unmarked_stderr_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a nonzero exit whose stderr carries no missing-path evidence
    run = mock.Mock(return_value=_streams("", "connection refused\n", 1))
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When/Then: the read is FAILED, not MISSING, and no snapshot is built
    assert openclaw.inspect_config(("main",), _inventory()) is None


def test_malformed_config_output_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: config get exits zero with malformed JSON
    monkeypatch.setattr(openclaw_config, "_run", mock.Mock(return_value=_completed("not-json")))

    # When/Then: no untyped value crosses the adapter boundary
    assert openclaw.inspect_config(("main",), _inventory()) is None


def test_secret_ref_is_one_atomic_structured_write(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: dry-run validation and one config publication succeed
    dry_run = json.dumps(
        {
            "ok": True,
            "operations": 1,
            "configPath": "/state/openclaw.json",
            "inputModes": ["json"],
            "checks": {
                "schema": True,
                "resolvability": True,
                "resolvabilityComplete": True,
            },
            "refsChecked": 0,
            "skippedExecRefs": 1,
        }
    )
    responses = iter((_completed(dry_run), _completed("")))
    calls: list[list[str]] = []

    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        calls.append(argv)
        return next(responses)

    monkeypatch.setattr(openclaw_config, "_run", run)
    secret_ref = SecretRefConfig(id="weather_token")

    # When: one selected mapping is requested
    result = openclaw.set_secret_ref("weather", secret_ref)

    # Then: both calls carry the complete object at one path, never three field writes
    assert result is True
    assert len(calls) == 2
    assert all(any("agentTokenMap.weather" in argument for argument in call) for call in calls)
    assert all(secret_ref.model_dump_json() in call for call in calls)


def test_set_config_encodes_hostile_string_as_one_strict_json_atom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: validated writes and a value containing shell/JSON metacharacters
    dry_run = json.dumps(
        {
            "ok": True,
            "operations": 1,
            "configPath": "/state/openclaw.json",
            "inputModes": ["json"],
            "checks": {
                "schema": True,
                "resolvability": True,
                "resolvabilityComplete": True,
            },
            "refsChecked": 0,
            "skippedExecRefs": 0,
        }
    )
    responses = iter((_completed(dry_run), _completed("")))
    calls: list[list[str]] = []

    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        calls.append(argv)
        return next(responses)

    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: the hostile value crosses the argv boundary
    result = openclaw.set_config("agents.defaults.model", '$(echo pwned) "quoted"')

    # Then: it remains one JSON atom and cannot become a key or option
    assert result is True
    encoded = '"$(echo pwned) \\"quoted\\""'
    assert all(encoded in call for call in calls)
    assert openclaw.set_config("--help", "ignored") is False
