from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_PATH: Final = Path(__file__).parents[1] / "configs" / "openclaw" / "with-plugin.json"
INFISICAL_COMMAND: Final = "/usr/local/bin/openclaw-infisical-resolver"


class StrictConfigModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SecretRef(StrictConfigModel):
    source: Literal["env", "file", "exec"]
    provider: str
    id: str


class AgentTokenMapConfig(StrictConfigModel):
    agentTokenMap: dict[str, SecretRef]


class PluginEntryConfig(StrictConfigModel):
    config: AgentTokenMapConfig


class PluginEntriesConfig(StrictConfigModel):
    traderbot_token_injector: PluginEntryConfig = Field(alias="traderbot-token-injector")


class PluginLoadConfig(StrictConfigModel):
    paths: list[str]


class PluginsConfig(StrictConfigModel):
    load: PluginLoadConfig
    entries: PluginEntriesConfig


class ExecProviderConfig(StrictConfigModel):
    source: Literal["exec"]
    command: str
    args: list[str]
    passEnv: list[str]
    jsonOnly: bool


class SecretsProvidersConfig(StrictConfigModel):
    infisical: ExecProviderConfig


class SecretsConfig(StrictConfigModel):
    providers: SecretsProvidersConfig


class McpServerConfig(StrictConfigModel):
    command: Literal["traderbot-mcp-server"]
    transport: Literal["stdio"]
    env: dict[str, str] | None = None


class McpServersConfig(StrictConfigModel):
    traderbot: McpServerConfig


class McpConfig(StrictConfigModel):
    servers: McpServersConfig


class WithPluginConfig(StrictConfigModel):
    plugins: PluginsConfig
    secrets: SecretsConfig
    mcp: McpConfig


def load_with_plugin_config() -> WithPluginConfig:
    return WithPluginConfig.model_validate_json(CONFIG_PATH.read_text(encoding="utf-8"))


def test_with_plugin_uses_infisical_provider_not_vault() -> None:
    providers = load_with_plugin_config().secrets.providers

    assert providers.model_fields_set == {"infisical"}
    assert "vault" not in providers.model_fields_set


def test_infisical_provider_is_exec_with_absolute_resolver_command() -> None:
    provider = load_with_plugin_config().secrets.providers.infisical

    assert provider.source == "exec"
    assert provider.command == INFISICAL_COMMAND
    assert provider.command.startswith("/usr/local/bin/")
    assert provider.jsonOnly is True
    assert set(provider.passEnv) == {"INFISICAL_TOKEN", "INFISICAL_DOMAIN"}


def test_agent_token_map_uses_exec_source_with_infisical_provider() -> None:
    entries = load_with_plugin_config().plugins.entries
    token_map = entries.traderbot_token_injector.config.agentTokenMap

    assert set(token_map) == {"weather", "sysadmin", "dev-liaison"}
    for agent_id, secret_ref in token_map.items():
        assert secret_ref.source == "exec"
        assert secret_ref.provider == "infisical"
        assert secret_ref.id == f"{agent_id}_token"


def test_traderbot_mcp_server_env_enables_real_auth() -> None:
    server = load_with_plugin_config().mcp.servers.traderbot

    assert server.command == "traderbot-mcp-server"
    assert server.transport == "stdio"
    assert server.env == {"TRADERBOT_USE_HARDCODED_AUTH": "0"}
