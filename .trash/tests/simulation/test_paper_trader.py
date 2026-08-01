"""Tests for PaperTrader buying power (cash-only, matching Kalshi)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from traderbot.db.positions import init_table as init_positions_table
from traderbot.kalshi.provider import (
    MarketSnapshot,
    MockDataProvider,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
)
from traderbot.risk import RiskCheckError
from traderbot.simulation.paper_trader import PaperFill, PaperTrader

NOW = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
TICKER = "MKT-001"


def _provider(ticker: str = TICKER) -> MockDataProvider:
    return MockDataProvider(
        markets={
            ticker: MarketSnapshot(
                ticker=ticker,
                status="open",
                open_interest_cents=10_000_00,
                close_time=NOW,
                settlement_result=None,
            )
        },
        orderbooks={
            ticker: OrderBookSnapshot(
                yes_bids=(OrderBookLevelSnapshot(price_cents=50, size=1000),),
                no_bids=(OrderBookLevelSnapshot(price_cents=50, size=1000),),
                timestamp=NOW,
            )
        },
    )


def _trader(cash: int = 10_000) -> tuple[PaperTrader, sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(provider=_provider(), db_conn=conn, initial_cash_cents=cash)
    return trader, conn


@pytest.mark.asyncio
async def test_submit_order_accepted_when_cash_sufficient() -> None:
    """Small order passes cash-only position limit and gets Kelly-sized."""
    trader, conn = _trader()

    fill = await trader.submit_order(
        ticker=TICKER,
        side="yes",
        quantity=20,
        price_cents=50,
        edge_estimate=0.10,
    )

    assert fill is not None
    assert fill.quantity > 0
    assert fill.price_cents == 51  # 50 + 1 base slippage
    assert trader._cash_cents < 10_000
    conn.close()


@pytest.mark.asyncio
async def test_submit_order_rejected_exceeds_cash_only_position_limit() -> None:
    """Risk gate rejects orders exceeding 15%% of cash-only buying power."""
    trader, conn = _trader()

    with pytest.raises(RiskCheckError, match="Position would exceed"):
        await trader.submit_order(
            ticker=TICKER,
            side="yes",
            quantity=31,  # 31 * 50 = 1_550 > 10_000 * 0.15 = 1_500
            price_cents=50,
            edge_estimate=0.10,
        )
    conn.close()


@pytest.mark.asyncio
async def test_existing_position_reduces_available_buying_power() -> None:
    """Existing cost basis reduces cash, tightening the cash-only limit.

    KEY BEHAVIORAL CHANGE: Old model had constant 10_000 buying power.
    New model: buying power = cash, drops as positions consume cash.
    """
    trader, conn = _trader(cash=10_000)

    fill1 = await trader.submit_order(
        ticker=TICKER,
        side="yes",
        quantity=20,
        price_cents=50,
        edge_estimate=0.10,
    )
    assert fill1 is not None
    assert trader._cash_cents < 10_000

    with pytest.raises(RiskCheckError, match="Position would exceed"):
        await trader.submit_order(
            ticker=TICKER,
            side="yes",
            quantity=20,
            price_cents=50,
            edge_estimate=0.10,
        )
    conn.close()


@pytest.mark.asyncio
async def test_order_accepted_after_cash_regenerated() -> None:
    """Closing a position restores cash, allowing new orders again."""
    trader, conn = _trader(cash=10_000)

    fill1 = await trader.submit_order(
        ticker=TICKER,
        side="yes",
        quantity=10,
        price_cents=50,
        edge_estimate=0.10,
    )
    assert fill1 is not None

    close_fill = PaperFill(
        ticker=TICKER,
        side="no",
        price_cents=55,
        quantity=-fill1.quantity,
        slippage_cents=0,
        timestamp=NOW,
    )
    trader.record_fill(close_fill)

    assert trader._cash_cents > 9_000

    fill2 = await trader.submit_order(
        ticker=TICKER,
        side="yes",
        quantity=10,
        price_cents=50,
        edge_estimate=0.10,
    )
    assert fill2 is not None
    conn.close()


def test_mark_settled_void_refunds_cost(tmp_path: Path) -> None:
    """Void settlement refunds cost basis to cash and zeros quantity."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(provider=_provider(), db_conn=conn, initial_cash_cents=10_000)

    trader.record_fill(
        PaperFill(ticker=TICKER, side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=NOW)
    )
    assert trader._cash_cents == 10_000 - 500

    trader.mark_settled(TICKER, "void")

    pos = trader.get_positions()
    assert len(pos) == 0 or (len(pos) == 1 and pos[0].quantity == 0)

    # Cash should be restored — refunded the 500¢ cost
    assert trader._cash_cents == 10_000
    conn.close()


def test_position_value_cents_preserved() -> None:
    """_position_value_cents() still exists and works for reporting."""
    trader, conn = _trader()

    assert trader._position_value_cents() == 0

    trader.record_fill(
        PaperFill(
            ticker="A",
            side="yes",
            price_cents=50,
            quantity=10,
            slippage_cents=0,
            timestamp=NOW,
        )
    )

    assert trader._position_value_cents() == 500
    conn.close()


