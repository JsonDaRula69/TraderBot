"""Tests for analysis registry, CategoryAnalyzer protocol, and GenericAnalyzer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from traderbot.analysis.registry import (
    AnalysisRegistry,
    CategorySignals,
    GenericAnalyzer,
)
from traderbot.kalshi.models import MarketCategory


# --- CategorySignals model ---


@pytest.mark.unit
def test_category_signals_valid() -> None:
    cs = CategorySignals(
        category=MarketCategory.ECONOMICS,
        signals=["RSI=45.0"],
        confidence=0.8,
        data_sources=["rsi"],
    )
    assert cs.category == MarketCategory.ECONOMICS
    assert cs.signals == ["RSI=45.0"]
    assert cs.confidence == 0.8
    assert cs.data_sources == ["rsi"]


@pytest.mark.unit
def test_category_signals_rejects_extra_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CategorySignals(
            category=MarketCategory.POLITICS,
            signals=[],
            confidence=0.5,
            data_sources=[],
            extra_field=123,
        )


@pytest.mark.unit
def test_category_signals_confidence_above_1_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CategorySignals(
            category=MarketCategory.SPORTS,
            signals=[],
            confidence=1.5,
            data_sources=[],
        )


@pytest.mark.unit
def test_category_signals_confidence_below_0_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CategorySignals(
            category=MarketCategory.WEATHER,
            signals=[],
            confidence=-0.1,
            data_sources=[],
        )


@pytest.mark.unit
def test_market_category_values() -> None:
    assert MarketCategory.ECONOMICS == "economics"
    assert MarketCategory.POLITICS == "politics"
    assert MarketCategory.WEATHER == "weather"
    assert MarketCategory.SPORTS == "sports"
    assert MarketCategory.ENTERTAINMENT == "entertainment"
    assert MarketCategory.SCIENCE_AND_TECHNOLOGY == "science_and_technology"


# --- GenericAnalyzer ---


@pytest.mark.unit
def test_generic_analyzer_empty_data() -> None:
    analyzer = GenericAnalyzer()
    result = analyzer.analyze({}, MarketCategory.ECONOMICS)
    assert result.category == MarketCategory.ECONOMICS
    assert result.signals == []
    assert result.confidence == 0.3
    assert result.data_sources == []


@pytest.mark.unit
def test_generic_analyzer_with_prices() -> None:
    analyzer = GenericAnalyzer()
    prices = [50, 52, 48, 55, 60, 58, 62, 65, 63, 67, 70, 68, 72, 75, 71, 69, 73, 76, 74, 78]
    result = analyzer.analyze({"prices": prices}, MarketCategory.POLITICS)
    assert result.category == MarketCategory.POLITICS
    assert len(result.signals) > 0
    assert "rsi" in result.data_sources
    assert "bollinger" in result.data_sources
    assert "ema" in result.data_sources


# --- AnalysisRegistry ---


@pytest.mark.unit
def test_registry_default_returns_generic() -> None:
    registry = AnalysisRegistry()
    analyzer = registry.get(MarketCategory.ECONOMICS)
    assert isinstance(analyzer, GenericAnalyzer)


@pytest.mark.unit
def test_registry_register_and_get() -> None:
    registry = AnalysisRegistry()

    class FakeAnalyzer:
        def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
            return CategorySignals(
                category=category, signals=["FAKE"], confidence=0.99, data_sources=["fake"]
            )

    fake = FakeAnalyzer()
    registry.register(MarketCategory.SPORTS, fake)
    result = registry.analyze({}, MarketCategory.SPORTS)
    assert result.signals == ["FAKE"]
    assert result.confidence == 0.99


@pytest.mark.unit
def test_registry_unregistered_category_uses_generic() -> None:
    registry = AnalysisRegistry()

    class FakeAnalyzer:
        def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
            return CategorySignals(
                category=category, signals=["FAKE"], confidence=0.5, data_sources=["fake"]
            )

    registry.register(MarketCategory.SPORTS, FakeAnalyzer())

    result = registry.analyze({}, MarketCategory.ECONOMICS)
    assert isinstance(result, CategorySignals)
    assert result.category == MarketCategory.ECONOMICS


@pytest.mark.unit
def test_registry_analyze_delegates_to_registered() -> None:
    registry = AnalysisRegistry()

    class SportsAnalyzer:
        def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
            return CategorySignals(
                category=category, signals=["MOMENTUM=high"], confidence=0.7, data_sources=["sports_api"]
            )

    registry.register(MarketCategory.SPORTS, SportsAnalyzer())
    result = registry.analyze({"ticker": "SPX"}, MarketCategory.SPORTS)
    assert result.category == MarketCategory.SPORTS
    assert "MOMENTUM=high" in result.signals
    assert "sports_api" in result.data_sources


@pytest.mark.unit
def test_category_analyzer_protocol_check() -> None:
    from traderbot.analysis.registry import CategoryAnalyzer

    class GoodAnalyzer:
        def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
            return CategorySignals(
                category=category, signals=[], confidence=0.0, data_sources=[]
            )

    class BadAnalyzer:
        def other_method(self) -> None:
            pass

    assert isinstance(GoodAnalyzer(), CategoryAnalyzer)
    assert not isinstance(BadAnalyzer(), CategoryAnalyzer)


# --- Cross-module import checks ---


@pytest.mark.unit
def test_simulation_imports_market_category() -> None:
    from datetime import UTC, datetime

    from traderbot.kalshi.models import Market, PortfolioState
    from traderbot.simulation.engine import Context

    portfolio = PortfolioState(
        portfolio_value_cents=1000000,
        peak_value_cents=1000000,
        current_positions_value_cents=0,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=0,
    )
    from traderbot.risk.circuit_breaker import CircuitBreakerState
    from traderbot.kalshi.models import Trade
    breaker_state = CircuitBreakerState()
    ctx = Context(
        portfolio=portfolio,
        market=Market(
            ticker="KX-TEST",
            question="Test?",
            outcome_prices=["0.65", "0.35"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            status="open",
            event_ticker="KX-EVENT",
            category="technology",
        ),
        recent_trades=[],
        sentiment_score=0.5,
        breaker_state=breaker_state,
    )


@pytest.mark.unit
def test_analysis_imports_market_category() -> None:
    from traderbot.analysis import CategorySignals

    cs = CategorySignals(
        category=MarketCategory.SCIENCE_AND_TECHNOLOGY,
        signals=["test"],
        confidence=0.5,
        data_sources=["test"],
    )
    assert cs.category == MarketCategory.SCIENCE_AND_TECHNOLOGY