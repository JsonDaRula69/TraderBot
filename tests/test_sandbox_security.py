"""Phase 5 sandbox containment security — TDD RED suite (plan todo T2, D3).

Security invariants for the not-yet-written ``traderbot.sandbox`` module
(issue #169; implemented by plan todo T5). Every test here MUST fail while
the module is absent. The module is imported lazily via ``_sandbox()`` so
this file collects cleanly and each test fails individually.

Security surface pinned here (T5 implements exactly this):

- ``FORBIDDEN_MOUNTS`` — the exported forbidden-host-path table (D1 /
  Must-NOT): host ~/.traderbot, ~/.openclaw config + credentials, ~/.gnupg,
  the docker socket, and host-root paths.
- ``SandboxRefusalError`` — the typed refusal ``sandbox_config_for`` raises
  for main/sysadmin (exact name pinned; IS-2).
- ``DockerSandboxConfig.to_openclaw_keys()`` — the OpenClaw-key
  serialization (nested, JSON-able, camelCase per the pinned 2026.7.1-2
  schema); the D9 dangerous-* set is asserted over it.
- ``EXPECTED_IMAGE_RE`` — compiled predicate for the D10 tag grammar.

Each test carries a short test-map comment naming the decision it enforces.
"""

# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
# (D3 RED: these tests dynamically import the unwritten ``traderbot.sandbox``
# module, so every pinned-symbol access is intentionally Any-typed.)

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from traderbot.kalshi.models import MarketCategory


def _sandbox() -> ModuleType:
    """Import the containment module lazily (it does not exist yet — D3 RED)."""
    return importlib.import_module("traderbot.sandbox")


