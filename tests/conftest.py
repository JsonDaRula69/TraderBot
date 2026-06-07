"""Shared test fixtures and configuration for TraderBot tests."""

from __future__ import annotations

import pytest

pytest.register_assert_rewrite("tests.news")

import re
import sqlite3

pytest_plugins = ["tests.integration_conftest"]
from datetime import UTC, datetime
from pathlib import Path

from traderbot.kalshi.provider import (
    MarketSnapshot,
    MockDataProvider,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
    SettlementResult,
)
from traderbot.simulation.paper_trader import PaperSlippageModel, PaperTrader


@pytest.fixture(scope="session", autouse=True)
def _restore_workspace_templates():
    """Snapshot git-tracked workspace templates before tests; restore after.

    Tests that invoke heartbeat or WAL code can mutate HEARTBEAT_DATA.md
    and SESSION-STATE.md via module-level default paths. This fixture
    snapshots both files before the session and restores them on teardown,
    ensuring the git-tracked templates stay in their original state.
    """
    from traderbot.paths import get_workspace_dir, WORKSPACE_TEMPLATE_FILES

    ws = get_workspace_dir()
    snapshots: dict[str, bytes] = {}

    for name in WORKSPACE_TEMPLATE_FILES:
        target = ws / name
        if target.exists():
            snapshots[name] = target.read_bytes()

    yield

    for name, content in snapshots.items():
        target = ws / name
        target.write_bytes(content)

# ---------------------------------------------------------------------------
# Re-apply existing fixtures (kept from original conftest) — they are still
# used by older tests.  We add new fixtures below without disturbing them.
# ---------------------------------------------------------------------------

# The existing conftest defined fixtures: sample_market_data, sample_orderbook_data,
# sample_trade_data, sample_portfolio_state.  They are imported from the original
# file which we read.  Since we are *overwriting* conftest.py, we must include them.

TIMESTAMP = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_market_data() -> dict:
    """Kalshi-formatted market data for a single market."""
    return {
        "ticker": "KXBTCD-26MAR31-T55000",
        "question": "Will BTC touch $55,000 before March 31?",
        "outcome_prices": ["0.65", "0.35"],
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
        "portfolio_value_cents": 100000_00,
        "peak_value_cents": 110000_00,
        "current_positions_value_cents": 4000_00,
        "today_realized_loss_cents": 500_00,
        "today_unrealized_loss_cents": 200_00,
        "open_positions_count": 8,
    }


# ---------------------------------------------------------------------------
# New fixtures for unit-test modules
# ---------------------------------------------------------------------------


def _make_ob_levels(*pairs: tuple[int, int]) -> tuple[OrderBookLevelSnapshot, ...]:
    """Helper: list of (price_cents, size) → tuple[OrderBookLevelSnapshot, ...]."""
    return tuple(OrderBookLevelSnapshot(price_cents=p, size=s) for p, s in pairs)


@pytest.fixture
def mock_provider() -> MockDataProvider:
    """MockDataProvider with pre-configured markets, orderbooks, and settlements."""
    markets = {
        "TEST-MKT1": MarketSnapshot(
            ticker="TEST-MKT1",
            status="open",
            open_interest_cents=10_000_00,
            close_time=datetime(2026, 12, 31, 23, 59, 0, tzinfo=UTC),
        ),
        "TEST-MKT2": MarketSnapshot(
            ticker="TEST-MKT2",
            status="open",
            open_interest_cents=5_000_00,
            close_time=datetime(2026, 12, 31, 23, 59, 0, tzinfo=UTC),
        ),
        "TEST-SETTLED": MarketSnapshot(
            ticker="TEST-SETTLED",
            status="settled",
            open_interest_cents=0,
            close_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        ),
    }

    orderbooks = {
        "TEST-MKT1": OrderBookSnapshot(
            yes_bids=_make_ob_levels((50, 200), (49, 300)),
            no_bids=_make_ob_levels((50, 200), (51, 150)),
            timestamp=TIMESTAMP,
        ),
        "TEST-MKT2": OrderBookSnapshot(
            yes_bids=_make_ob_levels((40, 100)),
            no_bids=_make_ob_levels((60, 100)),
            timestamp=TIMESTAMP,
        ),
    }

    settlements = {
        "TEST-SETTLED": SettlementResult(
            ticker="TEST-SETTLED",
            outcome=True,
            settled_at=datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC),
        ),
    }

    return MockDataProvider(markets=markets, orderbooks=orderbooks, settlements=settlements)


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """In-memory SQLite connection for PaperTrader tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def paper_trader(mock_provider: MockDataProvider, in_memory_db: sqlite3.Connection) -> PaperTrader:
    """PaperTrader wired to mock_provider and in-memory DB."""
    return PaperTrader(
        provider=mock_provider,
        db_conn=in_memory_db,
        initial_cash_cents=1_000_00,
        slippage_model=PaperSlippageModel(base_slippage_cents=1),
    )


# ---------------------------------------------------------------------------
# ANSI-stripping helper for CLI help-text tests.
# On CI (GITHUB_ACTIONS=true), Rich forces terminal codes into --help output.
# Substring assertions like assert "--flag" in result.output fail because ANSI
# sequences split the dashes from the flag name.
# Use this function in test assertions to get the plain text.
# ---------------------------------------------------------------------------

_ANSI_ESCAPE = re.compile(r"\x1B\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)
