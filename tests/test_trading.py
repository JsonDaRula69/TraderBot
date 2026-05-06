"""Tests for TradingService — place, cancel, get, and list orders."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr, ValidationError

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
        api_key=SecretStr("test-key"),
        private_key_pem=SecretStr('-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDNjtDWFqzW5zUP\ngtqTevUWEgvoW3iCBruf8qOB21eIEOLKvqQdqMWzInkR1hWZKWrmfDwFGU//fx6C\nPPpB/Mr/EYzc/MsIHm1IqkP03YwbpMYfBX+FHmlIfMUBTrb1WmsJ+ho8n6V/pn9V\nTVI2sL6m6gffKML/VEopp0l3OWvCG5GYxKcAXgo4aMhM573QmPJ2TbGLzsg8SUkx\nGZlYBh2Qtx4VuIJ8Bi6cK/An/Oae8h4AL5/23A82gj8eef8X+szHX++PMS8nS0YK\n2ZmTi4bCi33DB8CPRAH9xzhC0NkLCNqD1hp6VWeky4DnLteQuLITvXuU5GwjkQYl\nLIYUSgbDAgMBAAECggEAK/AZipGJO1xrdpfRUdHn/mI4ImAe96gpxcwvEAxK/v4h\nBBZQ7TgMnjhBqcLZlgYI4CBxEePxuhq5cjxHgABhgbkGI5xzZ5ZdZLlkUjxi/Oux\nH6NkuRchiQmGcLubFwHPPHA12HyFey4jLKAc8SzBa9s9eIF1gO9K9PFZnj7rXi91\nBjaFm6jpHlEDeLY7oCT033HJxi7wvEflCz0J+j4lSf6XUM8rhgiApKOwwsYwFwZT\nynKxyj3rAf8wDHY/vTNdO984T2bD/eEymCyqDnXEY/zzMnrUDMwyRe+cm1HsfvE8\ns83x7EA6EPFwhEf796mCth7fLFbBOlsEMaPGTNjxYQKBgQD4JJbth+jyKihc/L5N\nS/BnGxUxIhKYbTS1uEPDqT5X/aMhgaxGY63AiOwQYoy1gfMN04zjE+dtH4I6ZUWH\nx4WcUlFciBqdVs479iVIMeIVULcwTzSCnWgPVF+fvaB+98oPPEj+USlcWhKTtcHj\nC2voN6qHOTpNQenlE2yIS79JYQKBgQDUEQm3tn2BHMAI5BwFENBmp1AzJgFk64gV\ngKxwUUH7ks5feSXXLc75ZfamR6oD5eGwqon4rFHf9cqg2ZUGhjXu0dQxVqeLSaej\nUzU9uZDnLvAfTRnMuy+nS3dR//Bd3Ee1nTqkQenD8dWi/nwuuQIl7L+EMZkBVqko\nIS73DlsOowKBgGZYAP/a7FLk3FztyTdsOKzt2KG5Id5IPFMuupQ6e4IjFGM/bmRh\nvEoKrwJbAxnhjPOI6zTFAtBZDIc1OaY0voCo2vHFGOUH5muIq/vIxyxva/66zDeK\n4F5iOEZUGZwEaww5mwl5RAvZAox1jJAuJ8VRID5BdjBjHSrkBgF47F5BAoGAZnc9\nDMleZu4vU5x0dXYkXBVnyO8KKWssu8cKitKYYSgUE0mEIS5/HT5JKRrjaTLAFA6y\nz7bjcKVgnMvFF/vtP1Gfh59pIQIbv+zKguKQw0OIvncQij2/zsPGCZby20c+VuB7\nnzZB722AXls8QY8fHJgCCau1VFI9Naii+rizAqUCgYEAuo3UCkhZdyU5yAK431yC\nzUFIT+WIaADq7UKi8+czvIv5SqQv1nNcLHHrzg0NXXDAVFAFwtwD/nho91MKH667\nVAiz14bK+fVXaSbUq1GMTj8QHq8VLRK56iMcY8FyY8mWyHgPa842l5b9ygZktkXg\nfoC58VQaR20DGjpjGUyXpoQ=\n-----END PRIVATE KEY-----\n'),
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
                action="buy",
                side=OrderSide.yes,
                count=10,
                price_cents=55,
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
        respx.get(f"{cfg.active_url}/portfolio/events/orders/ord-001").mock(
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
        respx.get(f"{cfg.active_url}/portfolio/events/orders").mock(
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
        route = respx.get(f"{cfg.active_url}/portfolio/events/orders").mock(
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
        respx.get(f"{cfg.active_url}/portfolio/events/orders").mock(
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
                action="buy",
                side=OrderSide.yes,
                count=10,
                price_cents=100,
            )

    def test_place_order_zero_quantity(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                action="buy",
                side=OrderSide.yes,
                count=0,
                price_cents=55,
            )

    def test_order_request_model_strict(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                action="buy",
                side=OrderSide.yes,
                count=10,
                price_cents=55,
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
        assert OrderStatus.resting.value == "resting"
        assert OrderStatus.matched.value == "matched"
        assert OrderStatus.filled.value == "filled"
        assert OrderStatus.cancelled.value == "cancelled"
        assert OrderStatus.expired.value == "expired"

    def test_order_request_requires_action(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSide.yes,
                count=10,
                price_cents=55,
            )

    def test_order_request_negative_quantity(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                action="buy",
                side=OrderSide.yes,
                count=-1,
                price_cents=55,
            )

    def test_order_request_price_zero(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                action="buy",
                side=OrderSide.yes,
                count=10,
                price_cents=0,
            )

    def test_to_v2_body_maps_price_cents_to_price_dollars(self) -> None:
        req = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            action="buy",
            side=OrderSide.yes,
            count=10,
            price_cents=55,
        )
        body = req.to_v2_body()
        assert body["price_dollars"] == 55
        assert body["ticker"] == "KXBTCD-26MAR31-T55000"
        assert body["side"] == "yes"
        assert "yes_price" not in body
