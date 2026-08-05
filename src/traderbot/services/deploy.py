"""Service deployment and removal across platforms (DD-022).

Detects the active service manager (systemd / launchd / Windows Task
Scheduler), reads a ``{placeholder}`` template via ``importlib.resources``,
substitutes resolved paths, and writes the unit file to the
platform-appropriate location. No shell scripts — substitution uses Python
``str.format`` only. Deploys a single ``traderbot.service`` daemon unit, not
per-agent ``@.service`` template units.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from importlib.resources import files
from pathlib import Path

from traderbot.services.paths import BinPaths, resolve_bin_paths

logger = logging.getLogger(__name__)

# Template name per service manager (package data in traderbot.services).
_TEMPLATES: dict[str, str] = {
    "systemd": "traderbot.service.in",
    "launchd": "com.traderbot.daemon.plist.in",
    "windows": "traderbot-daemon.xml.in",
}

# Platform-appropriate destination paths.
_DESTINATIONS: dict[str, str] = {
    "systemd": "/etc/systemd/system/traderbot.service",
    "launchd": "/Library/LaunchDaemons/com.traderbot.daemon.plist",
}


def detect_service_manager() -> str:
    """Return the active service manager for this platform.

    Returns one of ``"systemd"``, ``"launchd"``, ``"windows"``, or ``"none"``.
    """
    system = platform.system()
    if system == "Linux":
        return "systemd"
    if system == "Darwin":
        return "launchd"
    if system == "Windows":
        return "windows"
    return "none"


def _load_template(name: str) -> str:
    """Read a service template from package data via importlib.resources."""
    return files("traderbot.services").joinpath(name).read_text(encoding="utf-8")


def _render(template_name: str, paths: BinPaths, profile_token: str) -> str:
    """Substitute placeholders in a template with resolved values."""
    template = _load_template(template_name)
    return template.format(
        traderbot_bin=paths.traderbot_bin,
        python_bin=paths.python_bin,
        home=paths.home,
        user=paths.user,
        profile_token=profile_token,
    )


def _destination(manager: str, paths: BinPaths) -> Path:
    """Return the destination path for the given service manager."""
    if manager == "windows":
        return paths.home / ".traderbot" / "traderbot-daemon.xml"
    return Path(_DESTINATIONS[manager])


def _sudo_prefix() -> list[str]:
    """Return the command prefix to run a privileged command.

    Returns ``["sudo"]`` when not running as root (so a service unit can be
    written under ``/etc/systemd/system`` or launched via ``systemctl``);
    otherwise an empty list.
    """
    if os.name == "posix" and os.geteuid() != 0:
        return ["sudo"]
    return []


def _write_unit(destination: Path, rendered: str) -> None:
    """Write a rendered service unit, elevating via sudo when required."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        return
    except PermissionError:
        pass

    proc = subprocess.run(
        [*_sudo_prefix(), "tee", str(destination)],
        input=rendered,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to write service unit {destination}: {proc.stderr.strip()}")


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a systemctl command, elevating via sudo when required."""
    return subprocess.run(
        [*_sudo_prefix(), "systemctl", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def enable_and_start_service() -> bool:
    """Enable and start the installed TraderBot daemon service (systemd).

    Returns True when the service reports active after the operation.
    """
    if detect_service_manager() != "systemd":
        return False
    _systemctl("daemon-reload")
    _systemctl("enable", "traderbot.service")
    _systemctl("start", "traderbot.service")
    return _systemctl("is-active", "traderbot.service").returncode == 0


def disable_and_stop_service() -> bool:
    """Stop and disable the installed TraderBot daemon service (systemd).

    Returns True when the service is no longer active.
    """
    if detect_service_manager() != "systemd":
        return False
    _ = _systemctl("stop", "traderbot.service")
    _ = _systemctl("disable", "traderbot.service")
    return _systemctl("is-active", "traderbot.service").returncode != 0


def service_status(paths: BinPaths | None = None) -> str:
    """Return the TraderBot daemon service status.

    Returns ``"active"``, ``"inactive"``, or ``"not installed"`` depending on
    whether the unit file exists and the platform service manager reports the
    service as running.
    """
    paths = paths or resolve_bin_paths()
    manager = detect_service_manager()
    if manager == "none":
        return "not installed"

    destination = _destination(manager, paths)
    if not destination.exists():
        return "not installed"

    if manager == "systemd":
        command = ["systemctl", "is-active", "traderbot.service"]
    elif manager == "launchd":
        command = ["launchctl", "list"]
    else:
        command = ["sc.exe", "query", "traderbot"]

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "inactive"

    if manager == "systemd":
        return "active" if proc.returncode == 0 else "inactive"
    if manager == "launchd":
        for line in proc.stdout.splitlines():
            if "com.traderbot.daemon" in line:
                return "active"
        return "inactive"
    return "active" if proc.returncode == 0 else "inactive"


def deploy_service(profile_token: str = "", paths: BinPaths | None = None) -> Path:
    """Deploy the TraderBot daemon service to this platform.

    Detects the active service manager, renders the matching template with
    resolved paths (plus an optional ``{profile_token}``), and writes the
    unit file to the platform-appropriate location.

    Args:
        profile_token: Optional value for the ``{profile_token}`` placeholder.
        paths: Precomputed ``BinPaths``; resolved on demand when omitted.

    Returns:
        The path that was written.

    Raises:
        RuntimeError: If no supported service manager is detected.
    """
    paths = paths or resolve_bin_paths()
    manager = detect_service_manager()
    if manager == "none":
        raise RuntimeError(
            f"No supported service manager detected for platform {platform.system()!r}"
        )

    rendered = _render(_TEMPLATES[manager], paths, profile_token)
    destination = _destination(manager, paths)
    _write_unit(destination, rendered)
    logger.info("Deployed %s service to %s", manager, destination)
    return destination


def remove_service(paths: BinPaths | None = None) -> bool:
    """Remove the TraderBot daemon service file from this platform.

    Args:
        paths: Precomputed ``BinPaths``; resolved on demand when omitted.

    Returns:
        True if the file existed and was removed, False otherwise.
    """
    paths = paths or resolve_bin_paths()
    manager = detect_service_manager()
    if manager == "none":
        return False

    destination = _destination(manager, paths)
    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to remove service file %s: %s", destination, exc)
        return False

    removed = not destination.exists()
    if removed:
        logger.info("Removed service file %s", destination)
    return removed
