"""Tests for technical indicators."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.analysis.indicators import (
    BollingerBands,
    bollinger_bands,
    ema,
    rsi,
    sma,
    volume_weighted_price,
)
from traderbot.kalshi.models import Trade

# --- SMA ---


@pytest.mark.unit
def test_sma_known_value() -> None:
    assert sma([50, 60, 70], 3) == 60.0


@pytest.mark.unit
def test_sma_fewer_prices_than_period() -> None:
    assert sma([50, 60], 5) == 55.0


@pytest.mark.unit
def test_sma_empty_raises() -> None:
    with pytest.raises(ValueError):
        sma([], 3)


@pytest.mark.unit
def test_sma_single_value() -> None:
    assert sma([42], 5) == 42.0


# --- EMA ---


@pytest.mark.unit
def test_ema_convergence_to_higher_price() -> None:
    prices = [50] * 10 + [60] * 10
    result = ema(prices, 5)
    assert 55.0 < result < 60.0


@pytest.mark.unit
def test_ema_single_element() -> None:
    assert ema([42], 5) == 42.0


@pytest.mark.unit
def test_ema_empty_raises() -> None:
    with pytest.raises(ValueError):
        ema([], 3)


@pytest.mark.unit
def test_ema_constant_prices() -> None:
    assert ema([50, 50, 50, 50], 3) == 50.0


# --- RSI ---


@pytest.mark.unit
def test_rsi_all_increasing() -> None:
    prices = list(range(10, 50))
    result = rsi(prices, 14)
    assert result > 90.0


@pytest.mark.unit
def test_rsi_all_decreasing() -> None:
    prices = list(range(50, 10, -1))
    result = rsi(prices, 14)
    assert result < 10.0


@pytest.mark.unit
def test_rsi_constant_prices() -> None:
    prices = [50] * 20
    result = rsi(prices, 14)
    assert 45.0 <= result <= 55.0


@pytest.mark.unit
def test_rsi_single_element() -> None:
    assert rsi([50]) == 50.0


@pytest.mark.unit
def test_rsi_empty_raises() -> None:
    with pytest.raises(ValueError):
        rsi([], 14)


@pytest.mark.unit
def test_rsi_two_elements_no_loss() -> None:
    assert rsi([10, 20]) == 100.0


@pytest.mark.unit
def test_rsi_two_elements_no_gain() -> None:
    assert rsi([20, 10]) == 0.0


# --- Bollinger Bands ---


@pytest.mark.unit
def test_bollinger_middle_equals_sma() -> None:
    prices = [40, 50, 60, 55, 45]
    bb = bollinger_bands(prices, 5)
    assert bb.middle == round(sum(prices) / len(prices))


@pytest.mark.unit
def test_bollinger_upper_greater_than_middle() -> None:
    prices = [40, 50, 60, 55, 45, 50, 52]
    bb = bollinger_bands(prices, 5)
    assert bb.upper > bb.middle > bb.lower


@pytest.mark.unit
def test_bollinger_empty_raises() -> None:
    with pytest.raises(ValueError):
        bollinger_bands([], 5)


@pytest.mark.unit
def test_bollinger_single_value() -> None:
    bb = bollinger_bands([50], 5)
    assert bb.lower == bb.middle == bb.upper == 50


@pytest.mark.unit
def test_bollinger_model_fields() -> None:
    bb = BollingerBands(lower=40, middle=50, upper=60)
    assert bb.lower == 40
    assert bb.middle == 50
    assert bb.upper == 60


# --- Volume-Weighted Price ---


@pytest.mark.unit
def test_vwap_two_trades() -> None:
    t1 = Trade(
        ticker="TEST",
        price=50,
        quantity=10,
        side="yes",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    t2 = Trade(
        ticker="TEST",
        price=60,
        quantity=10,
        side="yes",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert volume_weighted_price([t1, t2]) == 55


@pytest.mark.unit
def test_vwap_empty_raises() -> None:
    with pytest.raises(ValueError):
        volume_weighted_price([])


@pytest.mark.unit
def test_vwap_weighted_by_quantity() -> None:
    t1 = Trade(
        ticker="TEST",
        price=20,
        quantity=100,
        side="yes",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    t2 = Trade(
        ticker="TEST",
        price=80,
        quantity=1,
        side="no",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = volume_weighted_price([t1, t2])
    assert result == 21  # (20*100 + 80*1) / 101 = 20.79... → 21
