"""Abstract base class for data providers that supply weather forecasts and analytics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.data.models import BiasReport, CityForecast, ModelConsensus


class BaseDataProvider(ABC):
    """ABC for weather data providers.

    Subclass and implement the async methods to integrate with
    specific weather data sources (NWS, Open-Meteo, GFS, etc.).
    """

    @abstractmethod
    async def get_forecasts(self, cities: list[str]) -> dict[str, CityForecast]:
        """Fetch current forecasts for a list of cities.

        Args:
            cities: List of city names to fetch forecasts for.

        Returns:
            Dict mapping city name to its CityForecast.
        """
        ...

    @abstractmethod
    async def get_model_consensus(self, city: str) -> ModelConsensus:
        """Compute multi-model consensus for a single city.

        Args:
            city: City name to get consensus for.

        Returns:
            ModelConsensus with aggregate statistics across available models.
        """
        ...

    @abstractmethod
    async def get_historical_bias(
        self, city: str, model: str = "nws", days: int = 90
    ) -> BiasReport:
        """Calculate historical forecast bias for a model/location combination.

        Args:
            city: City name.
            model: Model identifier (default: "nws").
            days: Lookback window in days (default: 90).

        Returns:
            BiasReport with accuracy statistics over the lookback period.
        """
        ...
