from collections.abc import Iterator
from pathlib import Path

import pytest

from traderbot.profiles.tokens import LocalTokenStore, set_store


@pytest.fixture
def token_store(tmp_path: Path) -> Iterator[LocalTokenStore]:
    store = LocalTokenStore(base_path=tmp_path)
    set_store(store)
    try:
        yield store
    finally:
        set_store(None)


@pytest.fixture
def real_auth(
    monkeypatch: pytest.MonkeyPatch,
    token_store: LocalTokenStore,
) -> LocalTokenStore:
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")
    return token_store


@pytest.fixture
def secrets_resolver_reset(tmp_path: Path) -> Iterator[None]:
    """Reset the secrets resolver singleton, active store, and suspended set.

    Ensures lazy-init runs against a fresh LocalTokenStore rooted at
    ``tmp_path`` (so the ~/.traderbot guard does not fire) and leaves no
    resolver state behind after the test.
    """
    from traderbot.mcp.resolver import _SUSPENDED_PROFILES
    from traderbot.profiles.tokens import LocalTokenStore, set_store
    from traderbot.secrets.resolver import set_resolver

    set_resolver(None)
    set_store(LocalTokenStore(base_path=tmp_path))
    _SUSPENDED_PROFILES.clear()
    try:
        yield
    finally:
        _SUSPENDED_PROFILES.clear()
        set_resolver(None)
