"""Bounded subprocess wrappers for the first-party OpenClaw CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from traderbot.deploy.openclaw_models import (
    AgentCreated,
    AgentInventory,
    ConfigDryRun,
    CronJob,
    CronJobResult,
    DoctorResult,
    GatewayResult,
    JsonObject,
    SetupResult,
)
from traderbot.deploy.openclaw_process import run_bounded

_AGENT_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_CONFIG_KEY_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*$")
_RESERVED_AGENT_IDS: Final = frozenset({"main", "openclaw", "crestodian"})
_SANDBOX_MODES: Final = frozenset({"off", "non-main", "all"})
_NAMED_SESSIONS: Final = frozenset({"main", "isolated", "current"})
_FAILURE_STATUSES: Final = frozenset({"error", "failed", "failure"})

_run = run_bounded


def _parse_result[ResultT: BaseModel](
    argv: list[str],
    timeout: float,
    model: type[ResultT],
) -> ResultT | None:
    result = _run(argv, timeout=timeout)
    if result is None or result.returncode != 0:
        return None
    try:
        return model.model_validate_json(result.stdout)
    except ValidationError:
        return None


def _workspace_key(workspace: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(workspace)))


def _normalize_session(session: str) -> str | None:
    raw = session.strip()
    lowered = raw.lower()
    if lowered in _NAMED_SESSIONS:
        return lowered
    if not lowered.startswith("session:"):
        return None
    session_id = raw[8:].strip()
    return f"session:{session_id}" if session_id else None


def _cron_add_succeeded(argv: list[str]) -> bool:
    parsed = _parse_result(argv, 60.0, JsonObject)
    if parsed is None:
        return False
    payload = parsed.root
    status = payload.get("status")
    if "ok" in payload and payload["ok"] is not True:
        return False
    if payload.get("error") is not None:
        return False
    if status is not None and not isinstance(status, str):
        return False
    if isinstance(status, str) and status.lower() in _FAILURE_STATUSES:
        return False
    job = payload.get("job")
    candidate = job if isinstance(job, dict) else payload
    try:
        _ = CronJobResult.model_validate(candidate)
    except ValidationError:
        return False
    return True


def _normalize_agent_id(agent_id: str) -> str | None:
    if not agent_id.strip():
        return None
    normalized = re.sub(r"[^a-z0-9_-]+", "-", agent_id.strip().lower()).strip("-")[:64]
    if not _AGENT_ID_PATTERN.fullmatch(normalized):
        return None
    return normalized


def detect_openclaw() -> str | None:
    """Return the resolved OpenClaw executable path, if installed."""
    return shutil.which("openclaw")


def install_openclaw() -> bool:
    """Install the current first-party OpenClaw npm package when npm exists."""
    npm = shutil.which("npm")
    if npm is None:
        return False
    result = _run(
        [npm, "install", "-g", "openclaw@latest", "--allow-scripts", "openclaw"],
        timeout=300.0,
    )
    return result is not None and result.returncode == 0


def openclaw_setup() -> bool:
    """Create or observe the noninteractive OpenClaw baseline configuration."""
    return _parse_result(
        ["openclaw", "setup", "--baseline", "--json"],
        120.0,
        SetupResult,
    ) is not None


def create_agent(agent_id: str, sandbox_mode: str = "all") -> bool:
    """Create one normalized agent and apply its sandbox mode separately."""
    normalized = _normalize_agent_id(agent_id)
    if (
        normalized is None
        or normalized in _RESERVED_AGENT_IDS
        or sandbox_mode not in _SANDBOX_MODES
    ):
        return False
    workspace = Path.home() / ".openclaw" / f"workspace-{normalized}"
    inventory = _parse_result(
        ["openclaw", "agents", "list", "--json"],
        30.0,
        AgentInventory,
    )
    if inventory is None:
        return False
    matches = [agent for agent in inventory.root if agent.id == normalized]
    if len(matches) > 1:
        return False
    if matches:
        if _workspace_key(matches[0].workspace) != _workspace_key(str(workspace)):
            return False
    else:
        created = _parse_result(
            [
                "openclaw", "agents", "add", normalized, "--workspace", str(workspace),
                "--non-interactive", "--json",
            ],
            120.0,
            AgentCreated,
        )
        if (
            created is None
            or created.agentId != normalized
            or _workspace_key(created.workspace) != _workspace_key(str(workspace))
        ):
            return False
    return set_config(f"agents.entries.{normalized}.sandbox.mode", sandbox_mode)


def register_cron(
    agent: str,
    prompt: str,
    at: str | None = None,
    every: str | None = None,
    session: str = "isolated",
    delete_after_run: bool = False,
) -> bool:
    """Register one current-style cron with exactly one schedule selector."""
    normalized = _normalize_agent_id(agent)
    session_target = _normalize_session(session)
    schedules = [("at", at), ("every", every)]
    selected = [(kind, value) for kind, value in schedules if value is not None]
    if (
        normalized is None
        or len(selected) != 1
        or session_target is None
        or not prompt.strip()
    ):
        return False
    kind, schedule = selected[0]
    if not schedule.strip():
        return False
    schedule_slug = re.sub(r"[^a-z0-9_-]+", "-", schedule.lower()).strip("-")[:24]
    if not schedule_slug:
        schedule_slug = sha256(schedule.encode()).hexdigest()[:12]
    name = f"traderbot-{normalized[:24]}-{kind}-{schedule_slug}"
    argv = [
        "openclaw",
        "cron",
        "add",
        "--name",
        name,
        "--agent",
        normalized,
        "--session",
        session_target,
        f"--{kind}",
        schedule,
        "--system-event" if session_target == "main" else "--message",
        prompt,
    ]
    if delete_after_run:
        argv.append("--delete-after-run")
    argv.append("--json")
    return _cron_add_succeeded(argv)


def _read_crons(*, strict_members: bool) -> list[CronJob] | None:
    result = _run(["openclaw", "cron", "list", "--json"], timeout=30.0)
    if result is None or result.returncode != 0:
        return None
    try:
        payload = JsonObject.model_validate_json(result.stdout).root
    except ValidationError:
        return None
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return None
    if strict_members and any(not isinstance(job, dict) for job in jobs):
        return None
    return [job for job in jobs if isinstance(job, dict)]


def inspect_crons() -> list[CronJob] | None:
    """Return a checked cron inventory, or None when it cannot be read."""
    return _read_crons(strict_members=True)


def list_crons() -> list[CronJob]:
    """Return cron jobs while preserving the original empty-on-failure API."""
    return _read_crons(strict_members=False) or []


def openclaw_doctor() -> bool:
    """Run the read-only OpenClaw configuration lint."""
    return _parse_result(
        ["openclaw", "doctor", "--lint", "--json"],
        30.0,
        DoctorResult,
    ) is not None


def gateway_status() -> bool:
    """Require a successful gateway RPC status response."""
    return _parse_result(
        ["openclaw", "gateway", "status", "--json", "--require-rpc"],
        30.0,
        GatewayResult,
    ) is not None


def set_config(key: str, value: str) -> bool:
    """Set one dotted OpenClaw config key using strict JSON string syntax."""
    if not _CONFIG_KEY_PATTERN.fullmatch(key):
        return False
    encoded = json.dumps(value)
    validated = _parse_result(
        [
            "openclaw", "config", "set", key, encoded, "--strict-json", "--dry-run",
            "--json",
        ],
        60.0,
        ConfigDryRun,
    )
    if validated is None:
        return False
    result = _run(
        ["openclaw", "config", "set", key, encoded, "--strict-json"],
        timeout=60.0,
    )
    return result is not None and result.returncode == 0