_REQUIRED_FORBIDDEN_MOUNTS: tuple[str, ...] = (
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


def _dangerous_entries(node: object) -> dict[str, object]:
    """Collect every dangerously-* key anywhere in a nested JSON value."""
    entries: dict[str, object] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and "dangerously" in key:
                entries[key] = value
            entries.update(_dangerous_entries(value))
    elif isinstance(node, (list, tuple)):
        for item in node:
            entries.update(_dangerous_entries(item))
    return entries


def test_forbidden_mounts_table_is_exhaustive() -> None:
    # Test-map: D1/Must-NOT — the exported table covers every host path the
    # plan names (issue #169 deliverable): the TraderBot secrets root, the
    # OpenClaw config + credential stores, the GPG home, the docker socket,
    # and host-root paths.
    sandbox = _sandbox()
    forbidden = {_expanded(str(entry)) for entry in sandbox.FORBIDDEN_MOUNTS}
    assert forbidden
    required = {_expanded(entry) for entry in _REQUIRED_FORBIDDEN_MOUNTS}
    assert required <= forbidden


@pytest.mark.parametrize("category", list(MarketCategory))
def test_no_generated_bind_exposes_a_forbidden_mount(
    category: MarketCategory,
    tmp_path: Path,
) -> None:
    # Test-map: D1/Must-NOT/IS-1 — for every one of the nine categories, the
    # generated bind set has exactly two binds and no bind source is — or is
    # an ancestor of — any forbidden host path (mounting an ancestor of
    # ~/.traderbot would expose it wholesale).
    sandbox = _sandbox()
    data_root = tmp_path / "data"
    workspace = tmp_path / "workspace" / category.value
    config = sandbox.sandbox_config_for(category.value, data_root, workspace)
    binds = tuple(config.binds)
    assert len(binds) == 2  # IS-1: exactly two binds — never vacuous below
    forbidden = {_expanded(str(entry)) for entry in sandbox.FORBIDDEN_MOUNTS}
    for bind in binds:
        source = _expanded(bind.rsplit(":", 2)[0])
        for host_path in forbidden:
            assert not _exposes(source, host_path), (category, bind, host_path)


def test_cross_category_bind_isolation_pairwise(tmp_path: Path) -> None:
    # Test-map: IS-1/IS-6 — agent A's bind set never names agent B's
    # workspace or data paths, for all nine categories pairwise (the
    # weather container must never see the economics bind, and vice versa).
    sandbox = _sandbox()
    data_root = tmp_path / "data"
    workspace_root = tmp_path / "workspace"
    binds_by_agent: dict[str, tuple[str, ...]] = {}
    data_dirs_by_agent: dict[str, str] = {}
    for category in MarketCategory:
        config = sandbox.sandbox_config_for(
            category.value, data_root, workspace_root / category.value
        )
        binds = tuple(config.binds)
        assert len(binds) == 2  # IS-1: exactly two binds — never vacuous below
        binds_by_agent[category.value] = binds
        data_dirs_by_agent[category.value] = f"{data_root}/{config.mode}-{category.value}"
    for agent_a in MarketCategory:
        for agent_b in MarketCategory:
            if agent_a is agent_b:
                continue
            other_workspace = str(workspace_root / agent_b.value)
            other_data = data_dirs_by_agent[agent_b.value]
            for bind in binds_by_agent[agent_a.value]:
                assert other_workspace not in bind, (agent_a, agent_b, bind)
                assert other_data not in bind, (agent_a, agent_b, bind)


@pytest.mark.parametrize("refused", ["main", "sysadmin"])
def test_builder_refuses_main_and_sysadmin(refused: str, tmp_path: Path) -> None:
    # Test-map: IS-2/DD-036/D2/#491 — main and sysadmin are never sandboxed;
    # the builder never hands out a config for them. The exact exception name
    # is PINNED here: traderbot.sandbox.SandboxRefusalError (T5 implements
    # exactly this name; their explicit mode "off" is written by the deploy
    # path, never a sandbox config from this builder).
    sandbox = _sandbox()
    with pytest.raises(sandbox.SandboxRefusalError):
        sandbox.sandbox_config_for(refused, tmp_path / "data", tmp_path / "workspace" / refused)


def test_dangerous_flag_set_is_exact(tmp_path: Path) -> None:
    # Test-map: D9/D1 — the owner-approved dangerous-* set is EXACTLY
    # {dangerouslyAllowExternalBindSources, dangerouslyAllowReservedContainerTargets},
    # both true, and no other dangerous-* key anywhere. Asserted over the
    # config's OpenClaw-key serialization; the serialization's method name
    # is PINNED here: DockerSandboxConfig.to_openclaw_keys() (T5 implements
    # it: nested, JSON-able, camelCase per the pinned 2026.7.1-2 schema).
    sandbox = _sandbox()
    config = sandbox.sandbox_config_for(
        "weather", tmp_path / "data", tmp_path / "workspace" / "weather"
    )
    keys = config.to_openclaw_keys()
    assert isinstance(keys, dict)
    assert isinstance(json.dumps(keys), str)  # JSON-able — D5 strict-json writes
    assert _dangerous_entries(keys) == {
        "dangerouslyAllowExternalBindSources": True,
        "dangerouslyAllowReservedContainerTargets": True,
    }


def test_expected_image_predicate_shape() -> None:
    # Test-map: D10 — the exported image predicate accepts exactly the
    # content-addressed tag grammar; the floating ":test" tag
    # (hollow-posture class) is rejected by construction.
    sandbox = _sandbox()
    predicate = sandbox.EXPECTED_IMAGE_RE
    # Compiled-regex pin: a bare string export has no ``.pattern`` and fails
    # here, so only the pinned predicate object can pass.
    assert predicate.pattern == r"^traderbot-sandbox:d[0-9a-f]{8}$"
    assert predicate.fullmatch("traderbot-sandbox:d0123abcd") is not None
    assert predicate.fullmatch("traderbot-sandbox:ddeadbeef") is not None
    for rejected in (
        "traderbot-sandbox:test",
        "traderbot-sandbox:d0123abc",
        "traderbot-sandbox:d0123abcz",
        "traderbot-sandbox:d0123abcd0",
        "traderbot-sandbox",
        "not-traderbot-sandbox:d0123abcd",
    ):
        assert predicate.fullmatch(rejected) is None, rejected
