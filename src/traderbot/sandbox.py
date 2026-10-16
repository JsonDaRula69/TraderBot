"""TraderBot Phase 5 Docker sandbox containment — the single source of truth.

This module is the leaf both the deploy path and ``traderbot verify`` consume
(IS-5): it defines the per-agent Docker sandbox contract
(:class:`DockerSandboxConfig`), the D10 content-addressed image tag derivation
(:func:`sandbox_image_tag`), the hardened ``docker run`` renderer
(:func:`generate_docker_run_command`), the per-agent builder
(:func:`sandbox_config_for`), and the forbidden-mount guard
(:data:`FORBIDDEN_MOUNTS`, :func:`check_mount_allowed`).

Decision anchors:

- **D1** — explicit-binds mount contract: exactly two binds (own workspace
  read-only at ``/workspace`` first, own ``{mode}-{name}`` data dir read-write
  at ``/data`` second) plus the hardening set (read-only root, ``--cap-drop
  ALL``, ``1000:1000``, network ``none``).
- **D3** — failing-first tests are the executable spec; this module implements
  exactly the surface ``tests/test_sandbox_config.py`` and
  ``tests/test_sandbox_security.py`` assert.
- **D10** — the image tag is ``traderbot-sandbox:d`` + the first 8 hex of the
  sha256 of the Dockerfile bytes.
- **IS-1** — every sandboxed agent gets exactly two binds, never more.
- **IS-2** — main/sysadmin are never sandboxed; the builder refuses them.
- **IS-5** — one model renders BOTH the OpenClaw config keys
  (:meth:`DockerSandboxConfig.to_openclaw_keys`) and the printed command the QA
  matrix compares.

The module has no deploy-layer imports, no subprocess use, and never invokes
docker: it only *describes* the posture. Building the image is the deploy
seam's job (T7; ``traderbot.deploy.sandbox_build``), and writing config is
T8's.
"""

# pyright: reportPrivateLocalImportUsage=false
# (T5 contract pins the import to the public re-export ``traderbot.kalshi.models``;
# basedpyright flags that module's grouped re-export — the same pattern
# ``traderbot.profiles.models`` uses — so silence the export check here, not the
# import source.)

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from traderbot.deploy.openclaw_models import JsonValue

from pydantic import BaseModel, ConfigDict, Field, computed_field

from traderbot.kalshi.models import MarketCategory

__all__ = [
    "EXPECTED_IMAGE_RE",
    "FORBIDDEN_MOUNTS",
    "DockerSandboxConfig",
    "DockerUnavailableError",
    "SandboxRefusalError",
    "assert_docker_available",
    "check_mount_allowed",
    "generate_docker_run_command",
    "sandbox_config_for",
    "sandbox_image_tag",
]

# OpenClaw's sandbox mode is the container-posture ladder (off|non-main|all) —
# never the trading mode (backtest|paper|live). Sandboxed agents run "all".
_OPENCLAW_SANDBOX_MODE = "all"
_WORKSPACE_TARGET = "/workspace"
_DATA_TARGET = "/data"
_SANDBOX_USER = "1000:1000"
_SANDBOX_NETWORK = "none"
# A-DCFG-KEYS pinned hardening emission (todo-8 standing ruling): the
# deployed 2026.7.1-2 SandboxDockerSchema defines readOnlyRoot/network/user/
# capDrop as OPTIONAL WITHOUT defaults (``default: <undefined>`` per key) and
# the gateway runtime emits --read-only/--network/--user/--cap-drop ONLY when
# the key is truthy — omitting any of them silently yields Docker defaults
# (writable rootfs, bridge network, root user, full capabilities). The writer
# therefore ALWAYS emits all four with these pinned values.
_DOCKER_READ_ONLY_ROOT = True
_DOCKER_CAP_DROP: tuple[str, ...] = ("ALL",)
_IMAGE_REPOSITORY = "traderbot-sandbox"

