"""Tests for the local → Infisical token migration (DD-037, Phase 1.5).

The migration reads the Phase 1 ``LocalTokenStore`` file (``tokens.json``)
and stores each profile token via :class:`SecretsStore`. Tests drive the
migration through the recorded-call Infisical fake from ``test_secrets_store``
so no real Infisical instance is required, and verify the one-way contract:
the original file is never modified or deleted.

Run with: pytest tests/test_migrate.py -v
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from tests.test_secrets_store import FakeInfisicalClient
from traderbot.secrets import SecretsStore
from traderbot.secrets.migrate import build_infisical_store, migrate_local_to_infisical
from traderbot.secrets.protocols import (
    InfisicalClient,
    SecretListResult,
    SecretResult,
    SecretsResource,
)

TOKENS = {
    "tok-weather": {"profile": "weather", "agent_id": "weather"},
    "tok-sys": {"profile": "sysadmin", "agent_id": "sysadmin"},
}


class _UnreachableSecrets:
    def get_secret_by_name(
        self,
        *,
        secret_name: str,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        view_secret_value: bool = True,
    ) -> SecretResult:
        del secret_name, environment_slug, secret_path, project_slug, view_secret_value
        raise RequestsConnectionError("unreachable")

    def create_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
    ) -> SecretResult:
        del secret_name, secret_path, environment_slug, project_slug, secret_value
        raise RequestsConnectionError("unreachable")

    def update_secret_by_name(
        self,
        *,
        current_secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
    ) -> SecretResult:
        del current_secret_name, secret_path, environment_slug, project_slug, secret_value
        raise RequestsConnectionError("unreachable")

    def delete_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
    ) -> SecretResult:
        del secret_name, secret_path, environment_slug, project_slug
        raise RequestsConnectionError("unreachable")

    def list_secrets(
        self,
        *,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        view_secret_value: bool = True,
    ) -> SecretListResult:
        del environment_slug, secret_path, project_slug, view_secret_value
        raise RequestsConnectionError("unreachable")


class _UnreachableClient(InfisicalClient):
    @property
    def secrets(self) -> SecretsResource:
        return _UnreachableSecrets()


def _write_tokens(path: Path, tokens: Mapping[str, Mapping[str, str]]) -> None:
    path.write_text(json.dumps({"tokens": dict(tokens)}), encoding="utf-8")


def _store(client: FakeInfisicalClient | None = None) -> SecretsStore:
    return SecretsStore(infisical_client=client or FakeInfisicalClient())


def test_migrate_all_tokens_successfully(tmp_path) -> None:
    client = FakeInfisicalClient()
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(tokens_path, TOKENS)

    count = migrate_local_to_infisical(store=_store(client), tokens_path=tokens_path)

    assert count == 2
    for token, entry in TOKENS.items():
        stored = _store(client).get_profile_token(entry["agent_id"])
        assert stored is not None
        assert stored["token"] == token
        assert stored["profile"] == entry["profile"]
        assert stored["agent_id"] == entry["agent_id"]
        assert stored["categories"] == []
        assert stored["permissions"] == []


def test_migrate_uses_agent_id_token_names_in_tokens_namespace(tmp_path) -> None:
    client = FakeInfisicalClient()
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(tokens_path, TOKENS)

    _ = migrate_local_to_infisical(store=_store(client), tokens_path=tokens_path)

    created = [c for c in client.secrets.calls if c[0] == "create"]
    assert {c[1]["secret_name"] for c in created} == {"weather_token", "sysadmin_token"}
    assert all(c[1]["project_slug"] == "traderbot-agent-tokens" for c in created)
    assert all(c[1]["environment_slug"] == "prod" for c in created)


def test_migrate_unreachable_infisical_raises_connection_error(tmp_path) -> None:
    store = SecretsStore(infisical_client=_UnreachableClient())
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(tokens_path, {"tok-1": {"profile": "weather", "agent_id": "weather"}})

    with pytest.raises(ConnectionError, match="Infisical unreachable"):
        _ = migrate_local_to_infisical(store=store, tokens_path=tokens_path)


def test_migrate_missing_tokens_file_raises_informative_error(tmp_path) -> None:
    missing = tmp_path / "no-tokens.json"

    with pytest.raises(FileNotFoundError, match="nothing to migrate"):
        _ = migrate_local_to_infisical(store=_store(), tokens_path=missing)


def test_migrate_empty_tokens_file_returns_zero(tmp_path) -> None:
    client = FakeInfisicalClient()
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(tokens_path, {})

    count = migrate_local_to_infisical(store=_store(client), tokens_path=tokens_path)

    assert count == 0
    assert client.secrets.calls == []


def test_migrate_does_not_delete_original_file(tmp_path) -> None:
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(tokens_path, TOKENS)
    original = tokens_path.read_bytes()

    _ = migrate_local_to_infisical(store=_store(), tokens_path=tokens_path)

    assert tokens_path.exists()
    assert tokens_path.read_bytes() == original


def test_build_store_from_env(monkeypatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "service-token")
    monkeypatch.setenv("INFISICAL_DOMAIN", "https://infisical.example")

    store = build_infisical_store()

    assert isinstance(store, SecretsStore)


def test_build_store_missing_env_config_raises(monkeypatch) -> None:
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.delenv("INFISICAL_DOMAIN", raising=False)

    with pytest.raises(RuntimeError, match="INFISICAL_TOKEN and INFISICAL_DOMAIN"):
        _ = build_infisical_store()
