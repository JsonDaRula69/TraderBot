"""Populate the experiment database with real Kalshi + Open-Meteo data.

Uses event-based market discovery instead of broken /markets pagination.
Probes known KXHIGH event tickers for Apr-Jun 2026 dates, then fetches
each market individually and stores settlement results from the `result` field.

Usage:
    python3 -m experiments.v3.data_sources.populate_db --db experiments/data.db
    python3 -m experiments.v3.data_sources.populate_db --db experiments/data.db --verify-data
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import contextlib
import logging
import sqlite3
import time
from datetime import UTC, datetime

from experiments.v3.data_sources.accuracy_calculator import compute_accuracy, save_accuracy
from experiments.v3.data_sources.kalshi_fetcher import (
    create_client,
    extract_prices_at_timestep,
    fetch_trade_history,
    save_to_db,
)
from experiments.v3.data_sources.openmeto_fetcher import fetch_forecast_series, save_forecasts
from experiments.v3.db_schema import create_tables
from experiments.v3.ticker_parser import parse_ticker

logger = logging.getLogger(__name__)

# ── City prefixes to probe ───────────────────────────────────
CITY_PREFIXES = [
    "KXHIGHAUS", "KXHIGHCHI", "KXHIGHDEN", "KXHIGHLAX", "KXHIGHMIA",
    "KXHIGHNY", "KXHIGHPHIL",
    "KXHIGHTATL", "KXHIGHTBOS", "KXHIGHTDAL", "KXHIGHTDC", "KXHIGHTHOU",
    "KXHIGHTLV", "KXHIGHTMIN", "KXHIGHTSEA", "KXHIGHTSFO", "KXHIGHTPHX",
    "KXHIGHTSATX", "KXHIGHTNOLA", "KXHIGHTOKC", "KXHIGHNYC", "KXHIGHLVX",
]

# ── Dates to probe (Apr-Jun 2026) ────────────────────────────
DATES = [
    "26APR01", "26APR06", "26APR08", "26APR16",
    "26MAY01", "26MAY06", "26MAY07", "26MAY08", "26MAY11",
    "26JUN01", "26JUN07",
]


def _build_event_tickers() -> list[str]:
    """Build all event tickers from city prefixes x dates."""
    tickers = []
    for prefix in CITY_PREFIXES:
        for date in DATES:
            tickers.append(f"{prefix}-{date}")
    return tickers


async def _discover_markets(client) -> list[str]:
    """Probe events API for each city+date combo, collect market tickers."""
    event_tickers = _build_event_tickers()
    discovered: list[str] = []
    hits = 0
    misses = 0

    for event_ticker in event_tickers:
        try:
            resp = await client.get(f"/events/{event_ticker}")
            if resp.status_code == 404:
                misses += 1
                continue
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("event", {}).get("markets", [])
            if markets:
                hits += 1
                for t in markets:
                    if isinstance(t, str) and t not in discovered:
                        discovered.append(t)
                    elif isinstance(t, dict):
                        ticker = t.get("ticker", "")
                        if ticker and ticker not in discovered:
                            discovered.append(ticker)
                logger.info("  Event %s: %d markets", event_ticker, len(markets))
        except Exception as e:
            # 404s are expected for dates with no event — only log real errors
            if "404" not in str(e):
                logger.debug("  Event %s: %s", event_ticker, e)
            misses += 1
            continue

        await asyncio.sleep(0.1)

    logger.info("Event discovery: %d hits, %d misses, %d market tickers", hits, misses, len(discovered))
    return discovered


async def _fetch_market_detail(client, ticker: str) -> dict | None:
    """Fetch a single market by ticker, reading `result` for settlement.

    The Kalshi API returns `result` (yes/no) for settled markets, not
    `settlement_result`. We map it to `settlement_result` for DB storage.
    """
    resp = await client.get(f"/markets/{ticker}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    market = data.get("market", data)

    # Settlement from `result` field — this is the correct Kalshi field
    raw_result = market.get("result")
    settlement_result = None
    if raw_result is not None:
        settlement_result = raw_result.upper() if isinstance(raw_result, str) else str(raw_result).upper()
        if settlement_result not in ("YES", "NO"):
            settlement_result = "YES" if settlement_result == "Y" else "NO"

    # Also check settlement_result as fallback (populated for some markets)
    if settlement_result is None:
        sr = market.get("settlement_result")
        if sr is not None:
            settlement_result = str(sr).upper()

    actual_value = market.get("settlement_value")
    floor_strike = market.get("floor_strike")
    ceiling_strike = market.get("ceiling_strike")
    event_ticker = market.get("event_ticker", "")
    series_ticker = market.get("series_ticker", "")

    close_time_raw = market.get("close_time")
    resolution_date = ""
    if close_time_raw is not None:
        with contextlib.suppress(ValueError, TypeError, OSError):
            resolution_date = datetime.fromtimestamp(int(close_time_raw), tz=UTC).strftime("%Y-%m-%d")

    # Derive city/strike_type from ticker using kalshi_fetcher helpers
    from experiments.v3.data_sources.kalshi_fetcher import (
        _city_from_ticker,
        _strike_type_from_ticker,
        _threshold_from_ticker,
    )

    return {
        "ticker": ticker,
        "city": _city_from_ticker(ticker),
        "strike_type": _strike_type_from_ticker(ticker),
        "floor_strike": float(floor_strike) if floor_strike is not None else None,
        "ceiling_strike": float(ceiling_strike) if ceiling_strike is not None else None,
        "threshold": _threshold_from_ticker(ticker),
        "resolution_date": resolution_date,
        "settlement_result": settlement_result,
        "actual_value": float(actual_value) if actual_value is not None else None,
        "event_ticker": event_ticker,
        "series_ticker": series_ticker,
    }


async def _populate_async(db_path: str, max_markets: int = 200) -> None:
    """Async core: discover markets via events, fetch details, store."""
    conn = sqlite3.connect(db_path)
    create_tables(conn)

    # 1. Create Kalshi client
    logger.info("Creating Kalshi client...")
    client = create_client()
    from traderbot.kalshi.history import HistoryService

    history_svc = HistoryService(client)

    # 2. Discover market tickers from events
    logger.info("Discovering KXHIGH markets via event probes...")
    market_tickers = await _discover_markets(client)
    logger.info("Discovered %d market tickers", len(market_tickers))

    if not market_tickers:
        logger.warning("No markets discovered. Check API connectivity and city/date lists.")
        conn.close()
        return

    market_tickers = market_tickers[:max_markets]

    # 3. For each market, fetch details and store
    stored_count = 0
    skipped_parse = 0
    skipped_no_result = 0

    for i, ticker in enumerate(market_tickers):
        logger.info("[%d/%d] Processing %s", i + 1, len(market_tickers), ticker)

        try:
            # Parse ticker for city, strike_type, threshold, lat, lon, date
            try:
                parsed = parse_ticker(ticker)
            except Exception as e:
                logger.warning("  Skipping %s: ticker parse failed: %s", ticker, e)
                skipped_parse += 1
                continue

            # Fetch market details (settlement from `result` field)
            details = await _fetch_market_detail(client, ticker)
            if not details:
                logger.warning("  Skipping %s: no details from API", ticker)
                continue

            if not details.get("settlement_result"):
                skipped_no_result += 1
                logger.info("  %s: no settlement result yet (status may not be finalized)", ticker)

            # Compute resolution timestamp for trade history windows
            date_str = parsed.get("date", "")
            try:
                target_date = datetime.fromisoformat(date_str)
                resolution_ts = int(calendar.timegm(target_date.timetuple()))
            except (ValueError, TypeError):
                resolution_ts = int(time.time())

            # Fetch prices at 5 timesteps (T-4 through T-0)
            timestep_windows: list[tuple[str, str]] = []
            ts_windows: list[tuple[int, int]] = []
            for t in range(5):
                days_before = 4 - t
                window_end = resolution_ts - (days_before * 86400)
                window_start = window_end - 86400
                timestep_windows.append(
                    (datetime.fromtimestamp(window_start, tz=UTC).isoformat(),
                     datetime.fromtimestamp(window_end, tz=UTC).isoformat())
                )
                ts_windows.append((window_start, window_end))

            trades = await fetch_trade_history(
                history_svc, ticker, ts_windows[0][0], resolution_ts
            )
            prices = extract_prices_at_timestep(trades, timestep_windows) if trades else []

            # No orderbook for settled markets (they're closed)
            orderbook: dict = {}

            # Store market + settlement + prices
            save_to_db(conn, details, prices, orderbook)

            # Fetch Open-Meteo forecasts
            lat = parsed.get("lat")
            lon = parsed.get("lon")
            if lat and lon and date_str:
                try:
                    forecasts = fetch_forecast_series(lat, lon, date_str)
                    if forecasts:
                        save_forecasts(conn, ticker, forecasts)
                except Exception as e:
                    logger.warning("  Open-Meteo fetch failed for %s: %s", ticker, e)

            stored_count += 1
            conn.commit()

            # Rate limit courtesy
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error("  Error processing %s: %s", ticker, e)
            continue

    # 4. Compute forecast accuracy
    logger.info("Computing forecast accuracy...")
    try:
        accuracy_rows = compute_accuracy(conn)
        if accuracy_rows:
            save_accuracy(conn, accuracy_rows)
            conn.commit()
            logger.info("  Stored accuracy for %d city/lead-time pairs", len(accuracy_rows))
    except Exception as e:
        logger.warning("  Accuracy computation skipped: %s", e)

    logger.info(
        "Done! Stored %d markets (%d parse-skipped, %d no-result).",
        stored_count, skipped_parse, skipped_no_result,
    )
    conn.close()


def populate_db(db_path: str, max_markets: int = 200) -> None:
    """Synchronous entry point that runs the async populate logic."""
    asyncio.run(_populate_async(db_path, max_markets))


def verify_data(db_path: str) -> None:
    """Check database contents and print summary."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM markets")
    market_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM markets WHERE settlement_result IS NOT NULL")
    settled_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(DISTINCT city) FROM markets")
    city_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM forecast_snapshots")
    forecast_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM settlement_results")
    settlement_count = cursor.fetchone()[0]

    cursor = conn.execute(
        "SELECT city, COUNT(*) as cnt FROM markets GROUP BY city ORDER BY cnt DESC LIMIT 10"
    )
    city_breakdown = cursor.fetchall()

    cursor = conn.execute(
        "SELECT settlement_result, COUNT(*) FROM markets WHERE settlement_result IS NOT NULL GROUP BY settlement_result"
    )
    result_breakdown = cursor.fetchall()

    print(f"\n  Database: {db_path}")
    print(f"  Markets: {market_count}")
    print(f"  Settled (with result): {settled_count}")
    print(f"  Cities: {city_count}")
    print(f"  Forecasts: {forecast_count}")
    print(f"  Settlement records: {settlement_count}")
    print("\n  Top cities:")
    for city, cnt in city_breakdown:
        print(f"    {city}: {cnt}")
    print("\n  Settlement breakdown:")
    for result, cnt in result_breakdown:
        print(f"    {result}: {cnt}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Populate experiment DB with real Kalshi data via event-based discovery"
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database file")
    parser.add_argument(
        "--max-markets", type=int, default=200,
        help="Max markets to fetch (default: 200)",
    )
    parser.add_argument(
        "--verify-data", action="store_true",
        help="Print database summary and exit",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")

    if args.verify_data:
        verify_data(args.db)
    else:
        populate_db(args.db, args.max_markets)