# D1/Must-NOT: host paths a generated bind must never expose. Kept as literal
# "~"-prefixed strings so consumers expand them exactly like the T2 security
# suite does (``Path(entry).expanduser()``); mounting any of these — or any
# ancestor of them — is the escape this table guards against.
FORBIDDEN_MOUNTS: tuple[str, ...] = (
    "~/.traderbot",
    "~/.openclaw/config",
    "~/.openclaw/credentials",
    "~/.gnupg",
    "/var/run/docker.sock",
    "/",
    "/etc",
    "/root",
)

# D10: the exact tag grammar — a compiled predicate, never a bare string, so a
# floating ":test" tag (hollow-posture class) is rejected by construction.
EXPECTED_IMAGE_RE: re.Pattern[str] = re.compile(r"^traderbot-sandbox:d[0-9a-f]{8}$")

# IS-2/DD-036/#491: main and sysadmin run unsandboxed (mode "off"); the builder
# never hands out a sandbox config for them.
_REFUSED_AGENTS = frozenset({"main", "sysadmin"})

# The repo-root-relative Dockerfile D10 derives the tag from; the deploy host is
# the checkout host, so this resolves from the package location (src/traderbot/
# -> repo root).
_DEFAULT_DOCKERFILE: Path = (
    Path(__file__).resolve().parents[2] / "install" / "docker" / "Dockerfile"
)


class SandboxRefusalError(RuntimeError):
    """Raised when a sandbox config is refused (IS-2 / D1 guard).

    Raised by :func:`sandbox_config_for` for main/sysadmin, which are never
    sandboxed, and by :func:`generate_docker_run_command` if a config would
    expose a forbidden host path.
    """


class DockerUnavailableError(RuntimeError):
    """Raised by :func:`assert_docker_available` when docker is absent (D7).

    Presence-gate only: this checks the ``docker`` CLI is on ``PATH`` via
    :func:`shutil.which` and never contacts the daemon.
    """


def _bind_source(bind: str) -> str:
    """Return the host source of a ``source:target[:mode]`` bind string."""
    return bind.rsplit(":", 2)[0]


def _expand(path: str) -> str:
    """Expand a leading ``~`` and normalise to a string, mirrors the T2 suite."""
    return str(Path(path).expanduser())


def _exposes(source: str, forbidden: str) -> bool:
    """True when mounting ``source`` would expose ``forbidden``.

    Mounting a host path exposes everything at or below it, so the dangerous
    direction is the bind source BEING the forbidden path or one of its
    ancestors — never a descendant. ``~/.traderbot/backtest-weather`` is a
    sanctioned subdirectory mount; ``~/.traderbot`` itself is the blanket mount
    the plan's Must-NOT list forbids.
    """
    source_root = source if source == "/" else source.rstrip("/")
    if forbidden == source_root:
        return True
    prefix = source_root if source_root.endswith("/") else source_root + "/"
    return forbidden.startswith(prefix)


def check_mount_allowed(binds: Iterable[str]) -> bool:
    """Return ``True`` iff no bind source exposes a :data:`FORBIDDEN_MOUNTS` path.

    A bind is rejected when its host source *is* a forbidden path or an
    *ancestor* of one (mounting an ancestor exposes it wholesale); descendant
    mounts such as ``~/.traderbot/{mode}-{name}`` are sanctioned.
    """
    forbidden = tuple(_expand(entry) for entry in FORBIDDEN_MOUNTS)
    for bind in binds:
        source = _expand(_bind_source(bind))
        for host_path in forbidden:
            if _exposes(source, host_path):
                return False
    return True


def assert_docker_available() -> None:
    """Raise :class:`DockerUnavailableError` unless the ``docker`` CLI is on PATH.

    D7 presence gate: this is a :func:`shutil.which` check only. It never shells
    out to ``docker info``/``docker version``, so it cannot be fooled (or slowed)
    by a daemon call.
    """
    if shutil.which("docker") is None:
        raise DockerUnavailableError(
            "docker is not on PATH; install Docker (or start the daemon, e.g. "
            + "'systemctl start docker') and re-run (D7 fail-closed gate)"
        )


