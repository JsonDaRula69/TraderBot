"""Real-process QA for current OpenClaw agent creation output."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

import traderbot.deploy.openclaw as openclaw
from tests.deploy_fake_openclaw import write_fake_openclaw
from traderbot.deploy.openclaw_models import AgentRuntimeConfig


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
