"""Tests for auth module with mocked keyring backend."""

from __future__ import annotations

import os

import keyring.backend
import pytest
from pydantic import SecretStr

from traderbot.auth import (
    AuthManager,
    CredentialResult,
    KeyringUnavailableError,
    ServiceInfo,
    get_credential,
)


class FakeKeyring(keyring.backend.KeyringBackend):
    """In-memory keyring for testing."""

    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, servicename: str, username: str, password: str) -> None:
        self._store[(servicename, username)] = password

    def get_password(self, servicename: str, username: str) -> str | None:
        return self._store.get((servicename, username))

    def delete_password(self, servicename: str, username: str) -> None:
        self._store.pop((servicename, username), None)


class FailKeyring(keyring.backend.KeyringBackend):
    """Simulates an unavailable keyring backend."""

    priority = 1

    def set_password(self, servicename: str, username: str, password: str) -> None:
        raise RuntimeError("Keyring unavailable")

    def get_password(self, servicename: str, username: str) -> str | None:
        raise RuntimeError("Keyring unavailable")

    def delete_password(self, servicename: str, username: str) -> None:
        raise RuntimeError("Keyring unavailable")


@pytest.fixture
def fake_keyring() -> FakeKeyring:
    return FakeKeyring()


@pytest.fixture
def auth_manager(fake_keyring: FakeKeyring) -> AuthManager:
    return AuthManager(keyring_module=fake_keyring, keyring_available=True)


class TestAuthManagerSetAndGet:
    def test_set_and_get_credential(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "api_key", "test-key-123")
        result = auth_manager.get_credential("kalshi", "api_key")
        assert isinstance(result, CredentialResult)
        assert result.value.get_secret_value() == "test-key-123"
        assert result.source == "keyring"
        assert result.service == "kalshi"
        assert result.key == "api_key"

    def test_credential_is_secretstr(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "private_key_pem", "super-secret")
        result = auth_manager.get_credential("kalshi", "private_key_pem")
        assert isinstance(result, CredentialResult)
        assert isinstance(result.value, SecretStr)
        assert repr(result.value) != "super-secret"

    def test_service_namespaced(self, fake_keyring: FakeKeyring) -> None:
        mgr = AuthManager(keyring_module=fake_keyring, keyring_available=True)
        mgr.set_credential("kalshi", "api_key", "val")
        assert fake_keyring._store[("traderbot.kalshi", "api_key")] == "val"

    def test_get_nonexistent_credential(self, auth_manager: AuthManager) -> None:
        result = auth_manager.get_credential("kalshi", "nonexistent")
        assert result is None


class TestAuthManagerDelete:
    def test_delete_credential(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "api_key", "to-delete")
        deleted = auth_manager.delete_credential("kalshi", "api_key")
        assert deleted is True
        result = auth_manager.get_credential("kalshi", "api_key")
        assert result is None

    def test_delete_nonexistent_returns_false(self, auth_manager: AuthManager) -> None:
        deleted = auth_manager.delete_credential("kalshi", "nonexistent")
        assert deleted is False


class TestAuthManagerListServices:
    def test_list_services_with_keyring(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "api_key", "k1")
        auth_manager.set_credential("kalshi", "private_key_pem", "k2")
        services = auth_manager.list_services()
        kalshi = next(s for s in services if s.name == "kalshi")
        assert "api_key" in kalshi.keys
        assert "private_key_pem" in kalshi.keys

    def test_list_services_empty(self, auth_manager: AuthManager) -> None:
        services = auth_manager.list_services()
        assert len(services) == 0 or all(len(s.keys) == 0 for s in services)

    def test_list_never_shows_values(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "api_key", "secret-value")
        services = auth_manager.list_services()
        for s in services:
            for k in s.keys:
                assert isinstance(k, str)
                assert k != "secret-value"


class TestAuthManagerEnvFallback:
    def test_fallback_to_env_when_keyring_empty(
        self, fake_keyring: FakeKeyring
    ) -> None:
        mgr = AuthManager(keyring_module=fake_keyring, keyring_available=True)
        os.environ["KALSHI_API_KEY"] = "env-key-123"
        try:
            result = mgr.get_credential("kalshi", "api_key")
            assert isinstance(result, CredentialResult)
            assert result.value.get_secret_value() == "env-key-123"
            assert result.source == "env"
        finally:
            os.environ.pop("KALSHI_API_KEY", None)

    def test_keyring_takes_priority_over_env(
        self, auth_manager: AuthManager
    ) -> None:
        auth_manager.set_credential("kalshi", "api_key", "from-keyring")
        os.environ["KALSHI_API_KEY"] = "from-env"
        try:
            result = auth_manager.get_credential("kalshi", "api_key")
            assert isinstance(result, CredentialResult)
            assert result.value.get_secret_value() == "from-keyring"
            assert result.source == "keyring"
        finally:
            os.environ.pop("KALSHI_API_KEY", None)

    def test_fail_keyring_falls_to_env(self) -> None:
        mgr = AuthManager(keyring_available=False)
        os.environ["KALSHI_API_KEY"] = "fallback-value"
        try:
            result = mgr.get_credential("kalshi", "api_key")
            assert isinstance(result, CredentialResult)
            assert result.value.get_secret_value() == "fallback-value"
            assert result.source == "env"
        finally:
            os.environ.pop("KALSHI_API_KEY", None)


