#!/usr/bin/env python3
"""Standalone TraderBot update script — zero traderbot package imports.

Usage:
  python3 install/traderbot-update.py          # update from main branch
  python3 install/traderbot-update.py --dev     # update from dev branch

This script self-updates first: it downloads the latest version of itself
from GitHub before proceeding with the full update pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("traderbot-update")

REPO = "JsonDaRula69/TraderBot"
GITHUB_RAW = f"https://raw.githubusercontent.com/{REPO}/main"
REPO_DIR = Path.home() / "traderbot"
VENV_BIN = REPO_DIR / ".venv" / "bin"
PYTHON = VENV_BIN / "python3"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("timeout", 120)
    logger.info("  $ %s", " ".join(cmd))
    return subprocess.run(cmd, **kwargs)


def _self_update() -> bool:
    """Download latest version of this script from GitHub, then re-exec."""
    dest = REPO_DIR / "install" / "traderbot-update.py"
    try:
        import urllib.request
        url = f"{GITHUB_RAW}/install/traderbot-update.py"
        with urllib.request.urlopen(url, timeout=15) as resp:
            new_code = resp.read().decode()
            old_code = dest.read_text() if dest.exists() else ""
        if new_code != old_code:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(new_code)
            logger.info("Self-updated. Re-executing with latest version...")
            os.execv(sys.executable, [sys.executable, str(dest), *sys.argv[1:]])
            return True  # unreachable
        return False
    except Exception:
        logger.warning("Self-update failed — continuing with local version")
        return False


def _git_pull(branch: str) -> None:
    _run(["git", "stash", "--include-untracked"], cwd=REPO_DIR, capture_output=True)
    _run(["git", "pull", "origin", branch], cwd=REPO_DIR)


def _pip_install() -> None:
    _run([str(PYTHON), "-m", "pip", "install", "-e", "."], cwd=REPO_DIR)


def _refresh_workspace_files() -> None:
    ws_root = Path.home() / ".openclaw" / "workspace"
    template_root = REPO_DIR / ".openclaw" / "workspace"
    if not ws_root.is_dir():
        return
    template_files = ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md", "HEARTBEAT.md"]
    for agent_dir in ws_root.iterdir():
        if not agent_dir.is_dir():
            continue
        ag_name = agent_dir.name
        if ag_name == "main" or (agent_dir / "AGENTS.md").is_file() and "sysadmin" in (agent_dir / "AGENTS.md").read_text():
            tdir = template_root
        elif (template_root / ag_name).is_dir():
            tdir = template_root / ag_name
        else:
            tdir = template_root / "agent"
        if tdir.is_dir():
            for fname in template_files:
                src = tdir / fname
                if src.is_file():
                    shutil.copy2(str(src), str(agent_dir / fname))
                    logger.info("  Refresh: %s", agent_dir / fname)


def _rebuild_sandbox_image() -> None:
    build_script = REPO_DIR / "install" / "docker" / "build-sandbox.sh"
    if shutil.which("docker") and build_script.is_file():
        _run(["bash", str(build_script)], cwd=REPO_DIR)


def _configure_openclaw_sandbox() -> None:
    if not shutil.which("openclaw"):
        return
    home = os.environ["HOME"]
    config = [
        ("agents.defaults.sandbox.mode", "non-main"),
        ("agents.defaults.sandbox.backend", "docker"),
        ("agents.defaults.sandbox.scope", "agent"),
        ("agents.defaults.sandbox.workspaceAccess", "rw"),
        ("agents.defaults.sandbox.docker.image", "traderbot-sandbox:bookworm-slim"),
        ("agents.defaults.sandbox.docker.network", "bridge"),
        ("agents.defaults.sandbox.docker.readOnlyRoot", "true"),
        ("agents.defaults.sandbox.docker.capDrop", '["ALL"]'),
        ("agents.defaults.sandbox.docker.memory", "1g"),
        ("agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources", "true"),
        ("agents.defaults.sandbox.docker.binds", '["{0}/traderbot:/traderbot:ro","{0}/.traderbot:/home/traderbot/.traderbot:rw"]'.format(home)),
        ("agents.list[0].sandbox.mode", "off"),
        ("agents.list[0].tools.profile", "coding"),
        ("agents.list[1].tools.profile", "coding"),
    ]
    for key, val in config:
        _run(["openclaw", "config", "set", key, val], capture_output=True)


def _enable_bootstrap_hook() -> None:
    if not shutil.which("openclaw"):
        return
    hook_dir = Path.home() / ".openclaw" / "hooks" / "traderbot-bootstrap"
    hook_dir.mkdir(parents=True, exist_ok=True)
    # Write HOOK.md
    hook_md = """---
