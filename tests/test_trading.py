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
    OrderResult,
    OrderSide,
    OrderSideV2,
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
    "side": "bid",
    "order_type": "limit",
    "yes_price_dollars": "0.5500",
    "initial_count_fp": "10",
    "fill_count_fp": "0",
    "status": "live",
    "created_time": CREATED_TIME_INT,
}


class TestPlaceOrder:
    @respx.mock
    async def test_place_order_success(self) -> None:
        v2_create_response = {
            "order_id": "ord-001",
            "client_order_id": "client-abc",
            "fill_count": "0",
            "remaining_count": "10",
            "average_fill_price": None,
            "ts_ms": 1745150400000,
        }
        cfg = _make_config()
        respx.post(f"{cfg.base_url}/portfolio/events/orders/v2").mock(
            return_value=httpx.Response(200, json=v2_create_response)
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            order_request = OrderRequest(
                ticker="KXBTCD-26MAR31-T55000",
                side=OrderSideV2.bid,
                count="10",
                price="0.55",
            )
            result = await service.place_order(order_request)

        assert isinstance(result, OrderResult)
        assert result.order_id == "ord-001"
        assert result.client_order_id == "client-abc"
        assert result.fill_count == "0"
        assert result.remaining_count == "10"
        assert result.average_fill_price is None
        assert result.ts_ms == 1745150400000


class TestCancelOrder:
    @respx.mock
    async def test_cancel_order_success(self) -> None:
        cfg = _make_config()
        respx.delete(f"{cfg.base_url}/portfolio/events/orders/ord-001").mock(
            return_value=httpx.Response(200, json={"order_id": "ord-001", "client_order_id": "client-abc", "reduced_by": "0", "ts_ms": 1745150401000})
        )
        async with KalshiClient(cfg) as client:
            client._session_token = "tok"
            service = TradingService(client)
            result = await service.cancel_order("ord-001")

        assert isinstance(result, CancelResponse)
        assert result.order_id == "ord-001"
        assert result.status is None
        assert result.reduced_by == "0"

    @respx.mock
    async def test_cancel_order_not_found(self) -> None:
        cfg = _make_config()
        respx.delete(f"{cfg.base_url}/portfolio/events/orders/nonexistent").mock(
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
        respx.get(f"{cfg.base_url}/portfolio/orders/ord-001").mock(
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
            "side": "ask",
            "order_type": "market",
            "initial_count_fp": "5",
            "no_price_dollars": "0.4500",
            "fill_count_fp": "5",
            "status": "matched",
            "created_time": CREATED_TIME_INT,
        }
        cfg = _make_config()
        respx.get(f"{cfg.base_url}/portfolio/orders").mock(
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
        route = respx.get(f"{cfg.base_url}/portfolio/orders").mock(
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
        respx.get(f"{cfg.base_url}/portfolio/orders").mock(
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

    def test_order_side_v2_enum(self) -> None:
        assert OrderSideV2.bid.value == "bid"
        assert OrderSideV2.ask.value == "ask"

    def test_order_type_enum(self) -> None:
        assert OrderType.limit.value == "limit"
        assert OrderType.market.value == "market"

    def test_order_request_model_strict(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                ticker="KX",
                side=OrderSideV2.bid,
                count="10",
                price="0.55",
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

    def test_to_v2_body_maps_fields(self) -> None:
        req = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="10",
            price="0.5500",
        )
        body = req.to_v2_body()
        assert body["price"] == "0.5500"
        assert body["count"] == "10"
        assert body["side"] == "bid"
        assert body["ticker"] == "KXBTCD-26MAR31-T55000"
        assert "client_order_id" in body
        assert body["time_in_force"] == "good_till_canceled"
        assert body["self_trade_prevention_type"] == "taker_at_cross"
        assert "yes_price" not in body
        assert "no_price" not in body
        assert "count_fp" not in body
        assert "price_dollars" not in body

    def test_to_v2_body_auto_generates_client_order_id(self) -> None:
        req = OrderRequest(
            ticker="KX",
            side=OrderSideV2.ask,
            count="5",
            price="0.45",
        )
        body = req.to_v2_body()
        assert body["client_order_id"]  # auto-generated UUID4

    def test_to_v2_body_uses_provided_client_order_id(self) -> None:
        req = OrderRequest(
            ticker="KX",
            side=OrderSideV2.bid,
            count="5",
            price="0.45",
            client_order_id="custom-id-123",
        )
        body = req.to_v2_body()
        assert body["client_order_id"] == "custom-id-123"


class TestParseOrder:
    @staticmethod
    def _base() -> dict:
        return {
            "order_id": "ord-001",
            "ticker": "KXBTCD-26MAR31-T55000",
            "side": "bid",
            "order_type": "limit",
            "yes_price_dollars": "0.5500",
            "initial_count_fp": "10",
            "fill_count_fp": "0",
            "status": "live",
            "created_time": CREATED_TIME_INT,
        }

    def test_all_v2_fields(self) -> None:
        order = TradingService._parse_order(self._base())
        assert order.order_id == "ord-001"
        assert order.ticker == "KXBTCD-26MAR31-T55000"
        assert order.side == OrderSide.yes
        assert order.order_type == OrderType.limit
        assert order.quantity == 10
        assert order.price == 55
        assert order.status == OrderStatus.live
        assert order.created_time == CREATED_TIME_DT
        assert order.filled_quantity == 0

    def test_price_fp_instead_of_price_dollars(self) -> None:
        raw = {
            **self._base(),
            "yes_price_dollars": None,
            "no_price_dollars": None,
            "price_dollars": None,
            "price_fp": "0.6600",
        }
        order = TradingService._parse_order(raw)
        assert order.price == 66

    def test_bid_side_maps_to_yes(self) -> None:
        raw = {**self._base(), "side": "bid"}
        order = TradingService._parse_order(raw)
        assert order.side == OrderSide.yes

    def test_ask_side_maps_to_no(self) -> None:
        raw = {**self._base(), "side": "ask"}
        order = TradingService._parse_order(raw)
        assert order.side == OrderSide.no

    def test_missing_created_time_raises_validation_error(self) -> None:
        raw = self._base()
        del raw["created_time"]
        with pytest.raises(ValidationError):
            TradingService._parse_order(raw)

    def test_unknown_order_type_raises_value_error(self) -> None:
        raw = {**self._base(), "order_type": "weird_custom_type"}
        with pytest.raises(ValueError, match="is not a valid OrderType"):
            TradingService._parse_order(raw)

    def test_unknown_side_falls_back_to_raw_value(self) -> None:
        """When side is not bid/ask, it passes through OrderSide(raw_side)."""
        raw = {**self._base(), "side": "no"}
        order = TradingService._parse_order(raw)
        assert order.side == OrderSide.no

    def test_empty_price_raises_validation_error(self) -> None:
        raw = {**self._base(), "yes_price_dollars": None, "no_price_dollars": None, "price_dollars": None, "price_fp": None}
        with pytest.raises(ValidationError):
            TradingService._parse_order(raw)

    def test_empty_count_returns_zero(self) -> None:
        raw = {**self._base(), "initial_count_fp": None, "count_fp": None}
        order = TradingService._parse_order(raw)
        assert order.quantity == 0

    def test_status_defaults_to_live(self) -> None:
        raw = self._base().copy()
        del raw["status"]
        order = TradingService._parse_order(raw)
        assert order.status == OrderStatus.live

    def test_created_time_str_rejected_by_model(self) -> None:
        raw = {**self._base(), "created_time": "2025-04-20T12:00:00Z"}
        with pytest.raises(ValidationError):
            TradingService._parse_order(raw)

    def test_ask_enum_value_maps_to_no(self) -> None:
        raw = {**self._base(), "side": OrderSideV2.ask}
        order = TradingService._parse_order(raw)
        assert order.side == OrderSide.no

    def test_bid_enum_value_maps_to_yes(self) -> None:
        raw = {**self._base(), "side": OrderSideV2.bid}
        order = TradingService._parse_order(raw)
        assert order.side == OrderSide.yes