class TestAuthManagerCheckCredentials:
    def test_check_with_all_present(self, auth_manager: AuthManager) -> None:
        auth_manager.set_credential("kalshi", "api_key", "k1")
        auth_manager.set_credential("kalshi", "private_key_pem", "k2")
        status = auth_manager.check_credentials()
        assert status["kalshi"]["api_key"] is True
        assert status["kalshi"]["private_key_pem"] is True

    def test_check_with_missing(self, auth_manager: AuthManager) -> None:
        status = auth_manager.check_credentials()
        assert status["kalshi"]["api_key"] is False
        assert status["kalshi"]["private_key_pem"] is False


class TestAuthManagerNoKeyring:
    def test_set_credential_raises_when_keyring_unavailable(self) -> None:
        mgr = AuthManager(keyring_available=False)
        with pytest.raises(KeyringUnavailableError):
            mgr.set_credential("kalshi", "api_key", "test")


class TestCredentialResult:
    def test_result_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            CredentialResult(
                service="kalshi", key="api_key", value=SecretStr("val"),
                source="keyring", extra="bad"
            )

    def test_result_source_literal(self) -> None:
        r = CredentialResult(service="s", key="k", value=SecretStr("v"), source="keyring")
        assert r.source == "keyring"
        r2 = CredentialResult(service="s", key="k", value=SecretStr("v"), source="env")
        assert r2.source == "env"

    def test_result_rejects_invalid_source(self) -> None:
        with pytest.raises(Exception):
            CredentialResult(service="s", key="k", value=SecretStr("v"), source="invalid")


class TestServiceInfo:
    def test_service_info_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            ServiceInfo(name="kalshi", keys=["api_key"], extra="bad")


class TestGetCredentialConvenience:
    def test_convenience_get_credential_returns_secretstr(
        self, auth_manager: AuthManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth_manager.set_credential("kalshi", "api_key", "direct-key")
        monkeypatch.setattr("traderbot.auth.AuthManager", lambda **kw: auth_manager)
        result = get_credential("kalshi", "api_key")
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "direct-key"

    def test_convenience_get_credential_returns_none(self) -> None:
        result = get_credential("nonexistent", "missing")
        assert result is None


class TestKeyringKalshiConfig:
    def test_config_resolves_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KALSHI_API_KEY", "env-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PEM", "env-secret")
        from traderbot.kalshi.config import KeyringKalshiConfig
        cfg = KeyringKalshiConfig()
        assert cfg.resolve_api_key() == "env-key"
        assert cfg.resolve_api_secret() is not None

    def test_config_defaults(self) -> None:
        from traderbot.kalshi.config import KeyringKalshiConfig
        cfg = KeyringKalshiConfig()
        assert cfg.demo_mode is False
        assert cfg.base_url == "https://api.elections.kalshi.com/trade-api/v2"

    def test_active_url_demo(self) -> None:
        from traderbot.kalshi.config import KeyringKalshiConfig
        cfg = KeyringKalshiConfig(demo_mode=True)
        assert cfg.active_url == "https://demo-api.elections.kalshi.com/trade-api/v2"

    def test_active_url_prod(self) -> None:
        from traderbot.kalshi.config import KeyringKalshiConfig
        cfg = KeyringKalshiConfig()
        assert cfg.active_url == "https://api.elections.kalshi.com/trade-api/v2"

    def test_config_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            from traderbot.kalshi.config import KeyringKalshiConfig
            KeyringKalshiConfig(extra_field="bad")


class TestEnvMapping:
    def test_kalshi_api_key_env_mapping(self) -> None:
        assert AuthManager._service_key_to_env("kalshi", "api_key") == "KALSHI_API_KEY"

    def test_kalshi_api_secret_env_mapping(self) -> None:
        assert AuthManager._service_key_to_env("kalshi", "private_key_pem") == "KALSHI_PRIVATE_KEY_PEM"

    def test_generic_service_env_mapping(self) -> None:
        assert AuthManager._service_key_to_env("voyage", "api_key") == "VOYAGE_API_KEY"