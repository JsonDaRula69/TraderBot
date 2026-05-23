"""Command-line interface for TraderBot."""

from __future__ import annotations

import asyncio
import json as json_lib
import logging
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry

logger = logging.getLogger(__name__)

_SUDO = shutil.which("sudo") or "/usr/bin/sudo"
_SYSTEMCTL = shutil.which("systemctl") or "/usr/bin/systemctl"
_LAUNCHCTL = shutil.which("launchctl") or "/bin/launchctl"
_SC = shutil.which("sc.exe") or shutil.which("sc")
_SCHTASKS = shutil.which("schtasks.exe") or shutil.which("schtasks")


def _mask_token(token: str) -> str:
    """Mask a token, showing only the last 4 characters."""
    return "****" + token[-4:] if len(token) > 4 else "****"

app = typer.Typer(
    name="traderbot",
    help="Autonomous prediction market investment toolkit for Kalshi.",
    rich_markup_mode="rich",
)


def _version(value: bool) -> None:
    if value:
        from traderbot.updater import get_current_version

        print(f"traderbot v{get_current_version()}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-v", help="Show version and exit.", callback=_version, is_eager=True
        ),
    ] = False,
) -> None:
    """TraderBot — Autonomous prediction market agent."""


auth_app = typer.Typer(
    name="auth",
    help="Manage API credentials via environment variables.",
    rich_markup_mode="rich",
)
app.add_typer(auth_app, name="auth")

cron_app = typer.Typer(name="cron", help="Register cron loops and heartbeat with OpenClaw.")
app.add_typer(cron_app, name="cron")

err_console = Console(stderr=True)


def _resolve_db_path(db_path: Path | None = None) -> Path:
    """Resolve database path: explicit override > profile-specific > global default."""
    from traderbot.db import DB_PATH
    from traderbot.profiles.isolation import get_profile_db_path

    if db_path is not None:
        return db_path

    from traderbot.profiles.runtime import get_current_profile
    profile = get_current_profile()
    if profile is not None:
        return get_profile_db_path(profile, "decisions.db")

    return DB_PATH


