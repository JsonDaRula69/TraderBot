"""Tests for the Phase 2 daemon's WebSocket message router (DD-016)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

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


# Issue #251 slice 1: Kalshi's v2 ticker payload names prices as fixed-point
# dollar strings and counts as ``*_fp`` fields (mirroring the REST path in
# ``kalshi/_normalize.py``); the pre-v2 cent-integer names remain fallbacks.
_V2_TICKER_FRAME: Final = {
    "market_ticker": "KXWETHRM0700M",
    "last_price_dollars": "0.55",
    "yes_bid_dollars": "0.54",
    "yes_ask_dollars": "0.56",
    "volume_fp": 1234,
    "open_interest_fp": 567,
    "ts": 1700000000000,
}


def _read_market_data_row(db: Path, ticker: str) -> tuple[float, ...] | None:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT last_price, bid, ask, volume, open_interest FROM market_data WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_v2_ticker_frame_yields_real_prices_and_persists(tmp_path: Path) -> None:
    """A v2-shaped frame must land as real prices in the cache and in the row."""
    db = tmp_path / "t.db"
    cache = MarketCache(db_path=db)

    await apply_ws_message({"type": "ticker", "msg": dict(_V2_TICKER_FRAME)}, cache)

    ticker = cache.get_ticker("KXWETHRM0700M")
    assert ticker is not None
    assert ticker["last_price"] == 55.0
    assert ticker["bid"] == 54.0
    assert ticker["ask"] == 56.0
    assert ticker["volume"] == 1234.0
    assert ticker["open_interest"] == 567.0
    assert ticker["updated_at"] > 0.0

    cache.persist_to_db()
    assert _read_market_data_row(db, "KXWETHRM0700M") == (55.0, 54.0, 56.0, 1234.0, 567.0)


@pytest.mark.asyncio
async def test_v2_ticker_frame_with_missing_fields_patches_only_those(tmp_path: Path) -> None:
    """Fields absent from the frame must not zero the cached placeholder."""
    db = tmp_path / "t.db"
    cache = MarketCache(db_path=db)

    await apply_ws_message(
        {"type": "ticker", "msg": {"market_ticker": "KXWETHRM0700M", "yes_ask_dollars": "0.60"}},
        cache,
    )

    ticker = cache.get_ticker("KXWETHRM0700M")
    assert ticker is not None
    assert ticker["ask"] == 60.0
    assert ticker["last_price"] == 0.0
    cache.persist_to_db()
    assert _read_market_data_row(db, "KXWETHRM0700M") == (0.0, 0.0, 60.0, 0.0, 0.0)


@pytest.mark.asyncio
async def test_legacy_ticker_frame_still_parses(tmp_path: Path) -> None:
    """Pre-v2 cent-scale field names remain a working fallback (no regression)."""
    cache = MarketCache(db_path=tmp_path / "t.db")
    message = {
        "type": "ticker",
        "msg": {
            "market_ticker": "KXWETHRM0700M",
            "last_price": 55,
            "bid": 54,
            "ask": 56,
            "volume": 1234,
            "open_interest": 567,
        },
    }

    await apply_ws_message(message, cache)

    ticker = cache.get_ticker("KXWETHRM0700M")
    assert ticker is not None
    assert ticker["last_price"] == 55.0
    assert ticker["bid"] == 54.0
    assert ticker["ask"] == 56.0
    assert ticker["volume"] == 1234.0
    assert ticker["open_interest"] == 567.0


@pytest.mark.asyncio
async def test_v2_ticker_names_take_precedence_over_legacy(tmp_path: Path) -> None:
    """When both shapes are present the v2 names win (REST path convention)."""
    cache = MarketCache(db_path=tmp_path / "t.db")
    frame = dict(_V2_TICKER_FRAME)
    frame["last_price"] = 99  # legacy fallback must lose to last_price_dollars
    frame["volume"] = 77  # ...and to volume_fp

    await apply_ws_message({"type": "ticker", "msg": frame}, cache)

    ticker = cache.get_ticker("KXWETHRM0700M")
    assert ticker is not None
    assert ticker["last_price"] == 55.0
    assert ticker["volume"] == 1234.0
