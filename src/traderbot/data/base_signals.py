"""Abstract base class for signal engines that produce trading signals from forecasts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.data.models import CityForecast, TradingSignal
    from traderbot.experiment.shared import MarketData


class BaseSignalEngine(ABC):
    """ABC for signal computation engines.

    Subclass and implement compute_signals to transform forecast data
    and market conditions into actionable TradingSignal instances.
    """

    @abstractmethod
    def compute_signals(
        self,
        forecasts: dict[str, CityForecast],
        markets: dict[str, MarketData],
    ) -> list[TradingSignal]:
        """Compute trading signals from forecasts and market data.

        Args:
            forecasts: City name → CityForecast mapping.
            markets: Ticker → MarketData mapping for active markets.

        Returns:
            List of TradingSignal recommendations.
        """
        ...
