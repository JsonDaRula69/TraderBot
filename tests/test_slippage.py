from __future__ import annotations

from datetime import UTC, datetime

from traderbot.kalshi.provider import OrderBookLevelSnapshot, OrderBookSnapshot
from traderbot.simulation.paper_trader import PaperSlippageModel


def _ob(
    yes_bids: tuple[tuple[int, int], ...] = (),
    no_bids: tuple[tuple[int, int], ...] = (),
    yes_asks: tuple[tuple[int, int], ...] = (),
    no_asks: tuple[tuple[int, int], ...] = (),
) -> OrderBookSnapshot:
    """Build an OrderBookSnapshot from (price_cents, size) pairs."""
    return OrderBookSnapshot(
        yes_bids=tuple(OrderBookLevelSnapshot(p, s) for p, s in yes_bids),
        yes_asks=tuple(OrderBookLevelSnapshot(p, s) for p, s in yes_asks),
        no_bids=tuple(OrderBookLevelSnapshot(p, s) for p, s in no_bids),
        no_asks=tuple(OrderBookLevelSnapshot(p, s) for p, s in no_asks),
        timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )


class TestComputeFillPrice:
    """Tests for PaperSlippageModel.compute_fill_price.

    Key rule:
    - Buy orders (is_buy=True) walk asks — the trader pays to cross the spread.
    - Sell orders (is_buy=False) walk bids — the trader receives the bid price.
    """

    def test_empty_book_returns_midpoint_plus_slippage(self) -> None:
        """No asks or bids at all → fallback midpoint + base."""
        model = PaperSlippageModel(base_slippage_cents=2)
        ob = _ob()
        result = model.compute_fill_price(ob, "yes", 10, is_buy=True)
        assert result == 50 + 2

    def test_empty_book_sell_returns_midpoint_plus_slippage(self) -> None:
        """No bids for a sell order → fallback midpoint + base."""
        model = PaperSlippageModel(base_slippage_cents=2)
        ob = _ob()
        result = model.compute_fill_price(ob, "yes", 10, is_buy=False)
        assert result == 50 + 2

    def test_buy_yes_walks_asks(self) -> None:
        """Buy YES walks yes_asks (pay ask prices)."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_asks=((55, 200),))
        result = model.compute_fill_price(ob, "yes", 50, is_buy=True)
        assert result == 55 + 1

    def test_buy_yes_multi_level_asks_weighted_average(self) -> None:
        """Buy YES across multiple ask levels — weighted avg + base."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_asks=((55, 100), (60, 100)))
        result = model.compute_fill_price(ob, "yes", 200, is_buy=True)
        expected_avg = (55 * 100 + 60 * 100) // 200
        assert result == min(expected_avg + 1, 99)

    def test_buy_no_walks_no_asks(self) -> None:
        """Buy NO walks no_asks."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(no_asks=((45, 200),))
        result = model.compute_fill_price(ob, "no", 100, is_buy=True)
        assert result == 45 + 1

    def test_sell_yes_walks_yes_bids(self) -> None:
        """Sell YES walks yes_bids (receive bid prices)."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_bids=((55, 200),))
        result = model.compute_fill_price(ob, "yes", 50, is_buy=False)
        assert result == 55 + 1

    def test_sell_no_walks_no_bids(self) -> None:
        """Sell NO walks no_bids."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(no_bids=((45, 200),))
        result = model.compute_fill_price(ob, "no", 100, is_buy=False)
        assert result == 45 + 1

    def test_buy_quantity_exceeds_ask_depth(self) -> None:
        """Buy YES with thin asks — walks partial book, avg price with base."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_asks=((55, 10), (60, 5)))
        result = model.compute_fill_price(ob, "yes", 100, is_buy=True)
        total_cost = 55 * 10 + 60 * 5
        total_filled = 15
        expected_avg = total_cost // total_filled
        assert result == min(expected_avg + 1, 99)

    def test_buy_yes_thin_asks_slippage_above_best_ask(self) -> None:
        """Buy YES with only 10 ask contracts at 55, trying to buy 100
        → walks asks, slippage > 0, price higher than best ask."""
        model = PaperSlippageModel(base_slippage_cents=1)
        # Thick bids on the other side (should NOT be used for buys)
        ob = _ob(
            yes_bids=((50, 10_000),),
            yes_asks=((55, 10),),
        )
        result = model.compute_fill_price(ob, "yes", 100, is_buy=True)
        # Only 10 available asks at 55 → avg = 55, then +1 base
        assert result == 55 + 1  # only 10 ask contracts, can only fill 10 at best ask price

    def test_sell_yes_thin_bids_slippage_below_best_bid(self) -> None:
        """Sell YES with only 10 bid contracts at 50, trying to sell 100
        → walks bids, lower price than best bid for excess qty."""
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(
            yes_bids=((50, 10),),
            yes_asks=((55, 10_000),),
        )
        result = model.compute_fill_price(ob, "yes", 100, is_buy=False)
        # Only 10 bids at 50 → can only fill 10 at bid price
        assert result == 50 + 1

    def test_result_capped_at_99(self) -> None:
        """Fill price never exceeds 99 cents."""
        model = PaperSlippageModel(base_slippage_cents=50)
        ob = _ob(yes_asks=((55, 100),))
        result = model.compute_fill_price(ob, "yes", 10, is_buy=True)
        assert result == 99

    def test_default_slippage_is_one_cent(self) -> None:
        """Default base_slippage is 1 cent."""
        model = PaperSlippageModel()
        ob = _ob(yes_asks=((60, 100),))
        result = model.compute_fill_price(ob, "yes", 10, is_buy=True)
        assert result == 60 + 1
