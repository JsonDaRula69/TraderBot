"""Tests for token staleness detection and env sync."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from traderbot.profiles.tokens import (
    _check_token_expired,
    staleness_warning,
    sync_env_token,
)


@pytest.fixture
def _patch_token_registry(tmp_path):
    """Redirect token registry to a temp directory for isolation."""
    with patch("traderbot.profiles.tokens._TOKENS_FILE", tmp_path / "tokens.enc"), \
         patch("traderbot.profiles.tokens._get_keys_dir", lambda: tmp_path / "keys"):
        (tmp_path / "keys").mkdir(parents=True, exist_ok=True)
        yield


@pytest.fixture
def sample_token_data():
    """Return a valid token entry dict."""
    now = datetime.now(UTC)
    return {
        "token": "abc123token",
        "profile": "test-profile",
        "agent": "test-agent",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }


class TestCheckTokenExpired:
    @pytest.mark.unit
    def test_expired_token_returns_true(self, _patch_token_registry, sample_token_data):
        from traderbot.profiles.tokens import _save_tokens_file

        past = datetime.now(UTC) - timedelta(days=1)
        sample_token_data["expires_at"] = past.isoformat()
        _save_tokens_file([sample_token_data])

        assert _check_token_expired("abc123token") is True

    @pytest.mark.unit
    def test_valid_token_returns_false(self, _patch_token_registry, sample_token_data):
        from traderbot.profiles.tokens import _save_tokens_file

        future = datetime.now(UTC) + timedelta(days=30)
        sample_token_data["expires_at"] = future.isoformat()
        _save_tokens_file([sample_token_data])

        assert _check_token_expired("abc123token") is False

    @pytest.mark.unit
    def test_unknown_token_returns_false(self, _patch_token_registry):
        assert _check_token_expired("nonexistent") is False


class TestStalenessWarning:
    @pytest.mark.unit
    def test_no_token_env_or_file(self, _patch_token_registry):
        with patch.dict(os.environ, {}, clear=True), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=None), \
             patch("traderbot.profiles.runtime._read_env_file_token", return_value=None):
            result = staleness_warning()
        assert result["valid"] is False
        assert result["token_source"] == "none"
        assert result["expired"] is False

    @pytest.mark.unit
    def test_env_token_valid(self, _patch_token_registry):
        with patch.dict(os.environ, {"TRADERBOT_PROFILE_TOKEN": "good-token"}, clear=False), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=("my-profile", "agent-1")):
            result = staleness_warning()
        assert result["valid"] is True
        assert result["token_source"] == "env"
        assert result["profile"] == "my-profile"
        assert result["agent"] == "agent-1"

    @pytest.mark.unit
    def test_env_file_token_invalid(self, _patch_token_registry):
        with patch.dict(os.environ, {}, clear=True), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=None), \
             patch("traderbot.profiles.tokens._check_token_expired", return_value=True), \
             patch("traderbot.profiles.runtime._read_env_file_token", return_value="stale-token"):
            result = staleness_warning()
        assert result["valid"] is False
        assert result["token_source"] == "env_file"
        assert result["expired"] is True

    @pytest.mark.unit
    def test_profile_name_valid_token(self, _patch_token_registry):
        with patch("traderbot.profiles.tokens.get_profile_token", return_value="profile-token"), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=("named-profile", "agent-2")):
            result = staleness_warning(profile_name="named-profile")
        assert result["valid"] is True
        assert result["token_source"] == "registry"
        assert result["profile"] == "named-profile"

    @pytest.mark.unit
    def test_profile_name_no_token(self, _patch_token_registry):
        with patch("traderbot.profiles.tokens.get_profile_token", return_value=None):
            result = staleness_warning(profile_name="missing-profile")
        assert result["valid"] is False
        assert result["token_source"] == "none"


class TestSyncEnvToken:
    @pytest.mark.unit
    def test_sync_valid_token(self, _patch_token_registry):
        with patch("traderbot.profiles.tokens.get_profile_token", return_value="sync-token"), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=("my-profile", "agent-1")), \
             patch("traderbot.profiles.registry.ProfileRegistry") as mock_reg, \
             patch("traderbot.cli.helpers._write_token_to_env") as mock_write:
            mock_reg.return_value.profile_exists.return_value = True
            token = sync_env_token("my-profile")
            assert token == "sync-token"
            mock_write.assert_called_once_with("sync-token")

    @pytest.mark.unit
    def test_sync_profile_not_found(self, _patch_token_registry):
        with patch("traderbot.profiles.registry.ProfileRegistry") as mock_reg, \
             patch("traderbot.profiles.tokens.get_profile_token"), \
             patch("traderbot.profiles.tokens.resolve_token"):
            mock_reg.return_value.profile_exists.return_value = False
            token = sync_env_token("nonexistent")
            assert token is None

    @pytest.mark.unit
    def test_sync_invalid_token(self, _patch_token_registry):
        with patch("traderbot.profiles.tokens.get_profile_token", return_value="bad-token"), \
             patch("traderbot.profiles.tokens.resolve_token", return_value=None), \
             patch("traderbot.profiles.registry.ProfileRegistry") as mock_reg:
            mock_reg.return_value.profile_exists.return_value = True
            token = sync_env_token("my-profile")
            assert token is None

    @pytest.mark.unit
    def test_sync_no_token_assigned(self, _patch_token_registry):
        with patch("traderbot.profiles.tokens.get_profile_token", return_value=None), \
             patch("traderbot.profiles.registry.ProfileRegistry") as mock_reg:
            mock_reg.return_value.profile_exists.return_value = True
            token = sync_env_token("my-profile")
            assert token is None