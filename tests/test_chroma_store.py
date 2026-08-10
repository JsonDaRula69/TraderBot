"""Collection management and category-isolation tests for ChromaStore."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from traderbot.db.chroma_store import ChromaStore
from traderbot.db.models import (
    ChromaCategoryError,
    ChromaMetadataMismatchError,
    InvalidCollectionNameError,
    agent_collection_name,
)
from traderbot.db.security import create_chroma_root
from traderbot.kalshi.models import MarketCategory


@runtime_checkable
class _Closable(Protocol):
    def close(self) -> None: ...


@pytest.fixture
def chroma_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    root = tmp_path / ".traderbot" / "chromadb"
    create_chroma_root(root)
    return root


def test_agent_collection_name_normalizes_hyphenated_source() -> None:
    assert agent_collection_name("weather-alerts", "paper", "decisions") == (
        "weather_alerts_paper_decisions"
    )


def test_agent_collection_name_accepts_one_character_source() -> None:
    assert agent_collection_name("w", "live", "learnings") == "w_live_learnings"


@pytest.mark.parametrize("source", ["", "weather_agent", "Weather", "sysadmin", "a" * 45])
def test_agent_collection_name_rejects_invalid_or_reserved_source(source: str) -> None:
    with pytest.raises(InvalidCollectionNameError):
        _ = agent_collection_name(source, "paper", "decisions")


def test_agent_collection_name_allows_only_modeless_canonical_sysadmin() -> None:
    assert agent_collection_name("sysadmin", None, "decisions") == "sysadmin_decisions"
    assert agent_collection_name("sysadmin", None, "learnings") == "sysadmin_learnings"
    with pytest.raises(InvalidCollectionNameError):
        _ = agent_collection_name("weather", None, "decisions")


def test_shared_collection_names_can_be_created_and_listed(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        for name in ChromaStore.SHARED_COLLECTIONS:
            store.get_or_create_collection(name, 3)
        names = store.list_collections()

    assert names == sorted(ChromaStore.SHARED_COLLECTIONS)


def test_category_metadata_is_injected_on_write_and_read(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.add(
            MarketCategory.WEATHER,
            "news",
            ["forecast-1"],
            [[1.0, 0.0, 0.0]],
            ["rain"],
            [{"source": "nws"}],
        )
        result = store.get(MarketCategory.WEATHER, "news", ["forecast-1"], None, None)

    assert result["ids"] == ["weather:forecast-1"]
    assert result["metadatas"] == [{"category": "weather", "source": "nws"}]


def test_same_caller_id_coexists_in_two_categories(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.upsert(
            MarketCategory.WEATHER,
            "data_points",
            ["same"],
            [[1.0, 0.0, 0.0]],
            ["weather"],
            None,
        )
        store.upsert(
            MarketCategory.ECONOMICS,
            "data_points",
            ["same"],
            [[0.0, 1.0, 0.0]],
            ["economics"],
            None,
        )
        weather = store.get(MarketCategory.WEATHER, "data_points", ["same"], None, None)
        economics = store.get(MarketCategory.ECONOMICS, "data_points", ["same"], None, None)

    assert weather["documents"] == ["weather"]
    assert economics["documents"] == ["economics"]


def test_weather_upsert_does_not_mutate_economics_record(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.upsert(
            MarketCategory.ECONOMICS,
            "market_patterns",
            ["same"],
            [[0.0, 1.0, 0.0]],
            ["original"],
            None,
        )
        store.upsert(
            MarketCategory.WEATHER,
            "market_patterns",
            ["same"],
            [[1.0, 0.0, 0.0]],
            ["changed"],
            None,
        )
        economics = store.get(MarketCategory.ECONOMICS, "market_patterns", ["same"], None, None)

    assert economics["documents"] == ["original"]


def test_cross_category_read_and_delete_are_denied(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.add(
            MarketCategory.WEATHER,
            "news_signals",
            ["signal"],
            [[1.0, 0.0, 0.0]],
            None,
            None,
        )
        denied = store.get(MarketCategory.SPORTS, "news_signals", ["signal"], None, None)
        store.delete(MarketCategory.SPORTS, "news_signals", ["signal"], None)
        retained = store.get(MarketCategory.WEATHER, "news_signals", ["signal"], None, None)

    assert denied["ids"] == []
    assert retained["ids"] == ["weather:signal"]


def test_get_query_and_delete_compose_caller_where_with_category(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.add(
            MarketCategory.WEATHER,
            "news",
            ["keep", "remove"],
            [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]],
            None,
            [{"group": "keep"}, {"group": "remove"}],
        )
        store.add(
            MarketCategory.SPORTS,
            "news",
            ["remove"],
            [[1.0, 0.0, 0.0]],
            None,
            [{"group": "remove"}],
        )
        got = store.get(MarketCategory.WEATHER, "news", None, {"group": "keep"}, None)
        queried = store.query(
            MarketCategory.WEATHER, "news", [[1.0, 0.0, 0.0]], 10, {"group": "keep"}
        )
        store.delete(MarketCategory.WEATHER, "news", None, {"group": "remove"})
        weather = store.get(MarketCategory.WEATHER, "news", None, None, None)
        sports = store.get(MarketCategory.SPORTS, "news", None, None, None)

    assert got["ids"] == ["weather:keep"]
    assert queried["ids"] == [["weather:keep"]]
    assert weather["ids"] == ["weather:keep"]
    assert sports["ids"] == ["sports:remove"]


def test_conflicting_category_metadata_fails_without_mutation(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        with pytest.raises(ChromaCategoryError):
            store.upsert(
                MarketCategory.WEATHER,
                "data_points",
                ["unsafe"],
                [[1.0, 0.0, 0.0]],
                None,
                [{"category": "sports"}],
            )
        collections = store.list_collections()

    assert "data_points" not in collections


def test_add_and_upsert_are_idempotent(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        for operation in (store.add, store.upsert):
            operation(
                MarketCategory.WEATHER,
                "market_patterns",
                ["stable"],
                [[1.0, 0.0, 0.0]],
                ["stable"],
                None,
            )
            operation(
                MarketCategory.WEATHER,
                "market_patterns",
                ["stable"],
                [[1.0, 0.0, 0.0]],
                ["stable"],
                None,
            )
        result = store.get(MarketCategory.WEATHER, "market_patterns", None, None, None)

    assert result["ids"] == ["weather:stable"]


def test_collection_metadata_same_value_reopens(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.get_or_create_collection("news", 3)
    with ChromaStore(chroma_root) as reopened:
        reopened.get_or_create_collection("news", 3)


@pytest.mark.parametrize("metadata", [{"dimension": 4, "model": "explicit"}, {"dimension": 3}])
def test_collection_metadata_mismatch_fails_closed(
    chroma_root: Path, metadata: dict[str, str | int]
) -> None:
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=chroma_root,
        settings=Settings(
            chroma_api_impl="chromadb.api.rust.RustBindingsAPI",
            anonymized_telemetry=False,
        ),
    )
    _ = client.get_or_create_collection("news", metadata=metadata, embedding_function=None)
    assert isinstance(client, _Closable)
    client.close()

    with ChromaStore(chroma_root) as store, pytest.raises(ChromaMetadataMismatchError):
        store.get_or_create_collection("news", 3)


def test_market_conditions_is_global_and_unprefixed(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        store.upsert(
            MarketCategory.WEATHER,
            "market_conditions",
            ["current"],
            [[1.0, 0.0, 0.0]],
            None,
            [{"regime": "risk-on"}],
        )
        result = store.get(MarketCategory.SPORTS, "market_conditions", ["current"], None, None)

    assert result["ids"] == ["current"]
    assert result["metadatas"] == [{"regime": "risk-on"}]


def test_lock_contention_and_release_across_processes(chroma_root: Path) -> None:
    store = ChromaStore(chroma_root)
    code = """
