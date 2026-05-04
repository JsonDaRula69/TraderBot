"""Tests for simulation/paper_trader.py — PaperTrader composing with DemoAdapter."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from traderbot.kalshi.demo import DemoAdapter
from traderbot.kalshi.models import (
    Market,
    OrderBook,
    OrderBookLevel,
)
from traderbot.simulation.paper_trader import (
    PaperFill,
    PaperPortfolio,
    PaperPosition,
    PaperSlippageModel,
    PaperTrader,
)

# --- Helpers ---

PORTFOLIO_VALUE_CENTS = 100_000_00  # $100k


def _make_market(
    ticker: str = "KX-TEST",
    question: str = "Test market?",
    status: str = "open",
    volume: int = 5000,
    open_interest: int = 2000,
    settlement_result: bool | None = None,
    close_time: datetime | None = None,
    category: str = "test",
) -> Market:
    return Market(
        ticker=ticker,
        question=question,
        outcome_prices=["0.65", "0.35"],
        volume=volume,
        open_interest=open_interest,
        close_time=close_time or datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        status=status,
        event_ticker="KX-EVENT",
        category=category,
        settlement_result=settlement_result,
    )


def _make_orderbook(
    yes_bids: list[tuple[int, int]] | None = None,
    no_bids: list[tuple[int, int]] | None = None,
) -> OrderBook:
    if yes_bids is None:
        yes_bids = [(65, 100), (64, 200), (63, 300)]
    if no_bids is None:
        no_bids = [(35, 150), (36, 200), (37, 300)]
    return OrderBook(
        yes_bids=[OrderBookLevel(price=p, size=s) for p, s in yes_bids],
        no_bids=[OrderBookLevel(price=p, size=s) for p, s in no_bids],
    )


def _in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _make_demo_adapter() -> DemoAdapter:
    """Create a DemoAdapter with default demo config (no real keys)."""
    from pydantic import SecretStr

    from traderbot.kalshi.client import KalshiConfig
    config = KalshiConfig(
        api_key=SecretStr("demo"),
        private_key_pem=SecretStr("demo"),
        demo_mode=True,
    )
    return DemoAdapter(config)


# --- Pydantic Model Tests ---

class TestPaperFill:
    def test_creation(self) -> None:
        fill = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=3,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        assert fill.ticker == "KX-TEST"
        assert fill.side == "yes"
        assert fill.price_cents == 60
        assert fill.quantity == 10
        assert fill.slippage_cents == 3

    def test_rejects_extra_fields(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PaperFill(
                ticker="KX-TEST",
                side="yes",
                price_cents=60,
                quantity=10,
                slippage_cents=3,
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                extra="bad",
            )

    def test_rejects_float_price(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PaperFill(
                ticker="KX-TEST",
                side="yes",
                price_cents=60.5,  # type: ignore[arg-type]
                quantity=10,
                slippage_cents=3,
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
            )


class TestPaperPosition:
    def test_creation(self) -> None:
        pos = PaperPosition(
            ticker="KX-TEST",
            side="yes",
            avg_price_cents=60,
            quantity=10,
        )
        assert pos.ticker == "KX-TEST"
        assert pos.side == "yes"
        assert pos.avg_price_cents == 60
        assert pos.quantity == 10

    def test_rejects_extra_fields(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PaperPosition(
                ticker="KX-TEST",
                side="yes",
                avg_price_cents=60,
                quantity=10,
                extra="bad",
            )


class TestPaperPortfolio:
    def test_creation(self) -> None:
        portfolio = PaperPortfolio(
            cash_cents=PORTFOLIO_VALUE_CENTS,
            positions=[],
        )
        assert portfolio.cash_cents == PORTFOLIO_VALUE_CENTS
        assert portfolio.positions == []

    def test_rejects_extra_fields(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PaperPortfolio(
                cash_cents=PORTFOLIO_VALUE_CENTS,
                positions=[],
                extra="bad",
            )


# --- SlippageModel Tests ---

class TestPaperSlippageModel:
    def test_realistic_slippage_yes(self) -> None:
        """Slippage model should add realistic slippage based on orderbook depth."""
        model = PaperSlippageModel(base_slippage_cents=1)
        book = _make_orderbook(yes_bids=[(65, 100), (64, 200)], no_bids=[(35, 150)])
        fill_price = model.compute_fill_price(
            orderbook=book,
            side="yes",
            quantity=50,  # within depth of best level
        )
        # For YES buy at 65 with 1 cent base slippage
        assert fill_price == 66

    def test_realistic_slippage_no(self) -> None:
        model = PaperSlippageModel(base_slippage_cents=1)
        book = _make_orderbook(yes_bids=[(65, 100)], no_bids=[(35, 150), (36, 200)])
        fill_price = model.compute_fill_price(
            orderbook=book,
            side="no",
            quantity=50,
        )
        # For NO buy at 35 with 1 cent base slippage
        assert fill_price == 36

    def test_depth_exceeds_best_level_yes(self) -> None:
        """When quantity exceeds best level, slippage should walk the book."""
        model = PaperSlippageModel(base_slippage_cents=1)
        book = _make_orderbook(
            yes_bids=[(65, 10), (64, 20), (63, 100)],
            no_bids=[(35, 150)],
        )
        # Buying 30 YES contracts: 10 at 65, 20 at 64 → avg is weighted
        fill_price = model.compute_fill_price(
            orderbook=book,
            side="yes",
            quantity=30,
        )
        # Weighted avg: (10*65 + 20*64) / 30 = (650+1280)/30 = 64.33 → 64
        # Plus 1 cent slippage = 65
        # Actually integer arithmetic: (650+1280)//30 = 64 + 1 = 65
        assert fill_price == 65

    def test_empty_orderbook_uses_midpoint(self) -> None:
        """Empty orderbook should fall back to midpoint (50 cents)."""
        model = PaperSlippageModel(base_slippage_cents=0)
        book = OrderBook(yes_bids=[], no_bids=[])
        fill_price = model.compute_fill_price(
            orderbook=book,
            side="yes",
            quantity=10,
        )
        assert fill_price == 50

    def test_default_base_slippage(self) -> None:
        model = PaperSlippageModel()
        assert model.base_slippage_cents == 1


# --- PaperTrader Tests ---

class TestPaperTrader:
    def _make_trader(
        self,
        conn: sqlite3.Connection | None = None,
        demo: DemoAdapter | None = None,
    ) -> PaperTrader:
        if conn is None:
            conn = _in_memory_db()
        if demo is None:
            demo = _make_demo_adapter()
        return PaperTrader(
            demo_adapter=demo,
            db_conn=conn,
            initial_cash_cents=PORTFOLIO_VALUE_CENTS,
        )

    # --- Init Tests ---

    def test_init_creates_tables(self) -> None:
        """Initializing PaperTrader should create paper_positions and log to decisions."""
        conn = _in_memory_db()
        self._make_trader(conn=conn)
        conn.execute("SELECT 1 FROM paper_positions LIMIT 1")
        conn.commit()

    def test_init_sets_initial_cash(self) -> None:
        trader = self._make_trader()
        portfolio = trader.get_portfolio()
        assert portfolio.cash_cents == PORTFOLIO_VALUE_CENTS
        assert portfolio.positions == []

    def test_composes_with_demo_adapter(self) -> None:
        """PaperTrader must compose with DemoAdapter, not duplicate it."""
        demo = _make_demo_adapter()
        trader = self._make_trader(demo=demo)
        assert trader.demo_adapter is demo
        assert trader.is_demo is True

    # --- Position Tracking Tests ---

    def test_open_position_creates_paper_position(self) -> None:
        """Opening a position should create a PaperPosition and deduct cash."""
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn)
        fill = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].ticker == "KX-TEST"
        assert positions[0].side == "yes"
        assert positions[0].avg_price_cents == 60
        assert positions[0].quantity == 10

        portfolio = trader.get_portfolio()
        # Cash deducted: price * quantity = 60 * 10 = 600 cents
        assert portfolio.cash_cents == PORTFOLIO_VALUE_CENTS - 600

    def test_add_to_existing_position_updates_avg_price(self) -> None:
        """Adding to an existing position should update avg price with weighted average."""
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn)

        fill1 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill1)

        fill2 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=70,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill2)

        positions = trader.get_positions()
        assert len(positions) == 1
        # Weighted avg: (60*10 + 70*10) / 20 = 65
        assert positions[0].avg_price_cents == 65
        assert positions[0].quantity == 20

    def test_close_position_adds_cash_back(self) -> None:
        """Closing a position should add proceeds back to cash."""
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn)

        fill1 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill1)

        # Simulate a close/sell: same ticker, same side
        fill2 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=80,
            quantity=-10,  # negative = close
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill2)

        # Position should be closed
        positions = trader.get_positions()
        assert len(positions) == 0

        # P&L: bought 10 at 60 = 600 cost, sold 10 at 80 = 800 proceeds
        # Cash = 10000000 - 600 + 800 = 10000200
        portfolio = trader.get_portfolio()
        assert portfolio.cash_cents == PORTFOLIO_VALUE_CENTS - 600 + 800

    def test_separate_from_live_positions(self) -> None:
        """Paper positions go into paper_positions table, not live positions table."""
        conn = _in_memory_db()
        # Also init the live positions table
        from traderbot.db.positions import init_table as init_live_positions
        init_live_positions(conn)

        trader = self._make_trader(conn=conn)
        fill = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        # Live positions table should be empty
        live_rows = conn.execute("SELECT COUNT(*) as cnt FROM positions").fetchone()
        assert live_rows["cnt"] == 0

        # Paper positions table should have the row
        paper_rows = conn.execute("SELECT COUNT(*) as cnt FROM paper_positions").fetchone()
        assert paper_rows["cnt"] == 1

    # --- P&L Tests ---

    def test_pnl_no_positions_is_zero(self) -> None:
        trader = self._make_trader()
        pnl = trader.get_pnl()
        assert pnl == 0

    def test_pnl_open_position_uses_mark_price(self) -> None:
        """Unrealized P&L for open positions should use current market price."""
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn)

        fill = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        # Mark price: YES at 80 → unrealized P&L = (80-60)*10 = 200
        pnl = trader.get_pnl(mark_prices={"KX-TEST": 80})
        assert pnl == 200

    def test_pnl_closed_position_uses_realized(self) -> None:
        """Realized P&L should be computed from closed positions."""
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn)

        fill1 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill1)

        fill2 = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=80,
            quantity=-10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill2)

        # Realized P&L = 200 (buy at 60, sell at 80, 10 contracts)
        pnl = trader.get_pnl()
        assert pnl == 200

    # --- Decision Logging Tests ---

    def test_decision_logged_with_paper_trade_marker(self) -> None:
        """Decisions should be logged to the decisions table with paper_trade marker."""
        conn = _in_memory_db()
        from traderbot.db.decisions import init_table as init_decisions
        init_decisions(conn)

        trader = self._make_trader(conn=conn)
        fill = PaperFill(
            ticker="KX-TEST",
            side="yes",
            price_cents=60,
            quantity=10,
            slippage_cents=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        # Check decisions table has a row with paper_trade marker
        rows = conn.execute(
            "SELECT * FROM decisions WHERE risk_checks LIKE '%paper_trade%'"
        ).fetchall()
        assert len(rows) >= 1

    # --- Graceful Degradation Tests ---

    async def test_demo_adapter_failure_doesnt_crash(self) -> None:
        """If DemoAdapter throws, PaperTrader logs error, holds position, doesn't crash."""
        demo = _make_demo_adapter()
        # Make the market service throw
        failing_service = AsyncMock()
        failing_service.get_market = AsyncMock(side_effect=Exception("demo API down"))
        failing_service.get_orderbook = AsyncMock(side_effect=Exception("demo API down"))

        with patch.object(demo, "get_market_service", return_value=failing_service):
            conn = _in_memory_db()
            trader = self._make_trader(conn=conn, demo=demo)
            # Should NOT raise
            result = await trader.submit_order(
                ticker="KX-TEST",
                side="yes",
                quantity=10,
                price_cents=65,
            )
            # Should return None indicating failure but no crash
            assert result is None

    async def test_demo_adapter_orderbook_failure_graceful(self) -> None:
        """Orderbook fetch failure should log error, not crash."""
        demo = _make_demo_adapter()
        market_service = AsyncMock()
        market_service.get_market = AsyncMock(return_value=_make_market())
        market_service.get_orderbook = AsyncMock(side_effect=Exception("orderbook error"))

        with patch.object(demo, "get_market_service", return_value=market_service):
            conn = _in_memory_db()
            trader = self._make_trader(conn=conn, demo=demo)
            result = await trader.submit_order(
                ticker="KX-TEST",
                side="yes",
                quantity=10,
                price_cents=65,
            )
            assert result is None

    # --- Portfolio Summary Tests ---

    def test_get_portfolio_initial(self) -> None:
        trader = self._make_trader()
        portfolio = trader.get_portfolio()
        assert portfolio.cash_cents == PORTFOLIO_VALUE_CENTS
        assert portfolio.positions == []

    def test_get_positions_empty(self) -> None:
        trader = self._make_trader()
        assert trader.get_positions() == []

    # --- Submit Order Integration ---

    async def test_submit_order_success(self) -> None:
        """Successful order submission should create a fill and update position."""
        demo = _make_demo_adapter()
        market_service = AsyncMock()
        market_service.get_market = AsyncMock(return_value=_make_market())
        market_service.get_orderbook = AsyncMock(return_value=_make_orderbook())

        with patch.object(demo, "get_market_service", return_value=market_service):
            conn = _in_memory_db()
            from traderbot.db.decisions import init_table as init_decisions
            init_decisions(conn)
            trader = self._make_trader(conn=conn, demo=demo)

            fill = await trader.submit_order(
                ticker="KX-TEST",
                side="yes",
                quantity=10,
                price_cents=65,
            )
            assert fill is not None
            assert fill.ticker == "KX-TEST"
            assert fill.side == "yes"
            assert fill.quantity == 10

            positions = trader.get_positions()
            assert len(positions) == 1
            assert positions[0].ticker == "KX-TEST"

    async def test_submit_order_zero_quantity_rejected(self) -> None:
        """Zero or negative quantity should be rejected."""
        demo = _make_demo_adapter()
        conn = _in_memory_db()
        trader = self._make_trader(conn=conn, demo=demo)
        result = await trader.submit_order(
            ticker="KX-TEST",
            side="yes",
            quantity=0,
            price_cents=65,
        )
        assert result is None

    async def test_submit_order_insufficient_cash(self) -> None:
        """Order exceeding available cash should be partially filled or rejected."""
        demo = _make_demo_adapter()
        market_service = AsyncMock()
        market_service.get_market = AsyncMock(return_value=_make_market())
        market_service.get_orderbook = AsyncMock(return_value=_make_orderbook())

        with patch.object(demo, "get_market_service", return_value=market_service):
            conn = _in_memory_db()
            trader = PaperTrader(
                demo_adapter=demo,
                db_conn=conn,
                initial_cash_cents=100,  # very little cash
            )
            fill = await trader.submit_order(
                ticker="KX-TEST",
                side="yes",
                quantity=10,
                price_cents=65,
            )
            # Either None (rejected) or partial fill
            if fill is not None:
                assert fill.quantity < 10
            else:
                assert fill is None

    # --- is_demo Property ---

    def test_is_demo_always_true(self) -> None:
        trader = self._make_trader()
        assert trader.is_demo is True
