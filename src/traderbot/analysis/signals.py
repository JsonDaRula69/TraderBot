"""Weighted signal combination for binary prediction markets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.analysis.indicators import bollinger_bands, ema, rsi
from traderbot.analysis.odds import detect_edge

if TYPE_CHECKING:
    from traderbot.kalshi.models import OrderBook, Trade


class SignalSource(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    weight: Annotated[float, Field(ge=0, le=1)]
    direction: Literal["yes", "no", "neutral"]
    strength: Annotated[float, Field(ge=0, le=1)]


class CombinedSignal(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    direction: Literal["yes", "no", "neutral"]
    confidence: Annotated[float, Field(ge=0, le=1)]
    sources: list[SignalSource]
    estimated_prob: float
    edge_cents: int


def combine_signals(
    sources: list[SignalSource],
) -> tuple[Literal["yes", "no", "neutral"], float]:
    """Weighted average of signed signal strengths into direction and confidence."""
    if not sources:
        return ("neutral", 0.0)

    total_weight = sum(s.weight for s in sources)
    signed_sum = 0.0
    for s in sources:
        if s.direction == "yes":
            signed_sum += s.strength * s.weight * 1.0
        elif s.direction == "no":
            signed_sum += s.strength * s.weight * -1.0
    if signed_sum > 0.01:
        direction: Literal["yes", "no", "neutral"] = "yes"
    elif signed_sum < -0.01:
        direction = "no"
    else:
        direction = "neutral"

    confidence = min(1.0, max(0.0, abs(signed_sum) / total_weight)) if total_weight > 0 else 0.0

    return (direction, confidence)


def default_weights(include_sentiment: bool = False) -> dict[str, float]:
    """Signal source weights for 3-source or 4-source combinations."""
    if include_sentiment:
        return {"indicators": 0.25, "odds": 0.45, "momentum": 0.15, "sentiment": 0.15}
    return {"indicators": 0.3, "odds": 0.5, "momentum": 0.2}


def generate_signal(
    ticker: str,
    prices: list[int],
    trades: list[Trade],
    orderbook: OrderBook,
    estimated_prob: float,
    news_sentiment: float | None = None,
) -> CombinedSignal:
    """Combine indicators, odds, momentum, and optional news sentiment into a signal."""
    has_sentiment = news_sentiment is not None
    weights = default_weights(include_sentiment=has_sentiment)
    sources: list[SignalSource] = []

    # --- Indicators source: RSI + Bollinger position ---
    rsi_val = rsi(prices, period=14) if len(prices) >= 2 else 50.0
    bb = bollinger_bands(prices, period=20, k=2.0)

    if rsi_val < 30:
        ind_direction: Literal["yes", "no", "neutral"] = "yes"
        ind_strength = 1.0 - rsi_val / 100.0
    elif rsi_val > 70:
        ind_direction = "no"
        ind_strength = rsi_val / 100.0
    elif prices and prices[-1] < bb.lower:
        ind_direction = "yes"
        ind_strength = 0.7
    elif prices and prices[-1] > bb.upper:
        ind_direction = "no"
        ind_strength = 0.7
    else:
        # Position within bands: closer to lower → yes lean, closer to upper → no lean
        ind_direction = "neutral"
        if bb.upper != bb.lower and prices:
            position = (prices[-1] - bb.lower) / (bb.upper - bb.lower)
            ind_strength = min(1.0, abs(position - 0.5) * 2)
        else:
            ind_strength = 0.1

    sources.append(
        SignalSource(
            name="indicators",
            weight=weights["indicators"],
            direction=ind_direction,
            strength=ind_strength,
        )
    )

    # --- Odds source: detect edge from orderbook ---
    edge_result = detect_edge(estimated_prob, orderbook)
    if edge_result.direction in ("yes", "no"):
        odds_strength = min(1.0, abs(edge_result.edge) * 5)
        odds_direction: Literal["yes", "no", "neutral"] = edge_result.direction
    else:
        odds_strength = 0.1
        odds_direction = "neutral"

    sources.append(
        SignalSource(
            name="odds",
            weight=weights["odds"],
            direction=odds_direction,
            strength=odds_strength,
        )
    )

    # --- Momentum source: EMA crossover ---
    if len(prices) >= 20:
        short_ema = ema(prices, 5)
        long_ema = ema(prices, 20)
        if short_ema > long_ema:
            mom_direction: Literal["yes", "no", "neutral"] = "yes"
            mom_strength = (
                min(1.0, (short_ema - long_ema) / long_ema * 10) if long_ema != 0 else 0.1
            )
        elif short_ema < long_ema:
            mom_direction = "no"
            mom_strength = (
                min(1.0, (long_ema - short_ema) / long_ema * 10) if long_ema != 0 else 0.1
            )
        else:
            mom_direction = "neutral"
            mom_strength = 0.1
    else:
        mom_direction = "neutral"
        mom_strength = 0.1

    sources.append(
        SignalSource(
            name="momentum",
            weight=weights["momentum"],
            direction=mom_direction,
            strength=mom_strength,
        )
    )

    if has_sentiment and news_sentiment is not None:
        if news_sentiment > 0.1:
            sent_direction: Literal["yes", "no", "neutral"] = "yes"
        elif news_sentiment < -0.1:
            sent_direction = "no"
        else:
            sent_direction = "neutral"
        sources.append(
            SignalSource(
                name="sentiment",
                weight=weights["sentiment"],
                direction=sent_direction,
                strength=min(abs(news_sentiment), 1.0),
            )
        )

    direction, confidence = combine_signals(sources)
    edge_cents = round(edge_result.edge * 100)

    return CombinedSignal(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        sources=sources,
        estimated_prob=estimated_prob,
        edge_cents=edge_cents,
    )
