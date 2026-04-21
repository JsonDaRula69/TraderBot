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

auth_app = typer.Typer(
    name="auth",
    help="Manage API credentials via OS keyring.",
    rich_markup_mode="rich",
)
app.add_typer(auth_app, name="auth")

err_console = Console(stderr=True)


def _with_db(db_path, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(db_path) as conn:
        init_schema(conn)
        return func(conn)


def _get_strategy(name: str):
    from traderbot.simulation.engine import Context, Signal

    class MomentumStrategy:
        def on_market_open(self, market, context: Context) -> list[Signal]:
            if market.volume < 100:
                return []
            prices = market.outcome_prices
            yes_price = float(prices[0]) if prices else 0.5
            edge = abs(yes_price - 0.5)
            if edge < 0.03:
                return []
            direction = "yes" if yes_price > 0.5 else "no"
            prob = yes_price if direction == "yes" else 1.0 - yes_price
            return [Signal(
                ticker=market.ticker, direction=direction,
                quantity=1, price_cents=int(yes_price * 100),
                estimated_prob=prob, confidence=min(edge * 2, 1.0),
            )]

        def on_trade(self, trade, context: Context) -> list[Signal]:
            return []

        def on_settle(self, market, outcome, context: Context) -> None:
            pass

    if name == "momentum":
        return MomentumStrategy()

    class MeanReversionStrategy:
        def on_market_open(self, market, context: Context) -> list[Signal]:
            prices = market.outcome_prices
            yes_price = float(prices[0]) if prices else 0.5
            if 0.35 < yes_price < 0.65:
                return []
            direction = "no" if yes_price > 0.65 else "yes"
            prob = 1.0 - yes_price if direction == "no" else yes_price
            return [Signal(
                ticker=market.ticker, direction=direction,
                quantity=1, price_cents=int(yes_price * 100),
                estimated_prob=prob, confidence=0.5,
            )]

        def on_trade(self, trade, context: Context) -> list[Signal]:
            return []

        def on_settle(self, market, outcome, context: Context) -> None:
            pass

    if name == "mean_reversion":
        return MeanReversionStrategy()

    class ConservativeStrategy:
        def on_market_open(self, market, context: Context) -> list[Signal]:
            prices = market.outcome_prices
            yes_price = float(prices[0]) if prices else 0.5
            edge = abs(yes_price - 0.5)
            if edge < 0.10 or market.volume < 500:
                return []
            direction = "yes" if yes_price > 0.5 else "no"
            prob = yes_price if direction == "yes" else 1.0 - yes_price
            return [Signal(
                ticker=market.ticker, direction=direction,
                quantity=1, price_cents=int(yes_price * 100),
                estimated_prob=prob, confidence=min(edge, 1.0),
            )]

        def on_trade(self, trade, context: Context) -> list[Signal]:
            return []

        def on_settle(self, market, outcome, context: Context) -> None:
            pass

    if name == "conservative":
        return ConservativeStrategy()

    return MomentumStrategy()


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
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy name")] = "momentum",
    from_date: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = "2025-01-01",
    to_date: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD)")] = "2025-03-01",
    bankroll: Annotated[int, typer.Option("--bankroll", help="Initial bankroll in cents")] = 100000,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run backtests against historical data."""
    from datetime import date as date_type

    from rich.progress import Progress

    from traderbot.simulation.engine import BacktestEngine
    from traderbot.simulation.performance import compute_metrics

    console = Console()
    start = date_type.fromisoformat(from_date)
    end = date_type.fromisoformat(to_date)

    try:
        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.history import HistoryService

        client = KalshiClient()
        history = HistoryService(client)
    except Exception:
        if json_output:
            json_lib.dump({"error": "API connection required for backtest"}, sys.stdout)
        else:
            console.print("[red]API connection required for backtest.[/red]")
        return

    from traderbot.db import get_connection, init_schema
    from traderbot.simulation.data_loader import DataLoader, init_cache_tables

    with get_connection(db_path) as conn:
        init_schema(conn)
        init_cache_tables(conn)
        loader = DataLoader(conn, history)
        engine = BacktestEngine(loader, _get_strategy(strategy), initial_bankroll_cents=bankroll)

        if not json_output:
            with Progress() as progress:
                task = progress.add_task("Running backtest...", total=None)
                result = asyncio.run(engine.run(start, end))
                progress.update(task, completed=1)
        else:
            result = asyncio.run(engine.run(start, end))

    metrics = compute_metrics(result, initial_bankroll_cents=bankroll)

    if json_output:
        output = result.model_dump(mode="json")
        output["metrics"] = {k: v for k, v in metrics.items()}
        json_lib.dump(output, sys.stdout, default=str)
        return

    table = Table(title=f"Backtest Results \u2014 {strategy}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Trades", str(metrics["trade_count"]))
    table.add_row("Total P&L", f"${metrics['total_pnl_cents'] / 100:.2f}")
    table.add_row("Win Rate", f"{metrics['win_rate']:.1%}" if metrics["win_rate"] is not None else "\u2014")
    table.add_row("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}" if metrics["sharpe_ratio"] is not None else "\u2014")
    table.add_row("Max Drawdown", f"{metrics['max_drawdown']:.1%}" if metrics["max_drawdown"] is not None else "\u2014")
    table.add_row("Brier Score", f"{metrics['brier_score']:.4f}" if metrics["brier_score"] is not None else "\u2014")
    table.add_row("Edge Capture", f"{metrics['edge_capture']:.1%}" if metrics["edge_capture"] is not None else "\u2014")
    console.print(table)


@app.command()
def paper(
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy name")] = "momentum",
    duration: Annotated[int, typer.Option("--duration", help="Run duration in minutes")] = 60,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Paper trade a strategy with simulated orders."""
    from traderbot.kalshi.demo import DemoAdapter
    from traderbot.simulation.paper_trader import PaperTrader

    console = Console()

    try:
        demo = DemoAdapter()
    except Exception:
        if json_output:
            json_lib.dump({"error": "Demo API connection required for paper trading"}, sys.stdout)
        else:
            console.print("[red]Demo API connection required for paper trading.[/red]")
        return

    from traderbot.db import get_connection, init_schema

    with get_connection(db_path) as conn:
        init_schema(conn)
        trader = PaperTrader(demo, conn)
        portfolio = trader.get_portfolio()
        pnl = trader.get_pnl()

    result = {
        "strategy": strategy,
        "duration_minutes": duration,
        "cash_cents": portfolio.cash_cents,
        "position_count": len(portfolio.positions),
        "pnl_cents": pnl,
        "positions": [p.model_dump(mode="json") for p in portfolio.positions],
    }

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    console.print(f"[bold]Paper Trading[/bold] \u2014 {strategy} ({duration}min)")
    console.print(f"  Cash:       ${portfolio.cash_cents / 100:.2f}")
    console.print(f"  P&L:        ${pnl / 100:+.2f}")
    console.print(f"  Positions:  {len(portfolio.positions)}")

    if portfolio.positions:
        table = Table(title="Paper Positions")
        table.add_column("Ticker", style="cyan")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Price", justify="right")
        for p in portfolio.positions:
            table.add_row(p.ticker, p.side, str(p.quantity), f"${p.avg_price_cents / 100:.2f}")
        console.print(table)


