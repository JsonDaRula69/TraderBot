"""No-follow path hardening for encrypted local secret storage."""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError


class SecretPathError(RuntimeError):
    """Raised when local secret storage cannot be proven private and contained."""


class _WindowsAclReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    owner_sid: str
    current_sid: str
    protected: bool
    unsafe_allow_sids: list[str]


@dataclass(frozen=True, slots=True)
class SecureSecretPaths:
    data_root: Path
    secrets_root: Path
    files: tuple[Path, ...]

    @classmethod
    def parse(
        cls,
        secrets_root: Path,
        data_root: Path,
        files: tuple[Path, ...],
    ) -> SecureSecretPaths:
        if not secrets_root.is_absolute() or not data_root.is_absolute():
            raise SecretPathError("local secret paths must be absolute")
        if ".." in secrets_root.parts or ".." in data_root.parts:
            raise SecretPathError("local secret paths must not contain parent traversal")
        if secrets_root == data_root or not secrets_root.is_relative_to(data_root):
            raise SecretPathError("secret root must be contained beneath the data root")
        if any(path.parent != secrets_root for path in files):
            raise SecretPathError("secret files must be direct children of the secret root")
        paths = cls(data_root=data_root, secrets_root=secrets_root, files=files)
        paths.prepare(create=False)
        return paths

    def prepare(self, *, create: bool) -> None:
        _reject_linked_ancestors(self.data_root)
        if create and not self.data_root.exists():
            self.data_root.mkdir(parents=True, mode=0o700)
            _reject_linked_ancestors(self.data_root)
        if not self.data_root.exists():
            return
        self._validate_directory(self.data_root, harden=False)
        current = self.data_root
        for part in self.secrets_root.relative_to(self.data_root).parts:
            current /= part
            info = _lstat_optional(current)
            if info is None:
                if not create:
                    return
                current.mkdir(mode=0o700)
            self._validate_directory(current, harden=current == self.secrets_root)
        for path in self.files:
            info = _lstat_optional(path)
            if info is not None:
                self._validate_file(path, info)

    def validate_publication(self, path: Path) -> None:
        self.prepare(create=True)
        info = _lstat_optional(path)
        if info is not None:
            self._validate_file(path, info)

    def atomic_write(self, path: Path, contents: bytes) -> None:
        """Publish owner-only bytes without following the configured directory."""
        self.validate_publication(path)
        if sys.platform == "win32":
            self._atomic_write_windows(path, contents)
            return
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        directory = os.open(self.secrets_root, directory_flags)
        temporary_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
        try:
            self._assert_directory_identity(directory)
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                remaining = memoryview(contents)
                while remaining:
                    remaining = remaining[os.write(descriptor, remaining) :]
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.validate_publication(path)
            self._assert_directory_identity(directory)
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
            os.fsync(directory)
        finally:
            _unlink_temporary(temporary_name, directory)
            os.close(directory)
        self.prepare(create=False)

    def _assert_directory_identity(self, descriptor: int) -> None:
        opened = os.fstat(descriptor)
        current = _required_lstat(self.secrets_root)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SecretPathError("secret root identity changed during publication")

    def _atomic_write_windows(self, path: Path, contents: bytes) -> None:
        temporary = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=self.secrets_root,
            delete=False,
        )
        temporary_path = Path(temporary.name)
        try:
            with temporary as stream:
                _ = stream.write(contents)
            self.validate_publication(path)
            _secure_windows_acl(temporary_path)
            os.replace(temporary_path, path)
        except (OSError, SecretPathError):
            temporary_path.unlink(missing_ok=True)
            raise
        self.prepare(create=False)

    @staticmethod
    def _validate_directory(path: Path, *, harden: bool) -> None:
        info = _required_lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SecretPathError("secret path component is linked or not a directory")
        _validate_owner(path, info)
        if sys.platform == "win32":
            _secure_windows_acl(path)
        elif harden:
            path.chmod(0o700, follow_symlinks=False)
            if stat.S_IMODE(_required_lstat(path).st_mode) != 0o700:
                raise SecretPathError("secret root mode is not owner-only")

    @staticmethod
    def _validate_file(path: Path, info: os.stat_result) -> None:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise SecretPathError("secret storage file is linked or not regular")
        _validate_owner(path, info)
        if sys.platform == "win32":
            _secure_windows_acl(path)
        else:
            path.chmod(0o600, follow_symlinks=False)
            if stat.S_IMODE(_required_lstat(path).st_mode) != 0o600:
                raise SecretPathError("secret file mode is not owner-only")


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SecretPathError("cannot inspect local secret path") from exc


def _reject_linked_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = _lstat_optional(current)
        if info is None:
            return
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SecretPathError("configured data-root ancestry is linked or not a directory")


def _unlink_temporary(name: str, directory: int) -> None:
    try:
        os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        return


def _required_lstat(path: Path) -> os.stat_result:
    info = _lstat_optional(path)
    if info is None:
        raise SecretPathError("local secret path disappeared")
    return info


def _validate_owner(path: Path, info: os.stat_result) -> None:
    if sys.platform == "win32":
        if getattr(info, "st_file_attributes", 0) & 0x400:
            raise SecretPathError("Windows reparse points are forbidden")
        return
    if info.st_uid != os.getuid():
        raise SecretPathError(f"local secret path has foreign owner: {path.name}")


def _secure_windows_acl(path: Path) -> None:
    script = r"""
$ErrorActionPreference = 'Stop'
$item = Get-Item -LiteralPath $args[0]
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $args[0]
$acl.SetAccessRuleProtection($true, $false)
@($acl.Access) | ForEach-Object { [void]$acl.RemoveAccessRuleSpecific($_) }
$acl.SetOwner($current)
$flags = if ($item.PSIsContainer) { 'ContainerInherit,ObjectInherit' } else { 'None' }
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
  $current, 'FullControl', $flags, 'None', 'Allow'
)
[void]$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $args[0] -AclObject $acl
$verified = Get-Acl -LiteralPath $args[0]
$unsafe = @($verified.Access | Where-Object {
  $candidate = $_.IdentityReference.Translate(
    [System.Security.Principal.SecurityIdentifier]
  )
  $_.AccessControlType -eq 'Allow' -and $candidate.Value -ne $current.Value
})
[PSCustomObject]@{
  owner_sid = $verified.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  current_sid = $current.Value
  protected = $verified.AreAccessRulesProtected
  unsafe_allow_sids = @($unsafe | ForEach-Object { $_.IdentityReference.Value })
} | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        report = _WindowsAclReport.model_validate_json(result.stdout)
    except (OSError, subprocess.SubprocessError, ValidationError, json.JSONDecodeError) as exc:
        raise SecretPathError("Windows secret ACL hardening failed") from exc
    if report.owner_sid != report.current_sid or not report.protected or report.unsafe_allow_sids:
        raise SecretPathError("Windows secret ACL is not owner-only")


__all__ = ["SecureSecretPaths", "SecretPathError"]
