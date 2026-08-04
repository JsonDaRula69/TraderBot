"""Tests for the SecretsStore profile-token operations (DD-037 §4).

Profile tokens live in ``namespace="tokens"`` as 5-field JSON documents
(``token``, ``profile``, ``agent_id``, ``categories``, ``permissions``) under
the secret name ``f"{agent_id}_token"``. The store is exercised through both
backends: the recorded-call Infisical fake (from ``test_secrets_store``) and
the dict-backed local fake.

Run with: pytest tests/test_secrets_store_tokens.py -v
"""

from __future__ import annotations

import pytest

from tests.test_secrets_store import FakeInfisicalClient, FakeLocalStore
from traderbot.secrets import SecretsStore
from traderbot.secrets.store import ProfileTokenPayload

CATEGORIES = ["weather"]
PERMISSIONS = ["market_edge"]


def _store(client: FakeInfisicalClient | None = None) -> SecretsStore:
    return SecretsStore(infisical_client=client or FakeInfisicalClient())


def test_store_and_get_roundtrip_local() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    entry = store.get_profile_token("weather")
    assert entry == {
        "token": "tok-1",
        "profile": "weather-profile",
        "agent_id": "weather",
        "categories": ["weather"],
        "permissions": ["market_edge"],
    }


def test_store_and_get_roundtrip_infisical() -> None:
    client = FakeInfisicalClient()
    store = _store(client)

    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    assert store.get_profile_token("weather") == {
        "token": "tok-1",
        "profile": "weather-profile",
        "agent_id": "weather",
        "categories": ["weather"],
        "permissions": ["market_edge"],
    }


def test_get_profile_token_is_direct_lookup_not_list_scan() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    client.secrets.calls.clear()

    _ = store.get_profile_token("weather")

    assert [name for name, _ in client.secrets.calls] == ["get"]
    assert client.secrets.calls[0][1]["secret_name"] == "weather_token"


def test_get_profile_token_unknown_agent_returns_none() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    assert store.get_profile_token("sysadmin") is None


def test_resolve_profile_token_matches_stored_token() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-weather",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    store.store_profile_token(
        agent_id="sysadmin",
        token="tok-sys",
        profile="sysadmin-profile",
        categories=["all"],
        permissions=["all"],
    )

    assert store.resolve_profile_token("tok-weather") == ("weather-profile", "weather")


def test_resolve_profile_token_unknown_token_returns_none() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-weather",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    assert store.resolve_profile_token("no-such-token") is None


def test_resolve_profile_token_uses_list_scan() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-weather",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    client.secrets.calls.clear()

    _ = store.resolve_profile_token("tok-weather")

    assert [name for name, _ in client.secrets.calls] == ["list"]


def test_store_then_store_is_create_or_update() -> None:
    client = FakeInfisicalClient()
    store = _store(client)

    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    store.store_profile_token(
        agent_id="weather",
        token="tok-2",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    assert [name for name, _ in client.secrets.calls] == ["get", "create", "get", "update"]
    entry = store.get_profile_token("weather")
    assert entry is not None
    assert entry["token"] == "tok-2"


def test_stored_value_is_five_field_json_document() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    create_call = next(c for c in client.secrets.calls if c[0] == "create")
    assert create_call[1]["secret_name"] == "weather_token"
    raw_value = create_call[1]["secret_value"]
    assert isinstance(raw_value, str)
    payload = ProfileTokenPayload.model_validate_json(raw_value)
    assert payload.model_dump() == {
        "token": "tok-1",
        "profile": "weather-profile",
        "agent_id": "weather",
        "categories": ["weather"],
        "permissions": ["market_edge"],
    }
    assert payload.model_fields_set == {
        "token",
        "profile",
        "agent_id",
        "categories",
        "permissions",
    }


def test_tokens_namespace_maps_to_agent_tokens_project() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    create_call = next(c for c in client.secrets.calls if c[0] == "create")
    assert create_call[1]["project_slug"] == "traderbot-agent-tokens"
    assert create_call[1]["environment_slug"] == "prod"


def test_corrupt_token_value_parses_to_none() -> None:
    store = SecretsStore(local_store=FakeLocalStore())
    store.set("weather", "token", "not-json", namespace="tokens")

    assert store.get_profile_token("weather") is None


def test_rotate_updates_token_keeping_other_fields() -> None:
    store = SecretsStore(local_store=FakeLocalStore())
    store.store_profile_token(
        agent_id="weather",
        token="tok-old",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    store.rotate_profile_token("weather", "tok-new")

    entry = store.get_profile_token("weather")
    assert entry is not None
    assert entry["token"] == "tok-new"
    assert entry["profile"] == "weather-profile"
    assert entry["categories"] == CATEGORIES
    assert entry["permissions"] == PERMISSIONS


def test_rotate_uses_update_not_create() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    store.store_profile_token(
        agent_id="weather",
        token="tok-old",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    client.secrets.calls.clear()

    store.rotate_profile_token("weather", "tok-new")

    assert [name for name, _ in client.secrets.calls] == ["get", "get", "update"]


def test_rotate_unknown_agent_raises_key_error() -> None:
    store = SecretsStore(local_store=FakeLocalStore())

    with pytest.raises(KeyError, match="No profile token stored for agent_id='nope'"):
        store.rotate_profile_token("nope", "tok-new")


def test_list_profile_tokens_returns_all_entries() -> None:
    store = SecretsStore(local_store=FakeLocalStore())
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    store.store_profile_token(
        agent_id="sysadmin",
        token="tok-2",
        profile="sysadmin-profile",
        categories=["all"],
        permissions=["all"],
    )

    tokens = store.list_profile_tokens()

    assert len(tokens) == 2
    assert {entry["agent_id"] for entry in tokens} == {"weather", "sysadmin"}


def test_list_profile_tokens_skips_non_token_and_invalid_entries() -> None:
    local = FakeLocalStore()
    store = SecretsStore(local_store=local)
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )
    # A non-token secret in the tokens namespace (not agent_id_token named).
    store.set("misc", "shared", "value", namespace="tokens")
    # A token-named secret whose value is not a valid 5-field document.
    store.set("broken", "token", "not-json", namespace="tokens")

    tokens = store.list_profile_tokens()

    assert len(tokens) == 1
    assert tokens[0]["agent_id"] == "weather"


def test_local_get_uses_agent_id_token_service_key() -> None:
    local = FakeLocalStore()
    store = SecretsStore(local_store=local)
    store.store_profile_token(
        agent_id="weather",
        token="tok-1",
        profile="weather-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )

    assert local.data["tokens"]["weather"]["token"] is not None
