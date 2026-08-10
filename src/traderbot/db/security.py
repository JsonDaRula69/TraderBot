"""Filesystem and backend guards for embedded ChromaDB storage."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol, override

from pydantic import BaseModel, ConfigDict, ValidationError

from traderbot.paths import get_data_dir

_RUST_BACKEND = "chromadb.api.rust.RustBindingsAPI"
_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True, slots=True)
class InvalidChromaRootError(RuntimeError):
    """Raised when a Chroma root does not satisfy ownership invariants."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid Chroma root {self.path}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ChromaBackendError(RuntimeError):
    """Raised when Chroma is not using the pinned embedded backend."""

    backend: str
    telemetry_enabled: bool
    reason: str = "backend or telemetry invariant failed"

    @override
    def __str__(self) -> str:
        return (
            f"unsafe Chroma backend settings: backend={self.backend!r}, "
            f"anonymized_telemetry={self.telemetry_enabled}, reason={self.reason}"
        )


class _BackendSettings(Protocol):
    @property
    def chroma_api_impl(self) -> str: ...

    @property
    def anonymized_telemetry(self) -> bool: ...


class _SettingsClient(Protocol):
    def get_settings(self) -> _BackendSettings: ...


class _WindowsAclReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    owner_sid: str
    current_sid: str
    protected: bool
    unsafe_allow_sids: list[str]


def _current_posix_uid() -> int:
    import posix

    return posix.getuid()


def _raise_invalid(path: Path, reason: str) -> None:
    raise InvalidChromaRootError(path=path, reason=reason)


def _windows_acl_report(path: Path) -> _WindowsAclReport:
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $args[0]
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
$unsafe = @($acl.Access | Where-Object {
    $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
    $_.IdentityReference.Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value -ne $current
} | ForEach-Object {
    $_.IdentityReference.Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
})
[PSCustomObject]@{
    owner_sid = $owner
    current_sid = $current
    protected = $acl.AreAccessRulesProtected
    unsafe_allow_sids = $unsafe
} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return _WindowsAclReport.model_validate_json(result.stdout)


def _validate_windows_acl(path: Path) -> None:
    try:
        report = _windows_acl_report(path)
    except (OSError, subprocess.SubprocessError, ValidationError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"Windows ACL validation unavailable for {path}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return
    if report.owner_sid != report.current_sid:
        _raise_invalid(path, "owner SID does not match the current user SID")
    if not report.protected:
        _raise_invalid(path, "DACL inheritance is not protected")
    if report.unsafe_allow_sids:
        _raise_invalid(path, f"foreign allow ACEs: {report.unsafe_allow_sids}")


def _validate_macos_acl(path: Path, flags: int) -> None:
    if flags != 0:
        _raise_invalid(path, f"filesystem flags are present: {flags:#x}")
    try:
        result = subprocess.run(
            ["ls", "-lde", str(path)], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InvalidChromaRootError(path, f"macOS ACL inspection failed: {exc}") from exc
    lines = result.stdout.splitlines()
    mode_field = lines[0].split()[0] if lines else ""
    if mode_field.endswith("+") or any(line.lstrip()[:1].isdigit() for line in lines[1:]):
        _raise_invalid(path, "extended ACL entries are not allowed")


def validate_chroma_root(path: Path) -> None:
    """Reject a Chroma root unless it is private, owned, and contained."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise InvalidChromaRootError(path, f"cannot inspect root: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        _raise_invalid(path, "symlink roots are forbidden")
    if not stat.S_ISDIR(info.st_mode):
        _raise_invalid(path, "root is not a directory")

    resolved = Path(os.path.realpath(path))
    data_root = Path(os.path.realpath(get_data_dir()))
    if resolved == data_root or not resolved.is_relative_to(data_root):
        _raise_invalid(path, f"root is not contained beneath {data_root}")

    if sys.platform == "win32":
        file_attributes = getattr(info, "st_file_attributes", 0)
        if file_attributes & _WINDOWS_REPARSE_POINT:
            _raise_invalid(path, "Windows reparse points are forbidden")
        _validate_windows_acl(path)
        return

    if info.st_uid != _current_posix_uid():
        _raise_invalid(path, f"owner uid {info.st_uid} does not match current user")
    mode = stat.S_IMODE(info.st_mode)
    if mode != 0o700:
        _raise_invalid(path, f"mode must be 0700, got {mode:04o}")
    if sys.platform == "darwin":
        _validate_macos_acl(path, getattr(info, "st_flags", 0))


def _harden_windows_acl(path: Path) -> None:
    script = r"""
$ErrorActionPreference = 'Stop'
$item = Get-Item -LiteralPath $args[0]
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $args[0]
$acl.SetAccessRuleProtection($true, $false)
@($acl.Access) | ForEach-Object { [void]$acl.RemoveAccessRuleSpecific($_) }
$acl.SetOwner($sid)
$inheritance = if ($item.PSIsContainer) {
    [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
} else {
    [System.Security.AccessControl.InheritanceFlags]::None
}
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
    $sid,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    $inheritance,
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow
)
[void]$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $args[0] -AclObject $acl
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        warnings.warn(
            f"Windows ACL hardening failed for {path}: {result.stderr.strip()}",
            RuntimeWarning,
            stacklevel=2,
        )


def _remove_created_root(path: Path, lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)
    path.rmdir()


def create_chroma_root(path: Path) -> None:
    """Create a new private Chroma root and fail closed on every check."""
    lock_path = path / "chromadb.lock"
    created = False
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        created = True
        path.chmod(0o700)
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _ = os.write(descriptor, b"\0")
        finally:
            os.close(descriptor)
        lock_path.chmod(0o600)
        if sys.platform == "win32":
            _harden_windows_acl(path)
            _harden_windows_acl(lock_path)
        validate_chroma_root(path)
        validate_chroma_lock_file(lock_path)
    except FileExistsError as exc:
        raise InvalidChromaRootError(path, "target already exists") from exc
    except InvalidChromaRootError:
        if created:
            _remove_created_root(path, lock_path)
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        if created:
            _remove_created_root(path, lock_path)
        raise InvalidChromaRootError(path, f"creation failed: {exc}") from exc


def validate_chroma_lock_file(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise InvalidChromaRootError(path, f"cannot inspect lock file: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _raise_invalid(path, "lock must be a regular non-symlink file")
    if sys.platform == "win32":
        _validate_windows_acl(path)
        return
    if info.st_uid != _current_posix_uid():
        _raise_invalid(path, "lock owner does not match current user")
    mode = stat.S_IMODE(info.st_mode)
    if mode != 0o600:
        _raise_invalid(path, f"lock mode must be 0600, got {mode:04o}")


def assert_embedded_backend(client: _SettingsClient) -> None:
    """Require the Rust embedded backend with telemetry disabled."""
    settings = client.get_settings()
    if settings.chroma_api_impl != _RUST_BACKEND or settings.anonymized_telemetry:
        raise ChromaBackendError(settings.chroma_api_impl, settings.anonymized_telemetry)


__all__ = [
    "ChromaBackendError",
    "InvalidChromaRootError",
    "assert_embedded_backend",
    "create_chroma_root",
    "validate_chroma_root",
]
