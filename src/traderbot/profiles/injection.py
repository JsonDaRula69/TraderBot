"""Token injection into OpenClaw agent TOOLS.md files (DEPRECATED).

Provides stub functions kept for backward compatibility.
All profile token injection is disabled per security fix.
"""

import logging
import shutil
from pathlib import Path

from traderbot.profiles.injection_strategies import (
    FENCED_BLOCK_MARKERS,
    FILE_STRATEGIES,
    InjectionStrategy,
    ask_then_merge,
    fenced_merge,
    init_if_missing,
    inject_agents_block,
    inject_profile_into_identity,
    inject_soul_block,
)

logger = logging.getLogger(__name__)


def propagate_workspace_files(profile, target_dir: Path, overwrite: bool = False) -> None:
    """Deploy workspace templates using merge strategies per FILE_STRATEGIES.

    If overwrite is True, template content replaces target files entirely.
    If overwrite is False (default), templates are merged using fenced blocks.
    """
    _src_dir = Path(__file__).resolve().parent.parent.parent
    template_dir = _src_dir.parent / ".openclaw" / "workspace"

    target_dir.mkdir(parents=True, exist_ok=True)

    for filename, strategy in FILE_STRATEGIES.items():
        if filename.endswith("/"):
            target_path = target_dir / filename.rstrip("/")
            _handle_directory_merge(template_dir, target_path, strategy)
            continue

        template_path = template_dir / filename
        target_path = target_dir / filename

        if not template_path.exists():
            logger.debug("Template %s not found, skipping", filename)
            continue

        template_content = template_path.read_text()

        if overwrite and target_path.exists():
            shutil.copy2(template_path, target_path)
            logger.info("Overwrote %s", target_path)
            continue

        if strategy == InjectionStrategy.FENCED_MERGE:
            match filename:
                case "AGENTS.md":
                    inject_agents_block(template_content, target_path)
                case "SOUL.md":
                    inject_soul_block(template_content, target_path)
                case "TOOLS.md":
                    markers = FENCED_BLOCK_MARKERS.get(filename)
                    if markers:
                        fenced_merge(template_content, target_path, markers)
                case "IDENTITY.md":
                    inject_profile_into_identity(profile, target_path)
                case _:
                    markers = FENCED_BLOCK_MARKERS.get(filename)
                    if markers:
                        fenced_merge(template_content, target_path, markers)
        elif strategy == InjectionStrategy.INIT_IF_MISSING:
            init_if_missing(template_content, target_path)
        elif strategy == InjectionStrategy.ASK_THEN_MERGE:
            markers = FENCED_BLOCK_MARKERS.get(filename)
            if markers:
                ask_then_merge(template_content, target_path, markers, filename)
            else:
                init_if_missing(template_content, target_path)


def _handle_directory_merge(
    template_dir: Path, target_path: Path, strategy: InjectionStrategy
) -> None:
    if strategy != InjectionStrategy.INIT_IF_MISSING:
        return
    if target_path.exists():
        return
    src_dir = template_dir / (target_path.name + "/")
    if not src_dir.exists():
        return
    target_path.mkdir(parents=True, exist_ok=True)
    for filepath in src_dir.rglob("*"):
        if filepath.is_file():
            rel = filepath.relative_to(src_dir)
            dst = target_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(filepath.read_text())


def inject_token(agent_path: str, token: str | None = None) -> None:
    """Stub: profile token injection is disabled.

    Previously injected a reference to TRADERBOT_PROFILE_TOKEN into an
    agent's TOOLS.md. That mechanism has been removed for security.
    """
    logger.debug("inject_token is a no-op after token-injection removal")


def remove_token_from_tools(agent_path: str) -> None:
    """Stub: profile token removal is disabled.

    Previously removed TRADERBOT_PROFILE_TOKEN references from an agent's
    TOOLS.md. That mechanism has been removed for security.
    """
    logger.debug("remove_token_from_tools is a no-op after token-injection removal")


def get_token_from_tools(agent_path: str) -> None:
    """Stub: always returns None.

    Previously checked whether a TRADERBOT_PROFILE_TOKEN reference existed
    in an agent's TOOLS.md. That mechanism has been removed for security.
    """
    return None
