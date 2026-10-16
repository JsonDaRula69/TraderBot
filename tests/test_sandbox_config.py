"""Phase 5 sandbox containment contract — TDD RED suite (plan todo T2, D3).

Executable spec for the not-yet-written ``traderbot.sandbox`` module
(issue #169; implemented by plan todo T5). Every test here MUST fail while
the module is absent and must go green once T5 lands it. The module is
imported lazily via ``_sandbox()`` so this file collects cleanly and each
test fails individually on the missing module instead of hiding behind a
single collection error.

API surface pinned by these tests (T5 implements exactly this):

- ``DockerSandboxConfig`` — strict pydantic model, constructible with
  exactly ``name``, ``mode``, ``category``, ``data_root``, ``workspace``;
  every other field (``image``, ``agent_id``, ...) must carry a default;
  ``binds`` is the derived two-entry bind tuple (workspace bind first).
- ``sandbox_image_tag(dockerfile_path: Path) -> str`` — D10 content-addressed
  tag: ``traderbot-sandbox:d`` + first 8 hex of sha256 of the Dockerfile bytes.
- ``generate_docker_run_command(agent: str, *, config=...) -> str`` — IS-5
  single source of truth renders the runnable hardened container command.
- ``sandbox_config_for(agent: str, data_root: Path, workspace: Path) ->
  DockerSandboxConfig`` — per-agent builder; refuses main/sysadmin with
  ``SandboxRefusalError`` (name pinned in test_sandbox_security.py).

Each test carries a short test-map comment naming the decision it enforces.
"""

# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
# (D3 RED: these tests dynamically import the unwritten ``traderbot.sandbox``
# module, so every pinned-symbol access is intentionally Any-typed.)

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from traderbot.kalshi.models import MarketCategory


def _sandbox() -> ModuleType:
    """Import the containment module lazily (it does not exist yet — D3 RED)."""
    return importlib.import_module("traderbot.sandbox")


# Host paths a generated bind must never mount (D1 / plan Must-NOT). Kept
# literal here — independent of the module's own FORBIDDEN_MOUNTS table — so
# the render check cannot pass merely because the module's table is incomplete.
_FORBIDDEN_HOST_PATHS: tuple[str, ...] = (
    "~/.traderbot",
    "~/.openclaw/config",
    "~/.openclaw/credentials",
    "~/.gnupg",
    "/var/run/docker.sock",
    "/",
    "/etc",
    "/root",
)


def _expanded(path: str) -> str:
    return str(Path(path).expanduser())


def _exposes(source: str, forbidden: str) -> bool:
    """True when a bind of ``source`` would expose ``forbidden``.

    Mounting a host path exposes everything at or below it, so the dangerous
    direction is the bind source BEING the forbidden path or one of its
    ancestors — never a descendant. ``~/.traderbot/backtest-weather`` is a
    sanctioned subdirectory mount; ``~/.traderbot`` itself is the blanket
    mount the plan's Must-NOT list forbids.
    """
    source_root = source if source == "/" else source.rstrip("/")
    if forbidden == source_root:
        return True
    prefix = source_root if source_root.endswith("/") else source_root + "/"
    return forbidden.startswith(prefix)


def test_docker_sandbox_config_rejects_extra_fields(tmp_path: Path) -> None:
    # Test-map: D3/D4 — the model is strict and extra-forbidding, mirroring
    # the pinned strict OpenClaw schema; smuggled keys are a defect.
    sandbox = _sandbox()
    with pytest.raises(ValidationError):
        sandbox.DockerSandboxConfig(
            name="weather",
            mode="backtest",
            category=MarketCategory.WEATHER,
            data_root=tmp_path / "data",
            workspace=tmp_path / "workspace" / "weather",
            sandbox_mode="all",
        )


def test_docker_sandbox_config_category_accepts_members_and_rejects_others(
    tmp_path: Path,
) -> None:
    # Test-map: DD-011/D1 — category is the MarketCategory enum (exactly the
    # 9 members) or None for the category-less dev-liaison; no other value.
    sandbox = _sandbox()
    for category in MarketCategory:
        config = sandbox.DockerSandboxConfig(
            name=category.value,
            mode="backtest",
            category=category,
            data_root=tmp_path / "data",
            workspace=tmp_path / "workspace" / category.value,
        )
        assert config.category == category
    dev_liaison = sandbox.DockerSandboxConfig(
        name="dev-liaison",
        mode="paper",
        category=None,
        data_root=tmp_path / "data",
        workspace=tmp_path / "workspace" / "dev-liaison",
    )
    assert dev_liaison.category is None
    with pytest.raises(ValidationError):
        sandbox.DockerSandboxConfig(
            name="weather",
            mode="backtest",
            category="basket-weaving",
            data_root=tmp_path / "data",
            workspace=tmp_path / "workspace" / "weather",
        )


