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
