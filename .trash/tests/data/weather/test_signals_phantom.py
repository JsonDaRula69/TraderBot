"""Tests for phantom edge detection in WeatherSignalEngine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.data.models import CityForecast
from traderbot.data.weather.signals import WeatherSignalEngine
from traderbot.experiment.shared import MarketData
from traderbot.kalshi.models import OrderBook, OrderBookLevel


def _make_forecast(high_temp_f: float, city: str = "New York") -> CityForecast:
    return CityForecast(
        ticker="KXHIGHNY",
        city=city,
        lat=40.7,
        lon=-74.0,
        date=datetime.now(UTC).date(),
        high_temp_f=high_temp_f,
        low_temp_f=high_temp_f - 15,
        precip_prob=0.1,
        wind_speed=5.0,
        detailed_forecast="Sunny",
        source="nws",
    )


def _make_market_data(threshold: float = 85.0, strike_type: str = "greater") -> MarketData:
    return MarketData(
        ticker="KXHIGHNY",
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


class TestDetectPhantomEdge:
    def test_logistic_asymptote_penalty(self):
        """Forecast >30°F from threshold returns phantom edge penalty."""
        engine = WeatherSignalEngine(orderbooks={"KXHIGHNY": _make_orderbook()})
        mult, flag = engine._detect_phantom_edge(
            forecast_temp=50.0,  # 35°F from 85°F threshold
            threshold=85.0,
            market_prob=0.55,
            agreement_mult=0.95,
            ticker="KXHIGHNY",
        )
        assert mult < 1.0, "Logistic asymptote should reduce multiplier"
        assert flag is not None
        assert "logistic_asymptote" in flag

    def test_low_consensus_penalty(self):
        """Low model consensus (agreement_mult < 0.5) returns phantom edge penalty."""
        engine = WeatherSignalEngine(orderbooks={"KXHIGHNY": _make_orderbook()})
        mult, flag = engine._detect_phantom_edge(
            forecast_temp=75.0,
            threshold=85.0,
            market_prob=0.55,
            agreement_mult=0.3,
            ticker="KXHIGHNY",
        )
        assert mult < 1.0
        assert flag is not None
        assert "low_consensus" in flag

    def test_missing_orderbook_penalty(self):
        """Missing orderbook returns phantom edge penalty."""
        engine = WeatherSignalEngine(orderbooks={})  # No orderbooks at all
        mult, flag = engine._detect_phantom_edge(
            forecast_temp=75.0,
            threshold=85.0,
            market_prob=0.5,
            agreement_mult=0.95,
            ticker="KXHIGHNY",
        )
        assert mult < 1.0
        assert flag is not None
        assert "missing_orderbook" in flag

    def test_wide_spread_penalty(self):
        """Bid-ask spread >10¢ returns phantom edge penalty."""
        spread_wide = _make_orderbook(yes_price=60, no_price=40)  # 20¢ spread
        engine = WeatherSignalEngine(orderbooks={"KXHIGHNY": spread_wide})
        mult, flag = engine._detect_phantom_edge(
            forecast_temp=75.0,
            threshold=85.0,
            market_prob=0.55,
            agreement_mult=0.95,
            ticker="KXHIGHNY",
        )
        assert mult < 1.0
        assert flag is not None
        assert "wide_spread" in flag

    def test_clean_signal_no_penalty(self):
        """No phantom edge conditions → multiplier = 1.0 and flag = None."""
        engine = WeatherSignalEngine(
            orderbooks={"KXHIGHNY": _make_orderbook(yes_price=55, no_price=45)}  # 10¢ spread = okay
        )
        mult, _flag = engine._detect_phantom_edge(
            forecast_temp=80.0,  # 5°F from 85°F threshold
            threshold=85.0,
            market_prob=0.55,
            agreement_mult=0.95,
            ticker="KXHIGHNY",
        )
        assert mult == 1.0
        assert _flag is None

    def test_penalty_compounds_multiplicatively(self):
        """Multiple phantom edge conditions compound penalty multiplicatively with 0.1 floor."""
        engine = WeatherSignalEngine(orderbooks={})  # Missing orderbook = 0.6x
        mult, _ = engine._detect_phantom_edge(
            forecast_temp=50.0,  # Logistic asymptote = 0.5x
            threshold=85.0,
            market_prob=0.5,
            agreement_mult=0.3,  # Low consensus = 0.4x
            ticker="KXHIGHNY",
        )
        # Expected: 0.5 * 0.4 * 0.6 = 0.12
        assert mult < 1.0
        assert mult >= 0.1, "Penalty floor should be 0.1"
        assert mult == pytest.approx(0.12, abs=0.001)

    def test_signal_confidence_with_phantom_edge(self):
        """Phantom edge penalty reduces confidence in computed TradingSignal."""
        engine = WeatherSignalEngine(orderbooks={})
        forecasts = {"nyc": _make_forecast(high_temp_f=50.0)}
        markets = {"KXHIGHNY": _make_market_data(threshold=85.0)}
        signals = engine.compute_signals(forecasts, markets)
        assert len(signals) == 1
        signal = signals[0]
        # Missing orderbook + logistic asymptote should reduce confidence
        assert signal.phantom_edge_flag is not None
        assert "missing_orderbook" in signal.phantom_edge_flag
