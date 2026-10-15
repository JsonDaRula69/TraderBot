from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import ClassVar, Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, ConfigDict, Field

from tests.deploy_fake_openclaw import write_fake_openclaw
from traderbot.deploy.openclaw_models import CronJob, JsonValue
from traderbot.deploy.wizard_state import SecretRefConfig


class FakeAgentConfig(BaseModel):
    # Typed JSON values (not dict[str, str]): the realigned list-first fake stores
    # sandbox.docker.binds arrays and dangerous-* booleans structurally.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    heartbeat: dict[str, JsonValue] = Field(default_factory=dict)
    sandbox: dict[str, JsonValue] = Field(default_factory=dict)


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
    child_env = dict(env)
    project_root = Path(__file__).parents[1]
    child_env["PYTHONPATH"] = os.pathsep.join((str(project_root), str(project_root / "src")))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.deploy_cli_runner",
            "deploy",
            "--config",
            str(config),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
        env=child_env,
        cwd=cwd,
    )
