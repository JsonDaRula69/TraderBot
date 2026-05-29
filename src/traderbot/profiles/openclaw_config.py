"""OpenClaw configuration management for agent profile pairing.

Handles hooks enablement and bootstrap hook creation
during the ``traderbot profile assign`` flow. All functions are idempotent.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_OPENCLAW_DIR = Path.home() / ".openclaw"
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

1. Scans SESSION-STATE.md for PENDING or ESCALATE entries from a prior session.
2. Scans HEARTBEAT_DATA.md for circuit breaker state and open alerts.
3. Injects a structured Pre-Session Status block when any flags are raised.
"""

BOOTSTRAP_HANDLER_TS_CONTENT = r"""import * as fs from 'fs';
import * as path from 'path';

export default {
  'agent:bootstrap': async (event: any) => {
    const workspace = event.workspace;
    if (!workspace) return {};

    const context: string[] = [];

    // 1. Read SESSION-STATE.md for pending/escalated entries
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

    // 2. Read HEARTBEAT_DATA.md for circuit breaker + alerts
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


def _openclaw_cli(*args: str, timeout: int = 30) -> bool:
    """Run an ``openclaw`` CLI command. Returns ``True`` on success.

    Searches common install locations and ensures the npm global bin
    directory is on PATH (required when spawned from a Python
    subprocess that has not sourced the user's shell init files).
    """
    env = os.environ.copy()
    env["PATH"] = ":".join([
        str(Path.home() / ".npm-global" / "bin"),
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
        env.get("PATH", ""),
    ])

    for cli_path in _OPENCLAW_CLI_CANDIDATES:
        resolved = shutil.which(str(cli_path), path=env["PATH"])
        if isinstance(cli_path, str):
            if not resolved:
                continue
            cmd = resolved
        elif not cli_path.exists() and not resolved:
            continue
        else:
            cmd = resolved if resolved else str(cli_path)
        try:
            result = subprocess.run(
                [cmd, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return False

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
    """Enable the built-in ``session-memory`` hook via CLI only.

    We no longer manipulate ``openclaw.json`` directly because the schema
    changes between OpenClaw versions.  Rely on ``openclaw hooks enable``
    to keep the config valid.  Best-effort — returns True regardless.
    """
    if _openclaw_cli("hooks", "enable", "session-memory"):
        logger.info("Enabled session-memory hook via CLI")
    else:
        logger.warning(
            "Could not enable session-memory hook via CLI; "
            "run 'openclaw hooks enable session-memory' manually if needed"
        )
    return True


def ensure_agent_bootstrap_hook() -> bool:
    """Deploy bootstrap hook files to the filesystem.

    Hook registration is left to the OpenClaw CLI (``openclaw hooks enable``).
    We no longer write to ``openclaw.json`` directly to avoid schema drift.
    Idempotent.
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

    logger.info("Bootstrap hook files deployed to %s", hook_dir)
    return True


