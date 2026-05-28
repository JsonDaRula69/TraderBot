"""Implied probability, edge detection, and Kelly criterion for binary markets."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Literal

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from traderbot.kalshi.models import OrderBook


class ImpliedProb(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    yes_prob: float
    no_prob: float
    spread_cents: int
    mid_price_cents: int


class EdgeEstimate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    estimated_prob: float
    market_prob: float
    edge: float
    direction: Literal["yes", "no", "neutral"]


class KellyInputs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    prob: float
    odds: float
    edge: float
    kelly_fraction: float


def implied_probability(orderbook: OrderBook) -> ImpliedProb:
    """Extract implied probabilities from bid data in a binary order book."""
    best_yes_bid = max((lvl.price for lvl in orderbook.yes_bids), default=0)
    best_no_bid = max((lvl.price for lvl in orderbook.no_bids), default=0)

    if best_yes_bid == 0 and best_no_bid == 0:
        raise ValueError("Order book has no bids on either side")

    yes_prob = best_yes_bid / 100.0
    no_prob = best_no_bid / 100.0
    best_yes_ask = 100 - best_no_bid
    spread_cents = best_yes_ask - best_yes_bid
    mid_price_cents = max(1, round((best_yes_bid + best_yes_ask) / 2))

    return ImpliedProb(
        yes_prob=yes_prob,
        no_prob=no_prob,
        spread_cents=spread_cents,
        mid_price_cents=mid_price_cents,
    )


def detect_edge(estimated_prob: float, orderbook: OrderBook) -> EdgeEstimate:
    """Compare estimated probability against market-implied probability."""
    market_prob = implied_probability(orderbook).yes_prob
    edge = estimated_prob - market_prob

    if abs(edge) < 0.01:
        direction: Literal["yes", "no", "neutral"] = "neutral"
    elif edge > 0:
        direction = "yes"
    else:
        direction = "no"

    return EdgeEstimate(
        estimated_prob=estimated_prob,
        market_prob=market_prob,
        edge=edge,
        direction=direction,
    )


def compute_kelly_inputs(estimated_prob: float, market_price_cents: int) -> KellyInputs:
    """Compute Kelly criterion fraction for a binary market position."""
    profit = 100 - market_price_cents
    loss = market_price_cents
    odds = profit / loss
    edge = estimated_prob - (market_price_cents / 100.0)
    kelly = (estimated_prob * odds - (1 - estimated_prob)) / odds
    kelly_fraction = max(0.0, min(1.0, kelly))

    return KellyInputs(
        prob=estimated_prob,
        odds=odds,
        edge=edge,
        kelly_fraction=kelly_fraction,
    )


def expected_value(prob: float, market_price_cents: int, quantity: int = 1) -> int:
    """Compute expected value in cents for a yes-position in a binary market."""
    profit_per = 100 - market_price_cents
    loss_per = market_price_cents
    ev = prob * profit_per * quantity - (1 - prob) * loss_per * quantity
    return round(ev)
