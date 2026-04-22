"""Token injection into OpenClaw agent TOOLS.md files

Provides functions to inject, remove, and retrieve profile tokens from
OpenClaw agent TOOLS.md files for automatic authentication.
"""

import re
import tempfile
from pathlib import Path


def inject_token_into_tools(agent_path: str, token: str) -> None:
    """Inject profile token into agent's TOOLS.md file
    
    Args:
        agent_path: Path to agent directory (e.g., .openclaw/workspace/agent-id)
        token: Profile token to inject
        
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
    
    # Token line to inject
    token_line = f"- `TRADERBOT_PROFILE_TOKEN={token}`: Your assigned profile token (do not modify)"
    
    # Check if Environment Variables section exists
    env_section_pattern = r"## Environment Variables\s*\n"
    env_section_match = re.search(env_section_pattern, content)
    
    if env_section_match:
        # Section exists - check if token already present
        token_pattern = r"- `TRADERBOT_PROFILE_TOKEN=[^`]+`: Your assigned profile token \(do not modify\)"
        
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
    
    # Remove token line (with or without value)
    token_pattern = r"- `TRADERBOT_PROFILE_TOKEN[^`]*`: Your assigned profile token \(do not modify\)\n?"
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
    """Extract profile token from agent's TOOLS.md file
    
    Args:
        agent_path: Path to agent directory (e.g., .openclaw/workspace/agent-id)
        
    Returns:
        Token string if found, None otherwise
    """
    agent_dir = Path(agent_path)
    tools_path = agent_dir / "TOOLS.md"
    
    if not tools_path.exists():
        return None
    
    content = tools_path.read_text()
    
    # Extract token from line
    token_pattern = r"- `TRADERBOT_PROFILE_TOKEN=([^`]+)`:"
    match = re.search(token_pattern, content)
    
    if match:
        return match.group(1)
    
    return None

# Made with Bob
