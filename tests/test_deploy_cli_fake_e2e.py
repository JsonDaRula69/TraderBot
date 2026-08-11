from __future__ import annotations

import json
import os
import secrets
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import ClassVar, Literal

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, ConfigDict, Field

from tests.deploy_fake_openclaw import write_fake_openclaw
from traderbot.db.chroma_store import ChromaStore
from traderbot.deploy.openclaw_models import CronJob
from traderbot.deploy.wizard import DeployResult
from traderbot.deploy.wizard_state import SecretRefConfig
from traderbot.profiles.registry import ProfileRegistry
from traderbot.secrets.resolver import build_secrets_store


class FakeAgentConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    heartbeat: dict[str, str] = Field(default_factory=dict)
    sandbox: dict[str, str] = Field(default_factory=dict)


class FakeAgentState(BaseModel):
    workspace: str
    config: FakeAgentConfig


class FakeLedger(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    mode: Literal["normal", "partial"]
    agents: dict[str, FakeAgentState]
    refs: dict[str, SecretRefConfig]
    crons: list[CronJob]
    events: list[str]
    mutations: list[str]


def build_fake_environment(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_openclaw(fake_bin / "openclaw")
    home = tmp_path / "home"
    home.mkdir()
    data = tmp_path / "data"
    state = tmp_path / "openclaw-state.json"
    env = os.environ.copy()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "TRADERBOT_DATA_DIR": str(data),
            "FAKE_OC_STATE": str(state),
            "TRADERBOT_USE_HARDCODED_AUTH": "1",
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
            "TRADERBOT_TEST_KALSHI_KEY": secrets.token_urlsafe(),
            "TRADERBOT_TEST_KALSHI_PEM": private_key_pem,
        }
    )
    return state, env