name: traderbot-bootstrap
description: "Injects pre-session status from SESSION-STATE.md and HEARTBEAT_DATA.md into every session"
metadata:
  { "openclaw": { "emoji": "🏗", "events": ["agent:bootstrap"], "requires": {} } }
---
"""
    (hook_dir / "HOOK.md").write_text(hook_md.strip())
    # Write handler.ts
    handler_ts = """const handler = async (event) => {
  if (event.type !== "agent:bootstrap") return;
  const ws = event.context?.workspace;
  if (!ws) return;
  try {
    const ss = ws.files?.find((f) => f.path?.endsWith("SESSION-STATE.md"));
    const hb = ws.files?.find((f) => f.path?.endsWith("HEARTBEAT_DATA.md"));
    let status = "";
    if (ss?.text?.includes("PENDING")) status += "Has pending actions. ";
    if (ss?.text?.includes("ESCALATE")) status += "Has escalation. ";
    if (hb?.text?.includes("HALT") || hb?.text?.includes("STOP")) status += "Circuit breaker active. ";
    if (status) event.messages?.push("Pre-Session Status: " + status);
  } catch {}
};
export default handler;
"""
    (hook_dir / "handler.ts").write_text(handler_ts)
    _run(["openclaw", "hooks", "enable", "traderbot-bootstrap"], capture_output=True)


def _reregister_cron_jobs() -> None:
    if not (PYTHON.is_file()):
        return
    # Main agent (sysadmin) — learning-pipeline, error-logger, health-check, gateway-health
    _run([str(PYTHON), "-m", "traderbot", "cron", "setup",
          "--agent", "main", "--role", "sysadmin", "--replace"], capture_output=True)
    # Category agents (traders) — decision-loop, position-review, forecast-check, circuit-breaker, health-check
    agents_root = Path.home() / ".openclaw" / "agents"
    if agents_root.is_dir():
        for agent_dir in agents_root.iterdir():
            if agent_dir.name == "main" or not (agent_dir / "agent").is_dir():
                continue
            _run([str(PYTHON), "-m", "traderbot", "cron", "setup",
                  "--agent", agent_dir.name, "--role", "trader", "--replace"], capture_output=True)


def _kill_ws_daemon() -> None:
    """Kill any running ws_daemon processes before restart."""
    try:
        subprocess.run(
            ["pkill", "-f", "ws_daemon.py"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def _restart_ws_daemon() -> None:
    _kill_ws_daemon()
    daemon = REPO_DIR / "src" / "traderbot" / "kalshi" / "ws_daemon.py"
    if daemon.is_file():
        # Non-blocking Popen — daemon manages its own lifecycle
        subprocess.Popen([str(PYTHON), str(daemon)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)


def _restart_gateway() -> None:
    if shutil.which("openclaw"):
        subprocess.Popen(["openclaw", "gateway", "restart"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)


def _backup_databases() -> None:
    data_dir = Path.home() / ".traderbot"
    backup_dir = data_dir / ".update_backup"
    for f in data_dir.rglob("*.db"):
        if ".update_backup" in str(f) or ".manual_update_backup" in str(f):
            continue
        rel = f.relative_to(data_dir)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        logger.info("  Backed up: %s", f)
    cutoff = time.time() - 2592000
    for f in backup_dir.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()


def main() -> None:
    branch = "dev" if "--dev" in sys.argv else "main"

    print("=== TraderBot Update ===")
    print(f"  Branch: {branch}")
    print()

    _self_update()

    print("  → Backing up databases...")
    _backup_databases()

    # Detect install mode: pip vs git
    try:
        import traderbot
        traderbot_dir = Path(traderbot.__file__).resolve().parent.parent.parent
        is_git = (traderbot_dir / ".git").is_dir()
    except Exception:
        is_git = REPO_DIR.is_dir() and (REPO_DIR / ".git").is_dir()

    if is_git:
        print("  → Pulling latest code...")
        _git_pull(branch)
        print("  → Reinstalling package...")
        _pip_install()
    else:
        print("  → Upgrading via pip...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "traderbot"],
            check=False,
        )

    print("  → Refreshing workspace files...")
    _refresh_workspace_files()

    print("  → Rebuilding sandbox image...")
    _rebuild_sandbox_image()

    print("  → Re-applying OpenClaw config...")
    _configure_openclaw_sandbox()

    print("  → Deploying bootstrap hook...")
    _enable_bootstrap_hook()

    print("  → Re-registering cron jobs...")
    _reregister_cron_jobs()

    print("  → Restarting WS daemon...")
    _restart_ws_daemon()

    print("  → Restarting OpenClaw gateway...")
    _restart_gateway()

    print()
    print("=== Update complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())