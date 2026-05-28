"""Tests for OrderRequest V2 endpoint and dollar pricing — regression coverage.

Verifies OrderRequest.to_v2_body() produces correct V2 API body with
bid/ask sides and dollar-formatted prices.
"""

import pytest

from traderbot.kalshi.models import OrderRequest, OrderSideV2


class TestOrderRequestV2Body:
    """Verify to_v2_body() output for the V2 API endpoint."""

    def test_to_v2_body_returns_dict(self) -> None:
        """to_v2_body() must return a dictionary."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert isinstance(body, dict)

    def test_side_is_bid(self) -> None:
        """When side is OrderSideV2.bid, body side must be 'bid'."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["side"] == "bid"

    def test_side_is_ask(self) -> None:
        """When side is OrderSideV2.ask, body side must be 'ask'."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.ask,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["side"] == "ask"

    def test_side_is_not_yes_or_no(self) -> None:
        """V2 body must NOT use 'yes' or 'no' as side values."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["side"] not in ("yes", "no")
        assert body["side"] in ("bid", "ask")

    def test_price_is_dollar_string(self) -> None:
        """Price must be a dollar-formatted string (e.g. '0.65' for 65 cents)."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="10",
            price="0.42",
        )
        body = order.to_v2_body()
        assert body["price"] == "0.42"
        assert isinstance(body["price"], str)
        assert "." in body["price"]

    def test_count_is_string(self) -> None:
        """Count must be a string type in the V2 body."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["count"] == "5"
        assert isinstance(body["count"], str)

    def test_ticker_included(self) -> None:
        """Ticker must be present in the V2 body."""
        ticker = "KXHIGHTNY-TEMP55"
        order = OrderRequest(
            ticker=ticker,
            side=OrderSideV2.ask,
            count="1",
            price="0.75",
        )
        body = order.to_v2_body()
        assert body["ticker"] == ticker

    def test_client_order_id_generated(self) -> None:
        """If client_order_id is None, a UUID is auto-generated."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
            client_order_id=None,
        )
        body = order.to_v2_body()
        assert "client_order_id" in body
        assert body["client_order_id"] is not None
        assert isinstance(body["client_order_id"], str)
        assert len(body["client_order_id"]) > 0

    def test_client_order_id_preserved(self) -> None:
        """If client_order_id is provided, it must be preserved in the body."""
        custom_id = "my-ordered-001"
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
            client_order_id=custom_id,
        )
        body = order.to_v2_body()
        assert body["client_order_id"] == custom_id

    def test_time_in_force_default(self) -> None:
        """Default time_in_force must be 'good_till_canceled'."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["time_in_force"] == "good_till_canceled"

    def test_self_trade_prevention_default(self) -> None:
        """Default self_trade_prevention_type must be 'taker_at_cross'."""
        order = OrderRequest(
            ticker="KXBTCD-26MAR31-T55000",
            side=OrderSideV2.bid,
            count="5",
            price="0.65",
        )
        body = order.to_v2_body()
        assert body["self_trade_prevention_type"] == "taker_at_cross"


class TestV2Endpoint:
    """Verify the V2 endpoint path is used in the trading service."""

    def test_place_order_uses_v2_endpoint(self) -> None:
        """The trading service must POST to /portfolio/events/orders/v2."""
        # We verify this by checking the source module's path constant.
        # This is a structural test confirming the endpoint string.
        import traderbot.kalshi.trading as trading_mod
        import inspect

        src = inspect.getsource(trading_mod.TradingService.place_order)
        assert "/portfolio/events/orders/v2" in src, (
            "place_order() must use V2 endpoint /portfolio/events/orders/v2"
        )


class TestOrderSideV2Enum:
    """Verify OrderSideV2 enum values."""

    def test_bid_value(self) -> None:
        """OrderSideV2.bid must be 'bid'."""
        assert OrderSideV2.bid == "bid"

    def test_ask_value(self) -> None:
        """OrderSideV2.ask must be 'ask'."""
        assert OrderSideV2.ask == "ask"

    def test_no_yes_no_in_v2(self) -> None:
        """OrderSideV2 must NOT contain 'yes' or 'no' values."""
        for member in OrderSideV2:
            assert member.value not in ("yes", "no")
