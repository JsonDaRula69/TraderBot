import re
from pathlib import Path
from typing import Final

from traderbot.mcp.tools import TOOL_DEFINITIONS

WORKSPACE_DIR: Final = Path(__file__).parents[1] / "workspace"
TOOLS_PATHS: Final = [
    WORKSPACE_DIR / agent / "TOOLS.md" for agent in ("sysadmin", "dev-liaison", "weather")
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
