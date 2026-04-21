"""Shared test fixtures and configuration for TraderBot tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_market_data() -> dict:
    """Raw Kalshi API response for a single market."""
    return {
        "ticker": "KXBTCD-26MAR31-T55000",
        "question": "Will BTC touch $55,000 before March 31?",
        "outcome_prices": ["0.65", "0.35"],
        "volume": 15000,
        "open_interest": 2500,
        "close_time": "2026-03-31T23:59:59Z",
        "state": "open",
        "event_ticker": "KXBTCD-26MAR31",
        "category": "crypto",
    }


@pytest.fixture
def sample_orderbook_data() -> dict:
    """Raw Kalshi API response for an orderbook."""
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
    """Raw Kalshi API response for a trade."""
    return {
        "ticker": "KXBTCD-26MAR31-T55000",
        "price": 65,
        "quantity": 10,
        "side": "yes",
        "timestamp": 1745184000,
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