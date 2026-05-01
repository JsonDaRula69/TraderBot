"""OpenClaw agent auto-discovery from IDENTITY.md files."""

import json
import re
from pathlib import Path

_OPENCLAW_DIR = Path.home() / ".openclaw"
_OPENCLAW_CONFIG = _OPENCLAW_DIR / "openclaw.json"


def _get_openclaw_dir() -> Path:
    return Path.home() / ".openclaw"


def _get_openclaw_config() -> Path:
    return _get_openclaw_dir() / "openclaw.json"


def discover_agents(workspace_dir: str = ".openclaw/workspace") -> list[dict[str, str]]:
    """Scan OpenClaw multi-agent layout and workspace directories for agents.

    Search order:
    1. ~/.openclaw/openclaw.json agents.list (authoritative multi-agent config)
    2. ~/.openclaw/agents/<agentId>/ workspace directories
    3. Workspace directories (default, CWD, ~/traderbot)
    """
    agents = []
    seen: set[str] = set()

    for agent in _discover_from_config():
        if agent["agent_id"] not in seen:
            seen.add(agent["agent_id"])
            agents.append(agent)

    for agent in _discover_from_agent_dirs():
        if agent["agent_id"] not in seen:
            seen.add(agent["agent_id"])
            agents.append(agent)

    for agent in _discover_from_workspaces(workspace_dir):
        if agent["agent_id"] not in seen:
            seen.add(agent["agent_id"])
            agents.append(agent)

    return agents


def _discover_from_config() -> list[dict[str, str]]:
    """Parse openclaw.json for agent definitions."""
    config_path = _get_openclaw_config()
    if not config_path.exists():
        return []

    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    agent_list = _get_nested(config, ["agents", "list"]) or []
    if not isinstance(agent_list, list):
        return []

    results = []
    for agent_conf in agent_list:
        if not isinstance(agent_conf, dict):
            continue
        agent_id = agent_conf.get("id", "")
        if not agent_id:
            continue
        workspace = agent_conf.get("workspace", "")
        if workspace:
            workspace = str(Path(workspace).expanduser())
        name = agent_conf.get("name", agent_id)
        results.append({
            "agent_id": agent_id,
            "name": name,
            "path": workspace or str(_get_openclaw_dir() / "workspace"),
        })

    return results


def _discover_from_agent_dirs() -> list[dict[str, str]]:
    """Scan ~/.openclaw/agents/<agentId>/ for workspaces with IDENTITY.md."""
    agents_dir = _get_openclaw_dir() / "agents"
    if not agents_dir.exists():
        return []

    results = []
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        identity = get_agent_identity(str(agent_dir))
        if identity:
            results.append({
                "agent_id": identity["agent_id"],
                "name": identity["name"],
                "path": str(agent_dir),
            })

    return results


def _discover_from_workspaces(workspace_dir: str) -> list[dict[str, str]]:
    """Scan workspace directories for IDENTITY.md files."""
    search_paths = _resolve_search_paths(workspace_dir)
    results = []

    for path in search_paths:
        for agent_path in list_agent_dirs(path):
            identity = get_agent_identity(agent_path)
            if identity:
                results.append({
                    "agent_id": identity["agent_id"],
                    "name": identity["name"],
                    "path": agent_path,
                })

        identity = get_agent_identity(path)
        if identity:
            results.append({
                "agent_id": identity["agent_id"],
                "name": identity["name"],
                "path": path,
            })

    return results


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


def _get_nested(data: dict, keys: list[str]) -> object:
    """Get a nested value from a dict by a list of keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def get_agent_identity(agent_path: str) -> dict[str, str] | None:
    """Read IDENTITY.md from agent directory and extract agent_id and name."""
    identity_file = Path(agent_path) / "IDENTITY.md"

    if not identity_file.exists():
        return None

    try:
        content = identity_file.read_text()
    except Exception:
        return None

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
    """List all subdirectory paths in a workspace directory."""
    workspace_path = Path(workspace_dir)

    if not workspace_path.exists() or not workspace_path.is_dir():
        return []

    agent_dirs = []
    for item in workspace_path.iterdir():
        if item.is_dir():
            agent_dirs.append(str(item))

    return sorted(agent_dirs)