def _with_db(db_path, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(_resolve_db_path(db_path)) as conn:
        init_schema(conn)
        return func(conn)


def _get_strategy(name: str):
    from traderbot.simulation.strategies import get_strategy as _get_strat

    return _get_strat(name)


@app.command()
def scan(
    limit: Annotated[int, typer.Option("--limit", help="Max markets to return")] = 500,
    category: Annotated[str | None, typer.Option("--category", help="Filter by category")] = None,
    continuous: Annotated[
        bool, typer.Option("--continuous", help="Continuous polling mode for agent service (re-scans every 5min)")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List open markets from Kalshi. Use --continuous for agent service polling."""
    from traderbot.kalshi.markets import MarketService

    console = Console()

    def _scan_once() -> list[dict[str, object]]:
        try:
            from traderbot.kalshi.client import KalshiClient

            client = KalshiClient()
            service = MarketService(client)
            if category is not None:
                result = asyncio.run(service.list_markets_by_category(category=category, limit=limit))
            else:
                result = asyncio.run(service.list_markets(limit=limit))
            return [m.model_dump(mode="json") for m in result.markets]
        except Exception:
            return []

    if continuous:
        import time
        while True:
            markets = _scan_once()
            if json_output:
                json_lib.dump(markets, sys.stdout, default=str)
                sys.stdout.flush()
            else:
                console.print(f"[{datetime.now(UTC).isoformat()}] Scan complete: {len(markets)} markets")
            time.sleep(300)  # 5-minute polling interval to match decision loop cadence

    markets = _scan_once()

    if json_output:
        json_lib.dump(markets, sys.stdout, default=str)
        return

    table = Table(title="Open Markets")
    table.add_column("Ticker", style="cyan")
    table.add_column("Question", style="white")
    table.add_column("Volume", justify="right")
    table.add_column("State", style="green")
    for m in markets:
        table.add_row(m.ticker, m.question, str(m.volume), m.status)
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

        async def _fetch(ticker: str):
            market = await service.get_market(ticker)
            orderbook = await service.get_orderbook(ticker)
            await client.close()
            return market, orderbook

        market, orderbook = asyncio.run(_fetch(ticker))
    except Exception as exc:
        logger.warning("analyze failed for %s: %s", ticker, exc)
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            return
        console.print(f"[red]Error analyzing {ticker}:[/red] {exc}")
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
    console.print(f"State: {market.status}  Volume: {market.volume}  OI: {market.open_interest}")
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
    category: Annotated[
        str | None, typer.Option("--category", help="Filter by market category")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max markets to scan")] = 10,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Compute and display trading signals across open markets."""
    from traderbot.analysis.odds import implied_probability
    from traderbot.analysis.signals import generate_signal
    from traderbot.kalshi.models import MarketCategory

    console = Console()

    category_enum: MarketCategory | None = None
    if category is not None:
        try:
            category_enum = MarketCategory(category.lower())
        except ValueError:
            valid = ", ".join(c.value for c in MarketCategory)
            if json_output:
                json_lib.dump({"error": f"Invalid category: {category}. Valid: {valid}"}, sys.stdout)
            else:
                err_console.print(f"[red]Invalid category:[/red] {category}. Valid: {valid}")
            raise typer.Exit(code=1) from None

    try:
        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.markets import MarketService

        client = KalshiClient()
        service = MarketService(client)
        if category_enum is not None:
            result = asyncio.run(service.list_markets_by_category(category=category, limit=limit))
        else:
            result = asyncio.run(service.list_markets(limit=limit))
        markets = result.markets
    except Exception:
        if json_output:
            json_lib.dump({"note": "Signal generation requires API connection"}, sys.stdout)
        else:
            console.print("[yellow]Signal generation requires API connection.[/yellow]")
        return

    if category_enum is not None:
        cat_val = category_enum.value
        markets = [m for m in markets if m.market_category == category_enum or (m.category and m.category.lower() in (cat_val, f"climate and {cat_val}"))]

    if not markets:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print("[yellow]No open markets found.[/yellow]")
        return

    news_context: dict | None = None
    if category is not None:
        try:
            from traderbot.news.ingest import get_news_context
            news_context = get_news_context(category=category.lower())
        except Exception:
            pass
    news_sentiment: float | None = news_context.get("sentiment") if news_context else None
    news_article_count: int = news_context.get("article_count", 0) if news_context else 0

    results: list[dict] = []
    for market in markets:
        try:
            orderbook = asyncio.run(service.get_orderbook(market.ticker))
        except Exception:
            continue

        try:
            prob = implied_probability(orderbook)
        except ValueError:
            continue

        try:
            prices_int = [int(float(p)) for p in market.outcome_prices]
        except (ValueError, TypeError):
            continue

        signal = generate_signal(
            ticker=market.ticker,
            prices=prices_int,
            orderbook=orderbook,
            estimated_prob=prob.yes_prob,
            news_sentiment=news_sentiment,
        )
        results.append(
            {
                "ticker": market.ticker,
                "category": market.market_category.value if market.market_category else (market.category or "uncategorized"),
                "direction": signal.direction,
                "confidence": round(signal.confidence, 3),
                "estimated_prob": round(signal.estimated_prob, 3),
                "edge_cents": signal.edge_cents,
                "news_sentiment": news_sentiment,
                "news_article_count": news_article_count,
                "sources": [
                    {"name": s.name, "weight": s.weight, "direction": s.direction, "strength": round(s.strength, 3)}
                    for s in signal.sources
                ],
            }
        )

    if json_output:
        json_lib.dump(results, sys.stdout, default=str)
        return

    table = Table(title="Active Signals")
    table.add_column("Ticker", style="cyan")
    table.add_column("Category")
    table.add_column("Direction")
    table.add_column("Confidence", justify="right")
    table.add_column("Prob", justify="right")
    table.add_column("Edge", justify="right")
    has_news = any(r.get("news_sentiment") is not None for r in results)
    if has_news:
        table.add_column("News Sent", justify="right")
    for r in results:
        row = [
            r["ticker"],
            r["category"],
            r["direction"],
            f"{r['confidence']:.1%}",
            f"{r['estimated_prob']:.1%}",
            f"{r['edge_cents']}¢",
        ]
        if has_news:
            ns = r.get("news_sentiment")
            ns_str = f"{ns:+.2f}" if ns is not None else "—"
            row.append(ns_str)
        table.add_row(*row)
    console.print(table)


@app.command()
def trade(
    ticker: Annotated[str, typer.Argument(help="Market ticker symbol")],
    direction: Annotated[
        str, typer.Option("--direction", help="Trade direction: yes or no")
    ] = "yes",
    quantity: Annotated[int, typer.Option("--quantity", help="Number of contracts")] = 1,
    price: Annotated[int, typer.Option("--price", help="Limit price in cents")] = 50,
    estimated_prob: Annotated[
        float | None,
        typer.Option("--estimated-prob", help="Agent's estimated probability (0.0-1.0). Overrides market-implied."),
    ] = None,
    confidence: Annotated[
        float | None,
        typer.Option("--confidence", help="Agent's confidence in the estimate (0.0-1.0). Default 0.5 if not set."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
    no_confirm: Annotated[
        bool, typer.Option("--no-confirm", help="Skip confirmation prompt (for automation). Also skipped when TRADERBOT_CONFIRM_TRADES=false.")
    ] = False,
) -> None:
    """Place a trade through risk checks.

    Use --estimated-prob and --confidence to provide your own probability estimate
    instead of relying on market-implied probability, which often yields ~0 edge
    and causes all trades to be rejected by the Kelly sizing formula.
    """
    from traderbot.master_password import require_auth
    require_auth()

    from traderbot.analysis.odds import implied_probability
    from traderbot.kalshi.client import KalshiClient
    from traderbot.kalshi.markets import MarketService
    from traderbot.kalshi.models import PortfolioState, TradeRequest
    from traderbot.profiles.runtime import get_current_profile
    from traderbot.risk import evaluate_trade
    from traderbot.risk.circuit_breaker import CircuitBreaker
    from traderbot.wal import (
        DEFAULT_SESSION_STATE_PATH,
        WalAction,
        WalStatus,
        update_status,
        write_intent,
    )

    console = Console()

    profile = get_current_profile()

    confirm_trades = os.environ.get("TRADERBOT_CONFIRM_TRADES", "true").lower() != "false"
    if confirm_trades and not no_confirm:
        summary = (
            f"\n  Ticker:     {ticker}\n"
            f"  Direction:  {direction}\n"
            f"  Quantity:   {quantity}\n"
            f"  Price:      ¢{price}\n"
        )
        console.print(f"[bold]Trade Confirmation Required[/bold]{summary}")
        response = input("Execute trade? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            console.print("[yellow]Trade cancelled.[/yellow]")
            raise SystemExit(0)

    resolved_prob = estimated_prob
    resolved_confidence = confidence if confidence is not None else 0.5
    edge_estimate = 0.0
    market_price_cents = price
    market_open_interest = 0

    try:
        client = KalshiClient()
        service = MarketService(client)
        market = asyncio.run(service.get_market(ticker))
        orderbook = asyncio.run(service.get_orderbook(ticker))
        prob = implied_probability(orderbook)
        market_price_cents = prob.mid_price_cents
        market_implied = prob.yes_prob if direction.lower() == "yes" else prob.no_prob
        if resolved_prob is None:
            resolved_prob = market_implied
        edge_estimate = abs(resolved_prob - (market_price_cents / 100.0))
        market_open_interest = market.open_interest
    except Exception:
        if resolved_prob is None:
            resolved_prob = 0.5

    trade_request = TradeRequest(
        ticker=ticker,
        direction=direction,
        quantity=quantity,
        price_cents=price,
        estimated_prob=resolved_prob,
        confidence=resolved_confidence,
        edge_estimate=edge_estimate,
        market_price_cents=market_price_cents,
        market_open_interest=market_open_interest,
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

    wal_action = WalAction.BUY if direction.lower() == "yes" else WalAction.SELL
    wal_entry = write_intent(
        DEFAULT_SESSION_STATE_PATH,
        action=wal_action,
        ticker=ticker,
        direction=direction.lower(),
        quantity=quantity,
        price_cents=price,
        reason=f"CLI trade: {ticker} {direction}",
        risk_checks="pending evaluation",
        confidence=resolved_confidence,
    )

    sized = evaluate_trade(trade_request, portfolio, breaker, profile)

    if sized == 0:
        state = breaker.get_state()
        update_status(DEFAULT_SESSION_STATE_PATH, wal_entry.intent_id, WalStatus.CANCELLED)
        result = {
            "ticker": ticker,
            "direction": direction,
            "outcome": "rejected",
            "sized_position_cents": 0,
            "reason": state.reason or "Risk check failed",
            "wal_intent_id": wal_entry.intent_id,
        }
    else:
        update_status(DEFAULT_SESSION_STATE_PATH, wal_entry.intent_id, WalStatus.COMPLETED)
        result = {
            "ticker": ticker,
            "direction": direction,
            "outcome": "executed",
            "sized_position_cents": sized,
            "wal_intent_id": wal_entry.intent_id,
        }

    from traderbot.risk.audit import AuditLogger
    from traderbot.kalshi.models import Decision

    decision = Decision(
        timestamp=datetime.now(UTC),
        ticker=ticker,
        direction=direction,
        quantity=quantity,
        price=price,
        signal_strength=resolved_prob,
        confidence=resolved_confidence,
        edge_estimate=edge_estimate,
        risk_checks={"all_passed": sized > 0},
        outcome=result["outcome"],
        rejection_reason=result.get("reason"),
    )
    AuditLogger().log_decision(decision)

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
    from traderbot.profiles.runtime import get_current_profile

    db = _resolve_db_path(db_path)
    profile = get_current_profile()
    if profile is None and db_path is None:
        logger.info(
            "No active profile; using default DB at %s. Set TRADERBOT_PROFILE_TOKEN or pass --db to query a profile-specific DB.",
            db,
        )

    all_positions = _with_db(db, list_all)

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

    decisions = _with_db(_resolve_db_path(db_path), _query_decisions)

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


def _python_version_ok() -> tuple[bool, str, tuple[int, int]]:
    """Check if the running Python version is compatible (3.12.x only)."""
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    return (major, minor) == (3, 12), version_str, (major, minor)


@app.command()
def bootstrap(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate without writing to DB")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """One-time setup wizard for new users."""
    import platform

    from traderbot.auth import AuthManager
    from traderbot.db import DB_PATH, get_connection, init_schema
    from traderbot.paths import get_data_dir

    console = Console()
    steps: dict[str, str | bool] = {}

    # Step 1: Check Python version (3.12.x — chroma-hnswlib has no wheels for 3.13+)
    py_ok, version_str, _py_version_tuple = _python_version_ok()
    steps["python_version"] = version_str
    steps["python_version_ok"] = py_ok

    if not py_ok:
        if json_output:
            json_lib.dump(
                {"error": f"Python {version_str} — 3.12.x required (chromadb dependency)", "steps": steps},
                sys.stdout,
            )
            raise typer.Exit(code=1)
        console.print(f"[red]Python {version_str} found, but 3.12.x is required (chromadb has no wheels for 3.13+).[/red]")
        raise typer.Exit(code=1)

    # Step 2: Create default config directory
    config_dir = get_data_dir()
    config_dir_exists = config_dir.exists()
    steps["config_dir"] = str(config_dir)
    if not dry_run and not config_dir_exists:
        config_dir.mkdir(parents=True, exist_ok=True)
    steps["config_dir_created"] = not config_dir_exists and not dry_run

    mgr = AuthManager()
    status = mgr.check_credentials()

    if not dry_run and not json_output:
        console.print("\n[bold]Credential Setup[/bold]")
        console.print("Enter your API credentials (press Enter to skip any field):")
        from traderbot.auth import _ALL_SERVICES

        env_lines: list[str] = []
        for service_name, keys in _ALL_SERVICES.items():
            for key in keys:
                value = typer.prompt(f"  {service_name}.{key}", default="", show_default=False)
                if value:
                    env_key = f"{service_name.upper()}_{key.upper()}"
                    env_lines.append(f"{env_key}={value}")
                    console.print(f"[green]Saved to .env:[/green] {env_key}")

        if env_lines:
            env_path = get_data_dir() / ".env"
            env_path.parent.mkdir(parents=True, exist_ok=True)
            existing = env_path.read_text() if env_path.exists() else ""
            new_content = existing.rstrip() + "\n" + "\n".join(env_lines) + "\n"
            env_path.write_text(new_content)
            os.chmod(env_path, 0o600)
            console.print(f"[dim]Credentials written to {env_path}[/dim]")

    # Step 5: Create SQLite DB at configured path
    db_path = DB_PATH
    steps["db_path"] = str(db_path)
    if not dry_run:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with get_connection(_resolve_db_path(db_path)) as conn:
            init_schema(conn)
    steps["db_created"] = not dry_run

    # Step 6: Run auth check to verify all credentials
    status = mgr.check_credentials()
    all_ok = all(ok for keys in status.values() for ok in keys.values())
    steps["credentials_ok"] = all_ok
    steps["credential_status"] = {
        s: {k: v for k, v in keys.items()} for s, keys in sorted(status.items())
    }

    missing = [f"{s}.{k}" for s, keys in status.items() for k, ok in keys.items() if not ok]
    steps["missing_credentials"] = missing

    # Step 7: Platform info
    steps["platform"] = platform.platform()

    if json_output:
        json_lib.dump(steps, sys.stdout, default=str)
        return

    console.print("\n[bold]TraderBot Bootstrap[/bold]")
    console.print("=" * 40)

    console.print("\n[bold]1. Python Version[/bold]")
    if py_ok:
        console.print(f"  [green]✓[/green] Python {steps['python_version']} (= 3.12)")
    else:
        console.print(f"  [red]✗[/red] Python {steps['python_version']} (requires = 3.12)")

    console.print("\n[bold]2. Config Directory[/bold]")
    if config_dir_exists or dry_run:
        console.print(f"  [green]✓[/green] {config_dir}")
    else:
        console.print(f"  [green]✓[/green] Created {config_dir}")

    console.print("\n[bold]3. Credentials[/bold]")
    for service_name, keys in sorted(status.items()):
        for key, ok in keys.items():
            mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
            console.print(f"  {mark} {service_name}.{key}")

    console.print("\n[bold]4. Database[/bold]")
    if dry_run:
        console.print(f"  (dry-run) {db_path}")
    else:
        console.print(f"  [green]✓[/green] {db_path}")

    console.print("\n" + "=" * 40)
    if all_ok:
        console.print("[bold green]Bootstrap complete![/bold green]")
        console.print("\nNext steps:")
        console.print("  [cyan]traderbot scan[/cyan]               — list open markets")
        console.print("  [cyan]traderbot backtest --strategy momentum[/cyan] — run a backtest")
    else:
        console.print("[bold yellow]Bootstrap partially complete.[/bold yellow]")
        if missing:
            console.print(f"  Missing credentials: {', '.join(missing)}")
            console.print(
                "  Run [bold]traderbot auth check[/bold] to verify credentials."
            )


@app.command()
def heartbeat(
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report only — no state changes")
    ] = False,
) -> None:
    """Periodic self-review: performance, adaptation, risk state, and learning promotion."""
    from traderbot.db import init_schema
    from traderbot.db.learnings import init_table as init_learnings_table
    from traderbot.heartbeat import DEFAULT_HEARTBEAT_PATH, run_heartbeat_cycle
    from traderbot.profiles.runtime import get_current_profile
    from traderbot.simulation.adapter_state import resolve_state_path

    console = Console()

    def _run(conn):
        init_schema(conn)
        init_learnings_table(conn)
        from traderbot.learning import init_task_observations_table

        init_task_observations_table(conn)

        # Compute state path based on profile
        profile = get_current_profile()
        state_path = None
        if profile:
            state_path = resolve_state_path(profile_base_dir=profile.base_dir)
        else:
            state_path = resolve_state_path(state_path=Path(".traderbot/adaptation_state.json"))

        return asyncio.run(run_heartbeat_cycle(
            conn, heartbeat_path=DEFAULT_HEARTBEAT_PATH, state_path=state_path, dry_run=dry_run
        ))

    try:
        result = _with_db(_resolve_db_path(db_path), _run)
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
        else:
            console.print(f"[red]Heartbeat failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        json_lib.dump(result.model_dump(mode="json"), sys.stdout, default=str)
        return

    perf = result.performance
    decision = result.decisions
    adapt = result.adaptation
    lrn = result.learning_promotion
    cb = result.circuit_breaker
    health = result.system_health

    console.print(f"\n[bold]Heartbeat[/bold] — {result.timestamp.isoformat()}")
    console.print(f"  Steps completed: {', '.join(result.steps_completed)}")

    console.print("\n[bold]Performance[/bold]")
    pnl_str = f"{perf.total_pnl_cents / 100:+.2f}"
    console.print(
        f"  Trades: {perf.trade_count}  Win rate: {perf.win_rate:.0%}  P&L: {pnl_str} USD"
    )
    if perf.deviation_flag:
        console.print(f"  [yellow]⚠[/yellow] {perf.deviation_flag}")

    console.print("\n[bold]Decisions[/bold]")
    console.print(
        f"  Closed: {decision.closed_count}  "
        f"Correct: {decision.correct_predictions}  "
        f"Accuracy: {decision.prediction_accuracy:.0%}"
    )
    if decision.pending_review:
        console.print(f"  Open: {decision.open_count} — {', '.join(decision.pending_review[:5])}")

    console.print("\n[bold]Adaptation[/bold]")
    if adapt.updated:
        console.print(
            f"  Edge threshold: {adapt.direction} "
            f"(magnitude={adapt.magnitude:.4f}, "
            f"confidence={adapt.confidence:.2f})"
        )
        console.print(f"  Method: {adapt.method}")
    else:
        console.print(f"  No update — {adapt.skipped_reason}")

    console.print("\n[bold]Learnings[/bold]")
    if lrn.promoted:
        for key in lrn.promoted:
            console.print(f"  [green]Promoted:[/green] {key}")
    else:
        console.print("  No promotions this cycle")

    console.print("\n[bold]Circuit Breaker[/bold]")
    level_style = "green" if cb.level == "NORMAL" else "red"
    console.print(f"  Level: [{level_style}]{cb.level}[/{level_style}]  Can trade: {cb.can_trade}")

    console.print("\n[bold]System Health[/bold]")
    console.print(
        f"  API: {health.api_connectivity}  "
        f"DB: {health.db_integrity}  "
        f"Freshness: {health.data_freshness}"
    )

    if health.alerts or cb.level != "NORMAL":
        console.print("\n[bold yellow]Alerts[/bold yellow]")
        for alert in health.alerts:
            console.print(f"  [yellow]⚠[/yellow] {alert}")
        if cb.level != "NORMAL":
            console.print(f"  [yellow]⚠[/yellow] Circuit breaker: {cb.level} — {cb.reason}")


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
def resume(
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Resume trading after circuit breaker halt. Clears FULL_STOP/HALT state."""
    from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker, CircuitBreakerState

    console = Console()
    breaker = CircuitBreaker()
    state = breaker.get_state()

    if state.level == BreakerLevel.NORMAL:
        if json_output:
            json_lib.dump(state.model_dump(mode="json"), sys.stdout, default=str)
        else:
            console.print("[green]Circuit breaker already NORMAL — no action needed.[/green]")
        return

    breaker._state = CircuitBreakerState()
    breaker._persist_state()
    new_state = breaker.get_state()

    if json_output:
        json_lib.dump(
            {"previous_level": state.level.name, "current_level": new_state.level.name, "can_trade": new_state.can_trade},
            sys.stdout,
            default=str,
        )
        return

    console.print(f"[green]✓[/green] Circuit breaker cleared: {state.level.name} → {new_state.level.name}")
    console.print(f"  Can trade: {new_state.can_trade}")


@app.command()
def news(
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            help="Filter by category: Economics, Politics, Weather, Culture, Tech, Science",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max items to fetch")] = 10,
    source: Annotated[
        str | None,
        typer.Option("--source", help="Filter by source: newsapi, twitter, reddit, open-meteo, coingecko, thesportsdb, openweathermap, fred, google-trends, all"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch and display news for tracked markets."""
    from traderbot.news.cache_paths import get_news_cache_path
    from traderbot.news.classifier import NewsClassifier
    from traderbot.news.models import DataPoint, NewsCategory, NewsItem, NewsSource
    from traderbot.news.sentiment_scorer import SentimentScorer
    from traderbot.news.sources import DataSourcesConfig, NewsAggregator
    from traderbot.profiles.config import resolve_fred_key, resolve_newsapi_key, resolve_openweather_key
    from traderbot.profiles.runtime import get_current_profile

    console = Console()

    # Resolve active profile
    profile = get_current_profile()

    # Validate --category
    category_enum: NewsCategory | None = None
    if category is not None:
        try:
            category_enum = NewsCategory(category.lower())
        except ValueError:
            valid = ", ".join(c.value for c in NewsCategory)
            if json_output:
                json_lib.dump(
                    {"error": f"Invalid category: {category}. Valid: {valid}"}, sys.stdout
                )
            else:
                err_console.print(f"[red]Invalid category:[/red] {category}. Valid: {valid}")
            raise typer.Exit(code=1) from None

    # Profile-aware category validation: --category must be in enabled_categories
    if (
        profile is not None
        and category_enum is not None
        and profile.enabled_categories
        and not profile.is_category_enabled(category_enum)
    ):
        if json_output:
            json_lib.dump(
                {
                    "error": f"Category '{category_enum.value}' not enabled for profile '{profile.name}'"
                },
                sys.stdout,
            )
        else:
            err_console.print(
                f"[red]Category '{category_enum.value}' not enabled for profile '{profile.name}'.[/red] "
                f"Enabled: {', '.join(c.value for c in profile.enabled_categories)}"
            )
        raise typer.Exit(code=1) from None

    # Build category filter from profile and/or --category flag
    category_filter: list[NewsCategory] | None = None
    if profile is not None and profile.enabled_categories:
        category_filter = profile.enabled_categories

    # If --category was explicitly passed, use it for fetching even without a profile
    if category_enum is not None:
        if category_filter is not None:
            # Both profile categories and --category: intersect (must be in both)
            if category_enum not in category_filter:
                category_filter = None  # let it fall through to the display filter
            else:
                category_filter = [category_enum]
        else:
            # No profile categories: use --category alone
            category_filter = [category_enum]

    # Validate --source (normalize hyphens to underscores for enum lookup)
    source_filter: NewsSource | None = None
    if source is not None and source != "all":
        try:
            source_filter = NewsSource(source.lower().replace("-", "_"))
        except ValueError:
            valid = ", ".join(s.value.replace("_", "-") for s in NewsSource)
            if json_output:
                json_lib.dump({"error": f"Invalid source: {source}. Valid: {valid}"}, sys.stdout)
            else:
                err_console.print(f"[red]Invalid source:[/red] {source}. Valid: {valid}")
            raise typer.Exit(code=1) from None

    # Resolve API keys via profile-aware chain
    newsapi_key = resolve_newsapi_key(profile)
    twitter_key = os.environ.get("TWITTER_API_KEY")
    openweather_key = resolve_openweather_key(profile)
    fred_key = resolve_fred_key(profile)

    # Profile-aware news cache path
    cache_path = get_news_cache_path(profile)
    logger.debug("News cache path: %s", cache_path)

    ds_config = DataSourcesConfig(
        newsapi_key=newsapi_key,
        openweather_key=openweather_key,
        fred_key=fred_key,
    )

    async def _fetch() -> list[NewsItem | DataPoint]:
        async with NewsAggregator(config=ds_config, twitter_api_key=twitter_key) as aggregator:
            return await aggregator.fetch_all(
                limit=limit,
                category_filter=category_filter,
                source_filter=source_filter,
            )

    try:
        items = asyncio.run(_fetch())
    except Exception:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print("[red]Failed to fetch news.[/red]")
        return

    classifier = NewsClassifier()
    scorer = SentimentScorer()
    classified_items: list[dict] = []
    datapoints: list[DataPoint] = []
    for item_or_dp in items:
        if isinstance(item_or_dp, DataPoint):
            datapoints.append(item_or_dp)
            continue
        classified = classifier.classify(item_or_dp, category_filter=category_filter)
        if classified is None:
            continue
        if category_enum is not None and classified.category != category_enum:
            continue
        sentiment = scorer.score(item_or_dp.title, item_or_dp.source, item_or_dp.id)
        classified_items.append(
            {
                "classified": classified,
                "sentiment": sentiment,
            }
        )

    if json_output:
        output = []
        for entry in classified_items:
            c = entry["classified"]
            s = entry["sentiment"]
            item = c.news_item
            output.append(
                {
                    "type": "news_item",
                    "id": item.id,
                    "title": item.title,
                    "source": item.source.value,
                    "category": c.category.value,
                    "published_at": item.published_at.isoformat(),
                    "sentiment_score": s.score,
                    "sentiment_confidence": s.confidence,
                    "sentiment_model": s.model,
                    "url": item.url,
                    "ticker_refs": item.ticker_refs,
                }
            )
        for dp in datapoints:
            output.append(
                {
                    "type": "data_point",
                    "id": dp.id,
                    "source": dp.source.value,
                    "category": dp.category.value if dp.category else None,
                    "title": dp.title,
                    "data": dp.data,
                    "timestamp": dp.timestamp.isoformat(),
                    "ticker_refs": dp.ticker_refs,
                    "metadata": dp.metadata,
                }
            )
        json_lib.dump(output, sys.stdout, default=str)
        return

    if not classified_items and not datapoints:
        console.print("No news items found.")
        return

    table = Table(title="News Feed")
    table.add_column("Title", style="white", max_width=50)
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Published", style="dim")
    table.add_column("Sentiment", justify="right")

    for entry in classified_items:
        c = entry["classified"]
        s = entry["sentiment"]
        item = c.news_item
        title = item.title[:50] + "\u2026" if len(item.title) > 50 else item.title
        published = item.published_at.strftime("%Y-%m-%d %H:%M") if item.published_at else "\u2014"
        score_str = f"{s.score:+.2f}"
        table.add_row(title, "news", item.source.value, c.category.value, published, score_str)

    for dp in datapoints:
        title = dp.title[:50] + "\u2026" if len(dp.title) > 50 else dp.title
        cat_str = dp.category.value if dp.category else "\u2014"
        ts_str = dp.timestamp.strftime("%Y-%m-%d %H:%M")
        table.add_row(title, "data", dp.source.value, cat_str, ts_str, "\u2014")
    console.print(table)


@app.command()
def sentiment(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BTC, SPX)")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Analyze market sentiment from news and social for a ticker."""
    from traderbot.news.cache_paths import get_news_cache_path
    from traderbot.news.classifier import NewsClassifier
    from traderbot.news.impact_assessor import ImpactAssessor
    from traderbot.news.models import NewsCategory, NewsItem, NewsSource
    from traderbot.news.sentiment_scorer import SentimentScorer
    from traderbot.news.sources import NewsAggregator
    from traderbot.profiles.config import resolve_newsapi_key
    from traderbot.profiles.runtime import get_current_profile

    console = Console()

    profile = get_current_profile()

    newsapi_key = resolve_newsapi_key(profile)
    twitter_key = os.environ.get("TWITTER_API_KEY")

    category_filter: list[NewsCategory] | None = None
    if profile is not None and profile.enabled_categories:
        category_filter = profile.enabled_categories

    cache_path = get_news_cache_path(profile)
    logger.debug("News cache path: %s", cache_path)

    async def _fetch() -> list[NewsItem]:
        async with NewsAggregator(
            newsapi_key=newsapi_key, twitter_api_key=twitter_key
        ) as aggregator:
            return await aggregator.fetch_all(limit=50)

    try:
        items = asyncio.run(_fetch())
    except Exception:
        if json_output:
            json_lib.dump({"error": "Failed to fetch news"}, sys.stdout)
        else:
            console.print("[red]Failed to fetch news.[/red]")
        return

    # Filter items that reference the ticker (case-insensitive)
    ticker_upper = ticker.upper()
    ticker_refs_items = [
        item
        for item in items
        if any(t.upper() == ticker_upper for t in item.ticker_refs)
        or ticker_upper in item.title.upper()
    ]

    if not ticker_refs_items and not items:
        if json_output:
            json_lib.dump({"ticker": ticker_upper, "error": "No news found"}, sys.stdout)
        else:
            console.print(
                f"[yellow]No news found for [/yellow]{ticker_upper}[yellow]. Check API keys.[/yellow]"
            )
        return

    # Fall back to all items if none have ticker refs
    items_to_analyze = ticker_refs_items if ticker_refs_items else items[:10]

    classifier = NewsClassifier()
    scorer = SentimentScorer()
    assessor = ImpactAssessor()

    results: list[dict] = []
    for item in items_to_analyze:
        classified = classifier.classify(item, category_filter=category_filter)
        if classified is None:
            continue
        sentiment = scorer.score(item.title, item.source, item.id)
        impact = assessor.assess(item, classified, sentiment)
        results.append(
            {
                "classified": classified,
                "sentiment": sentiment,
                "impact": impact,
            }
        )

    if not results:
        if json_output:
            json_lib.dump({"ticker": ticker_upper, "items_analyzed": 0}, sys.stdout)
        else:
            console.print(f"[yellow]No relevant news found for {ticker_upper}.[/yellow]")
        return

    # Compute aggregate sentiment
    scores = [r["sentiment"].score for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    confidences = [r["sentiment"].confidence for r in results]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    direction = "bullish" if avg_score > 0.1 else "bearish" if avg_score < -0.1 else "neutral"

    if json_output:
        output = {
            "ticker": ticker_upper,
            "items_analyzed": len(results),
            "sentiment": {
                "score": round(avg_score, 4),
                "direction": direction,
                "confidence": round(avg_confidence, 4),
            },
            "impacts": [
                {
                    "news_id": r["impact"].news_id,
                    "ticker": r["impact"].ticker,
                    "direction": r["impact"].direction,
                    "magnitude": r["impact"].magnitude,
                    "confidence": r["impact"].confidence,
                    "timeframe": r["impact"].timeframe,
                    "reasoning": r["impact"].reasoning,
                }
                for r in results
            ],
        }
        json_lib.dump(output, sys.stdout, default=str)
        return

    # Rich output
    console.print(f"\n[bold]Sentiment Analysis: {ticker_upper}[/bold]")
    console.print(f"  Items analyzed: {len(results)}")
    console.print(f"  Sentiment score: {avg_score:+.4f}")
    direction_style = (
        "green" if direction == "bullish" else "red" if direction == "bearish" else "yellow"
    )
    console.print(f"  Direction: [{direction_style}]{direction}[/{direction_style}]")
    console.print(f"  Confidence: {avg_confidence:.1%}")

    if results:
        table = Table(title=f"Impact Assessments \u2014 {ticker_upper}")
        table.add_column("Title", style="white", max_width=40)
        table.add_column("Dir", style="bold")
        table.add_column("Magnitude", justify="right")
        table.add_column("Timeframe")
        table.add_column("Confidence", justify="right")
        for r in results:
            impact = r["impact"]
            title = (
                r["classified"].news_item.title[:40] + "\u2026"
                if len(r["classified"].news_item.title) > 40
                else r["classified"].news_item.title
            )
            dir_color = (
                "green"
                if impact.direction == "bullish"
                else "red"
                if impact.direction == "bearish"
                else "yellow"
            )
            table.add_row(
                title,
                f"[{dir_color}]{impact.direction}[/{dir_color}]",
                f"{impact.magnitude:.2f}",
                impact.timeframe,
                f"{impact.confidence:.1%}",
            )
        console.print(table)


@app.command()
def news_ingest(
    limit: Annotated[int, typer.Option("--limit", help="Max items to fetch per run")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch, classify, embed, and store news articles into ChromaDB.

    Runs as a pure data pipeline — no LLM required. Call from cron/timer
    to accumulate news while the agent is offline. Subsequent calls
    automatically deduplicate by URL hash.
    """
    from traderbot.news.ingest import ingest_news
    from traderbot.profiles.runtime import get_current_profile
    from traderbot.profiles.config import resolve_newsapi_key, resolve_openweather_key, resolve_fred_key

    console = Console()

    profile = get_current_profile()
    newsapi_key = resolve_newsapi_key(profile)
    openweather_key = resolve_openweather_key(profile)
    fred_key = resolve_fred_key(profile)

    if newsapi_key:
        os.environ["NEWSAPI_API_KEY"] = newsapi_key
    if openweather_key:
        os.environ["OPENWEATHER_API_KEY"] = openweather_key
    if fred_key:
        os.environ["FRED_API_KEY"] = fred_key
    if profile:
        voyage_key = os.environ.get(
            f"VOYAGE_API_KEY_PROFILE_{profile.name.upper()}",
            os.environ.get("VOYAGE_API_KEY", "")
        )
        if voyage_key:
            os.environ["VOYAGE_API_KEY"] = voyage_key

    report = ingest_news(
        limit=limit,
        newsapi_key=newsapi_key,
        openweather_key=openweather_key,
        fred_key=fred_key,
    )

    if json_output:
        json_lib.dump(report.to_dict(), sys.stdout, default=str)
        return

    console.print(f"[green]✓[/green] Ingest report — "
                  f"[bold]{report.new}[/bold] new, "
                  f"{report.duplicates} duplicates, "
                  f"{report.skipped} skipped, "
                  f"{report.signals} signals, "
                  f"{report.errors} errors "
                  f"({report.elapsed_seconds:.1f}s)")
    console.print(f"  News collection: {report.collection_sizes.get('news', 0)} items")
    console.print(f"  Signals collection: {report.collection_sizes.get('news_signals', 0)} items")
    dp_count = report.collection_sizes.get("data_points", 0)
    if dp_count:
        console.print(f"  DataPoints collection: {dp_count} items")


@app.command()
def news_context(
    category: Annotated[str, typer.Argument(help="News/market category (economics, weather, politics, ...)")],
    hours: Annotated[int, typer.Option("--hours", "-h", help="Look back window in hours")] = 24,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max articles to return")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    include_data: Annotated[bool, typer.Option("--include-data", help="Also include data point readings (weather, economic indicators, etc.)")] = False,
) -> None:
    """Get news context for a market category — aggregated sentiment + top articles.

    Queries ChromaDB for news in the given category, computes aggregate
    sentiment, and returns structured data. Use this before trading to
    understand the news landscape for a market category.

    Use --include-data to also fetch quantitative readings (temperature,
    humidity, economic indicators, crypto prices) for the same category.
    """
    from traderbot.news.ingest import get_news_context

    console = Console()
    ctx = get_news_context(category=category, since_hours=hours, max_articles=limit, include_data_points=include_data)

    if json_output:
        json_lib.dump(ctx, sys.stdout, default=str)
        return

    if ctx["article_count"] == 0:
        console.print(f"[yellow]No news articles found for '{category}' in the last {hours}h.[/yellow]")
    else:
        console.print(f"[bold]News Context:[/bold] {category} — last {hours}h")
        console.print(f"  Articles: {ctx['article_count']}")
        console.print(f"  Sentiment: [bold]{ctx['sentiment']}[/bold] "
                      f"(+{ctx['positive_count']}/-{ctx['negative_count']}/{ctx['neutral_count']})")
        console.print()

        table = Table(title="Top Articles")
        table.add_column("Source", style="cyan")
        table.add_column("Sentiment", justify="right")
        table.add_column("Title", style="white")
        for a in ctx["articles"]:
            sent_str = f"{a['sentiment_score']:.2f}" if a["sentiment_score"] is not None else "—"
            table.add_row(a["source"], sent_str, a["title"][:80])
        console.print(table)

    # Show data points when included
    data_pts = ctx.get("data_points")
    if data_pts and data_pts.get("count", 0) > 0:
        console.print()
        console.print(f"[bold]Data Points:[/bold] {data_pts['count']} readings")
        for dp in data_pts["data_points"][:5]:
            title = dp.get("title", "")[:80]
            data_str = "; ".join(f"{k}={v}" for k, v in dp.get("data", {}).items())
            console.print(f"  [cyan]{dp['source']}[/cyan] {title} — {data_str}")


@app.command()
def backfill(
    months: Annotated[int, typer.Option("--months", "-m", help="Months of history to backfill")] = 6,
) -> None:
    """One-time historical data backfill for weather and economic indicators.

    Fetches 6 months (default) of historical weather data from Open-Meteo
    and economic observations from FRED, storing to the data_points
    ChromaDB collection. Run this once to bootstrap historical context
    before regular news-ingest cycles take over.
    """
    from traderbot.news.ingest import backfill_data

    console = Console()
    console.print(f"[bold]Backfill:[/bold] fetching {months} months of historical data...")

    counts = backfill_data(months=months)

    console.print()
    console.print("[bold green]Backfill complete:[/bold green]")
    for source, count in counts.items():
        console.print(f"  {source}: {count} data points stored")
    total = sum(counts.values())
    console.print(f"  [bold]Total: {total}[/bold]")


@app.command()
def data_points(
    category: Annotated[str, typer.Argument(help="Market category (weather, economics, politics, ...)")],
    hours: Annotated[int, typer.Option("--hours", "-h", help="Look back window in hours")] = 48,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max data points to return")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Query data point readings for a market category.

    Returns structured quantitative data (weather readings, economic
    indicators, crypto prices, sports scores) stored by the offline
    ingestion pipeline. Useful for pre-trade context on weather,
    economics, and other data-driven markets.
    """
    from traderbot.news.ingest import get_data_points

    console = Console()
    ctx = get_data_points(category=category, since_hours=hours, max_items=limit)

    if json_output:
        import json as _json
        _json.dump(ctx, sys.stdout, default=str)
        return

    if ctx["count"] == 0:
        console.print(f"[yellow]No data points found for '{category}' in the last {hours}h.[/yellow]")
        return

    console.print(f"[bold]Data Points:[/bold] {category} — last {hours}h")
    console.print(f"  Readings: {ctx['count']}")
    console.print()

    for dp in ctx["data_points"]:
        console.print(f"[cyan]{dp['source']}[/cyan] — {dp['title']}")
        data_str = "; ".join(f"{k}={v}" for k, v in dp.get("data", {}).items())
        if data_str:
            console.print(f"  Data: {data_str}")


@app.command()
def news_summary(
    since: Annotated[
        str | None,
        typer.Option("--since", help="ISO 8601 timestamp — only articles after this time"),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option("--category", help="Filter by category (Economics, Politics, Weather, ...)"),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="Filter by source (newsapi, reddit, coingecko, ...)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max articles to return")] = 30,
    query: Annotated[
        str | None,
        typer.Option("--query", help="Semantic search query (uses VoyageAI embedding)"),
    ] = None,
    signal_only: Annotated[
        bool,
        typer.Option("--signals", help="Only return high-impact signals"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Retrieve accumulated news from ChromaDB.

    Supports time-range filtering, category/source filters, and
    semantic search via VoyageAI. Without --since, returns the
    most recent articles across all time.
    """
    from traderbot.news.ingest import get_news_summary

    console = Console()

    since_dt: datetime | None = None
    if since is not None:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            err_console = Console(stderr=True)
            err_console.print(f"[red]Invalid timestamp:[/red] {since}. Use ISO 8601 format.")
            raise typer.Exit(code=1) from None

    items = get_news_summary(
        since=since_dt,
        category=category,
        source=source,
        limit=limit,
        query=query,
        signal_only=signal_only,
    )

    if json_output:
        json_lib.dump([it.to_dict() for it in items], sys.stdout, default=str)
        return

    if not items:
        console.print("No accumulated news found.")
        return

    table = Table(title="Accumulated News")
    table.add_column("Title", style="white", max_width=50)
    table.add_column("Source", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Sentiment", justify="right")
    table.add_column("Impact", justify="right")
    table.add_column("Published", style="dim")

    for item in items:
        meta = item.metadata
        title = meta.get("title", item.text[:80]) or item.text[:80]
        score_str = meta.get("sentiment_score", "")
        imp_str = meta.get("impact_magnitude", "")
        table.add_row(
            title,
            meta.get("source", ""),
            meta.get("category", ""),
            f"{score_str}" if score_str else "",
            f"{imp_str}" if imp_str else "",
            meta.get("published", "")[:10],
        )
    console.print(table)


@app.command()
def backtest(
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy name")] = "momentum",
    from_date: Annotated[
        str, typer.Option("--from", help="Start date (YYYY-MM-DD)")
    ] = "2025-01-01",
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

    with get_connection(_resolve_db_path(db_path)) as conn:
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
    table.add_row(
        "Win Rate", f"{metrics['win_rate']:.1%}" if metrics["win_rate"] is not None else "\u2014"
    )
    table.add_row(
        "Sharpe Ratio",
        f"{metrics['sharpe_ratio']:.2f}" if metrics["sharpe_ratio"] is not None else "\u2014",
    )
    table.add_row(
        "Max Drawdown",
        f"{metrics['max_drawdown']:.1%}" if metrics["max_drawdown"] is not None else "\u2014",
    )
    table.add_row(
        "Brier Score",
        f"{metrics['brier_score']:.4f}" if metrics["brier_score"] is not None else "\u2014",
    )
    table.add_row(
        "Edge Capture",
        f"{metrics['edge_capture']:.1%}" if metrics["edge_capture"] is not None else "\u2014",
    )
    console.print(table)


@app.command()
def paper(
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy name")] = "momentum",
    duration: Annotated[int, typer.Option("--duration", help="Run duration in minutes")] = 60,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    initial_balance: Annotated[
        int | None,
        typer.Option(
            "--initial-balance",
            help="Starting cash in dollars (converted to cents). 0 = fetch from prod API.",
        ),
    ] = None,
    reconcile: Annotated[
        bool,
        typer.Option(
            "--reconcile",
            help="Run settlement reconciliation on startup (not yet implemented).",
        ),
    ] = False,
) -> None:
    """Run a paper trading session with real market data.

    Connects to the live Kalshi API, fetches open markets, runs the specified
    strategy through risk checks, and tracks simulated positions and P&L.
    Press Ctrl+C to stop early and see final results.
    """
    from traderbot.master_password import require_auth
    require_auth()

    import asyncio
    import time

    from traderbot.kalshi.cache import MarketDataCache
    from traderbot.kalshi.client import KalshiClient
    from traderbot.kalshi.markets import MarketService
    from traderbot.kalshi.provider import ProdDataProvider
    from traderbot.simulation.engine import Signal
    from traderbot.simulation.paper_trader import PaperTrader, DEFAULT_INITIAL_BALANCE_CENTS
    from traderbot.simulation.settlement import SettlementVerifier
    from traderbot.simulation.strategies import get_strategy

    console = Console()
    err_console = Console(stderr=True)

    strat = get_strategy(strategy)

    from traderbot.db import get_connection, init_schema
    from traderbot.profiles import get_current_profile

    profile = get_current_profile()

    cache = MarketDataCache(profile=profile)

    try:
        client = KalshiClient()
    except Exception:
        if json_output:
            json_lib.dump({"error": "Kalshi API connection required for paper trading"}, sys.stdout)
        else:
            console.print("[red]Kalshi API connection required for paper trading.[/red]")
        return

    provider = ProdDataProvider(client, cache, profile)
    market_service = MarketService(client)

    # --- resolve initial balance ---
    initial_cash_cents: int

    if initial_balance is not None and initial_balance > 0:
        initial_cash_cents = initial_balance * 100
        logger.info("Using CLI balance: $%s", initial_balance)
        console.print(f"[dim]Using CLI balance: ${initial_balance:,}[/dim]")
    elif profile is not None and profile.initial_balance_cents is not None:
        initial_cash_cents = profile.initial_balance_cents
        logger.info("Using profile balance: $%s", profile.initial_balance_cents / 100)
        console.print(f"[dim]Using profile balance: ${profile.initial_balance_cents / 100:,.2f}[/dim]")
    else:
        fetched = False
        try:
            from traderbot.kalshi.client import KalshiClient
            from traderbot.kalshi.portfolio import PortfolioService

            prod_client = KalshiClient()
            portfolio_svc = PortfolioService(prod_client)
            balance_data = asyncio.run(portfolio_svc.get_balance())
            balance_cents = balance_data.get("balance") or balance_data.get("available_balance")
            if isinstance(balance_cents, str):
                balance_cents = int(float(balance_cents) * 100)
            if balance_cents and int(balance_cents) > 0:
                initial_cash_cents = int(balance_cents)
                fetched = True
                amount_str = f"${initial_cash_cents / 100:,.2f}"
                logger.info("Using prod API balance: %s", amount_str)
                console.print(f"[dim]Using prod API balance: {amount_str}[/dim]")
        except Exception:
            pass

        if not fetched:
            initial_cash_cents = DEFAULT_INITIAL_BALANCE_CENTS
            logger.warning("Balance fetch failed, using default: $%s", initial_cash_cents / 100)
            console.print(f"[yellow]Balance fetch failed, using default: ${initial_cash_cents / 100:,.2f}[/yellow]")

    with get_connection(_resolve_db_path(db_path)) as conn:
        init_schema(conn)
        trader = PaperTrader(provider, conn, initial_cash_cents, cache=cache, profile=profile)
        settlement = SettlementVerifier(provider, trader, cache=cache)

        console.print(f"[bold]Paper Trading[/bold] — {strategy} ({duration}min)")
        console.print(f"  Starting cash: ${trader.get_portfolio().cash_cents / 100:.2f}")

        asyncio.run(settlement.check_settlements_on_startup())
        logger.info("Startup settlement check complete.")

        if reconcile:
            try:
                asyncio.run(settlement.reconcile_positions())
                logger.info("Reconciliation run.")
            except NotImplementedError:
                logger.warning(
                    "Reconciliation requested but not yet implemented. Skipping reconciliation."
                )
                console.print("[yellow]Reconciliation requested but not yet implemented.[/yellow]")

        start_time = time.time()
        end_time = start_time + duration * 60
        iteration = 0

        try:
            while time.time() < end_time:
                iteration += 1
                try:
                    markets = asyncio.run(market_service.list_markets(limit=5)).markets
                except Exception:
                    console.print("[yellow]Could not fetch markets, retrying...[/yellow]")
                    time.sleep(30)
                    continue

                for market in markets:
                    try:
                        orderbook = asyncio.run(market_service.get_orderbook(market.ticker))

                        prices = [int(p) for p in market.outcome_prices]
                        from traderbot.kalshi.models import Trade as _Trade

                        signals = strat.on_market_open(market, trader.get_portfolio())
                        for sig in signals:
                            result = asyncio.run(
                                trader.submit_order(
                                    ticker=sig.ticker,
                                    side=sig.direction,
                                    quantity=sig.quantity,
                                    price_cents=sig.price_cents,
                                    edge_estimate=sig.estimated_prob - 0.5 if sig.estimated_prob else 0.05,
                                )
                            )
                            if result is not None:
                                console.print(
                                    f"  [green]FILL[/green] {sig.direction.upper()} "
                                    f"{result.quantity}x {sig.ticker} @ {result.price_cents}¢"
                                )
                    except Exception:
                        continue

                elapsed_min = (time.time() - start_time) / 60
                portfolio = trader.get_portfolio()
                pnl = trader.get_pnl()
                console.print(
                    f"  [{iteration}] Cash: ${portfolio.cash_cents / 100:.2f} "
                    f"Pos: {len(portfolio.positions)} P&L: ${pnl / 100:+.2f} "
                    f"({elapsed_min:.1f}/{duration}min)"
                )
                time.sleep(60)

        except KeyboardInterrupt:
            console.print("\n[yellow]Paper trading stopped by user.[/yellow]")

    portfolio = trader.get_portfolio()
    pnl = trader.get_pnl()

    result = {
        "strategy": strategy,
        "duration_minutes": duration,
        "iterations": iteration,
        "cash_cents": portfolio.cash_cents,
        "position_count": len(portfolio.positions),
        "pnl_cents": pnl,
        "positions": [p.model_dump(mode="json") for p in portfolio.positions],
    }

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    console.print(f"\n[bold]Paper Trading Summary[/bold]")
    console.print(f"  Strategy:    {strategy}")
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
    from_date: Annotated[
        str, typer.Option("--from", help="Start date (YYYY-MM-DD)")
    ] = "2025-01-01",
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

    with get_connection(_resolve_db_path(db_path)) as conn:
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

    metric_keys = [
        "trade_count",
        "total_pnl_cents",
        "win_rate",
        "sharpe_ratio",
        "max_drawdown",
        "brier_score",
        "edge_capture",
    ]
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

    decisions = _with_db(_resolve_db_path(db_path), lambda conn: list_by_date_range(conn, start=start_dt, end=end_dt))

    executed = [d for d in decisions if d.outcome == "executed"]

    trade_count = len(executed)
    total_pnl = 0
    if trade_count > 0:
        winning = sum(1 for d in executed if d.actual_result is True or d.price > 50)
        win_rate = winning / trade_count
        for d in executed:
            if d.actual_result is None:
                continue
            if d.direction == "yes":
                if d.actual_result:
                    total_pnl += d.quantity * (100 - d.price)
                else:
                    total_pnl -= d.quantity * d.price
            elif d.direction == "no":
                if d.actual_result:
                    total_pnl -= d.quantity * (100 - d.price)
                else:
                    total_pnl += d.quantity * d.price
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
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status: active, deprecated, pending_review"),
    ] = "active",
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            help="Filter by category: MarketBehavior, RiskSignal, Timing, Strategy, Execution, FeatureRequest",
        ),
    ] = None,
    promote: Annotated[
        str | None,
        typer.Option("--promote", help="Manually promote a pattern by pattern-key"),
    ] = None,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List learned patterns and trigger promotions."""
    from traderbot.db.learnings import (
        LearningCategory,
        LearningStatus,
        find_by_pattern_key,
        get_patterns,
        init_table,
    )
    from traderbot.learning import promote_learning

    console = Console()

    def _run(conn):
        init_table(conn)

        if promote is not None:
            entries = find_by_pattern_key(conn, promote)
            active_entries = [e for e in entries if e.status != LearningStatus.DEPRECATED]
            if not active_entries:
                if json_output:
                    json_lib.dump(
                        {"error": f"No active learning found for pattern-key: {promote}"},
                        sys.stdout,
                    )
                else:
                    err_console.print(
                        f"[red]No active learning found for pattern-key:[/red] {promote}"
                    )
                raise typer.Exit(code=1)

            learning_id = active_entries[0].id
            result_path = promote_learning(conn, learning_id)
            if result_path is None:
                if json_output:
                    json_lib.dump(
                        {"error": f"Promotion failed for learning #{learning_id}"}, sys.stdout
                    )
                else:
                    err_console.print(f"[red]Promotion failed for learning[/red] #{learning_id}")
                raise typer.Exit(code=1)

            promoted_entry = {
                "learning_id": learning_id,
                "pattern_key": promote,
                "promoted_to": str(result_path),
            }
            if json_output:
                json_lib.dump(promoted_entry, sys.stdout, default=str)
            else:
                console.print(
                    f"[green]Promoted[/green] pattern [cyan]{promote}[/cyan] (learning #{learning_id})"
                )
                console.print(f"  Written to: {result_path}")
            return

        cat_enum = None
        if category is not None:
            try:
                cat_enum = LearningCategory(category)
            except ValueError:
                valid = ", ".join(c.value for c in LearningCategory)
                if json_output:
                    json_lib.dump(
                        {"error": f"Unknown category: {category}. Valid: {valid}"}, sys.stdout
                    )
                else:
                    err_console.print(f"[red]Unknown category:[/red] {category}. Valid: {valid}")
                raise typer.Exit(code=1) from None

        patterns = get_patterns(conn, category=cat_enum)

        status_enum = None
        if status is not None:
            try:
                status_enum = LearningStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in LearningStatus)
                if json_output:
                    json_lib.dump(
                        {"error": f"Unknown status: {status}. Valid: {valid}"}, sys.stdout
                    )
                else:
                    err_console.print(f"[red]Unknown status:[/red] {status}. Valid: {valid}")
                raise typer.Exit(code=1) from None

        if status_enum is not None:
            patterns = [p for p in patterns if p.status == status_enum]

        if json_output:
            json_lib.dump([p.model_dump(mode="json") for p in patterns], sys.stdout, default=str)
            return

        if not patterns:
            console.print("No learnings found.")
            return

        table = Table(title="Learned Patterns")
        table.add_column("ID", justify="right")
        table.add_column("Category", style="cyan")
        table.add_column("Summary")
        table.add_column("Confidence", justify="right")
        table.add_column("Status")
        table.add_column("Updated", style="dim")

        status_styles = {
            LearningStatus.ACTIVE: "[green]active[/green]",
            LearningStatus.DEPRECATED: "[dim]deprecated[/dim]",
            LearningStatus.PENDING_REVIEW: "[yellow]pending_review[/yellow]",
        }

        for p in patterns:
            badge = status_styles.get(p.status, p.status.value)
            updated = p.updated_at.strftime("%Y-%m-%d") if p.updated_at else "\u2014"
            table.add_row(
                str(p.id),
                p.category.value,
                p.summary[:60],
                f"{p.confidence:.0%}",
                badge,
                updated,
            )
        console.print(table)

    _with_db(_resolve_db_path(db_path), _run)


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
    """Rotate a credential (prompt for new values and update .env)."""
    from traderbot.auth import _ALL_SERVICES
    from traderbot.paths import get_data_dir

    console = Console()

    keys = _ALL_SERVICES.get(service)
    if keys is None:
        console.print(f"[red]Unknown service:[/red] {service}")
        raise typer.Exit(code=1)

    env_lines: list[str] = []
    for key in keys:
        new_val = typer.prompt(f"Enter new value for {service}.{key}", hide_input=True)
        env_key = f"{service.upper()}_{key.upper()}"
        env_lines.append(f"{env_key}={new_val}")
        console.print(f"[green]Updated[/green] {service}.{key}")

    if env_lines:
        env_path = get_data_dir() / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing = env_path.read_text() if env_path.exists() else ""
        existing_lines = [l for l in existing.splitlines() if not any(l.startswith(ek.split("=")[0]) for ek in env_lines)]
        new_content = "\n".join(existing_lines).rstrip() + "\n" + "\n".join(env_lines) + "\n"
        env_path.write_text(new_content)
        os.chmod(env_path, 0o600)
        console.print(f"[dim]Credentials updated in {env_path}[/dim]")


@auth_app.command("check")
def auth_check(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Verify KALSHI_API_KEY is configured in environment."""
    console = Console()
    key = os.getenv("KALSHI_API_KEY")

    if key and key.strip():
        ok = True
        if json_output:
            print(json_lib.dumps({"status": "ok", "key_found": True}))
        else:
            console.print("[green]OK: KALSHI_API_KEY configured[/green]")
    else:
        ok = False
        if json_output:
            print(json_lib.dumps({"status": "missing", "key_found": False}))
        else:
            console.print("[red]Missing: KALSHI_API_KEY not found in .env or environment[/red]")

    if not ok and not json_output:
        console.print(
            "[dim]Add KALSHI_API_KEY to your .env file in the data directory.[/dim]"
        )


@auth_app.command("setup-master-password")
def auth_setup_master_password() -> None:
    """Create a new master password for trade/simulate command gating."""
    from traderbot.master_password import is_setup, setup_master_password

    if is_setup():
        err_console.print("[red]Master password already configured.[/red]")
        err_console.print("Use [bold]traderbot auth change-master-password[/bold] to change it.")
        raise typer.Exit(code=1)

    password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        setup_master_password(password)
        Console().print("[green]Master password created. Session authenticated for 30 minutes.[/green]")
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@auth_app.command("change-master-password")
def auth_change_master_password() -> None:
    """Change an existing master password (requires current password)."""
    from traderbot.master_password import change_master_password, is_setup

    if not is_setup():
        err_console.print("[red]No master password configured.[/red]")
        err_console.print("Run [bold]traderbot auth setup-master-password[/bold] first.")
        raise typer.Exit(code=1)

    old_password = typer.prompt("Current master password", hide_input=True)
    new_password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        change_master_password(old_password, new_password)
        Console().print("[green]Master password changed. Session authenticated for 30 minutes.[/green]")
    except (ValueError, FileNotFoundError) as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@auth_app.command("check-master-password")
def auth_check_master_password(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Check whether master password is configured and session is active."""
    from traderbot.master_password import is_setup, session_active

    configured = is_setup()
    active = session_active() if configured else False

    if json_output:
        json_lib.dump({"configured": configured, "session_active": active}, sys.stdout)
        return

    console = Console()
    if configured:
        console.print("[green]Master password: configured[/green]")
        if active:
            console.print("[green]Session: authenticated[/green]")
        else:
            console.print("[yellow]Session: not authenticated[/yellow]")
    else:
        console.print("[red]Master password: not configured[/red]")


@auth_app.command("set-kalshi")
def auth_set_kalshi() -> None:
    """Store Kalshi credentials in OS keyring (or .env fallback)."""
    from traderbot.auth import AuthManager

    console = Console()
    api_key = typer.prompt("KALSHI_API_KEY", hide_input=True)
    private_key_pem = typer.prompt("KALSHI_PRIVATE_KEY_PEM", hide_input=True)

    mgr = AuthManager()
    api_source = mgr.set_credential("kalshi", "api_key", api_key)
    pem_source = mgr.set_credential("kalshi", "private_key_pem", private_key_pem)

    if api_source == "keyring" and pem_source == "keyring":
        console.print("[green]Kalshi credentials stored in OS keyring.[/green]")
    else:
        console.print("[yellow]Keyring unavailable; credentials stored in .env file.[/yellow]")


@auth_app.command("migrate")
def auth_migrate(
    service: Annotated[
        str | None,
        typer.Option("--service", "-s", help="Service to migrate (default: all)"),
    ] = None,
) -> None:
    """Migrate credentials from .env to OS keyring."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    result = mgr.migrate_to_keyring(service)

    if result["migrated"] == 0 and result["skipped"] == 0:
        console.print("[yellow]Keyring unavailable; migration skipped.[/yellow]")
    elif result["migrated"] > 0:
        console.print(f"[green]Migrated {result['migrated']} credential(s) to keyring.[/green]")
        if result["skipped"] > 0:
            console.print(f"[dim]Skipped {result['skipped']} (already in keyring or not found).[/dim]")
    else:
        console.print("[dim]No new credentials to migrate.[/dim]")


@auth_app.command("delete-key")
def auth_delete_key(
    service: Annotated[str, typer.Argument(help="Service name")],
    key: Annotated[str, typer.Argument(help="Key name (e.g., api_key)")],
) -> None:
    """Delete a credential from OS keyring."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    if mgr.delete_credential(service, key):
        console.print(f"[green]Deleted {service}.{key} from keyring.[/green]")
    else:
        console.print(f"[yellow]{service}.{key} not found in keyring or keyring unavailable.[/yellow]")


@auth_app.command("clear-session")
def auth_clear_session(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Clear the current authenticated session token."""
    from traderbot.master_password import clear_session

    clear_session()
    if json_output:
        json_lib.dump({"status": "session_cleared"}, sys.stdout)
    else:
        Console().print("[green]Session token cleared. Authentication will be required for next trade/simulate.[/green]")


sandbox_app = typer.Typer(
    name="sandbox",
    help="Agent filesystem sandbox: isolate workspace, lock src/ read-only.",
    rich_markup_mode="rich",
)
app.add_typer(sandbox_app, name="sandbox")


@sandbox_app.command("enter")
def sandbox_enter() -> None:
    """Enter the sandbox: lock src/ read-only, create isolated workspace."""
    from traderbot.sandbox import FilesystemSandbox

    sandbox = FilesystemSandbox()
    if sandbox.status.value == "active":
        Console().print("[yellow]Sandbox is already active.[/yellow]")
        return

    try:
        sandbox.enter()
        Console().print(f"[green]Sandbox active[/green] (workspace: {sandbox.workspace_dir})")
        if sandbox.is_available():
            Console().print(f"[dim]macOS sandbox-exec enforcement enabled[/dim]")
        else:
            Console().print(f"[dim]Fallback: POSIX chmod enforcement[/dim]")
    except Exception as e:
        err_console.print(f"[red]Failed to enter sandbox:[/red] {e}")
        raise typer.Exit(code=1)


@sandbox_app.command("exit")
def sandbox_exit(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Exit the sandbox: restore permissions, workspace retained."""
    from traderbot.sandbox import FilesystemSandbox

    sandbox = FilesystemSandbox()
    sandbox.exit_sandbox()

    if json_output:
        json_lib.dump({"status": "sandbox_exited", "workspace": str(sandbox.workspace_dir)}, sys.stdout)
    else:
        Console().print("[green]Sandbox exited. Workspace retained at[/green]")
        Console().print(f"[dim]{sandbox.workspace_dir}[/dim]")


@sandbox_app.command("status")
def sandbox_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show sandbox status: active/inactive, enforcement mode, workspace path."""
    from traderbot.sandbox import FilesystemSandbox, get_active_sandbox

    sandbox = get_active_sandbox() or FilesystemSandbox()
    source_readonly = sandbox.verify() if sandbox.status.value == "active" else False

    if json_output:
        json_lib.dump({
            "status": str(sandbox.status),
            "workspace": str(sandbox.workspace_dir),
            "src_root": str(sandbox.src_root),
            "source_readonly": source_readonly,
            "os_sandbox_available": sandbox.is_available(),
        }, sys.stdout)
        return

    console = Console()
    status_color = "green" if sandbox.status.value == "active" else "yellow"
    console.print(f"Status:       [{status_color}]{sandbox.status}[/{status_color}]")
    console.print(f"Workspace:    [dim]{sandbox.workspace_dir}[/dim]")
    console.print(f"Source root:  [dim]{sandbox.src_root}[/dim]")
    console.print(f"Src read-only: {'[green]yes[/green]' if source_readonly else '[red]no[/red]'}")
    console.print(f"OS sandbox:   {'available' if sandbox.is_available() else 'unavailable [dim](chmod fallback)[/dim]'}")


@sandbox_app.command("verify")
def sandbox_verify(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Test source tree write protection by attempting to create a probe file."""
    from traderbot.sandbox import FilesystemSandbox

    sandbox = FilesystemSandbox()
    protected = sandbox.verify()

    if json_output:
        json_lib.dump({"source_write_protected": protected}, sys.stdout)
    elif protected:
        Console().print("[green]Source tree is write-protected. Sandbox working correctly.[/green]")
    else:
        Console().print("[red]Source tree is writable. Sandbox is not active or has failed.[/red]")


@app.command()
def update(
    dev: Annotated[bool, typer.Option("--dev", help="Update from dev branch instead of main")] = False,
    check: Annotated[bool, typer.Option("--check", help="Check for update only, do not apply")] = False,
    force: Annotated[bool, typer.Option("--force", help="Pull and apply even if versions match")] = False,
) -> None:
    """Check for and apply updates. Defaults to check+apply; use --check to check only."""
    from traderbot.update_config import UpdateConfig
    from traderbot.updater import apply_update, check_for_updates, get_current_version

    console = Console()
    config = UpdateConfig.load()
    current = get_current_version()

    if check and not force:
        result = check_for_updates(force=True, check_interval_minutes=config.check_interval_minutes, dev=dev)
        if result:
            if dev:
                console.print(f"[yellow]Dev branch update available: {result['latest']}[/yellow]")
            else:
                console.print(f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]")
            console.print(f"[dim]Release: {result['url']}[/dim]")
        else:
            console.print(f"[green]Already up to date (v{current}).[/green]")
        return

    if force:
        branch_label = "dev" if dev else "main"
        console.print(f"[bold]Forcing update from {branch_label} branch...[/bold]")
        if apply_update(dev=dev):
            console.print("[green]✓ Update applied successfully.[/green]")
        else:
            console.print("[red]✗ Update failed. Check logs for details.[/red]")
        return

    result = check_for_updates(force=True, check_interval_minutes=config.check_interval_minutes, dev=dev)
    if result:
        branch_label = "dev" if dev else "main"
        console.print(f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]")
        console.print(f"[bold]Applying update from {branch_label} branch...[/bold]")
        if apply_update(dev=dev):
            console.print("[green]✓ Update applied successfully.[/green]")
        else:
            console.print("[red]✗ Update failed. Check logs for details.[/red]")
    else:
        console.print(f"[green]Already up to date (v{current}).[/green]")


@app.command("update-configure")
def update_configure(
    enabled: Annotated[bool | None, typer.Option(help="Enable/disable update checking")] = None,
    check_on_startup: Annotated[bool | None, typer.Option(help="Check on startup")] = None,
    check_interval_minutes: Annotated[int | None, typer.Option(help="Minutes between checks")] = None,
    auto_apply: Annotated[bool | None, typer.Option(help="Auto-apply updates")] = None,
) -> None:
    """Configure auto-update settings."""
    from traderbot.update_config import UpdateConfig

    console = Console()
    config = UpdateConfig.load()
    if enabled is not None:
        config.enabled = enabled
    if check_on_startup is not None:
        config.check_on_startup = check_on_startup
    if check_interval_minutes is not None:
        config.check_interval_minutes = check_interval_minutes
    if auto_apply is not None:
        config.auto_apply = auto_apply
    config.save()
    console.print(f"[green]Update config saved to {UpdateConfig.CONFIG_PATH}[/green]")
    console.print(config.model_dump_json(indent=2))


# Profile management commands
profile_app = typer.Typer(
    name="profile",
    help="Manage trading profiles for multi-agent deployment.",
    rich_markup_mode="rich",
)
app.add_typer(profile_app, name="profile")


@profile_app.command("create")
def profile_create(
    name: Annotated[str | None, typer.Argument(help="Profile name (omit for interactive mode)")] = None,
    mode: Annotated[str | None, typer.Option(help="Trading mode: paper or live")] = None,
    description: Annotated[str | None, typer.Option(help="Profile description")] = None,
    categories: Annotated[str | None, typer.Option(help="Comma-separated market categories")] = None,
    risk_multiplier: Annotated[float | None, typer.Option(help="Risk multiplier (0-1)")] = None,
    max_position_pct: Annotated[
        float | None, typer.Option(help="Max position per market %")
    ] = None,
    max_daily_loss_pct: Annotated[float | None, typer.Option(help="Max daily loss %")] = None,
    max_drawdown_pct: Annotated[float | None, typer.Option(help="Max drawdown %")] = None,
    max_open_positions: Annotated[int | None, typer.Option(help="Max open positions")] = None,
    min_liquidity: Annotated[int | None, typer.Option(help="Min liquidity threshold")] = None,
    min_edge_pct: Annotated[float | None, typer.Option(help="Min edge %")] = None,
    initial_balance_cents: Annotated[
        int | None, typer.Option(help="Initial balance in cents for paper trading (default: 10000 = $100)")
    ] = None,
) -> None:
    """Create a new trading profile. Interactive if no name given; uses flags if name provided."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.models import TradingProfile
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.risk.limits import HARD_LIMITS

    console = Console()
    registry = ProfileRegistry()

    if name is None and sys.stdin.isatty():
        _interactive_profile_create(console, registry)
        return

    has_flags = any(v is not None for v in [mode, description, categories, risk_multiplier,
                                              max_position_pct, max_daily_loss_pct, max_drawdown_pct,
                                              max_open_positions, min_liquidity, min_edge_pct, initial_balance_cents])

    if name is None:
        console.print("[dim]Use: traderbot profile create <name> [options][/dim]")
        console.print("[dim]Or run without arguments for interactive mode.[/dim]")
        raise typer.Exit(0)

    profile_mode = mode or "paper"
    if profile_mode not in ("paper", "live"):
        console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
        raise typer.Exit(1)

    enabled_categories = []
    if categories:
        try:
            enabled_categories = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None

    profile_data = {
        "name": name,
        "mode": profile_mode,
        "description": description or f"{name} trading profile",
        "enabled_categories": enabled_categories,
        "risk_multiplier": risk_multiplier or 1.0,
        "max_position_per_market_pct": max_position_pct or HARD_LIMITS["max_position_per_market_pct"],
        "max_daily_loss_pct": max_daily_loss_pct or HARD_LIMITS["max_daily_loss_pct"],
        "max_drawdown_pct": max_drawdown_pct or HARD_LIMITS["max_drawdown_pct"],
        "max_open_positions": max_open_positions or int(HARD_LIMITS["max_open_positions"]),
        "min_liquidity_threshold": min_liquidity or int(HARD_LIMITS["min_liquidity_threshold"]),
        "min_edge_pct": min_edge_pct or HARD_LIMITS["min_edge_pct"],
    }

    try:
        profile = TradingProfile(**profile_data)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    if registry.profile_exists(name):
        console.print(f"[yellow]Profile '{name}' already exists.[/yellow]")
        console.print("  [1] Overwrite the existing profile")
        console.print("  [2] Choose a different name")
        console.print("  [3] Cancel")
        choice = typer.prompt("  Select an option", default="3")
        if choice == "1":
            registry.delete_profile(name)
            registry.create_profile(profile)
            console.print(f"[green]✓[/green] Overwrote profile '{name}' in {profile_mode} mode")
        elif choice == "2":
            new_name = typer.prompt("  New profile name")
            profile_data["name"] = new_name
            try:
                profile = TradingProfile(**profile_data)
                registry.create_profile(profile)
                console.print(f"[green]✓[/green] Created profile '{new_name}' in {profile_mode} mode")
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from None
        else:
            console.print("[dim]Cancelled.[/dim]")
        return

    registry.create_profile(profile)
    console.print(f"[green]✓[/green] Created profile '{name}' in {profile_mode} mode")


def _interactive_profile_create(console: Console, registry: "ProfileRegistry") -> None:
    """Walk user through profile creation with numbered selections."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.models import TradingProfile
    from traderbot.risk.limits import HARD_LIMITS

    console.print("\n[bold]=== TraderBot Profile Setup ===[/bold]\n")

    profile_name = ""
    while not profile_name:
        profile_name = typer.prompt("Profile name")
        if not profile_name:
            console.print("[red]Profile name cannot be empty.[/red]")

    if registry.profile_exists(profile_name):
        console.print(f"[yellow]Profile '{profile_name}' already exists.[/yellow]")
        console.print("  [1] Overwrite")
        console.print("  [2] Choose a different name")
        console.print("  [3] Cancel")
        choice = typer.prompt("Select", default="3")
        if choice == "1":
            registry.delete_profile(profile_name)
        elif choice == "2":
            profile_name = typer.prompt("New profile name")
        else:
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print("\n[bold]Trading mode:[/bold]")
    console.print("  1) paper  (recommended — no real money at risk)")
    console.print("  2) live   (real money — use with caution)")
    mode_choice = typer.prompt("Choice", default="1")
    profile_mode = "live" if mode_choice == "2" else "paper"

    description = typer.prompt("Description", default=f"{profile_name} trading profile")

    console.print("\n[bold]Market categories[/bold] (comma-separated numbers, or 'a' for all):")
    cat_keys = [c.value for c in MarketCategory]
    cat_labels = [c.name.replace("_", " ").title() for c in MarketCategory]
    for i, label in enumerate(cat_labels, 1):
        console.print(f"  {i:2d}) {label}")
    console.print("   a) All categories")
    cat_input = typer.prompt("Choice", default="a")
    enabled_categories = []
    if cat_input.lower() in ("a", ""):
        enabled_categories = list(MarketCategory)
    else:
        for num in cat_input.split(","):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(cat_keys):
                cat_val = cat_keys[int(num) - 1]
                try:
                    enabled_categories.append(MarketCategory(cat_val))
                except ValueError:
                    pass

    console.print("\n[bold]Risk parameters[/bold] (press Enter for defaults)")
    rm = typer.prompt("  Risk multiplier", default="1.0")
    risk_mult = float(rm)

    mpp = typer.prompt(f"  Max position per market %", default=f"{HARD_LIMITS['max_position_per_market_pct']:.0%}")
    max_pos_pct = _parse_pct(mpp)

    mdl = typer.prompt(f"  Max daily loss %", default=f"{HARD_LIMITS['max_daily_loss_pct']:.0%}")
    max_daily = _parse_pct(mdl)

    mdd = typer.prompt(f"  Max drawdown %", default=f"{HARD_LIMITS['max_drawdown_pct']:.0%}")
    max_drawdown = _parse_pct(mdd)

    mop = typer.prompt(f"  Max open positions", default=str(int(HARD_LIMITS["max_open_positions"])))
    max_open = int(mop)

    ml = typer.prompt(f"  Min liquidity threshold (cents)", default=str(int(HARD_LIMITS["min_liquidity_threshold"])))
    min_liq = int(ml)

    me = typer.prompt(f"  Min edge %", default=f"{HARD_LIMITS['min_edge_pct']:.0%}")
    min_edge = _parse_pct(me)

    # Paper trading balance
    if profile_mode == "paper":
        console.print("\n[bold]Paper trading initial balance[/bold]")
        console.print("[dim]  This is the starting balance for simulated trading (in cents).[/dim]")
        console.print("[dim]  $100 = 10000 cents, $1000 = 100000 cents[/dim]")
        ib = typer.prompt("  Initial balance (cents)", default="10000")
        initial_balance = int(ib) if ib.isdigit() else 10_000
    else:
        initial_balance = None

    profile_data = {
        "name": profile_name,
        "mode": profile_mode,
        "description": description,
        "enabled_categories": enabled_categories,
        "risk_multiplier": risk_mult,
        "max_position_per_market_pct": max_pos_pct or HARD_LIMITS["max_position_per_market_pct"],
        "max_daily_loss_pct": max_daily or HARD_LIMITS["max_daily_loss_pct"],
        "max_drawdown_pct": max_drawdown or HARD_LIMITS["max_drawdown_pct"],
        "max_open_positions": max_open or int(HARD_LIMITS["max_open_positions"]),
        "min_liquidity_threshold": min_liq or int(HARD_LIMITS["min_liquidity_threshold"]),
        "min_edge_pct": min_edge or HARD_LIMITS["min_edge_pct"],
    }

    if initial_balance is not None:
        profile_data["initial_balance_cents"] = initial_balance

    try:
        profile = TradingProfile(**profile_data)
        registry.create_profile(profile)
        console.print(f"\n[green]✓[/green] Created profile '{profile_name}' in {profile_mode} mode")
        cat_str = ", ".join(str(c.value) for c in enabled_categories) if enabled_categories else "all"
        console.print(f"  Mode: {profile_mode}  Categories: {cat_str}")
    except ValueError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def _parse_pct(value: str) -> float | None:
    """Parse a percentage string like '5%' or '0.05' into a float ratio."""
    try:
        cleaned = value.strip().rstrip("%")
        if "%" in value:
            return float(cleaned) / 100
        return float(cleaned)
    except (ValueError, TypeError):
        return None


@profile_app.command("list")
def profile_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all trading profiles."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()
    profile_names = registry.list_profiles()

    if not profile_names:
        if not json_output:
            console.print("[yellow]No profiles found[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        # Get full profile data for JSON output
        profiles = []
        for name in profile_names:
            profile = registry.get_profile(name)
            if profile:
                profiles.append(profile.model_dump(mode="json"))
        print(json_lib.dumps(profiles, indent=2))
    else:
        # Table output
        table = Table(title="Trading Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Mode", style="magenta")
        table.add_column("Description")
        table.add_column("Risk Multiplier", justify="right")

        for name in profile_names:
            profile = registry.get_profile(name)
            if profile:
                table.add_row(
                    profile.name,
                    profile.mode,
                    profile.description,
                    f"{profile.risk_multiplier:.2f}",
                )

        console.print(table)


@profile_app.command("show")
def profile_show(
    name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show details for a specific profile."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()
    profile = registry.get_profile(name)

    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    if json_output:
        print(json_lib.dumps(profile.model_dump(mode="json"), indent=2))
    else:
        console.print(f"\n[bold cyan]Profile: {profile.name}[/bold cyan]")
        console.print(f"Mode: {profile.mode}")
        console.print(f"Description: {profile.description}")
        console.print("\n[bold]Risk Parameters:[/bold]")
        console.print(f"  Risk Multiplier: {profile.risk_multiplier}")
        console.print(f"  Max Position per Market: {profile.max_position_per_market_pct}%")
        console.print(f"  Max Daily Loss: {profile.max_daily_loss_pct}%")
        console.print(f"  Max Drawdown: {profile.max_drawdown_pct}%")
        console.print(f"  Max Open Positions: {profile.max_open_positions}")
        console.print(f"  Min Liquidity: {profile.min_liquidity_threshold}")
        console.print(f"  Min Edge: {profile.min_edge_pct}%")

        if profile.enabled_categories:
            console.print("\n[bold]Enabled Categories:[/bold]")
            for cat in profile.enabled_categories:
                console.print(f"  • {cat.value}")
        else:
            console.print("\n[bold]Enabled Categories:[/bold] All")


@profile_app.command("delete")
def profile_delete(
    name: str,
    keep_data: Annotated[bool, typer.Option(help="Keep data directories")] = True,
) -> None:
    """Delete a trading profile."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    if not registry.profile_exists(name):
        console.print(f"[yellow]Warning:[/yellow] Profile '{name}' does not exist")
        return

    registry.delete_profile(name, keep_data=keep_data)
    console.print(f"[green]✓[/green] Deleted profile '{name}'")

    if not keep_data:
        console.print("[yellow]Note:[/yellow] Data directories were also deleted")


def _resolve_agent_path(agent_id: str) -> Path | None:
    """Resolve agent path from openclaw.json config, then fall back to filesystem heuristics.

    Source of truth is always openclaw.json ``agents.list``.  This handles every
    combination OpenClaw supports: explicit workspace, inherited default workspace,
    agentDir-only configs, and default-flagged agents.
    """
    from pathlib import Path
    import json as _json

    # 1. Read openclaw.json — authoritative agent definitions
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            config = _json.loads(config_path.read_text())
            section = config.get("agents", {})
            defaults_ws = section.get("defaults", {}).get("workspace", "")

            for entry in section.get("list", []):
                if not isinstance(entry, dict):
                    continue
                if entry.get("id") != agent_id:
                    continue

                ws = entry.get("workspace") or defaults_ws
                if ws:
                    p = Path(ws).expanduser()
                    if p.is_dir() and ((p / "IDENTITY.md").exists() or (p / "TOOLS.md").exists()):
                        return p

                ad = entry.get("agentDir", "")
                if ad:
                    p = Path(ad).expanduser()
                    if p.is_dir() and ((p / "IDENTITY.md").exists() or (p / "TOOLS.md").exists()):
                        return p

                # Return existing dir even without markers — propagate_workspace_files creates them
                if ws:
                    p = Path(ws).expanduser()
                    if p.is_dir():
                        return p

                break
        except (_json.JSONDecodeError, OSError):
            pass

    # 2. Fallback: filesystem heuristics for agents not in config
    candidates = [
        Path.home() / ".openclaw" / f"workspace-{agent_id}",
        Path.home() / ".openclaw" / "workspace" / agent_id,
        Path.home() / ".openclaw" / "agents" / agent_id,
        Path.cwd() / ".openclaw" / "workspace" / agent_id,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and ((candidate / "IDENTITY.md").exists() or (candidate / "TOOLS.md").exists()):
            return candidate
    return None


@profile_app.command("assign")
def profile_assign(
    profile_name: Annotated[str | None, typer.Argument(help="Profile name")] = None,
    agent_id: Annotated[str | None, typer.Argument(help="Agent ID or name")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Auto-apply all workspace templates without prompting")] = False,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite workspace files instead of merging")] = False,
    force: Annotated[bool, typer.Option("--force", help="Reassign token even if profile already has one")] = False,
) -> None:
    """Assign a token to an agent for profile access.

    Called without arguments, enters interactive mode: select a profile, then an agent, then choose merge or overwrite.
    Called with profile_name and agent_id, applies directly (non-interactive with --yes).
    """
    from traderbot.profiles.injection import inject_token, propagate_workspace_files
    from traderbot.profiles.injection_strategies import set_skip_prompts
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.profiles.tokens import assign_token, generate_token

    if yes:
        set_skip_prompts(True)

    console = Console()
    registry = ProfileRegistry()

    if profile_name is None or agent_id is None:
        if not sys.stdin.isatty():
            console.print("[red]Error:[/red] profile_name and agent_id required in non-interactive mode")
            raise typer.Exit(1)
        _interactive_assign(console, registry, overwrite=overwrite)
        return

    _do_assign(profile_name, agent_id, overwrite=overwrite, force=force, console=console, script_output=yes)


def _do_assign(
    profile_name: str,
    agent_id: str,
    overwrite: bool = False,
    force: bool = False,
    console: Console | None = None,
    script_output: bool = False,
) -> None:
    from traderbot.profiles.injection import inject_token, propagate_workspace_files
    from traderbot.profiles.injection_strategies import set_skip_prompts
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.profiles.tokens import TokenAlreadyAssignedError, assign_token, generate_token

    if console is None:
        console = Console()

    registry = ProfileRegistry()

    if not registry.profile_exists(profile_name):
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    profile = registry.get_profile(profile_name)

    try:
        token = generate_token()
        assign_token(profile_name, agent_id, token, force=force)
        console.print(
            f"[green]✓[/green] Assigned token to profile '{profile_name}' for agent '{agent_id}'"
        )
        if script_output:
            console.print(f"Token: [bold]{_mask_token(token)}[/bold]")
            print(f"RAW_TOKEN:{token}")

        try:
            agent_path = _resolve_agent_path(agent_id)
            if not agent_path or not agent_path.exists():
                console.print(
                    f"[yellow]Warning:[/yellow] Agent directory not found for '{agent_id}'"
                )
                console.print("Token assigned but not injected into TOOLS.md")
            else:
                propagate_workspace_files(profile, agent_path, overwrite=overwrite)
                inject_token(str(agent_path), token)
                mode = "overwritten" if overwrite else "merged"
                console.print(
                    f"[green]✓[/green] Workspace files {mode} and token injected into {agent_id}/"
                )

                # Configure OpenClaw features for this agent
                try:
                    from traderbot.profiles.openclaw_config import (
                        enable_session_memory_hook,
                        ensure_agent_bootstrap_hook,
                    )

                    enable_session_memory_hook()
                    ensure_agent_bootstrap_hook()
                    console.print(
                        "[green]✓[/green] OpenClaw features configured (hooks)"
                    )

                    # Install news ingestion timer
                    try:
                        news_result = _install_news_ingest_timer(
                            agent_user=agent_id,
                            console=console,
                        )
                        if news_result.get("registered"):
                            console.print(
                                "[green]✓[/green] News ingestion timer installed"
                            )
                    except Exception as ni_err:
                        logger.warning("News ingest timer install failed: %s", ni_err)
                        console.print(
                            "[yellow]Warning:[/yellow] News ingestion timer could not be installed "
                            f"({ni_err})"
                        )
                except Exception as oc_err:
                    logger.warning("OpenClaw feature setup failed: %s", oc_err)
                    console.print(
                        "[yellow]Warning:[/yellow] OpenClaw features partially configured: "
                        f"{oc_err}"
                    )
        except FileNotFoundError:
            console.print("[yellow]Warning:[/yellow] Agent directory not found")
            console.print("Token assigned but not injected into TOOLS.md")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Failed to inject token into TOOLS.md: {e}")
            console.print("Token assigned but not injected")
    except TokenAlreadyAssignedError:
        console.print(f"[yellow]Profile '{profile_name}' already has a token assigned.[/yellow]")
        console.print("Use [bold]traderbot profile revoke[/bold] first, or re-run with [bold]--force[/bold] to reassign.")
        raise typer.Exit(1) from None


def _interactive_assign(console: Console, registry: "ProfileRegistry", overwrite: bool = False) -> None:
    from traderbot.profiles.discovery import discover_agents

    profiles = registry.list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found.[/yellow] Create one with: traderbot profile create")
        return

    console.print("\n[bold]Select a profile:[/bold]")
    for i, p_name in enumerate(profiles, 1):
        profile = registry.get_profile(p_name)
        mode = f" [{profile.mode}]" if profile else ""
        desc = f" — {profile.description}" if profile and profile.description else ""
        console.print(f"  {i}. {p_name}{mode}{desc}")

    try:
        choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if choice < 1 or choice > len(profiles):
        console.print("[red]Invalid selection[/red]")
        return

    profile_name = profiles[choice - 1]

    agents = discover_agents()
    if not agents:
        console.print("[yellow]No agents found. Run 'traderbot profile discover-agents' to scan.[/yellow]")
        console.print(f"\n[dim]To assign manually: traderbot profile assign {profile_name} <agent_id>[/dim]")
        return

    console.print("\n[bold]Select an agent:[/bold]")
    for i, agent in enumerate(agents, 1):
        console.print(f"  {i}. {agent['name']} ({agent['agent_id']}) — {agent['path']}")

    try:
        agent_choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if agent_choice < 1 or agent_choice > len(agents):
        console.print("[red]Invalid selection[/red]")
        return

    agent = agents[agent_choice - 1]
    agent_id = agent["agent_id"]

    console.print("\n[bold]Workspace file mode:[/bold]")
    console.print("  1. Merge — backup existing files, then merge TraderBot templates (recommended)")
    console.print("  2. Overwrite — replace workspace files with TraderBot templates")

    try:
        ws_choice = typer.prompt("Select [1]", type=int)
    except (ValueError, KeyboardInterrupt):
        ws_choice = 1

    overwrite = ws_choice == 2

    # Paper trading balance prompt
    profile = registry.get_profile(profile_name)
    if profile and profile.mode == "paper" and profile.initial_balance_cents is None:
        console.print(f"\n[bold]Paper trading initial balance[/bold]")
        console.print("[dim]  This profile has no initial balance set. Without it, paper trading cannot start.[/dim]")
        console.print("[dim]  $100 = 10000 cents, $1000 = 100000 cents[/dim]")
        ib = typer.prompt("  Initial balance (cents)", default="10000")
        initial_balance = int(ib) if ib.isdigit() else 10_000
        from traderbot.profiles.registry import ProfileRegistry as PR2
        reg2 = PR2()
        reg2.update_profile(profile_name, {"initial_balance_cents": initial_balance})
        console.print(f"[green]✓[/green] Set initial balance to ${initial_balance / 100:,.2f}")

    _do_assign(profile_name, agent_id, overwrite=overwrite, force=True, console=console)


@profile_app.command("revoke")
def profile_revoke(
    profile_name: str,
) -> None:
    """Revoke token assignment for a profile."""

    from traderbot.profiles.injection import remove_token_from_tools
    from traderbot.profiles.tokens import get_profile_token, resolve_token, revoke_token

    console = Console()

    # Get token for profile
    token = get_profile_token(profile_name)
    if token is None:
        console.print(f"[yellow]Warning:[/yellow] No token assigned to profile '{profile_name}'")
        return

    # Get agent ID before revoking
    resolved = resolve_token(token)
    agent_id = resolved[1] if resolved else None

    # Revoke token
    revoke_token(token)
    console.print(f"[green]✓[/green] Revoked token for profile '{profile_name}'")

    # Remove token from agent's TOOLS.md
    if agent_id:
        try:
            agent_path = _resolve_agent_path(agent_id)
            if agent_path and agent_path.exists():
                remove_token_from_tools(str(agent_path))
                console.print(f"[green]✓[/green] Token removed from {agent_id}/TOOLS.md")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Failed to remove token from TOOLS.md: {e}")


@profile_app.command("assignments")
def profile_assignments(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all token assignments."""
    from traderbot.profiles.tokens import list_assignments

    console = Console()
    assignments = list_assignments()

    if not assignments:
        if not json_output:
            console.print("[yellow]No token assignments found[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        masked_assignments = [
            {**a, "token": _mask_token(a["token"])} for a in assignments
        ]
        print(json_lib.dumps(masked_assignments, indent=2))
    else:
        table = Table(title="Token Assignments")
        table.add_column("Profile", style="cyan")
        table.add_column("Agent ID", style="magenta")
        table.add_column("Token", style="yellow")
        table.add_column("Created At")

        for assignment in assignments:
            table.add_row(
                assignment["profile"],
                assignment["agent"],
                _mask_token(assignment["token"]),
                assignment["created_at"],
            )

        console.print(table)


@profile_app.command("update")
def profile_update(
    name: Annotated[str | None, typer.Argument(help="Profile name to update")] = None,
    mode: Annotated[str | None, typer.Option(help="Trading mode: paper or live")] = None,
    description: Annotated[str | None, typer.Option(help="Profile description")] = None,
    categories: Annotated[
        str | None, typer.Option(help="Comma-separated market categories")
    ] = None,
    risk_multiplier: Annotated[float | None, typer.Option(help="Risk multiplier (0-1)")] = None,
    max_position_pct: Annotated[
        float | None, typer.Option(help="Max position per market %")
    ] = None,
    max_daily_loss_pct: Annotated[float | None, typer.Option(help="Max daily loss %")] = None,
    max_drawdown_pct: Annotated[float | None, typer.Option(help="Max drawdown %")] = None,
    max_open_positions: Annotated[int | None, typer.Option(help="Max open positions")] = None,
    min_liquidity: Annotated[int | None, typer.Option(help="Min liquidity threshold")] = None,
    min_edge_pct: Annotated[float | None, typer.Option(help="Min edge %")] = None,
    initial_balance_cents: Annotated[
        int | None, typer.Option(help="Initial balance in cents for paper trading (default: 10000 = $100)")
    ] = None,
) -> None:
    """Update specific fields of an existing profile.

    Called without a name, enters interactive mode: select a profile, then choose
    to edit, delete, or assign an agent to it. Called with a name and flags, applies
    the flags directly (non-interactive).
    """
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    has_flags = any(v is not None for v in [mode, description, categories, risk_multiplier, max_position_pct, max_daily_loss_pct, max_drawdown_pct, max_open_positions, min_liquidity, min_edge_pct, initial_balance_cents])

    if name is None:
        profiles = registry.list_profiles()
        if not profiles:
            console.print("[yellow]No profiles found.[/yellow] Create one with: traderbot profile create <name>")
            raise typer.Exit(0)

        if not has_flags and sys.stdin.isatty():
            name = _interactive_profile_select(profiles, console)
            if name is None:
                raise typer.Exit(0)
            _interactive_profile_action(name, console, registry)
            return

        console.print("[bold]Available profiles:[/bold]")
        for p_name in profiles:
            console.print(f"  • {p_name}")
        console.print("\n[dim]Use: traderbot profile update <name> [options] to update a profile[/dim]")
        raise typer.Exit(0)

    _apply_profile_update(name, mode, description, categories, risk_multiplier,
                          max_position_pct, max_daily_loss_pct, max_drawdown_pct,
                          max_open_positions, min_liquidity, min_edge_pct,
                          initial_balance_cents=initial_balance_cents,
                          console=console, registry=registry)


def _interactive_profile_select(profiles: list[str], console: Console) -> str | None:
    from traderbot.profiles.registry import ProfileRegistry

    registry = ProfileRegistry()
    console.print("\n[bold]Select a profile:[/bold]")
    for i, p_name in enumerate(profiles, 1):
        profile = registry.get_profile(p_name)
        desc = f" — {profile.description}" if profile and profile.description else ""
        mode = f" [{profile.mode}]" if profile else ""
        console.print(f"  {i}. {p_name}{mode}{desc}")

    try:
        choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return None

    if choice < 1 or choice > len(profiles):
        console.print("[red]Invalid selection[/red]")
        return None

    return profiles[choice - 1]


def _interactive_profile_action(name: str, console: Console, registry: "ProfileRegistry") -> None:
    profile = registry.get_profile(name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    console.print(f"\n[bold]Profile: {name}[/bold] ({profile.mode})")
    console.print(f"  Description:    {profile.description}")
    console.print(f"  Categories:     {', '.join(str(c.value) for c in profile.enabled_categories) if profile.enabled_categories else 'all'}")
    console.print(f"  Risk multiplier:{profile.risk_multiplier:.1%}")
    console.print(f"  Max position:   {profile.max_position_per_market_pct:.1%}")
    console.print(f"  Max daily loss:  {profile.max_daily_loss_pct:.1%}")
    console.print(f"  Max drawdown:    {profile.max_drawdown_pct:.1%}")
    console.print(f"  Max open pos:   {profile.max_open_positions}")
    console.print(f"  Min liquidity:   {profile.min_liquidity_threshold}")
    console.print(f"  Min edge:        {profile.min_edge_pct:.1%}")

    console.print("\n[bold]Actions:[/bold]")
    console.print("  1. Edit profile")
    console.print("  2. Delete profile")
    console.print("  3. Assign agent")
    console.print("  4. Exit")

    try:
        action = typer.prompt("Choose action", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if action == 1:
        _interactive_edit_profile(name, profile, console, registry)
    elif action == 2:
        _interactive_delete_profile(name, console, registry)
    elif action == 3:
        _interactive_assign_agent(name, console, registry)


def _interactive_edit_profile(name: str, profile: "TradingProfile", console: Console, registry: "ProfileRegistry") -> None:
    from traderbot.kalshi.models import MarketCategory

    update_kwargs: dict = {}

    console.print(f"\n[bold]Editing profile '{name}'[/bold] (press Enter to keep current value)")

    new_mode = typer.prompt(f"  Mode [{profile.mode}]", default="", show_default=False)
    if new_mode:
        if new_mode not in ("paper", "live"):
            console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
            return
        update_kwargs["mode"] = new_mode

    new_desc = typer.prompt(f"  Description", default=profile.description)
    if new_desc != profile.description:
        update_kwargs["description"] = new_desc

    current_cats = ", ".join(str(c.value) for c in profile.enabled_categories) if profile.enabled_categories else ""
    new_cats = typer.prompt(f"  Categories [{current_cats or 'all'}]", default="", show_default=False)
    if new_cats:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in new_cats.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            return

    new_rm = typer.prompt(f"  Risk multiplier [{profile.risk_multiplier}]", default="", show_default=False)
    if new_rm:
        try:
            update_kwargs["risk_multiplier"] = float(new_rm)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_mp = typer.prompt(f"  Max position per market % [{profile.max_position_per_market_pct}]", default="", show_default=False)
    if new_mp:
        try:
            update_kwargs["max_position_per_market_pct"] = float(new_mp)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_ml = typer.prompt(f"  Max daily loss % [{profile.max_daily_loss_pct}]", default="", show_default=False)
    if new_ml:
        try:
            update_kwargs["max_daily_loss_pct"] = float(new_ml)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_md = typer.prompt(f"  Max drawdown % [{profile.max_drawdown_pct}]", default="", show_default=False)
    if new_md:
        try:
            update_kwargs["max_drawdown_pct"] = float(new_md)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_op = typer.prompt(f"  Max open positions [{profile.max_open_positions}]", default="", show_default=False)
    if new_op:
        try:
            update_kwargs["max_open_positions"] = int(new_op)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_lq = typer.prompt(f"  Min liquidity threshold [{profile.min_liquidity_threshold}]", default="", show_default=False)
    if new_lq:
        try:
            update_kwargs["min_liquidity_threshold"] = int(new_lq)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_edge = typer.prompt(f"  Min edge % [{profile.min_edge_pct}]", default="", show_default=False)
    if new_edge:
        try:
            update_kwargs["min_edge_pct"] = float(new_edge)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    if not update_kwargs:
        console.print("[yellow]No changes made[/yellow]")
        return

    try:
        registry.update_profile(name, **update_kwargs)
        console.print(f"[green]✓[/green] Updated profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")


def _interactive_delete_profile(name: str, console: Console, registry: "ProfileRegistry") -> None:
    confirm = typer.prompt(f"Delete profile '{name}'? Type 'yes' to confirm")
    if confirm.lower() != "yes":
        console.print("[yellow]Cancelled[/yellow]")
        return

    try:
        registry.delete_profile(name)
        console.print(f"[green]✓[/green] Deleted profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")


def _interactive_assign_agent(name: str, console: Console, registry: "ProfileRegistry") -> None:
    from traderbot.profiles.discovery import discover_agents
    from traderbot.profiles.injection import inject_token, propagate_workspace_files
    from traderbot.profiles.tokens import TokenAlreadyAssignedError, assign_token, generate_token

    agents = discover_agents()
    if not agents:
        console.print("[yellow]No agents found. Run 'traderbot profile discover-agents' to scan.[/yellow]")
        return

    console.print("\n[bold]Select an agent:[/bold]")
    for i, agent in enumerate(agents, 1):
        console.print(f"  {i}. {agent['name']} ({agent['agent_id']}) — {agent['path']}")

    try:
        choice = typer.prompt("Select agent number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if choice < 1 or choice > len(agents):
        console.print("[red]Invalid selection[/red]")
        return

    agent = agents[choice - 1]
    agent_id = agent["agent_id"]

    console.print("\n[bold]Workspace file mode:[/bold]")
    console.print("  1. Merge — backup existing files, then merge TraderBot templates (recommended)")
    console.print("  2. Overwrite — replace workspace files with TraderBot templates")

    try:
        ws_choice = typer.prompt("Select [1]", type=int)
    except (ValueError, KeyboardInterrupt):
        ws_choice = 1

    overwrite = ws_choice == 2

    profile = registry.get_profile(name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        return

    try:
        token = generate_token()
        assign_token(name, agent_id, token, force=True)
    except TokenAlreadyAssignedError:
        console.print(f"[yellow]Profile '{name}' already has a token assigned.[/yellow]")
        console.print("Use [bold]traderbot profile revoke[/bold] first, or re-run with [bold]--force[/bold] to reassign.")
        return

    console.print(f"[green]✓[/green] Assigned token to profile '{name}' for agent '{agent_id}'")

    agent_path = _resolve_agent_path(agent_id)
    if agent_path and agent_path.exists():
        propagate_workspace_files(profile, agent_path, overwrite=overwrite)
        inject_token(str(agent_path), token)
        mode = "overwritten" if overwrite else "merged"
        console.print(f"[green]✓[/green] Workspace files {mode} and token injected into {agent_id}/")
    else:
        console.print(f"[yellow]Warning:[/yellow] Agent directory not found for '{agent_id}'")
        console.print("Token assigned but not injected into workspace")


def _apply_profile_update(
    name: str,
    mode: str | None,
    description: str | None,
    categories: str | None,
    risk_multiplier: float | None,
    max_position_pct: float | None,
    max_daily_loss_pct: float | None,
    max_drawdown_pct: float | None,
    max_open_positions: int | None,
    min_liquidity: int | None,
    min_edge_pct: float | None,
    initial_balance_cents: int | None = None,
    console: Console = None,
    registry: "ProfileRegistry" = None,
) -> None:
    from traderbot.kalshi.models import MarketCategory

    if not registry.profile_exists(name):
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    update_kwargs: dict = {}

    if mode is not None:
        if mode not in ("paper", "live"):
            console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
            raise typer.Exit(1)
        update_kwargs["mode"] = mode

    if description is not None:
        update_kwargs["description"] = description

    if categories is not None:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None
        update_kwargs["mode"] = mode

    if description is not None:
        update_kwargs["description"] = description

    if categories is not None:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None

    if risk_multiplier is not None:
        update_kwargs["risk_multiplier"] = risk_multiplier

    if max_position_pct is not None:
        update_kwargs["max_position_per_market_pct"] = max_position_pct

    if max_daily_loss_pct is not None:
        update_kwargs["max_daily_loss_pct"] = max_daily_loss_pct

    if max_drawdown_pct is not None:
        update_kwargs["max_drawdown_pct"] = max_drawdown_pct

    if max_open_positions is not None:
        update_kwargs["max_open_positions"] = max_open_positions

    if min_liquidity is not None:
        update_kwargs["min_liquidity_threshold"] = min_liquidity

    if min_edge_pct is not None:
        update_kwargs["min_edge_pct"] = min_edge_pct

    if initial_balance_cents is not None:
        update_kwargs["initial_balance_cents"] = initial_balance_cents

    if not update_kwargs:
        console.print("[yellow]Warning:[/yellow] No fields to update")
        return

    try:
        registry.update_profile(name, **update_kwargs)
        console.print(f"[green]✓[/green] Updated profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@profile_app.command("discover-agents")
def profile_discover_agents(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Scan OpenClaw workspaces for available agents."""
    from traderbot.profiles.discovery import discover_agents

    console = Console()
    agents = discover_agents()

    if not agents:
        if not json_output:
            console.print("[yellow]No agents found in .openclaw/workspace[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        print(json_lib.dumps(agents, indent=2))
    else:
        table = Table(title="Discovered Agents")
        table.add_column("Agent ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Path", style="yellow")

        for agent in agents:
            table.add_row(
                agent["agent_id"],
                agent["name"],
                agent["path"],
            )

        console.print(table)


@profile_app.command("auth")
def profile_auth(
    profile_name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show configured credentials for a profile (from environment variables)."""
    from traderbot.profiles.auth import ProfileAuthStore
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    profile = registry.get_profile(profile_name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    auth_store = ProfileAuthStore(profile)
    known_services = ["kalshi", "voyage", "newsapi", "twitter", "reddit"]
    found_services: list[str] = []
    for svc in known_services:
        if auth_store.has_credentials(svc):
            found_services.append(svc)

    if not found_services:
        if not json_output:
            console.print(
                f"[yellow]No credentials configured for profile '{profile_name}'[/yellow]"
            )
        else:
            print("[]")
        return

    if json_output:
        creds_list = []
        for svc in found_services:
            creds = auth_store.get_credentials(svc)
            if creds:
                creds_list.append(
                    {
                        "service": svc,
                        "key": _mask_token(creds[0]),
                    }
                )
        print(json_lib.dumps(creds_list, indent=2))
    else:
        table = Table(title=f"Credentials for Profile '{profile_name}'")
        table.add_column("Service", style="cyan")
        table.add_column("Key", style="yellow")

        for svc in found_services:
            creds = auth_store.get_credentials(svc)
            if creds:
                masked_key = creds[0][:8] + "..." if len(creds[0]) > 8 else "***"
                table.add_row(svc, masked_key)

        console.print(table)



def _run_openclaw_cron_add(args: list[str]) -> tuple[int, str]:
    """Run `openclaw cron add` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "add", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron add timed out"


def _write_heartbeat_config(agent_id: str, heartbeat_interval: str) -> bool:
    """Write heartbeat config for an agent into ~/.openclaw/openclaw.json."""
    import json as _json

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    config: dict = {}

    if config_path.exists():
        try:
            config = _json.loads(config_path.read_text())
        except (ValueError, OSError):
            config = {}

    agents = config.setdefault("agents", {})
    agent_list = agents.setdefault("list", [])

    for entry in agent_list:
        if entry.get("id") == agent_id:
            entry["heartbeat"] = {
                "every": heartbeat_interval,
                "lightContext": True,
                "isolatedSession": True,
            }
            break
    else:
        agent_list.append({
            "id": agent_id,
            "heartbeat": {
                "every": heartbeat_interval,
                "lightContext": True,
                "isolatedSession": True,
            },
        })

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_json.dumps(config, indent=2) + "\n")
    return True


def _install_news_ingest_timer(
    agent_user: str,
    interval_minutes: int = 30,
    console: object | None = None,
) -> dict[str, str | bool]:
    """Install systemd timer for offline news ingestion.

    Returns dict with 'registered' key and optional 'error'.
    No-op on non-Linux or non-systemd systems.
    """
    import subprocess

    result: dict[str, str | bool] = {
        "name": "news_ingest_timer",
        "registered": False,
    }

    if sys.platform == "win32":
        return _install_news_ingest_timer_windows(agent_user, interval_minutes, console, result)
    if sys.platform != "linux":
        return result
    if not _systemd_available():
        return result

    repo_root = Path(__file__).resolve().parent.parent.parent
    service_template = repo_root / "install" / "services" / "traderbot-news-ingest@.service"
    timer_template = repo_root / "install" / "services" / "traderbot-news-ingest@.timer"

    if not service_template.exists() or not timer_template.exists():
        result["error"] = "service/timer template not found"
        if console:
            console.print(f"  [red]✗[/red] news_ingest_timer: template not found at {service_template}")
        return result

    import getpass as _gp

    user = agent_user or _gp.getuser()
    home = Path(f"/home/{user}")

    svc_content = service_template.read_text()
    svc_content = svc_content.replace("User=%i", f"User={user}")
    svc_content = svc_content.replace("/home/%i/", f"/home/{user}/")
    svc_content = svc_content.replace("%h/.traderbot/.env", f"{home}/.traderbot/.env")

    tmp_svc = Path(f"/tmp/traderbot-news-ingest@{user}.service")
    tmp_svc.write_text(svc_content)

    tmr_content = timer_template.read_text()
    tmr_content = tmr_content.replace("(%i)", f"({user})")
    tmr_content = tmr_content.replace("@<user>", f"@{user}")
    tmp_tmr = Path(f"/tmp/traderbot-news-ingest@{user}.timer")
    tmp_tmr.write_text(tmr_content)

    try:
        subprocess.run([_SUDO, "cp", str(tmp_svc), f"/etc/systemd/system/traderbot-news-ingest@{user}.service"], check=True, capture_output=True)
        subprocess.run([_SUDO, "cp", str(tmp_tmr), f"/etc/systemd/system/traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "enable", f"traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "start", f"traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
        result["registered"] = True
    except subprocess.CalledProcessError as exc:
        result["error"] = str(exc.stderr.decode() if exc.stderr else exc)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        tmp_svc.unlink(missing_ok=True)
        tmp_tmr.unlink(missing_ok=True)

    return result


def _install_news_ingest_timer_windows(
    agent_user: str,
    interval_minutes: int,
    console: object | None,
    result: dict[str, str | bool],
) -> dict[str, str | bool]:
    import getpass as _gp

    from traderbot.windows_service import (
        install_news_ingest_task,
        schtasks_available,
    )

    if not schtasks_available():
        result["error"] = "schtasks.exe not available"
        return result

    user = agent_user or _gp.getuser()
    try:
        success = install_news_ingest_task(user=user, interval_minutes=interval_minutes)
        if success:
            result["registered"] = True
        else:
            result["error"] = "schtasks create returned non-zero"
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _systemd_available() -> bool:
    """Check if systemd is available on this system."""
    import subprocess
    try:
        subprocess.run([_SYSTEMCTL, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _remove_news_ingest_timer(
    agent_user: str,
    console: object | None = None,
) -> None:
    import subprocess

    if sys.platform == "win32":
        from traderbot.windows_service import uninstall_news_ingest_task
        try:
            uninstall_news_ingest_task(agent_user)
        except Exception:
            pass
        return
    if sys.platform != "linux":
        return
    if not _systemd_available():
        return

    try:
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "stop", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "disable", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.service"],
            check=True, capture_output=True,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.timer"],
            check=True, capture_output=True,
        )
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True, timeout=15)
    except Exception:
        pass


@cron_app.command("setup")
def cron_setup(
    agent_id: Annotated[
        str,
        typer.Option("--agent", help="OpenClaw agent ID to register loops for"),
    ],
    channel: Annotated[
        str | None,
        typer.Option("--channel", help="Delivery channel for announce (e.g. telegram, slack, whatsapp)"),
    ] = None,
    to: Annotated[
        str | None,
        typer.Option("--to", help="Delivery target (chat ID for telegram, E.164 phone for whatsapp)"),
    ] = None,
    heartbeat_interval: Annotated[
        str,
        typer.Option("--heartbeat-every", help="Heartbeat interval (e.g. 30m, 1h, 6h)"),
    ] = "6h",
    news_ingest_interval: Annotated[
        int | None,
        typer.Option("--news-ingest-every", help="News ingestion interval in minutes. 0=disable, omit=skip"),
    ] = None,
    skip_heartbeat_config: Annotated[
        bool,
        typer.Option("--skip-heartbeat-config", help="Skip writing heartbeat config to openclaw.json"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be registered without executing"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Register decision, heartbeat, and news cron loops with OpenClaw for an agent."""
    from traderbot.cron_loops import DecisionLoopPayload, HeartbeatLoopPayload, NewsLoopPayload

    console = Console()

    if bool(channel) ^ bool(to):
        console.print("[red]Error:[/red] Both --channel and --to are required when either is provided.")
        raise typer.Exit(1)

    results: list[dict[str, str | bool]] = []

    if not dry_run:
        if not shutil.which("openclaw"):
            console.print("[red]Error:[/red] openclaw CLI not found in PATH")
            console.print("Install OpenClaw first: https://github.com/openclaw/openclaw")
            raise typer.Exit(1)

        # channel/to validated by XOR check above — either both provided or neither
        bool(channel and to)  # implicit announce when channel+to provided

    decision_payload = DecisionLoopPayload()
    heartbeat_payload = HeartbeatLoopPayload()
    news_payload = NewsLoopPayload(topic="impact", impact_score=0.7)

    cron_jobs = [
        {
            "name": "decision_loop",
            "cron_expr": "*/5 * * * *",
            "session": "isolated",
            "message": decision_payload.message,
        },
        {
            "name": "heartbeat_loop",
            "every": heartbeat_interval,
            "session": "isolated",
            "message": heartbeat_payload.message,
        },
        {
            "name": "news_loop",
            "event": "impact",
            "session": "main",
            "message": news_payload.message,
        },
    ]

    for job in cron_jobs:
        job_result: dict[str, str | bool] = {
            "name": job["name"],
            "registered": False,
        }

        if dry_run:
            if "cron_expr" in job:
                job_result["cron"] = job["cron_expr"]
            elif "event" in job:
                job_result["event"] = job["event"]
            else:
                job_result["every"] = job["every"]
            job_result["message"] = job["message"]
            job_result["registered"] = True
            results.append(job_result)
            continue

        args = [
            "--name", job["name"],
            "--session", job["session"],
            "--message", job["message"],
            "--agent", agent_id,
            "--announce",
        ]
        if channel and to:
            args.extend(["--channel", channel, "--to", to])
        if "cron_expr" in job:
            args.extend(["--cron", job["cron_expr"]])
        elif "event" in job:
            args.extend(["--event", job["event"]])
        else:
            args.extend(["--every", job["every"]])

        exit_code, output = _run_openclaw_cron_add(args)
        job_result["exit_code"] = str(exit_code)
        job_result["output"] = output

        if exit_code == 0:
            job_result["registered"] = True
        else:
            job_result["error"] = output if exit_code > 0 else f"openclaw error: {output}"

        results.append(job_result)

    hb_result: dict[str, str | bool] = {
        "name": "heartbeat_config",
        "registered": False,
    }
    if not skip_heartbeat_config:
        if dry_run:
            hb_result["interval"] = heartbeat_interval
            hb_result["agent_id"] = agent_id
            hb_result["registered"] = True
        else:
            try:
                _write_heartbeat_config(agent_id, heartbeat_interval)
                hb_result["registered"] = True
            except Exception as e:
                hb_result["error"] = str(e)
    results.append(hb_result)

    if news_ingest_interval is not None:
        if news_ingest_interval > 0:
            news_result = _install_news_ingest_timer(agent_user=agent_id, console=console)
            results.append(news_result)
        else:
            _remove_news_ingest_timer(agent_user=agent_id, console=console)
            results.append({"name": "news_ingest_timer", "registered": True, "removed": True})

    if json_output:
        print(json_lib.dumps({"agent_id": agent_id, "loops": results}, indent=2))
        return

    console.print(f"\n[bold]Cron Registration for Agent '{agent_id}'[/bold]\n")

    for r in results:
        name = r["name"]
        if r["registered"]:
            console.print(f"  [green]✓[/green] {name}")
        else:
            console.print(f"  [red]✗[/red] {name}: {r.get('error', 'unknown error')}")

    failed = [r for r in results if not r["registered"]]
    if failed:
        console.print(f"\n[yellow]{len(failed)} loop(s) failed to register.[/yellow]")
        raise typer.Exit(1)

    console.print("\n[green]All loops registered successfully.[/green]")


def _check_updates_on_startup() -> None:
    """Check for updates on startup if configured."""
    try:
        from traderbot.update_config import UpdateConfig
        from traderbot.updater import check_for_updates

        config = UpdateConfig.load()
        if not config.enabled or not config.check_on_startup:
            return

        result = check_for_updates(check_interval_minutes=config.check_interval_minutes)
        if result:
            Console().print(
                f"[dim]Update available: v{result['current']} → v{result['latest']}. "
                f"Run 'traderbot update' to update.[/dim]"
            )
    except Exception:
        pass


@app.command()
def uninstall(
    remove_data: Annotated[
        bool,
        typer.Option("--remove-data", help="Remove all profiles, databases, and user data (~/.traderbot/)"),
    ] = False,
    remove_repo: Annotated[
        bool,
        typer.Option("--remove-repo", help="Remove the TraderBot repository (~/traderbot/)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON for machine consumption"),
    ] = False,
) -> None:
    """Uninstall TraderBot — remove services, data, and optionally the repository."""
    from traderbot.paths import get_data_dir, list_all_data_paths
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    data_dir = get_data_dir()
    repo_dir = Path.home() / "traderbot"
    removed: list[str] = []

    # Step 1: Stop and remove system services
    import platform
    import subprocess

    if json_output:
        removed_services = []
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                for plist in daemon_dir.glob("com.traderbot.agent.*.plist"):
                    label = plist.stem
                    subprocess.run([_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                    if result.returncode == 0:
                        removed_services.append(str(plist))
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                for svc in service_dir.glob("traderbot-agent@*.service"):
                    unit = svc.name
                    subprocess.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                    subprocess.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    if result.returncode == 0:
                        removed_services.append(str(svc))
                for svc in list(service_dir.glob("traderbot-news-ingest@*.service")):
                    unit = svc.name
                    timer_unit = unit.replace(".service", ".timer")
                    subprocess.run([_SUDO, _SYSTEMCTL, "stop", timer_unit], capture_output=True)
                    subprocess.run([_SUDO, _SYSTEMCTL, "disable", timer_unit], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    if result.returncode == 0:
                        removed_services.append(str(svc))
                    timer_path = service_dir / timer_unit
                    if timer_path.exists():
                        subprocess.run([_SUDO, "rm", "-f", str(timer_path)], capture_output=True)
                        removed_services.append(str(timer_path))
                subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True)
        elif sys.platform == "win32":
            from traderbot.windows_service import (
                list_agent_services,
                list_news_tasks,
                uninstall_agent_service,
                uninstall_news_ingest_task,
            )
            for svc_name in list_agent_services():
                agent_name = svc_name.replace("TraderBotAgent-", "", 1)
                uninstall_agent_service(agent_name)
                removed_services.append(svc_name)
            for task_name in list_news_tasks():
                uninstall_news_ingest_task(task_name)
                removed_services.append(task_name)
        removed.extend(removed_services)
    else:
        console.print("[bold]Step 1: Removing system services[/bold]")
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                for plist in daemon_dir.glob("com.traderbot.agent.*.plist"):
                    label = plist.stem
                    subprocess.run([_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                    if result.returncode == 0:
                        console.print(f"  Removed: {plist}")
                        removed.append(str(plist))
                    else:
                        console.print(f"  [yellow]Could not remove: {plist}[/yellow]")
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                for svc in service_dir.glob("traderbot-agent@*.service"):
                    unit = svc.name
                    subprocess.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                    subprocess.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    if result.returncode == 0:
                        console.print(f"  Removed: {svc}")
                        removed.append(str(svc))
                    else:
                        console.print(f"  [yellow]Could not remove: {svc}[/yellow]")
                for svc in service_dir.glob("traderbot-news-ingest@*.service"):
                    unit = svc.name
                    timer_unit = unit.replace(".service", ".timer")
                    subprocess.run([_SUDO, _SYSTEMCTL, "stop", timer_unit], capture_output=True)
                    subprocess.run([_SUDO, _SYSTEMCTL, "disable", timer_unit], capture_output=True)
                    result = subprocess.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    if result.returncode == 0:
                        console.print(f"  Removed: {svc}")
                        removed.append(str(svc))
                    else:
                        console.print(f"  [yellow]Could not remove: {svc}[/yellow]")
                    timer_path = service_dir / timer_unit
                    if timer_path.exists():
                        subprocess.run([_SUDO, "rm", "-f", str(timer_path)], capture_output=True)
                        console.print(f"  Removed: {timer_path}")
                subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True)
        elif sys.platform == "win32":
            from traderbot.windows_service import (
                list_agent_services,
                list_news_tasks,
                uninstall_agent_service,
                uninstall_news_ingest_task,
            )
            for svc_name in list_agent_services():
                agent_name = svc_name.replace("TraderBotAgent-", "", 1)
                success = uninstall_agent_service(agent_name)
                if success:
                    console.print(f"  Removed: {svc_name}")
                    removed.append(svc_name)
                else:
                    console.print(f"  [yellow]Could not remove: {svc_name}[/yellow]")
            for task_name in list_news_tasks():
                success = uninstall_news_ingest_task(task_name)
                if success:
                    console.print(f"  Removed: {task_name}")
                    removed.append(task_name)
                else:
                    console.print(f"  [yellow]Could not remove: {task_name}[/yellow]")

    # Step 2: Prompt about data removal
    if not remove_data:
        if json_output:
            pass  # Non-interactive — skip data removal unless flag is set
        else:
            registry = ProfileRegistry()
            profile_names = registry.list_profiles()

            console.print(f"\n[bold]Data directory:[/bold] {data_dir}")
            if data_dir.exists():
                data_paths = list_all_data_paths()
                existing = [p for p in data_paths if p.exists()]
                if existing:
                    console.print(f"  [yellow]{len(existing)} data paths found[/yellow]")
                if profile_names:
                    console.print(f"  Profiles: {', '.join(profile_names)}")

            console.print("\n[bold]Remove all profiles, databases, and user data?[/bold]")
            console.print("[dim]This will permanently delete ~/.traderbot/ including all audit trails and credentials.[/dim]")
            answer = typer.confirm("  Remove data", default=False)
            if answer:
                remove_data = True

    if remove_data and data_dir.exists():
        if json_output:
            data_paths = list_all_data_paths()
            for p in data_paths:
                if p.exists():
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    removed.append(str(p))
            if data_dir.exists():
                shutil.rmtree(data_dir)
                removed.append(str(data_dir))
        else:
            console.print("[bold]Step 2: Removing user data[/bold]")
            data_paths = list_all_data_paths()
            for p in data_paths:
                if not p.exists():
                    continue
                label = p.relative_to(data_dir) if p.is_relative_to(data_dir) else p
                if p.is_dir():
                    shutil.rmtree(p)
                    console.print(f"  Removed dir:  {label}")
                else:
                    p.unlink()
                    console.print(f"  Removed file: {label}")
                removed.append(str(p))
            if data_dir.exists():
                shutil.rmtree(data_dir)
                console.print(f"  Removed data dir: {data_dir}")
                removed.append(str(data_dir))

    # Step 3: Prompt about repo removal
    if not remove_repo:
        if json_output:
            pass
        elif repo_dir.exists():
            console.print(f"\n[bold]Repository:[/bold] {repo_dir}")
            console.print("[dim]This will permanently delete the source code and virtual environment.[/dim]")
            answer = typer.confirm("  Remove repository", default=False)
            if answer:
                remove_repo = True

    if remove_repo and repo_dir.exists():
        if json_output:
            shutil.rmtree(repo_dir)
            removed.append(str(repo_dir))
        else:
            console.print("[bold]Step 3: Removing repository[/bold]")
            shutil.rmtree(repo_dir)
            print(f"  Removed: {repo_dir}")
            removed.append(str(repo_dir))

    # Step 4: Remove binary symlinks
    for bin_path in [Path("/usr/local/bin/traderbot"), Path.home() / ".local" / "bin" / "traderbot"]:
        if bin_path.is_symlink() or bin_path.exists():
            try:
                if json_output:
                    bin_path.unlink()
                    removed.append(str(bin_path))
                else:
                    subprocess.run([_SUDO, "rm", "-f", str(bin_path)], capture_output=True)
                    print(f"  Removed: {bin_path}")
                    removed.append(str(bin_path))
            except OSError:
                pass

    # Step 5: Clean temp files and caches
    import tempfile
    tmp_cleaned: list[str] = []
    for tmp_file in Path(tempfile.gettempdir()).glob("traderbot*"):
        try:
            if tmp_file.is_dir():
                shutil.rmtree(tmp_file)
            else:
                tmp_file.unlink()
            tmp_cleaned.append(str(tmp_file))
        except OSError:
            pass
    pip_cache = Path.home() / ".cache" / "pip"
    wheel_cache_glob = list(pip_cache.glob("wheels/*traderbot*")) if pip_cache.exists() else []
    for wc in wheel_cache_glob:
        try:
            if wc.is_dir():
                shutil.rmtree(wc)
            else:
                wc.unlink()
            tmp_cleaned.append(str(wc))
        except OSError:
            pass
    if tmp_cleaned:
        removed.extend(tmp_cleaned)
        if not json_output:
            for t in tmp_cleaned:
                print(f"  Cleaned: {t}")

    # Result — use print() instead of console.print() because repo removal
    # may have deleted the venv (including rich), making Rich unusable.
    if json_output:
        json_lib.dump({"removed": removed, "data_removed": remove_data, "repo_removed": remove_repo}, sys.stdout, default=str)
    else:
        if not removed:
            print("Nothing to remove — TraderBot is not installed.")
        else:
            print(f"\n✓ TraderBot uninstalled. {len(removed)} items removed.")


@app.command("cache")
def cache_command(
    action: Annotated[
        str,
        typer.Argument(help="Cache action: 'warm' to pre-populate event cache"),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Manage TraderBot caches. Use 'warm' to pre-populate the event category cache."""
    from traderbot.kalshi.client import KalshiClient
    from traderbot.kalshi.markets import MarketService, _save_event_cache_to_disk

    console = Console()

    if action != "warm":
        console.print(f"[red]Unknown cache action:[/red] {action}. Use 'warm'.")
        raise typer.Exit(1)

    async def _warm() -> dict[str, int]:
        from traderbot.kalshi.markets import _event_category_cache, _event_cache_ts

        client = KalshiClient()
        svc = MarketService(client)
        event_map = await svc._build_event_category_map()
        _event_category_cache.update(event_map)
        _event_cache_ts = time.monotonic()
        _save_event_cache_to_disk()
        await client.close()
        return {"events": len(event_map), "categories": len(set(event_map.values()))}

    result = asyncio.run(_warm())

    if json_output:
        json_lib.dump({"status": "warmed", **result}, sys.stdout)
    else:
        console.print(f"[green]✓[/green] Event cache warmed: {result['events']} events across {result['categories']} categories")


def main() -> None:
    """Entry point for the traderbot CLI."""
    _check_updates_on_startup()
    app()


if __name__ == "__main__":
    main()
