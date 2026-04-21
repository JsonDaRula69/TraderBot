"""Order placement service — create, cancel, and track Kalshi portfolio orders."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi.models import (
    CancelResponse,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingOrder,
)

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


class TradingService:
    """Manages portfolio orders on Kalshi via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def place_order(self, order_request: OrderRequest) -> TradingOrder:
        """Submit a new order and return the created order."""
        body: dict[str, Any] = {
            "ticker": order_request.ticker,
            "side": order_request.side.value,
            "order_type": order_request.order_type.value,
            "quantity": order_request.quantity,
            "price": order_request.price,
        }
        response = await self._client.post("/portfolio/orders", **body)
        response.raise_for_status()
        data = response.json()
        order_data = data.get("order", data)
        return self._parse_order(order_data)

    async def cancel_order(self, order_id: str) -> CancelResponse:
        """Cancel an existing order by ID."""
        response = await self._client._request("DELETE", f"/portfolio/orders/{order_id}")
        response.raise_for_status()
        data = response.json()
        return CancelResponse(
            order_id=data["order_id"],
            status=OrderStatus(data["status"]),
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

        return TradingOrder(
            order_id=raw["order_id"],
            ticker=raw["ticker"],
            side=OrderSide(raw.get("side", "yes")),
            order_type=OrderType(raw.get("order_type", "limit")),
            quantity=int(raw.get("quantity", 0)),
            price=int(raw.get("price", 0)),
            status=OrderStatus(raw.get("status", "live")),
            created_time=created_time,
            filled_quantity=int(raw.get("filled_quantity", 0)),
        )
