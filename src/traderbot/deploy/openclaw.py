"""Bounded subprocess wrappers for the first-party OpenClaw CLI."""

from __future__ import annotations

import os
import re
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from traderbot.deploy.openclaw_config import inspect_config, set_config, set_secret_ref
from traderbot.deploy.openclaw_models import (
    AgentCreated,
    AgentInventory,
    CronJob,
    CronJobResult,
    DoctorResult,
    GatewayResult,
    JsonObject,
    SetupResult,
)
from traderbot.deploy.openclaw_process import run_bounded

__all__ = (
    "inspect_config",
    "set_config",
    "set_secret_ref",
)

_AGENT_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESERVED_AGENT_IDS: Final = frozenset({"main", "openclaw", "crestodian"})
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


def inspect_agents() -> AgentInventory | None:
    """Return the complete checked configured-agent inventory."""
    return _parse_result(
        ["openclaw", "agents", "list", "--json"],
        30.0,
        AgentInventory,
    )


def create_agent(agent_id: str, workspace: Path) -> bool:
    """Request one explicit-path agent creation without inferring ownership state."""
    normalized = _normalize_agent_id(agent_id)
    if normalized is None or normalized in _RESERVED_AGENT_IDS or not workspace.is_absolute():
        return False
    created = _parse_result(
        [
            "openclaw", "agents", "add", normalized, "--workspace", str(workspace),
            "--non-interactive", "--json",
        ],
        120.0,
        AgentCreated,
    )
    return (
        created is not None
        and created.agentId == normalized
        and _workspace_key(created.workspace) == _workspace_key(str(workspace))
    )


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
