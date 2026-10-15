"""Sanctioned Docker image-build seam for deploy step 7 (plan T7; D7/NOTE A).

Exactly one code path in the repository invokes a Phase 5 sandbox image build:
this module. It resolves the repo Dockerfile (the D10 single source of truth),
verifies its provenance against the digest pinned in
``install/docker/build-sandbox.sh``, and runs that script — the repo's only build
entry-point — once, with a scrubbed environment and a bounded timeout.

Typed, fail-closed surface:

- :func:`resolve_sandbox_dockerfile` locates ``install/docker/Dockerfile`` from
  the checkout and FAILS CLOSED when the Dockerfile or the build script is absent,
  when the script carries no provenance pin, or when the pinned digest no longer
  matches the Dockerfile bytes (drift). It never guesses a path.
- :func:`ensure_docker_available` is the D7 presence gate. It delegates to
  :func:`traderbot.sandbox.assert_docker_available` (``shutil.which`` only) and
  NEVER shells out to ``docker info``/``docker version``; T8 composes the
  live-daemon gate separately.
- :func:`build_sandbox_image` runs ``build-sandbox.sh`` and returns a typed
  :class:`SandboxBuildResult`, or raises a typed :class:`SandboxImageBuildError`
  whose remedy names the cause (daemon unavailable vs base-image pull vs build
  failure vs timeout), so a Docker Hub rate limit is never mistaken for a defect.

Test seams are explicit parameters (``repo_root``, ``runner``, ``env``); tests
never monkey-patch production subprocess internals.

Subprocess hygiene (#448-class): the child environment is an allowlist of
operational variables (``PATH``, ``HOME``, locale, temp, ``PYTHONPATH``,
``DOCKER_HOST``); no TraderBot secret is forwarded — the build needs none. The
``PYTHONPATH`` entry is pinned to the checkout's ``src`` so the script's own
``python3`` tag derivation works even when the invoking interpreter is not the
project venv.

The image tag is ALWAYS computed by :func:`traderbot.sandbox.sandbox_image_tag`
from the resolved Dockerfile bytes; deploy/verify consumers pass the resulting
image explicitly and never rely on ``DockerSandboxConfig.image``'s default (that
default resolves the repo tree relative to the package and is unavailable in a
wheel install).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol

from traderbot.sandbox import (
    DockerUnavailableError,
    assert_docker_available,
    sandbox_image_tag,
)

__all__ = [
    "BUILD_TIMEOUT_SECONDS",
    "BuildFailureCause",
    "BuildRunner",
    "DockerUnavailableError",
    "SandboxBuildError",
    "SandboxBuildResult",
    "SandboxDockerfileNotFoundError",
    "SandboxImageBuildError",
    "SandboxProvenanceError",
    "build_sandbox_image",
    "ensure_docker_available",
    "resolve_sandbox_dockerfile",
]

_INSTALL_DOCKER_DIR: Final = ("install", "docker")
_DOCKERFILE_NAME: Final = "Dockerfile"
_BUILD_SCRIPT_NAME: Final = "build-sandbox.sh"

# The provenance pin lives in the build script header; the resolver recomputes
# the Dockerfile digest and refuses to build on drift or a missing pin.
_PROVENANCE_RE: Final = re.compile(r"DOCKERFILE_SHA256=([0-9a-f]{64})")

# Bounded build budget (IS-6 target is <=5 min on a warm host; 10 min leaves
# headroom for a cold base-image layer cache without ever hanging forever).
BUILD_TIMEOUT_SECONDS: Final = 600.0

# The child environment is an ALLOWLIST, not a denylist: nothing secret-bearing
# can leak because it is simply never copied. DOCKER_HOST is included so a
# non-default daemon endpoint still works (the script's docker CLI needs it);
# DOCKER_CONFIG is deliberately omitted — no registry auth is needed under
# --pull=false, and its credential file must not be discoverable from here.
_BUILD_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "SYSTEMROOT",
        "DOCKER_HOST",
    }
)

BuildFailureCause = Literal[
    "daemon-unavailable",
    "base-image-pull",
    "build-failure",
    "timeout",
]

_REMEDIES: Final[dict[BuildFailureCause, str]] = {
    "daemon-unavailable": (
        "install/start Docker (e.g. systemctl start docker) and re-run traderbot deploy"
    ),
    "base-image-pull": (
        "the digest-pinned base image could not be fetched — check Docker Hub access "
        + "(anonymous pull rate limits on shared daemons)"
    ),
    "build-failure": "the base image failed to build — inspect the attached docker stderr",
    "timeout": "the image build exceeded its time budget — re-run or raise the timeout",
}

_DAEMON_MARKERS: Final = (
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "error during connect",
    "docker: not found",
)

_PULL_MARKERS: Final = (
    "pull access denied",
    "manifest unknown",
    "not found: manifest",
    "toomanyrequests",
    "rate limit",
    "unauthorized",
)


class BuildRunner(Protocol):
    """Explicit subprocess seam so tests never patch production internals."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True)
