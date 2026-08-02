import json
from pathlib import Path
from typing import Final

from traderbot.mcp.tools import TOOL_DEFINITIONS
from traderbot.profiles import ProfileRegistry

CONFIG_DIR: Final = Path(__file__).parents[1] / "configs" / "openclaw"
CONFIG_PATHS: Final = {
    agent: CONFIG_DIR / f"{agent}.json" for agent in ("sysadmin", "dev-liaison", "weather")
}


def test_configs_are_valid_json() -> None:
    for config_path in CONFIG_PATHS.values():
        _ = json.loads(config_path.read_text(encoding="utf-8"))


def test_configs_match_registry_list_profiles() -> None:
    registry_profiles = ProfileRegistry().list_profiles()
    current_tools = {f"traderbot__{str(definition['name'])}" for definition in TOOL_DEFINITIONS}
    general_tools = {
        "traderbot__health",
        "traderbot__auth_check",
        "traderbot__profile_list",
    }

    for agent, config_path in CONFIG_PATHS.items():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = set(config["tools"]["alsoAllow"])
        denied = set(config["tools"]["deny"])
        effective_current = (allowed & current_tools) - denied
        profile_permissions = set(registry_profiles[agent]["permissions"])
        assert effective_current <= profile_permissions | general_tools

    weather_config = json.loads(CONFIG_PATHS["weather"].read_text(encoding="utf-8"))
    weather_allowed = set(weather_config["tools"]["alsoAllow"])
    weather_extras = {"bundle-mcp", "sessions_send"}
    assert weather_allowed - weather_extras == set(registry_profiles["weather"]["permissions"])


def test_secretref_names_correct() -> None:
    expected = {
        "sysadmin": "traderbot_sysadmin_token",
        "dev-liaison": "traderbot_dev_liaison_token",
        "weather": "traderbot_weather_token",
    }

    for agent, secret_ref in expected.items():
        config = json.loads(CONFIG_PATHS[agent].read_text(encoding="utf-8"))
        assert config["env"]["TRADERBOT_PROFILE_TOKEN"]["secretRef"] == secret_ref
