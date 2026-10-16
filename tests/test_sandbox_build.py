"""Sanctioned docker build-seam tests (plan todo T7; D7/NOTE A).

Unit coverage for ``traderbot.deploy.sandbox_build``: fail-closed Dockerfile
resolution + provenance drift detection, the explicit runner/env seams, typed
build-failure classification, and the D7 presence gate. The full recording-
emulator canary (a real fake-docker subprocess) lives in
``tests/test_deploy_integration.py``.

Each test carries a short test-map comment naming the decision it enforces.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from traderbot.deploy.sandbox_build import (
    BUILD_TIMEOUT_SECONDS,
    SandboxDockerfileNotFoundError,
    SandboxImageBuildError,
    SandboxProvenanceError,
    build_sandbox_image,
    ensure_docker_available,
    resolve_sandbox_dockerfile,
)
from traderbot.sandbox import DockerUnavailableError, sandbox_image_tag

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_DOCKERFILE = _REPO_ROOT / "install" / "docker" / "Dockerfile"
_PINNED_DIGEST = "a1a6482142a45c3e017a2bb6b172719d3019f5c1f4034cb47da96565ebefaac2"


class _RecordingRunner:
    """Records the seam call and returns/raises a configured outcome."""

    def __init__(
        self,
        *,
        result: subprocess.CompletedProcess[str] | None = None,
        raises: BaseException | None = None,
    ) -> None:
        self.result = result
        self.raises = raises
        self.calls: list[tuple[tuple[str, ...], dict[str, str], Path, float]] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(argv), dict(env), cwd, timeout))
        if self.raises is not None:
            raise self.raises
        assert self.result is not None
        return self.result


def _write_repo(root: Path, *, dockerfile: str, script: str) -> None:
    install = root / "install" / "docker"
    install.mkdir(parents=True)
    (install / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    (install / "build-sandbox.sh").write_text(script, encoding="utf-8")


def _pin_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_resolve_returns_verified_repo_dockerfile() -> None:
    # Test-map: D10 — the default resolver returns the checkout's Dockerfile and
    # accepts it only because the build script's pin matches its bytes.
    resolved = resolve_sandbox_dockerfile()
    assert resolved == _REAL_DOCKERFILE
    assert resolved.is_file()
    assert sandbox_image_tag(resolved) == "traderbot-sandbox:da1a64821"


def test_resolve_fails_closed_when_dockerfile_absent(tmp_path: Path) -> None:
    # Test-map: D10 fail-closed — no Dockerfile anywhere means no guess: a typed
    # error with a remedy, never a silent path.
    (tmp_path / "install" / "docker").mkdir(parents=True)
    with pytest.raises(SandboxDockerfileNotFoundError):
        resolve_sandbox_dockerfile(repo_root=tmp_path)


def test_resolve_fails_closed_when_build_script_absent(tmp_path: Path) -> None:
    # Test-map: D10 fail-closed — the Dockerfile alone is not buildable without
    # the sanctioned entry-point script; absence aborts.
    install = tmp_path / "install" / "docker"
    install.mkdir(parents=True)
    (install / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    with pytest.raises(SandboxDockerfileNotFoundError):
        resolve_sandbox_dockerfile(repo_root=tmp_path)


def test_resolve_fails_closed_on_provenance_drift(tmp_path: Path) -> None:
    # Test-map: D10/stubbed-artifact — a Dockerfile whose bytes no longer match
    # the pinned digest is refused rather than built.
    dockerfile = "FROM scratch\n"
    _write_repo(
        tmp_path,
        dockerfile=dockerfile,
        script=f"# DOCKERFILE_SHA256={_pin_for('something else')}\nset -eu\n",
    )
    with pytest.raises(SandboxProvenanceError):
        resolve_sandbox_dockerfile(repo_root=tmp_path)


def test_resolve_fails_closed_when_pin_is_missing(tmp_path: Path) -> None:
    # Test-map: D10 — an unpinned script cannot vouch for the Dockerfile bytes;
    # the resolver refuses instead of trusting.
    _write_repo(tmp_path, dockerfile="FROM scratch\n", script="#!/bin/sh\nset -eu\n")
    with pytest.raises(SandboxProvenanceError):
        resolve_sandbox_dockerfile(repo_root=tmp_path)


def test_resolve_accepts_matching_pin(tmp_path: Path) -> None:
    # Test-map: D10 — positive control: a correct pin resolves cleanly.
    dockerfile = "FROM scratch\n"
    _write_repo(
        tmp_path,
        dockerfile=dockerfile,
        script=f"# DOCKERFILE_SHA256={_pin_for(dockerfile)}\nset -eu\n",
    )
    assert resolve_sandbox_dockerfile(repo_root=tmp_path).name == "Dockerfile"


def test_ensure_docker_available_is_presence_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test-map: D7 — presence gate only. An empty PATH raises the typed error;
    # a PATH with a docker entry passes, and no daemon call is ever made.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(DockerUnavailableError):
        ensure_docker_available()

    # Portable presence: patch the ``shutil.which`` the production code calls
    # (a POSIX sh shim named ``docker`` is not executable on win32, and an
    # executable shim would be executed — violating the no-daemon-call intent).
    monkeypatch.setattr(
        "shutil.which", lambda name: "/fake/bin/docker" if name == "docker" else None
    )
    ensure_docker_available()  # must not raise and must not execute docker


def test_build_invokes_script_with_filtered_env_and_bounded_timeout() -> None:
    # Test-map: D7/#448-class — the seam runs the sole entry-point script once,
    # with a bounded timeout and an allowlisted env that carries no TraderBot
    # secret; PYTHONPATH is pinned to the checkout src.
    result = subprocess.CompletedProcess([], 0, "traderbot-sandbox:da1a64821\n", "")
    runner = _RecordingRunner(result=result)
    outcome = build_sandbox_image(
        runner=runner,
        env={
            "PATH": "/usr/bin",
            "HOME": "/home/tester",
            "PYTHONPATH": "/pre-existing",
            "TRADERBOT_TEST_KALSHI_KEY": "topsecretkey",
            "KALSHI_PRIVATE_KEY_PEM": "-----BEGIN PRIVATE KEY-----",
        },
    )

    assert len(runner.calls) == 1
    argv, child_env, cwd, timeout = runner.calls[0]
    assert argv == ("sh", str(_REPO_ROOT / "install" / "docker" / "build-sandbox.sh"))
    assert cwd == _REPO_ROOT
    assert timeout == BUILD_TIMEOUT_SECONDS
    assert child_env["PATH"] == "/usr/bin"
    assert child_env["HOME"] == "/home/tester"
    assert child_env["PYTHONPATH"] == os.pathsep.join((str(_REPO_ROOT / "src"), "/pre-existing"))
    assert "TRADERBOT_TEST_KALSHI_KEY" not in child_env
    assert "KALSHI_PRIVATE_KEY_PEM" not in child_env
    assert outcome.image == "traderbot-sandbox:da1a64821"
    assert outcome.dockerfile == _REAL_DOCKERFILE
    assert outcome.script == _REPO_ROOT / "install" / "docker" / "build-sandbox.sh"
    assert outcome.context == _REPO_ROOT / "install" / "docker"


def test_build_allows_absent_optional_env() -> None:
    # Test-map: #448-class — with no env supplied the allowlist copies only what
    # os.environ actually has; PYTHONPATH still points at the checkout src.
    result = subprocess.CompletedProcess([], 0, "", "")
    runner = _RecordingRunner(result=result)
    _ = build_sandbox_image(runner=runner, env={"PATH": "/usr/bin"})
    _, child_env, _, _ = runner.calls[0]
    assert child_env["PYTHONPATH"] == str(_REPO_ROOT / "src")
    assert set(child_env) <= {"PATH", "PYTHONPATH"}


def test_build_maps_daemon_failure_to_typed_error_with_remedy() -> None:
    # Test-map: D7 — a non-zero exit with daemon stderr maps to the typed error,
    # classifies the cause, and attaches the docker stderr verbatim.
    stderr = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock."
    runner = _RecordingRunner(result=subprocess.CompletedProcess([], 125, "", stderr))
    with pytest.raises(SandboxImageBuildError) as caught:
        build_sandbox_image(runner=runner)
    assert caught.value.cause == "daemon-unavailable"
    assert caught.value.stderr == stderr
    assert caught.value.image == "traderbot-sandbox:da1a64821"
    assert "install/start Docker" in str(caught.value)


def test_build_maps_pull_failure_to_typed_error() -> None:
    # Test-map: Metis 4.3 — a base-image pull failure is classified distinctly so
    # a Docker Hub rate limit is never read as a code defect.
    stderr = "toomanyrequests: You have reached your pull rate limit."
    runner = _RecordingRunner(result=subprocess.CompletedProcess([], 1, "", stderr))
    with pytest.raises(SandboxImageBuildError) as caught:
        build_sandbox_image(runner=runner)
    assert caught.value.cause == "base-image-pull"
    assert "Docker Hub" in str(caught.value)


def test_build_maps_generic_failure_to_build_error() -> None:
    # Test-map: D7 — any other non-zero exit is a compile-time build failure with
    # stderr attached.
    runner = _RecordingRunner(result=subprocess.CompletedProcess([], 1, "", "boom"))
    with pytest.raises(SandboxImageBuildError) as caught:
        build_sandbox_image(runner=runner)
    assert caught.value.cause == "build-failure"
    assert caught.value.stderr == "boom"


def test_build_maps_timeout_to_typed_error() -> None:
    # Test-map: D7 — the bounded timeout is enforced and surfaces as a typed cause.
    runner = _RecordingRunner(raises=subprocess.TimeoutExpired("sh", 1.0))
    with pytest.raises(SandboxImageBuildError) as caught:
        build_sandbox_image(runner=runner)
    assert caught.value.cause == "timeout"


def test_build_maps_exec_failure_to_daemon_error() -> None:
    # Test-map: D7 — an OSError from the seam (e.g. sh unavailable) is typed, not
    # a raw traceback.
    runner = _RecordingRunner(raises=OSError("no sh"))
    with pytest.raises(SandboxImageBuildError) as caught:
        build_sandbox_image(runner=runner)
    assert caught.value.cause == "daemon-unavailable"
    assert "no sh" in str(caught.value)


def test_build_refuses_before_running_on_provenance_drift(tmp_path: Path) -> None:
    # Test-map: D7/stubbed-artifact — the provenance check runs BEFORE any
    # subprocess: a drifted Dockerfile never reaches the runner.
    dockerfile = "FROM scratch\n"
    _write_repo(
        tmp_path,
        dockerfile=dockerfile,
        script=f"# DOCKERFILE_SHA256={_pin_for('other')}\nset -eu\n",
    )
    runner = _RecordingRunner(result=subprocess.CompletedProcess([], 0, "", ""))
    with pytest.raises(SandboxProvenanceError):
        build_sandbox_image(repo_root=tmp_path, runner=runner)
    assert runner.calls == []


def test_real_dockerfile_matches_committed_pin() -> None:
    # Test-map: D10/stubbed-artifact — the checked-in Dockerfile still hashes to
    # the digest recorded in the plan, so the artifact was not silently swapped.
    assert hashlib.sha256(_REAL_DOCKERFILE.read_bytes()).hexdigest() == _PINNED_DIGEST


def _lf_normalized(data: bytes) -> bytes:
    """Collapse CRLF/CR line endings to LF, mirroring sandbox._lf_normalized_sha256."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _crlf_variant(data: bytes) -> bytes:
    """Return the bytes a Windows ``core.autocrlf=true`` checkout would produce."""
    return _lf_normalized(data).replace(b"\n", b"\r\n")


