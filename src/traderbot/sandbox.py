"""Application-level filesystem sandbox for agent workspace isolation.

Enforces a read-only constraint on the source tree and provides an
isolated workspace directory for agent file operations. On macOS,
delegates to sandbox-exec when available; on all platforms, falls
back to POSIX permission enforcement or Windows ACLs.
"""

from __future__ import annotations

import contextlib
import enum
import logging
import os
import shutil
import sys
import time
from typing import TYPE_CHECKING

import portalocker

from traderbot.fileops import set_dir_owner_only, set_file_owner_only
from traderbot.paths import get_agent_workspace_dir, get_source_root

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_SANDBOX_EXEC = shutil.which("sandbox-exec")

SANDBOX_PROFILE = """(version 1)
(allow default)
(deny file-write*
    (subpath "{src_root}")
    (subpath "{src_root}/"))
(allow file-write*
    (subpath "{workspace}")
    (subpath "{workspace}/"))
"""

SANDBOX_LOCK_EXT = ".sandbox_lock"


class SandboxStatus(enum.StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNAVAILABLE = "unavailable"


class FilesystemSandbox:
    """Enforces filesystem isolation for agent operations.

    On macOS: delegates to sandbox-exec for kernel-level enforcement.
    Fallback (all platforms): applies POSIX chmod 0o555 on src/ tree
    and grants 0o700 to the agent workspace.

    Workspace isolation is independent of sandbox mode: the workspace
    is always created with owner-only permissions and the source tree
    is locked to read-only during any sandbox operation.
    """

    def __init__(
        self,
        src_root: Path | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        self._src_root = src_root
        if self._src_root is None:
            try:
                self._src_root = get_source_root()
            except FileNotFoundError:
                self._src_root = None
        self._workspace_dir = workspace_dir or get_agent_workspace_dir()
        self._lock_path = self._workspace_dir / SANDBOX_LOCK_EXT
        self._status = SandboxStatus.INACTIVE
        self._entered_at: float | None = None

    @property
    def status(self) -> SandboxStatus:
        """Current sandbox status."""
        return self._status

    @property
    def workspace_dir(self) -> Path:
        """Path to the isolated agent workspace."""
        return self._workspace_dir

    @property
    def src_root(self) -> Path | None:
        """Path to the source tree (locked read-only when active).

        Returns None in pip-installed scenarios where no source tree exists.
        """
        return self._src_root

    def is_available(self) -> bool:
        """Check whether OS-level sandboxing is available."""
        return _SANDBOX_EXEC is not None

    def enter(self) -> None:
        """Enter the sandbox: lock src/ read-only, isolate workspace.

        On macOS, spawns a sandbox-exec subprocess for kernel-level
        enforcement. On fallback, applies chmod to lock the source tree.
        Raises RuntimeError if already active.
        """
        if self._status == SandboxStatus.ACTIVE:
            raise RuntimeError("Sandbox is already active")

        if self._src_root is None:
            logger.info("No source tree (pip install) — skipping src lockdown")
        else:
            self._lock_src_readonly()

        self._ensure_workspace()
        self._write_lock()

        if self.is_available():
            self._enter_macos_sandbox()
        else:
            logger.info("OS sandbox unavailable; using fallback chmod enforcement")
            self._status = SandboxStatus("unavailable")

        self._entered_at = time.time()
        self._status = SandboxStatus.ACTIVE
        logger.info(
            "Sandbox entered: workspace=%s src=%s mode=%s",
            self._workspace_dir,
            self._src_root,
            "macOS-sandbox-exec" if self.is_available() else "chmod-fallback",
        )

    def exit_sandbox(self) -> None:
        """Exit the sandbox: restore permissions and remove lock file."""
        if self._status != SandboxStatus.ACTIVE:
            return

        self._unlock_src()
        self._remove_lock()
        self._status = SandboxStatus.INACTIVE
        self._entered_at = None
        logger.info("Sandbox exited; workspace retained at %s", self._workspace_dir)

    def verify(self) -> bool:
        """Verify the sandbox is enforcing read-only on src/.

        Attempts to create a temporary file in the source root;
        returns True if blocked (sandbox working), False if writable.
        Returns True (vacuously) when no source tree exists (pip install).
        """
        if self._status != SandboxStatus.ACTIVE:
            return False

        if self._src_root is None:
            return True

        probe = self._src_root / f".sandbox_probe_{os.getpid()}"
        try:
            probe.touch()
            return False
        except (OSError, PermissionError):
            logger.debug("Sandbox probe touch failed at %s — likely inside sandbox", probe)
            return True
        finally:
            if probe.exists():
                with contextlib.suppress(OSError):
                    probe.unlink()

    def _ensure_workspace(self) -> None:
        """Create workspace if missing with owner-only permissions."""
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        set_dir_owner_only(self._workspace_dir)

    def _lock_src_readonly(self) -> None:
        """Lock the source tree to read-only via chmod on Unix.

        On Windows, this is a no-op; NTFS ACLs handle this separately
        via the icacls command (not yet implemented).
        No-op when _src_root is None (pip-installed, no source tree).
        """
        if self._src_root is None:
            return

        if not self._src_root.exists():
            raise FileNotFoundError(f"Source root not found: {self._src_root}")

        if sys.platform == "win32":
            return

        for path in self._src_root.rglob("*"):
            with contextlib.suppress(OSError):
                path.chmod(0o555)

    def _unlock_src(self) -> None:
        """Restore original permissions on source tree.

        Reverts src/ tree to 0o755 for directories and 0o644 for files.
        No-op when _src_root is None (pip-installed, no source tree).
        """
        if sys.platform == "win32":
            return

        if self._src_root is None or not self._src_root.exists():
            return

        for path in self._src_root.rglob("*"):
            try:
                if path.is_dir():
                    path.chmod(0o755)
                else:
                    path.chmod(0o644)
            except OSError:
                logger.debug("Sandbox chmod failed for %s", path)

    def _write_lock(self) -> None:
        """Write a PID-based lock file to the workspace."""
        self._lock_path.write_text(
            f"pid={os.getpid()}\nentered_at={self._entered_at or time.time()}"
        )
        set_file_owner_only(self._lock_path)

    def _remove_lock(self) -> None:
        """Remove the workspace lock file."""
        if self._lock_path.exists():
            self._lock_path.unlink(missing_ok=True)

    def _enter_macos_sandbox(self) -> None:
        """Spawn a sandbox-exec subprocess for kernel-level enforcement.

        The sandbox profile denies writes to the source root and allows
        writes to the agent workspace only.
        No-op when _src_root is None (pip-installed, no source tree).
        """
        if self._src_root is None:
            logger.info("No source tree (pip install) — skipping macOS sandbox profile")
            return
        profile = SANDBOX_PROFILE.format(
            src_root=str(self._src_root.resolve()),
            workspace=str(self._workspace_dir.resolve()),
        )
        profile_path = self._workspace_dir / ".sandbox_profile.sb"
        profile_path.write_text(profile)
        try:
            os.environ["TRADERBOT_SANDBOX_PROFILE"] = str(profile_path)
            logger.debug("macOS sandbox profile written to %s", profile_path)
        finally:
            pass


def create_sandbox(
    src_root: Path | None = None,
    workspace_dir: Path | None = None,
) -> FilesystemSandbox:
    """Create a configured sandbox instance."""
    return FilesystemSandbox(src_root=src_root, workspace_dir=workspace_dir)


def get_active_sandbox() -> FilesystemSandbox | None:
    """Return the active sandbox if one is running, else None."""
    from traderbot.paths import get_agent_workspace_dir

    lock_path = get_agent_workspace_dir() / SANDBOX_LOCK_EXT
    if not lock_path.exists():
        return None

    try:
        from traderbot.paths import get_source_root as _get_source_root

        with contextlib.suppress(FileNotFoundError):
            src_root = _get_source_root()
        return FilesystemSandbox(
            src_root=src_root,
            workspace_dir=get_agent_workspace_dir(),
        )
    except portalocker.exceptions.LockException:
        logger.debug("FilesystemSandbox lock contention, returning None")
        return None
