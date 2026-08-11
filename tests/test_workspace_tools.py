import re
from pathlib import Path
from typing import Final

from traderbot.kalshi.models import MarketCategory
from traderbot.mcp.tools import TOOL_DEFINITIONS

PROJECT_ROOT: Final = Path(__file__).parents[1]
WORKSPACE_DIR: Final = PROJECT_ROOT / "workspace"
CATEGORY_NAMES: Final = tuple(category.value for category in MarketCategory)
AGENTS_PATHS: Final = [
    WORKSPACE_DIR / agent / "AGENTS.md"
    for agent in ("sysadmin", "dev-liaison", *CATEGORY_NAMES)
]


def _tools_section(content: str) -> str:
    return content.split("## Tools\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_agents_tools_sections_are_canonical_and_match_definitions() -> None:
    # Given
    expected = {str(definition["name"]) for definition in TOOL_DEFINITIONS}

    # When
    sections = [_tools_section(path.read_text(encoding="utf-8")) for path in AGENTS_PATHS]

    # Then
    assert len(set(sections)) == 1
    for agents_path, section in zip(AGENTS_PATHS, sections, strict=True):
        content = agents_path.read_text(encoding="utf-8")
        documented = set(re.findall(r"^### `traderbot__(\w+)`$", section, re.MULTILINE))
        assert content.count("## Tools\n") == 1
        assert documented == expected


def test_full_workspace_template_inventories() -> None:
    expected = {
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "USER.md",
        "SESSION-STATE.md",
        ".learnings",
    }

    for workspace_name in ("weather", "sysadmin"):
        assert {path.name for path in (WORKSPACE_DIR / workspace_name).iterdir()} == expected
        assert (WORKSPACE_DIR / workspace_name / ".learnings").is_dir()


def test_minimal_category_template_inventories() -> None:
    expected = {"AGENTS.md", "SOUL.md", "IDENTITY.md"}

    for category in CATEGORY_NAMES[1:]:
        assert {path.name for path in (WORKSPACE_DIR / category).iterdir()} == expected


def test_dev_liaison_template_contains_only_agents_guidance() -> None:
    assert {path.name for path in (WORKSPACE_DIR / "dev-liaison").iterdir()} == {"AGENTS.md"}


def test_packaged_workspace_source_excludes_legacy_openclaw_files() -> None:
    legacy_names = {"TOOLS.md", "HEARTBEAT.md"}

    assert not [path for path in WORKSPACE_DIR.rglob("*") if path.name in legacy_names]
