import base64
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO

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


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "{}",
        '{"tokens": []}',
        '{"tokens": {"weather-token": []}}',
        '{"tokens": {"weather-token": {"profile": "weather"}}}',
        ('{"tokens": {"weather-token": {"profile": 1, "agent_id": "weather-agent"}}}'),
        ('{"tokens": {"weather-token": {"profile": "weather", "agent_id": 1}}}'),
    ],
)
def test_malformed_payload_returns_none(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    payload: str,
) -> None:
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text(payload, encoding="utf-8")
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


def test_rotate_token_removes_every_prior_match(tmp_path: Path) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    store.store_token("weather", "weather-agent", "old-token-one")
    store.store_token("weather", "weather-agent", "old-token-two")
    store.store_token("weather", "other-agent", "unrelated-token")

    new_token = store.rotate_token("weather", "weather-agent")

    assert store.resolve_token("old-token-one") is None
    assert store.resolve_token("old-token-two") is None
    assert store.resolve_token(new_token) == ("weather", "weather-agent")
    assert store.resolve_token("unrelated-token") == ("weather", "other-agent")


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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions are unavailable")
def test_temp_token_file_is_private_during_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalTokenStore(base_path=tmp_path)
    original_dump: Callable[..., None] = json.dump

    def dump_after_permission_check(
        payload: dict[str, dict[str, dict[str, str]]],
        file_handle: IO[str],
        *,
        indent: int,
    ) -> None:
        temp_files = list(tmp_path.iterdir())
        assert len(temp_files) == 1
        assert temp_files[0].stat().st_mode & 0o777 == 0o600
        original_dump(payload, file_handle, indent=indent)

    monkeypatch.setattr(json, "dump", dump_after_permission_check)
    previous_umask = os.umask(0o022)
    try:
        store.store_token("weather", "weather-agent", "weather-token")
    finally:
        _ = os.umask(previous_umask)


def test_write_failure_propagates_and_removes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalTokenStore(base_path=tmp_path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError(source, destination)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(PermissionError):
        store.store_token("weather", "weather-agent", "weather-token")

    assert list(tmp_path.iterdir()) == []
