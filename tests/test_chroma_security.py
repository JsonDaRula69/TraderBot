"""Security regressions for the embedded ChromaDB boundary."""

from __future__ import annotations

import ast
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from traderbot.db import (
    ChromaBackendError,
    ChromaStore,
    InvalidChromaRootError,
    assert_embedded_backend,
    create_chroma_root,
    validate_chroma_root,
)
from traderbot.db.models import ChromaMetadataMismatchError
from traderbot.kalshi.models import MarketCategory


@pytest.fixture
def chroma_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    root = tmp_path / ".traderbot" / "chromadb"
    create_chroma_root(root)
    return root


def test_owned_private_directory_passes(chroma_root: Path) -> None:
    validate_chroma_root(chroma_root)
    assert stat.S_IMODE(chroma_root.lstat().st_mode) == 0o700
    assert stat.S_IMODE((chroma_root / "chromadb.lock").lstat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
@pytest.mark.parametrize("mode", [0o755, 0o777])
def test_permissive_mode_is_rejected(chroma_root: Path, mode: int) -> None:
    chroma_root.chmod(mode)
    with pytest.raises(InvalidChromaRootError, match="mode"):
        validate_chroma_root(chroma_root)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership")
def test_wrong_owner_is_rejected(chroma_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from traderbot.db import security

    monkeypatch.setattr(security, "_current_posix_uid", lambda: chroma_root.lstat().st_uid + 1)
    with pytest.raises(InvalidChromaRootError, match="owner"):
        validate_chroma_root(chroma_root)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
def test_symlink_is_rejected_before_target_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o777)
    outside.chmod(0o777)
    root = tmp_path / ".traderbot" / "chromadb"
    root.parent.mkdir(mode=0o700)
    root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InvalidChromaRootError, match="symlink"):
        _ = ChromaStore(root)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS extended ACL semantics")
def test_extended_acl_is_rejected(chroma_root: Path) -> None:
    _ = subprocess.run(
        ["chmod", "+a", "everyone allow read,write,execute", str(chroma_root)], check=True
    )
    try:
        with pytest.raises(InvalidChromaRootError, match="extended ACL"):
            validate_chroma_root(chroma_root)
    finally:
        _ = subprocess.run(["chmod", "-N", str(chroma_root)], check=True)


def test_out_of_containment_directory_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    with pytest.raises(InvalidChromaRootError, match="contained"):
        validate_chroma_root(outside)


@dataclass(frozen=True, slots=True)
class _Settings:
    chroma_api_impl: str
    anonymized_telemetry: bool


@dataclass(frozen=True, slots=True)
class _Client:
    settings: _Settings

    def get_settings(self) -> _Settings:
        return self.settings


def test_backend_assertion_rejects_remote_or_telemetry_settings() -> None:
    client = _Client(_Settings("remote.Backend", True))
    with pytest.raises(ChromaBackendError):
        assert_embedded_backend(client)