def _lf_normalized_sha256(content: bytes) -> str:
    """sha256 hexdigest of ``content`` with line endings normalized to LF.

    CI checkout portability: GitHub Windows runners check out with
    ``core.autocrlf=true``, rewriting LF to CRLF on disk, so hashing raw bytes
    would drift from the committed LF digest (the D10 tag and the D10
    provenance pin both derive from it). Normalizing CRLF/CR to LF before
    hashing keeps the digest stable across checkout EOL config. This stays
    fail-closed: only the line-ending bytes are normalized, so any real
    content change still yields a different digest and trips the pin.
    """
    normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def sandbox_image_tag(dockerfile_path: Path) -> str:
    """Return the D10 content-addressed tag for a Dockerfile.

    The tag is ``traderbot-sandbox:d`` followed by the first 8 lowercase hex
    characters of the sha256 digest of the Dockerfile bytes with line endings
    normalized to LF (CI autocrlf checkouts and LF checkouts tag identically).
    Identical content always yields the identical tag; any byte change beyond
    EOL style yields a different one.
    """
    digest = _lf_normalized_sha256(dockerfile_path.read_bytes())
    return f"{_IMAGE_REPOSITORY}:d{digest[:8]}"


def _default_image_tag() -> str:
    """Derive the default image tag from the checked-in Dockerfile (D10)."""
    return sandbox_image_tag(_DEFAULT_DOCKERFILE)


