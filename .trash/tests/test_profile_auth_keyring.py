"""Unit tests for ProfileAuthStore keyring integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from traderbot.profiles.auth import ProfileAuthStore, _profile_keyring_service


class FakeProfile:
    def __init__(self, name: str) -> None:
        self.name = name


class TestProfileKeyringService:
    def test_profile_keyring_service_name(self) -> None:
        assert _profile_keyring_service("weather-agent", "kalshi") == "traderbot.profiles.weather-agent.kalshi"


class TestProfileAuthStoreKeyringRead:
    def setup_method(self) -> None:
        self.profile = FakeProfile("test-profile")
        self.store = ProfileAuthStore(self.profile)

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=True)
    def test_get_kalshi_from_keyring(self, mock_avail: MagicMock) -> None:
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = lambda svc, key: {
            ("traderbot.profiles.test-profile.kalshi", "api_key"): "profile-key",
            ("traderbot.profiles.test-profile.kalshi", "private_key_pem"): "profile-pem",
        }.get((svc, key))

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = self.store.get_credentials("kalshi")
        assert result is not None
        assert result == ("profile-key", "profile-pem")

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=False)
    def test_get_kalshi_env_fallback(self, mock_avail: MagicMock) -> None:
        import os

        with patch.dict(
            os.environ,
            {
                "KALSHI_API_KEY_PROFILE_TEST_PROFILE": "env-key",
                "KALSHI_PRIVATE_KEY_PEM_PROFILE_TEST_PROFILE": "env-pem",
            },
        ):
            result = self.store.get_credentials("kalshi")
        assert result is not None
        assert result == ("env-key", "env-pem")

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=True)
    def test_get_generic_from_keyring(self, mock_avail: MagicMock) -> None:
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "generic-key"

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = self.store.get_credentials("coingecko")
        assert result is not None
        assert result == ("generic-key", "")


class TestProfileAuthStoreKeyringWrite:
    def setup_method(self) -> None:
        self.profile = FakeProfile("test-profile")
        self.store = ProfileAuthStore(self.profile)

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=True)
    def test_set_credentials_in_keyring(self, mock_avail: MagicMock) -> None:
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = self.store.set_credentials("kalshi", "api_key", "new-key")
        assert result is True
        mock_keyring.set_password.assert_called_once()

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=False)
    def test_set_credentials_no_keyring(self, mock_avail: MagicMock) -> None:
        result = self.store.set_credentials("kalshi", "api_key", "new-key")
        assert result is False

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=True)
    def test_delete_credentials_from_keyring(self, mock_avail: MagicMock) -> None:
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = self.store.delete_credentials("kalshi", "api_key")
        assert result is True

    @patch("traderbot.profiles.auth._is_keyring_available", return_value=True)
    def test_delete_credentials_not_found(self, mock_avail: MagicMock) -> None:
        import keyring as real_keyring

        mock_keyring = MagicMock()
        mock_keyring.delete_password.side_effect = real_keyring.errors.PasswordDeleteError()
        mock_keyring.errors = real_keyring.errors
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = self.store.delete_credentials("kalshi", "api_key")
        assert result is False