class SandboxBuildResult:
    """Typed outcome of one sanctioned image build (D7 ordering input for T8)."""

    image: str
    dockerfile: Path
    context: Path
    script: Path
    stdout: str


class SandboxBuildError(RuntimeError):
    """Base class for typed failures raised by the sanctioned build seam."""


class SandboxDockerfileNotFoundError(SandboxBuildError):
    """The repo Dockerfile or its build script is absent (D10 fail-closed)."""


class SandboxProvenanceError(SandboxBuildError):
    """The Dockerfile bytes no longer match the pinned digest, or the pin is absent."""


class SandboxImageBuildError(SandboxBuildError):
    """``build-sandbox.sh`` could not produce the image (D7 fail-closed)."""

    def __init__(
        self,
        *,
        image: str,
        returncode: int,
        cause: BuildFailureCause,
        stderr: str = "",
    ) -> None:
        self.image: str = image
        self.returncode: int = returncode
        self.cause: BuildFailureCause = cause
        self.stderr: str = stderr
        super().__init__(self._render())

    def _render(self) -> str:
        detail = self.stderr.strip()
        tail = f" stderr: {detail}" if detail else ""
        remedy = _REMEDIES[self.cause]
        return (
            f"docker build of {self.image} failed "
            f"(exit {self.returncode}; cause={self.cause}): {remedy}.{tail}"
        )


def _default_repo_root() -> Path:
    """Repo root of the running checkout (``src/traderbot/deploy`` -> root)."""
    return Path(__file__).resolve().parents[3]


def _assert_provenance(dockerfile: Path, script: Path) -> None:
    """Fail closed unless the script pins the Dockerfile's exact sha256."""
    match = _PROVENANCE_RE.search(script.read_text(encoding="utf-8"))
    if match is None:
        raise SandboxProvenanceError(
            f"build script {script} carries no DOCKERFILE_SHA256=<64-hex> provenance "
            + "pin; refusing to build a Dockerfile whose bytes cannot be verified (D10)."
        )
    actual = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
    if actual != match.group(1):
        raise SandboxProvenanceError(
            f"sandbox Dockerfile provenance drift: {dockerfile} hashes to {actual} "
            + f"but {script} pins {match.group(1)}; refusing to build a drifted or "
            + "stubbed Dockerfile (D10)."
        )


