import base64
import sys
from pathlib import Path

import pytest

from traderbot.profiles.tokens import LocalTokenStore, generate_token


def test_local_store_roundtrip(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "weather-token")

    assert store.resolve_token("weather-token") == ("weather", "weather-agent")


def test_resolve_invalid_token_returns_none(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "weather-token")

    assert store.resolve_token("invalid-token") is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)

    assert store.resolve_token("missing-token") is None


def test_corrupt_file_returns_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text("{not-json", encoding="utf-8")
    store = LocalTokenStore(base_path=tmp_path)

    assert store.resolve_token("weather-token") is None
    assert "unreadable; treating as empty" in caplog.text


def test_token_entropy() -> None:
    tokens = {generate_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) == 43 for token in tokens)
    assert all(len(base64.urlsafe_b64decode(f"{token}=")) == 32 for token in tokens)


def test_duplicate_token_overwrites(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "shared-token")

    store.store_token("sysadmin", "sysadmin-agent", "shared-token")

    assert store.resolve_token("shared-token") == ("sysadmin", "sysadmin-agent")
    assert len(store.list_tokens()) == 1


def test_rotate_token_success(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "old-token")

    new_token = store.rotate_token("weather", "weather-agent")

    assert new_token != "old-token"
    assert store.resolve_token("old-token") is None
    assert store.resolve_token(new_token) == ("weather", "weather-agent")


def test_rotate_token_keyerror(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)

    with pytest.raises(KeyError, match="No token for profile='weather'"):
        _ = store.rotate_token("weather", "weather-agent")


def test_list_tokens_returns_expected_shape(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "weather-token")

    assert store.list_tokens() == [
        {"token": "weather-token", "profile": "weather", "agent_id": "weather-agent"}
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions are unavailable")
def test_token_file_permissions(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)

    store.store_token("weather", "weather-agent", "weather-token")

    assert store.token_file.stat().st_mode & 0o777 == 0o600