def run_fake_cli(
    config: Path,
    env: dict[str, str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from traderbot.cli import main; raise SystemExit(main())",
            "deploy",
            "--config",
            str(config),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
        env=env,
        cwd=cwd,
    )


def _write_happy_state(
    state_path: Path,
    tmp_path: Path,
    mode: Literal["normal", "partial"] = "normal",
) -> None:
    state = FakeLedger(
        mode=mode,
        agents={
            "main": FakeAgentState(
                workspace=str(tmp_path / "existing-main"),
                config=FakeAgentConfig(heartbeat={"every": "30m"}, sandbox={"mode": "off"}),
            ),
            "weather": FakeAgentState(
                workspace=str(tmp_path / "nested" / "team" / "weather"),
                config=FakeAgentConfig(heartbeat={"every": "30m"}, sandbox={"mode": "all"}),
            ),
            "sports": FakeAgentState(
                workspace=str(tmp_path / "unselected-sports"),
                config=FakeAgentConfig(heartbeat={"every": "15m"}, sandbox={"mode": "all"}),
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
    _ = state_path.write_text(state.model_dump_json(), encoding="utf-8")


def _write_config(
    path: Path,
    crypto_workspace: Path,
    secret_approvals: dict[str, bool] | None = None,
) -> None:
    payload = {
        "categories": ["weather", "crypto"],
        "mode": "backtest",
        "tokens": {
            "kalshi_api_key_env": "TRADERBOT_TEST_KALSHI_KEY",
            "kalshi_private_key_pem_env": "TRADERBOT_TEST_KALSHI_PEM",
        },
        "category_workspaces": {"crypto": str(crypto_workspace)},
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": True,
            "heartbeat_change": True,
        },
        "heartbeat_every": "0m",
    }
    if secret_approvals is not None:
        payload["secret_approvals"] = secret_approvals
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_real_cli_reconciles_selected_agents_and_reruns_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: main and nested weather exist while selected crypto is missing
    state_path, env = build_fake_environment(tmp_path)
    _write_happy_state(state_path, tmp_path)
    crypto = tmp_path / "approved" / "crypto"
    config = tmp_path / "deploy.json"
    _write_config(config, crypto)

    # When: the real console script runs twice against the fake Gateway CLI
    first = run_fake_cli(config, env)
    first_state = FakeLedger.model_validate_json(state_path.read_text(encoding="utf-8"))
    encrypted_path = Path(env["TRADERBOT_DATA_DIR"]) / "secrets" / "secrets.json"
    encrypted_after_first = encrypted_path.read_bytes()
    second = run_fake_cli(config, env)
    second_state_text = state_path.read_text(encoding="utf-8")
    second_state = FakeLedger.model_validate_json(second_state_text)

    # Then: one selected agent is added and Gateway bootstrap is the final mutation
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stderr
    assert first_state.mutations.count("add:crypto") == 1
    assert first_state.mutations[-1] == "cron:add"
    assert second_state.mutations == first_state.mutations
    assert not [event for event in second_state.mutations if "sports" in event]
    assert not [event for event in second_state.mutations if event.startswith("forbidden:")]

    first_result = DeployResult.model_validate_json(first.stdout)
    second_result = DeployResult.model_validate_json(second.stdout)
    assert first_result.required_new_agent_paths == {"crypto": crypto}
    assert second_result.required_new_agent_paths == {}
    assert first_result.deployment_complete is False
    assert first_result.completed_steps == (1, 2, 3, 4, 5)
    assert first_result.remaining_steps == (6, 7, 8)
    assert second_state.agents["main"].workspace == str(tmp_path / "existing-main")
    assert second_state.agents["weather"].workspace == str(tmp_path / "nested" / "team" / "weather")

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    store = build_secrets_store()
    registry = ProfileRegistry()
    main_identity = store.get_profile_token("main")
    weather_identity = store.get_profile_token("weather")
    crypto_identity = store.get_profile_token("crypto")
    assert main_identity is not None
    assert weather_identity is not None
    assert crypto_identity is not None
    resolved = tuple(
        store.resolve_profile_token(identity["token"])
        for identity in (main_identity, weather_identity, crypto_identity)
    )
    assert all(identity is not None for identity in resolved)
    assert all(
        registry.get_profile(identity[0]) is not None
        for identity in resolved
        if identity is not None
    )
    exposed = first.stdout + first.stderr + second.stdout + second.stderr + second_state_text
    assert env["TRADERBOT_TEST_KALSHI_KEY"] not in exposed
    assert env["TRADERBOT_TEST_KALSHI_PEM"] not in exposed
    assert env["TRADERBOT_TEST_KALSHI_KEY"].encode() not in encrypted_after_first
    assert env["TRADERBOT_TEST_KALSHI_PEM"].encode() not in encrypted_after_first
    assert encrypted_path.read_bytes() == encrypted_after_first

    data_root = Path(env["TRADERBOT_DATA_DIR"])
    expected_databases = {
        data_root / "backtest-weather" / "db" / "decisions.db",
        data_root / "backtest-crypto" / "db" / "decisions.db",
    }
    assert all(path.is_file() for path in expected_databases)
    assert not tuple(data_root.glob("*-sysadmin/db/decisions.db"))
    assert stat.S_IMODE((data_root / "chromadb").stat().st_mode) == 0o700
    with ChromaStore(data_root / "chromadb") as chroma:
        assert chroma.list_collections() == []
    for path in expected_databases:
        with sqlite3.connect(path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
        assert len(tables - {"schema_version"}) == 7
    assert all(
        identity["token"] not in exposed
        for identity in (main_identity, weather_identity, crypto_identity)
    )


def test_real_cli_adopts_stable_nonzero_partial_creation(tmp_path: Path) -> None:
    # Given: the fake stable add commits config before returning nonzero malformed output
    state_path, env = build_fake_environment(tmp_path)
    _write_happy_state(state_path, tmp_path, "partial")
    crypto = tmp_path / "approved" / "crypto"
    config = tmp_path / "deploy.json"
    _write_config(config, crypto)

    # When: deploy and its rerun reconcile from post-exit inventory
    first = run_fake_cli(config, env)
    second = run_fake_cli(config, env)
    ledger = FakeLedger.model_validate_json(state_path.read_text(encoding="utf-8"))

    # Then: exact partial state is adopted once and converges
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stderr
    assert ledger.mutations.count("add:crypto") == 1
    assert ledger.agents["crypto"].workspace == str(crypto)


def test_real_cli_overlap_failure_is_read_only(tmp_path: Path) -> None:
    # Given: unselected sports owns an ancestor of requested crypto workspace
    state_path, env = build_fake_environment(tmp_path)
    _write_happy_state(state_path, tmp_path)
    crypto = tmp_path / "unselected-sports" / "crypto"
    config = tmp_path / "deploy.json"
    _write_config(config, crypto)

    # When: the real console script performs global ownership preflight
    result = run_fake_cli(config, env)
    ledger = FakeLedger.model_validate_json(state_path.read_text(encoding="utf-8"))

    # Then: it fails with only read-only commands and creates no workspace
    assert result.returncode == 1
    assert ledger.mutations == []
    assert crypto.exists() is False
    report = DeployResult.model_validate_json(result.stdout)
    assert report.success is False
    assert "overlaps configured owner" in report.steps[0].message
