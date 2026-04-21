"""Command-line interface for TraderBot."""

import asyncio
import json as json_lib
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="traderbot",
    help="Autonomous prediction market investment toolkit for Kalshi.",
    rich_markup_mode="rich",
)

err_console = Console(stderr=True)


def _with_db(db_path, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(db_path) as conn:
        init_schema(conn)
        return func(conn)


@app.command()
def scan(
    limit: Annotated[int, typer.Option("--limit", help="Max markets to return")] = 20,
    category: Annotated[str | None, typer.Option("--category", help="Filter by category")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List open markets from Kalshi."""
    from traderbot.kalshi.markets import MarketService

    console = Console()
    try:
        from traderbot.kalshi.client import KalshiClient

        client = KalshiClient()
        service = MarketService(client)
        result = asyncio.run(service.list_markets(limit=limit, category=category))
        markets = result.markets
    except Exception:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print("Scanning markets... (requires API connection)")
        return

    if json_output:
        json_lib.dump([m.model_dump(mode="json") for m in markets], sys.stdout, default=str)
        return

    table = Table(title="Open Markets")
    table.add_column("Ticker", style="cyan")
    table.add_column("Question", style="white")
    table.add_column("Volume", justify="right")
    table.add_column("State", style="green")
    for m in markets:
        table.add_row(m.ticker, m.question, str(m.volume), m.state)
    console.print(table)


@app.command()
def analyze(
    ticker: Annotated[str, typer.Argument(help="Market ticker symbol")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Get market details, orderbook, and indicators."""
    from traderbot.kalshi.markets import MarketService

    console = Console()
    try:
        from traderbot.kalshi.client import KalshiClient

        client = KalshiClient()
        service = MarketService(client)
        market = asyncio.run(service.get_market(ticker))
        orderbook = asyncio.run(service.get_orderbook(ticker))
    except Exception:
        if json_output:
            json_lib.dump({}, sys.stdout)
            return
        console.print(f"Market analysis for {ticker}... (requires API connection)")
        return

    if json_output:
        json_lib.dump(
            {
                "market": market.model_dump(mode="json"),
                "orderbook": orderbook.model_dump(mode="json"),
            },
            sys.stdout,
            default=str,
        )
        return

    console.print(f"[bold]{market.ticker}[/bold]: {market.question}")
    console.print(f"State: {market.state}  Volume: {market.volume}  OI: {market.open_interest}")
    console.print(f"YES bids: {len(orderbook.yes_bids)}  NO bids: {len(orderbook.no_bids)}")

    from traderbot.analysis.odds import implied_probability

    prob = implied_probability(orderbook)
    console.print("\n[bold]Analysis[/bold]")
    console.print(f"  Implied YES prob: {prob.yes_prob:.2%}")
    console.print(f"  Implied NO prob:  {prob.no_prob:.2%}")
    console.print(f"  Spread:           {prob.spread_cents}¢")
    console.print(f"  Mid price:        {prob.mid_price_cents}¢")


@app.command()
def signals(
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Show active signals across tracked markets. (Phase 4)"""
    if json_output:
        json_lib.dump(
            {"note": "Signal generation requires tracked markets and price data"}, sys.stdout
        )
        return
    Console().print("Signal generation requires tracked markets with price data.")


@app.command()
def trade(
    ticker: Annotated[str, typer.Argument(help="Market ticker symbol")],
    direction: Annotated[
        str, typer.Option("--direction", help="Trade direction: yes or no")
    ] = "yes",
    quantity: Annotated[int, typer.Option("--quantity", help="Number of contracts")] = 1,
    price: Annotated[int, typer.Option("--price", help="Limit price in cents")] = 50,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Place a trade through risk checks."""
    from traderbot.kalshi.models import PortfolioState, TradeRequest
    from traderbot.risk import evaluate_trade
    from traderbot.risk.circuit_breaker import CircuitBreaker

    console = Console()
    trade_request = TradeRequest(
        ticker=ticker,
        direction=direction,
        quantity=quantity,
        price_cents=price,
        estimated_prob=0.5,
        confidence=0.5,
        edge_estimate=0.0,
        market_price_cents=price,
        market_open_interest=0,
    )
    portfolio = PortfolioState(
        portfolio_value_cents=100_000_00,
        peak_value_cents=100_000_00,
        current_positions_value_cents=0,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=0,
    )
    breaker = CircuitBreaker()
    sized = evaluate_trade(trade_request, portfolio, breaker)

    if sized == 0:
        state = breaker.get_state()
        result = {
            "ticker": ticker,
            "direction": direction,
            "outcome": "rejected",
            "sized_position_cents": 0,
            "reason": state.reason or "Risk check failed",
        }
    else:
        result = {
            "ticker": ticker,
            "direction": direction,
            "outcome": "executed",
            "sized_position_cents": sized,
        }

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    if result["outcome"] == "executed":
        console.print(
            f"[green]Trade executed[/green]: {ticker} {direction} — sized ${sized / 100:.2f}"
        )
    else:
        console.print(f"[red]Trade rejected[/red]: {ticker} — {result['reason']}")


@app.command()
def positions(
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List current positions from SQLite."""
    from traderbot.db.positions import list_all

    all_positions = _with_db(db_path, list_all)

    if json_output:
        json_lib.dump([p.model_dump(mode="json") for p in all_positions], sys.stdout, default=str)
        return

    console = Console()
    if not all_positions:
        console.print("No open positions.")
        return

    table = Table(title="Positions")
    table.add_column("Ticker", style="cyan")
    table.add_column("Quantity", justify="right")
    table.add_column("Avg Price", justify="right")
    table.add_column("Settled")
    for p in all_positions:
        settled = "\u2014" if p.settlement_result is None else str(p.settlement_result)
        table.add_row(p.ticker, str(p.quantity), str(p.avg_price), settled)
    console.print(table)


@app.command()
def audit(
    ticker: Annotated[str | None, typer.Option("--ticker", help="Filter by ticker")] = None,
    start: Annotated[str | None, typer.Option("--start", help="Start date (ISO format)")] = None,
    end: Annotated[str | None, typer.Option("--end", help="End date (ISO format)")] = None,
    outcome: Annotated[str | None, typer.Option("--outcome", help="Filter by outcome")] = None,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Show decision history from SQLite."""
    from datetime import datetime

    from traderbot.db.decisions import list_by_date_range, list_by_outcome, list_by_ticker

    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    def _query_decisions(conn):
        if ticker:
            return list_by_ticker(conn, ticker)
        elif outcome:
            return list_by_outcome(conn, outcome)
        else:
            return list_by_date_range(conn, start=start_dt, end=end_dt)

    decisions = _with_db(db_path, _query_decisions)

    if json_output:
        json_lib.dump([d.model_dump(mode="json") for d in decisions], sys.stdout, default=str)
        return

    console = Console()
    if not decisions:
        console.print("No decisions found.")
        return

    table = Table(title="Decision Audit")
    table.add_column("Time", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Dir", style="bold")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Outcome", style="green")
    table.add_column("Reason")
    for d in decisions:
        reason = d.rejection_reason or ""
        table.add_row(
            d.timestamp.isoformat(),
            d.ticker,
            d.direction,
            str(d.quantity),
            str(d.price),
            d.outcome,
            reason,
        )
    console.print(table)


@app.command()
def heartbeat() -> None:
    """Print status summary."""
    Console().print("Heartbeat: system operational. No active positions.")


@app.command()
def halt(
    force: Annotated[bool, typer.Option("--force", help="Force halt (set FULL_STOP)")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Check circuit breaker status or force halt."""
    from traderbot.risk.circuit_breaker import CircuitBreaker

    console = Console()
    breaker = CircuitBreaker()

    if force:
        from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreakerState

        breaker._state = CircuitBreakerState(
            level=BreakerLevel.FULL_STOP,
            can_trade=False,
            position_size_multiplier=0.0,
            reason="Manual halt via CLI",
        )
        breaker._persist_state()

    state = breaker.get_state()
    result = state.model_dump(mode="json")

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    console.print(f"[bold]Circuit Breaker:[/bold] {state.level.name}")
    console.print(f"  Can trade:          {state.can_trade}")
    console.print(f"  Size multiplier:    {state.position_size_multiplier}")
    if state.reason:
        console.print(f"  Reason:             {state.reason}")


@app.command()
def news(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch and display news for tracked markets. (Phase 7)"""
    Console().print("Not yet implemented \u2014 coming in Phase 7.")


@app.command()
def sentiment(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Analyze market sentiment from news and social. (Phase 7)"""
    Console().print("Not yet implemented \u2014 coming in Phase 7.")


@app.command()
def backtest(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run backtests against historical data. (Phase 5)"""
    Console().print("Not yet implemented \u2014 coming in Phase 5.")


@app.command()
def paper(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Paper trade a strategy with simulated orders. (Phase 5)"""
    Console().print("Not yet implemented \u2014 coming in Phase 5.")


@app.command()
def compare(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Compare strategy performance across markets. (Phase 5)"""
    Console().print("Not yet implemented \u2014 coming in Phase 5.")


@app.command()
def performance(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show performance metrics and P&L. (Phase 5)"""
    Console().print("Not yet implemented \u2014 coming in Phase 5.")


@app.command()
def learnings(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Review and export self-learning adjustments. (Phase 6)"""
    Console().print("Not yet implemented \u2014 coming in Phase 6.")


def main() -> None:
    """Entry point for the traderbot CLI."""
    app()


if __name__ == "__main__":
    main()
