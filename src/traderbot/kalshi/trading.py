"""Order placement service — create, cancel, and track Kalshi portfolio orders."""

from typing import Any

from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.models import (
    CancelResponse,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderSideV2,
    OrderStatus,
    OrderType,
    TradingOrder,
)


class TradingService:
    """Manages portfolio orders on Kalshi via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """Submit a new order via the V2 endpoint and return the response.

        Uses Create Order (V2) at /portfolio/events/orders/v2 with
        dollar-based fixed-point pricing per the Kalshi API spec.
        """
        body = order_request.to_v2_body()
        response = await self._client.post("/portfolio/events/orders/v2", **body)
        response.raise_for_status()
        data = response.json()
        return OrderResult(
            order_id=data["order_id"],
            client_order_id=data.get("client_order_id"),
            fill_count=data.get("fill_count", "0"),
            remaining_count=data.get("remaining_count", "0"),
            average_fill_price=data.get("average_fill_price"),
            ts_ms=data.get("ts_ms"),
        )

    async def cancel_order(self, order_id: str) -> CancelResponse:
        """Cancel an existing order by ID."""
        response = await self._client.delete(f"/portfolio/events/orders/{order_id}")
        response.raise_for_status()
        data = response.json()
        return CancelResponse(
            order_id=data["order_id"],
            status=None,
            reduced_by=data.get("reduced_by"),
        )

    async def get_order(self, order_id: str) -> TradingOrder:
        """Retrieve a single order by ID."""
        response = await self._client.get(f"/portfolio/orders/{order_id}")
        response.raise_for_status()
        data = response.json()
        order_data = data.get("order", data)
        return self._parse_order(order_data)

    async def list_orders(self, ticker: str | None = None) -> list[TradingOrder]:
        """List all orders, optionally filtered by ticker."""
        params: dict[str, Any] = {}
        if ticker is not None:
            params["ticker"] = ticker

        response = await self._client.get("/portfolio/orders", **params)
        response.raise_for_status()
        data = response.json()
        orders_raw = data.get("orders", [])
        return [self._parse_order(o) for o in orders_raw]

    @staticmethod
    def _parse_order(raw: dict[str, Any]) -> TradingOrder:
        """Normalize a raw API order dict into a TradingOrder model."""
        created_time = raw.get("created_time")
        if isinstance(created_time, int):
            from datetime import UTC, datetime

            created_time = datetime.fromtimestamp(created_time, tz=UTC)

        # Legacy Order schema: yes_price_dollars/no_price_dollars, price_dollars/price_fp
        price_dollars = (
            raw.get("yes_price_dollars")
            or raw.get("no_price_dollars")
            or raw.get("price_dollars")
            or raw.get("price_fp")
        )
        price = round(float(price_dollars) * 100) if price_dollars is not None else 0

        # Legacy Order schema: initial_count_fp, falling back to count_fp
        initial_count = raw.get("initial_count_fp") or raw.get("count_fp")
        quantity = int(initial_count) if initial_count is not None else 0

        # Map V2 bid/ask → internal yes/no
        raw_side = raw.get("side", "yes")
        if raw_side in (OrderSideV2.bid.value, OrderSideV2.bid):
            side = OrderSide.yes
        elif raw_side in (OrderSideV2.ask.value, OrderSideV2.ask):
            side = OrderSide.no
        else:
            side = OrderSide(raw_side)

        # Legacy fill count: fill_count_fp (string) or filled_quantity (int)
        fill_count_fp = raw.get("fill_count_fp")
        filled_quantity = int(fill_count_fp) if fill_count_fp is not None else int(raw.get("filled_quantity", 0))

        return TradingOrder(
            order_id=raw["order_id"],
            ticker=raw["ticker"],
            side=side,
            order_type=OrderType(raw.get("order_type", "limit")),
            quantity=quantity,
            price=price,
            status=OrderStatus(raw.get("status", "live")),
            created_time=created_time,
            filled_quantity=filled_quantity,
        )
