"""Adversarial filesystem tests for encrypted local secret storage."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from traderbot.secrets.local_encrypted import LocalEncryptedStore, SecretIntegrityError


def _write(store: LocalEncryptedStore) -> None:
    store.set(service="kalshi", key="api_key", value=os.urandom(24).hex(), namespace="global")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
@pytest.mark.parametrize(
    "linked_component",
    ["configured_ancestor", "root", "ancestor", "target"],
)
def test_linked_secret_paths_fail_closed_without_touching_target(
    tmp_path: Path,
    linked_component: str,
) -> None:
    # Given: a link at each trust-boundary position and an external sentinel.
    external = tmp_path / "external"
    external.mkdir()
    if linked_component == "configured_ancestor":
        linked = tmp_path / "linked-data"
        linked.symlink_to(external, target_is_directory=True)
        data_root = linked / "data"
        data_root.mkdir()
    else:
        data_root = tmp_path / "data"
        data_root.mkdir()
    sentinel = external / "sentinel"
    _ = sentinel.write_bytes(os.urandom(16))
    before = sentinel.read_bytes()
    if linked_component == "configured_ancestor":
        secrets_root = data_root / "secrets"
    elif linked_component == "root":
        secrets_root = data_root / "secrets"
        secrets_root.symlink_to(external, target_is_directory=True)
    elif linked_component == "ancestor":
        linked = data_root / "linked"
        linked.symlink_to(external, target_is_directory=True)
        secrets_root = linked / "secrets"
    else:
        secrets_root = data_root / "secrets"
        secrets_root.mkdir()
        (secrets_root / "secrets.json").symlink_to(sentinel)

    # When/Then: construction or first use rejects the link without target mutation.
    with pytest.raises(SecretIntegrityError):
        store = LocalEncryptedStore(base_path=secrets_root, data_root=data_root)
        _write(store)
    assert sentinel.read_bytes() == before


def test_relative_or_escaping_secret_root_is_rejected(tmp_path: Path) -> None:
    # Given/When/Then: lexical escape and relative configuration fail before use.
    with pytest.raises(SecretIntegrityError):
        _ = LocalEncryptedStore(base_path=Path("relative/secrets"), data_root=tmp_path)
    with pytest.raises(SecretIntegrityError):
        _ = LocalEncryptedStore(
            base_path=tmp_path / "data" / ".." / "escape", data_root=tmp_path / "data"
        )


def test_wrong_type_secret_root_is_rejected(tmp_path: Path) -> None:
    # Given: the configured secret directory is a regular file.
    data_root = tmp_path / "data"
    data_root.mkdir()
    root = data_root / "secrets"
    _ = root.write_bytes(os.urandom(12))

    # When/Then: no write follows the wrong-type target.
    with pytest.raises(SecretIntegrityError):
        _ = LocalEncryptedStore(base_path=root, data_root=data_root)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions are unavailable")
def test_existing_directory_and_files_are_hardened_before_use(tmp_path: Path) -> None:
    # Given: a valid existing store is made permissive after its first write.
    data_root = tmp_path / "data"
    data_root.mkdir()
    root = data_root / "secrets"
    original = LocalEncryptedStore(base_path=root, data_root=data_root)
    _write(original)
    root.chmod(0o755)
    original.secrets_file.chmod(0o644)
    original.integrity_file.chmod(0o644)

    # When: the existing root is reopened.
    reopened = LocalEncryptedStore(base_path=root, data_root=data_root)

    # Then: directory and files are owner-only before any read.
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(reopened.secrets_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(reopened.integrity_file.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership is unavailable")
def test_foreign_owned_root_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: lstat reports a valid directory owned by another uid.
    data_root = tmp_path / "data"
    data_root.mkdir()
    root = data_root / "secrets"
    root.mkdir()
    real_lstat = os.lstat

    def foreign_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        result = real_lstat(path)
        if Path(path) == root:
            values = list(result)
            values[4] = result.st_uid + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", foreign_lstat)

    # When/Then: ownership mismatch is rejected before chmod or publication.
    with pytest.raises(SecretIntegrityError):
        _ = LocalEncryptedStore(base_path=root, data_root=data_root)
