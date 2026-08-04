from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict

CONFIG_DIR: Final = Path(__file__).parents[1] / "configs" / "openclaw"
AGENT_CONFIG_PATHS: Final = {
    agent: CONFIG_DIR / f"{agent}.json" for agent in ("sysadmin", "dev-liaison", "weather")
}
GATEWAY_CONFIG_PATH: Final = CONFIG_DIR / "gateway.json"
STRICT_AGENT_FIELDS: Final = frozenset({"id", "sandbox", "tools"})
ROLE_TRADERBOT_TOOLS: Final[dict[str, frozenset[str]]] = {
    "dev-liaison": frozenset(
        {
            "traderbot__reference",
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
        }
    ),
    "weather": frozenset(
        {
            "traderbot__weather_forecast_prob",
            "traderbot__weather_accuracy",
            "traderbot__weather_seasonal_context",
            "traderbot__weather_decision_brief",
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
            "traderbot__market_edge",
            "traderbot__market_prices",
            "traderbot__trade",
            "traderbot__positions",
            "traderbot__heartbeat",
            "traderbot__performance",
            "traderbot__audit",
            "traderbot__learnings",
            "traderbot__news_context",
            "traderbot__data_points",
        }
    ),
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
    "weather": frozenset({"sessions_send"}),
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
    command: Literal["traderbot-mcp-server"]
    transport: Literal["stdio"]
    env: dict[str, str] | None = None


class McpServersConfig(StrictConfigModel):
    traderbot: McpServerConfig


class McpConfig(StrictConfigModel):
    servers: McpServersConfig


class GatewayConfig(StrictConfigModel):
    mcp: McpConfig


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


def test_agent_allowlists_match_role_permissions() -> None:
    for agent in ("dev-liaison", "weather"):
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


def test_weather_sandbox_has_second_mcp_tool_gate() -> None:
    config = load_agent(AGENT_CONFIG_PATHS["weather"])

    assert config.sandbox.mode == "all"
    assert {"group:runtime", "group:fs"} <= set(config.tools.deny)
    assert config.tools.sandbox is not None
    assert "bundle-mcp" in config.tools.sandbox.tools.allow


def test_gateway_registers_traderbot_mcp_server_once() -> None:
    gateway = GatewayConfig.model_validate_json(GATEWAY_CONFIG_PATH.read_text(encoding="utf-8"))

    assert gateway.model_fields_set == {"mcp"}
    assert gateway.mcp.servers.model_fields_set == {"traderbot"}
    assert gateway.mcp.servers.traderbot.command == "traderbot-mcp-server"
    assert gateway.mcp.servers.traderbot.transport == "stdio"
