"""Tests for strike_type detection and threshold-based probability estimation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.data.models import CityForecast
from traderbot.data.weather.signals import (
    WeatherSignalEngine,
    _detect_strike_type,
    _estimate_prob_from_threshold,
)
from traderbot.experiment.shared import MarketData
from traderbot.kalshi.models import OrderBook, OrderBookLevel


def _make_forecast(high_temp_f: float, city: str = "Chicago") -> CityForecast:
    return CityForecast(
        ticker="KXHIGHTCHI",
        city=city,
        lat=41.88,
        lon=-87.63,
        date=datetime.now(UTC).date(),
        high_temp_f=high_temp_f,
        low_temp_f=high_temp_f - 15,
        precip_prob=0.1,
        wind_speed=5.0,
        detailed_forecast="Sunny",
        source="nws",
    )


def _make_market_data(
    ticker: str = "KXHIGHTCHI-26JUN02-T81",
    threshold: float = 81.0,
    strike_type: str = "less",
) -> MarketData:
    return MarketData(
        ticker=ticker,
        threshold=threshold,
        strike_type=strike_type,
        expiration=datetime.now(UTC),
        category="weather",
    )


def _make_orderbook(
    yes_price: int = 55, yes_size: int = 10, no_price: int = 40, no_size: int = 10
) -> OrderBook:
    return OrderBook(
        yes_bids=[OrderBookLevel(price=yes_price, size=yes_size)],
        no_bids=[OrderBookLevel(price=no_price, size=no_size)],
    )


class TestDetectStrikeType:
    def test_kxhigh_t_type_returns_less(self):
        assert _detect_strike_type("KXHIGHTCHI-26JUN02-T81") == "less"

    def test_kxhighch_t_type_returns_less(self):
        assert _detect_strike_type("KXHIGHCHI-26JUN02-T81") == "less"

    def test_kxlowt_t_type_returns_greater(self):
        assert _detect_strike_type("KXLOWTCHI-26JUN02-T32") == "greater"

    def test_kxlowtny_t_type_returns_greater(self):
        assert _detect_strike_type("KXLOWTNY-26JUN02-T32") == "greater"

    def test_b_type_returns_between(self):
        assert _detect_strike_type("KXHIGHTCHI-26JUN02-B72.5") == "between"

    def test_kxlow_b_type_returns_between(self):
        assert _detect_strike_type("KXLOWTCHI-26JUN02-B32.5") == "between"

    def test_case_insensitive(self):
        assert _detect_strike_type("kxhightchi-26jun02-t81") == "less"

    def test_unrecognized_returns_between(self):
        assert _detect_strike_type("SOMEOTHER-26JUN02-X81") == "between"

    def test_question_fallback_below(self):
        result = _detect_strike_type("UNKNOWN", question="Will it be below 85°F?")
        assert result == "less"

    def test_question_fallback_above(self):
        result = _detect_strike_type("UNKNOWN", question="Will it be above 32°F?")
        assert result == "greater"

    def test_question_fallback_less_than(self):
        result = _detect_strike_type("UNKNOWN", question="Will the high be less than 90?")
        assert result == "less"

    def test_question_fallback_no_match_returns_between(self):
        result = _detect_strike_type("UNKNOWN", question="What is the temperature?")
        assert result == "between"


class TestEstimateProbFromThreshold:
    def test_less_type_forecast_below_threshold(self):
        prob = _estimate_prob_from_threshold(forecast_temp=70.0, threshold=81.0, strike_type="less")
        assert prob > 0.85, "forecast well below threshold → high prob for 'less'"

    def test_less_type_forecast_above_threshold(self):
        prob = _estimate_prob_from_threshold(forecast_temp=86.0, threshold=81.0, strike_type="less")
        assert prob < 0.5, "forecast above threshold → low prob for 'less'"

    def test_greater_type_forecast_above_threshold(self):
        prob = _estimate_prob_from_threshold(forecast_temp=90.0, threshold=81.0, strike_type="greater")
        assert prob > 0.85, "forecast well above threshold → high prob for 'greater'"

    def test_greater_type_forecast_below_threshold(self):
        prob = _estimate_prob_from_threshold(forecast_temp=70.0, threshold=81.0, strike_type="greater")
        assert prob < 0.5, "forecast below threshold → low prob for 'greater'"

    def test_between_returns_half(self):
        prob = _estimate_prob_from_threshold(forecast_temp=90.0, threshold=81.0, strike_type="between")
        assert prob == 0.5

    def test_bug_143_kxhigh_t81_with_86f(self):
        """Bug #143: KXHIGHCHI-T81 with NWS 86°F should compute edge for NO.

        For KXHIGH T-type (YES = temp < threshold), forecast 86°F > 81°F
        means the estimated probability for YES should be LOW (< 0.5),
        driving an edge for NO.
        """
        prob = _estimate_prob_from_threshold(forecast_temp=86.0, threshold=81.0, strike_type="less")
        assert prob < 0.5, f"Expected prob < 0.5 for T-type less, got {prob}"

    def test_kxlowt_t32_with_40f(self):
        """KXLOWT T-type (YES = temp > threshold): 40°F > 32°F → high YES prob."""
        prob = _estimate_prob_from_threshold(forecast_temp=40.0, threshold=32.0, strike_type="greater")
        assert prob > 0.5, f"Expected prob > 0.5 for T-type greater, got {prob}"


class TestComputeOneStrikeTypeResolution:
    """Test that _compute_one correctly resolves strike_type from ticker."""

    def test_kxhigh_t_type_uses_less(self):
        """KXHIGH T-type ticker should use 'less' even if MarketData says 'between'."""
        engine = WeatherSignalEngine(orderbooks={"KXHIGHTCHI-26JUN02-T81": _make_orderbook()})
        fc = _make_forecast(high_temp_f=86.0)
        market = _make_market_data(ticker="KXHIGHTCHI-26JUN02-T81", strike_type="between")
        signal = engine._compute_one("KXHIGHTCHI-26JUN02-T81", market, fc)
        assert signal.direction == "no", (
            f"KXHIGH T-type with forecast 86°F > threshold 81°F should recommend NO, got {signal.direction}"
        )
        assert signal.estimated_prob < 0.5

    def test_kxhigh_t_type_explicit_less_preserved(self):
        """When MarketData already has 'less', it should be preserved."""
        engine = WeatherSignalEngine(orderbooks={"KXHIGHTCHI-26JUN02-T81": _make_orderbook()})
        fc = _make_forecast(high_temp_f=70.0)
        market = _make_market_data(ticker="KXHIGHTCHI-26JUN02-T81", strike_type="less")
        signal = engine._compute_one("KXHIGHTCHI-26JUN02-T81", market, fc)
        assert signal.direction == "yes", (
            f"KXHIGH T-type with forecast 70°F < threshold 81°F should recommend YES, got {signal.direction}"
        )
        assert signal.estimated_prob > 0.5

    def test_kxlowt_t_type_uses_greater(self):
        """KXLOWT T-type ticker should use 'greater' even if MarketData says 'between'."""
        engine = WeatherSignalEngine(orderbooks={"KXLOWTCHI-26JUN02-T32": _make_orderbook()})
        fc = CityForecast(
            ticker="KXLOWTCHI",
            city="Chicago",
            lat=41.88,
            lon=-87.63,
            date=datetime.now(UTC).date(),
            high_temp_f=40.0,
            low_temp_f=33.0,
            precip_prob=0.1,
            wind_speed=5.0,
            detailed_forecast="Cold",
            source="nws",
        )
        market = _make_market_data(ticker="KXLOWTCHI-26JUN02-T32", threshold=32.0, strike_type="between")
        signal = engine._compute_one("KXLOWTCHI-26JUN02-T32", market, fc)
        assert signal.direction == "yes", (
            f"KXLOWT T-type with forecast 40°F > threshold 32°F should recommend YES, got {signal.direction}"
        )
        assert signal.estimated_prob > 0.5