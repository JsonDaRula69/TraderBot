"""Tests for odds module — implied probability, edge detection, Kelly, and EV."""

from __future__ import annotations

import pytest

from traderbot.analysis.odds import (
    EdgeEstimate,
    ImpliedProb,
    KellyInputs,
    compute_kelly_inputs,
    detect_edge,
    expected_value,
    implied_probability,
)
from traderbot.kalshi.models import OrderBook, OrderBookLevel


def _make_orderbook(
    yes_price: int = 55,
    yes_size: int = 10,
    no_price: int = 40,
    no_size: int = 10,
) -> OrderBook:
    return OrderBook(
        yes_bids=[OrderBookLevel(price=yes_price, size=yes_size)],
        no_bids=[OrderBookLevel(price=no_price, size=no_size)],
    )


# --- implied_probability ---


@pytest.mark.unit
def test_implied_probability_basic():
    ob = _make_orderbook(yes_price=55, no_price=40)
    result = implied_probability(ob)

    assert isinstance(result, ImpliedProb)
    assert result.yes_prob == pytest.approx(0.55)
    assert result.no_prob == pytest.approx(0.40)
    assert result.spread_cents == 5  # ask_yes(60) - bid_yes(55)
    assert result.mid_price_cents == 58  # round((55 + 60) / 2)


@pytest.mark.unit
def test_implied_probability_empty_orderbook_raises():
    ob = OrderBook(yes_bids=[], no_bids=[])
    with pytest.raises(ValueError):
        implied_probability(ob)


@pytest.mark.unit
def test_implied_probability_no_yes_bids():
    ob = OrderBook(yes_bids=[], no_bids=[OrderBookLevel(price=45, size=5)])
    result = implied_probability(ob)

    assert result.yes_prob == pytest.approx(0.0)
    assert result.no_prob == pytest.approx(0.45)
    assert result.mid_price_cents == 28  # round((0 + 55) / 2)


@pytest.mark.unit
def test_implied_probability_no_no_bids():
    ob = OrderBook(yes_bids=[OrderBookLevel(price=60, size=5)], no_bids=[])
    result = implied_probability(ob)

    assert result.yes_prob == pytest.approx(0.60)
    assert result.no_prob == pytest.approx(0.0)
    assert result.mid_price_cents == 80  # round((60 + 100) / 2)
    assert result.spread_cents == 40  # ask_yes(100) - bid_yes(60)


# --- detect_edge ---


@pytest.mark.unit
def test_detect_edge_yes_direction():
    ob = _make_orderbook(yes_price=55, no_price=40)
    result = detect_edge(0.7, ob)

    assert isinstance(result, EdgeEstimate)
    assert result.direction == "yes"
    assert result.edge == pytest.approx(0.15)
    assert result.market_prob == pytest.approx(0.55)
    assert result.estimated_prob == pytest.approx(0.7)


@pytest.mark.unit
def test_detect_edge_no_direction():
    ob = _make_orderbook(yes_price=55, no_price=40)
    result = detect_edge(0.50, ob)

    assert result.direction == "no"
    assert result.edge == pytest.approx(-0.05)


@pytest.mark.unit
def test_detect_edge_neutral():
    ob = _make_orderbook(yes_price=55, no_price=40)
    result = detect_edge(0.555, ob)  # within 0.01 of 0.55

    assert result.direction == "neutral"


@pytest.mark.unit
def test_detect_edge_neutral_exact():
    ob = _make_orderbook(yes_price=55, no_price=40)
    result = detect_edge(0.55, ob)

    assert result.direction == "neutral"
    assert result.edge == pytest.approx(0.0)


# --- compute_kelly_inputs ---


@pytest.mark.unit
def test_kelly_positive_edge():
    result = compute_kelly_inputs(estimated_prob=0.6, market_price_cents=50)

    assert isinstance(result, KellyInputs)
    assert result.odds == pytest.approx(1.0)
    # kelly = (0.6*1 - 0.4)/1 = 0.2
    assert result.kelly_fraction == pytest.approx(0.2)
    assert result.edge == pytest.approx(0.1)  # 0.6 - 0.5


@pytest.mark.unit
def test_kelly_negative_clamped():
    result = compute_kelly_inputs(estimated_prob=0.3, market_price_cents=50)

    assert result.kelly_fraction == pytest.approx(0.0)


@pytest.mark.unit
def test_kelly_high_confidence():
    result = compute_kelly_inputs(estimated_prob=0.9, market_price_cents=60)

    # odds = 40/60 ≈ 0.6667
    # kelly = (0.9 * 0.6667 - 0.1) / 0.6667 ≈ 0.75
    assert result.odds == pytest.approx(40 / 60)
    assert result.kelly_fraction > 0.0
    assert result.kelly_fraction <= 1.0
    assert result.edge == pytest.approx(0.3)  # 0.9 - 0.6


@pytest.mark.unit
def test_kelly_capped_at_one():
    result = compute_kelly_inputs(estimated_prob=0.99, market_price_cents=1)

    assert result.kelly_fraction <= 1.0


# --- expected_value ---


@pytest.mark.unit
def test_expected_value_positive():
    ev = expected_value(prob=0.6, market_price_cents=50, quantity=1)

    # 0.6 * 50 - 0.4 * 50 = 30 - 20 = 10
    assert ev == 10


@pytest.mark.unit
def test_expected_value_negative():
    ev = expected_value(prob=0.3, market_price_cents=50, quantity=1)

    # 0.3 * 50 - 0.7 * 50 = 15 - 35 = -20
    assert ev == -20


@pytest.mark.unit
def test_expected_value_with_quantity():
    ev = expected_value(prob=0.6, market_price_cents=50, quantity=5)

    # 5 * (0.6 * 50 - 0.4 * 50) = 5 * 10 = 50
    assert ev == 50


@pytest.mark.unit
def test_expected_value_rounds():
    ev = expected_value(prob=0.33, market_price_cents=33, quantity=1)

    # 0.33 * 67 - 0.67 * 33 = 22.11 - 22.11 = ~0
    assert isinstance(ev, int)
