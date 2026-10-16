from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import final

import pytest

from traderbot.db.decisions import init_decisions_db
from traderbot.db.migrations import init_schema
from traderbot.deploy import verify_sandbox
from traderbot.deploy.verify_models import CheckId, CheckStatus, ProbeResult, VerificationRequest
from traderbot.deploy.verify_ports import ProductionVerificationPorts
from traderbot.deploy.verify_sandbox import ImageInspection, ImageState
from traderbot.deploy.verify_storage import decisions_databases, global_database
from traderbot.deploy.verify_tokens import TokenVerifier, auth_mode
from traderbot.kalshi.order_models import MarketCategory
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.sandbox import DockerUnavailableError
from traderbot.secrets.store import SecretsStore


@final
class MemoryStore:
    __slots__ = ("values",)

    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], str] = {}

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        return self.values.get((service, key, namespace))

    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None:
        self.values[(service, key, namespace)] = value

    def delete(self, service: str, key: str, namespace: str = "global") -> None:
        del self.values[(service, key, namespace)]

    def get_namespace(self, namespace: str) -> dict[str, str]:
        return {
            f"{service}_{key}": value
            for (service, key, stored_namespace), value in self.values.items()
            if stored_namespace == namespace
        }


def _request(root: Path) -> VerificationRequest:
    return VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        data_root=root,
    )