def test_docker_sandbox_config_mode_is_the_trading_ladder(tmp_path: Path) -> None:
    # Test-map: DD-013/DD-017 + GAP-12 — ``mode`` is the TRADING ladder
    # (backtest/paper/live). "docker" is a backend, never a mode; "off" is
    # OpenClaw's sandbox mode, never a trading mode.
    sandbox = _sandbox()
    for mode in ("backtest", "paper", "live"):
        config = sandbox.DockerSandboxConfig(
            name="weather",
            mode=mode,
            category=MarketCategory.WEATHER,
            data_root=tmp_path / "data",
            workspace=tmp_path / "workspace" / "weather",
        )
        assert config.mode == mode
    for invalid in ("docker", "off", "prod", ""):
        with pytest.raises(ValidationError):
            sandbox.DockerSandboxConfig(
                name="weather",
                mode=invalid,
                category=MarketCategory.WEATHER,
                data_root=tmp_path / "data",
                workspace=tmp_path / "workspace" / "weather",
            )


def test_sandbox_image_tag_grammar(tmp_path: Path) -> None:
    # Test-map: D10 — the tag is content-addressed: "traderbot-sandbox:d"
    # plus exactly 8 lowercase hex characters, nothing more.
    sandbox = _sandbox()
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim-bookworm@sha256:deadbeef\n", encoding="utf-8")
    tag = sandbox.sandbox_image_tag(dockerfile)
    assert isinstance(tag, str)
    assert re.fullmatch(r"traderbot-sandbox:d[0-9a-f]{8}", tag), tag


def test_sandbox_image_tag_is_content_addressed(tmp_path: Path) -> None:
    # Test-map: D10 — the tag changes when — and only when — the Dockerfile
    # bytes change; identical bytes yield the identical tag.
    sandbox = _sandbox()
    base = tmp_path / "Dockerfile.base"
    twin = tmp_path / "Dockerfile.twin"
    changed = tmp_path / "Dockerfile.changed"
    base.write_text("FROM python:3.12-slim-bookworm@sha256:deadbeef\n", encoding="utf-8")
    twin.write_text("FROM python:3.12-slim-bookworm@sha256:deadbeef\n", encoding="utf-8")
    changed.write_text("FROM python:3.12-slim-bookworm@sha256:feedface\n", encoding="utf-8")
    tag = sandbox.sandbox_image_tag(base)
    assert sandbox.sandbox_image_tag(base) == tag  # deterministic re-read
    assert sandbox.sandbox_image_tag(twin) == tag  # identical bytes
    assert sandbox.sandbox_image_tag(changed) != tag  # changed bytes


def test_generate_docker_run_command_exact_render(tmp_path: Path) -> None:
    # Test-map: D1 (explicit-binds mount contract + hardening flags) / IS-1 /
    # IS-5 — one model renders the runnable command; the /data mode segment
    # comes from the config's trading mode (backtest here); D7/D10 — the
    # command names the content-addressed built image, never a floating
    # ":test" tag (hollow-posture class).
    sandbox = _sandbox()
    data_root = tmp_path / "data"
    workspace = tmp_path / "workspace" / "weather"
    config = sandbox.DockerSandboxConfig(
        name="weather",
        mode="backtest",
        category=MarketCategory.WEATHER,
        data_root=data_root,
        workspace=workspace,
    )
    command = sandbox.generate_docker_run_command("weather", config=config)

    assert isinstance(command, str)
    assert command.startswith("docker run")
    for hardening in (
        "--read-only",
        "--cap-drop ALL",
        "--user 1000:1000",
        "--network none",
        "--name openclaw-sbx-weather-",
    ):
        assert hardening in command, hardening

    workspace_bind = f"{workspace}:/workspace:ro"
    data_bind = f"{data_root}/backtest-weather:/data:rw"
    # The two binds appear exactly once each, as the only two mounts.
    assert command.count(f"-v {workspace_bind}") == 1
    assert command.count(f"-v {data_bind}") == 1
    tokens = command.split()
    rendered_binds = [tokens[index + 1] for index, token in enumerate(tokens) if token == "-v"]
    assert rendered_binds == [workspace_bind, data_bind]

    # Forbidden mounts: no docker socket anywhere, and no bind source that
    # is — or is an ancestor of — any forbidden host path.
    assert "docker.sock" not in command
    assert re.search(r"traderbot-sandbox:d[0-9a-f]{8}", command)
    for bind in rendered_binds:
        source = _expanded(bind.rsplit(":", 2)[0])
        for forbidden in _FORBIDDEN_HOST_PATHS:
            assert not _exposes(source, _expanded(forbidden)), (bind, forbidden)