def resolve_sandbox_dockerfile(*, repo_root: Path | None = None) -> Path:
    """Return the verified repo Dockerfile path, or fail closed (D10).

    Resolves ``install/docker/Dockerfile`` from the checkout (``repo_root``
    overrides the default location for tests). Raises
    :class:`SandboxDockerfileNotFoundError` when the Dockerfile or the build
    script is missing, and :class:`SandboxProvenanceError` on a missing pin or
    digest drift. Never guesses a fallback path.
    """
    root = _default_repo_root() if repo_root is None else repo_root
    dockerfile = root.joinpath(*_INSTALL_DOCKER_DIR, _DOCKERFILE_NAME)
    script = root.joinpath(*_INSTALL_DOCKER_DIR, _BUILD_SCRIPT_NAME)
    if not dockerfile.is_file():
        raise SandboxDockerfileNotFoundError(
            f"sandbox Dockerfile not found at {dockerfile} (D10 single source of truth). "
            + "Remedy: run deploy from a TraderBot checkout that contains "
            + "install/docker/Dockerfile."
        )
    if not script.is_file():
        raise SandboxDockerfileNotFoundError(
            f"sandbox build script not found at {script}. Remedy: run deploy from a "
            + "TraderBot checkout that contains install/docker/build-sandbox.sh."
        )
    _assert_provenance(dockerfile, script)
    return dockerfile


def ensure_docker_available() -> None:
    """D7 presence gate — delegates to :func:`traderbot.sandbox.assert_docker_available`.

    ``shutil.which`` only: no ``docker info``/``docker version`` daemon call. T8
    composes the live-daemon gate on top of this; the seam never network-tests.
    """
    assert_docker_available()


def _build_env(env: Mapping[str, str] | None, repo_root: Path) -> dict[str, str]:
    """Return the allowlisted child environment, with the checkout's ``src`` on PYTHONPATH."""
    source = os.environ if env is None else env
    child = {name: source[name] for name in _BUILD_ENV_ALLOWLIST if name in source}
    src_dir = repo_root / "src"
    existing = child.get("PYTHONPATH")
    child["PYTHONPATH"] = (
        str(src_dir) if not existing else os.pathsep.join((str(src_dir), existing))
    )
    return child


def _default_runner(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=dict(env),
        cwd=str(cwd),
        timeout=timeout,
    )


def _classify_failure(stderr: str) -> BuildFailureCause:
    """Map docker stderr onto a typed remedy so pull limits are not read as defects."""
    lowered = stderr.lower()
    if any(marker in lowered for marker in _DAEMON_MARKERS):
        return "daemon-unavailable"
    if any(marker in lowered for marker in _PULL_MARKERS):
        return "base-image-pull"
    return "build-failure"


def build_sandbox_image(
    *,
    repo_root: Path | None = None,
    runner: BuildRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = BUILD_TIMEOUT_SECONDS,
) -> SandboxBuildResult:
    """Build the Phase 5 sandbox image via ``install/docker/build-sandbox.sh`` once.

    The image tag is :func:`traderbot.sandbox.sandbox_image_tag` of the resolved
    Dockerfile. This function writes NO config and NO deploy state: it returns the
    typed result that step 7 (T8) orders *before* any config write (D7). Raises
    :class:`SandboxImageBuildError` (with the cause classified and docker stderr
    attached) on a non-zero exit, a timeout, or an exec failure.
    """
    root = _default_repo_root() if repo_root is None else repo_root
    dockerfile = resolve_sandbox_dockerfile(repo_root=root)
    script = root.joinpath(*_INSTALL_DOCKER_DIR, _BUILD_SCRIPT_NAME)
    context = root.joinpath(*_INSTALL_DOCKER_DIR)
    ensure_docker_available()
    image = sandbox_image_tag(dockerfile)
    run = _default_runner if runner is None else runner
    child_env = _build_env(env, root)
    argv = ("sh", str(script))
    try:
        completed = run(argv, env=child_env, cwd=root, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SandboxImageBuildError(
            image=image,
            returncode=-1,
            cause="timeout",
            stderr=str(exc),
        ) from exc
    except OSError as exc:
        raise SandboxImageBuildError(
            image=image,
            returncode=-1,
            cause="daemon-unavailable",
            stderr=str(exc),
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr or ""
        raise SandboxImageBuildError(
            image=image,
            returncode=completed.returncode,
            cause=_classify_failure(stderr),
            stderr=stderr,
        )
    return SandboxBuildResult(
        image=image,
        dockerfile=dockerfile,
        context=context,
        script=script,
        stdout=completed.stdout or "",
    )
