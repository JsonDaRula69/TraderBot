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


class TestNoDeprecatedEcmwfIfens:
    """Regression: ecmwf_ifens was renamed to ecmwf_ifs.

    Bug: the old model name 'ecmwf_ifens' persisted in code after the rename.
    This test scans all source files to ensure no references remain.
    """

    def test_no_deprecated_ecmwf_ifens_in_source(self) -> None:
        import os

        root = os.path.join(os.path.dirname(__file__), "..", "..", "src", "traderbot")
        root = os.path.normpath(root)
        found: list[tuple[str, int]] = []
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fn.endswith(".py"):
                    path = os.path.join(dirpath, fn)
                    with open(path) as f:
                        for i, line in enumerate(f, 1):
                            if "ecmwf_ifens" in line:
                                found.append((path, i))
        assert not found, f"Deprecated ecmwf_ifens still referenced in: {found}"
