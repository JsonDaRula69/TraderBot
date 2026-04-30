"""OpenClaw agent auto-discovery from IDENTITY.md files."""

import re
from pathlib import Path


def discover_agents(workspace_dir: str = ".openclaw/workspace") -> list[dict[str, str]]:
    """Scan workspace for agent directories and discover valid agents.

    When workspace_dir is the default, also checks ~/.openclaw/workspace/
    and ~/traderbot/.openclaw/workspace/. When explicitly provided, only
    that path is searched.
    """
    agents = []

    search_paths = _resolve_search_paths(workspace_dir)

    for path in search_paths:
        for agent_path in list_agent_dirs(path):
            identity = get_agent_identity(agent_path)
            if identity:
                agents.append({
                    "agent_id": identity["agent_id"],
                    "name": identity["name"],
                    "path": agent_path,
                })

        identity = get_agent_identity(path)
        if identity:
            agents.append({
                "agent_id": identity["agent_id"],
                "name": identity["name"],
                "path": path,
            })

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for a in agents:
        if a["agent_id"] not in seen:
            seen.add(a["agent_id"])
            unique.append(a)

    return unique


def _resolve_search_paths(workspace_dir: str) -> list[str]:
    """Resolve workspace search paths in priority order."""
    from pathlib import Path as P

    explicit = P(workspace_dir)
    if workspace_dir != ".openclaw/workspace":
        return [str(explicit)] if explicit.exists() else []

    candidates = [
        explicit,
        P.home() / ".openclaw" / "workspace",
        P.home() / "traderbot" / ".openclaw" / "workspace",
    ]
    return [str(p) for p in candidates if p.exists() and p.is_dir()]


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
