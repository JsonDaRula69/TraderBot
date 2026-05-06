"""Merge strategies for workspace file injection.

Replaces destructive shutil.copy2 overwrites with non-destructive merge
strategies that preserve customizations in existing agent workspace files.
"""

from __future__ import annotations

import logging
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


class InjectionStrategy(StrEnum):
    """Strategy for injecting a template file into an agent workspace."""

    FENCED_MERGE = "fenced_merge"
    INIT_IF_MISSING = "init_if_missing"
    ASK_THEN_MERGE = "ask_then_merge"


FENCED_BLOCK_MARKERS: dict[str, tuple[str, str]] = {
    "AGENTS.md": ("<!-- TRADERBOT_RULES_START -->", "<!-- TRADERBOT_RULES_END -->"),
    "SOUL.md": ("<!-- TRADERBOT_SOUL_START -->", "<!-- TRADERBOT_SOUL_END -->"),
    "TOOLS.md": ("<!-- TRADERBOT_TOOLS_START -->", "<!-- TRADERBOT_TOOLS_END -->"),
    "IDENTITY.md": ("<!-- TRADERBOT_PROFILE_START -->", "<!-- TRADERBOT_PROFILE_END -->"),
    "BOOTSTRAP.md": ("<!-- TRADERBOT_BOOTSTRAP_START -->", "<!-- TRADERBOT_BOOTSTRAP_END -->"),
    "BOOT.md": ("<!-- TRADERBOT_BOOT_START -->", "<!-- TRADERBOT_BOOT_END -->"),
    "HEARTBEAT.md": ("<!-- TRADERBOT_HEARTBEAT_START -->", "<!-- TRADERBOT_HEARTBEAT_END -->"),
}

FILE_STRATEGIES: dict[str, InjectionStrategy] = {
    "AGENTS.md": InjectionStrategy.FENCED_MERGE,
    "SOUL.md": InjectionStrategy.FENCED_MERGE,
    "TOOLS.md": InjectionStrategy.FENCED_MERGE,
    "IDENTITY.md": InjectionStrategy.FENCED_MERGE,
    "BOOTSTRAP.md": InjectionStrategy.ASK_THEN_MERGE,
    "BOOT.md": InjectionStrategy.ASK_THEN_MERGE,
    "HEARTBEAT.md": InjectionStrategy.ASK_THEN_MERGE,
    "USER.md": InjectionStrategy.INIT_IF_MISSING,
    "MEMORY.md": InjectionStrategy.INIT_IF_MISSING,
    "SESSION-STATE.md": InjectionStrategy.INIT_IF_MISSING,
    "HEARTBEAT_DATA.md": InjectionStrategy.INIT_IF_MISSING,
    ".learnings/": InjectionStrategy.INIT_IF_MISSING,
}


def _extract_fenced_block(content: str, start_marker: str, end_marker: str) -> str:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        return ""
    start_idx += len(start_marker)
    return content[start_idx:end_idx].strip()


def _replace_fenced_block(
    content: str, start_marker: str, end_marker: str, new_block: str
) -> str:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        return (
            content + "\n\n" + start_marker + "\n" + new_block + "\n" + end_marker + "\n"
        )
    after_start = start_idx + len(start_marker)
    return content[:after_start] + "\n" + new_block + "\n" + content[end_idx:]


def _extract_marked_section(
    template_content: str, start_marker: str, end_marker: str
) -> str:
    start_idx = template_content.find(start_marker)
    end_idx = template_content.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        return template_content
    end_idx += len(end_marker)
    return template_content[start_idx:end_idx]


def fenced_merge(
    template_content: str, target_path: Path, markers: tuple[str, str]
) -> None:
    """Inject or replace content between fenced markers in target file.

    If target doesn't exist, writes the full template.
    If target has markers, replaces the block between them.
    If target lacks markers, appends the block at the end.
    """
    start_marker, end_marker = markers
    block = _extract_fenced_block(template_content, start_marker, end_marker)
    if not target_path.exists():
        target_path.write_text(template_content)
        return
    existing = target_path.read_text()
    if start_marker in existing and end_marker in existing:
        new_content = _replace_fenced_block(existing, start_marker, end_marker, block)
    else:
        new_content = existing.rstrip() + "\n\n" + block + "\n"
    target_path.write_text(new_content)


def init_if_missing(template_content: str, target_path: Path) -> bool:
    """Deploy template if file absent, skip if already exists.

    Returns True if file was deployed, False if skipped.
    """
    if target_path.exists():
        return False
    target_path.write_text(template_content)
    return True


def ask_then_merge(
    template_content: str,
    target_path: Path,
    markers: tuple[str, str],
    file_label: str,
) -> bool:
    """Prompt user for confirmation, then fenced_merge if accepted.

    In non-interactive mode (no TTY), falls back to init_if_missing.

    Returns True if merge was applied, False otherwise.
    """
    if not sys.stdin.isatty():
        return init_if_missing(template_content, target_path)
    try:
        response = input(f"Apply TraderBot template for {file_label}? [y/N]: ")
        if response.lower().startswith("y"):
            fenced_merge(template_content, target_path, markers)
            return True
    except EOFError:
        pass
    return False


def inject_profile_into_identity(profile: TradingProfile, target_path: Path) -> bool:
    """Inject trading profile info into IDENTITY.md via fenced markers.

    Builds a profile block from TradingProfile fields and delegates to
    fenced_merge using the IDENTITY.md marker pair. Returns True on
    successful injection, False on failure.
    """
    markers = FENCED_BLOCK_MARKERS["IDENTITY.md"]
    start_marker, end_marker = markers

    category = profile.enabled_categories[0].value if profile.enabled_categories else "auto"
    categories_str = ", ".join(c.value for c in profile.enabled_categories)

    profile_block = f"""<!-- TRADERBOT_PROFILE_START -->
- **Name**: {profile.name}
- **Category**: {category}
- **Risk Multiplier**: {profile.risk_multiplier}
- **Max Position %**: {profile.max_position_per_market_pct}
- **Enabled Categories**: {categories_str}
<!-- TRADERBOT_PROFILE_END -->"""

    try:
        if target_path.exists():
            existing = target_path.read_text()
            if start_marker in existing and end_marker in existing:
                inner = _extract_fenced_block(profile_block, start_marker, end_marker)
                new_content = _replace_fenced_block(existing, start_marker, end_marker, inner)
            else:
                new_content = existing.rstrip() + "\n\n" + profile_block + "\n"
            target_path.write_text(new_content)
        else:
            target_path.write_text(profile_block)
        return True
    except Exception:
        logger.exception("Failed to inject profile into identity")
        return False


def inject_agents_block(template: str, target_path: Path) -> bool:
    """Inject trader rules block into AGENTS.md using fenced markers."""
    markers = FENCED_BLOCK_MARKERS["AGENTS.md"]
    try:
        fenced_merge(template, target_path, markers)
        return True
    except Exception:
        logger.exception("Failed to inject agents block")
        return False


def inject_soul_block(template: str, target_path: Path) -> bool:
    """Inject personality block into SOUL.md using fenced markers."""
    markers = FENCED_BLOCK_MARKERS["SOUL.md"]
    try:
        fenced_merge(template, target_path, markers)
        return True
    except Exception:
        logger.exception("Failed to inject soul block")
        return False