@pytest.mark.asyncio
async def test_submit_order_yes_thin_asks_increases_slippage() -> None:
    """Buy YES with thin asks produces higher fill price than best bid.

    Regression test: previously, buy orders incorrectly walked bids.
    Now they cross asks, so thin asks produce a higher fill price than
    the midpoint + base slippage would suggest.
    """
    provider = MockDataProvider(
        markets={
            TICKER: MarketSnapshot(
                ticker=TICKER,
                status="open",
                open_interest_cents=10_000_00,
                close_time=NOW,
                settlement_result=None,
            )
        },
        orderbooks={
            TICKER: OrderBookSnapshot(
                yes_bids=(OrderBookLevelSnapshot(price_cents=50, size=10_000),),
                yes_asks=(OrderBookLevelSnapshot(price_cents=55, size=10),),
                no_bids=(OrderBookLevelSnapshot(price_cents=50, size=10_000),),
                no_asks=(OrderBookLevelSnapshot(price_cents=45, size=10_000),),
                timestamp=NOW,
            )
        },
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000)

    fill = await trader.submit_order(
        ticker=TICKER,
        side="yes",
        quantity=20,
        price_cents=50,
        edge_estimate=0.10,
    )

    assert fill is not None
    # Only 10 ask contracts exist at 55 → walks asks → avg=55, +1 base → 56
    # Under old bug (walked bids at 50) this would be 51
    assert fill.price_cents == 56
    assert fill.slippage_cents == 6  # 56 - 50 = 6 (was 1 under old bug)
    conn.close()


# ═══════════════════════════════════════════════
#  mark_settled(): settlement payout + mirror write
# ═══════════════════════════════════════════════


def test_mark_settled_yes_win() -> None:
    """YES position wins when outcome=True — credits 100¢ per contract."""
    trader, conn = _trader(cash=1_000)
    init_positions_table(conn)

    trader.record_fill(
        PaperFill(ticker=TICKER, side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=NOW)
    )
    assert trader._cash_cents == 1_000 - 500  # cost deducted

    trader.mark_settled(TICKER, outcome=True)

    # Cash: 500 remaining + 100*10 payout = 1500
    assert trader._cash_cents == 1_500

    # Paper position: status=settled, quantity=0
    pos = trader.get_positions()
    assert pos[0].status == "settled"
    assert pos[0].quantity == 0

    # Positions table mirror write
    db_pos = conn.execute("SELECT * FROM positions WHERE ticker = ?", (TICKER,)).fetchone()
    assert db_pos is not None
    assert db_pos["side"] == "yes"
    assert db_pos["settlement_result"] == 1
    assert db_pos["pnl_cents"] == 1000 - 500  # payout - cost
    conn.close()


def test_mark_settled_no_win() -> None:
    """NO position wins when outcome=False — credits 100¢ per contract."""
    trader, conn = _trader(cash=1_000)
    init_positions_table(conn)

    trader.record_fill(
        PaperFill(ticker=TICKER, side="no", price_cents=40, quantity=5, slippage_cents=0, timestamp=NOW)
    )
    assert trader._cash_cents == 1_000 - 200  # cost deducted

    trader.mark_settled(TICKER, outcome=False)

    # Cash: 800 remaining + 100*5 payout = 1300
    assert trader._cash_cents == 1_300

    # Paper position: status=settled, quantity=0
    pos = trader.get_positions()
    assert pos[0].status == "settled"
    assert pos[0].quantity == 0

    # Positions table mirror write
    db_pos = conn.execute("SELECT * FROM positions WHERE ticker = ?", (TICKER,)).fetchone()
    assert db_pos is not None
    assert db_pos["side"] == "no"
    assert db_pos["settlement_result"] == 0  # False → 0 in SQLite
    assert db_pos["pnl_cents"] == 500 - 200  # payout - cost
    conn.close()


def test_mark_settled_yes_lose() -> None:
    """YES position loses when outcome=False — no payout, cost is sunk."""
    trader, conn = _trader(cash=1_000)
    init_positions_table(conn)

    trader.record_fill(
        PaperFill(ticker=TICKER, side="yes", price_cents=60, quantity=10, slippage_cents=0, timestamp=NOW)
    )
    assert trader._cash_cents == 1_000 - 600  # cost deducted

    trader.mark_settled(TICKER, outcome=False)

    # Cash unchanged: 400 remaining, no payout
    assert trader._cash_cents == 400

    # Paper position: status=settled, quantity=0
    pos = trader.get_positions()
    assert pos[0].status == "settled"
    assert pos[0].quantity == 0

    # Positions table mirror write
    db_pos = conn.execute("SELECT * FROM positions WHERE ticker = ?", (TICKER,)).fetchone()
    assert db_pos is not None
    assert db_pos["side"] == "yes"
    assert db_pos["settlement_result"] == 0  # False → 0
    assert db_pos["pnl_cents"] == -600  # lost full cost
    conn.close()


def test_mark_settled_no_lose() -> None:
    """NO position loses when outcome=True — no payout, cost is sunk."""
    trader, conn = _trader(cash=1_000)
    init_positions_table(conn)

    trader.record_fill(
        PaperFill(ticker=TICKER, side="no", price_cents=30, quantity=8, slippage_cents=0, timestamp=NOW)
    )
    assert trader._cash_cents == 1_000 - 240  # cost deducted

    trader.mark_settled(TICKER, outcome=True)

    # Cash unchanged: 760 remaining, no payout
    assert trader._cash_cents == 760

    # Paper position: status=settled, quantity=0
    pos = trader.get_positions()
    assert pos[0].status == "settled"
    assert pos[0].quantity == 0

    # Positions table mirror write
    db_pos = conn.execute("SELECT * FROM positions WHERE ticker = ?", (TICKER,)).fetchone()
    assert db_pos is not None
    assert db_pos["side"] == "no"
    assert db_pos["settlement_result"] == 1
    assert db_pos["pnl_cents"] == -240  # lost full cost
    conn.close()
