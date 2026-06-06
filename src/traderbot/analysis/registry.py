"""Category-based analysis registry with protocol-based analyzer dispatch."""

from __future__ import annotations

import logging
from typing import Annotated, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict, Field

from traderbot.analysis.indicators import bollinger_bands, ema, rsi
from traderbot.analysis.odds import detect_edge
from traderbot.analysis.signals import generate_signal
from traderbot.kalshi.models import MarketCategory  # noqa: TC001


class CategorySignals(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    signals: list[str]
    confidence: Annotated[float, Field(ge=0, le=1)]
    data_sources: list[str]


@runtime_checkable
class CategoryAnalyzer(Protocol):
    def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals: ...


class AnalysisRegistry:
    def __init__(self) -> None:
        self._analyzers: dict[MarketCategory, CategoryAnalyzer] = {}

    def register(self, category: MarketCategory, analyzer: CategoryAnalyzer) -> None:
        self._analyzers[category] = analyzer

    def get(self, category: MarketCategory) -> CategoryAnalyzer:
        if category in self._analyzers:
            return self._analyzers[category]
        return self._default

    def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
        analyzer = self.get(category)
        return analyzer.analyze(market_data, category)

    @property
    def _default(self) -> CategoryAnalyzer:
        return GenericAnalyzer()


class GenericAnalyzer:
    """Wraps the existing indicator/odds/signal pipeline as the default analyzer."""

    def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
        prices: list[int] = market_data.get("prices", [])
        trades = market_data.get("trades", [])
        orderbook = market_data.get("orderbook")
        estimated_prob: float = market_data.get("estimated_prob", 0.5)
        ticker: str = market_data.get("ticker", "UNKNOWN")

        signals: list[str] = []
        data_sources: list[str] = []
        confidence = 0.0

        if len(prices) >= 2:
            rsi_val = rsi(prices, period=14)
            signals.append(f"RSI={rsi_val:.1f}")
            data_sources.append("rsi")

            bb = bollinger_bands(prices, period=20, k=2.0)
            signals.append(f"BB=[{bb.lower},{bb.middle},{bb.upper}]")
            data_sources.append("bollinger")

            short = ema(prices, 5)
            long = ema(prices, 20)
            signals.append(f"EMA5={short:.1f},EMA20={long:.1f}")
            data_sources.append("ema")

        if orderbook is not None:
            edge = detect_edge(estimated_prob, orderbook)
            signals.append(f"edge={edge.edge:.3f},dir={edge.direction}")
            data_sources.append("odds")

        if prices and trades and orderbook is not None:
            combined = generate_signal(ticker, prices, orderbook, estimated_prob)
            confidence = combined.confidence
            signals.append(f"combined={combined.direction},conf={combined.confidence:.2f}")
            data_sources.append("signals")
        else:
            confidence = 0.3

        return CategorySignals(
            category=category,
            signals=signals,
            confidence=confidence,
            data_sources=data_sources,
        )
