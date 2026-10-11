"""Descriptor-relative POSIX workspace publication."""

from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

_DIRECTORY_FLAGS: Final = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_LEAF_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_PERMISSION_BITS: Final = 0o777


class WritePlan(Protocol):
    @property
    def target(self) -> Path: ...

    @property
    def content(self) -> bytes: ...

    @property
    def original(self) -> bytes | None: ...

    @property
    def mode(self) -> int: ...


@dataclass(frozen=True, slots=True)
class PosixPublicationError(ValueError):
    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class _Directory:
    path: Path
    descriptor: int
    identity: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _StagedWrite:
    plan: WritePlan
    directory: _Directory
    temporary_name: str
    identity: tuple[int, int]


def _validate_control(path: Path, info: os.stat_result) -> None:
    if not stat.S_ISDIR(info.st_mode):
        raise PosixPublicationError(path, "path component must be a directory")
    owner = info.st_uid
    mode = stat.S_IMODE(info.st_mode)
    if owner not in {0, os.getuid()}:
        raise PosixPublicationError(path, "path component has a foreign owner")
    if mode & stat.S_IWGRP:
        raise PosixPublicationError(path, "path component is group-writable")
    if mode & stat.S_IWOTH and not (owner == 0 and mode & stat.S_ISVTX):
        raise PosixPublicationError(path, "path component is writable by another account")


def _open_directory(path: Path) -> _Directory:
    current = Path(path.anchor)
    descriptor = os.open(current, _DIRECTORY_FLAGS)
    try:
        _validate_control(current, os.fstat(descriptor))
        for part in path.parts[1:]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            current /= part
            _validate_control(current, os.fstat(descriptor))
        info = os.fstat(descriptor)
        return _Directory(path, descriptor, (info.st_dev, info.st_ino))
    except (OSError, PosixPublicationError):
        os.close(descriptor)
        raise


def _assert_directory_identity(directory: _Directory) -> None:
    try:
        info = directory.path.lstat()
    except OSError as exc:
        raise PosixPublicationError(directory.path, "directory changed during publication") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or (info.st_dev, info.st_ino) != directory.identity
    ):
        raise PosixPublicationError(directory.path, "directory changed during publication")
    _validate_control(directory.path, info)


def _unlink(name: str, directory: int) -> None:
    try:
        os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        return


def _stage(directory: _Directory, plan: WritePlan, content: bytes) -> tuple[str, tuple[int, int]]:
    name = f".{plan.target.name}.{secrets.token_hex(12)}.tmp"
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        plan.mode & _PERMISSION_BITS,
        dir_fd=directory.descriptor,
    )
    try:
        os.fchmod(descriptor, plan.mode & _PERMISSION_BITS)
        stream = os.fdopen(descriptor, "wb")
    except (OSError, ValueError):
        os.close(descriptor)
        _unlink(name, directory.descriptor)
        raise
    try:
        with stream:
            _ = stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
    except OSError:
        _unlink(name, directory.descriptor)
        raise
    return name, (info.st_dev, info.st_ino)


def _validate_leaf(item: _StagedWrite) -> None:
    plan = item.plan
    try:
        descriptor = os.open(plan.target.name, _LEAF_FLAGS, dir_fd=item.directory.descriptor)
    except FileNotFoundError:
        if plan.original is None:
            return
        raise PosixPublicationError(plan.target, "target changed during publication") from None
    except OSError as exc:
        raise PosixPublicationError(plan.target, "target cannot be opened safely") from exc
    try:
        stream = os.fdopen(descriptor, "rb")
    except (OSError, ValueError):
        os.close(descriptor)
        raise
    try:
        with stream:
            info = os.fstat(stream.fileno())
            contents = stream.read(len(plan.original or b"") + 1)
    except OSError as exc:
        raise PosixPublicationError(plan.target, "target cannot be read safely") from exc
    if plan.original is None:
        raise PosixPublicationError(plan.target, "target appeared during publication")
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise PosixPublicationError(plan.target, "target ownership or type changed")
    if stat.S_IMODE(info.st_mode) & _PERMISSION_BITS != plan.mode or contents != plan.original:
        raise PosixPublicationError(plan.target, "target changed during publication")


def _validate_published(item: _StagedWrite) -> None:
    try:
        descriptor = os.open(
            item.plan.target.name,
            _LEAF_FLAGS,
            dir_fd=item.directory.descriptor,
        )
    except OSError as exc:
        raise PosixPublicationError(item.plan.target, "published target is unsafe") from exc
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != item.identity:
        raise PosixPublicationError(item.plan.target, "published target inode changed")
    if info.st_uid != os.getuid():
        raise PosixPublicationError(item.plan.target, "published target has a foreign owner")
    if stat.S_IMODE(info.st_mode) & _PERMISSION_BITS != item.plan.mode:
        raise PosixPublicationError(item.plan.target, "published target mode changed")


def _replace(item: _StagedWrite, source: str) -> None:
    os.replace(
        source,
        item.plan.target.name,
        src_dir_fd=item.directory.descriptor,
        dst_dir_fd=item.directory.descriptor,
    )


def _rollback(item: _StagedWrite) -> None:
    if item.plan.original is None:
        _unlink(item.plan.target.name, item.directory.descriptor)
    else:
        name, _identity = _stage(item.directory, item.plan, item.plan.original)
        try:
            _replace(item, name)
        finally:
            _unlink(name, item.directory.descriptor)
    os.fsync(item.directory.descriptor)


def apply_posix_writes(plans: tuple[WritePlan, ...]) -> None:
    directories: dict[Path, _Directory] = {}
    staged: list[_StagedWrite] = []
    committed: list[_StagedWrite] = []
    try:
        for plan in plans:
            directory = directories.get(plan.target.parent)
            if directory is None:
                directory = _open_directory(plan.target.parent)
                directories[plan.target.parent] = directory
            name, identity = _stage(directory, plan, plan.content)
            staged.append(_StagedWrite(plan, directory, name, identity))
        for item in staged:
            _assert_directory_identity(item.directory)
            _validate_leaf(item)
            _replace(item, item.temporary_name)
            committed.append(item)
            _validate_published(item)
            os.fsync(item.directory.descriptor)
            _assert_directory_identity(item.directory)
    except (OSError, PosixPublicationError) as error:
        for item in reversed(committed):
            try:
                _rollback(item)
            except (OSError, PosixPublicationError) as cleanup_error:
                error.add_note(f"workspace rollback failed: {cleanup_error}")
        raise
    finally:
        for item in staged:
            _unlink(item.temporary_name, item.directory.descriptor)
        for directory in directories.values():
            os.close(directory.descriptor)


__all__ = ["PosixPublicationError", "apply_posix_writes"]
