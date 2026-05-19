"""Fetch real Kalshi market data via TraderBot's existing API adapter."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from traderbot.kalshi.client import KalshiClient

if TYPE_CHECKING:
    from traderbot.kalshi.history import HistoryService
    from traderbot.kalshi.markets import MarketService

_KXHIGH_CITY_MAP: dict[str, str] = {
    "KXHIGHNY": "New York",
    "KXHIGHPHIL": "Philadelphia",
    "KXHIGHTPHX": "Phoenix",
    "KXHIGHTMIN": "Minneapolis",
    "KXHIGHTSEA": "Seattle",
    "KXHIGHTCHI": "Chicago",
    "KXHIGHCHI": "Chicago",
    "KXHIGHTHOU": "Houston",
    "KXHIGHTLA": "Los Angeles",
    "KXHIGHLAX": "Los Angeles",
    "KXHIGHTMIA": "Miami",
    "KXHIGHMIA": "Miami",
    "KXHIGHTDEN": "Denver",
    "KXHIGHDEN": "Denver",
    "KXHIGHTATL": "Atlanta",
    "KXHIGHTBOS": "Boston",
    "KXHIGHTDAL": "Dallas",
    "KXHIGHTDET": "Detroit",
    "KXHIGHTSF": "San Francisco",
    "KXHIGHAUS": "Austin",
    "KXHIGHTDC": "Washington DC",
    "KXHIGHTLV": "Las Vegas",
}


def _city_from_ticker(ticker: str) -> str:
    prefix = ticker.split("-")[0]
    return _KXHIGH_CITY_MAP.get(prefix, "Unknown")


def _strike_type_from_ticker(ticker: str) -> str:
    parts = ticker.split("-")
    if len(parts) < 3:
        return "unknown"
    strike_part = parts[-1]
    if strike_part.startswith("T"):
        return "greater"
    if strike_part.startswith("B"):
        return "between"
    if strike_part.startswith("L"):
        return "less"
    return "unknown"


def _threshold_from_ticker(ticker: str) -> float:
    parts = ticker.split("-")
    if len(parts) < 3:
        return 0.0
    strike_part = parts[-1]
    if strike_part.startswith("T"):
        val = strike_part[1:]
        return float(val) if val else 0.0
    if strike_part.startswith("B"):
        val = strike_part[1:]
        n = float(val) if val else 0.0
        return n + 0.5 if n.is_integer() else n
    if strike_part.startswith("L"):
        val = strike_part[1:]
        return float(val) if val else 0.0
    return 0.0


def create_client() -> KalshiClient:
    api_key = os.getenv("KALSHI_API_KEY")
    pem = os.getenv("KALSHI_PRIVATE_KEY_PEM")
    if not api_key:
        raise RuntimeError("KALSHI_API_KEY environment variable not set")
    if not pem:
        raise RuntimeError("KALSHI_PRIVATE_KEY_PEM environment variable not set")
    from pydantic import SecretStr

    from traderbot.kalshi.client import KalshiConfig

    config = KalshiConfig(
        api_key=SecretStr(api_key),
        private_key_pem=SecretStr(pem),
    )
    return KalshiClient(config=config)


async def fetch_settled_markets(
    history_svc: HistoryService,
    event_prefix: str = "KXHIGH",
) -> list[dict]:
    """Legacy: paginates all settled markets. Too slow for old KXHIGH markets."""
    all_markets: list[dict] = []
    cursor = None
    while True:
        resp = await history_svc.get_settled_markets(cursor=cursor, limit=100)
        for m in resp.markets:
            if m.event_ticker and m.event_ticker.startswith(event_prefix):
                all_markets.append({
                    "ticker": m.ticker,
                    "settlement": m.settlement_result,
                    "city": _city_from_ticker(m.ticker),
                    "strike_type": _strike_type_from_ticker(m.ticker),
                    "threshold": _threshold_from_ticker(m.ticker),
                })
        cursor = resp.cursor
        if not cursor:
            break
    return all_markets


async def fetch_kxhigh_markets(
    client: KalshiClient,
    series_prefixes: list[str] | None = None,
    max_per_series: int = 100,
) -> list[dict]:
    """Fetch KXHIGH markets via per-series API queries instead of global pagination."""
    if series_prefixes is None:
        series_prefixes = list(_KXHIGH_CITY_MAP.keys())

    all_markets: list[dict] = []
    seen_tickers: set[str] = set()

    for prefix in series_prefixes:
        try:
            resp = await client.get(
                "/markets",
                params={"series_ticker": prefix, "status": "settled", "limit": max_per_series},
            )
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", [])

            for m in markets:
                ticker = m.get("ticker", "")
                if ticker and ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    all_markets.append({
                        "ticker": ticker,
                        "settlement": m.get("settlement_result"),
                        "city": _city_from_ticker(ticker),
                        "strike_type": _strike_type_from_ticker(ticker),
                        "threshold": _threshold_from_ticker(ticker),
                    })

            # Also try finalized markets for this series
            resp2 = await client.get(
                "/markets",
                params={"series_ticker": prefix, "status": "finalized", "limit": max_per_series},
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            markets2 = data2.get("markets", [])

            for m in markets2:
                ticker = m.get("ticker", "")
                if ticker and ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    all_markets.append({
                        "ticker": ticker,
                        "settlement": m.get("settlement_result"),
                        "city": _city_from_ticker(ticker),
                        "strike_type": _strike_type_from_ticker(ticker),
                        "threshold": _threshold_from_ticker(ticker),
                    })

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to fetch series %s: %s", prefix, e)
            continue

    return all_markets


async def fetch_market_details(
    client: KalshiClient,
    market_svc: MarketService,
    ticker: str,
) -> dict:
    raw_resp = await client.get(f"/markets/{ticker}")
    raw_resp.raise_for_status()
    raw = raw_resp.json()
    market_raw = raw.get("market", raw)

    settlement_result = market_raw.get("settlement_result")
    actual_value = market_raw.get("settlement_value")

    floor_strike = market_raw.get("floor_strike")
    ceiling_strike = market_raw.get("ceiling_strike")

    event_ticker = market_raw.get("event_ticker", "")
    series_ticker = market_raw.get("series_ticker", "")

    close_time_raw = market_raw.get("close_time")
    resolution_date = ""
    if close_time_raw is not None:
        with contextlib.suppress(ValueError, TypeError, OSError):
            resolution_date = datetime.fromtimestamp(int(close_time_raw), tz=UTC).strftime("%Y-%m-%d")

    return {
        "ticker": ticker,
        "city": _city_from_ticker(ticker),
        "strike_type": _strike_type_from_ticker(ticker),
        "floor_strike": float(floor_strike) if floor_strike is not None else None,
        "ceiling_strike": float(ceiling_strike) if ceiling_strike is not None else None,
        "threshold": _threshold_from_ticker(ticker),
        "resolution_date": resolution_date,
        "settlement_result": str(settlement_result) if settlement_result is not None else None,
        "actual_value": float(actual_value) if actual_value is not None else None,
        "event_ticker": event_ticker,
        "series_ticker": series_ticker,
    }


async def fetch_trade_history(
    history_svc: HistoryService,
    ticker: str,
    start_ts: int,
    end_ts: int,
) -> list[dict]:
    after = datetime.fromtimestamp(start_ts, tz=UTC)
    before = datetime.fromtimestamp(end_ts, tz=UTC)

    all_trades: list[dict] = []
    cursor = None
    while True:
        resp = await history_svc.get_historical_trades(
            ticker,
            after=after,
            before=before,
            limit=100,
            cursor=cursor,
        )
        for t in resp.trades:
            price_pct = t.price / 100.0
            all_trades.append({
                "timestamp": t.timestamp.isoformat(),
                "yes_price": price_pct if t.side == "yes" else round(1.0 - price_pct, 2),
                "no_price": price_pct if t.side == "no" else round(1.0 - price_pct, 2),
                "count": t.quantity,
            })
        cursor = resp.cursor
        if not cursor:
            break
    return all_trades


async def fetch_orderbook_snapshot(
    market_svc: MarketService,
    ticker: str,
) -> dict:
    ob = await market_svc.get_orderbook(ticker, depth=10)

    yes_bids_json = json.dumps([{"price": lvl.price, "size": lvl.size} for lvl in ob.yes_bids])
    no_bids_json = json.dumps([{"price": lvl.price, "size": lvl.size} for lvl in ob.no_bids])

    best_yes = ob.yes_bids[0].price if ob.yes_bids else None
    best_no = ob.no_bids[0].price if ob.no_bids else None

    implied_prob = None
    if best_yes is not None:
        implied_prob = best_yes / 100.0

    return {
        "yes_bids_json": yes_bids_json,
        "no_bids_json": no_bids_json,
        "best_yes_bid": implied_prob if implied_prob is not None else None,
        "best_no_bid": (best_no / 100.0) if best_no is not None else None,
        "implied_prob": implied_prob,
    }


def extract_prices_at_timestep(
    trades: list[dict],
    timestep_windows: list[tuple[str, str]],
) -> list[dict]:
    results: list[dict] = []
    for i, (start_str, end_str) in enumerate(timestep_windows, start=1):
        start_dt = datetime.fromisoformat(start_str)
        end_dt = datetime.fromisoformat(end_str)

        last_trade: dict | None = None
        for t in trades:
            t_dt = datetime.fromisoformat(t["timestamp"])
            if start_dt <= t_dt < end_dt:
                last_trade = t

        if last_trade is not None:
            results.append({
                "timestep": i,
                "yes_price": last_trade["yes_price"],
                "no_price": last_trade["no_price"],
                "trade_count": last_trade.get("count", 0),
            })
    return results


def save_to_db(
    conn: sqlite3.Connection,
    market: dict,
    prices: list[dict],
    orderbook: dict,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO markets
           (ticker, city, strike_type, floor_strike, ceiling_strike, threshold,
            resolution_date, settlement_result, actual_value, event_ticker, series_ticker)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            market["ticker"],
            market.get("city"),
            market.get("strike_type"),
            market.get("floor_strike"),
            market.get("ceiling_strike"),
            market.get("threshold"),
            market.get("resolution_date"),
            market.get("settlement_result"),
            market.get("actual_value"),
            market.get("event_ticker"),
            market.get("series_ticker"),
        ),
    )

    if market.get("actual_value") is not None or market.get("settlement_result") is not None:
        conn.execute(
            """INSERT OR REPLACE INTO settlement_results
               (ticker, actual_temp_f, settlement_result, settlement_source)
               VALUES (?, ?, ?, ?)""",
            (
                market["ticker"],
                market.get("actual_value"),
                market.get("settlement_result"),
                "kalshi",
            ),
        )

    for p in prices:
        conn.execute(
            """INSERT INTO market_prices
               (ticker, timestep, yes_price, no_price, trade_count, open_interest, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                market["ticker"],
                p.get("timestep", 0),
                p.get("yes_price"),
                p.get("no_price"),
                p.get("trade_count", 0),
                p.get("open_interest", 0),
                datetime.now(UTC).isoformat(),
            ),
        )

    if orderbook:
        conn.execute(
            """INSERT INTO orderbook_snapshots
               (ticker, timestep, yes_bids_json, no_bids_json, best_yes_bid, best_no_bid, implied_prob)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                market["ticker"],
                0,
                orderbook.get("yes_bids_json", "[]"),
                orderbook.get("no_bids_json", "[]"),
                orderbook.get("best_yes_bid"),
                orderbook.get("best_no_bid"),
                orderbook.get("implied_prob"),
            ),
        )

    conn.commit()
