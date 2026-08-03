"""Tests for the encrypted local secrets store (DD-037 §9)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from traderbot.secrets import SecretsStore
from traderbot.secrets.local_encrypted import (
    LocalEncryptedStore,
    SecretIntegrityError,
    derive_key,
)
from traderbot.secrets.store import SecretNotFoundError


def test_api_key_roundtrip(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    assert store.get(service="kalshi", key="api_key", namespace="global") == "sk-live-123"


def test_profile_token_roundtrip(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    store.set(service="sysadmin", key="token", value="agent-token", namespace="tokens")

    assert store.get(service="sysadmin", key="token", namespace="tokens") == "agent-token"


def test_set_overwrites_existing_value(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="first", namespace="global")

    store.set(service="kalshi", key="api_key", value="second", namespace="global")

    assert store.get(service="kalshi", key="api_key", namespace="global") == "second"


def test_missing_key_returns_none(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    assert store.get(service="kalshi", key="api_key", namespace="global") is None


def test_delete_removes_key(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    store.delete(service="kalshi", key="api_key", namespace="global")

    assert store.get(service="kalshi", key="api_key", namespace="global") is None


def test_delete_missing_key_raises_not_found(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    with pytest.raises(SecretNotFoundError):
        store.delete(service="kalshi", key="api_key", namespace="global")


def test_get_namespace_flattens_service_keys(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")
    store.set(service="kalshi", key="private_key_pem", value="PEM", namespace="global")
    store.set(service="voyage", key="api_key", value="v-k", namespace="global")

    assert store.get_namespace("global") == {
        "kalshi_api_key": "sk-live-123",
        "kalshi_private_key_pem": "PEM",
        "voyage_api_key": "v-k",
    }


def test_namespaces_are_isolated(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="global-key", namespace="global")
    store.set(service="sysadmin", key="token", value="agent-token", namespace="tokens")

    assert store.get(service="kalshi", key="api_key", namespace="global") == "global-key"
    assert store.get(service="sysadmin", key="token", namespace="tokens") == "agent-token"
    assert store.get(service="kalshi", key="api_key", namespace="tokens") is None
    assert store.get(service="sysadmin", key="token", namespace="global") is None


def test_secrets_file_is_not_plaintext(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    raw = store.secrets_file.read_text(encoding="utf-8")
    assert "sk-live-123" not in raw
    assert "api_key" not in raw
    assert "kalshi" not in raw


def test_tampered_integrity_file_fails_closed(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")
    _ = store.integrity_file.write_text("0" * 64, encoding="ascii")

    with pytest.raises(SecretIntegrityError, match="integrity check failed"):
        _ = store.get(service="kalshi", key="api_key", namespace="global")


def test_missing_integrity_file_fails_closed(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")
    store.integrity_file.unlink()

    with pytest.raises(SecretIntegrityError, match="cannot read integrity metadata"):
        _ = store.get(service="kalshi", key="api_key", namespace="global")


def test_corrupt_payload_fails_closed(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")
    _ = store.secrets_file.write_text("garbage", encoding="utf-8")
    _ = store.integrity_file.write_text(hashlib.sha256(b"garbage").hexdigest(), encoding="ascii")

    with pytest.raises(SecretIntegrityError, match="is corrupt"):
        _ = store.get(service="kalshi", key="api_key", namespace="global")


def test_foreign_machine_key_cannot_decrypt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = derive_key("other-host", "other-user", "other-machine-id")
    foreign_store = LocalEncryptedStore(base_path=tmp_path)
    monkeypatch.setattr(foreign_store, "_fernet", foreign)
    foreign_store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    local_store = LocalEncryptedStore(base_path=tmp_path)

    with pytest.raises(SecretIntegrityError, match="cannot be decrypted"):
        _ = local_store.get(service="kalshi", key="api_key", namespace="global")


def test_empty_store_returns_none_and_empty_namespace(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    assert store.get(service="kalshi", key="api_key", namespace="global") is None
    assert store.get_namespace("global") == {}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions are unavailable")
def test_secrets_files_permissions(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)

    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    assert store.secrets_file.stat().st_mode & 0o777 == 0o600
    assert store.integrity_file.stat().st_mode & 0o777 == 0o600


def test_persists_across_store_instances(tmp_path: Path) -> None:
    store = LocalEncryptedStore(base_path=tmp_path)
    store.set(service="kalshi", key="api_key", value="sk-live-123", namespace="global")

    reopened = LocalEncryptedStore(base_path=tmp_path)

    assert reopened.get(service="kalshi", key="api_key", namespace="global") == "sk-live-123"


def test_facade_roundtrip_through_local_encrypted_store(tmp_path: Path) -> None:
    facade = SecretsStore(local_store=LocalEncryptedStore(base_path=tmp_path))

    facade.set("kalshi", "api_key", "sk-live-123", namespace="global")
    facade.set("sysadmin", "token", "agent-token", namespace="tokens")

    assert facade.get("kalshi", "api_key", namespace="global") == "sk-live-123"
    assert facade.get("sysadmin", "token", namespace="tokens") == "agent-token"
    assert facade.get_namespace("global") == {"kalshi_api_key": "sk-live-123"}


def test_facade_delete_missing_key_raises(tmp_path: Path) -> None:
    facade = SecretsStore(local_store=LocalEncryptedStore(base_path=tmp_path))

    with pytest.raises(SecretNotFoundError):
        facade.delete("kalshi", "api_key", namespace="global")


def test_derive_key_produces_working_fernet() -> None:
    fernet = derive_key("host", "user", "machine")

    token = fernet.encrypt(b"data")

    assert fernet.decrypt(token) == b"data"
