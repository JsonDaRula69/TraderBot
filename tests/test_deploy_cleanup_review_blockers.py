"""Cleanup aggregation regressions for deploy database provisioning."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Never

import pytest

from traderbot.db.chroma_ownership import ChromaCleanupError
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.security import create_chroma_root
from traderbot.deploy.database_step import (
    DatabaseCleanupError,
    DeployMode,
    provision_deploy_databases,
)
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.secret_step import SecretsSelection
from traderbot.deploy.wizard_contracts import StepStatus, WizardRequest
from traderbot.kalshi.models import MarketCategory
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.store import SecretsStore


class _PoolCleanupFault(RuntimeError):
    pass


class _ChromaCleanupFault(RuntimeError):
    pass


class _InjectedCloseTypeError(TypeError):
    pass


class _InjectedShutdownTypeError(TypeError):
    pass


@pytest.mark.parametrize(
    ("close_fails", "shutdown_fails"),
    [(True, False), (False, True), (True, True)],
)
def test_cleanup_attempts_chroma_then_pool_and_preserves_failure_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
    shutdown_fails: bool,
) -> None:
    # Given: cleanup adapters fault independently after Chroma ownership.
    import traderbot.deploy.database_step as database_step

    calls: list[str] = []

    class Pool:
        def shutdown(self) -> None:
            calls.append("pool:shutdown")
            if shutdown_fails:
                raise _PoolCleanupFault("pool cleanup identity")

    class Chroma:
        def __init__(self, root: Path) -> None:
            del root

        def list_collections(self) -> list[str]:
            return []

        def close(self) -> None:
            calls.append("chroma:close")
            if close_fails:
                raise ChromaCleanupError(
                    "Chroma cleanup failed",
                    [_ChromaCleanupFault("chroma cleanup identity")],
                )

    monkeypatch.setattr(database_step, "init_schema", lambda _path: None)
    monkeypatch.setattr(database_step, "SQLiteConnectionPool", Pool)
    monkeypatch.setattr(database_step, "create_chroma_root", lambda _path: None)
    monkeypatch.setattr(database_step, "ChromaStore", Chroma)
    monkeypatch.setattr(
        database_step,
        "SHARED_CHROMA_COLLECTIONS",
        frozenset({"unexpected"}),
    )

    # When: body and cleanup unwind with one or both cleanup faults.
    with pytest.raises(BaseException) as raised:
        _ = provision_deploy_databases((MarketCategory.WEATHER,), "backtest", tmp_path)

    # Then: shutdown always follows close and all cleanup identities survive.
    assert calls == ["chroma:close", "pool:shutdown"]
    rendered = repr(raised.value)
    if close_fails:
        assert "chroma cleanup identity" in rendered
    if shutdown_fails:
        assert "pool cleanup identity" in rendered


def test_chroma_client_close_fault_still_releases_lock_for_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a real owned Chroma root whose client closer faults once.
    root = tmp_path / "chromadb"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(tmp_path))
    create_chroma_root(root)
    store = ChromaStore(root)

    def fail_close() -> Never:
        raise _InjectedCloseTypeError("typed close fault")

    # When: close fails at the client boundary.
    with monkeypatch.context() as patch:
        patch.setattr(store._closer, "close", fail_close)
        with pytest.raises(ExceptionGroup):
            store.close()

        # Then: ownership is already released and another client can reopen.
        with ChromaStore(root):
            pass
    store.close()


def test_type_error_cleanup_still_attempts_pool_and_preserves_both_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: both database cleanup adapters raise their observed TypeError class.
    import traderbot.deploy.database_step as database_step

    calls: list[str] = []

    class Pool:
        def shutdown(self) -> None:
            calls.append("pool:shutdown")
            raise _InjectedShutdownTypeError("typed pool identity")

    class Chroma:
        def __init__(self, root: Path) -> None:
            del root

        def list_collections(self) -> list[str]:
            return []

        def close(self) -> None:
            calls.append("chroma:close")
            raise _InjectedCloseTypeError("typed Chroma identity")

    monkeypatch.setattr(database_step, "init_schema", lambda _path: None)
    monkeypatch.setattr(database_step, "SQLiteConnectionPool", Pool)
    monkeypatch.setattr(database_step, "create_chroma_root", lambda _path: None)
    monkeypatch.setattr(database_step, "ChromaStore", Chroma)
    monkeypatch.setattr(
        database_step,
        "SHARED_CHROMA_COLLECTIONS",
        frozenset({"unexpected"}),
    )

    # When: provisioning unwinds through both TypeError cleanup failures.
    with pytest.raises(DatabaseCleanupError) as raised:
        _ = provision_deploy_databases((MarketCategory.WEATHER,), "backtest", tmp_path)

    # Then: pool shutdown follows Chroma close and both typed identities survive.
    assert calls == ["chroma:close", "pool:shutdown"]
    rendered = repr(raised.value)
    assert "typed Chroma identity" in rendered
    assert "typed pool identity" in rendered


def test_phase_adapter_converts_database_cleanup_group_to_canonical_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: database provisioning raises an aggregated cleanup error with protected detail.
    import traderbot.deploy.phase45_runtime as phase45_runtime

    protected = secrets.token_urlsafe()

    def fail_provision(
        categories: tuple[MarketCategory, ...],
        mode: DeployMode,
        data_root: Path,
    ) -> Never:
        del categories, mode, data_root
        raise DatabaseCleanupError(
            "deploy storage cleanup failed",
            [_InjectedCloseTypeError(protected)],
        )

    local = SecretsStore(local_store=LocalEncryptedStore(tmp_path / "secrets"))
    adapter = Phase45Adapter(
        SecretsSelection(store=local, backend="local-encrypted", fallback_store=local),
        None,
        tmp_path,
    )
    request = WizardRequest.model_validate({"categories": ["weather"], "mode": "backtest"})
    monkeypatch.setattr(phase45_runtime, "provision_deploy_databases", fail_provision)

    # When: the phase boundary converts the cleanup group.
    escaped = False
    result = None
    try:
        result = adapter.provision_databases(request)
    except DatabaseCleanupError:
        escaped = True

    # Then: a typed failed step carries only the canonical message.
    assert escaped is False
    assert result is not None
    assert result.status is StepStatus.FAILED
    assert result.message == "database or Chroma cleanup failed"
    assert protected not in result.model_dump_json()