def test_real_dockerfile_pin_holds_under_crlf_checkout() -> None:
    # Test-map: D10 + CI-autocrlf — a Windows checkout stores CRLF bytes on
    # disk; LF normalization must still match the exact pinned digest, while
    # the raw CRLF hash would have drifted (proves the exercise is real).
    content = _REAL_DOCKERFILE.read_bytes()
    crlf = _crlf_variant(content)
    assert crlf != content
    assert hashlib.sha256(crlf).hexdigest() != _PINNED_DIGEST
    assert hashlib.sha256(_lf_normalized(crlf)).hexdigest() == _PINNED_DIGEST
    assert hashlib.sha256(_lf_normalized(content)).hexdigest() == _PINNED_DIGEST


def test_resolve_and_tag_are_stable_for_lf_and_crlf_copies(tmp_path: Path) -> None:
    # Test-map: D10 + CI-autocrlf — provenance resolution succeeds on BOTH the
    # LF and CRLF disk copies of the same Dockerfile, and both derive the
    # identical content-addressed tag.
    content = _REAL_DOCKERFILE.read_bytes()
    script = (_REPO_ROOT / "install" / "docker" / "build-sandbox.sh").read_bytes()
    resolved: dict[str, Path] = {}
    for label, payload in (("lf", _lf_normalized(content)), ("crlf", _crlf_variant(content))):
        install = tmp_path / label / "install" / "docker"
        install.mkdir(parents=True)
        (install / "Dockerfile").write_bytes(payload)
        (install / "build-sandbox.sh").write_bytes(script)
        resolved[label] = resolve_sandbox_dockerfile(repo_root=tmp_path / label)
    assert sandbox_image_tag(resolved["lf"]) == "traderbot-sandbox:da1a64821"
    assert sandbox_image_tag(resolved["crlf"]) == "traderbot-sandbox:da1a64821"


