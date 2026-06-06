"""Unit tests for paper balance computation (bug #146)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from traderbot.db.positions import init_table
from traderbot.paper import PaperBalance, compute_paper_balance
from traderbot.profiles.models import TradingProfile


def _make_profile(initial_cents: int = 10_000) -> TradingProfile:
    """Create a minimal paper-trading profile for testing."""
    return TradingProfile(
        name="test-profile",
        mode="paper",
        description="Test profile for paper balance tests",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=10,
        min_liquidity_threshold=2000,
        min_edge_pct=0.05,
        initial_balance_cents=initial_cents,
    )


def _seed_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: int,
    avg_price: int,
    settlement_result: bool | None = None,
) -> None:
    """Insert a position row directly into SQLite."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO positions (ticker, quantity, avg_price, settlement_result, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, quantity, avg_price, settlement_result, now),
    )
    conn.commit()


def _db_path_in_memory() -> tuple[sqlite3.Connection, str]:
    """Create an in-memory DB with positions table; return (conn, ':memory:' path)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_table(conn)
    return conn, ":memory:"


class TestCostAtRiskClamping:
    """Bug #146: cost_at_risk_cents must never be negative."""

    def test_profitable_settlements_clamp_to_zero(self) -> None:
        """When total_payout > total_cost, cost_at_risk_cents should be 0, not negative."""
        conn, _ = _db_path_in_memory()
        # Buy 10 contracts at 50¢ each => total_cost = 500
        # They all win => total_payout = 100 * 10 = 1000
        # cost_at_risk = 500 - 1000 = -500 WITHOUT fix → should clamp to 0
        _seed_position(conn, "WIN-MKT-001", quantity=10, avg_price=50, settlement_result=True)

        # We need to patch list_all to use our in-memory connection
        # compute_paper_balance uses get_connection internally,
        # so we pass the db_path and monkey-patch
        from unittest.mock import patch

        profile = _make_profile(initial_cents=10_000)

        # Patch get_connection to return our in-memory connection
        with patch("traderbot.paper.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = lambda s: conn
            mock_conn.return_value.__exit__ = lambda s, *a: None

            result = compute_paper_balance(profile, db_path=None)

        assert result is not None
        assert result.cost_at_risk_cents == 0, (
            f"Expected cost_at_risk_cents=0, got {result.cost_at_risk_cents}"
        )
        assert result.remaining_cents == 10_000 - 500 + 1000  # 10_500
        assert result.settled_payout_cents == 1000

    def test_normal_case_cost_at_risk_positive(self) -> None:
        """When open positions exist, cost_at_risk_cents should reflect actual cost minus settled."""
        conn, _ = _db_path_in_memory()
        # Buy 5 contracts at 60¢ each => total_cost = 300
        # All open (not settled) => total_payout = 0
        # cost_at_risk = 300 - 0 = 300
        _seed_position(conn, "OPEN-MKT-001", quantity=5, avg_price=60, settlement_result=None)

        profile = _make_profile(initial_cents=10_000)

        from unittest.mock import patch

        with patch("traderbot.paper.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = lambda s: conn
            mock_conn.return_value.__exit__ = lambda s, *a: None

            result = compute_paper_balance(profile, db_path=None)

        assert result is not None
        assert result.cost_at_risk_cents == 300
        assert result.open_position_count == 1
        assert result.remaining_cents == 10_000 - 300  # 9_700

    def test_mixed_positions_partial_settlement(self) -> None:
        """Mix of open, won, and lost positions."""
        conn, _ = _db_path_in_memory()
        # Open: 3 contracts at 40¢ each => cost = 120, payout = 0
        _seed_position(conn, "OPEN-001", quantity=3, avg_price=40, settlement_result=None)
        # Won: 5 contracts at 50¢ each => cost = 250, payout = 500
        _seed_position(conn, "WON-001", quantity=5, avg_price=50, settlement_result=True)
        # Lost: 2 contracts at 70¢ each => cost = 140, payout = 0
        _seed_position(conn, "LOST-001", quantity=2, avg_price=70, settlement_result=False)
        # total_cost = 120 + 250 + 140 = 510
        # total_payout = 500
        # cost_at_risk = 510 - 500 = 10
        # remaining = 10000 - 510 + 500 = 9990

        profile = _make_profile(initial_cents=10_000)

        from unittest.mock import patch

        with patch("traderbot.paper.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = lambda s: conn
            mock_conn.return_value.__exit__ = lambda s, *a: None

            result = compute_paper_balance(profile, db_path=None)

        assert result is not None
        assert result.cost_at_risk_cents == 10
        assert result.remaining_cents == 9_990
        assert result.settled_payout_cents == 500
        assert result.open_position_count == 1


class TestPortfolioValueClamping:
    """portfolio_value_cents should never be negative."""

    def test_portfolio_value_clamps_to_zero(self) -> None:
        """When mark_to_market is deeply negative, portfolio_value_cents clamps to 0."""
        pb = PaperBalance(
            initial_cents=10_000,
            cost_at_risk_cents=500,
            settled_payout_cents=0,
            remaining_cents=9_500,
            open_position_count=5,
            effective_balance_cents=10_000,
            mark_to_market_cents=-20_000,  # Unrealized loss exceeding remaining
        )
        # 9_500 + (-20_000) = -10_500 → should clamp to 0
        assert pb.portfolio_value_cents == 0

    def test_portfolio_value_normal_case(self) -> None:
        """Normal positive case: remaining + mark_to_market."""
        pb = PaperBalance(
            initial_cents=10_000,
            cost_at_risk_cents=500,
            settled_payout_cents=0,
            remaining_cents=9_500,
            open_position_count=5,
            effective_balance_cents=10_000,
            mark_to_market_cents=300,
        )
        assert pb.portfolio_value_cents == 9_800

    def test_portfolio_value_zero_mark_to_market(self) -> None:
        """Default mark_to_market is 0, so portfolio_value == remaining."""
        pb = PaperBalance(
            initial_cents=10_000,
            cost_at_risk_cents=500,
            settled_payout_cents=0,
            remaining_cents=9_500,
            open_position_count=5,
            effective_balance_cents=10_000,
        )
        assert pb.portfolio_value_cents == 9_500