def test_sandbox_config_for_category_agent_binds(tmp_path: Path) -> None:
    # Test-map: D1/IS-1 — a category agent's derived binds are EXACTLY its
    # own workspace (ro) plus its own {mode}-{name} data dir (rw), in that
    # order; the builder infers the MarketCategory from the agent name.
    sandbox = _sandbox()
    data_root = tmp_path / "data"
    workspace = tmp_path / "workspace" / "weather"
    config = sandbox.sandbox_config_for("weather", data_root, workspace)
    assert config.category == MarketCategory.WEATHER
    assert tuple(config.binds) == (
        f"{workspace}:/workspace:ro",
        f"{data_root}/{config.mode}-weather:/data:rw",
    )


def test_sandbox_config_for_dev_liaison_binds(tmp_path: Path) -> None:
    # Test-map: D1/GAP-13/IS-1 — dev-liaison is a sandboxed, category-less
    # target: same bind grammar with a {mode}-dev-liaison data dir and its
    # own .../workspace/dev-liaison path.
    sandbox = _sandbox()
    data_root = tmp_path / "data"
    workspace = tmp_path / "workspace" / "dev-liaison"
    config = sandbox.sandbox_config_for("dev-liaison", data_root, workspace)
    assert config.category is None
    assert tuple(config.binds) == (
        f"{workspace}:/workspace:ro",
        f"{data_root}/{config.mode}-dev-liaison:/data:rw",
    )


def test_to_openclaw_keys_emits_exact_eight_key_docker_surface(tmp_path: Path) -> None:
    # Test-map: A-DCFG-KEYS (todo-8 standing ruling) / D9 / D5 — the emitted
    # OpenClaw payload carries EXACTLY the 8-key docker surface: image, binds,
    # the four pinned hardening keys (readOnlyRoot/network/user/capDrop —
    # optional WITHOUT defaults in the pinned 2026.7.1-2 SandboxDockerSchema,
    # so omission would silently yield Docker defaults) plus the exact D9
    # two-flag dangerous-* set. Nothing more, nothing less.
    sandbox = _sandbox()
    config = sandbox.sandbox_config_for(
        "weather", tmp_path / "data", tmp_path / "workspace" / "weather"
    )
    keys = config.to_openclaw_keys()
    assert set(keys) == {"mode", "workspaceAccess", "docker"}
    assert keys["mode"] == "all"
    assert keys["workspaceAccess"] == "none"
    docker = keys["docker"]
    assert set(docker) == {
        "image",
        "binds",
        "readOnlyRoot",
        "network",
        "user",
        "capDrop",
        "dangerouslyAllowExternalBindSources",
        "dangerouslyAllowReservedContainerTargets",
    }
    assert docker["image"] == config.image
    assert list(docker["binds"]) == list(config.binds)
    assert docker["readOnlyRoot"] is True
    assert docker["network"] == "none"
    assert docker["user"] == "1000:1000"
    assert docker["capDrop"] == ["ALL"]
    assert docker["dangerouslyAllowExternalBindSources"] is True
    assert docker["dangerouslyAllowReservedContainerTargets"] is True


def test_sandbox_config_for_writer_supplies_explicit_d10_image(tmp_path: Path) -> None:
    # Test-map: D10 + todo-8 — the deploy writer passes the image tag
    # EXPLICITLY (sandbox_image_tag(resolve_sandbox_dockerfile())), never
    # relying on the default_factory, so the written config always carries
    # the tag the build step just proved.
    sandbox = _sandbox()
    explicit = "traderbot-sandbox:d0000000a"
    config = sandbox.sandbox_config_for(
        "weather",
        tmp_path / "data",
        tmp_path / "workspace" / "weather",
        image=explicit,
    )
    assert config.image == explicit
    assert config.to_openclaw_keys()["docker"]["image"] == explicit


def test_sandbox_image_tag_stable_under_crlf_checkout(tmp_path: Path) -> None:
    # Test-map: D10 + CI-autocrlf — a Windows ``core.autocrlf=true`` checkout
    # stores CRLF bytes on disk; the derived tag must still equal the committed
    # LF-checkout value.
    sandbox = _sandbox()
    source = Path(__file__).resolve().parents[1] / "install" / "docker" / "Dockerfile"
    lf_bytes = source.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
    lf_copy = tmp_path / "Dockerfile.lf"
    crlf_copy = tmp_path / "Dockerfile.crlf"
    lf_copy.write_bytes(lf_bytes)
    crlf_copy.write_bytes(crlf_bytes)
    lf_tag = sandbox.sandbox_image_tag(lf_copy)
    assert lf_tag == "traderbot-sandbox:da1a64821"
    assert sandbox.sandbox_image_tag(crlf_copy) == lf_tag
