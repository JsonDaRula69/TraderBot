"""Tests for the news stub and settlement monitor providers (DD-028)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from traderbot.data.providers import NewsProvider, SettlementMonitor
from traderbot.data.providers.news import _NEWS_INTERVAL_SECONDS
from traderbot.data.providers.settlement import _HOURLY_INTERVAL_SECONDS


def _mock_client(*, status_code: int = 200, json: object | None = None) -> MagicMock:
    client = MagicMock()
    request = httpx.Request("GET", "https://api.example.com/markets")
    resp = httpx.Response(status_code, json=json if json is not None else {}, request=request)
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_news_provider_stub_fetch() -> None:
    provider = NewsProvider()

    payload = await provider.fetch()

    assert payload["stub"] is True
    assert payload["runs"] == 1

    inserted = await provider.insert(payload)
    assert inserted == 0


def test_news_provider_metadata() -> None:
    provider = NewsProvider()

    assert provider.name == "news"
    assert provider.interval_seconds == _NEWS_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_settlement_monitor_fetch_records_outcomes(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    markets = [
        {
            "ticker": "KXWETHRM0700M",
            "result": "yes",
            "close_time": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "ticker": "KXWETHRM0800M",
            "result": "no",
            "close_time": (now - timedelta(hours=2)).isoformat(),
        },
    ]
    client = _mock_client(json={"markets": markets})

    monitor = SettlementMonitor(client=client, db_path=tmp_path / "test.db")
    records = await monitor.fetch()

    assert len(records) == 2
    assert records[0]["ticker"] == "KXWETHRM0700M"
    assert records[0]["outcome"] == 1
    assert records[1]["ticker"] == "KXWETHRM0800M"
    assert records[1]["outcome"] == 0
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_settlement_monitor_fetch_error_returns_empty(tmp_path: Path) -> None:
    client = _mock_client(status_code=500)

    monitor = SettlementMonitor(client=client, db_path=tmp_path / "test.db")
    records = await monitor.fetch()

    assert records == []


@pytest.mark.asyncio
async def test_settlement_monitor_fetch_filters_stale_markets(tmp_path: Path) -> None:
    # close_time 30 days ago must be excluded by the look-back window.
    markets = [
        {
            "ticker": "KXWETHRM0700M",
            "result": "yes",
            "close_time": "2026-07-05T12:00:00Z",
        }
    ]
    client = _mock_client(json={"markets": markets})

    monitor = SettlementMonitor(client=client, db_path=tmp_path / "test.db")
    records = await monitor.fetch()

    assert records == []


@pytest.mark.asyncio
async def test_settlement_monitor_insert_writes_rows(tmp_path: Path) -> None:
    client = MagicMock()
    monitor = SettlementMonitor(client=client, db_path=tmp_path / "test.db")

    inserted = await monitor.insert(
        [
            {"ticker": "KXWETHRM0700M", "outcome": 1, "settled_at": "2026-08-04T12:00:00Z"},
            {"ticker": "KXWETHRM0800M", "outcome": 0, "settled_at": "2026-08-04T13:00:00Z"},
        ]
    )

    assert inserted == 2
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        rows = conn.execute(
            "SELECT ticker, outcome FROM settlement_cache ORDER BY ticker"
        ).fetchall()
        assert rows == [("KXWETHRM0700M", 1), ("KXWETHRM0800M", 0)]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_settlement_monitor_insert_is_idempotent(tmp_path: Path) -> None:
    client = MagicMock()
    monitor = SettlementMonitor(client=client, db_path=tmp_path / "test.db")
    rows = [{"ticker": "KXWETHRM0700M", "outcome": 1, "settled_at": "2026-08-04T12:00:00Z"}]

    await monitor.insert(rows)
    second = await monitor.insert(rows)

    assert second == 0  # INSERT OR IGNORE — duplicate is skipped
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        count = conn.execute("SELECT COUNT(*) FROM settlement_cache").fetchone()
        assert count is not None
        assert count[0] == 1
    finally:
        conn.close()


def test_settlement_monitor_metadata() -> None:
    client = MagicMock()
    monitor = SettlementMonitor(client=client)

    assert monitor.name == "settlement-monitor"
    assert monitor.interval_seconds == _HOURLY_INTERVAL_SECONDS
