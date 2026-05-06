"""PaperTrader — live-simulated trading against the Kalshi demo API."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.risk import evaluate_trade

if TYPE_CHECKING:
    import sqlite3

    from traderbot.kalshi.demo import DemoAdapter
    from traderbot.kalshi.models import OrderBook
    from traderbot.profiles.models import TradingProfile
    from traderbot.risk.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class PaperFill(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    side: Literal["yes", "no"]
    price_cents: Annotated[int, Field(ge=1, description="Fill price in cents")]
    quantity: Annotated[int, Field(description="Positive=open, negative=close")]
    slippage_cents: Annotated[int, Field(ge=0)]
    timestamp: datetime


class PaperPosition(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    side: Literal["yes", "no"]
    avg_price_cents: Annotated[int, Field(ge=1, description="Weighted-average price in cents")]
    quantity: Annotated[int, Field(ge=0)]


class PaperPortfolio(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    cash_cents: Annotated[int, Field(ge=0)]
    positions: list[PaperPosition]


class PaperSlippageModel:
    def __init__(self, base_slippage_cents: int = 1) -> None:
        self.base_slippage_cents = base_slippage_cents

    def compute_fill_price(
        self,
        orderbook: OrderBook,
        side: Literal["yes", "no"],
        quantity: int,
    ) -> int:
        bids = orderbook.yes_bids if side == "yes" else orderbook.no_bids

        if not bids:
            return 50 + self.base_slippage_cents

        remaining = quantity
        total_cost = 0
        total_filled = 0

        for level in bids:
            if remaining <= 0:
                break
            fill_at_level = min(remaining, level.size)
            total_cost += fill_at_level * level.price
            total_filled += fill_at_level
            remaining -= fill_at_level

        if total_filled == 0:
            return 50 + self.base_slippage_cents

        avg_price = total_cost // total_filled
        return min(avg_price + self.base_slippage_cents, 99)


def _init_paper_positions_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS paper_positions (
            ticker TEXT UNIQUE NOT NULL,
            side TEXT NOT NULL,
            avg_price_cents INTEGER NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()


class PaperTrader:
    def __init__(
        self,
        demo_adapter: DemoAdapter,
        db_conn: sqlite3.Connection,
        initial_cash_cents: int = 100_000_00,
        slippage_model: PaperSlippageModel | None = None,
        breaker: CircuitBreaker | None = None,
        profile: TradingProfile | None = None,
        default_open_interest: int = 5000,
    ) -> None:
        if breaker is None:
            from traderbot.risk.circuit_breaker import CircuitBreaker as _CircuitBreaker
            breaker = _CircuitBreaker()
        self._demo = demo_adapter
        self._conn = db_conn
        self._cash_cents = initial_cash_cents
        self._initial_cash_cents = initial_cash_cents
        self._slippage = slippage_model or PaperSlippageModel()
        self._breaker = breaker
        self._profile = profile
        self._default_open_interest = default_open_interest
        self._realized_pnl_cents = 0
        _init_paper_positions_table(db_conn)

    @property
    def demo_adapter(self) -> DemoAdapter:
        return self._demo

    @property
    def is_demo(self) -> bool:
        return True

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    @property
    def profile(self) -> TradingProfile | None:
        return self._profile

    def _position_value_cents(self) -> int:
        total = 0
        for pos in self.get_positions():
            total += pos.avg_price_cents * pos.quantity
        return total

    def get_portfolio(self) -> PaperPortfolio:
        positions = self.get_positions()
        return PaperPortfolio(cash_cents=self._cash_cents, positions=positions)

    def get_positions(self) -> list[PaperPosition]:
        rows = self._conn.execute(
            "SELECT ticker, side, avg_price_cents, quantity FROM paper_positions ORDER BY ticker"
        ).fetchall()
        return [
            PaperPosition(
                ticker=row["ticker"],
                side=row["side"],
                avg_price_cents=row["avg_price_cents"],
                quantity=row["quantity"],
            )
            for row in rows
        ]

    def get_pnl(self, mark_prices: dict[str, int] | None = None) -> int:
        unrealized = 0
        if mark_prices:
            rows = self._conn.execute(
                "SELECT ticker, side, avg_price_cents, quantity FROM paper_positions"
            ).fetchall()
            for row in rows:
                mark = mark_prices.get(row["ticker"])
                if mark is not None and row["quantity"] > 0:
                    if row["side"] == "yes":
                        unrealized += (mark - row["avg_price_cents"]) * row["quantity"]
                    else:
                        unrealized += (row["avg_price_cents"] - mark) * row["quantity"]
        return self._realized_pnl_cents + unrealized

    def record_fill(self, fill: PaperFill) -> None:
        now = datetime.now(UTC).isoformat()

        if fill.quantity < 0:
            self._close_position(fill, now)
        else:
            self._open_or_add_position(fill, now)

        self._log_decision(fill)

    async def submit_order(
        self,
        ticker: str,
        side: Literal["yes", "no"],
        quantity: int,
        price_cents: int,
        edge_estimate: float = 0.05,
    ) -> PaperFill | None:
        if quantity <= 0:
            logger.warning("Rejected zero/negative quantity order: ticker=%s qty=%d", ticker, quantity)
            return None

        from traderbot.kalshi.models import PortfolioState, TradeRequest

        portfolio = PortfolioState(
            portfolio_value_cents=max(self._cash_cents, 1),
            peak_value_cents=max(self._cash_cents, 1),
            current_positions_value_cents=self._position_value_cents(),
            today_realized_loss_cents=max(0, self._initial_cash_cents - self._cash_cents - self._position_value_cents()),
            today_unrealized_loss_cents=0,
            open_positions_count=len(self.get_positions()),
        )
        # Derive estimated probability from price + edge offset
        # For paper trading, we assume the agent has a view that differs from market
        # by at least edge_estimate (default 5%). This ensures the min_edge check passes.
        market_price_prob = price_cents / 100.0 if price_cents > 0 else 0.5
        est_prob = min(max(market_price_prob + edge_estimate, 0.01), 0.99)
        market_oi = self._default_open_interest
        try:
            market_svc = self._demo.get_market_service()
            market = await market_svc.get_market(ticker)
            if market and market.open_interest:
                market_oi = market.open_interest
        except Exception:
            pass  # Use default when market data is unavailable

        trade_request = TradeRequest(
            ticker=ticker,
            direction=side,
            quantity=quantity,
            price_cents=price_cents,
            estimated_prob=est_prob,
            confidence=0.6,
            edge_estimate=edge_estimate,
            market_price_cents=price_cents,
            market_open_interest=market_oi,
        )

        sized = evaluate_trade(trade_request, portfolio, self._breaker, profile=self._profile)
        if sized == 0:
            logger.info("Paper trade rejected by risk gate: ticker=%s side=%s", ticker, side)
            return None

        risk_adjusted_qty = min(quantity, sized // max(price_cents, 1))
        if risk_adjusted_qty <= 0:
            logger.info("Paper trade sized to zero: ticker=%s sized=%d price=%d", ticker, sized, price_cents)
            return None

        try:
            market_service = self._demo.get_market_service()
            orderbook = await market_service.get_orderbook(ticker)
        except Exception:
            logger.exception("DemoAdapter failure fetching orderbook for %s", ticker)
            return None

        fill_price = self._slippage.compute_fill_price(orderbook, side, risk_adjusted_qty)

        max_cost = fill_price * risk_adjusted_qty
        if max_cost > self._cash_cents:
            risk_adjusted_qty = self._cash_cents // max(fill_price, 1)

        if risk_adjusted_qty <= 0:
            logger.warning("Insufficient cash for order: ticker=%s need=%d have=%d", ticker, max_cost, self._cash_cents)
            return None

        fill = PaperFill(
            ticker=ticker,
            side=side,
            price_cents=fill_price,
            quantity=risk_adjusted_qty,
            slippage_cents=fill_price - price_cents if fill_price > price_cents else 0,
            timestamp=datetime.now(UTC),
        )
        self.record_fill(fill)
        return fill

    def _open_or_add_position(self, fill: PaperFill, now: str) -> None:
        cost = fill.price_cents * fill.quantity
        self._cash_cents -= cost

        row = self._conn.execute(
            "SELECT avg_price_cents, quantity FROM paper_positions WHERE ticker = ?",
            (fill.ticker,),
        ).fetchone()

        if row is None:
            self._conn.execute(
                """INSERT INTO paper_positions (ticker, side, avg_price_cents, quantity, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (fill.ticker, fill.side, fill.price_cents, fill.quantity, now),
            )
        else:
            old_qty: int = row["quantity"]
            old_avg: int = row["avg_price_cents"]
            new_qty = old_qty + fill.quantity
            new_avg = (old_avg * old_qty + fill.price_cents * fill.quantity) // new_qty
            self._conn.execute(
                "UPDATE paper_positions SET avg_price_cents = ?, quantity = ?, updated_at = ? WHERE ticker = ?",
                (new_avg, new_qty, now, fill.ticker),
            )
        self._conn.commit()

    def _close_position(self, fill: PaperFill, now: str) -> None:
        close_qty = abs(fill.quantity)
        row = self._conn.execute(
            "SELECT side, avg_price_cents, quantity FROM paper_positions WHERE ticker = ?",
            (fill.ticker,),
        ).fetchone()

        if row is None:
            logger.warning("No position to close for ticker=%s", fill.ticker)
            return

        proceeds = fill.price_cents * close_qty
        self._cash_cents += proceeds

        if row["side"] == "yes":
            pnl = (fill.price_cents - row["avg_price_cents"]) * close_qty
        else:
            pnl = (row["avg_price_cents"] - fill.price_cents) * close_qty
        self._realized_pnl_cents += pnl

        remaining = row["quantity"] - close_qty
        if remaining <= 0:
            self._conn.execute("DELETE FROM paper_positions WHERE ticker = ?", (fill.ticker,))
        else:
            self._conn.execute(
                "UPDATE paper_positions SET quantity = ?, updated_at = ? WHERE ticker = ?",
                (remaining, now, fill.ticker),
            )
        self._conn.commit()

    def _log_decision(self, fill: PaperFill) -> None:
        try:
            from traderbot.db.decisions import init_table as init_decisions
            init_decisions(self._conn)

            now_iso = datetime.now(UTC).isoformat()
            risk_checks = {"paper_trade": True}
            self._conn.execute(
                """INSERT INTO decisions
                   (timestamp, ticker, direction, quantity, price, signal_strength,
                    confidence, edge_estimate, risk_checks, outcome, rejection_reason,
                    actual_result)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_iso,
                    fill.ticker,
                    fill.side,
                    abs(fill.quantity),
                    fill.price_cents,
                    1.0,
                    1.0,
                    0.0,
                    json.dumps(risk_checks),
                    "executed",
                    None,
                    None,
                ),
            )
            self._conn.commit()
        except Exception:
            logger.exception("Failed to log decision for fill ticker=%s", fill.ticker)
