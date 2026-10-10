from __future__ import annotations

import json
from pathlib import Path

from tests.deploy_cli_support import (
    FakeLedger,
    build_fake_environment,
    run_fake_cli,
)
from tests.test_deploy_cli_fake_e2e import write_config, write_happy_state
from traderbot.deploy.wizard import DeployResult


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
    assert not [event for event in ledger.events if "docker" in event.lower()]


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
