"""Backtest strategy implementations for binary prediction markets."""

from traderbot.simulation.engine import Context, Signal


def _yes_probability(market) -> float:
    """Extract yes-side probability (0.0–1.0) from market V2 price fields.

    Uses last_price_cents if available, falls back to mid-price of yes bid/ask spread.
    """
    if hasattr(market, "last_price_cents") and market.last_price_cents > 0:
        return market.last_price_cents / 100.0
    if hasattr(market, "yes_bid_cents") and market.yes_bid_cents > 0:
        yes_ask = market.yes_ask_cents if market.yes_ask_cents > 0 else 100
        return ((market.yes_bid_cents + yes_ask) / 2) / 100.0
    return 0.5


class MomentumStrategy:
    """Follow price momentum — buy when price moves strongly away from 50%."""

    def on_market_open(self, market, context: Context) -> list[Signal]:
        if market.volume < 100:
            return []
        yes_price = _yes_probability(market)
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
        yes_price = _yes_probability(market)
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
        yes_price = _yes_probability(market)
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