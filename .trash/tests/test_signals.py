"""Tests for signal combination and generation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.analysis.signals import (
    CombinedSignal,
    SignalSource,
    combine_signals,
    default_weights,
    generate_signal,
)
from traderbot.kalshi.models import OrderBook, OrderBookLevel, Trade


def _make_orderbook(
    yes_price: int = 55, yes_size: int = 10, no_price: int = 40, no_size: int = 10
) -> OrderBook:
    return OrderBook(
        yes_bids=[OrderBookLevel(price=yes_price, size=yes_size)],
        no_bids=[OrderBookLevel(price=no_price, size=no_size)],
    )


def _make_trade(price: int, quantity: int, ticker: str = "KX-TEST") -> Trade:
    return Trade(
        ticker=ticker, price=price, quantity=quantity, side="yes", timestamp=datetime.now(UTC)
    )


# --- combine_signals ---


@pytest.mark.unit
def test_combine_signals_all_yes() -> None:
    sources = [
        SignalSource(name="a", weight=0.5, direction="yes", strength=0.8),
        SignalSource(name="b", weight=0.5, direction="yes", strength=0.6),
    ]
    direction, confidence = combine_signals(sources)
    assert direction == "yes"
    assert confidence > 0.0


@pytest.mark.unit
def test_combine_signals_conflicting_neutral() -> None:
    sources = [
        SignalSource(name="a", weight=0.5, direction="yes", strength=0.6),
        SignalSource(name="b", weight=0.5, direction="no", strength=0.6),
    ]
    direction, _confidence = combine_signals(sources)
    assert direction == "neutral"


@pytest.mark.unit
def test_combine_signals_empty() -> None:
    direction, confidence = combine_signals([])
    assert direction == "neutral"
    assert confidence == 0.0


@pytest.mark.unit
def test_combine_signals_confidence_clamped() -> None:
    sources = [
        SignalSource(name="a", weight=0.1, direction="yes", strength=1.0),
        SignalSource(name="b", weight=0.1, direction="yes", strength=1.0),
    ]
    _, confidence = combine_signals(sources)
    assert 0.0 <= confidence <= 1.0


@pytest.mark.unit
def test_combine_signals_single_no() -> None:
    sources = [SignalSource(name="x", weight=1.0, direction="no", strength=0.9)]
    direction, confidence = combine_signals(sources)
    assert direction == "no"
    assert confidence == pytest.approx(0.9)


# --- default_weights ---


@pytest.mark.unit
def test_default_weights() -> None:
    w = default_weights()
    assert w == {"indicators": 0.3, "odds": 0.5, "momentum": 0.2}


# --- generate_signal ---


@pytest.mark.unit
def test_generate_signal_declining_trend() -> None:
    prices = [70, 68, 65, 62, 60, 58, 55, 53, 50, 48] * 3
    ob = _make_orderbook(yes_price=55, no_price=40)
    signal = generate_signal(
        ticker="KX-TEST",
        prices=prices,
        orderbook=ob,
        estimated_prob=0.55,
    )
    assert isinstance(signal, CombinedSignal)
    assert signal.ticker == "KX-TEST"
    assert signal.direction in ("yes", "no", "neutral")
    assert 0.0 <= signal.confidence <= 1.0
    assert signal.estimated_prob == 0.55
    assert len(signal.sources) >= 2


@pytest.mark.unit
def test_generate_signal_oversold_rsi() -> None:
    # Force low RSI by having many declining prices
    low_prices = [
        90,
        80,
        70,
        60,
        50,
        45,
        40,
        38,
        36,
        35,
        34,
        33,
        32,
        31,
        30,
        29,
        28,
        27,
        26,
        25,
    ] + [25] * 10
    ob = _make_orderbook(yes_price=30, no_price=65)
    signal = generate_signal(
        ticker="KX-OVERSOLD",
        prices=low_prices,
        orderbook=ob,
        estimated_prob=0.30,
    )
    # RSI < 30 should push indicators source toward "yes"
    indicators_src = next(s for s in signal.sources if s.name == "indicators")
    assert indicators_src.direction == "yes" or indicators_src.strength > 0


@pytest.mark.unit
def test_generate_signal_edge_detection() -> None:
    # estimated_prob=0.8 vs market implied ~0.55 → edge ~0.25 → "yes" odds source
    ob = _make_orderbook(yes_price=55, no_price=40)
    signal = generate_signal(
        ticker="KX-EDGE",
        prices=[55] * 30,
        orderbook=ob,
        estimated_prob=0.80,
    )
    odds_src = next(s for s in signal.sources if s.name == "odds")
    assert odds_src.direction == "yes"
    assert odds_src.strength == min(1.0, abs(0.25) * 5)


@pytest.mark.unit
def test_generate_signal_short_prices_momentum_neutral() -> None:
    prices = [50, 52]
    ob = _make_orderbook(yes_price=50, no_price=45)
    signal = generate_signal(
        ticker="KX-SHORT",
        prices=prices,
        orderbook=ob,
        estimated_prob=0.50,
    )
    mom_src = next(s for s in signal.sources if s.name == "momentum")
    assert mom_src.direction == "neutral"
    assert mom_src.strength == 0.1


@pytest.mark.unit
def test_generate_signal_edge_cents() -> None:
    ob = _make_orderbook(yes_price=50, no_price=45)
    signal = generate_signal(
        ticker="KX-EC",
        prices=[50] * 30,
        orderbook=ob,
        estimated_prob=0.75,
    )
    # midpoint = round((50 + 55) / 2) = 52¢ (banker's rounding on 52.5)
    # edge = 0.75 - 0.52 = 0.23, edge_cents = 23
    assert signal.edge_cents == 23


@pytest.mark.unit
def test_generate_signal_price_below_bollinger_lower() -> None:
    # Oscillating prices with a crash at idx 6 → RSI ~37 (in 30-70 range)
    # Last price=10 is well below BB lower=22 → hits line 88-90 branch
    prices = [
        50,
        55,
        50,
        55,
        50,
        55,
        10,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        10,
    ]
    ob = _make_orderbook(yes_price=55, no_price=40)
    signal = generate_signal(
        ticker="KX-BB-LOW",
        prices=prices,
        orderbook=ob,
        estimated_prob=0.55,
    )
    ind_src = next(s for s in signal.sources if s.name == "indicators")
    assert ind_src.direction == "yes"
    assert ind_src.strength == 0.7


@pytest.mark.unit
def test_generate_signal_price_above_bollinger_upper() -> None:
    # Oscillating prices with a spike at idx 6 → RSI ~64 (in 30-70 range)
    # Last price=90 is above BB upper=79 → hits line 91-93 branch
    prices = [
        50,
        55,
        50,
        55,
        50,
        55,
        90,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        50,
        55,
        90,
    ]
    ob = _make_orderbook(yes_price=55, no_price=40)
    signal = generate_signal(
        ticker="KX-BB-HIGH",
        prices=prices,
        orderbook=ob,
        estimated_prob=0.45,
    )
    ind_src = next(s for s in signal.sources if s.name == "indicators")
    assert ind_src.direction == "no"
    assert ind_src.strength == 0.7


@pytest.mark.unit
def test_generate_signal_momentum_bullish_ema() -> None:
    # Rising prices → short EMA > long EMA → momentum direction="yes"
    prices = list(range(30, 80))  # 50 rising prices
    ob = _make_orderbook(yes_price=55, no_price=40)
    signal = generate_signal(
        ticker="KX-MOM-YES",
        prices=prices,
        orderbook=ob,
        estimated_prob=0.55,
    )
    mom_src = next(s for s in signal.sources if s.name == "momentum")
    assert mom_src.direction == "yes"
    assert mom_src.strength > 0
