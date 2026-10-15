from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from traderbot.deploy import openclaw, openclaw_config
from traderbot.deploy.openclaw_models import AgentInventory, AgentRuntimeConfig, AgentSummary
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


def _dry_run(input_mode: str = "json") -> str:
    return json.dumps(
        {
            "ok": True,
            "operations": 1,
            "configPath": "/state/openclaw.json",
            "inputModes": [input_mode],
            "checks": {
                "schema": True,
                "resolvability": True,
                "resolvabilityComplete": True,
            },
            "refsChecked": 0,
            "skippedExecRefs": 0,
        }
    )


def _recording_run(
    monkeypatch: pytest.MonkeyPatch,
    *responses: subprocess.CompletedProcess[str],
) -> list[list[str]]:
    calls: list[list[str]] = []
    queue = iter(responses)

    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        calls.append(argv)
        return next(queue)

    monkeypatch.setattr(openclaw_config, "_run", run)
    return calls


def test_set_config_json_writes_array_value_on_list_bracket_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: dry-run validation and publication both succeed
    calls = _recording_run(monkeypatch, _completed(_dry_run()), _completed(""))
    binds = '["/srv/ws/weather:/workspace:ro", "/srv/data/paper-weather:/data:rw"]'
    key = "agents.list[0].sandbox.docker.binds"

    # When: a pre-encoded JSON array is written on the deployed-shape path
    result = openclaw.set_config_json(key, binds)

    # Then: the value atom is passed byte-exactly through validation and write
    assert result is True
    assert calls == [
        ["openclaw", "config", "set", key, binds, "--strict-json", "--dry-run", "--json"],
        ["openclaw", "config", "set", key, binds, "--strict-json"],
    ]


@pytest.mark.parametrize("value", ["true", '{"image": "img", "binds": []}', "[]", "0"])
def test_set_config_json_accepts_any_json_document_value(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    # Given: validated writes for bool, object, array, and number JSON atoms
    calls = _recording_run(monkeypatch, _completed(_dry_run()), _completed(""))

    # When/Then: each valid JSON document is written without re-encoding
    assert openclaw.set_config_json("agents.list[2].sandbox.docker.network", value) is True
    assert all(value in call for call in calls)


@pytest.mark.parametrize("value", ["", "   ", "[unterminated", '{"a": }', "all", "'quoted'"])
def test_set_config_json_rejects_malformed_json_without_a_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    # Given: a value string that is not a JSON document
    run = mock.Mock()
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When/Then: the write fails closed before any CLI invocation
    assert openclaw.set_config_json("agents.list[0].sandbox.mode", value) is False
    run.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [
        "agents.list[]",
        "agents.list[x].sandbox.mode",
        "agents.list[0",
        "agents.list[0].sandbox.",
        "agents.list[0]..sandbox",
        ".agents.list[0]",
        "agents.list [0].sandbox",
        "agents.list[0 ].sandbox",
        "--help",
        "agents.list",
        "plugins.entries",
        "agents.defaults.models",
        "models.providers",
    ],
)
def test_config_writes_reject_malformed_bracket_paths_and_protected_roots(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    # Given: a grammatically invalid key or a wholesale-replacement-protected root
    run = mock.Mock()
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When/Then: every writer fails closed before touching the CLI
    assert openclaw.set_config(key, "value") is False
    assert openclaw.set_config_json(key, "true") is False
    assert openclaw.unset_config(key) is False
    run.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [
        "agents.list[0]",
        "agents.list[23].sandbox.docker.binds",
        "agents.list[0].heartbeat.every",
        "plugins.entries.traderbot-token-injector.config.agentTokenMap.weather",
        "agents.defaults.model",
    ],
)
def test_config_write_grammar_accepts_bracket_list_and_dotted_paths(key: str) -> None:
    # Given/When/Then: the write grammar matches the pinned CLI dot+bracket subset
    assert openclaw_config._CONFIG_KEY_PATTERN.fullmatch(key) is not None
    assert key not in openclaw_config._PROTECTED_CONFIG_PATHS


def test_unset_config_validates_then_removes_with_exact_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an unset dry-run validated with the unset input mode, then removal
    key = "agents.list[1].sandbox.docker.binds"
    calls = _recording_run(
        monkeypatch,
        _completed(_dry_run("unset")),
        _completed(f"Removed {key}. Restart the gateway..."),
    )

    # When: the key is removed through the seam
    result = openclaw.unset_config(key)

    # Then: dry-run validation precedes the real unset, matching the pinned CLI
    assert result is True
    assert calls == [
        ["openclaw", "config", "unset", key, "--dry-run", "--json"],
        ["openclaw", "config", "unset", key],
    ]


