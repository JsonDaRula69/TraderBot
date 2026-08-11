"""Fail-closed workspace template injection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from traderbot.profiles._injection_io import NEW_FILE_MODE as _NEW_FILE_MODE
from traderbot.profiles._injection_io import WorkspaceInjectionError
from traderbot.profiles._injection_io import WritePlan as _WritePlan
from traderbot.profiles._injection_io import apply_writes as _apply_writes
from traderbot.profiles._injection_io import existing_file_mode as _existing_file_mode
from traderbot.profiles._injection_io import (
    reject_symlink_or_wrong_type as _reject_symlink_or_wrong_type,
)
from traderbot.profiles._injection_io import validate_root as _validate_root

__all__ = (
    "InjectionAction",
    "InjectionRecord",
    "InjectionReport",
    "InjectionStrategy",
    "WorkspaceInjectionError",
    "WorkspaceTemplate",
    "inject_workspace",
    "validate_workspace_path",
)

START_MARKER: Final = b"<!-- BEGIN TRADERBOT MANAGED -->"
END_MARKER: Final = b"<!-- END TRADERBOT MANAGED -->"
_FENCED_FILES: Final = ("AGENTS.md", "SOUL.md", "IDENTITY.md")
_FULL_INIT_FILES: Final = ("USER.md", "SESSION-STATE.md")
_LEARNINGS_DIRECTORY: Final = ".learnings"
_FULL_WORKSPACES: Final = frozenset({"weather", "sysadmin"})


def validate_workspace_path(root: Path) -> Path:
    """Return an absolute workspace path only when every existing component is safe."""
    return _validate_root(root)


class InjectionStrategy(StrEnum):
    FENCED_MERGE = "fenced_merge"
    INIT_IF_MISSING = "init_if_missing"


FENCED_MERGE: Final = InjectionStrategy.FENCED_MERGE
INIT_IF_MISSING: Final = InjectionStrategy.INIT_IF_MISSING


class WorkspaceTemplate(StrEnum):
    WEATHER = "weather"
    ECONOMICS = "economics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    POLITICS = "politics"
    ENTERTAINMENT = "entertainment"
    FINANCIAL = "financial"
    WORLD = "world"
    OTHER = "other"
    SYSADMIN = "sysadmin"


class InjectionAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    PRESERVED = "preserved"


@dataclass(frozen=True, slots=True)
class InjectionRecord:
    path: str
    strategy: InjectionStrategy
    action: InjectionAction
    sha256: str | None


@dataclass(frozen=True, slots=True)
class InjectionReport:
    template: WorkspaceTemplate
    records: tuple[InjectionRecord, ...]
    manifest_hash: str


def _default_templates_root() -> Path:
    packaged = Path(__file__).parents[1] / "workspace"
    return packaged if packaged.is_dir() else Path(__file__).parents[3] / "workspace"


def _parse_template(value: WorkspaceTemplate | str) -> WorkspaceTemplate:
    try:
        return WorkspaceTemplate(str(value))
    except ValueError as exc:
        raise WorkspaceInjectionError(Path(str(value)), "template name is not allowed") from exc


def _file_names(template: WorkspaceTemplate) -> tuple[str, ...]:
    if template.value in _FULL_WORKSPACES:
        return (*_FENCED_FILES, *_FULL_INIT_FILES, _LEARNINGS_DIRECTORY)
    return _FENCED_FILES


def _strategy(name: str) -> InjectionStrategy:
    if name in _FENCED_FILES:
        return FENCED_MERGE
    return INIT_IF_MISSING


def _managed_bytes(template: bytes) -> bytes:
    return START_MARKER + b"\n" + template.rstrip(b"\n") + b"\n" + END_MARKER


def _merge_fenced(target: Path, existing: bytes, template: bytes) -> bytes:
    markers = tuple(
        line.strip()
        for line in existing.splitlines()
        if b"TRADERBOT" in line and (b"BEGIN" in line or b"END" in line)
    )
    start_count = existing.count(START_MARKER)
    end_count = existing.count(END_MARKER)
    if markers and any(marker not in (START_MARKER, END_MARKER) for marker in markers):
        raise WorkspaceInjectionError(target, "incompatible managed marker")
    if start_count == 0 and end_count == 0:
        separator = b"" if not existing or existing.endswith(b"\n") else b"\n"
        return existing + separator + _managed_bytes(template) + b"\n"
    if start_count != 1 or end_count != 1:
        raise WorkspaceInjectionError(target, "managed markers must form exactly one pair")
    start = existing.index(START_MARKER)
    end = existing.index(END_MARKER)
    if end < start:
        raise WorkspaceInjectionError(target, "managed markers are reversed")
    return existing[:start] + _managed_bytes(template) + existing[end + len(END_MARKER) :]


def _read_template(root: Path, template: WorkspaceTemplate, name: str) -> bytes:
    source = root / template.value / name
    if not source.is_relative_to(root):
        raise WorkspaceInjectionError(source, "template path escapes the template root")
    _ = _validate_root(source.parent)
    _reject_symlink_or_wrong_type(source, directory=False)
    try:
        return source.read_bytes()
    except FileNotFoundError as exc:
        raise WorkspaceInjectionError(source, "required template file is missing") from exc


def inject_workspace(
    workspace_root: Path,
    template: WorkspaceTemplate | str,
    templates_root: Path | None = None,
) -> InjectionReport:
    """Safely synchronize one allowlisted template into a selected workspace root."""
    selected = _parse_template(template)
    source_root = _validate_root(templates_root or _default_templates_root())
    root = _validate_root(workspace_root)
    names = _file_names(selected)
    templates = {
        name: _read_template(source_root, selected, name)
        for name in names
        if name != _LEARNINGS_DIRECTORY
    }
    root_exists = root.exists()
    if root_exists:
        _reject_symlink_or_wrong_type(root, directory=True)

    plans: list[_WritePlan] = []
    records: list[InjectionRecord] = []
    for name in names:
        strategy = _strategy(name)
        target = root / name
        if not target.is_relative_to(root):
            raise WorkspaceInjectionError(target, "target escapes the workspace root")
        if name == _LEARNINGS_DIRECTORY:
            _reject_symlink_or_wrong_type(target, directory=True)
            action = InjectionAction.PRESERVED if target.exists() else InjectionAction.CREATED
            records.append(InjectionRecord(name, strategy, action, None))
            continue
        _reject_symlink_or_wrong_type(target, directory=False)
        existing = target.read_bytes() if target.exists() else None
        mode = (
            _NEW_FILE_MODE
            if existing is None
            else _existing_file_mode(target)
        )
        if name in _FENCED_FILES:
            desired = _merge_fenced(target, existing or b"", templates[name])
            action = (
                InjectionAction.CREATED
                if existing is None
                else InjectionAction.UNCHANGED
                if desired == existing
                else InjectionAction.UPDATED
            )
        else:
            desired = templates[name] if existing is None else existing
            action = InjectionAction.CREATED if existing is None else InjectionAction.PRESERVED
        if existing != desired:
            plans.append(_WritePlan(target, desired, existing, mode))
        records.append(
            InjectionRecord(name, strategy, action, hashlib.sha256(desired).hexdigest())
        )

    created_root = not root_exists
    created_learnings = False
    learnings = root / _LEARNINGS_DIRECTORY
    try:
        _ = _validate_root(root)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if _LEARNINGS_DIRECTORY in names and not learnings.exists():
            learnings.mkdir(mode=0o700)
            created_learnings = True
        _apply_writes(tuple(plans))
    except (OSError, WorkspaceInjectionError):
        if created_learnings:
            learnings.rmdir()
        if created_root:
            root.rmdir()
        raise

    digest = hashlib.sha256()
    for record in records:
        digest.update(record.path.encode())
        digest.update(b"\0")
        digest.update((record.sha256 or "directory").encode())
        digest.update(b"\n")
    return InjectionReport(selected, tuple(records), digest.hexdigest())
