from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.deploy_cli_support import (
    FakeLedger,
    build_fake_environment,
    run_fake_cli,
)
from tests.test_deploy_cli_fake_e2e import write_config, write_happy_state
from traderbot.deploy.sandbox_build import build_sandbox_image, resolve_sandbox_dockerfile
from traderbot.deploy.wizard import DeployResult
from traderbot.sandbox import sandbox_image_tag


def test_full_deploy_mocked(tmp_path: Path, clean_workspace_root: Path) -> None:
    # Given: a unique data root, fake OpenClaw, and a Docker invocation canary
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, clean_workspace_root)
    config = tmp_path / "deploy.json"
    write_config(config, clean_workspace_root / "approved" / "crypto")
    default_root = Path(env["HOME"]) / ".traderbot"
    docker_log = tmp_path / "docker-calls.jsonl"
    docker = tmp_path / "bin" / "docker"
    _ = docker.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$TRADERBOT_DOCKER_LOG"\nexit 97\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env["TRADERBOT_DOCKER_LOG"] = str(docker_log)

    # When: the real module CLI completes config-mode deployment
    result = run_fake_cli(config, env)

    # Then: every owned artifact is under the isolated root and Docker/default state are untouched
    assert result.returncode == 0, result.stdout + result.stderr
    report = DeployResult.model_validate_json(result.stdout)
    assert report.completed_steps == tuple(range(1, 9))
    data_root = Path(env["TRADERBOT_DATA_DIR"])
    expected = {
        data_root / "backtest-weather" / "db" / "decisions.db",
        data_root / "backtest-crypto" / "db" / "decisions.db",
        data_root / "chromadb",
        data_root / "deploy-state.json",
        data_root / "secrets" / "secrets.json",
    }
    assert all(path.exists() for path in expected)
    assert default_root.exists() is False
    assert docker_log.exists() is False
    ledger = FakeLedger.model_validate_json(state_path.read_text(encoding="utf-8"))
    # The docker CLI canary above proves the daemon was never invoked (the fake
    # exits 97 if called); step 7's sanctioned sandbox.docker writes reach the
    # fake gateway ONLY via the deployed list-first bracket grammar with
    # --strict-json (todo-8 lane).
    docker_events = [event for event in ledger.events if "sandbox.docker" in event]
    assert docker_events
    assert all(event.startswith("config set agents.list[") for event in docker_events)
    assert all("--strict-json" in event for event in docker_events)
    assert not [event for event in ledger.events if event.split(" ", 1)[0] == "docker"]


def test_invalid_json_exits_2(tmp_path: Path, clean_workspace_root: Path) -> None:
    # Given: malformed config input and observable fake external state
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, clean_workspace_root)
    initial_state = state_path.read_bytes()
    config = tmp_path / "deploy.json"
    _ = config.write_text('{"categories": ["weather"],', encoding="utf-8")
    data_root = Path(env["TRADERBOT_DATA_DIR"])

    # When: the real module CLI parses the malformed document
    result = run_fake_cli(config, env)

    # Then: it reports invalid input before filesystem or external mutation
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_request"}
    assert result.stderr == ""
    assert data_root.exists() is False
    assert state_path.read_bytes() == initial_state


# --- T7 recording-emulator canary (GAP-9/NOTE A; plan todo 7) ---------------
#
# The Docker canary below replaces the old "docker is never invoked" fake with a
# RECORDING EMULATOR: a real fake-docker binary that succeeds ONLY for the exact
# sanctioned build argv and records every call's argv + environment. The seam
# under test is traderbot.deploy.sandbox_build.build_sandbox_image(), which runs
# install/docker/build-sandbox.sh once.

_EMULATOR_TEMPLATE = '''\
#!/usr/bin/env python3
"""Recording docker emulator: exit 0 ONLY for the sanctioned sandbox build."""
import json
import os
import sys
from pathlib import Path

LOG = Path(__LOG__)
SANCTIONED_DOCKERFILE = __DOCKERFILE__
SANCTIONED_TAG = __TAG__
SANCTIONED_CONTEXT = __CONTEXT__

args = sys.argv[1:]
record = {"argv": args, "env": dict(os.environ)}
with LOG.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\\n")

sanctioned = (
    bool(args)
    and args[0] == "build"
    and "--pull=false" in args
    and "--network" in args
    and args[args.index("--network") + 1] == "none"
    and "-f" in args
    and args[args.index("-f") + 1] == SANCTIONED_DOCKERFILE
    and "-t" in args
    and args[args.index("-t") + 1] == SANCTIONED_TAG
    and args[-1] == SANCTIONED_CONTEXT
)
raise SystemExit(0 if sanctioned else 97)
'''


def _write_recording_docker(
    path: Path,
    log_path: Path,
    *,
    dockerfile: str,
    tag: str,
    context: str,
) -> None:
    script = (
        _EMULATOR_TEMPLATE.replace("__LOG__", repr(str(log_path)))
        .replace("__DOCKERFILE__", repr(dockerfile))
        .replace("__TAG__", repr(tag))
        .replace("__CONTEXT__", repr(context))
    )
    _ = path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def test_sandbox_build_recording_emulator_single_sanctioned_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test-map: GAP-9/NOTE A/D7/D10 — the sanctioned seam makes exactly ONE
    # docker build call, with the Dockerfile + install/docker context, no host
    # network and no remote pull, and forwards no TraderBot secret.
    dockerfile = resolve_sandbox_dockerfile()
    tag = sandbox_image_tag(dockerfile)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_path = tmp_path / "docker-calls.jsonl"
    _write_recording_docker(
        fake_bin / "docker",
        log_path,
        dockerfile="install/docker/Dockerfile",
        tag=tag,
        context="install/docker",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("TRADERBOT_TEST_KALSHI_KEY", "should-never-leak")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PEM", "should-never-leak-pem")

    result = build_sandbox_image()

    assert result.image == tag
    assert tag in result.stdout
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    argv = records[0]["argv"]
    assert argv[0] == "build"
    assert "--pull=false" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("-f") + 1] == "install/docker/Dockerfile"
    assert argv[argv.index("-t") + 1] == tag
    assert argv[-1] == "install/docker"
    # No remote pull and no host networking anywhere in the invocation.
    assert "--pull" not in argv
    assert "host" not in argv
    assert "--network=host" not in argv
    # #448-class: the child env carries operational vars only — never a secret.
    child_env = records[0]["env"]
    assert "PATH" in child_env
    assert "TRADERBOT_TEST_KALSHI_KEY" not in child_env
    assert "KALSHI_PRIVATE_KEY_PEM" not in child_env
    assert "should-never-leak" not in json.dumps(child_env)
