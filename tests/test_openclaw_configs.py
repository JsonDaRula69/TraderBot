from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import MarketCategory
from traderbot.mcp.tools import TOOL_DEFINITIONS

CONFIG_DIR: Final = Path(__file__).parents[1] / "configs" / "openclaw"
CATEGORY_NAMES: Final = tuple(category.value for category in MarketCategory)
AGENT_CONFIG_PATHS: Final = {
    agent: CONFIG_DIR / f"{agent}.json"
    for agent in ("sysadmin", "dev-liaison", *CATEGORY_NAMES)
}
GATEWAY_CONFIG_PATH: Final = CONFIG_DIR / "gateway.json"
STRICT_AGENT_FIELDS: Final = frozenset({"id", "sandbox", "tools"})
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


class SandboxConfig(StrictConfigModel):
    mode: Literal["off", "non-main", "all"]


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
    implemented = {
        f"traderbot__{definition['name']}" for definition in TOOL_DEFINITIONS
    }

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