@pytest.mark.parametrize(
    ("responses", "expected_calls"),
    [
        # Failed dry-run: removal must never be attempted
        ((_completed("Config path not found: x", returncode=1),), 1),
        # Malformed dry-run envelope: fail closed before the real unset
        ((_completed("not-json"),), 1),
        # Real unset exits nonzero after a green dry-run
        ((_completed(_dry_run("unset")), _completed("", returncode=1)), 2),
    ],
)
def test_unset_config_fails_closed_on_dry_run_or_removal_failure(
    monkeypatch: pytest.MonkeyPatch,
    responses: tuple[subprocess.CompletedProcess[str], ...],
    expected_calls: int,
) -> None:
    # Given: a failing stage in the validate-then-remove sequence
    calls = _recording_run(monkeypatch, *responses)

    # When/Then: the seam reports failure and stops at the broken stage
    assert openclaw.unset_config("agents.list[0].sandbox.mode") is False
    assert len(calls) == expected_calls


def test_sandbox_config_types_full_docker_block_and_forbids_extra_keys() -> None:
    # Given: the D1/D9 full sandbox object as served by the deployed gateway
    payload = {
        "id": "weather",
        "sandbox": {
            "mode": "all",
            "workspaceAccess": "none",
            "docker": {
                "image": "traderbot-sandbox:d0123abcd",
                "binds": [
                    "/srv/ws/weather:/workspace:ro",
                    "/srv/data/paper-weather:/data:rw",
                ],
                "dangerouslyAllowExternalBindSources": True,
                "dangerouslyAllowReservedContainerTargets": True,
            },
        },
    }

    # When: the re-read crosses the typed deploy boundary
    config = AgentRuntimeConfig.model_validate(payload)

    # Then: every sandbox field is typed with the pinned schema's key names
    assert config.sandbox is not None
    assert config.sandbox.mode == "all"
    assert config.sandbox.workspaceAccess == "none"
    docker = config.sandbox.docker
    assert docker is not None
    assert docker.image == "traderbot-sandbox:d0123abcd"
    assert docker.binds == [
        "/srv/ws/weather:/workspace:ro",
        "/srv/data/paper-weather:/data:rw",
    ]
    assert docker.dangerouslyAllowExternalBindSources is True
    assert docker.dangerouslyAllowReservedContainerTargets is True

    # And: the strict docker model forbids keys outside the owner-approved D9 set
    forbidden = json.loads(json.dumps(payload))
    forbidden["sandbox"]["docker"]["dangerouslyAllowContainerNamespaceJoin"] = True
    with pytest.raises(ValidationError):
        AgentRuntimeConfig.model_validate(forbidden)

    # And: workspaceAccess is deploy-narrowed to "none" (never ro/rw leases)
    widened = json.loads(json.dumps(payload))
    widened["sandbox"]["workspaceAccess"] = "rw"
    with pytest.raises(ValidationError):
        AgentRuntimeConfig.model_validate(widened)


def test_agent_config_path_resolves_entries_then_list_from_current_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: entries is absent and the deployed list shape serves the agent
    run = mock.Mock(
        side_effect=[
            _completed('{"error":"Config path not found: agents.entries.main"}', returncode=1),
            _completed('{"id":"main","sandbox":{"mode":"all"}}'),
        ]
    )
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: the write prefix is resolved from current gateway state
    prefix = openclaw.agent_config_path("main", _inventory())

    # Then: the entries-first + list-fallback logic lands on agents.list[0]
    assert prefix == "agents.list[0]"
    assert run.call_count == 2


def test_agent_config_path_prefers_entries_when_the_legacy_shape_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a gateway that still serves the entries namespace (post-2026.8.1)
    monkeypatch.setattr(
        openclaw_config,
        "_run",
        mock.Mock(return_value=_completed('{"sandbox":{"mode":"off"}}')),
    )

    # When/Then: the canonical entries prefix wins per the existing read order
    assert openclaw.agent_config_path("main", _inventory()) == "agents.entries.main"


def test_agent_config_path_fails_closed_for_unknown_agent_or_failed_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an agent outside the inventory — resolution must not guess an index
    run = mock.Mock()
    monkeypatch.setattr(openclaw_config, "_run", run)
    assert openclaw.agent_config_path("ghost", _inventory()) is None
    run.assert_not_called()

    # And: an unmarked read failure resolves to None, never a guessed prefix
    monkeypatch.setattr(
        openclaw_config,
        "_run",
        mock.Mock(return_value=_streams("", "connection refused\n", 1)),
    )
    assert openclaw.agent_config_path("main", _inventory()) is None
