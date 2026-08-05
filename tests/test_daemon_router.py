"""Tests for the Phase 2 daemon's WebSocket message router (DD-016)."""

from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.daemon import apply_ws_message
from traderbot.kalshi.ws_cache import MarketCache


@pytest.mark.asyncio
async def test_ticker_message_updates_cache(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    message = {
        "type": "ticker",
        "msg": {"market_ticker": "KXWETHRM0700M", "last_price": 55, "bid": 54, "ask": 56},
    }

    await apply_ws_message(message, cache)

    ticker = cache.get_ticker("KXWETHRM0700M")
    assert ticker is not None
    assert ticker["last_price"] == 55.0
    assert ticker["bid"] == 54.0
    assert ticker["ask"] == 56.0


@pytest.mark.asyncio
async def test_orderbook_snapshot_updates_cache(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    message = {
        "type": "orderbook_delta",
        "msg": {
            "market_ticker": "KXWETHRM0700M",
            "bids": [{"price": 0.54, "count": 100}],
            "asks": [{"price": 0.56, "count": 200}],
        },
    }

    await apply_ws_message(message, cache)

    book = cache.get_orderbook("KXWETHRM0700M")
    assert book is not None
    bid_levels = [lvl for lvl in book["bids"] if isinstance(lvl, dict)]
    assert len(bid_levels) == 1


@pytest.mark.asyncio
async def test_correct_orderbook_delta_requires_snapshot(tmp_path: Path) -> None:
    # A delta-only message (no bids/asks list) must not clobber the cache.
    cache = MarketCache(db_path=tmp_path / "t.db")
    message = {
        "type": "orderbook_delta",
        "msg": {
            "market_ticker": "KXWETHRM0700M",
            "price_dollars": 0.55,
            "delta_fp": 1,
            "side": "yes",
        },
    }

    await apply_ws_message(message, cache)

    assert cache.get_orderbook("KXWETHRM0700M") is None


@pytest.mark.asyncio
async def test_unknown_type_is_ignored(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")

    await apply_ws_message({"type": "error", "msg": {"code": 1, "msg": "boom"}}, cache)

    assert cache.get_ticker("KXWETHRM0700M") is None


@pytest.mark.asyncio
async def test_malformed_message_is_ignored(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")

    await apply_ws_message({"no_type": "here"}, cache)

    assert cache.get_ticker("KXWETHRM0700M") is None