def test_resolve_fails_closed_on_content_change_despite_normalization(
    tmp_path: Path,
) -> None:
    # Test-map: D10 fail-closed — EOL normalization never masks a real content
    # change: one added line still trips the pinned digest.
    install = tmp_path / "install" / "docker"
    install.mkdir(parents=True)
    changed = _crlf_variant(_REAL_DOCKERFILE.read_bytes()) + b"# drifted\r\n"
    (install / "Dockerfile").write_bytes(changed)
    (install / "build-sandbox.sh").write_bytes(
        (_REPO_ROOT / "install" / "docker" / "build-sandbox.sh").read_bytes()
    )
    with pytest.raises(SandboxProvenanceError):
        resolve_sandbox_dockerfile(repo_root=tmp_path)


def test_build_with_injected_runner_needs_no_docker_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test-map: D7 + CI-no-docker — with an injected runner the host docker CLI
    # is irrelevant: an EMPTY PATH must not stop the build (the macOS CI host).
    monkeypatch.setenv("PATH", str(tmp_path))
    runner = _RecordingRunner(result=subprocess.CompletedProcess([], 0, "ok\n", ""))
    outcome = build_sandbox_image(runner=runner)
    assert outcome.image == "traderbot-sandbox:da1a64821"


def test_default_runner_fails_closed_without_docker_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test-map: D7 fail-closed — the DEFAULT runner still gates on the docker
    # CLI; only an injected runner skips the host toolchain.
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(DockerUnavailableError):
        build_sandbox_image()