def test_database_probes_leave_files_byte_and_metadata_identical(tmp_path: Path) -> None:
    # Given
    global_path = tmp_path / "traderbot.db"
    decisions_path = tmp_path / "backtest-weather" / "db" / "decisions.db"
    init_schema(global_path)
    decisions_path.parent.mkdir(parents=True)
    init_decisions_db(decisions_path)
    before = {
        path: (
            hashlib.sha256(path.read_bytes()).digest(),
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for path in (global_path, decisions_path)
    }

    # When
    global_result = global_database(_request(tmp_path))
    decisions_result = decisions_databases(_request(tmp_path))

    # Then
    assert global_result.status is CheckStatus.PASS
    assert decisions_result.status is CheckStatus.PASS
    assert before == {
        path: (
            hashlib.sha256(path.read_bytes()).digest(),
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for path in (global_path, decisions_path)
    }
    assert not list(tmp_path.rglob("*-wal"))
    assert not list(tmp_path.rglob("*-shm"))
    assert not list(tmp_path.rglob("*-journal"))


def test_forbidden_sysadmin_decisions_db_fails(tmp_path: Path) -> None:
    # Given
    forbidden = tmp_path / "paper-sysadmin" / "db" / "decisions.db"
    forbidden.parent.mkdir(parents=True)
    forbidden.touch()

    # When
    result = decisions_databases(_request(tmp_path))

    # Then
    assert result.action == "sysadmin_db_forbidden"


def test_token_probe_returns_secret_without_exposing_value(tmp_path: Path) -> None:
    # Given
    local = MemoryStore()
    store = SecretsStore(local_store=local)
    profile = create_sysadmin_profile()
    store.store_profile_token(
        "main",
        "TOKEN-CANARY",
        profile.name,
        [category.value for category in profile.enabled_categories],
        profile.permissions,
    )
    store.store_profile_token("weather", "WEATHER-CANARY", "weather", ["weather"], [])
    request = _request(tmp_path)

    # When
    result = TokenVerifier(request, store).inspect()

    # Then
    assert result.result.status is CheckStatus.PASS
    assert "CANARY" not in repr(result)
    assert "CANARY" not in result.model_dump_json()


def test_exact_auth_mode_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    # When / Then
    for value in (None, "", "false", "1"):
        if value is None:
            monkeypatch.delenv("TRADERBOT_USE_HARDCODED_AUTH", raising=False)
        else:
            monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", value)
        assert auth_mode().status is CheckStatus.FAIL
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")
    assert auth_mode().status is CheckStatus.PASS


# --- todo 9 (GAP-6): sandbox posture dispatch + inspect seam -------------------


@final
class _StubSandbox:
    __slots__ = ("calls",)

    def __init__(self, _request: VerificationRequest) -> None:
        self.calls: list[str] = []

    def mode_readback(self) -> ProbeResult:
        self.calls.append("mode_readback")
        return ProbeResult.passed("sandbox_mode_exact")

    def posture_config(self) -> ProbeResult:
        self.calls.append("posture_config")
        return ProbeResult.passed("sandbox_posture_exact")

    def off_negative(self) -> ProbeResult:
        self.calls.append("off_negative")
        return ProbeResult.passed("sandbox_off_exact")

    def image_presence(self) -> ProbeResult:
        self.calls.append("image_presence")
        return ProbeResult.passed("sandbox_image_present")


def test_probe_dispatches_each_sandbox_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _StubSandbox(_request(tmp_path))
    monkeypatch.setattr("traderbot.deploy.verify_ports.SandboxVerifier", lambda _request: sandbox)
    ports = ProductionVerificationPorts(_request(tmp_path))
    expected = {
        CheckId.SANDBOX_MODE_READBACK: "mode_readback",
        CheckId.SANDBOX_POSTURE_CONFIG: "posture_config",
        CheckId.SANDBOX_OFF_NEGATIVE: "off_negative",
        CheckId.SANDBOX_IMAGE_PRESENCE: "image_presence",
    }
    for check_id, method in expected.items():
        result = asyncio.run(ports.probe(check_id))
        assert result.status is CheckStatus.PASS
        assert sandbox.calls[-1] == method
    assert sandbox.calls == list(expected.values())


def test_inspect_sandbox_image_argv_env_timeout_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # T7/D7 conventions on the read-only seam: fixed inspect-only argv (never
    # -v, never a docker.sock bind or mutating verb), allowlisted child env,
    # bounded caller-controlled timeout.
    monkeypatch.setattr(verify_sandbox, "assert_docker_available", lambda: None)
    seen_argv: list[tuple[str, ...]] = []
    seen_env: list[dict[str, str]] = []
    seen_timeout: list[float] = []

    def runner(
        argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        seen_argv.append(tuple(argv))
        seen_env.append(dict(env))
        seen_timeout.append(timeout)
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    inspection = verify_sandbox.inspect_sandbox_image(
        "traderbot-sandbox:daabbccdd",
        runner=runner,
        env={"PATH": "/usr/bin", "DOCKER_HOST": "unix:///run/docker.sock", "AWS_TOKEN": "x"},
        timeout=3.0,
    )
    assert inspection.state is ImageState.PRESENT
    argv = seen_argv[0]
    assert argv == ("docker", "image", "inspect", "traderbot-sandbox:daabbccdd")
    assert "-v" not in argv
    assert not any("docker.sock" in part for part in argv)
    assert seen_timeout == [3.0]
    # The sentinel secret is not in the allowlist and never reaches the child.
    assert set(seen_env[0]) == {"PATH", "DOCKER_HOST"}


def _inspection_for(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    stderr: str = "",
    side_effect: BaseException | None = None,
    image: str = "traderbot-sandbox:daabbccdd",
) -> ImageInspection:
    monkeypatch.setattr(verify_sandbox, "assert_docker_available", lambda: None)

    def runner(
        argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        _ = env, timeout
        if side_effect is not None:
            raise side_effect
        return subprocess.CompletedProcess(list(argv), returncode, "", stderr)

    inspection = verify_sandbox.inspect_sandbox_image(image, runner=runner)
    return inspection


def test_inspect_sandbox_image_maps_states(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _inspection_for(monkeypatch, returncode=0).state is ImageState.PRESENT
    # A reachable daemon with no such image: absent, with no further parsing.
    assert _inspection_for(monkeypatch, returncode=1).state is ImageState.ABSENT
    # A dead daemon is a distinct state (different remedy than a missing image).
    assert (
        _inspection_for(
            monkeypatch,
            returncode=1,
            stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
        ).state
        is ImageState.DAEMON_UNAVAILABLE
    )
    assert (
        _inspection_for(monkeypatch, returncode=1, side_effect=OSError("exec failed")).state
        is ImageState.PROBE_ERROR
    )
    assert (
        _inspection_for(
            monkeypatch,
            returncode=1,
            side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10.0),
        ).state
        is ImageState.PROBE_ERROR
    )


def test_inspect_sandbox_image_rejects_floating_tags_without_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify_sandbox, "assert_docker_available", lambda: None)

    def runner(
        argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner must not be invoked for an invalid tag")

    inspection = verify_sandbox.inspect_sandbox_image("traderbot-sandbox:test", runner=runner)
    assert inspection.state is ImageState.PROBE_ERROR


def test_inspect_sandbox_image_skips_when_docker_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _absent() -> None:
        raise DockerUnavailableError("docker CLI is not on PATH")

    monkeypatch.setattr(verify_sandbox, "assert_docker_available", _absent)
    inspection = verify_sandbox.inspect_sandbox_image("traderbot-sandbox:daabbccdd")
    assert inspection.state is ImageState.DOCKER_ABSENT


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "fake-docker real-child harness is a POSIX sh shim; allowlisted-env "
        "assertion runs on POSIX CI lanes and win32 coverage stays with the "
        "recording-runner tests"
    ),
)
def test_inspect_sandbox_image_real_child_gets_allowlisted_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # End-to-end through a real subprocess with the existing fake-docker
    # convention: the fake records its argv and full environment; a sentinel
    # secret present in the parent environment must not leak to the child.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.log"
    env_log = tmp_path / "env.log"
    docker = bin_dir / "docker"
    _ = docker.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {argv_log}\nenv > {env_log}\nexit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("TRADERBOT_TEST_SENTINEL", "should-never-leak")
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    inspection = verify_sandbox.inspect_sandbox_image("traderbot-sandbox:daabbccdd")

    assert inspection.state is ImageState.PRESENT
    # One arg per line: exact inspect-only argv, no -v, no docker.sock bind.
    assert argv_log.read_text(encoding="utf-8").splitlines() == [
        "image",
        "inspect",
        "traderbot-sandbox:daabbccdd",
    ]
    child_env = env_log.read_text(encoding="utf-8")
    assert "should-never-leak" not in child_env
    assert "TRADERBOT" not in child_env
