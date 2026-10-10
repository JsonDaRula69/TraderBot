import shutil
import uuid
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
def clean_workspace_root() -> Iterator[Path]:
    """Private workspace root whose ancestor chain passes the injection guard.

    The POSIX publication walk (``_injection_posix._validate_control``) rejects
    any group-writable ancestor directory - the sticky bit does not exempt it -
    so real-CLI deploy E2Es whose workspaces live under a default pytest
    basetemp (``/tmp``, or a ``TMPDIR`` with a group-writable ancestor) fail
    injection for environmental reasons. This root lives under the real user
    home, whose ancestor chain is not group-writable on supported hosts, and
    is removed after the test.
    """
    base = Path.home() / ".tb-e2e-workspaces"
    root = base / uuid.uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


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
