"""Tests for the unified SecretsStore facade (DD-037)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from infisical_sdk.infisical_requests import APIError

from traderbot.secrets import SecretNotFoundError, SecretsStore


class FakeLocalStore:
    """Dict-backed stand-in for LocalEncryptedStore (Todo 4)."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict[str, str]]] = {}

    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        return self.data.get(namespace, {}).get(service, {}).get(key)

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        self.data.setdefault(namespace, {}).setdefault(service, {})[key] = value

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        del self.data.setdefault(namespace, {}).setdefault(service, {})[key]

    def get_namespace(self, namespace: str) -> dict[str, str]:
        flat: dict[str, str] = {}
        for service, keys in self.data.get(namespace, {}).items():
            for key, value in keys.items():
                flat[f"{service}_{key}"] = value
        return flat


@dataclass
class Secret:
    secretKey: str
    secretValue: str


@dataclass
class ListResponse:
    secrets: list[Secret]


class FakeSecretsClient:
    """Minimal stand-in for the Infisical V3RawSecrets client that records calls."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], str] = {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _record(self, op: str, kwargs: dict[str, object]) -> None:
        self.calls.append((op, dict(kwargs)))

    def get_secret_by_name(
        self,
        *,
        secret_name: str,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        **kwargs: object,
    ) -> Secret:
        self._record("get", locals())
        del secret_path, kwargs
        key = (project_slug or "", environment_slug, secret_name)
        value = self.store.get(key)
        if value is None:
            raise _NotFound(secret_name)
        return Secret(secretKey=secret_name, secretValue=value)

    def create_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
        **kwargs: object,
    ) -> Secret:
        self._record("create", locals())
        del secret_path, kwargs
        self.store[(project_slug or "", environment_slug, secret_name)] = secret_value or ""
        return Secret(secretKey=secret_name, secretValue=secret_value or "")

    def update_secret_by_name(
        self,
        *,
        current_secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
        **kwargs: object,
    ) -> Secret:
        self._record("update", locals())
        del secret_path, kwargs
        self.store[(project_slug or "", environment_slug, current_secret_name)] = (
            secret_value or ""
        )
        return Secret(secretKey=current_secret_name, secretValue=secret_value or "")

    def delete_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        **kwargs: object,
    ) -> Secret:
        self._record("delete", locals())
        del secret_path, kwargs
        del self.store[(project_slug or "", environment_slug, secret_name)]
        return Secret(secretKey=secret_name, secretValue="")

    def list_secrets(
        self,
        *,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        **kwargs: object,
    ) -> ListResponse:
        self._record("list", locals())
        del secret_path, kwargs
        secrets = [
            Secret(secretKey=key, secretValue=value)
            for (project, env, key), value in self.store.items()
            if project == (project_slug or "") and env == environment_slug
        ]
        return ListResponse(secrets=secrets)


class _NotFound(APIError):
    """Raised by FakeSecretsClient for a missing secret (real SDK error type)."""

    def __init__(self, secret_name: str) -> None:
        super().__init__(f"secret not found: {secret_name}", 404, {})


class FakeInfisicalClient:
    """Stand-in for InfisicalSDKClient exposing a fake ``secrets`` resource."""

    def __init__(self) -> None:
        self.secrets: FakeSecretsClient = FakeSecretsClient()


def test_local_roundtrip_set_then_get() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    store.set("kalshi", "api_key", "sk-live-123", namespace="global")

    assert store.get("kalshi", "api_key", namespace="global") == "sk-live-123"


def test_local_get_missing_key_returns_none() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    assert store.get("kalshi", "api_key", namespace="global") is None


def test_local_delete_missing_key_raises() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    with pytest.raises(SecretNotFoundError):
        store.delete("kalshi", "api_key", namespace="global")


def test_local_delete_existing_key_removes_it() -> None:
    local = FakeLocalStore()
    store = SecretsStore(local_store=local)
    store.set("kalshi", "api_key", "sk-live-123", namespace="global")

    store.delete("kalshi", "api_key", namespace="global")

    assert store.get("kalshi", "api_key", namespace="global") is None


def test_local_get_namespace_flattens_service_keys() -> None:
    local = FakeLocalStore()
    store = SecretsStore(local_store=local)
    store.set("kalshi", "api_key", "sk-live-123", namespace="global")
    store.set("kalshi", "private_key_pem", "PEM", namespace="global")
    store.set("voyage", "api_key", "v-k", namespace="global")

    assert store.get_namespace("global") == {
        "kalshi_api_key": "sk-live-123",
        "kalshi_private_key_pem": "PEM",
        "voyage_api_key": "v-k",
    }


def test_local_namespaces_are_isolated() -> None:
    local = FakeLocalStore()
    store = SecretsStore(local_store=local)
    store.set("kalshi", "api_key", "global-key", namespace="global")
    store.set("sysadmin", "token", "agent-token", namespace="tokens")

    assert store.get("kalshi", "api_key", namespace="global") == "global-key"
    assert store.get("sysadmin", "token", namespace="tokens") == "agent-token"
    assert store.get("kalshi", "api_key", namespace="tokens") is None
    assert store.get("sysadmin", "token", namespace="global") is None


def test_infisical_roundtrip_set_then_get() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)

    store.set("kalshi", "api_key", "sk-live-123", namespace="global")

    assert store.get("kalshi", "api_key", namespace="global") == "sk-live-123"


def test_infisical_get_missing_key_returns_none() -> None:
    store = SecretsStore(infisical_client=FakeInfisicalClient())

    assert store.get("kalshi", "api_key", namespace="global") is None


def test_infisical_delete_missing_key_raises() -> None:
    store = SecretsStore(infisical_client=FakeInfisicalClient())

    with pytest.raises(SecretNotFoundError):
        store.delete("kalshi", "api_key", namespace="global")


def test_infisical_get_namespace() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)
    store.set("kalshi", "api_key", "sk-live-123", namespace="global")
    store.set("voyage", "api_key", "v-k", namespace="global")

    assert store.get_namespace("global") == {
        "kalshi_api_key": "sk-live-123",
        "voyage_api_key": "v-k",
    }


def test_infisical_global_namespace_maps_to_traderbot_prod() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)

    store.set("kalshi", "api_key", "sk-live-123", namespace="global")

    create_call = next(c for c in client.secrets.calls if c[0] == "create")
    kwargs = create_call[1]
    assert kwargs["project_slug"] == "TraderBot"
    assert kwargs["environment_slug"] == "prod"


def test_infisical_tokens_namespace_maps_to_tokens_project() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)

    store.set("sysadmin", "token", "agent-token", namespace="tokens")

    create_call = next(c for c in client.secrets.calls if c[0] == "create")
    kwargs = create_call[1]
    assert kwargs["project_slug"] == "TraderBot Agent Tokens"
    assert kwargs["environment_slug"] == "prod"


def test_infisical_composite_key_names() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)

    store.set("kalshi", "api_key", "sk-live-123", namespace="global")

    create_call = next(c for c in client.secrets.calls if c[0] == "create")
    assert create_call[1]["secret_name"] == "kalshi_api_key"


def test_infisical_set_updates_existing_secret() -> None:
    client = FakeInfisicalClient()
    store = SecretsStore(infisical_client=client)
    store.set("kalshi", "api_key", "first", namespace="global")

    store.set("kalshi", "api_key", "second", namespace="global")

    op_names = [c[0] for c in client.secrets.calls]
    assert op_names == ["get", "create", "get", "update"]
    assert store.get("kalshi", "api_key", namespace="global") == "second"


def test_infisical_takes_precedence_over_local() -> None:
    client = FakeInfisicalClient()
    local = FakeLocalStore()
    store = SecretsStore(infisical_client=client, local_store=local)
    local.set(service="kalshi", key="api_key", value="local-value", namespace="global")

    store.set("kalshi", "api_key", "infisical-value", namespace="global")

    assert store.get("kalshi", "api_key", namespace="global") == "infisical-value"


def test_unknown_namespace_raises_key_error() -> None:
    store = SecretsStore(infisical_client=FakeInfisicalClient())

    with pytest.raises(KeyError, match="Unknown secrets namespace"):
        _ = store.get("kalshi", "api_key", namespace="nope")


def test_no_backend_configured_raises() -> None:
    store = SecretsStore()

    with pytest.raises(RuntimeError, match="No local secrets store configured"):
        _ = store.get("kalshi", "api_key", namespace="global")


def test_secret_not_found_error_is_key_error() -> None:
    error = SecretNotFoundError(service="kalshi", key="api_key", namespace="global")

    assert isinstance(error, KeyError)
    assert "kalshi" in str(error)
    assert "api_key" in str(error)
    assert "global" in str(error)
