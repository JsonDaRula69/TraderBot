"""Tests for SecretsResolver + TokenStoreAdapter (DD-037, Phase 1.5).

The Infisical client is always mocked/faked — no real Infisical is required.
The suite covers: adapter translation between the TokenStore ABC and
SecretsStore, resolver construction (credentials present / absent), the lazy
install of the adapter on first real-auth call, suspended-profile short-
circuiting, and preservation of the existing set_store() test seam.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.mcp.resolver import _SUSPENDED_PROFILES, resolve_token_adapter
from traderbot.profiles.tokens import LocalTokenStore, TokenStore, get_store, set_store
from traderbot.secrets.adapter import TokenStoreAdapter
from traderbot.secrets.resolver import SecretsResolver
from traderbot.secrets.store import SecretsStore


class _FakeLocalStore:
    """Dict-backed stand-in for LocalEncryptedStore (same shape as test_secrets_store)."""

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


class _FakeUniversalAuth:
    def __init__(self) -> None:
        self.login_calls: list[tuple[str, str]] = []

    def login(self, client_id: str, client_secret: str) -> None:
        self.login_calls.append((client_id, client_secret))


class _FakeAuth:
    def __init__(self) -> None:
        self.universal_auth: _FakeUniversalAuth = _FakeUniversalAuth()


class _FakeInfisicalClient:
    """Stand-in for InfisicalSDKClient: exposes a fake ``auth`` resource."""

    def __init__(self) -> None:
        self.auth: _FakeAuth = _FakeAuth()


def _credentials_at(home: Path) -> Path:
    """Write an infisical-credentials.json under ``home`` and return its path."""
    creds_dir = home / ".traderbot"
    creds_dir.mkdir(parents=True)
    creds_path = creds_dir / "infisical-credentials.json"
    _ = creds_path.write_text(
        '{"host": "http://localhost:8080", '
        + '"machineIdentity": {"clientId": "cid-1", "clientSecret": "cs-1"}}'
    )
    return creds_path


class TestTokenStoreAdapter:
    def test_implements_token_store_interface(self) -> None:
        adapter = TokenStoreAdapter(SecretsStore(local_store=_FakeLocalStore()))

        assert isinstance(adapter, TokenStore)

    def test_store_and_resolve_roundtrip(self) -> None:
        adapter = TokenStoreAdapter(SecretsStore(local_store=_FakeLocalStore()))

        adapter.store_token("weather", "weather-agent", "adapter-token")

        assert adapter.resolve_token("adapter-token") == ("weather", "weather-agent")

    def test_unknown_token_resolves_none(self) -> None:
        adapter = TokenStoreAdapter(SecretsStore(local_store=_FakeLocalStore()))

        assert adapter.resolve_token("nope") is None

    def test_rotate_replaces_token_and_returns_new_one(self) -> None:
        adapter = TokenStoreAdapter(SecretsStore(local_store=_FakeLocalStore()))
        adapter.store_token("weather", "weather-agent", "old-token")

        new_token = adapter.rotate_token("weather", "weather-agent")

        assert new_token != "old-token"
        assert new_token
        assert adapter.resolve_token("old-token") is None
        assert adapter.resolve_token(new_token) == ("weather", "weather-agent")

    def test_list_tokens_translates_five_field_entries(self) -> None:
        store = SecretsStore(local_store=_FakeLocalStore())
        store.store_profile_token(
            agent_id="weather-agent",
            token="tok-1",
            profile="weather",
            categories=["crypto"],
            permissions=["traderbot__*"],
        )
        adapter = TokenStoreAdapter(store)

        entries = adapter.list_tokens()

        assert entries == [{"token": "tok-1", "profile": "weather", "agent_id": "weather-agent"}]


class TestSecretsResolver:
    def test_no_credentials_falls_back_to_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        creds_path = tmp_path / ".traderbot" / "infisical-credentials.json"
        assert creds_path.exists() is False
        try:
            _ = SecretsResolver()

            assert isinstance(get_store(), TokenStoreAdapter)
        finally:
            set_store(None)

    def test_with_credentials_constructs_infisical_client(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _ = _credentials_at(tmp_path)

        from infisical_sdk import InfisicalSDKClient

        created: list[_FakeInfisicalClient] = []

        def fake_init(
            self: object, host: str, token: str | None = None, cache_ttl: int = 60
        ) -> None:
            del token, cache_ttl
            assert host == "http://localhost:8080"
            fake = _FakeInfisicalClient()
            created.append(fake)
            setattr(self, "auth", fake.auth)

        monkeypatch.setattr(InfisicalSDKClient, "__init__", fake_init)
        try:
            _ = SecretsResolver()

            assert len(created) == 1
            assert created[0].auth.universal_auth.login_calls == [("cid-1", "cs-1")]
            assert isinstance(get_store(), TokenStoreAdapter)
        finally:
            set_store(None)


class TestSuspendedProfiles:
    @pytest.fixture(autouse=True)
    def _env_real_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")

    def test_suspended_profile_returns_none_none(
        self, secrets_resolver_reset: None, real_auth: LocalTokenStore
    ) -> None:
        real_auth.store_token("weather", "weather-agent", "suspend-me")
        _SUSPENDED_PROFILES.add("weather")

        assert resolve_token_adapter("suspend-me") == (None, None)

    def test_suspended_set_survives_across_calls(
        self, secrets_resolver_reset: None, real_auth: LocalTokenStore
    ) -> None:
        real_auth.store_token("weather", "weather-agent", "survive-token")
        _SUSPENDED_PROFILES.add("weather")

        _ = resolve_token_adapter("survive-token")
        result = resolve_token_adapter("survive-token")

        assert result == (None, None)

    def test_nonsuspended_profile_resolves(
        self, secrets_resolver_reset: None, real_auth: LocalTokenStore
    ) -> None:
        real_auth.store_token("dev-liaison", "dev-agent", "fine-token")

        profile, agent_id = resolve_token_adapter("fine-token")

        assert profile is not None
        assert profile.name == "dev-liaison"
        assert agent_id == "dev-agent"

    def test_lazy_init_skips_injected_store(
        self, secrets_resolver_reset: None, real_auth: LocalTokenStore
    ) -> None:
        assert isinstance(get_store(), LocalTokenStore)

        _ = resolve_token_adapter("unused-token")

        assert isinstance(get_store(), LocalTokenStore)
        assert not isinstance(get_store(), TokenStoreAdapter)

    def test_lazy_init_installs_adapter_on_default_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        default_dir = tmp_path / ".traderbot"
        default_dir.mkdir(parents=True)
        set_store(LocalTokenStore(base_path=default_dir))
        try:
            _ = resolve_token_adapter("lazy-token")

            assert isinstance(get_store(), TokenStoreAdapter)
        finally:
            set_store(None)
