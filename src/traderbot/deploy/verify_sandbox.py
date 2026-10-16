"""Probe the deployed Phase 5 Docker sandbox posture (plan todo 9; IS-4/D2/D4/D9/D10).

The read-only counterpoint to the step-7 apply (todo 8): every probe below
re-reads LIVE OpenClaw config via the T6 seams (:func:`openclaw.inspect_agents`
+ :func:`openclaw_config.read_config_value`) against the deployed
``agents.list[i]`` shape (T1: entries are rejected), and derives the desired
state ONLY from :func:`traderbot.sandbox.sandbox_config_for` with the image
passed explicitly as ``sandbox_image_tag(resolve_sandbox_dockerfile())`` —
never the model default.

Checks (typed ids in :class:`CheckId`; stable names the wizard step-8 report
depends on):

- ``sandbox_mode_readback`` — every selected sandboxed agent re-reads
  ``sandbox.mode == "all"`` exactly (D2).
- ``sandbox_posture_config`` — ``workspaceAccess``/``docker`` byte-match the
  desired-state builder, INCLUDING the D9 exactly-two dangerous-* set and the
  four A-DCFG-KEYS hardening keys (absence on a sandboxed agent = failure).
- ``sandbox_off_negative`` — main/sysadmin stay unsandboxed: no docker block,
  no sandboxed ladder mode (IS-2/DD-036; the deploy never writes their mode,
  so an unset mode satisfies the off posture — only an explicit sandboxed
  ladder value or a docker block is a violation).
- ``sandbox_image_presence`` — read-only ``docker image inspect`` of the D10
  tag through the T7 sanitized seam conventions (env allowlist, bounded
  timeout, NEVER ``docker -v``, never a ``/var/run/docker.sock`` bind, no
  mutating verb of any kind).

Evidence gate (dependency skip): the probes assert REQUIRED posture only when
a step-7 apply is recorded — the wizard threads the selected set through
``VerificationRequest.created_agents``, or a standalone run finds a persisted
``DeployState.step7_docker_fingerprint``. With neither, each probe SKIP-passes
with a typed ``sandbox_apply_absent`` reason instead of asserting state the
deployment never claimed. Reader-tolerant (D4): foreign or legacy docker
blocks never crash a probe — an admitted superset carrying every required key
byte-exact reports ``sandbox_posture_drift`` naming the foreign keys; a
missing required key byte-fails ``sandbox_posture_missing`` (absent block) or
``sandbox_posture_mismatch`` (absent/diverging leaf).

Read-only by construction: this module imports NO config write seam and runs
NO docker mutating verb (inspect only); probes never touch config or state.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, final

from traderbot.deploy.deploy_state import DeployStateError, load_deploy_state
from traderbot.deploy.openclaw import inspect_agents
from traderbot.deploy.openclaw_config import read_config_value
from traderbot.deploy.openclaw_models import (
    AgentInventory,
    ConfigReadState,
    JsonValue,
)
from traderbot.deploy.sandbox_build import SandboxBuildError, resolve_sandbox_dockerfile
from traderbot.deploy.verify_models import ProbeResult, VerificationRequest
from traderbot.deploy.wizard_state import DEV_LIAISON_AGENT_ID, SandboxLadderMode
from traderbot.sandbox import (
    EXPECTED_IMAGE_RE,
    DockerUnavailableError,
    assert_docker_available,
    sandbox_config_for,
    sandbox_image_tag,
)

__all__ = [
    "INSPECT_TIMEOUT_SECONDS",
    "ImageInspection",
    "ImageState",
    "SandboxVerifier",
    "inspect_sandbox_image",
]

# IS-2/DD-036: the never-sandboxed deploy surface (mirrors
# ``traderbot.sandbox._REFUSED_AGENTS``; duplicated deliberately so verify does
# not import a private name).
_OFF_AGENTS: Final = frozenset({"main", "sysadmin"})

# Bounded, local, inspect-only probe: ``docker image inspect`` never leaves the
# host (no network), so a short fixed budget suffices regardless of the
# request's RPC-oriented timeout.
INSPECT_TIMEOUT_SECONDS: Final = 10.0

# Child environment ALLOWLIST (T7 convention): nothing secret-bearing can leak
# to the docker CLI because it is never copied; DOCKER_HOST keeps a non-default
# daemon endpoint working. PYTHONPATH is deliberately absent — the inspect
# probe invokes no Python helper.
_INSPECT_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "DOCKER_HOST",
    }
)

# stderr markers distinguishing a reachable-daemon "No such image" from a dead
# daemon (same exit class; different remedies), mirroring T7's classifier.
_DAEMON_MARKERS: Final = (
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "error during connect",
)

_APPLY_REMEDY: Final = (
    "Remedy: re-run traderbot deploy with the step-7 sandbox apply approval"
    " (TRADERBOT_PHASE5_SANDBOX=1)"
)

_APPLY_ABSENT_MESSAGE: Final = (
    "no Phase 5 sandbox apply is recorded for this selection (no threaded selected "
    "agents, no step-7 docker fingerprint); posture is proven only after a deploy "
    "with the sandbox apply approval"
)

# ProbeResult.message is capped at 240 chars: divergent-agent lists must be
# clipped, never grown unbounded (an oversized message would raise and mask the
# real failure behind a check_exception).
_CLIP_LIMIT: Final = 3


class ImageState(StrEnum):
    """Typed outcome of one read-only ``docker image inspect`` probe."""

    PRESENT = "present"
    ABSENT = "absent"
    DAEMON_UNAVAILABLE = "daemon_unavailable"
    DOCKER_ABSENT = "docker_absent"
    PROBE_ERROR = "probe_error"


@dataclass(frozen=True, slots=True)
class ImageInspection:
    state: ImageState
    detail: str = ""


class InspectRunner(Protocol):
    """Explicit subprocess seam so tests never patch production internals."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def _default_runner(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=dict(env),
        timeout=timeout,
    )


