from __future__ import annotations

from datetime import UTC, datetime

from traderbot.kalshi.provider import OrderBookLevelSnapshot, OrderBookSnapshot
from traderbot.simulation.paper_trader import PaperSlippageModel


def _ob(
    yes_bids: tuple[tuple[int, int], ...] = (),
    no_bids: tuple[tuple[int, int], ...] = (),
) -> OrderBookSnapshot:
    """Build an OrderBookSnapshot from (price_cents, size) pairs."""
    return OrderBookSnapshot(
        yes_bids=tuple(OrderBookLevelSnapshot(p, s) for p, s in yes_bids),
        no_bids=tuple(OrderBookLevelSnapshot(p, s) for p, s in no_bids),
        timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )


class TestComputeFillPrice:
    """Tests for PaperSlippageModel.compute_fill_price."""

    def test_empty_bids_returns_midpoint_plus_slippage(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=2)
        ob = _ob()
        result = model.compute_fill_price(ob, "yes", 10)
        assert result == 50 + 2

    def test_single_level_yes(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_bids=((55, 200),))
        result = model.compute_fill_price(ob, "yes", 50)
        assert result == 55 + 1

    def test_multi_level_yes_weighted_average(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_bids=((55, 100), (50, 100)))
        result = model.compute_fill_price(ob, "yes", 200)
        expected_avg = (55 * 100 + 50 * 100) // 200
        assert result == min(expected_avg + 1, 99)

    def test_no_side_uses_no_bids(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(no_bids=((45, 200),))
        result = model.compute_fill_price(ob, "no", 100)
        assert result == 45 + 1

    def test_quantity_exceeds_book_depth(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=1)
        ob = _ob(yes_bids=((55, 10), (50, 5)))
        result = model.compute_fill_price(ob, "yes", 100)
        total_cost = 55 * 10 + 50 * 5
        total_filled = 15
        expected_avg = total_cost // total_filled
        assert result == min(expected_avg + 1, 99)

    def test_result_capped_at_99(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=50)
        ob = _ob(yes_bids=((98, 100),))
        result = model.compute_fill_price(ob, "yes", 10)
        assert result == 99

    def test_default_slippage_is_one_cent(self) -> None:
        model = PaperSlippageModel()
        ob = _ob(yes_bids=((60, 100),))
        result = model.compute_fill_price(ob, "yes", 10)
        assert result == 60 + 1
