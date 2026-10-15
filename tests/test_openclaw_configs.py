import json
from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import MarketCategory
from traderbot.mcp.tools import TOOL_DEFINITIONS

CONFIG_DIR: Final = Path(__file__).parents[1] / "configs" / "openclaw"
CATEGORY_NAMES: Final = tuple(category.value for category in MarketCategory)
AGENT_CONFIG_PATHS: Final = {
    agent: CONFIG_DIR / f"{agent}.json" for agent in ("sysadmin", "dev-liaison", *CATEGORY_NAMES)
}
GATEWAY_CONFIG_PATH: Final = CONFIG_DIR / "gateway.json"
STRICT_AGENT_FIELDS: Final = frozenset({"id", "sandbox", "tools"})

# T4 (D1/D9): the full sandbox desired-state contract carried by the 11 agent fragments.
# The 10 sandboxed agents (9 MarketCategory agents + dev-liaison) get a docker block;
# sysadmin is explicitly mode "off" with NO docker block. `gateway.json` (top keys: mcp)
# and `with-plugin.json` (top keys: plugins, secrets, mcp) have no agent/sandbox block and
# are structurally OUT of the agent-fragment set — the set below is enumerated by NAME,
# never a blind glob, so a new file cannot silently join the contract.
SANDBOXED_AGENT_NAMES: Final = ("dev-liaison", *CATEGORY_NAMES)
AGENT_FRAGMENT_NAMES: Final = ("sysadmin", *SANDBOXED_AGENT_NAMES)
NON_AGENT_CONFIG_STEMS: Final = frozenset({"gateway", "with-plugin"})

# D10: the image tag is derived at deploy time from the Dockerfile bytes; a fragment cannot
# know those bytes, so the fragment documents the placeholder below and deploy substitutes
# the real `traderbot-sandbox:d<8hex>` tag. The sync test asserts the placeholder, never a
# literal hex tag.
IMAGE_PLACEHOLDER: Final = "traderbot-sandbox:DEPLOY_DERIVED"

# D9: the owner-approved exact dangerous-* set. No other dangerous-* key may appear anywhere.
D9_DANGEROUS_KEYS: Final = frozenset(
    {
        "dangerouslyAllowExternalBindSources",
        "dangerouslyAllowReservedContainerTargets",
    }
)

# D1 / Must-NOT-have: absolute forbidden bind sources. A bind to any of these would expose
# host secrets, the Docker socket, or system roots to a container.
FORBIDDEN_BIND_SUBSTRINGS: Final = (
    "~/.traderbot",
    "~/.openclaw/config",
    "~/.gnupg",
    "docker.sock",
)
FORBIDDEN_BIND_SOURCE_PREFIXES: Final = ("/etc", "/root")
FORBIDDEN_BIND_ROOT_SOURCES: Final = frozenset({"", "/", "//"})

ROLE_TRADERBOT_TOOLS: Final[dict[str, frozenset[str]]] = {
    "dev-liaison": frozenset(
        {
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
        }
    ),
    **{
        category: frozenset(
            {
                "traderbot__health",
                "traderbot__auth_check",
                "traderbot__profile_list",
                "traderbot__market_edge",
                "traderbot__market_prices",
            }
        )
        for category in CATEGORY_NAMES
    },
}
BUILT_IN_TOOLS: Final[dict[str, frozenset[str]]] = {
    "dev-liaison": frozenset(
        {
            "sessions_spawn",
            "sessions_send",
            "sessions_yield",
            "sessions_list",
            "sessions_history",
            "subagents",
        }
    ),
    **{category: frozenset() for category in CATEGORY_NAMES},
}
SYSADMIN_DENIALS: Final = frozenset(
    {
        "traderbot__trade",
        "traderbot__scan",
        "traderbot__analyze",
        "traderbot__market_edge",
        "traderbot__market_prices",
        "traderbot__weather_*",
    }
)


class StrictConfigModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SandboxDockerConfig(StrictConfigModel):
    # Pinned schema key names verbatim (SandboxDockerSchema, strict): extra="forbid" here
    # mechanically rejects any dangerous-* key outside the D9 set. The four
    # A-DCFG-KEYS hardening keys are optional-WITHOUT-defaults in the schema, so
    # omission silently yields Docker defaults; the deploy writer always emits
    # them, and this require-present model makes every fragment carry the pins.
    image: str
    binds: list[str]
    dangerouslyAllowExternalBindSources: bool
    dangerouslyAllowReservedContainerTargets: bool
    readOnlyRoot: Literal[True]
    network: Literal["none"]
    user: Literal["1000:1000"]
    capDrop: list[Literal["ALL"]] = Field(min_length=1, max_length=1)


class SandboxConfig(StrictConfigModel):
    mode: Literal["off", "non-main", "all"]
    workspaceAccess: Literal["none"] | None = None
    docker: SandboxDockerConfig | None = None


class SandboxToolPolicy(StrictConfigModel):
    allow: list[str]


class SandboxToolsConfig(StrictConfigModel):
    tools: SandboxToolPolicy


class AgentToolsConfig(StrictConfigModel):
    allow: list[str]
    deny: list[str]
    sandbox: SandboxToolsConfig | None = None