def inspect_sandbox_image(
    image: str,
    *,
    runner: InspectRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = INSPECT_TIMEOUT_SECONDS,
) -> ImageInspection:
    """Read-only presence probe for the D10 sandbox image tag.

    Fixed argv ``docker image inspect <image>``: never ``-v``, never a bind
    mount, never a mutating verb. The tag must match the compiled D10 grammar
    (a floating ``:test`` tag is a probe error by construction). Docker absent
    from PATH is a distinct typed state so the caller dependency-skips with a
    reason instead of failing.
    """
    if EXPECTED_IMAGE_RE.fullmatch(image) is None:
        return ImageInspection(ImageState.PROBE_ERROR, "tag fails the D10 grammar")
    try:
        assert_docker_available()
    except DockerUnavailableError:
        return ImageInspection(ImageState.DOCKER_ABSENT)
    run = _default_runner if runner is None else runner
    source = os.environ if env is None else env
    child = {name: source[name] for name in _INSPECT_ENV_ALLOWLIST if name in source}
    try:
        completed = run(("docker", "image", "inspect", image), env=child, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ImageInspection(ImageState.PROBE_ERROR, str(exc))
    if completed.returncode == 0:
        return ImageInspection(ImageState.PRESENT)
    stderr = (completed.stderr or "").lower()
    if any(marker in stderr for marker in _DAEMON_MARKERS):
        return ImageInspection(ImageState.DAEMON_UNAVAILABLE)
    return ImageInspection(ImageState.ABSENT)


@dataclass(frozen=True, slots=True)
class _ProbeTarget:
    """One selected sandboxed agent resolved against the live inventory."""

    agent_id: str
    prefix: str
    workspace: Path
    ladder: SandboxLadderMode


def _clip(entries: list[str]) -> str:
    """Render at most _CLIP_LIMIT offenders plus a count of the remainder."""
    shown = entries[:_CLIP_LIMIT]
    suffix = "" if len(entries) <= _CLIP_LIMIT else f" +{len(entries) - _CLIP_LIMIT} more"
    return ", ".join(shown) + suffix


@final
class SandboxVerifier:
    """Dependency-gated probes over the live deployed sandbox posture."""

    __slots__ = ("_apply", "_image", "_image_computed", "request")

    def __init__(self, request: VerificationRequest) -> None:
        self.request = request
        self._apply: bool | None = None
        self._image: str | None = None
        self._image_computed: bool = False

    # --- shared gates -------------------------------------------------------

    def _apply_recorded(self) -> bool:
        """A step-7 apply is evidenced by the threaded selected set (the wizard
        path runs verification only after a completed apply) or by a persisted
        step-7 docker fingerprint (standalone re-verification). Anything else
        means no apply was recorded -> dependency skip with a reason."""
        if self._apply is None:
            if self.request.created_agents:
                self._apply = True
            else:
                try:
                    state = load_deploy_state(self.request.data_root)
                except DeployStateError:
                    state = None
                self._apply = state is not None and bool(state.step7_docker_fingerprint)
        return self._apply

    def _expected_image(self) -> str | None:
        """D10 tag from the pinned repo Dockerfile; None on any resolve failure."""
        if not self._image_computed:
            self._image_computed = True
            try:
                self._image = sandbox_image_tag(resolve_sandbox_dockerfile())
            except SandboxBuildError:
                self._image = None
        return self._image

    def _targets(self, inventory: AgentInventory) -> tuple[_ProbeTarget, ...] | ProbeResult | None:
        """The selected SANDBOXED agents with list-shaped read prefixes.

        None means no apply is recorded (the caller dependency-skips); a
        ProbeResult failure means a required agent is absent from the live
        inventory. main/sysadmin are excluded — they are the off-negative
        probe's surface (mirrors ``resolve_sandbox_targets``).
        """
        if not self._apply_recorded():
            return None
        index_by_id = {agent.id: index for index, agent in enumerate(inventory.root)}
        ids: tuple[str, ...] = self.request.created_agents
        if not ids:
            ids = tuple(category.value for category in self.request.categories)
            # GAP-13: dev-liaison is adopted-only — asserted standalone when
            # already present, never demanded into existence.
            if DEV_LIAISON_AGENT_ID in index_by_id:
                ids = (*ids, DEV_LIAISON_AGENT_ID)
        targets: list[_ProbeTarget] = []
        missing: list[str] = []
        for agent_id in ids:
            if agent_id in _OFF_AGENTS:
                continue
            index = index_by_id.get(agent_id)
            if index is None:
                missing.append(agent_id)
                continue
            summary = inventory.root[index]
            ladder: SandboxLadderMode = (
                "paper" if agent_id == DEV_LIAISON_AGENT_ID else self.request.mode
            )
            targets.append(
                _ProbeTarget(
                    agent_id=agent_id,
                    prefix=f"agents.list[{index}]",
                    workspace=Path(summary.workspace),
                    ladder=ladder,
                )
            )
        if missing:
            return ProbeResult.failed(
                "sandbox_target_missing",
                f"selected agents absent from the live inventory: {_clip(missing)}",
            )
        return tuple(targets)

    def _gated_targets(self) -> tuple[_ProbeTarget, ...] | ProbeResult:
        inventory = inspect_agents()
        if inventory is None:
            return ProbeResult.failed("inventory_unreadable", "Agent inventory is unreadable")
        targets = self._targets(inventory)
        if targets is None:
            return ProbeResult.skipped("sandbox_apply_absent", _APPLY_ABSENT_MESSAGE)
        return targets

    def _live_sandbox(self, target: _ProbeTarget) -> dict[str, JsonValue] | None | ProbeResult:
        """Identity-guarded read of one agent's sandbox subtree (fail closed).

        The ``agents.list[i].id`` re-read must still name the agent — a
        re-ordered list would attribute another agent's posture, so the probe
        refuses rather than guesses. Returns None when the subtree is ABSENT,
        the parsed object when FOUND, or a failure ProbeResult.
        """
        identity = read_config_value(f"{target.prefix}.id")
        if identity.state is not ConfigReadState.FOUND or identity.value != target.agent_id:
            return ProbeResult.failed(
                "sandbox_identity_drift",
                f"agents.list identity drifted under {target.prefix} during verification",
            )
        read = read_config_value(f"{target.prefix}.sandbox")
        if read.state is ConfigReadState.FAILED:
            return ProbeResult.failed(
                "config_unreadable", f"sandbox config unreadable for {target.agent_id}"
            )
        if read.state is ConfigReadState.ABSENT:
            return None
        if not isinstance(read.value, dict):
            return ProbeResult.failed(
                "sandbox_posture_malformed",
                f"sandbox block for {target.agent_id} is not a JSON object",
            )
        return read.value

    # --- probes ---------------------------------------------------------------

    def mode_readback(self) -> ProbeResult:
        """D2: every selected sandboxed agent re-reads mode ``all`` exactly."""
        gated = self._gated_targets()
        if isinstance(gated, ProbeResult):
            return gated
        divergent: list[str] = []
        for target in gated:
            live = self._live_sandbox(target)
            if isinstance(live, ProbeResult):
                return live
            mode = live.get("mode") if live is not None else None
            if mode == "all":
                continue
            actual = mode if isinstance(mode, str) else "unset" if mode is None else "malformed"
            divergent.append(f"{target.agent_id}={actual}")
        if divergent:
            return ProbeResult.failed(
                "sandbox_mode_mismatch",
                f"sandboxed agents must run mode all: {_clip(divergent)}. {_APPLY_REMEDY}",
            )
        return ProbeResult.passed(
            "sandbox_mode_exact", f"{len(gated)} sandboxed agent(s) run mode all"
        )

    def posture_config(self) -> ProbeResult:
        """D4/D9/A-DCFG-KEYS: workspaceAccess + docker byte-match the desired
        builder — required-key absence or value drift FAILs; a foreign-key
        superset is admitted as named drift, never a crash."""
        gated = self._gated_targets()
        if isinstance(gated, ProbeResult):
            return gated
        image = self._expected_image()
        if image is None:
            return ProbeResult.failed(
                "sandbox_image_unverifiable",
                "install/docker/Dockerfile is missing or its provenance pin drifted — the "
                "expected image tag cannot be derived. Remedy: restore the pinned "
                "Dockerfile (digest pinned by install/docker/build-sandbox.sh)",
            )
        for target in gated:
            live = self._live_sandbox(target)
            if isinstance(live, ProbeResult):
                return live
            if live is None:
                return ProbeResult.failed(
                    "sandbox_posture_missing",
                    f"{target.agent_id} is selected but carries no sandbox block — "
                    f"unsandboxed posture. {_APPLY_REMEDY}",
                )
            problem = self._posture_diff(target, live, image)
            if problem is not None:
                return problem
        return ProbeResult.passed(
            "sandbox_posture_exact",
            f"{len(gated)} sandboxed agent(s) byte-match the desired posture",
        )

    def _posture_diff(
        self, target: _ProbeTarget, live: dict[str, JsonValue], image: str
    ) -> ProbeResult | None:
        desired = sandbox_config_for(
            target.agent_id,
            self.request.data_root,
            target.workspace,
            mode=target.ladder,
            image=image,
        ).to_openclaw_keys()
        desired_docker = desired["docker"]
        assert isinstance(desired_docker, dict)  # the builder always emits an object
        if live.get("workspaceAccess") != desired["workspaceAccess"]:
            return ProbeResult.failed(
                "sandbox_posture_mismatch",
                f"{target.agent_id}: sandbox.workspaceAccess is "
                f"{live.get('workspaceAccess')!r}, want 'none'. {_APPLY_REMEDY}",
            )
        docker = live.get("docker")
        if docker is None:
            return ProbeResult.failed(
                "sandbox_posture_missing",
                f"{target.agent_id}: sandbox.docker is absent on a sandboxed agent. "
                f"{_APPLY_REMEDY}",
            )
        if not isinstance(docker, dict):
            return ProbeResult.failed(
                "sandbox_posture_malformed",
                f"{target.agent_id}: sandbox.docker is not a JSON object",
            )
        problems: list[str] = []
        for leaf, want in desired_docker.items():
            if leaf not in docker:
                problems.append(f"docker.{leaf} missing")
            elif docker[leaf] != want:
                problems.append(f"docker.{leaf} differs")
        if problems:
            return ProbeResult.failed(
                "sandbox_posture_mismatch",
                f"{target.agent_id}: {_clip(problems)}. {_APPLY_REMEDY}",
            )
        foreign = sorted(set(docker) - set(desired_docker))
        foreign_scope = sorted(set(live) - {"mode", "workspaceAccess", "docker"})
        if foreign or foreign_scope:
            named = _clip([*(f"docker.{key}" for key in foreign), *foreign_scope])
            return ProbeResult.failed(
                "sandbox_posture_drift",
                f"{target.agent_id}: foreign keys beyond the pinned D9/A-DCFG-KEYS "
                f"surface: {named}. Remedy: remove the extra keys so the sandbox block "
                "matches the deploy-written posture exactly",
            )
        return None

    def off_negative(self) -> ProbeResult:
        """IS-2/D2: main/sysadmin stay unsandboxed — no docker block, and no
        sandboxed ladder mode (the deploy asserts mode off and writes nothing,
        so an unset mode already satisfies the off posture)."""
        if not self._apply_recorded():
            return ProbeResult.skipped("sandbox_apply_absent", _APPLY_ABSENT_MESSAGE)
        inventory = inspect_agents()
        if inventory is None:
            return ProbeResult.failed("inventory_unreadable", "Agent inventory is unreadable")
        for index, summary in enumerate(inventory.root):
            if summary.id not in _OFF_AGENTS:
                continue
            live = self._live_sandbox(
                _ProbeTarget(
                    agent_id=summary.id,
                    prefix=f"agents.list[{index}]",
                    workspace=Path(summary.workspace),
                    ladder="backtest",
                )
            )
            if isinstance(live, ProbeResult):
                return live
            if live is None:
                continue
            if "docker" in live:
                return ProbeResult.failed(
                    "sandbox_off_violation",
                    f"{summary.id} must stay unsandboxed but carries a sandbox.docker "
                    "block. Remedy: unset the sandbox.docker key for this agent "
                    "(main/sysadmin are never sandboxed; IS-2/DD-036)",
                )
            mode = live.get("mode")
            if mode not in (None, "off"):
                return ProbeResult.failed(
                    "sandbox_off_violation",
                    f"{summary.id} must stay unsandboxed but reads sandbox mode {mode!r}. "
                    "Remedy: set sandbox.mode to off (main/sysadmin are never sandboxed; "
                    "IS-2/DD-036)",
                )
        return ProbeResult.passed(
            "sandbox_off_exact", "main/sysadmin run unsandboxed with no docker block"
        )

    def image_presence(self) -> ProbeResult:
        """D10: the content-addressed sandbox image is present in the local
        daemon. Host-local and inspect-only; dependency-skipped (typed reason)
        when no apply is recorded or the docker CLI is absent."""
        if not self._apply_recorded():
            return ProbeResult.skipped("sandbox_apply_absent", _APPLY_ABSENT_MESSAGE)
        image = self._expected_image()
        if image is None:
            return ProbeResult.failed(
                "sandbox_image_unverifiable",
                "install/docker/Dockerfile is missing or its provenance pin drifted — the "
                "expected image tag cannot be derived. Remedy: restore the pinned "
                "Dockerfile (digest pinned by install/docker/build-sandbox.sh)",
            )
        inspection = inspect_sandbox_image(image)
        if inspection.state is ImageState.DOCKER_ABSENT:
            return ProbeResult.skipped(
                "docker_unavailable",
                "docker CLI is not on PATH; image presence skipped with the posture "
                "otherwise asserted. Remedy: install Docker (or start the daemon, e.g. "
                "systemctl start docker) and re-run traderbot verify",
            )
        if inspection.state is ImageState.PRESENT:
            return ProbeResult.passed("sandbox_image_present", f"sandbox image {image} is present")
        if inspection.state is ImageState.ABSENT:
            return ProbeResult.failed(
                "sandbox_image_absent",
                f"sandbox image {image} is absent while the posture asserts it. Remedy: "
                "build it via install/docker/build-sandbox.sh (or re-run traderbot "
                "deploy so step 7 builds it) before agents spawn",
            )
        if inspection.state is ImageState.DAEMON_UNAVAILABLE:
            return ProbeResult.failed(
                "sandbox_image_probe_failed",
                f"docker daemon is unreachable; image presence unreadable ({image}). "
                "Remedy: start the daemon (e.g. systemctl start docker) and re-run "
                "traderbot verify",
            )
        return ProbeResult.failed(
            "sandbox_image_probe_failed",
            f"docker image inspect failed for {image}: {inspection.detail or 'error'}",
        )