@app.command()
def compare(
    profiles: Annotated[
        str,
        typer.Option("--profiles", help="Comma-separated profile names from PRESETS"),
    ] = "Conservative,Moderate,Aggressive",
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy name")] = "momentum",
    from_date: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = "2025-01-01",
    to_date: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD)")] = "2025-03-01",
    bankroll: Annotated[int, typer.Option("--bankroll", help="Initial bankroll in cents")] = 100000,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Compare strategy performance across risk profiles."""
    from datetime import date as date_type

    from traderbot.simulation.profiles import PRESETS, compare_profiles, run_profiles

    console = Console()
    start = date_type.fromisoformat(from_date)
    end = date_type.fromisoformat(to_date)

    profile_names = [n.strip() for n in profiles.split(",")]
    unknown = [n for n in profile_names if n not in PRESETS]
    if unknown:
        console.print(f"[red]Unknown profile(s): {', '.join(unknown)}[/red]")
        console.print(f"Available: {', '.join(PRESETS.keys())}")
        raise typer.Exit(code=1)

    selected_profiles = [PRESETS[n] for n in profile_names]

    try:
        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.history import HistoryService

        client = KalshiClient()
        history = HistoryService(client)
    except Exception:
        if json_output:
            json_lib.dump({"error": "API connection required for compare"}, sys.stdout)
        else:
            console.print("[red]API connection required for compare.[/red]")
        return

    from traderbot.db import get_connection, init_schema
    from traderbot.simulation.data_loader import DataLoader, init_cache_tables
    from traderbot.simulation.engine import BacktestEngine

    with get_connection(db_path) as conn:
        init_schema(conn)
        init_cache_tables(conn)
        loader = DataLoader(conn, history)
        engine = BacktestEngine(loader, _get_strategy(strategy), initial_bankroll_cents=bankroll)

        profile_results = asyncio.run(run_profiles(engine, selected_profiles, start, end))

    comparisons = compare_profiles(profile_results, initial_bankroll_cents=bankroll)

    if json_output:
        json_lib.dump(comparisons, sys.stdout, default=str)
        return

    table = Table(title="Profile Comparison")
    table.add_column("Metric", style="cyan")

    for comp in comparisons:
        table.add_column(comp["profile_name"], justify="right")

    metric_keys = ["trade_count", "total_pnl_cents", "win_rate", "sharpe_ratio", "max_drawdown", "brier_score", "edge_capture"]
    metric_labels = {
        "trade_count": "Trades",
        "total_pnl_cents": "Total P&L",
        "win_rate": "Win Rate",
        "sharpe_ratio": "Sharpe Ratio",
        "max_drawdown": "Max Drawdown",
        "brier_score": "Brier Score",
        "edge_capture": "Edge Capture",
    }
    metric_formatters = {
        "trade_count": lambda v: str(v),
        "total_pnl_cents": lambda v: f"${v / 100:.2f}",
        "win_rate": lambda v: f"{v:.1%}" if v is not None else "\u2014",
        "sharpe_ratio": lambda v: f"{v:.2f}" if v is not None else "\u2014",
        "max_drawdown": lambda v: f"{v:.1%}" if v is not None else "\u2014",
        "brier_score": lambda v: f"{v:.4f}" if v is not None else "\u2014",
        "edge_capture": lambda v: f"{v:.1%}" if v is not None else "\u2014",
    }

    for key in metric_keys:
        label = metric_labels[key]
        fmt = metric_formatters[key]
        row_values = [fmt(comp.get(key)) for comp in comparisons]
        table.add_row(label, *row_values)

    console.print(table)


@app.command()
def performance(
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    from_date: Annotated[str | None, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[str | None, typer.Option("--to", help="End date (YYYY-MM-DD)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show performance metrics and P&L."""
    from datetime import datetime

    from traderbot.db.decisions import list_by_date_range

    console = Console()

    start_dt = datetime.fromisoformat(from_date) if from_date else None
    end_dt = datetime.fromisoformat(to_date) if to_date else None

    decisions = _with_db(db_path, lambda conn: list_by_date_range(conn, start=start_dt, end=end_dt))

    executed = [d for d in decisions if d.outcome == "executed"]

    trade_count = len(executed)
    total_pnl = 0
    if trade_count > 0:
        winning = sum(1 for d in executed if d.actual_result is True or d.price > 50)
        win_rate = winning / trade_count
        for d in executed:
            total_pnl += d.price
    else:
        win_rate = None

    result = {
        "trade_count": trade_count,
        "total_pnl_cents": total_pnl,
        "win_rate": win_rate,
        "date_range": {"from": from_date, "to": to_date},
    }

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    table = Table(title="Performance Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total Trades", str(trade_count))
    table.add_row("Total P&L", f"${total_pnl / 100:.2f}")
    table.add_row("Win Rate", f"{win_rate:.1%}" if win_rate is not None else "\u2014")
    if from_date or to_date:
        table.add_row("Period", f"{from_date or 'start'} \u2014 {to_date or 'now'}")
    console.print(table)


