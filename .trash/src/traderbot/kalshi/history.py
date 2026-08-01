"""Historical data service — cutoffs, historical trades, settled markets.

Kalshi partitions data into live and historical tiers.  Markets that settled
before the historical cutoff are archived and only available via the
``/historical/`` endpoints — these return data with different pagination
parameters (``min_settled_ts`` / ``max_settled_ts`` instead of
``status=settled``) and may include fields not present in the live response
shape (e.g. ``settlement_result`` on every market object).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _normalize_market, _normalize_trade, _unix_to_datetime
from traderbot.kalshi.models import (
    CutoffTimestamps,
    Market,
    MarketListResponse,
    TradeListResponse,
)

if TYPE_CHECKING:
    from datetime import datetime

    from traderbot.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


class HistoryService:
    """Fetches historical data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_cutoffs(self, ticker: str) -> CutoffTimestamps:
        """Return cutoff timestamps for a market from the historical database."""
        response = await self._client.get(f"/historical/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        if "market" not in data:
            logger.warning(
                "get_cutoffs: response for %s missing 'market' key — got %s",
                ticker,
                list(data.keys())[:5],
            )
        market_raw = data.get("market", data)

        def _parse_ts(key: str) -> datetime | None:
            val = market_raw.get(key)
            if val is None:
                return None
            return _unix_to_datetime(int(val))

        return CutoffTimestamps(
            market_settled_ts=_parse_ts("market_settled_ts"),
            trade_cutoff_ts=_parse_ts("trade_cutoff_ts"),
            order_cutoff_ts=_parse_ts("order_cutoff_ts"),
        )

    async def get_historical_trades(
        self,
        ticker: str,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> TradeListResponse:
        """Return trades that were filled before the historical cutoff.

        Uses ``GET /historical/trades`` because live ``/markets/trades``
        only returns trades after the cutoff; archived trades require
        the historical endpoint.
        """
        params: dict[str, Any] = {"limit": limit}
        logger.debug(
            "History query: ticker=%s from=%s to=%s limit=%s", ticker, after, before, limit
        )
        if after is not None:
            params["min_ts"] = int(after.timestamp())
        if before is not None:
            params["max_ts"] = int(before.timestamp())
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/historical/trades", ticker=ticker, **params)
        response.raise_for_status()
        data = response.json()
        if "trades" not in data:
            logger.warning(
                "get_historical_trades: response missing 'trades' key for ticker=%s — got %s",
                ticker,
                list(data.keys())[:5],
            )
        trades = [_normalize_trade(t) for t in data.get("trades", [])]
        return TradeListResponse(trades=trades, cursor=data.get("cursor"))

    async def get_settled_markets(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> MarketListResponse:
        """Return markets archived in the historical database.

        Uses ``GET /historical/markets`` because markets that settled before
        the historical cutoff are removed from the live ``/markets`` endpoint.
        The historical endpoint uses ``min_settled_ts``/``max_settled_ts``
        for time-range filtering instead of the ``status`` query param that
        the live endpoint accepts.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/historical/markets", **params)
        response.raise_for_status()
        data = response.json()
        if "markets" not in data:
            logger.warning(
                "get_settled_markets: response missing 'markets' key — got %s",
                list(data.keys())[:5],
            )
        markets = [_normalize_market(m) for m in data.get("markets", [])]
        return MarketListResponse(markets=markets, cursor=data.get("cursor"))

    async def get_market_series(self, ticker: str) -> Market:
        """Return a single historical market by ticker.

        Uses ``GET /historical/markets/{ticker}`` because settled markets
        may no longer be available at the live ``/markets/{ticker}`` endpoint.
        """
        response = await self._client.get(f"/historical/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        if "market" not in data:
            logger.warning(
                "get_market_series: response for %s missing 'market' key — got %s",
                ticker,
                list(data.keys())[:5],
            )
        market_raw = data.get("market", data)
        return _normalize_market(market_raw)
