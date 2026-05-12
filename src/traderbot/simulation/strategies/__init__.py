"""Backtest strategy implementations for binary prediction markets."""

from traderbot.kalshi._normalize import _to_cents
from traderbot.simulation.engine import Context, Signal


def _yes_probability(prices: list[str] | None) -> float:
    """Convert outcome_prices to yes-side probability (0.0–1.0).

    Handles both dollar format ("0.55") and cent format ("55").
    """
    if not prices:
        return 0.5
    cents = _to_cents(prices[0])
    return cents / 100.0 if cents > 0 else 0.5


class MomentumStrategy:
    """Follow price momentum — buy when price moves strongly away from 50%."""

    def on_market_open(self, market, context: Context) -> list[Signal]:
        if market.volume < 100:
            return []
        yes_price = _yes_probability(market.outcome_prices)
        price_cents = int(yes_price * 100)
        edge = abs(yes_price - 0.5)
        if edge < 0.03:
            return []
        direction = "yes" if yes_price > 0.5 else "no"
        prob = yes_price if direction == "yes" else 1.0 - yes_price
        return [
            Signal(
                ticker=market.ticker,
                direction=direction,
                quantity=1,
                price_cents=price_cents,
                estimated_prob=prob,
                confidence=min(edge * 2, 1.0),
            )
        ]

    def on_trade(self, trade, context: Context) -> list[Signal]:
        return []

    def on_settle(self, market, outcome, context: Context) -> None:
        pass


class MeanReversionStrategy:
    """Bet against extremes — buy the underpriced side when price deviates significantly."""

    def on_market_open(self, market, context: Context) -> list[Signal]:
        yes_price = _yes_probability(market.outcome_prices)
        price_cents = int(yes_price * 100)
        if 0.35 < yes_price < 0.65:
            return []
        direction = "no" if yes_price > 0.65 else "yes"
        prob = 1.0 - yes_price if direction == "no" else yes_price
        return [
            Signal(
                ticker=market.ticker,
                direction=direction,
                quantity=1,
                price_cents=price_cents,
                estimated_prob=prob,
                confidence=0.5,
            )
        ]

    def on_trade(self, trade, context: Context) -> list[Signal]:
        return []

    def on_settle(self, market, outcome, context: Context) -> None:
        pass


class ConservativeStrategy:
    """Only trade when edge is large and volume is high — capital preservation."""

    def on_market_open(self, market, context: Context) -> list[Signal]:
        yes_price = _yes_probability(market.outcome_prices)
        price_cents = int(yes_price * 100)
        edge = abs(yes_price - 0.5)
        if edge < 0.10 or market.volume < 500:
            return []
        direction = "yes" if yes_price > 0.5 else "no"
        prob = yes_price if direction == "yes" else 1.0 - yes_price
        return [
            Signal(
                ticker=market.ticker,
                direction=direction,
                quantity=1,
                price_cents=int(yes_price * 100),
                estimated_prob=prob,
                confidence=min(edge, 1.0),
            )
        ]

    def on_trade(self, trade, context: Context) -> list[Signal]:
        return []

    def on_settle(self, market, outcome, context: Context) -> None:
        pass


STRATEGY_MAP: dict[str, type] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "conservative": ConservativeStrategy,
}


def get_strategy(name: str):
    """Return a strategy instance by name, defaulting to momentum."""
    cls = STRATEGY_MAP.get(name.lower(), MomentumStrategy)
    return cls()