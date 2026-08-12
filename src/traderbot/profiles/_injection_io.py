from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, override

NEW_FILE_MODE: Final = 0o600
PERMISSION_BITS: Final = 0o777


@dataclass(frozen=True, slots=True)
class WritePlan:
    target: Path
    content: bytes
    original: bytes | None
    mode: int


@dataclass(frozen=True, slots=True)
class WorkspaceInjectionError(ValueError):
    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"unsafe workspace path {self.path}: {self.reason}"


def reject_symlink_or_wrong_type(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or not expected:
        kind = "directory" if directory else "regular file"
        raise WorkspaceInjectionError(path, f"target must be a non-symlink {kind}")


def validate_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(root)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode):
            raise WorkspaceInjectionError(current, "symlink path components are forbidden")
        if not stat.S_ISDIR(info.st_mode):
            raise WorkspaceInjectionError(current, "path component must be a directory")
    return absolute


def existing_file_mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode) & PERMISSION_BITS


def temporary_file(target: Path, content: bytes, mode: int = NEW_FILE_MODE) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        os.chmod(temporary, mode & PERMISSION_BITS)
    except OSError:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    try:
        file_handle = os.fdopen(descriptor, "wb")
    except (OSError, ValueError) as fdopen_error:
        try:
            os.close(descriptor)
        except OSError as cleanup_error:
            fdopen_error.add_note(f"descriptor cleanup failed: {cleanup_error}")
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            fdopen_error.add_note(f"temporary cleanup failed: {cleanup_error}")
        raise
    try:
        with file_handle:
            _ = file_handle.write(content)
            file_handle.flush()
            os.fsync(file_handle.fileno())
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def apply_writes(plans: tuple[WritePlan, ...]) -> None:
    if os.name != "nt":
        from traderbot.profiles._injection_posix import (
            PosixPublicationError,
            apply_posix_writes,
        )

        try:
            apply_posix_writes(plans)
        except PosixPublicationError as exc:
            raise WorkspaceInjectionError(exc.path, exc.reason) from exc
        return
    staged: list[tuple[Path, WritePlan]] = []
    committed: list[WritePlan] = []
    try:
        for plan in plans:
            staged.append((temporary_file(plan.target, plan.content, plan.mode), plan))
        for temporary, plan in staged:
            _ = validate_root(plan.target.parent)
            reject_symlink_or_wrong_type(plan.target, directory=False)
            os.replace(temporary, plan.target)
            committed.append(plan)
    except (OSError, WorkspaceInjectionError):
        for plan in reversed(committed):
            if plan.original is None:
                _ = plan.target.unlink(missing_ok=True)
            else:
                rollback = temporary_file(plan.target, plan.original, plan.mode)
                try:
                    os.replace(rollback, plan.target)
                finally:
                    _ = rollback.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _plan in staged:
            _ = temporary.unlink(missing_ok=True)