@app.command()
def learnings(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Review and export self-learning adjustments. (Phase 6)"""
    Console().print("Not yet implemented \u2014 coming in Phase 6.")


@auth_app.command("login")
def auth_login() -> None:
    """Interactive credential setup for all services."""
    from traderbot.auth import AuthManager, KeyringUnavailableError

    console = Console()
    mgr = AuthManager()

    if not mgr.keyring_available:
        console.print(
            "[red]Keyring backend unavailable.[/red] Set credentials via .env file instead."
        )
        raise typer.Exit(code=1)

    services = ["kalshi", "voyage", "newsapi", "twitter", "reddit"]
    service_keys = {
        "kalshi": ["api_key", "api_secret"],
        "voyage": ["api_key"],
        "newsapi": ["api_key"],
        "twitter": ["api_key"],
        "reddit": ["client_id", "client_secret"],
    }

    for service in services:
        for key in service_keys[service]:
            value = typer.prompt(f"  {service}.{key}", default="", show_default=False)
            if value:
                try:
                    mgr.set_credential(service, key, value)
                    console.print(f"[green]Stored[/green] {service}.{key}")
                except KeyringUnavailableError as exc:
                    console.print(f"[red]Failed:[/red] {exc}")
                    raise typer.Exit(code=1) from exc


@auth_app.command("set-key")
def auth_set_key(
    service: Annotated[str, typer.Argument(help="Service name (e.g. kalshi, voyage)")],
    key: Annotated[str, typer.Argument(help="Credential key (e.g. api_key)")],
) -> None:
    """Store a credential in the OS keyring."""
    from traderbot.auth import AuthManager, KeyringUnavailableError

    console = Console()
    mgr = AuthManager()

    if not mgr.keyring_available:
        console.print("[red]Keyring backend unavailable.[/red]")
        raise typer.Exit(code=1)

    value = typer.prompt(f"Enter value for {service}.{key}", hide_input=True)
    try:
        mgr.set_credential(service, key, value)
        console.print(f"[green]Stored[/green] {service}.{key}")
    except KeyringUnavailableError as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@auth_app.command("list-keys")
def auth_list_keys() -> None:
    """List configured services and keys (never values)."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    services = mgr.list_services()

    if not services:
        console.print("No credentials configured.")
        return

    table = Table(title="Configured Credentials")
    table.add_column("Service", style="cyan")
    table.add_column("Keys")
    for s in services:
        table.add_row(s.name, ", ".join(s.keys))
    console.print(table)


@auth_app.command("rotate")
def auth_rotate(
    service: Annotated[str, typer.Argument(help="Service name to rotate")],
) -> None:
    """Rotate a credential (delete old, prompt for new)."""
    from traderbot.auth import _ALL_SERVICES, AuthManager, KeyringUnavailableError

    console = Console()
    mgr = AuthManager()

    if not mgr.keyring_available:
        console.print("[red]Keyring backend unavailable.[/red]")
        raise typer.Exit(code=1)

    keys = _ALL_SERVICES.get(service)
    if keys is None:
        console.print(f"[red]Unknown service:[/red] {service}")
        raise typer.Exit(code=1)

    for key in keys:
        mgr.delete_credential(service, key)
        new_val = typer.prompt(f"Enter new value for {service}.{key}", hide_input=True)
        try:
            mgr.set_credential(service, key, new_val)
            console.print(f"[green]Rotated[/green] {service}.{key}")
        except KeyringUnavailableError as exc:
            console.print(f"[red]Failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc


@auth_app.command("check")
def auth_check() -> None:
    """Verify all required credentials are configured."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    status = mgr.check_credentials()

    table = Table(title="Credential Status")
    table.add_column("Service", style="cyan")
    table.add_column("Key")
    table.add_column("Status")
    for service_name, keys in sorted(status.items()):
        for key, ok in keys.items():
            mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
            table.add_row(service_name, key, mark)
    console.print(table)

    missing = [
        f"{s}.{k}" for s, keys in status.items() for k, ok in keys.items() if not ok
    ]
    if missing:
        console.print(f"[yellow]Missing credentials:[/yellow] {', '.join(missing)}")
        console.print("Run [bold]traderbot auth login[/bold] to configure.")


def main() -> None:
    """Entry point for the traderbot CLI."""
    app()


if __name__ == "__main__":
    main()
