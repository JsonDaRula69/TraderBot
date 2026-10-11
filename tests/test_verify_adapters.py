from __future__ import annotations

import hashlib
from pathlib import Path
from typing import final

import pytest

from traderbot.db.decisions import init_decisions_db
from traderbot.db.migrations import init_schema
from traderbot.deploy.verify_models import CheckStatus, VerificationRequest
from traderbot.deploy.verify_storage import decisions_databases, global_database
from traderbot.deploy.verify_tokens import TokenVerifier, auth_mode
from traderbot.kalshi.order_models import MarketCategory
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.secrets.store import SecretsStore


@final
class MemoryStore:
    __slots__ = ("values",)

    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], str] = {}

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        return self.values.get((service, key, namespace))

    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None:
        self.values[(service, key, namespace)] = value

    def delete(self, service: str, key: str, namespace: str = "global") -> None:
        del self.values[(service, key, namespace)]

    def get_namespace(self, namespace: str) -> dict[str, str]:
        return {
            f"{service}_{key}": value
            for (service, key, stored_namespace), value in self.values.items()
            if stored_namespace == namespace
        }


def _request(root: Path) -> VerificationRequest:
    return VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        data_root=root,
    )


def test_database_probes_leave_files_byte_and_metadata_identical(tmp_path: Path) -> None:
    # Given
    global_path = tmp_path / "traderbot.db"
    decisions_path = tmp_path / "backtest-weather" / "db" / "decisions.db"
    init_schema(global_path)
    decisions_path.parent.mkdir(parents=True)
    init_decisions_db(decisions_path)
    before = {
        path: (
            hashlib.sha256(path.read_bytes()).digest(),
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for path in (global_path, decisions_path)
    }

    # When
    global_result = global_database(_request(tmp_path))
    decisions_result = decisions_databases(_request(tmp_path))

    # Then
    assert global_result.status is CheckStatus.PASS
    assert decisions_result.status is CheckStatus.PASS
    assert before == {
        path: (
            hashlib.sha256(path.read_bytes()).digest(),
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for path in (global_path, decisions_path)
    }
    assert not list(tmp_path.rglob("*-wal"))
    assert not list(tmp_path.rglob("*-shm"))
    assert not list(tmp_path.rglob("*-journal"))


def test_forbidden_sysadmin_decisions_db_fails(tmp_path: Path) -> None:
    # Given
    forbidden = tmp_path / "paper-sysadmin" / "db" / "decisions.db"
    forbidden.parent.mkdir(parents=True)
    forbidden.touch()

    # When
    result = decisions_databases(_request(tmp_path))

    # Then
    assert result.action == "sysadmin_db_forbidden"


def test_token_probe_returns_secret_without_exposing_value(tmp_path: Path) -> None:
    # Given
    local = MemoryStore()
    store = SecretsStore(local_store=local)
    profile = create_sysadmin_profile()
    store.store_profile_token(
        "main",
        "TOKEN-CANARY",
        profile.name,
        [category.value for category in profile.enabled_categories],
        profile.permissions,
    )
    store.store_profile_token("weather", "WEATHER-CANARY", "weather", ["weather"], [])
    request = _request(tmp_path)

    # When
    result = TokenVerifier(request, store).inspect()

    # Then
    assert result.result.status is CheckStatus.PASS
    assert "CANARY" not in repr(result)
    assert "CANARY" not in result.model_dump_json()


def test_exact_auth_mode_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    # When / Then
    for value in (None, "", "false", "1"):
        if value is None:
            monkeypatch.delenv("TRADERBOT_USE_HARDCODED_AUTH", raising=False)
        else:
            monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", value)
        assert auth_mode().status is CheckStatus.FAIL
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")
    assert auth_mode().status is CheckStatus.PASS
