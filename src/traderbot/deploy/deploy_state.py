"""Validate and persist trusted deploy state and fingerprints."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import override

from pydantic import ValidationError

from traderbot.deploy.wizard_contracts import DeployState, WizardRequest

_MAX_STATE_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class DeployStateError(RuntimeError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


def validate_data_root(data_root: Path) -> Path:
    if not data_root.is_absolute() or ".." in data_root.parts or "\x00" in str(data_root):
        raise DeployStateError("data root path is invalid")
    current = Path(data_root.anchor)
    for part in data_root.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return data_root
        except OSError as exc:
            raise DeployStateError("data root cannot be inspected") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise DeployStateError("data root ancestry is linked or not a directory")
    info = data_root.lstat()
    if os.name != "nt" and info.st_uid != os.getuid():
        raise DeployStateError("data root has a foreign owner")
    if os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o700:
        raise DeployStateError("data root mode is not owner-only")
    return data_root


def step_fingerprint(request: WizardRequest, step: int) -> str:
    common = {
        "categories": [category.value for category in request.categories],
        "mode": request.mode,
        "data_root": str(request.data_root),
    }
    payloads = {
        6: common
        | {
            "months": request.months_backfill,
            "collector": None if request.collector_db is None else str(request.collector_db),
        },
        7: {"contract": "traderbot-main-at-5m-v1"},
        8: common
        | {
            "months": request.months_backfill,
            "collector": None if request.collector_db is None else str(request.collector_db),
            "sysadmin": None
            if request.sysadmin_workspace is None
            else str(request.sysadmin_workspace),
            "workspaces": {
                category.value: str(path)
                for category, path in sorted(
                    request.category_workspaces.items(), key=lambda item: item[0].value
                )
            },
            "infisical": request.infisical_url,
            "mcp": request.daemon_mcp_url,
        },
    }
    encoded = json.dumps(payloads[step], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_deploy_state(data_root: Path) -> DeployState | None:
    root = validate_data_root(data_root)
    path = root / "deploy-state.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DeployStateError("deploy state cannot be inspected") from exc
    _validate_state_metadata(info)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise DeployStateError("deploy state changed during validation")
            _validate_state_metadata(opened)
            contents = stream.read(_MAX_STATE_BYTES + 1)
    except OSError as exc:
        raise DeployStateError("deploy state cannot be read safely") from exc
    if len(contents) > _MAX_STATE_BYTES:
        raise DeployStateError("deploy state exceeds the size limit")
    try:
        return DeployState.model_validate_json(contents)
    except ValidationError as exc:
        raise DeployStateError("deploy state is malformed") from exc


def _validate_state_metadata(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise DeployStateError("deploy state is not regular")
    if os.name != "nt" and info.st_uid != os.getuid():
        raise DeployStateError("deploy state has a foreign owner")
    if os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o600:
        raise DeployStateError("deploy state mode is not owner-only")
    if info.st_size > _MAX_STATE_BYTES:
        raise DeployStateError("deploy state exceeds the size limit")


def save_deploy_state(data_root: Path, state: DeployState) -> None:
    data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = validate_data_root(data_root)
    directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    temporary = f".deploy-state.{secrets.token_hex(8)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        contents = state.model_dump_json().encode()
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            _ = stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, "deploy-state.json", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


__all__ = [
    "DeployState",
    "DeployStateError",
    "load_deploy_state",
    "save_deploy_state",
    "step_fingerprint",
    "validate_data_root",
]
