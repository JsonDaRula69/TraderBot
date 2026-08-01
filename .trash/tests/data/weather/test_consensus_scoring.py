"""Tests for ensemble consensus scoring in WeatherSignalEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from traderbot.data.models import ModelConsensus
from traderbot.data.weather.signals import WeatherSignalEngine
from traderbot.experiment.shared import MarketData


def _make_market_data(ticker: str = "KXHIGHNY", threshold: float = 85.0) -> MarketData:
    return MarketData(
        ticker=ticker,
        threshold=threshold,
        strike_type="greater",
        expiration=datetime.now(UTC),
        category="weather",
    )


class TestConsensusScoring:
    def test_consensus_populated_with_mocked_provider(self):
        """Mocked provider returning agreement_score=0.85 populates signal.model_consensus."""
        mock_provider = MagicMock()
        mock_provider.get_model_consensus = AsyncMock(
            return_value=ModelConsensus(
                mean_temp=80.0,
                std_dev=2.0,
                spread=5.0,
                models_used=["gfs_seamless", "ecmwf_ifs", "gem_global"],
                agreement_score=0.85,
            )
        )
        engine = WeatherSignalEngine(provider=mock_provider)
        score = engine._get_consensus_score("KXHIGHNY")
        assert score is not None
        assert score == pytest.approx(0.85, abs=0.001)

    def test_consensus_single_model_fallback(self):
        """Consensus with only 1 model returns 0.5 (unreliable)."""
        mock_provider = MagicMock()
        mock_provider.get_model_consensus = AsyncMock(
            return_value=ModelConsensus(
                mean_temp=80.0,
                std_dev=0.0,
                spread=0.0,
                models_used=["gfs_seamless"],
                agreement_score=0.95,
            )
        )
        engine = WeatherSignalEngine(provider=mock_provider)
        score = engine._get_consensus_score("KXHIGHNY")
        assert score == 0.5

    def test_consensus_missing_city_fallback(self):
        """Unknown ticker (not in _TICKER_TO_CITY) returns 0.5."""
        engine = WeatherSignalEngine()
        score = engine._get_consensus_score("KXBTCD-UNKNOWN")
        assert score == 0.5

    def test_consensus_error_fallback(self):
        """Provider error returns 0.5 gracefully."""
        mock_provider = MagicMock()
        mock_provider.get_model_consensus = AsyncMock(side_effect=RuntimeError("API error"))
        engine = WeatherSignalEngine(provider=mock_provider)
        score = engine._get_consensus_score("KXHIGHNY")
        assert score == 0.5