class AgentConfig(StrictConfigModel):
    id: str
    sandbox: SandboxConfig
    tools: AgentToolsConfig


class McpServerConfig(StrictConfigModel):
    url: str
    transport: Literal["streamable-http"]
    requestTimeoutMs: int
    connectionTimeoutMs: int


class McpServersConfig(StrictConfigModel):
    traderbot: McpServerConfig


class McpConfig(StrictConfigModel):
    servers: McpServersConfig


class GatewayConfig(StrictConfigModel):
    mcp: McpConfig


class TokenRef(StrictConfigModel):
    source: Literal["exec"]
    provider: Literal["infisical"]
    id: str


class InjectorSettings(StrictConfigModel):
    agentTokenMap: dict[str, TokenRef]


class InjectorEntry(StrictConfigModel):
    config: InjectorSettings


class PluginEntries(BaseModel):
    traderbot_token_injector: InjectorEntry = Field(alias="traderbot-token-injector")


class Plugins(BaseModel):
    entries: PluginEntries


class PluginConfig(BaseModel):
    plugins: Plugins


def load_agent(path: Path) -> AgentConfig:
    return AgentConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _load_raw(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_dict_keys(node: object) -> list[str]:
    keys: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            keys.append(key)
            keys.extend(_iter_dict_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.extend(_iter_dict_keys(item))
    return keys


def _iter_bind_strings(node: object) -> list[str]:
    binds: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "binds" and isinstance(value, list):
                binds.extend(item for item in value if isinstance(item, str))
            binds.extend(_iter_bind_strings(value))
    elif isinstance(node, list):
        for item in node:
            binds.extend(_iter_bind_strings(item))
    return binds


def _bind_source(bind: str) -> str:
    return bind.split(":", 1)[0]


def test_agent_fragments_reject_nested_mcp_and_other_unknown_fields() -> None:
    for config_path in AGENT_CONFIG_PATHS.values():
        config = load_agent(config_path)

        assert config.model_fields_set == STRICT_AGENT_FIELDS


def test_agent_policies_use_restrictive_allow_instead_of_additive_also_allow() -> None:
    for config_path in AGENT_CONFIG_PATHS.values():
        allowed = load_agent(config_path).tools.allow

        assert allowed
        assert "*" not in allowed
        assert "group:plugins" not in allowed
        assert "bundle-mcp" not in allowed


def test_live_traderbot_allowlists_are_subsets_of_implemented_tools() -> None:
    # Given
    implemented = {f"traderbot__{definition['name']}" for definition in TOOL_DEFINITIONS}

    # When / Then
    for config_path in AGENT_CONFIG_PATHS.values():
        allowed = set(load_agent(config_path).tools.allow)
        assert {name for name in allowed if name.startswith("traderbot__")} <= implemented


def test_agent_allowlists_match_role_permissions() -> None:
    for agent in ("dev-liaison", *CATEGORY_NAMES):
        expected = ROLE_TRADERBOT_TOOLS[agent] | BUILT_IN_TOOLS[agent]

        assert set(load_agent(AGENT_CONFIG_PATHS[agent]).tools.allow) == expected


def test_sysadmin_stays_unsandboxed_and_denies_trading_tools() -> None:
    config = load_agent(AGENT_CONFIG_PATHS["sysadmin"])

    assert config.sandbox.mode == "off"
    assert set(config.tools.deny) == SYSADMIN_DENIALS


def test_dev_liaison_has_no_host_runtime_or_filesystem_access() -> None:
    config = load_agent(AGENT_CONFIG_PATHS["dev-liaison"])

    assert config.sandbox.mode == "all"
    assert {"group:runtime", "group:fs"} <= set(config.tools.deny)


def test_category_sandboxes_have_second_mcp_tool_gate() -> None:
    for category in CATEGORY_NAMES:
        config = load_agent(AGENT_CONFIG_PATHS[category])

        assert config.sandbox.mode == "all"
        assert set(config.tools.deny) == {"group:runtime", "group:fs"}
        assert config.tools.sandbox is not None
        assert config.tools.sandbox.tools.allow == ["bundle-mcp"]


def test_existing_weather_policy_characterization() -> None:
    config = load_agent(AGENT_CONFIG_PATHS["weather"])

    assert config.sandbox.mode == "all"
    assert set(config.tools.deny) == {"group:runtime", "group:fs"}
    assert {
        "traderbot__health",
        "traderbot__auth_check",
        "traderbot__profile_list",
        "traderbot__market_edge",
        "traderbot__market_prices",
    } <= set(config.tools.allow)
    assert config.tools.sandbox is not None
    assert "bundle-mcp" in config.tools.sandbox.tools.allow


def test_gateway_registers_traderbot_mcp_server_once() -> None:
    gateway = GatewayConfig.model_validate_json(GATEWAY_CONFIG_PATH.read_text(encoding="utf-8"))

    assert gateway.model_fields_set == {"mcp"}
    assert gateway.mcp.servers.model_fields_set == {"traderbot"}
    assert gateway.mcp.servers.traderbot.url == "http://127.0.0.1:8765/mcp"
    assert gateway.mcp.servers.traderbot.transport == "streamable-http"


def test_plugin_token_map_preserves_existing_roles_and_maps_all_categories() -> None:
    plugin = PluginConfig.model_validate_json(
        (CONFIG_DIR / "with-plugin.json").read_text(encoding="utf-8")
    )
    token_map = plugin.plugins.entries.traderbot_token_injector.config.agentTokenMap

    assert set(token_map) == {"sysadmin", "dev-liaison", *CATEGORY_NAMES}
    for category in CATEGORY_NAMES:
        assert token_map[category].id == f"{category}_token"


def test_agent_fragment_set_is_exactly_the_eleven_named_agents() -> None:
    # T4: enumerate EXACTLY the 11 agent fragments by name; the non-agent configs
    # (gateway.json, with-plugin.json) must NOT be in the set, and no other file may exist.
    assert len(AGENT_FRAGMENT_NAMES) == 11
    assert len(set(AGENT_FRAGMENT_NAMES)) == 11
    assert "gateway" not in AGENT_FRAGMENT_NAMES
    assert "with-plugin" not in AGENT_FRAGMENT_NAMES
    assert set(AGENT_CONFIG_PATHS) == set(AGENT_FRAGMENT_NAMES)

    on_disk = {path.stem for path in CONFIG_DIR.glob("*.json")}
    assert on_disk == set(AGENT_FRAGMENT_NAMES) | NON_AGENT_CONFIG_STEMS


def test_sandboxed_fragments_carry_full_sandbox_contract() -> None:
    for agent in SANDBOXED_AGENT_NAMES:
        sandbox = load_agent(AGENT_CONFIG_PATHS[agent]).sandbox

        assert sandbox.mode == "all"
        assert sandbox.workspaceAccess == "none"
        assert sandbox.model_fields_set == {"mode", "workspaceAccess", "docker"}

        docker = sandbox.docker
        assert docker is not None
        assert docker.model_fields_set == {
            "image",
            "binds",
            "readOnlyRoot",
            "network",
            "user",
            "capDrop",
            *D9_DANGEROUS_KEYS,
        }
        assert docker.image == IMAGE_PLACEHOLDER
        assert docker.readOnlyRoot is True
        assert docker.network == "none"
        assert docker.user == "1000:1000"
        assert docker.capDrop == ["ALL"]
        assert docker.dangerouslyAllowExternalBindSources is True
        assert docker.dangerouslyAllowReservedContainerTargets is True

        # Exactly two bind slots: workspace read-only at /workspace, data read-write at /data.
        assert len(docker.binds) == 2
        workspace_bind, data_bind = docker.binds
        ws_source, ws_target, ws_mode = workspace_bind.split(":")
        assert (ws_source, ws_target, ws_mode) == ("<agent-workspace>", "/workspace", "ro")
        data_source, data_target, data_mode = data_bind.split(":")
        assert data_target == "/data"
        assert data_mode == "rw"
        assert data_source.startswith("<traderbot-data-root>/{mode}-")
        assert data_source.endswith(agent)


def test_sysadmin_fragment_is_explicitly_off_with_no_docker_block() -> None:
    sandbox = load_agent(AGENT_CONFIG_PATHS["sysadmin"]).sandbox

    assert sandbox.mode == "off"
    assert sandbox.docker is None
    assert sandbox.workspaceAccess is None
    assert sandbox.model_fields_set == {"mode"}

    raw = _load_raw(AGENT_CONFIG_PATHS["sysadmin"])
    assert isinstance(raw, dict)
    assert raw["sandbox"] == {"mode": "off"}


def test_no_dangerous_keys_outside_the_d9_set_across_all_fragments() -> None:
    # T4/D9: scan ALL 13 files (including the two non-agent configs) for any dangerous-* key.
    all_dangerous: set[str] = set()
    for path in sorted(CONFIG_DIR.glob("*.json")):
        dangerous = {
            key for key in _iter_dict_keys(_load_raw(path)) if key.startswith("dangerously")
        }
        all_dangerous |= dangerous

        if path.stem in SANDBOXED_AGENT_NAMES:
            assert dangerous == D9_DANGEROUS_KEYS, path.name
        else:
            assert dangerous == set(), path.name

    assert all_dangerous == D9_DANGEROUS_KEYS


def test_no_forbidden_bind_sources_anywhere() -> None:
    # T4/D1: no fragment may bind a host secret root, the Docker socket, or host root.
    for path in sorted(CONFIG_DIR.glob("*.json")):
        for bind in _iter_bind_strings(_load_raw(path)):
            source = _bind_source(bind)
            for forbidden in FORBIDDEN_BIND_SUBSTRINGS:
                assert forbidden not in bind, f"{path.name}: {bind}"
            for prefix in FORBIDDEN_BIND_SOURCE_PREFIXES:
                assert not source.startswith(prefix), f"{path.name}: {bind}"
            assert source not in FORBIDDEN_BIND_ROOT_SOURCES, f"{path.name}: {bind}"
            assert bind.endswith((":ro", ":rw")), f"{path.name}: {bind}"
