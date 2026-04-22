"""OpenClaw agent auto-discovery from IDENTITY.md files."""

import re
from pathlib import Path


def discover_agents(workspace_dir: str = ".openclaw/workspace") -> list[dict[str, str]]:
    """
    Scan workspace for agent directories and discover valid agents.
    
    Args:
        workspace_dir: Path to OpenClaw workspace directory
        
    Returns:
        List of dicts with agent_id, name, and path for each valid agent
    """
    agents = []
    
    for agent_path in list_agent_dirs(workspace_dir):
        identity = get_agent_identity(agent_path)
        if identity:
            agents.append({
                "agent_id": identity["agent_id"],
                "name": identity["name"],
                "path": agent_path,
            })
    
    return agents


def get_agent_identity(agent_path: str) -> dict[str, str] | None:
    """
    Read IDENTITY.md from agent directory and extract agent_id and name.
    
    Args:
        agent_path: Path to agent directory
        
    Returns:
        Dict with agent_id and name, or None if invalid/missing
    """
    identity_file = Path(agent_path) / "IDENTITY.md"
    
    if not identity_file.exists():
        return None
    
    try:
        content = identity_file.read_text()
    except Exception:
        return None
    
    # Parse agent_id and name using regex
    # Format: - **Agent ID**: molty
    #         - **Name**: Molty the Trader
    agent_id_match = re.search(
        r'-\s*\*\*\s*agent\s+id\s*\*\*\s*:\s*(.+?)(?:\n|$)',
        content,
        re.IGNORECASE
    )
    name_match = re.search(
        r'-\s*\*\*\s*name\s*\*\*\s*:\s*(.+?)(?:\n|$)',
        content,
        re.IGNORECASE
    )
    
    if not agent_id_match or not name_match:
        return None
    
    agent_id = agent_id_match.group(1).strip()
    name = name_match.group(1).strip()
    
    if not agent_id or not name:
        return None
    
    return {
        "agent_id": agent_id,
        "name": name,
    }


def list_agent_dirs(workspace_dir: str) -> list[str]:
    """
    List all agent directory paths in workspace.
    
    Args:
        workspace_dir: Path to OpenClaw workspace directory
        
    Returns:
        List of agent directory paths
    """
    workspace_path = Path(workspace_dir)
    
    if not workspace_path.exists() or not workspace_path.is_dir():
        return []
    
    agent_dirs = []
    for item in workspace_path.iterdir():
        if item.is_dir():
            agent_dirs.append(str(item))
    
    return sorted(agent_dirs)

# Made with Bob
