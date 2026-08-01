from __future__ import annotations

from traderbot.data.base_signals import BaseSignalEngine
from traderbot.data.models import TradingSignal


class TestTradingSignal:
    def test_direction_yes(self) -> None:
        ts = TradingSignal(
            ticker="KWEATHER-25APR15-A",
            direction="yes",
            estimated_prob=0.7,
            market_prob=0.65,
            edge=0.05,
            confidence=0.8,
            model_consensus=0.75,
            bias_adjustment=0.02,
            reasoning="Strong model agreement",
        )
        assert ts.direction == "yes"
        assert ts.confidence == 0.8

    def test_direction_no(self) -> None:
        ts = TradingSignal(
            ticker="KWEATHER-25APR15-A",
            direction="no",
            estimated_prob=0.3,
            market_prob=0.35,
            edge=-0.05,
            confidence=0.6,
            model_consensus=0.25,
            bias_adjustment=-0.01,
            reasoning="Models disagree with market",
        )
        assert ts.direction == "no"