from pathlib import Path
from traderbot.db.chroma_store import ChromaOwnershipError, ChromaStore
root = Path(__import__('os').environ['TRADERBOT_TEST_CHROMA_ROOT'])
try:
    with ChromaStore(root):
        pass
except ChromaOwnershipError:
    raise SystemExit(2)
"""
    env = os.environ.copy()
    env.update(
        HOME=str(chroma_root.parents[1]),
        USERPROFILE=str(chroma_root.parents[1]),
        TRADERBOT_TEST_CHROMA_ROOT=str(chroma_root),
    )
    contended = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    store.close()
    released = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )

    assert contended.returncode == 2
    assert released.returncode == 0, released.stderr


def test_product_module_has_no_network_server_or_model_path() -> None:
    source_path = Path(__file__).parents[1] / "src" / "traderbot" / "db" / "chroma_store.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert not imports & {"chromadb.server", "chromadb.api.fastapi", "fastapi", "uvicorn"}
    assert not names & {"HttpClient", "AsyncHttpClient", "CloudClient", "DefaultEmbeddingFunction"}


def test_public_methods_never_return_collection(chroma_root: Path) -> None:
    with ChromaStore(chroma_root) as store:
        assert store.get_or_create_collection("news", 3) is None
        assert (
            store.add(
                MarketCategory.WEATHER,
                "news",
                ["one"],
                [[1.0, 0.0, 0.0]],
                None,
                None,
            )
            is None
        )
        assert (
            store.upsert(
                MarketCategory.WEATHER,
                "news",
                ["one"],
                [[1.0, 0.0, 0.0]],
                None,
                None,
            )
            is None
        )
        assert store.delete(MarketCategory.WEATHER, "news", ["one"], None) is None
        assert not hasattr(store, "update")
        assert not hasattr(store, "collection")
