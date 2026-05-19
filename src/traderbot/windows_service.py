"""Windows Service management for TraderBot.

Provides sc.exe and schtasks.exe wrappers equivalent to the systemd/launchd
service management on Linux/macOS.

Agent daemon   -> Windows Service (sc.exe)
News ingest    -> Task Scheduler (schtasks.exe)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

_SC = shutil.which("sc.exe") or shutil.which("sc")
_SCHTASKS = shutil.which("schtasks.exe") or shutil.which("schtasks")


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# sc.exe — Windows Service management (agent daemon)
# ---------------------------------------------------------------------------


def sc_available() -> bool:
    """Check if sc.exe is available on this system."""
    if not is_windows():
        return False
    return _SC is not None


def schtasks_available() -> bool:
    """Check if schtasks.exe is available on this system."""
    if not is_windows():
        return False
    return _SCHTASKS is not None


@dataclass
class WindowsServiceDef:
    """Definition for a Windows Service."""

    name: str
    display_name: str
    bin_path: str
    description: str = ""


def _sc(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an sc.exe command."""
    if not _SC:
        raise FileNotFoundError("sc.exe not found on PATH")
    return subprocess.run([str(_SC), *args], capture_output=True, text=True)


def _schtasks(args: list[str]) -> subprocess.CompletedProcess[str]:
    if not _SCHTASKS:
        raise FileNotFoundError("schtasks.exe not found on PATH")
    return subprocess.run([str(_SCHTASKS), *args], capture_output=True, text=True)


def service_exists(name: str) -> bool:
    """Check if a Windows Service exists by name."""
    result = _sc(["query", name])
    return result.returncode == 0


def create_service(svc: WindowsServiceDef) -> bool:
    """Create and configure a Windows Service via sc.exe.

    Sets auto-start, restart-on-failure, and description.
    """
    result = _sc([
        "create", svc.name,
        "binPath=", svc.bin_path,
        "start=", "auto",
        "DisplayName=", svc.display_name,
    ])
    if result.returncode != 0:
        return False

    if svc.description:
        _sc(["description", svc.name, svc.description])

    _sc([
        "failure", svc.name,
        "reset=", "86400",
        "actions=", "restart/10000/restart/30000/restart/60000",
    ])
    return True


def start_service(name: str) -> bool:
    """Start a Windows Service."""
    result = _sc(["start", name])
    return result.returncode == 0


def stop_service(name: str) -> bool:
    """Stop a Windows Service."""
    result = _sc(["stop", name])
    return result.returncode == 0


def delete_service(name: str) -> bool:
    """Delete a Windows Service."""
    result = _sc(["delete", name])
    return result.returncode == 0


def install_agent_service(
    agent_name: str,
    profile_token: str,
    venv_python: str | None = None,
    working_dir: str | None = None,
) -> bool:
    """Install agent as a Windows Service (equivalent to systemd/launchd agent daemon).

    Creates a service named TraderBotAgent-<agent_name> that runs
    ``traderbot scan --continuous`` at boot, restarts on failure.

    Args:
        agent_name: Agent identifier (e.g. "molty", "alice").
        profile_token: Profile token for TRADERBOT_PROFILE_TOKEN env var.
        venv_python: Path to python.exe in the venv. Defaults to sys.executable.
        working_dir: Working directory. Defaults to current directory.
    """
    if venv_python is None:
        venv_python = sys.executable

    name = f"TraderBotAgent-{agent_name}"

    if service_exists(name):
        stop_service(name)
        delete_service(name)

    svc = WindowsServiceDef(
        name=name,
        display_name=f"TraderBot Agent ({agent_name})",
        bin_path=f'"{venv_python}" -m traderbot scan --continuous',
        description="TraderBot autonomous prediction market agent daemon",
    )

    if not create_service(svc):
        return False

    if profile_token:
        _sc(["config", name, f"env=TRADERBOT_PROFILE_TOKEN={profile_token}"])

    if working_dir:
        _sc(["config", name, "obj=LocalSystem", "binPath=", svc.bin_path])

    return start_service(name)


def uninstall_agent_service(agent_name: str) -> bool:
    """Remove agent Windows Service and return True if it was cleaned up."""
    name = f"TraderBotAgent-{agent_name}"
    if not service_exists(name):
        return True
    stop_service(name)
    return delete_service(name)


# ---------------------------------------------------------------------------
# schtasks.exe — Task Scheduler (news ingest, heartbeat)
# ---------------------------------------------------------------------------


@dataclass
class ScheduledTaskDef:
    """Definition for a Windows Scheduled Task."""

    task_name: str
    command: str
    interval_minutes: int


def task_exists(task_name: str) -> bool:
    """Check if a scheduled task exists by name."""
    result = _schtasks(["/query", "/tn", task_name])
    return result.returncode == 0


def create_scheduled_task(task: ScheduledTaskDef) -> bool:
    """Create a scheduled task via schtasks.exe that runs every N minutes.

    Equivalent to systemd timer with OnCalendar=*:0/N.
    """
    result = _schtasks([
        "/create",
        "/tn", task.task_name,
        "/tr", task.command,
        "/sc", "minute",
        "/mo", str(task.interval_minutes),
        "/f",
    ])
    return result.returncode == 0


def delete_scheduled_task(task_name: str) -> bool:
    """Delete a scheduled task."""
    result = _schtasks(["/delete", "/tn", task_name, "/f"])
    return result.returncode == 0


def install_news_ingest_task(
    user: str,
    interval_minutes: int = 30,
    venv_python: str | None = None,
) -> bool:
    """Install news ingest as a scheduled task via schtasks.exe.

    Equivalent to systemd traderbot-news-ingest@.timer/.service.

    Args:
        user: Agent user name (used in task name for uniqueness).
        interval_minutes: How often to run news ingestion (default every 30 min).
        venv_python: Path to python.exe in the venv.
    """
    if venv_python is None:
        venv_python = sys.executable

    task = ScheduledTaskDef(
        task_name=f"TraderBot News Ingest - {user}",
        command=f'"{venv_python}" -m traderbot news-ingest --json',
        interval_minutes=interval_minutes,
    )
    return create_scheduled_task(task)


def uninstall_news_ingest_task(user: str) -> bool:
    """Remove the news ingest scheduled task."""
    task_name = f"TraderBot News Ingest - {user}"
    if not task_exists(task_name):
        return True
    return delete_scheduled_task(task_name)


# ---------------------------------------------------------------------------
# Uninstall helpers
# ---------------------------------------------------------------------------


def list_agent_services() -> list[str]:
    """List all TraderBot agent Windows Services."""
    result = _sc(["query", "state=", "all"])
    services: list[str] = []
    for line in result.stdout.splitlines():
        if "TraderBotAgent-" in line:
            name = line.split("SERVICE_NAME:")[-1].strip()
            if name.startswith("TraderBotAgent-"):
                services.append(name)
    return services


def list_news_tasks() -> list[str]:
    """List all TraderBot news ingest scheduled tasks."""
    result = _schtasks(["/query", "/fo", "LIST"])
    tasks: list[str] = []
    for line in result.stdout.splitlines():
        if "TraderBot News Ingest" in line:
            name = line.split(":", 1)[-1].strip().lstrip("\\")
            tasks.append(name)
    return tasks
