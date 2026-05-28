"""Live trade position reconciliation — sync local positions DB with Kalshi API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from traderbot.db.positions import (
    delete,
    get,
    list_all,
    update_avg_price,
    update_settlement,
    upsert,
)

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient
    from traderbot.kalshi.models import Fill, Position, Settlement

logger = logging.getLogger(__name__)


async def reconcile_positions(db_path: str, kalshi_client: "KalshiClient") -> dict[str, int]:
    """Fetch open positions/orders from Kalshi and sync local DB.

    For each local position, checks if it still exists on Kalshi.
    - If missing: mark as closed (delete from local DB).
    - If Kalshi has different fill data: update quantity and avg_price.
    - If Kalshi has a new position not in local DB: insert it.

    Also fetches recent fills and applies them to update avg_price/quantity.

    Returns counts dict with keys: updated, closed, added.
    """
    from traderbot.db import get_connection
    from traderbot.kalshi.portfolio import PortfolioService

    counts = {"updated": 0, "closed": 0, "added": 0}

    portfolio_svc = PortfolioService(kalshi_client)

    try:
        api_positions: list[Position] = await portfolio_svc.get_positions(limit=1000)
        api_fills: list[Fill] = await portfolio_svc.get_fills(limit=1000)
    except Exception:
        logger.exception("Failed to fetch portfolio data from Kalshi for reconciliation")
        return counts

    api_pos_by_ticker: dict[str, Position] = {p.ticker: p for p in api_positions}

    with get_connection(db_path) as conn:
        local_positions = list_all(conn)
        local_tickers = {p.ticker for p in local_positions}
        api_tickers = set(api_pos_by_ticker.keys())

        for local in local_positions:
            if local.ticker not in api_tickers:
                logger.info("Closing local position %s (not found on Kalshi)", local.ticker)
                delete(conn, local.ticker)
                counts["closed"] += 1

        for local in local_positions:
            if local.ticker in api_pos_by_ticker:
                api_pos = api_pos_by_ticker[local.ticker]
                if local.quantity != api_pos.quantity or local.avg_price != api_pos.avg_price:
                    logger.info(
                        "Updating local position %s: qty %s→%s, avg_price %s→%s",
                        local.ticker,
                        local.quantity,
                        api_pos.quantity,
                        local.avg_price,
                        api_pos.avg_price,
                    )
                    upsert(conn, api_pos)
                    counts["updated"] += 1

        for ticker, api_pos in api_pos_by_ticker.items():
            if ticker not in local_tickers:
                logger.info("Adding new local position %s from Kalshi", ticker)
                upsert(conn, api_pos)
                counts["added"] += 1

        fill_counts: dict[str, list[Fill]] = {}
        for fill in api_fills:
            fill_counts.setdefault(fill.ticker, []).append(fill)

        for ticker, fills in fill_counts.items():
            local = get(conn, ticker)
            if local is None:
                continue
            total_additional_qty = sum(f.quantity for f in fills)
            if total_additional_qty == 0:
                continue
            weighted_price = sum(f.price * f.quantity for f in fills) // total_additional_qty
            try:
                update_avg_price(conn, ticker, total_additional_qty, weighted_price)
                counts["updated"] += 1
            except ValueError:
                pass

    return counts


async def reconcile_settlements(db_path: str, kalshi_client: "KalshiClient") -> dict[str, int]:
    """Fetch recent settlements from Kalshi and update local DB.

    For each settlement:
    - If the ticker exists locally, update settlement_result and pnl_cents.
    - If the local position no longer exists, log and skip.

    Returns counts dict with keys: settled, skipped.
    """
    from traderbot.db import get_connection
    from traderbot.kalshi.portfolio import PortfolioService

    counts = {"settled": 0, "skipped": 0}

    portfolio_svc = PortfolioService(kalshi_client)

    try:
        settlements: list[Settlement] = await portfolio_svc.get_settlements(limit=1000)
    except Exception:
        logger.exception("Failed to fetch settlements from Kalshi")
        return counts

    with get_connection(db_path) as conn:
        for settlement in settlements:
            local = get(conn, settlement.ticker)
            if local is None:
                logger.debug(
                    "Skipping settlement for %s (not in local DB)", settlement.ticker
                )
                counts["skipped"] += 1
                continue

            if settlement.pnl_cents > 0:
                result = settlement.side == "yes"
            elif settlement.pnl_cents < 0:
                result = settlement.side == "no"
            else:
                result = local.settlement_result

            logger.info(
                "Settling local position %s: result=%s pnl=%s¢",
                settlement.ticker,
                result,
                settlement.pnl_cents,
            )
            update_settlement(conn, settlement.ticker, result, settlement.pnl_cents)
            counts["settled"] += 1

    return counts


async def reconcile_all(db_path: str, kalshi_client: "KalshiClient") -> dict[str, dict[str, int]]:
    """Run both position and settlement reconciliation.

    Returns nested counts: {"positions": {...}, "settlements": {...}}.
    """
    pos_counts = await reconcile_positions(db_path, kalshi_client)
    settlement_counts = await reconcile_settlements(db_path, kalshi_client)
    return {"positions": pos_counts, "settlements": settlement_counts}
