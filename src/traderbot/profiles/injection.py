"""Token injection into OpenClaw agent TOOLS.md files

Provides functions to inject, remove, and retrieve profile tokens from
OpenClaw agent TOOLS.md files for automatic authentication.
"""

import logging
import re
import tempfile
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


def propagate_workspace_files(profile, target_dir: Path) -> None:
    """Deploy workspace templates using merge strategies per FILE_STRATEGIES."""
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
    """Inject profile token reference into agent's TOOLS.md file

    The token VALUE is never written to TOOLS.md. Instead, a reference to the
    TRADERBOT_PROFILE_TOKEN environment variable is injected so the agent reads
    it at runtime.

    Args:
        agent_path: Path to agent directory (e.g., .openclaw/workspace/agent-id)
        token: Ignored (kept for backward compatibility).

    Raises:
        FileNotFoundError: If agent directory doesn't exist
    """
    agent_dir = Path(agent_path)
    if not agent_dir.exists():
        raise FileNotFoundError(f"Agent directory not found: {agent_path}")

    tools_path = agent_dir / "TOOLS.md"

    # Read existing content or create minimal content
    if tools_path.exists():
        content = tools_path.read_text()
    else:
        content = "# Agent Tools\n\nThis file describes available tools.\n\n"

    # Token line to inject — reference the env var, not the value
    token_line = "- `TRADERBOT_PROFILE_TOKEN`: Your assigned profile token (read from environment variable, do not modify)"

    # Check if Environment Variables section exists
    env_section_pattern = r"## Environment Variables\s*\n"
    env_section_match = re.search(env_section_pattern, content)

    if env_section_match:
        token_pattern = r"- `TRADERBOT_PROFILE_TOKEN[^`]*`:[^\n]+"

        if re.search(token_pattern, content):
            # Replace existing token
            content = re.sub(token_pattern, token_line, content)
        else:
            # Add token after "The following environment variables are available:" line
            # or right after the section header if that line doesn't exist
            insert_pattern = r"(## Environment Variables\s*\n(?:The following environment variables are available:\s*\n)?)"
            content = re.sub(
                insert_pattern,
                r"\1" + token_line + "\n",
                content,
                count=1
            )
    else:
        # Section doesn't exist - create it at the end
        env_section = f"""## Environment Variables

The following environment variables are available:
{token_line}

"""
        content = content.rstrip() + "\n\n" + env_section

    # Atomic write using temp file
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=agent_dir,
        delete=False,
        suffix='.tmp'
    ) as tmp_file:
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    # Rename temp file to TOOLS.md
    tmp_path.replace(tools_path)


def remove_token_from_tools(agent_path: str) -> None:
    """Remove profile token from agent's TOOLS.md file

    Args:
        agent_path: Path to agent directory (e.g., .openclaw/workspace/agent-id)
    """
    agent_dir = Path(agent_path)
    tools_path = agent_dir / "TOOLS.md"

    if not tools_path.exists():
        return  # No-op if file doesn't exist

    content = tools_path.read_text()

    token_pattern = r"- `TRADERBOT_PROFILE_TOKEN[^`]*`: Your assigned profile token[^\n]+"
    content = re.sub(token_pattern, "", content)

    # Atomic write using temp file
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=agent_dir,
        delete=False,
        suffix='.tmp'
    ) as tmp_file:
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    # Rename temp file to TOOLS.md
    tmp_path.replace(tools_path)


def get_token_from_tools(agent_path: str) -> str | None:
    """Check if profile token reference exists in agent's TOOLS.md file

    Args:
        agent_path: Path to agent directory (e.g., .openclaw/workspace/agent-id)

    Returns:
        The string 'TRADERBOT_PROFILE_TOKEN' if reference found, None otherwise
    """
    agent_dir = Path(agent_path)
    tools_path = agent_dir / "TOOLS.md"

    if not tools_path.exists():
        return None

    content = tools_path.read_text()

    if "TRADERBOT_PROFILE_TOKEN" in content:
        return "TRADERBOT_PROFILE_TOKEN"

    return None

