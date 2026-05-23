"""Tests for traderbot.master_password — PBKDF2-HMAC-SHA256 password gate."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from traderbot.master_password import (
    SESSION_TOKEN_ENV,
    _constant_time_compare,
    _derive_key,
    _make_session_token,
    _verify_session_token,
    authenticate,
    change_master_password,
    clear_session,
    is_setup,
    require_auth,
    session_active,
    setup_master_password,
)


class TestDeriveKey:
    def test_derives_consistent_key(self) -> None:
        salt = b"a" * 32
        k1 = _derive_key("password123", salt, iterations=1000)
        k2 = _derive_key("password123", salt, iterations=1000)
        assert k1 == k2

    def test_different_password_yields_different_key(self) -> None:
        salt = b"a" * 32
        k1 = _derive_key("passwordA", salt, iterations=1000)
        k2 = _derive_key("passwordB", salt, iterations=1000)
        assert k1 != k2

    def test_different_salt_yields_different_key(self) -> None:
        k1 = _derive_key("password123", b"a" * 32, iterations=1000)
        k2 = _derive_key("password123", b"b" * 32, iterations=1000)
        assert k1 != k2

    def test_output_length(self) -> None:
        key = _derive_key("password", b"x" * 32)
        assert len(key) == 32


class TestConstantTimeCompare:
    def test_equal_bytes(self) -> None:
        assert _constant_time_compare(b"abc", b"abc")

    def test_different_bytes(self) -> None:
        assert not _constant_time_compare(b"abc", b"abd")

    def test_different_lengths(self) -> None:
        assert not _constant_time_compare(b"abc", b"ab")


class TestSessionToken:
    def test_roundtrip(self) -> None:
        key = b"k" * 32
        ts = int(time.time())
        token = _make_session_token(key, ts)
        assert _verify_session_token(token, key)

    def test_expired_token(self) -> None:
        key = b"k" * 32
        ts = int(time.time()) - 31 * 60
        token = _make_session_token(key, ts)
        assert not _verify_session_token(token, key)

    def test_wrong_key_fails(self) -> None:
        token = _make_session_token(b"k" * 32, int(time.time()))
        assert not _verify_session_token(token, b"w" * 32)

    def test_malformed_token(self) -> None:
        key = b"k" * 32
        assert not _verify_session_token("garbage", key)
        assert not _verify_session_token("123:nope", key)


class TestSetupMasterPassword:
    def test_setup_and_authenticate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        assert is_setup()
        assert session_active()

    def test_authenticate_correct_password(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)
        assert authenticate("securepass123")
        assert session_active()

    def test_authenticate_wrong_password(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)
        assert not authenticate("wrongpassword")

    def test_short_password(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)

        with pytest.raises(ValueError, match="8 characters"):
            setup_master_password("short")

    def test_double_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        with pytest.raises(FileExistsError):
            setup_master_password("another123")


class TestChangeMasterPassword:
    def test_change_succeeds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("oldpass123")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        change_master_password("oldpass123", "newpass123")
        assert authenticate("newpass123")
        assert not authenticate("oldpass123")

    def test_change_wrong_old_password(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("correctpass")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        with pytest.raises(ValueError, match="incorrect"):
            change_master_password("wrongpass", "newpass123")

    def test_change_not_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "nonexistent_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)

        with pytest.raises(FileNotFoundError):
            change_master_password("old", "newpass123")


class TestSessionManagement:
    def test_clear_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        assert session_active()

        clear_session()
        assert not session_active()

    def test_session_active_when_not_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = Path("/nonexistent_test_path/.master_key")
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        assert not session_active()


class TestRequireAuth:
    def test_require_auth_with_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        require_auth()

    def test_require_auth_not_setup_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "nonexistent_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        with pytest.raises(SystemExit, match="1"):
            require_auth()

    def test_require_auth_no_session_noninteractive(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)
        monkeypatch.setenv("TRADERBOT_NONINTERACTIVE", "1")

        setup_master_password("securepass123")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        with pytest.raises(SystemExit, match="1"):
            require_auth()

    def test_require_auth_prompt_correct(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)
        monkeypatch.delenv("TRADERBOT_NONINTERACTIVE", raising=False)

        setup_master_password("securepass123")
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        import builtins
        orig_input = builtins.input
        builtins.input = lambda _="": "securepass123"
        try:
            require_auth()
        finally:
            builtins.input = orig_input


class TestIsSetup:
    def test_not_setup_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "nonexistent_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        assert not is_setup()

    def test_is_setup_after_create(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key_path = tmp_path / "test_master_key"
        monkeypatch.setattr("traderbot.master_password.MASTER_KEY_PATH", key_path)
        monkeypatch.delenv(SESSION_TOKEN_ENV, raising=False)

        setup_master_password("securepass123")
        assert is_setup()
