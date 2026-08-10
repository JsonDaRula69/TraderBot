"""Binary path resolution for service template substitution (DD-022).

Resolves the traderbot and python executables at install time so that
service templates (systemd, launchd, Windows Task Scheduler) receive fully
resolved absolute paths. This is required because pipx binary paths vary by
backend (virtualenv vs uv) and by user-customized ``PIPX_*`` locations, and
the service managers require absolute paths at install time (no PATH
lookups at boot).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BinPaths:
    """Fully resolved paths used to substitute service templates.

    Attributes:
        traderbot_bin: Resolved absolute path to the traderbot console script.
        python_bin: Resolved absolute path to the Python interpreter.
        home: The user's home directory.
        user: The OS username running the service.
    """

    traderbot_bin: Path
    python_bin: Path
    home: Path
    user: str


def resolve_traderbot_bin() -> Path:
    """Resolve the absolute traderbot executable path.

    Uses ``shutil.which`` to locate the console script on PATH and resolves
    symlinks to the real binary. Falls back to the running interpreter's
    directory (``python -m traderbot`` style) when ``which`` fails, checking
    the POSIX name first and the Windows ``.exe`` name second.
    """
    found = shutil.which("traderbot")
    if found:
        return Path(found).resolve()

    candidate = Path(sys.executable).parent / "traderbot"
    if not candidate.exists():
        candidate = Path(sys.executable).parent / "traderbot.exe"  # Windows
    return candidate.resolve()


def resolve_bin_paths() -> BinPaths:
    """Resolve binary paths for service template substitution.

    Returns:
        A ``BinPaths`` instance with the traderbot binary, the python
        interpreter, the home directory, and the OS username.
    """
    return BinPaths(
        traderbot_bin=resolve_traderbot_bin(),
        python_bin=Path(sys.executable).resolve(),
        home=Path.home(),
        user=os.environ.get("USER", "traderbot"),
    )
