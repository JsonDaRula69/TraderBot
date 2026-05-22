"""Unit tests for keyring credential storage and .env fallback."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from traderbot.auth import (
    AuthManager,
    CredentialResult,
    _env_file_get_value,
    _env_file_set_value,
    _is_keyring_available,
    _keyring_service_name,
    _keyring_username,
)


class TestKeyringHelpers:
    def test_keyring_service_name(self) -> None:
        assert _keyring_service_name("kalshi") == "traderbot.kalshi"

    def test_keyring_username(self) -> None:
        assert _keyring_username("api_key") == "api_key"

    @patch("traderbot.auth.keyring", create=True)
    def test_is_keyring_available_with_backend(self, mock_keyring: MagicMock) -> None:
        mock_backend = MagicMock()
        mock_backend.__module__ = "keyring.backends.macOS"
        mock_keyring.get_keyring.return_value = mock_backend
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _is_keyring_available() is True

    def test_is_keyring_available_no_keyring(self) -> None:
        with patch("traderbot.auth.keyring", side_effect=ImportError, create=True):
            with patch.dict("sys.modules", {}, clear=False):
                result = _is_keyring_available()
                assert result is False


class TestAuthManagerKeyringRead:
    def setup_method(self) -> None:
        self.mgr = AuthManager()

    @patch.object(AuthManager, "_get_from_keyring", return_value="keyring-value")
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_get_credential_keyring_first(self, mock_avail: MagicMock, mock_kr: MagicMock) -> None:
        result = self.mgr.get_credential("kalshi", "api_key")
        assert result is not None
        assert result.source == "keyring"
        assert result.value.get_secret_value() == "keyring-value"
        mock_kr.assert_called_once_with("kalshi", "api_key")

    @patch.object(AuthManager, "_get_from_keyring", return_value=None)
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_get_credential_env_fallback(self, mock_avail: MagicMock, mock_kr: MagicMock) -> None:
        with patch.dict(os.environ, {"KALSHI_API_KEY": "env-value"}):
            result = self.mgr.get_credential("kalshi", "api_key")
            assert result is not None
            assert result.source == "env"
            assert result.value.get_secret_value() == "env-value"

    @patch("traderbot.auth._is_keyring_available", return_value=False)
    def test_get_credential_env_only_when_no_keyring(self, mock_avail: MagicMock) -> None:
        with patch.dict(os.environ, {"KALSHI_API_KEY": "env-value"}):
            result = self.mgr.get_credential("kalshi", "api_key")
            assert result is not None
            assert result.source == "env"

    @patch.object(AuthManager, "_get_from_keyring", return_value=None)
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_get_credential_not_found(self, mock_avail: MagicMock, mock_kr: MagicMock) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = self.mgr.get_credential("kalshi", "api_key")
            assert result is None


class TestAuthManagerKeyringWrite:
    def setup_method(self) -> None:
        self.mgr = AuthManager()

    @patch.object(AuthManager, "_set_in_keyring")
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_set_credential_keyring(self, mock_avail: MagicMock, mock_kr: MagicMock) -> None:
        result = self.mgr.set_credential("kalshi", "api_key", "test-val")
        assert result == "keyring"
        mock_kr.assert_called_once_with("kalshi", "api_key", "test-val")

    @patch("traderbot.auth._is_keyring_available", return_value=False)
    def test_set_credential_env_fallback(self, mock_avail: MagicMock, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch as upatch

        env_dir = Path(tempfile.mkdtemp())
        env_path = env_dir / ".env"
        with upatch("traderbot.paths.ensure_data_dir", return_value=env_dir):
            result = self.mgr.set_credential("kalshi", "api_key", "test-val")
        assert result == "env"

    @patch.object(AuthManager, "_delete_from_keyring", return_value=True)
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_delete_credential_keyring(self, mock_avail: MagicMock, mock_del: MagicMock) -> None:
        assert self.mgr.delete_credential("kalshi", "api_key") is True

    @patch("traderbot.auth._is_keyring_available", return_value=False)
    def test_delete_credential_no_keyring(self, mock_avail: MagicMock) -> None:
        assert self.mgr.delete_credential("kalshi", "api_key") is False


class TestAuthManagerMigration:
    def setup_method(self) -> None:
        self.mgr = AuthManager()

    @patch.object(AuthManager, "_get_from_keyring", return_value=None)
    @patch.object(AuthManager, "_set_in_keyring")
    @patch.object(AuthManager, "_get_from_env_only", return_value="env-value")
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_migrate_migrates_from_env(
        self, mock_avail: MagicMock, mock_env: MagicMock, mock_set: MagicMock, mock_get_kr: MagicMock
    ) -> None:
        result = self.mgr.migrate_to_keyring("kalshi")
        assert result["migrated"] >= 1

    @patch.object(AuthManager, "_get_from_keyring", return_value="already-there")
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_migrate_skips_existing_keyring(self, mock_avail: MagicMock, mock_kr: MagicMock) -> None:
        result = self.mgr.migrate_to_keyring("kalshi")
        assert result["skipped"] >= 1

    @patch("traderbot.auth._is_keyring_available", return_value=False)
    def test_migrate_skips_when_no_keyring(self, mock_avail: MagicMock) -> None:
        result = self.mgr.migrate_to_keyring("kalshi")
        assert result == {"migrated": 0, "skipped": 0}


class TestAuthManagerListServices:
    def setup_method(self) -> None:
        self.mgr = AuthManager()

    @patch.object(AuthManager, "_keyring_has", return_value=True)
    @patch("traderbot.auth._is_keyring_available", return_value=True)
    def test_list_services_includes_keyring(self, mock_avail: MagicMock, mock_has: MagicMock) -> None:
        services = self.mgr.list_services()
        names = [s.name for s in services]
        assert "kalshi" in names


class TestEnvFileHelpers:
    def test_env_file_get_value(self, tmp_path: object) -> None:
        from pathlib import Path

        env_path = Path(str(tmp_path)) / ".env"
        env_path.write_text("MY_KEY=hello\nOTHER=x\n")
        assert _env_file_get_value(env_path, "MY_KEY") == "hello"
        assert _env_file_get_value(env_path, "MISSING") is None

    def test_env_file_get_value_strips_quotes(self, tmp_path: object) -> None:
        from pathlib import Path

        env_path = Path(str(tmp_path)) / ".env"
        env_path.write_text('KEY="quoted"\n')
        assert _env_file_get_value(env_path, "KEY") == "quoted"

    def test_env_file_set_value_new(self, tmp_path: object) -> None:
        from pathlib import Path

        env_path = Path(str(tmp_path)) / ".env"
        _env_file_set_value(env_path, "NEW_KEY", "new_val")
        assert _env_file_get_value(env_path, "NEW_KEY") == "new_val"

    def test_env_file_set_value_update(self, tmp_path: object) -> None:
        from pathlib import Path

        env_path = Path(str(tmp_path)) / ".env"
        env_path.write_text("KEY=old\n")
        _env_file_set_value(env_path, "KEY", "updated")
        assert _env_file_get_value(env_path, "KEY") == "updated"


class TestCredentialResult:
    def test_keyring_source(self) -> None:
        r = CredentialResult(service="kalshi", key="api_key", value=SecretStr("v"), source="keyring")
        assert r.source == "keyring"

    def test_env_source(self) -> None:
        r = CredentialResult(service="kalshi", key="api_key", value=SecretStr("v"), source="env")
        assert r.source == "env"

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(Exception):
            CredentialResult(service="kalshi", key="api_key", value=SecretStr("v"), source="file")