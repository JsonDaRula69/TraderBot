from __future__ import annotations

from typing import Any

import pytest

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.models import BiasReport, CityForecast, ModelConsensus


class _ConcreteProvider(BaseDataProvider):
    def get_cache_key(self) -> str:
        return "test"

    async def get_forecasts(self, cities: list[str]) -> dict[str, CityForecast]:
        return {}

    async def get_model_consensus(self, city: str) -> ModelConsensus:
        return ModelConsensus(
            city=city,
            high_f_mean=70.0,
            high_f_std=2.0,
            num_models=1,
        )

    async def get_historical_bias(
        self, city: str, model: str = "nws", days: int = 90
    ) -> BiasReport:
        return BiasReport(
            city=city,
            model=model,
            total_comparisons=0,
            mean_error=0.0,
            mean_abs_error=0.0,
            std_error=0.0,
            last_n_days=days,
        )


class TestBaseDataProvider:
    def test_raises_on_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseDataProvider()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        provider = _ConcreteProvider()
        assert provider.get_cache_key() == "test"