class DockerSandboxConfig(BaseModel):
    """Per-agent Docker sandbox contract — the single source of truth (IS-5).

    Constructible with exactly ``name``, ``mode``, ``category``, ``data_root``
    and ``workspace``; every other field carries a default. ``binds`` is derived
    from those fields (workspace first), and ``to_openclaw_keys`` renders the
    pinned 2026.7.1-2 OpenClaw sandbox object.

    ``mode`` is the TRADING ladder (backtest/paper/live), never a backend; the
    OpenClaw sandbox mode is always ``"all"`` for a sandboxed agent.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid")

    name: str
    mode: Literal["backtest", "paper", "live"]
    category: MarketCategory | None = None
    data_root: Path
    workspace: Path
    agent_id: str | None = None
    label: str | None = None
    # D10: derived from the checked-in Dockerfile bytes at construction time.
    image: str = Field(default_factory=_default_image_tag)

    @computed_field
    @property
    def binds(self) -> tuple[str, str]:
        """The D1 mount contract: own workspace ``:ro`` first, own data ``:rw`` second."""
        return (
            f"{self.workspace}:{_WORKSPACE_TARGET}:ro",
            f"{self.data_root}/{self.mode}-{self.name}:{_DATA_TARGET}:rw",
        )

    def to_openclaw_keys(self) -> dict[str, JsonValue]:
        """Render the camelCase OpenClaw sandbox object (pinned 2026.7.1-2 schema).

        Nested and JSON-able (D5 strict-json writes): the ``sandbox`` keys with
        the D9 exact two-flag dangerous-* set under ``docker`` — and nothing
        else containing ``dangerously`` anywhere in the structure — plus the
        four A-DCFG-KEYS hardening keys (``readOnlyRoot``, ``network``,
        ``user``, ``capDrop``), always emitted with pinned values because the
        schema marks all four optional WITHOUT defaults and omission silently
        yields Docker defaults.
        """
        return {
            "mode": _OPENCLAW_SANDBOX_MODE,
            "workspaceAccess": "none",
            "docker": {
                "image": self.image,
                "binds": list(self.binds),
                "readOnlyRoot": _DOCKER_READ_ONLY_ROOT,
                "network": _SANDBOX_NETWORK,
                "user": _SANDBOX_USER,
                "capDrop": list(_DOCKER_CAP_DROP),
                "dangerouslyAllowExternalBindSources": True,
                "dangerouslyAllowReservedContainerTargets": True,
            },
        }


def sandbox_config_for(
    agent: str,
    data_root: Path,
    workspace: Path,
    *,
    mode: Literal["backtest", "paper", "live"] = "backtest",
    image: str | None = None,
) -> DockerSandboxConfig:
    """Build a :class:`DockerSandboxConfig` for a sandboxable agent.

    Category agents infer their :class:`MarketCategory` from the agent name;
    ``dev-liaison`` is the category-less sandboxed target (GAP-13/IS-1). main
    and sysadmin are refused with :class:`SandboxRefusalError` (IS-2) — they run
    unsandboxed (mode ``"off"``) and never receive a sandbox config here.

    ``mode`` defaults to ``"backtest"`` and is the trading ladder value used in
    the ``{mode}-{name}`` data-dir bind segment.

    ``image`` is the deploy writer's explicit D10 tag
    (``sandbox_image_tag(resolve_sandbox_dockerfile())``); T8 never relies on
    the ``default_factory`` so the written config always carries the tag the
    build just (re)proven. Omitted (tests/one-off renders), the factory
    derives the same tag from the checked-in Dockerfile.
    """
    if agent in _REFUSED_AGENTS:
        raise SandboxRefusalError(
            f"refusing to build a sandbox config for {agent!r}: main and sysadmin "
            + "are never sandboxed (sandbox.mode 'off' only; IS-2/DD-036/#491)"
        )
    try:
        category: MarketCategory | None = MarketCategory(agent)
    except ValueError:
        category = None
    if image is not None:
        return DockerSandboxConfig(
            name=agent,
            mode=mode,
            category=category,
            data_root=data_root,
            workspace=workspace,
            image=image,
        )
    return DockerSandboxConfig(
        name=agent,
        mode=mode,
        category=category,
        data_root=data_root,
        workspace=workspace,
    )


def _config_fingerprint(config: DockerSandboxConfig) -> str:
    """A short deterministic container-name suffix for a config."""
    seed = "|".join((config.name, config.mode, str(config.data_root), str(config.workspace)))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


def _default_data_root() -> Path:
    """Repo-convention data root used when no config is supplied at render time."""
    return Path("~/.traderbot").expanduser()


def _default_workspace(agent: str) -> Path:
    """Repo-convention workspace path used when no config is supplied at render time."""
    return Path("~/.openclaw/workspace").expanduser() / agent


def generate_docker_run_command(agent: str, *, config: DockerSandboxConfig | None = None) -> str:
    """Render the canonical hardened ``docker run`` command for an agent (IS-5).

    One string is the QA-comparable contract: the D1 hardening set
    (``--read-only --cap-drop ALL --user 1000:1000 --network none``), exactly two
    ``-v`` binds in order (workspace ``:ro`` then ``{mode}-{name}`` ``:rw``), a
    deterministic ``openclaw-sbx-<agent>-<hex>`` name, and the D10
    content-addressed image tag as the final argument.

    When ``config`` is omitted, a config is built from the repo conventions via
    :func:`sandbox_config_for`. Refuses to render if any bind would expose a
    forbidden host path.
    """
    resolved = (
        config
        if config is not None
        else sandbox_config_for(agent, _default_data_root(), _default_workspace(agent))
    )
    binds = tuple(resolved.binds)
    if not check_mount_allowed(binds):
        raise SandboxRefusalError(
            f"refusing to render a docker command for {agent!r}: a bind exposes a "
            + "forbidden host path (D1/Must-NOT)"
        )
    workspace_bind, data_bind = binds
    container_name = f"openclaw-sbx-{agent}-{_config_fingerprint(resolved)}"
    return " ".join(
        (
            "docker run",
            "--read-only",
            "--cap-drop ALL",
            f"--user {_SANDBOX_USER}",
            f"--network {_SANDBOX_NETWORK}",
            f"--name {container_name}",
            f"-v {workspace_bind}",
            f"-v {data_bind}",
            resolved.image,
        )
    )
