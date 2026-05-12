"""Shared test fixtures and configuration for TraderBot tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def sample_market_data() -> dict:
    """Kalshi-formatted market data for a single market."""
    return {
        "ticker": "KXBTCD-26MAR31-T55000",
        "question": "Will BTC touch $55,000 before March 31?",
        "last_price_dollars": "0.65",
        "yes_bid_dollars": "0.64",
        "yes_ask_dollars": "0.66",
        "no_bid_dollars": "0.34",
        "no_ask_dollars": "0.36",
        "volume": 15000,
        "open_interest": 2500,
        "close_time": datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        "status": "open",
        "event_ticker": "KXBTCD-26MAR31",
        "category": "crypto",
    }


@pytest.fixture
def sample_orderbook_data() -> dict:
    """Kalshi-formatted orderbook data."""
    return {
        "yes": [
            {"price": 64, "size": 100},
            {"price": 63, "size": 250},
            {"price": 62, "size": 500},
        ],
        "no": [
            {"price": 36, "size": 150},
            {"price": 37, "size": 200},
            {"price": 38, "size": 300},
        ],
    }


@pytest.fixture
def sample_trade_data() -> dict:
    """Kalshi-formatted trade data."""
    return {
        "ticker": "KXBTCD-26MAR31-T55000",
        "price": 65,
        "quantity": 10,
        "side": "yes",
        "timestamp": datetime(2025, 4, 20, 12, 0, 0, tzinfo=UTC),
    }


@pytest.fixture
def sample_portfolio_state() -> dict:
    """Portfolio state for risk checking."""
    return {
        "portfolio_value_cents": 100000_00,  # $100,000
        "peak_value_cents": 110000_00,  # $110,000
        "current_positions_value_cents": 4000_00,  # $4,000
        "today_realized_loss_cents": 500_00,  # $500
        "today_unrealized_loss_cents": 200_00,  # $200
        "open_positions_count": 8,
    }
