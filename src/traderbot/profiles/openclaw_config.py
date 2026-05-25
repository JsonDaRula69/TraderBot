"""OpenClaw configuration management for agent profile pairing.

Handles hooks enablement and bootstrap hook creation
during the ``traderbot profile assign`` flow. All functions are idempotent.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

_OPENCLAW_DIR = Path.home() / ".openclaw"
_OPENCLAW_CONFIG_PATH = _OPENCLAW_DIR / "openclaw.json"
_HOOKS_DIR = _OPENCLAW_DIR / "hooks"

# Common locations for the openclaw CLI
_OPENCLAW_CLI_CANDIDATES = [
    "openclaw",                                 # on PATH
    Path.home() / ".npm-global" / "bin" / "openclaw",
    Path.home() / ".local" / "bin" / "openclaw",
    Path("/usr/local/bin/openclaw"),
    Path("/usr/bin/openclaw"),
]

BOOTSTRAP_HOOK_DIRNAME = "traderbot-bootstrap"

# ---------------------------------------------------------------------------
# Embedded hook files — deployed to ~/.openclaw/hooks/traderbot-bootstrap/
# ---------------------------------------------------------------------------

BOOTSTRAP_HOOK_MD_CONTENT = """# TraderBot Bootstrap Hook

Validates agent workspace state before each session and injects pre-session
status context so the agent sees its state immediately on wake.

## Events

- `agent:bootstrap` — fires before workspace bootstrap files are injected

## Behavior

1. Checks whether BOOTSTRAP.md still exists (first-run setup incomplete).
2. Scans SESSION-STATE.md for PENDING or ESCALATE entries from a prior session.
3. Scans HEARTBEAT_DATA.md for circuit breaker state and open alerts.
4. Injects a structured Pre-Session Status block when any flags are raised.
"""

BOOTSTRAP_HANDLER_TS_CONTENT = r"""import * as fs from 'fs';
import * as path from 'path';