def test_hostile_environment_cannot_force_network_backend(chroma_root: Path) -> None:
    code = """
from pathlib import Path
from unittest.mock import patch
from traderbot.db import ChromaStore
from traderbot.kalshi.models import MarketCategory
root = Path(__import__('os').environ['TRADERBOT_TEST_CHROMA_ROOT'])
with patch('socket.socket.connect', side_effect=AssertionError('socket connect attempted')):
    store = ChromaStore(root)
    store.add(MarketCategory.WEATHER, 'security_vectors', ['one'], [[1.0, 0.0, 0.0]], None, None)
    store.close()
"""
    env = os.environ.copy()
    env.update(
        CHROMA_API_IMPL="chromadb.api.fastapi.FastAPI",
        CHROMA_SERVER_HOST="127.0.0.1",
        CHROMA_SERVER_HTTP_PORT="9",
        TRADERBOT_TEST_CHROMA_ROOT=str(chroma_root),
        HOME=str(chroma_root.parents[1]),
        USERPROFILE=str(chroma_root.parents[1]),
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr


def test_product_code_has_no_server_or_http_client_imports() -> None:
    db_root = Path(__file__).parents[1] / "src" / "traderbot" / "db"
    banned_modules = {"chromadb.server", "chromadb.api.fastapi", "fastapi", "uvicorn"}
    banned_names = {"FastAPI", "HttpClient", "AsyncHttpClient", "CloudClient"}
    for source_path in db_root.glob("*.py"):
        tree = ast.parse(source_path.read_text())
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not (imports & banned_modules)
        assert not (names & banned_names)


def test_second_process_cannot_acquire_owned_root(chroma_root: Path) -> None:
    store = ChromaStore(chroma_root)
    code = """
from pathlib import Path
from traderbot.db import ChromaOwnershipError, ChromaStore
try:
    ChromaStore(Path(__import__('os').environ['TRADERBOT_TEST_CHROMA_ROOT']))
except ChromaOwnershipError:
    raise SystemExit(0)
raise SystemExit(1)
"""
    env = os.environ.copy()
    env["TRADERBOT_TEST_CHROMA_ROOT"] = str(chroma_root)
    env["HOME"] = str(chroma_root.parents[1])
    env["USERPROFILE"] = str(chroma_root.parents[1])
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    store.close()
    assert result.returncode == 0, result.stderr


def test_dimension_mismatch_raises_chroma_error(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.add(
            MarketCategory.WEATHER,
            "dimension_vectors",
            ["three"],
            [[1.0, 0.0, 0.0]],
            None,
            None,
        )
        with pytest.raises(ChromaMetadataMismatchError):
            store.add(
                MarketCategory.WEATHER,
                "dimension_vectors",
                ["four"],
                [[1.0, 0.0, 0.0, 0.0]],
                None,
                None,
            )


def test_category_prefix_prevents_cross_category_upsert(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.upsert(
            MarketCategory.WEATHER,
            "shared_vectors",
            ["same"],
            [[1.0, 0.0, 0.0]],
            ["weather"],
            None,
        )
        store.upsert(
            MarketCategory.SPORTS,
            "shared_vectors",
            ["same"],
            [[0.0, 1.0, 0.0]],
            ["sports"],
            None,
        )
        weather = store.get(MarketCategory.WEATHER, "shared_vectors", ["same"], None, None)
        sports = store.get(MarketCategory.SPORTS, "shared_vectors", ["same"], None, None)
    assert weather["ids"] == ["weather:same"]
    assert sports["ids"] == ["sports:same"]
    assert weather["documents"] == ["weather"]
    assert sports["documents"] == ["sports"]


def test_all_operations_enforce_category_scope(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        for category, caller_id, embedding in (
            (MarketCategory.WEATHER, "w", (1.0, 0.0, 0.0)),
            (MarketCategory.SPORTS, "s", (0.0, 1.0, 0.0)),
        ):
            store.add(category, "scoped_vectors", [caller_id], [list(embedding)], None, None)
        got = store.get(MarketCategory.WEATHER, "scoped_vectors", None, None, None)
        queried = store.query(
            MarketCategory.WEATHER, "scoped_vectors", [[1.0, 0.0, 0.0]], 10, None
        )
        _ = store.delete(MarketCategory.WEATHER, "scoped_vectors", None, None)
        remaining = store.get(MarketCategory.SPORTS, "scoped_vectors", None, None, None)
        assert not hasattr(store, "collection")
        assert not hasattr(store, "update")
    assert got["ids"] == ["weather:w"]
    assert queried["ids"] == [["weather:w"]]
    assert remaining["ids"] == ["sports:s"]


def test_exact_audit_waiver_does_not_hide_other_advisories(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements-audit.txt"
    _ = requirements.write_text("urllib3==1.26.5\n")
    result = subprocess.run(
        [
            "uvx",
            "pip-audit",
            "--strict",
            "--aliases",
            "-r",
            str(requirements),
            "--ignore-vuln",
            "GHSA-f4j7-r4q5-qw2c",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "urllib3" in f"{result.stdout}\n{result.stderr}"
