"""Tests for TradingService — place, cancel, get, and list orders."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import ValidationError

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.models import (
    CancelResponse,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingOrder,
)
from traderbot.kalshi.trading import TradingService

CREATED_TIME_INT = 1745150400
CREATED_TIME_DT = datetime(2025, 4, 20, 12, 0, 0, tzinfo=UTC)


def _make_config() -> KalshiConfig:
    return KalshiConfig(
        api_key="test-key",
        api_secret="test-secret",
        rate_limit_rps=10.0,
        retry_base_delay=0.01,
    )


SAMPLE_ORDER_RAW = {
    "order_id": "ord-001",
    "ticker": "KXBTCD-26MAR31-T55000",
    "side": "yes",
    "order_type": "limit",
    "quantity": 10,
    "price": 55,
    "status": "live",
    "created_time": CREATED_TIME_INT,
    "filled_quantity": 0,
}


class TestPlaceOrder:
    @respx.mock
    async def test_place_order_success(self) -> None:
        cfg = _make_config()
        respx.post(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": SAMPLE_ORDER_RAW})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            order_request = OrderRequest(
                ticker="KXBTCD-26MAR31-T55000",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=10,
                price=55,
            )
            result = await service.place_order(order_request)

        assert isinstance(result, TradingOrder)
        assert result.order_id == "ord-001"
        assert result.ticker == "KXBTCD-26MAR31-T55000"
        assert result.side == OrderSide.yes
        assert result.order_type == OrderType.limit
        assert result.quantity == 10
        assert result.price == 55
        assert result.status == OrderStatus.live
        assert result.created_time == CREATED_TIME_DT
        assert result.filled_quantity == 0


class TestCancelOrder:
    @respx.mock
    async def test_cancel_order_success(self) -> None:
        cfg = _make_config()
        respx.delete(f"{cfg.active_url}/portfolio/orders/ord-001").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-001", "status": "cancelled"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            result = await service.cancel_order("ord-001")

        assert isinstance(result, CancelResponse)
        assert result.order_id == "ord-001"
        assert result.status == OrderStatus.cancelled

    @respx.mock
    async def test_cancel_order_not_found(self) -> None:
        cfg = _make_config()
        respx.delete(f"{cfg.active_url}/portfolio/orders/nonexistent").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            with pytest.raises(httpx.HTTPStatusError):
                await service.cancel_order("nonexistent")


class TestGetOrder:
    @respx.mock
    async def test_get_order_success(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/portfolio/orders/ord-001").mock(
            return_value=httpx.Response(200, json={"order": SAMPLE_ORDER_RAW})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            result = await service.get_order("ord-001")

        assert isinstance(result, TradingOrder)
        assert result.order_id == "ord-001"
        assert result.side == OrderSide.yes
        assert result.price == 55


class TestListOrders:
    @respx.mock
    async def test_list_orders_success(self) -> None:
        order_raw_2 = {
            "order_id": "ord-002",
            "ticker": "KXBTCD-26MAR31-T55000",
            "side": "no",
            "order_type": "market",
            "quantity": 5,
            "price": 45,
            "status": "matched",
            "created_time": CREATED_TIME_INT,
            "filled_quantity": 5,
        }
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": [SAMPLE_ORDER_RAW, order_raw_2]})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            result = await service.list_orders()

        assert len(result) == 2
        assert result[0].order_id == "ord-001"
        assert result[1].order_id == "ord-002"
        assert result[1].side == OrderSide.no
        assert result[1].filled_quantity == 5

    @respx.mock
    async def test_list_orders_by_ticker(self) -> None:
        cfg = _make_config()
        route = respx.get(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": [SAMPLE_ORDER_RAW]})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            await service.list_orders(ticker="KXBTCD-26MAR31-T55000")

        request_url = str(route.calls[0].request.url)
        assert "ticker=KXBTCD-26MAR31-T55000" in request_url

    @respx.mock
    async def test_list_orders_empty(self) -> None:
        cfg = _make_config()
        respx.get(f"{cfg.active_url}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            result = await service.list_orders()

        assert result == []


class TestOrderRequestValidation:
    def test_order_side_enum(self) -> None:
        assert OrderSide.yes.value == "yes"
        assert OrderSide.no.value == "no"

    def test_order_type_enum(self) -> None:
        assert OrderType.limit.value == "limit"
        assert OrderType.market.value == "market"

    def test_place_order_invalid_price(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=10,
                price=100,
            )

    def test_place_order_zero_quantity(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=0,
                price=55,
            )

    def test_order_request_model_strict(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=10,
                price=55,
                extra_field="bad",
            )


class TestModelStrictness:
    def test_trading_order_model_strict(self) -> None:
        with pytest.raises(ValidationError):
            TradingOrder(
                order_id="ord-001",
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=10,
                price=55,
                status=OrderStatus.live,
                created_time=CREATED_TIME_DT,
                filled_quantity=0,
                extra_field="bad",
            )

    def test_cancel_response_model_strict(self) -> None:
        with pytest.raises(ValidationError):
            CancelResponse(
                order_id="ord-001",
                status=OrderStatus.cancelled,
                extra_field="bad",
            )

    def test_order_status_enum(self) -> None:
        assert OrderStatus.live.value == "live"
        assert OrderStatus.matched.value == "matched"
        assert OrderStatus.cancelled.value == "cancelled"
        assert OrderStatus.expired.value == "expired"

    def test_order_request_negative_quantity(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=-1,
                price=55,
            )

    def test_order_request_price_zero(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                order_type=OrderType.limit,
                quantity=10,
                price=0,
            )
