"""BacktestEngine — event-driven backtester for binary outcome prediction markets."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import Market, PortfolioState, Trade, TradeRequest
from traderbot.paths import get_data_dir
from traderbot.risk import evaluate_trade
from traderbot.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState

if TYPE_CHECKING:
    from pathlib import Path

    from traderbot.profiles.models import TradingProfile
    from traderbot.simulation.data_loader import DataLoader
    from traderbot.simulation.profiles import StrategyProfile


@dataclass(frozen=True)
class Context:
    portfolio: PortfolioState
    market: Market
    recent_trades: list[Trade]
    sentiment_score: float | None
    breaker_state: CircuitBreakerState


class Signal(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    direction: str
    quantity: int = Field(ge=1)
    price_cents: int = Field(ge=1)
    estimated_prob: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class SlippageModel:
    def apply(self, yes_bid: int, no_bid: int, direction: str, quantity: int) -> int:
        if direction == "yes":
            return 100 - no_bid
        return 100 - yes_bid


@runtime_checkable
class Strategy(Protocol):
    def on_market_open(self, market: Market, context: Context) -> list[Signal]: ...
    def on_trade(self, trade: Trade, context: Context) -> list[Signal]: ...
    def on_settle(self, market: Market, outcome: bool, context: Context) -> None: ...


class BacktestTrade(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    direction: str
    entry_price_cents: int = Field(ge=0)
    exit_price_cents: int = Field(ge=0)
    quantity: int = Field(ge=1)
    pnl_cents: int
    timestamp: str


class BacktestResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    trade_count: int = Field(ge=0)
    total_pnl_cents: int
    winning_trades: int = Field(ge=0)
    losing_trades: int = Field(ge=0)
    win_rate: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    brier_score: float | None
    edge_capture: float | None
    fill_rate: float | None
    trades: list[BacktestTrade] = Field(default_factory=list)


class BacktestEngine:
    def __init__(
        self,
        data_loader: DataLoader,
        strategy: Strategy,
        initial_bankroll_cents: int = 100_000_00,
        slippage_model: SlippageModel | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self._data_loader = data_loader
        self._strategy = strategy
        self._initial_bankroll_cents = initial_bankroll_cents
        self._slippage = slippage_model or SlippageModel()
        self._state_dir = state_dir or get_data_dir()
        self._profile: TradingProfile | None = None

    async def run(
        self,
        start: date,
        end: date,
        profile: TradingProfile | None = None,
    ) -> BacktestResult:
        self._profile = profile
        markets = await self._data_loader.get_markets(start, end)

        trades_by_ticker: dict[str, list[Trade]] = {}
        for market in markets:
            ticker_trades = await self._data_loader.get_trades(market.ticker)
            trades_by_ticker[market.ticker] = ticker_trades

        outcomes = await self._data_loader.get_outcomes([m.ticker for m in markets])

        events = self._build_event_stream(markets, trades_by_ticker, outcomes)

        breaker = CircuitBreaker(state_file=self._state_dir / "cb_backtest.json")
        breaker.check(daily_loss_pct=0.0, drawdown_pct=0.0)

        positions: dict[str, _Position] = {}
        closed_trades: list[BacktestTrade] = []
        portfolio_value_cents = self._initial_bankroll_cents
        peak_value_cents = self._initial_bankroll_cents
        daily_loss_cents = 0
        market_events_processed: set[str] = set()

        for event in events:
            if event["type"] == "market_open":
                market = event["market"]
                market_events_processed.add(market.ticker)

                portfolio = self._build_portfolio(
                    portfolio_value_cents, peak_value_cents, positions, daily_loss_cents
                )
                recent = trades_by_ticker.get(market.ticker, [])
                context = Context(
                    portfolio=portfolio,
                    market=market,
                    recent_trades=recent,
                    sentiment_score=None,
                    breaker_state=breaker.get_state(),
                )

                signals = self._strategy.on_market_open(market, context)
                self._process_signals(signals, market, positions, portfolio_value_cents, breaker, context)

            elif event["type"] == "trade":
                trade = event["trade"]
                ticker = trade.ticker
                matching_market = self._find_market(ticker, markets)
                if matching_market is None:
                    continue

                portfolio = self._build_portfolio(
                    portfolio_value_cents, peak_value_cents, positions, daily_loss_cents
                )
                recent = trades_by_ticker.get(ticker, [])
                context = Context(
                    portfolio=portfolio,
                    market=matching_market,
                    recent_trades=recent,
                    sentiment_score=None,
                    breaker_state=breaker.get_state(),
                )

                signals = self._strategy.on_trade(trade, context)
                self._process_signals(signals, matching_market, positions, portfolio_value_cents, breaker, context)

            elif event["type"] == "settle":
                market = event["market"]
                outcome = event["outcome"]

                open_pos = positions.pop(market.ticker, None)
                if open_pos is not None:
                    exit_price = 100 if outcome else 0
                    pnl = open_pos.compute_pnl(exit_price)

                    closed_trades.append(BacktestTrade(
                        ticker=market.ticker,
                        direction=open_pos.direction,
                        entry_price_cents=open_pos.entry_price_cents,
                        exit_price_cents=exit_price,
                        quantity=open_pos.quantity,
                        pnl_cents=pnl,
                        timestamp=market.close_time.isoformat(),
                    ))

                    portfolio_value_cents += pnl
                    if pnl < 0:
                        daily_loss_cents += abs(pnl)
                    if portfolio_value_cents > peak_value_cents:
                        peak_value_cents = portfolio_value_cents

                breaker_state = breaker.get_state()
                portfolio = self._build_portfolio(
                    portfolio_value_cents, peak_value_cents, positions, daily_loss_cents
                )
                settle_context = Context(
                    portfolio=portfolio,
                    market=market,
                    recent_trades=trades_by_ticker.get(market.ticker, []),
                    sentiment_score=None,
                    breaker_state=breaker_state,
                )
                self._strategy.on_settle(market, outcome, settle_context)

        return self._compute_result(closed_trades, positions, portfolio_value_cents)

    async def run_profiles(
        self,
        profiles: list[StrategyProfile],
        start: date,
        end: date,
    ) -> dict[str, BacktestResult]:
        """Run multiple profiles on the same historical data for comparison.

        Each profile gets isolated position tracking and its own Context.
        HARD_LIMITS remain immutable — profiles only scale within them.
        """
        results: dict[str, BacktestResult] = {}
        for profile in profiles:
            profile_engine = BacktestEngine(
                data_loader=self._data_loader,
                strategy=self._strategy,
                initial_bankroll_cents=self._initial_bankroll_cents,
                slippage_model=self._slippage,
                state_dir=self._state_dir,
            )
            result = await profile_engine.run(start, end)
            results[profile.name] = result
        return results

    def _build_event_stream(
        self,
        markets: list[Market],
        trades_by_ticker: dict[str, list[Trade]],
        outcomes: dict[str, bool],
    ) -> list[dict]:
        events: list[dict] = []

        for market in markets:
            events.append({
                "type": "market_open",
                "timestamp": market.close_time,
                "market": market,
            })

            for trade in trades_by_ticker.get(market.ticker, []):
                events.append({
                    "type": "trade",
                    "timestamp": trade.timestamp,
                    "trade": trade,
                })

            if market.ticker in outcomes:
                events.append({
                    "type": "settle",
                    "timestamp": market.close_time,
                    "market": market,
                    "outcome": outcomes[market.ticker],
                })

        events.sort(key=lambda e: e["timestamp"])
        return events

    def _find_market(self, ticker: str, markets: list[Market]) -> Market | None:
        for m in markets:
            if m.ticker == ticker:
                return m
        return None

    def _build_portfolio(
        self,
        portfolio_value_cents: int,
        peak_value_cents: int,
        positions: dict[str, _Position],
        daily_loss_cents: int,
    ) -> PortfolioState:
        positions_value = sum(p.entry_price_cents * p.quantity for p in positions.values())
        position_count = len(positions)

        return PortfolioState(
            portfolio_value_cents=max(1, portfolio_value_cents),
            peak_value_cents=max(1, peak_value_cents),
            current_positions_value_cents=positions_value,
            today_realized_loss_cents=daily_loss_cents,
            today_unrealized_loss_cents=0,
            open_positions_count=position_count,
        )

    def _process_signals(
        self,
        signals: list[Signal],
        market: Market,
        positions: dict[str, _Position],
        portfolio_value_cents: int,
        breaker: CircuitBreaker,
        context: Context,
    ) -> None:
        for signal in signals:
            if signal.ticker in positions:
                continue

            yes_bid = market.outcome_prices[0] if len(market.outcome_prices) > 0 else "50"
            try:
                bid_pct = int(float(yes_bid) * 100)
            except (ValueError, IndexError):
                bid_pct = 50
            no_bid = 100 - bid_pct

            fill_price = self._slippage.apply(
                yes_bid=bid_pct,
                no_bid=no_bid,
                direction=signal.direction,
                quantity=signal.quantity,
            )

            trade_request = TradeRequest(
                ticker=signal.ticker,
                direction=signal.direction,
                quantity=signal.quantity,
                price_cents=fill_price,
                estimated_prob=signal.estimated_prob,
                confidence=signal.confidence,
                edge_estimate=abs(signal.estimated_prob - (fill_price / 100.0)),
                market_price_cents=fill_price,
                market_open_interest=market.open_interest,
            )

            sized = evaluate_trade(trade_request, context.portfolio, breaker, profile=self._profile)

            if sized > 0:
                actual_quantity = min(signal.quantity, sized // max(fill_price, 1))
                if actual_quantity > 0:
                    positions[signal.ticker] = _Position(
                        ticker=signal.ticker,
                        direction=signal.direction,
                        entry_price_cents=fill_price,
                        quantity=actual_quantity,
                        estimated_prob=signal.estimated_prob,
                    )

    def _compute_result(
        self,
        closed_trades: list[BacktestTrade],
        open_positions: dict[str, _Position],
        final_value: int,
    ) -> BacktestResult:
        trade_count = len(closed_trades)

        if trade_count == 0:
            return BacktestResult(
                trade_count=0,
                total_pnl_cents=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=None,
                sharpe_ratio=None,
                max_drawdown_pct=None,
                brier_score=None,
                edge_capture=None,
                fill_rate=None,
                trades=[],
            )

        total_pnl = sum(t.pnl_cents for t in closed_trades)
        winning = sum(1 for t in closed_trades if t.pnl_cents > 0)
        losing = sum(1 for t in closed_trades if t.pnl_cents <= 0)
        win_rate = winning / trade_count

        pnls = [t.pnl_cents for t in closed_trades]
        mean_pnl = sum(pnls) / len(pnls)
        std_pnl = (sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)) ** 0.5 if len(pnls) > 1 else 1.0
        sharpe = (mean_pnl / std_pnl) * math.sqrt(252) if std_pnl > 0 else 0.0

        cumulative = self._initial_bankroll_cents
        peak = cumulative
        max_dd = 0.0
        for t in closed_trades:
            cumulative += t.pnl_cents
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        brier_score = None
        if closed_trades:
            sq_diffs = []
            for t in closed_trades:
                pred = t.entry_price_cents / 100.0 if t.direction == "yes" else 1.0 - t.entry_price_cents / 100.0
                actual = 1.0 if t.pnl_cents > 0 else 0.0
                sq_diffs.append((pred - actual) ** 2)
            brier_score = sum(sq_diffs) / len(sq_diffs)

        return BacktestResult(
            trade_count=trade_count,
            total_pnl_cents=total_pnl,
            winning_trades=winning,
            losing_trades=losing,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            brier_score=brier_score,
            edge_capture=None,
            fill_rate=None,
            trades=closed_trades,
        )


class _Position:
    def __init__(
        self,
        ticker: str,
        direction: str,
        entry_price_cents: int,
        quantity: int,
        estimated_prob: float,
    ) -> None:
        self.ticker = ticker
        self.direction = direction
        self.entry_price_cents = entry_price_cents
        self.quantity = quantity
        self.estimated_prob = estimated_prob

    def compute_pnl(self, exit_price_cents: int) -> int:
        if self.direction == "yes":
            return (exit_price_cents - self.entry_price_cents) * self.quantity
        return (self.entry_price_cents - exit_price_cents) * self.quantity
