"""OpenClaw agent discovery from openclaw.json config."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_OPENCLAW_DIR = Path.home() / ".openclaw"
_OPENCLAW_CONFIG = _OPENCLAW_DIR / "openclaw.json"


def _get_openclaw_dir() -> Path:
    return Path.home() / ".openclaw"


def _get_openclaw_config() -> Path:
    return _get_openclaw_dir() / "openclaw.json"


def discover_agents(workspace_dir: str = ".openclaw/workspace") -> list[dict[str, str]]:
    """Discover agents from openclaw.json, agent dirs, and workspaces."""
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

    logger.info("Discovered %d agents", len(agents))
    return agents


def _discover_from_config() -> list[dict[str, str]]:
    """Parse openclaw.json for agent definitions — the authoritative source."""
    config_path = _get_openclaw_config()
    if not config_path.exists():
        logger.debug("No openclaw config found at %s", config_path)
        return []

    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read openclaw config from %s", config_path)
        return []

    agents_section = config.get("agents", {})
    agent_list = agents_section.get("list", [])
    if not isinstance(agent_list, list):
        return []

    default_workspace = agents_section.get("defaults", {}).get("workspace", "")

    results = []
    for agent_conf in agent_list:
        if not isinstance(agent_conf, dict):
            continue
        agent_id = agent_conf.get("id", "")
        if not agent_id:
            continue

        name = agent_conf.get("name", agent_id)

        # Determine the most relevant path for this agent
        workspace = agent_conf.get("workspace") or default_workspace
        agent_dir = agent_conf.get("agentDir", "")

        # Prefer existing workspace, then existing agentDir, then workspace path
        path_found: str | None = None

        if workspace:
            p = Path(workspace).expanduser()
            if p.exists() and p.is_dir():
                path_found = str(p)
            elif not agent_dir:
                # Workspace doesn't exist yet, but it's the configured path — include it anyway
                path_found = str(p)

        if path_found is None and agent_dir:
            p = Path(agent_dir).expanduser()
            if p.exists() and p.is_dir():
                path_found = str(p)

        if path_found is None and workspace:
            path_found = str(Path(workspace).expanduser())

        if path_found:
            results.append({"agent_id": agent_id, "name": name, "path": path_found})

    return results


def _discover_from_agent_dirs() -> list[dict[str, str]]:
    """Scan ~/.openclaw/agents/<agentId>/ for workspaces with IDENTITY.md."""
    agents_dir = _get_openclaw_dir() / "agents"
    if not agents_dir.exists():
        logger.debug("No agents dir found at %s", agents_dir)
        return []

    results = []
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        identity = get_agent_identity(str(agent_dir))
        if identity:
            results.append(
                {
                    "agent_id": identity["agent_id"],
                    "name": identity["name"],
                    "path": str(agent_dir),
                }
            )

    logger.debug("Discovered %d agents from agent dirs", len(results))
    return results


def _discover_from_workspaces(workspace_dir: str) -> list[dict[str, str]]:
    """Scan workspace directories for IDENTITY.md files."""
    search_paths = _resolve_search_paths(workspace_dir)
    results = []

    for path in search_paths:
        for agent_path in list_agent_dirs(path):
            identity = get_agent_identity(agent_path)
            if identity:
                results.append(
                    {
                        "agent_id": identity["agent_id"],
                        "name": identity["name"],
                        "path": agent_path,
                    }
                )

        identity = get_agent_identity(path)
        if identity:
            results.append(
                {
                    "agent_id": identity["agent_id"],
                    "name": identity["name"],
                    "path": path,
                }
            )

    logger.debug("Discovered %d agents from workspaces", len(results))
    return results


def _resolve_search_paths(workspace_dir: str) -> list[str]:
    """Resolve workspace search paths in priority order."""
    explicit = Path(workspace_dir)
    if workspace_dir != ".openclaw/workspace":
        return [str(explicit)] if explicit.exists() else []

    candidates = [
        explicit,
        Path.home() / ".openclaw" / "workspace",
        Path.home() / "traderbot" / ".openclaw" / "workspace",
    ]
    return [str(p) for p in candidates if p.exists() and p.is_dir()]


def get_agent_identity(agent_path: str) -> dict[str, str] | None:
    """Read IDENTITY.md from agent directory and extract agent_id and name."""
    identity_file = Path(agent_path) / "IDENTITY.md"

    if not identity_file.exists():
        return None

    try:
        content = identity_file.read_text()
    except Exception:
        logger.warning("Failed to read identity file %s", identity_file)
        return None

    agent_id_match = re.search(
        r"-\s*\*\*\s*agent\s+id\s*\*\*\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE
    )
    name_match = re.search(r"-\s*\*\*\s*name\s*\*\*\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)

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
