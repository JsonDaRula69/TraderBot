"""Isolation tests for every Todo-1 storage and authentication path seam."""

from pathlib import Path
from unittest import mock

import pytest

from traderbot.mcp.resolver import resolve_token_adapter
from traderbot.paths import get_data_dir
from traderbot.profiles.tokens import LocalTokenStore, set_store
from traderbot.secrets.resolver import build_secrets_store, set_resolver


def test_data_dir_environment_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: an explicit isolated TraderBot data root
    expected = tmp_path / "isolated"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(expected))

    # When/Then: the central path resolver uses the override verbatim
    assert get_data_dir() == expected


def test_local_token_store_defaults_to_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an explicit isolated TraderBot data root
    expected = tmp_path / "tokens-root"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(expected))

    # When: a token store uses its default base path
    store = LocalTokenStore()

    # Then: token persistence is rooted under the override
    assert store.base_path == expected
    assert store.token_file == expected / "tokens.json"


def test_real_auth_default_store_guard_uses_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: real auth with its default store rooted at the override
    expected = tmp_path / "auth-root"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(expected))
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")
    resolver_calls: list[bool] = []
    set_store(LocalTokenStore(base_path=expected))
    set_resolver(None)
    monkeypatch.setattr(
        "traderbot.secrets.resolver.get_resolver",
        lambda: resolver_calls.append(True),
    )

    try:
        # When: token resolution evaluates the default-store lazy-init guard
        _ = resolve_token_adapter("missing-token")

        # Then: the override-rooted store is recognized as the default
        assert resolver_calls == [True]
    finally:
        set_store(None)
        set_resolver(None)


def test_infisical_credentials_path_uses_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an explicit isolated TraderBot data root
    expected = tmp_path / "secrets-root"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(expected))

    # When: the secrets store looks for Infisical credentials
    with mock.patch.object(
        Path, "read_text", autospec=True, side_effect=FileNotFoundError
    ) as read_text:
        _ = build_secrets_store()

    # Then: credentials are resolved beneath the override.
    # OS-aware: on Linux the machine-identity derivation reads /etc/machine-id
    # first, so the credentials read is not necessarily read_text's first call.
    # The proven property is unchanged: build_secrets_store() reads the
    # Infisical credentials file at exactly <override>/infisical-credentials.json
    # and nowhere else.
    expected_path = expected / "infisical-credentials.json"
    read_paths = [c.args[0] for c in read_text.call_args_list]
    assert expected_path in read_paths
    assert not any(
        p != expected_path and Path(p).name == "infisical-credentials.json"
        for p in read_paths
    )
