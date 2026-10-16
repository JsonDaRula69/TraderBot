"""Real-process QA for current OpenClaw agent creation output."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

import traderbot.deploy.openclaw as openclaw
from tests.deploy_fake_openclaw import write_fake_openclaw
from traderbot.deploy.openclaw_models import (
    AgentRuntimeConfig,
    ConfigDryRun,
    SandboxDockerConfig,
)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_fake_executable_mirrors_deployed_missing_path_stderr_and_agents_list(
    tmp_path: Path,
) -> None:
    # Given: the fake OpenClaw executable with one seeded agent
    fake = tmp_path / "openclaw"
    write_fake_openclaw(fake)
    state_path = tmp_path / "state.json"
    _ = state_path.write_text(
        json.dumps(
            {
                "mode": "normal",
                "agents": {
                    "main": {
                        "workspace": "/openclaw/agents/main",
                        "config": {"heartbeat": {"every": "0m"}, "sandbox": {"mode": "off"}},
                    }
                },
                "refs": {},
                "crons": [],
                "events": [],
                "mutations": [],
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "FAKE_OC_STATE": str(state_path)}

    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(fake), *arguments],
            capture_output=True,
            text=True,
            timeout=10.0,
            env=env,
            check=False,
        )

    # When: a missing config path is requested
    missing = invoke("config", "get", "agents.entries.absent", "--json")

    # Then: the deployed 2026.7.1-2 contract is mirrored — stderr text, empty stdout
    assert missing.returncode == 1
    assert missing.stdout == ""
    assert "Config path not found: agents.entries.absent" in missing.stderr

    # And: the deployed agents.list[] shape returns id-bearing config JSON
    listed = invoke("config", "get", "agents.list[0]", "--json")
    assert listed.returncode == 0
    config = AgentRuntimeConfig.model_validate_json(listed.stdout)
    assert config.id == "main"
    assert config.heartbeat is not None
    assert config.heartbeat.every == "0m"

    # And: an out-of-range list index is a stderr missing path too
    absent = invoke("config", "get", "agents.list[1]", "--json")
    assert absent.returncode == 1
    assert absent.stdout == ""
    assert "Config path not found: agents.list[1]" in absent.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_current_agent_add_response_accepts_explicit_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: PATH contains a real executable emitting current string-array bindings
    fake = tmp_path / "openclaw"
    log = tmp_path / "argv.log"
    _ = fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            with Path({str(log)!r}).open("a", encoding="utf-8") as stream:
                stream.write("\\0".join(args) + "\\n")
            if args[:2] == ["agents", "add"]:
                workspace = args[args.index("--workspace") + 1]
                print(json.dumps({{
                    "agentId": "weather", "workspace": workspace,
                    "agentDir": "/state/agents/weather/agent",
                    "bindings": {{"added": ["telegram"], "updated": [],
                                 "skipped": [], "conflicts": []}},
                }}))
            else:
                raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    # When: production create_agent launches the executable
    workspace = tmp_path / "nested" / "weather"
    result = openclaw.create_agent("weather", workspace)

    # Then: the current add response is accepted without unrelated config writes
    calls = log.read_text(encoding="utf-8")
    assert result is True
    assert calls.count("agents\0add") == 1
    assert str(workspace) in calls
    assert "config\0set" not in calls


def _seeded_fake(
    tmp_path: Path, config: dict[str, object]
) -> tuple[Path, Path, Callable[..., subprocess.CompletedProcess[str]]]:
    fake = tmp_path / "openclaw"
    write_fake_openclaw(fake)
    state_path = tmp_path / "state.json"
    _ = state_path.write_text(
        json.dumps(
            {
                "mode": "normal",
                "agents": {
                    "weather": {
                        "workspace": "/openclaw/agents/weather",
                        "config": config,
                    }
                },
                "refs": {},
                "crons": [],
                "events": [],
                "mutations": [],
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "FAKE_OC_STATE": str(state_path)}

    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(fake), *arguments],
            capture_output=True,
            text=True,
            timeout=10.0,
            env=env,
            check=False,
        )

    return fake, state_path, invoke


_BINDS = ["/srv/ws/weather:/workspace:ro", "/srv/data/paper-weather:/data:rw"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_fake_executable_list_shaped_sandbox_write_round_trips_byte_equal(
    tmp_path: Path,
) -> None:
    # Given: the list-first fake with one sandboxed agent on the deployed shape
    _, _, invoke = _seeded_fake(
        tmp_path, {"heartbeat": {"every": "0m"}, "sandbox": {"mode": "all"}}
    )
    encoded_binds = json.dumps(_BINDS)

    # When: the full D1/D9 key set is written as JSON values on bracket paths
    writes = [
        ("agents.list[0].sandbox.docker.binds", encoded_binds),
        ("agents.list[0].sandbox.docker.image", json.dumps("traderbot-sandbox:d0123abcd")),
        ("agents.list[0].sandbox.docker.dangerouslyAllowExternalBindSources", "true"),
        ("agents.list[0].sandbox.docker.dangerouslyAllowReservedContainerTargets", "true"),
        ("agents.list[0].sandbox.workspaceAccess", json.dumps("none")),
    ]
    for key, value in writes:
        written = invoke("config", "set", key, value, "--strict-json")
        assert written.returncode == 0, written.stderr

    # Then: a re-read of the array through the same seam is BYTE-EQUAL to the
    # canonical JSON that was written (the CLI's `print` adds one newline)
    reread = invoke("config", "get", "agents.list[0].sandbox.docker.binds", "--json")
    assert reread.returncode == 0
    assert reread.stdout == encoded_binds + "\n"
    assert json.loads(reread.stdout) == _BINDS

    # And: the whole agent re-read types against the extended deploy model
    listed = invoke("config", "get", "agents.list[0]", "--json")
    config = AgentRuntimeConfig.model_validate_json(listed.stdout)
    assert config.id == "weather"
    assert config.sandbox is not None
    assert config.sandbox.mode == "all"
    assert config.sandbox.workspaceAccess == "none"
    assert config.sandbox.docker == SandboxDockerConfig(
        image="traderbot-sandbox:d0123abcd",
        binds=_BINDS,
        dangerouslyAllowExternalBindSources=True,
        dangerouslyAllowReservedContainerTargets=True,
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_fake_executable_unset_removes_key_and_reread_reports_absence(
    tmp_path: Path,
) -> None:
    # Given: a docker block with image + binds written through the real seam
    _, _, invoke = _seeded_fake(
        tmp_path,
        {
            "sandbox": {
                "mode": "all",
                "docker": {"image": "traderbot-sandbox:d0123abcd", "binds": list(_BINDS)},
            }
        },
    )
    key = "agents.list[0].sandbox.docker.binds"

    # When: the key is validated then removed through the unset subcommand
    validated = invoke("config", "unset", key, "--dry-run", "--json")
    assert validated.returncode == 0, validated.stderr
    dry_run = ConfigDryRun.model_validate_json(validated.stdout)
    assert "unset" in dry_run.inputModes
    removed = invoke("config", "unset", key)
    assert removed.returncode == 0, removed.stderr

    # Then: the re-read reports the deployed missing-path contract on STDERR
    gone = invoke("config", "get", key, "--json")
    assert gone.returncode == 1
    assert gone.stdout == ""
    assert f"Config path not found: {key}" in gone.stderr

    # And: the parent object survives with the key ABSENT (deleted, never null)
    listed = json.loads(invoke("config", "get", "agents.list[0]", "--json").stdout)
    assert "binds" not in listed["sandbox"]["docker"]
    assert listed["sandbox"]["docker"]["image"] == "traderbot-sandbox:d0123abcd"

    # And: unsetting an already-absent path fails the pinned dry-run gate too
    assert invoke("config", "unset", key, "--dry-run", "--json").returncode == 1
    assert invoke("config", "unset", key).returncode == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_fake_executable_rejects_entries_write_and_destructive_or_malformed_sets(
    tmp_path: Path,
) -> None:
    # Given: the deployed list-shaped config carrying a known sandbox mode
    _, state_path, invoke = _seeded_fake(tmp_path, {"sandbox": {"mode": "off"}})

    # When: an entries-namespace write targets the list-shaped config
    entries_write = invoke(
        "config",
        "set",
        "agents.entries.weather.sandbox.mode",
        json.dumps("all"),
        "--strict-json",
    )

    # Then: it is rejected on STDERR and the stored config provably never moved
    assert entries_write.returncode == 1
    assert "agents.entries" in entries_write.stderr
    listed = invoke("config", "get", "agents.list[0]", "--json")
    assert json.loads(listed.stdout)["sandbox"] == {"mode": "off"}

    # And: a malformed --strict-json value is rejected without a mutation
    malformed = invoke(
        "config",
        "set",
        "agents.list[0].sandbox.docker.binds",
        "[unterminated",
        "--strict-json",
    )
    assert malformed.returncode == 1
    assert "sandbox.docker.binds" in malformed.stderr

    # And: replacing the whole agents.list array is refused (pinned CLI guard)
    replace = invoke("config", "set", "agents.list", json.dumps([]), "--strict-json")
    assert replace.returncode == 1
    assert "agents.list" in replace.stderr

    # And: after every rejection the state file still serves the original agent
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert final_state["agents"]["weather"]["config"]["sandbox"] == {"mode": "off"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_production_seams_round_trip_json_values_through_the_fake_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the fake on PATH backing the REAL production wrapper seams
    _, state_path, _invoke = _seeded_fake(tmp_path, {"sandbox": {"mode": "all"}})
    monkeypatch.setenv("FAKE_OC_STATE", str(state_path))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    key = "agents.list[0].sandbox.docker.binds"
    encoded = json.dumps(_BINDS)

    # When: the production JSON-value seam writes through the deployed shape
    assert openclaw.set_config_json(key, encoded) is True

    # Then: the CLI re-read is byte-equal to the written canonical JSON
    reread = subprocess.run(
        ["openclaw", "config", "get", key, "--json"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    assert reread.returncode == 0
    assert reread.stdout == encoded + "\n"

    # And: the production unset seam removes it with the absence contract
    assert openclaw.unset_config(key) is True
    gone = subprocess.run(
        ["openclaw", "config", "get", key, "--json"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    assert gone.returncode == 1
    assert f"Config path not found: {key}" in gone.stderr
