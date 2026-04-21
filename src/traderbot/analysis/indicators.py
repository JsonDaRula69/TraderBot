"""Technical indicators adapted for binary prediction markets."""

from __future__ import annotations

import math
from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict

from traderbot.kalshi.models import Trade  # noqa: TC001


class IndicatorResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    value: float
    timestamp: datetime


class MovingAverageResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    sma: float
    ema: float
    period: int


class BollingerBands(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    lower: int
    middle: int
    upper: int


def sma(prices: list[int], period: int) -> float:
    """Simple moving average of the last *period* prices (or all if fewer)."""
    if not prices:
        raise ValueError("prices must not be empty")
    n = min(period, len(prices))
    return sum(prices[-n:]) / n


def ema(prices: list[int], period: int) -> float:
    """Exponential moving average with multiplier 2/(period+1)."""
    if not prices:
        raise ValueError("prices must not be empty")
    mult = 2 / (period + 1)
    if len(prices) == 1:
        return float(prices[0])
    n = min(period, len(prices))
    result = sum(prices[:n]) / n
    for price in prices[n:]:
        result = price * mult + result * (1 - mult)
    return result


def rsi(prices: list[int], period: int = 14) -> float:
    """Wilder's RSI using exponential smoothing on price deltas."""
    if not prices:
        raise ValueError("prices must not be empty")
    if len(prices) < 2:
        return 50.0

    deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]

    gains: list[float] = []
    losses: list[float] = []
    for d in deltas:
        gains.append(float(d) if d > 0 else 0.0)
        losses.append(float(-d) if d < 0 else 0.0)

    n = min(period, len(deltas))
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    for i in range(n, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger_bands(prices: list[int], period: int = 20, k: float = 2.0) -> BollingerBands:
    """Bollinger Bands with population standard deviation, returned as int cents."""
    if not prices:
        raise ValueError("prices must not be empty")
    n = min(period, len(prices))
    window = prices[-n:]
    middle = sum(window) / n
    variance = sum((p - middle) ** 2 for p in window) / n
    std = math.sqrt(variance)
    return BollingerBands(
        lower=round(middle - k * std),
        middle=round(middle),
        upper=round(middle + k * std),
    )


def volume_weighted_price(trades: list[Trade]) -> int:
    """Volume-weighted average price, returned as int cents."""
    if not trades:
        raise ValueError("trades must not be empty")
    total_value = sum(t.price * t.quantity for t in trades)
    total_qty = sum(t.quantity for t in trades)
    return round(total_value / total_qty)
