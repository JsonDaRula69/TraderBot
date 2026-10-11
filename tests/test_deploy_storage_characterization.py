"""Characterization locks for storage contracts consumed by deploy steps 4-5."""

from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.db.access import DatabaseAccess
from traderbot.db.chroma_store import ChromaOwnershipError, ChromaStore
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.security import create_chroma_root
from traderbot.profiles.generic import create_category_profile
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.store import SecretsStore


def test_secrets_facade_uses_encrypted_local_store_without_infisical(tmp_path: Path) -> None:
    # Given: the facade has no Infisical client and an isolated encrypted backend.
    encrypted = LocalEncryptedStore(base_path=tmp_path / "secrets")
    store = SecretsStore(local_store=encrypted)

    # When: a canonical Kalshi secret is persisted through the facade.
    store.set("kalshi", "api_key", "characterization-value")

    # Then: the facade resolves it while the encrypted file excludes plaintext.
    assert store.get("kalshi", "api_key") == "characterization-value"
    assert b"characterization-value" not in encrypted.secrets_file.read_bytes()


def test_database_access_denies_sysadmin_write_and_enumerates_category(
    tmp_path: Path,
) -> None:
    # Given: one selected category database exists through the authorized access seam.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    weather = create_category_profile("weather", "backtest")
    sysadmin = create_sysadmin_profile()
    with access.writable_decisions((weather, "weather")) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)

    # When/Then: canonical SysAdmin enumerates it but cannot acquire writable storage.
    with access.all_agent_decisions((sysadmin, "sysadmin")) as connections:
        assert len(connections) == 1
    with pytest.raises(RuntimeError):
        with access.writable_decisions((sysadmin, "sysadmin")):
            pytest.fail("SysAdmin must not receive a per-profile decisions database")
    pool.shutdown()


def test_chroma_close_releases_ownership_for_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one hardened embedded root is owned by a ChromaStore.
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(tmp_path))
    root = tmp_path / "chromadb"
    create_chroma_root(root)
    first = ChromaStore(root)

    # When/Then: contention is blocked until close, then a second owner can open.
    with pytest.raises(ChromaOwnershipError):
        _ = ChromaStore(root)
    first.close()
    with ChromaStore(root) as reopened:
        assert reopened.list_collections() == []
