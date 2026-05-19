"""Populate the experiment database with real Kalshi + Open-Meteo data.

Usage: python3 -m experiments.v3.data_sources.populate_db --db experiments/data.db --event-prefix KXHIGH
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import logging
import sqlite3
import time
from datetime import UTC, datetime

from experiments.v3.data_sources.accuracy_calculator import compute_accuracy, save_accuracy
from experiments.v3.data_sources.kalshi_fetcher import (
    create_client,
    extract_prices_at_timestep,
    fetch_market_details,
    fetch_orderbook_snapshot,
    fetch_settled_markets,
    fetch_trade_history,
    save_to_db,
)
from experiments.v3.data_sources.openmeto_fetcher import fetch_forecast_series, save_forecasts
from experiments.v3.db_schema import create_tables
from experiments.v3.ticker_parser import parse_ticker

logger = logging.getLogger(__name__)


async def _populate_async(db_path: str, event_prefix: str = "KXHIGH", max_markets: int = 50) -> None:
    """Async core: fetch real data and populate the database."""
    conn = sqlite3.connect(db_path)
    create_tables(conn)

    # 1. Create Kalshi client and services
    logger.info("Creating Kalshi client...")
    client = create_client()
    from traderbot.kalshi.history import HistoryService
    from traderbot.kalshi.markets import MarketService

    history_svc = HistoryService(client)
    market_svc = MarketService(client)

    # 2. Fetch settled markets
    logger.info("Fetching settled %s markets...", event_prefix)
    markets = await fetch_settled_markets(history_svc, event_prefix)
    logger.info("Found %d markets from API", len(markets))
    markets = markets[:max_markets]

    # 3. For each market, fetch details and store
    stored_count = 0
    for i, market in enumerate(markets):
        ticker = market["ticker"]
        logger.info("[%d/%d] Processing %s", i + 1, len(markets), ticker)

        try:
            # Parse ticker for city, strike_type, threshold, lat, lon, date
            try:
                parsed = parse_ticker(ticker)
            except Exception as e:
                logger.warning("  Skipping %s: ticker parse failed: %s", ticker, e)
                continue

            # Fetch market details (settlement result, strike info)
            details = await fetch_market_details(client, market_svc, ticker)
            if not details:
                logger.warning("  Skipping %s: no details from API", ticker)
                continue

            # Compute resolution timestamp for trade history windows
            date_str = parsed.get("date", "")
            try:
                target_date = datetime.fromisoformat(date_str)
                resolution_ts = int(calendar.timegm(target_date.timetuple()))
            except (ValueError, TypeError):
                resolution_ts = int(time.time())

            # Fetch prices at 5 timesteps (T-4 through T-0)
            timestep_windows: list[tuple[str, str]] = []
            for t in range(5):
                days_before = 4 - t
                window_end = resolution_ts - (days_before * 86400)
                window_start = window_end - 86400
                timestep_windows.append(
                    (datetime.fromtimestamp(window_start, tz=UTC).isoformat(),
                     datetime.fromtimestamp(window_end, tz=UTC).isoformat())
                )

            trades = await fetch_trade_history(
                history_svc, ticker, timestep_windows[0][0], str(resolution_ts)
            )
            prices = extract_prices_at_timestep(trades, timestep_windows) if trades else []

            # Fetch orderbook snapshot
            orderbook = await fetch_orderbook_snapshot(market_svc, ticker)

            # Store market + settlement + prices + orderbook via existing save_to_db
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
            time.sleep(0.5)

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

    logger.info("Done! Stored %d markets.", stored_count)
    conn.close()


def populate_db(db_path: str, event_prefix: str = "KXHIGH", max_markets: int = 50) -> None:
    """Synchronous entry point that runs the async populate logic."""
    asyncio.run(_populate_async(db_path, event_prefix, max_markets))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate experiment DB with real Kalshi + Open-Meteo data")
    parser.add_argument("--db", required=True, help="Path to the SQLite database file")
    parser.add_argument("--event-prefix", default="KXHIGH", help="Kalshi event prefix to fetch (default: KXHIGH)")
    parser.add_argument("--max-markets", type=int, default=50, help="Max markets to fetch (default: 50)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    populate_db(args.db, args.event_prefix, args.max_markets)