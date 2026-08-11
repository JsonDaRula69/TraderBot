import re
from pathlib import Path
from typing import Final

from traderbot.kalshi.models import MarketCategory
from traderbot.mcp.tools import TOOL_DEFINITIONS

WORKSPACE_DIR: Final = Path(__file__).parents[1] / "workspace"
CATEGORY_NAMES: Final = tuple(category.value for category in MarketCategory)
TOOLS_PATHS: Final = [
    WORKSPACE_DIR / agent / "TOOLS.md"
    for agent in ("sysadmin", "dev-liaison", *CATEGORY_NAMES)
]


def test_tools_md_matches_definitions() -> None:
    expected = {str(definition["name"]) for definition in TOOL_DEFINITIONS}

    for tools_path in TOOLS_PATHS:
        content = tools_path.read_text(encoding="utf-8")
        available_section = content.split("## Currently Available Tools", maxsplit=1)[1].split(
            "## Planned Tools", maxsplit=1
        )[0]
        documented = set(re.findall(r"^### `traderbot__(\w+)`$", available_section, re.MULTILINE))
        assert documented == expected


def test_token_instruction_present() -> None:
    for tools_path in TOOLS_PATHS:
        content = tools_path.read_text(encoding="utf-8")
        assert "Token Injector" in content
        assert "host-side" in content


def test_market_edge_is_documented_as_current_stub() -> None:
    for tools_path in TOOLS_PATHS:
        content = tools_path.read_text(encoding="utf-8")
        section = content.split("### `traderbot__market_edge`", maxsplit=1)[1].split(
            "### `traderbot__market_prices`", maxsplit=1
        )[0]

        assert "status: stub" in section
        assert "does not compute" in section
        assert "Compute the estimated edge" not in section


def test_existing_weather_tools_characterization() -> None:
    content = (WORKSPACE_DIR / "weather" / "TOOLS.md").read_text(encoding="utf-8")
    available_section = content.split("## Currently Available Tools", maxsplit=1)[1].split(
        "## Planned Tools", maxsplit=1
    )[0]

    assert set(re.findall(r"^### `traderbot__(\w+)`$", available_section, re.MULTILINE)) == {
        "health",
        "auth_check",
        "profile_list",
        "market_edge",
        "market_prices",
    }


def test_full_workspace_template_inventories() -> None:
    expected = {
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "HEARTBEAT.md",
        "USER.md",
        "SESSION-STATE.md",
        ".learnings",
    }

    for workspace_name in ("weather", "sysadmin"):
        assert {path.name for path in (WORKSPACE_DIR / workspace_name).iterdir()} == expected
        assert (WORKSPACE_DIR / workspace_name / ".learnings").is_dir()


def test_minimal_category_template_inventories() -> None:
    expected = {"AGENTS.md", "SOUL.md", "IDENTITY.md", "TOOLS.md", "HEARTBEAT.md"}

    for category in CATEGORY_NAMES[1:]:
        assert {path.name for path in (WORKSPACE_DIR / category).iterdir()} == expected
