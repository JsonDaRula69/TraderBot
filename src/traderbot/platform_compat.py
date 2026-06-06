from __future__ import annotations

import logging
import platform as _platform
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_platform() -> str:
    plat = _platform.system()
    if plat == "Darwin":
        return "Darwin"
    if plat == "Linux":
        return "Linux"
    if plat == "Windows" or sys.platform == "win32":
        return "Windows"
    return plat


def is_darwin() -> bool:
    return get_platform() == "Darwin"


def is_linux() -> bool:
    return get_platform() == "Linux"


def is_windows() -> bool:
    return get_platform() == "Windows"


def get_service_manager_label() -> str:
    if is_darwin():
        return "launchd"
    if is_linux():
        return "systemd"
    if is_windows():
        return "task_scheduler"
    return "unknown"


def get_traderbot_bin_paths() -> list[Path]:
    if is_windows():
        local_app_data = Path.home() / "AppData" / "Local"
        return [
            local_app_data / "Microsoft" / "WindowsApps" / "traderbot.exe",
            local_app_data / "Programs" / "TraderBot" / "traderbot.exe",
        ]
    return [
        Path("/usr/local/bin/traderbot"),
        Path.home() / ".local" / "bin" / "traderbot",
    ]


def get_pip_cache_dir() -> Path | None:
    if is_windows():
        local_app_data = Path.home() / "AppData" / "Local"
        return local_app_data / "pip" / "Cache"
    if is_darwin() or is_linux():
        return Path.home() / ".cache" / "pip"
    return None


def get_openclaw_bin_paths() -> list[Path]:
    if is_windows():
        local_app_data = Path.home() / "AppData" / "Local"
        return [
            local_app_data / "Microsoft" / "WindowsApps" / "openclaw.exe",
            local_app_data / "Programs" / "OpenClaw" / "openclaw.exe",
        ]
    return [
        Path("/usr/local/bin/openclaw"),
        Path("/usr/bin/openclaw"),
    ]


def get_systemd_available() -> bool:
    import shutil
    import subprocess

    systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
    try:
        subprocess.run([systemctl, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("systemctl not available, skipping systemd check")
        return False


def launchd_remove_services(glob_pattern: str) -> list[str]:
    import shutil
    import subprocess

    removed: list[str] = []
    sudo = shutil.which("sudo") or "/usr/bin/sudo"
    launchctl = shutil.which("launchctl") or "/bin/launchctl"
    daemon_dir = Path("/Library/LaunchDaemons")
    if not daemon_dir.exists():
        logger.debug("launchd daemon dir %s does not exist, nothing to remove", daemon_dir)
        return removed
    for plist in daemon_dir.glob(glob_pattern):
        label = plist.stem
        logger.info("Removing launchd service: %s (%s)", label, plist)
        subprocess.run(
            [sudo, launchctl, "bootout", f"system/{label}"],
            capture_output=True,
        )
        result = subprocess.run([sudo, "rm", "-f", str(plist)], capture_output=True)
        if result.returncode == 0:
            removed.append(str(plist))
            logger.info("Removed launchd plist: %s", plist)
        else:
            logger.warning(
                "Failed to remove launchd plist %s: %s", plist, result.stderr.decode().strip()
            )
    logger.info("launchd service removal complete: %d services removed", len(removed))
    return removed


def systemd_remove_services(
    service_glob: str,
    timer_glob: str | None = None,
) -> list[str]:
    import shutil
    import subprocess

    removed: list[str] = []
    sudo = shutil.which("sudo") or "/usr/bin/sudo"
    systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
    service_dir = Path("/etc/systemd/system")
    if not service_dir.exists():
        logger.debug("systemd service dir %s does not exist", service_dir)
        return removed
    for svc in service_dir.glob(service_glob):
        unit = svc.name
        logger.info("Removing systemd service: %s", unit)
        subprocess.run([sudo, systemctl, "stop", unit], capture_output=True)
        subprocess.run([sudo, systemctl, "disable", unit], capture_output=True)
        result = subprocess.run([sudo, "rm", "-f", str(svc)], capture_output=True)
        if result.returncode == 0:
            removed.append(str(svc))
            logger.info("Removed systemd unit: %s", unit)
        else:
            logger.warning(
                "Failed to remove systemd unit %s: %s", unit, result.stderr.decode().strip()
            )
    if timer_glob:
        for svc in list(service_dir.glob(timer_glob)):
            timer_unit = svc.name.replace(".service", ".timer")
            logger.info("Removing systemd timer: %s", timer_unit)
            subprocess.run([sudo, systemctl, "stop", timer_unit], capture_output=True)
            subprocess.run([sudo, systemctl, "disable", timer_unit], capture_output=True)
            result = subprocess.run([sudo, "rm", "-f", str(svc)], capture_output=True)
            if result.returncode == 0:
                removed.append(str(svc))
            timer_path = service_dir / timer_unit
            if timer_path.exists():
                subprocess.run([sudo, "rm", "-f", str(timer_path)], capture_output=True)
                removed.append(str(timer_path))
    subprocess.run([sudo, systemctl, "daemon-reload"], capture_output=True)
    logger.info("systemd service removal complete: %d units removed", len(removed))
    return removed


def task_scheduler_remove_tasks(task_name_pattern: str) -> list[str]:
    import subprocess

    removed: list[str] = []
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return removed
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(",")
            task_name = parts[0].strip().strip('"')
            if task_name_pattern in task_name:
                logger.info("Removing task scheduler task: %s", task_name)
                del_result = subprocess.run(
                    ["schtasks", "/delete", "/tn", task_name, "/f"],
                    capture_output=True,
                    timeout=15,
                )
                if del_result.returncode == 0:
                    removed.append(task_name)
                    logger.info("Removed task: %s", task_name)
                else:
                    logger.warning(
                        "Failed to remove task %s: %s",
                        task_name,
                        del_result.stderr.decode().strip(),
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("Windows task scheduler removal not available or timed out")
    logger.info("Task scheduler removal complete: %d tasks removed", len(removed))
    return removed
