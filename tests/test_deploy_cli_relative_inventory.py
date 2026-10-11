from __future__ import annotations

import json
from pathlib import Path

from tests.test_deploy_cli_fake_e2e import (
    FakeAgentConfig,
    FakeAgentState,
    FakeLedger,
    build_fake_environment,
    run_fake_cli,
)
from traderbot.deploy.wizard import DeployResult
from traderbot.deploy.wizard_state import SecretRefConfig


def _write_relative_inventory(state_path: Path) -> FakeLedger:
    ledger = FakeLedger(
        mode="normal",
        agents={
            "main": FakeAgentState(
                workspace="relative-main",
                config=FakeAgentConfig(heartbeat={"every": "30m"}),
            ),
            "weather": FakeAgentState(
                workspace="relative-weather",
                config=FakeAgentConfig(heartbeat={"every": "30m"}),
            ),
        },
        refs={
            "main": SecretRefConfig(id="main_token"),
            "weather": SecretRefConfig(id="weather_token"),
        },
        crons=[],
        events=[],
        mutations=[],
    )
    _ = state_path.write_text(ledger.model_dump_json(), encoding="utf-8")
    return ledger


def _write_existing_weather_config(config_path: Path) -> None:
    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": False,
            "heartbeat_change": False,
        },
        "heartbeat_every": "preserve",
    }
    _ = config_path.write_text(json.dumps(payload), encoding="utf-8")


def test_real_cli_rejects_relative_inventory_before_all_mutation(tmp_path: Path) -> None:
    # Given: installed-style CLI input with relative main and weather inventory roots
    state_path, env = build_fake_environment(tmp_path)
    original = _write_relative_inventory(state_path)
    config_path = tmp_path / "deploy.json"
    _write_existing_weather_config(config_path)
    cwd = tmp_path / "dedicated-cwd"
    cwd.mkdir()

    # When: the real CLI parses inventory from the fake Gateway
    result = run_fake_cli(config_path, env, cwd)
    after = FakeLedger.model_validate_json(state_path.read_text(encoding="utf-8"))

    # Then: the typed boundary fails before filesystem, token, config, or cron mutation
    assert result.returncode == 1
    report = DeployResult.model_validate_json(result.stdout)
    assert report.success is False
    assert report.steps[0].message == "inventory_failed: OpenClaw agent inventory is unreadable"
    assert after.mutations == []
    assert after.refs == original.refs
    assert after.crons == []
    assert after.events == ["agents list --json"]
    assert list(cwd.iterdir()) == []
    assert (cwd / "relative-main").exists() is False
    assert (cwd / "relative-weather").exists() is False
    assert Path(env["TRADERBOT_DATA_DIR"]).exists() is False
