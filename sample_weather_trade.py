"""
Sample: NYC weather market workflow
 1. Discover the current NYC weather event + market
 2. Fetch the orderbook
 3. Place a 1-unit limit order
 4. Cancel it immediately

Run:  python sample_weather_trade.py
Requires: KALSHI_API_KEY + KALSHI_PRIVATE_KEY_PEM in env or ~/.traderbot/.env
"""

import asyncio
import logging
import sys

from traderbot.kalshi.client import KalshiClient, AuthenticationError, RateLimitError
from traderbot.kalshi.markets import MarketService
from traderbot.kalshi.models import OrderRequest, OrderSideV2
from traderbot.kalshi.trading import TradingService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sample")


async def main() -> None:
    # ── Phase 0: Authenticated client ──────────────────────────────────
    async with KalshiClient() as client:
        markets = MarketService(client)
        trading = TradingService(client)

        # ── Phase 1: Find today's NYC weather market ───────────────────
        logger.info("Fetching weather markets…")
        resp = await markets.list_markets_by_category("weather", limit=200)

        # Narrow to open NYC-* markets with today's close
        import datetime as dt
        today = dt.date.today()
        today_ts = int(dt.datetime.combine(today, dt.time.min, tzinfo=dt.timezone.utc).timestamp())

        nyc_markets = [
            m for m in resp.markets
            if m.ticker and "NYC" in m.ticker.upper()
            and m.status == "open"
            and m.close_time is not None
            and m.close_time.date() == today
        ]

        if not nyc_markets:
            logger.warning("No open NYC weather markets found for today. Falling back to first open weather market.")
            target = next((m for m in resp.markets if m.status == "open"), None)
            if not target:
                sys.exit("No open weather markets at all. Try again later.")
        else:
            target = nyc_markets[0]

        logger.info("Target market: %s — %s", target.ticker, target.title)

        # ── Phase 2: Fetch the orderbook ───────────────────────────────
        logger.info("Fetching orderbook for %s …", target.ticker)
        ob = await markets.get_orderbook(target.ticker, depth=10)

        best_bid = ob.yes_bids[0] if ob.yes_bids else None
        best_offer = ob.no_bids[0] if ob.no_bids else None  # V2: no_bids = ask side
        logger.info(
            "Orderbook: best bid=%s @ %s¢ | best offer=%s @ %s¢",
            best_bid.size if best_bid else "—",
            best_bid.price_cents if best_bid else "—",
            best_offer.size if best_offer else "—",
            best_offer.price_cents if best_offer else "—",
        )

        if not best_bid:
            logger.warning("No bids on orderbook — can't price a reasonable order.")
            return

        # ── Phase 3: Place a 1-unit bid at the best bid price ──────────
        order = OrderRequest(
            ticker=target.ticker,
            side=OrderSideV2.bid,          # bid = buy YES
            count="1",                     # 1 contract
            price=str(best_bid.price_cents),  # cents as dollar string per V2 API
        )

        try:
            result = await trading.place_order(order)
            logger.info("Order placed: id=%s fill=%s remaining=%s",
                        result.order_id, result.fill_count, result.remaining_count)
        except (AuthenticationError, RateLimitError) as exc:
            logger.error("Order placement failed: %s", exc)
            return

        # ── Phase 4: Cancel the order ──────────────────────────────────
        cancel_result = await trading.cancel_order(result.order_id)
        logger.info("Order cancelled: id=%s reduced_by=%s",
                    cancel_result.order_id, cancel_result.reduced_by)


if __name__ == "__main__":
    asyncio.run(main())