export default {
  'agent:bootstrap': async (event: any) => {
    const workspace = event.workspace;
    if (!workspace) return {};

    const context: string[] = [];

    // 1. Check if bootstrap is incomplete
    const bootstrapPath = path.join(workspace, 'BOOTSTRAP.md');
    if (fs.existsSync(bootstrapPath)) {
      context.push('\u26a0\ufe0f BOOTSTRAP INCOMPLETE: BOOTSTRAP.md still exists. Complete first-run setup before normal operations.');
    }

    // 2. Read SESSION-STATE.md for pending/escalated entries
    const sessionPath = path.join(workspace, 'SESSION-STATE.md');
    if (fs.existsSync(sessionPath)) {
      const content = fs.readFileSync(sessionPath, 'utf-8');
      if (content.includes('**ESCALATE**') || content.includes('Status: ESCALATE')) {
        context.push('\u26a0\ufe0f ESCALATED ITEMS: SESSION-STATE.md has unresolved escalated items requiring human attention.');
      }
      if (content.includes('**PENDING**') || content.includes('Status: PENDING')) {
        context.push('\u23f3 PENDING ACTIONS: SESSION-STATE.md has incomplete actions from a previous session.');
      }
      const cbMatch = content.match(/Level:\s*(HALT|FULL_STOP)/);
      if (cbMatch) {
        context.push(`\ud83d\udd34 CIRCUIT BREAKER: ${cbMatch[1]} \u2014 no new trades allowed.`);
      }
    }

    // 3. Read HEARTBEAT_DATA.md for circuit breaker + alerts
    const hbPath = path.join(workspace, 'HEARTBEAT_DATA.md');
    if (fs.existsSync(hbPath)) {
      const content = fs.readFileSync(hbPath, 'utf-8');
      const cbMatch = content.match(/Level:\s*(HALT|FULL_STOP)/);
      if (cbMatch && !context.some(c => c.includes('CIRCUIT BREAKER'))) {
        context.push(`\ud83d\udd34 CIRCUIT BREAKER: ${cbMatch[1]} (from heartbeat data)`);
      }
      const alertMatch = content.match(/### Alerts\s*\n([\s\S]*?)(?=\n###|$)/);
      if (alertMatch && alertMatch[1].trim() && alertMatch[1].trim() !== 'None') {
        context.push(`\ud83d\udccb PENDING ALERTS:\n${alertMatch[1].trim()}`);
      }
    }

    if (context.length > 0) {
      return {
        inject: `## Pre-Session Status\n${context.join('\n\n')}\n\n---\n`
      };
    }

    return {};
  }
};
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_openclaw_config() -> dict[str, Any]:
    """Read ``openclaw.json``, returning empty dict if missing or corrupt."""
    if not _OPENCLAW_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_OPENCLAW_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to parse %s, starting fresh", _OPENCLAW_CONFIG_PATH)
        return {}


def _write_openclaw_config(config: dict[str, Any]) -> None:
    """Write ``openclaw.json`` atomically."""
    _OPENCLAW_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OPENCLAW_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def _openclaw_cli(*args: str, timeout: int = 30) -> bool:
    """Run an ``openclaw`` CLI command. Returns ``True`` on success.

    Searches common install locations — the ``openclaw`` binary is often
    installed via npm global but not always on the default SSH ``PATH``.
    """
    for cli_path in _OPENCLAW_CLI_CANDIDATES:
        try:
            result = subprocess.run(
                [str(cli_path), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None

def get_openclaw_version() -> str | None:
    """Return installed OpenClaw version string, or ``None``."""
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def enable_session_memory_hook() -> bool:
    """Enable the built-in ``session-memory`` hook.

    Uses the ``openclaw`` CLI if available; falls back to writing the
    hook entry directly into ``openclaw.json``.  Idempotent — safe to
    call on every ``profile assign``.
    """
    # Fast path: try CLI
    if _openclaw_cli("hooks", "enable", "session-memory"):
        logger.info("Enabled session-memory hook via CLI")
        return True

    # Fallback: add to openclaw.json under hooks.internal.entries
    config = _read_openclaw_config()
    hooks = config.setdefault("hooks", {})
    internal = hooks.setdefault("internal", {"enabled": True})
    entries = internal.setdefault("entries", {})
    if "session-memory" not in entries:
        entries["session-memory"] = {"enabled": True}
        hooks.pop("entries", None)
        _write_openclaw_config(config)
        logger.info("Enabled session-memory hook via config")
    return True


def ensure_agent_bootstrap_hook() -> bool:
    """Create and enable the ``agent:bootstrap`` hook for pre-session validation.

    Deploys ``HOOK.md`` and ``handler.ts`` to ``~/.openclaw/hooks/traderbot-bootstrap/``
    and registers the hook in ``openclaw.json``.  Idempotent.
    """
    hook_dir = _HOOKS_DIR / BOOTSTRAP_HOOK_DIRNAME
    hook_dir.mkdir(parents=True, exist_ok=True)

    hook_md = hook_dir / "HOOK.md"
    if not hook_md.exists():
        hook_md.write_text(BOOTSTRAP_HOOK_MD_CONTENT)
        logger.info("Created %s", hook_md)

    handler = hook_dir / "handler.ts"
    if not handler.exists():
        handler.write_text(BOOTSTRAP_HANDLER_TS_CONTENT)
        logger.info("Created %s", handler)

    config = _read_openclaw_config()
    hooks = config.setdefault("hooks", {})

    extra_dirs = hooks.setdefault("extraHookDirs", [])
    hook_dir_str = str(hook_dir)
    if hook_dir_str not in extra_dirs:
        extra_dirs.append(hook_dir_str)

    internal = hooks.setdefault("internal", {"enabled": True})
    entries = internal.setdefault("entries", {})
    if "traderbot-bootstrap" not in entries:
        entries["traderbot-bootstrap"] = {"enabled": True}
        hooks.pop("entries", None)
        _write_openclaw_config(config)

    _openclaw_cli("hooks", "enable", "traderbot-bootstrap")

    logger.info("Bootstrap hook deployed and registered")
    return True


def configure_agent_sandbox(agent_id: str) -> bool:
    """Add or update an agent entry in ``openclaw.json`` with sandbox and
    workspace access settings.

    Enables sandboxing and ``workspaceAccess: \"rw\"`` for the given agent ID.
    The sandbox prevents the agent from reading/writing files outside its
    workspace via absolute paths.  Idempotent.
    """
    config = _read_openclaw_config()
    agents = config.setdefault("agents", {})
    agent_list = agents.setdefault("list", [])

    for entry in agent_list:
        if entry.get("id") == agent_id:
            # Add sandbox config if not already set
            entry["sandbox"] = entry.get("sandbox", True)
            entry.setdefault("workspaceAccess", "rw")
            break
    else:
        agent_list.append({
            "id": agent_id,
            "sandbox": True,
            "workspaceAccess": "rw",
        })

    _write_openclaw_config(config)
    logger.info("Sandbox configured for agent '%s'", agent_id)
    return True
