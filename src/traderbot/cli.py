"""Command-line interface for TraderBot."""

import asyncio
import json as json_lib
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


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
    """TraderBot -- Autonomous prediction market agent."""


auth_app = typer.Typer(
    name="auth",
    help="Manage API credentials via OS keyring.",
    rich_markup_mode="rich",
)
app.add_typer(auth_app, name="auth")

update_app = typer.Typer(name="update", help="Check and apply TraderBot updates.")
app.add_typer(update_app, name="update")


@update_app.callback(invoke_without_command=True)
def update_default(
    ctx: typer.Context,
    check: Annotated[
        bool,
        typer.Option("--check", help="Check only, don't install updates"),
    ] = False,
    dev: Annotated[
        bool,
        typer.Option("--dev", help="Update from dev branch instead of main"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Bypass cache and check now"),
    ] = False,
    restart: Annotated[
        bool,
        typer.Option("--restart", help="Restart after update"),
    ] = False,
) -> None:
    """Default: pulls and installs latest from branch. --check to check only."""
    if ctx.invoked_subcommand is not None:
        return

    from traderbot.updater import apply_update, check_for_updates

    console = Console()
    branch = "dev" if dev else "main"

    if check:
        from traderbot.update_config import UpdateConfig
        config = UpdateConfig.load()
        if not config.enabled:
            console.print("[yellow]Update checking is disabled.[/yellow]")
            return
        result = check_for_updates(force=force, check_interval_hours=config.check_interval_hours)
        if result:
            console.print(
                f"[yellow]Update available: v{result['current']} -> v{result['latest']}[/yellow]"
            )
            console.print(f"[dim]Release: {result['url']}[/dim]")
            console.print("[dim]Run 'traderbot update' to install.[/dim]")
        else:
            console.print("[green]Already up to date.[/green]")
        return

    console.print(f"[dim]Pulling latest from {branch}...[/dim]")
    if apply_update(restart=restart, branch=branch):
        console.print("[green]Update applied successfully.[/green]")
    else:
        console.print("[red]Update failed. Check logs for details.[/red]")
        raise typer.Exit(1)

cron_app = typer.Typer(name="cron", help="Register cron loops and heartbeat with OpenClaw.")
app.add_typer(cron_app, name="cron")

err_console = Console(stderr=True)


def _with_db(db_path, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(db_path) as conn:
        init_schema(conn)
        return func(conn)


def _get_strategy(name: str):
    from traderbot.simulation.strategies import get_strategy as _get_strat

    return _get_strat(name)


@app.command()
def scan(
    limit: Annotated[int, typer.Option("--limit", help="Max markets to return")] = 20,
    category: Annotated[str | None, typer.Option("--category", help="Filter by category (e.g. mentions, politics, sports)")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List open markets from Kalshi. Use --category for category-scoped results."""
    from traderbot.kalshi.markets import MarketService

    console = Console()
    try:
        from traderbot.kalshi.client import KalshiClient

        client = KalshiClient()
        service = MarketService(client)
        if category:
            result = asyncio.run(service.list_markets_by_category(category=category))
        else:
            result = asyncio.run(service.list_markets(limit=limit, status="open"))
        markets = result.markets
    except Exception as exc:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print(f"[red]Error scanning markets:[/red] {exc}")
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

        async def _fetch():
            m = await service.get_market(ticker)
            o = await service.get_orderbook(ticker)
            await client.close()
            return m, o

        market, orderbook = asyncio.run(_fetch())
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
    console.print(f"State: {market.status}  Volume: {market.volume}  OI: {market.open_interest}")
    console.print(f"YES bids: {len(orderbook.yes_bids)}  NO bids: {len(orderbook.no_bids)}")

    from traderbot.analysis.odds import implied_probability

    prob = implied_probability(orderbook)
    console.print("\n[bold]Analysis[/bold]")
    console.print(f"  Implied YES prob: {prob.yes_prob:.2%}")
    console.print(f"  Implied NO prob:  {prob.no_prob:.2%}")
    console.print(f"  Spread:           {prob.spread_cents}c")
    console.print(f"  Mid price:        {prob.mid_price_cents}c")


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

        async def _fetch_markets():
            result = await service.list_markets(limit=limit, state="open")
            await client.close()
            return result

        markets = asyncio.run(_fetch_markets())
    except Exception:
        if json_output:
            json_lib.dump({"note": "Signal generation requires API connection"}, sys.stdout)
        else:
            console.print("[yellow]Signal generation requires API connection.[/yellow]")
        return

    if category_enum is not None:
        markets = [m for m in markets if m.market_category == category_enum]

    if not markets:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print("[yellow]No open markets found.[/yellow]")
        return

    results: list[dict] = []
    for market in markets:
        try:
            client2 = KalshiClient()
            svc2 = MarketService(client2)

            async def _fetch_ob():
                ob = await svc2.get_orderbook(market.ticker)
                await client2.close()
                return ob

            orderbook = asyncio.run(_fetch_ob())
        except Exception:
            continue

        prob = implied_probability(orderbook)
        prices_int = [int(p) for p in market.outcome_prices]
        signal = generate_signal(
            ticker=market.ticker,
            prices=prices_int,
            orderbook=orderbook,
            estimated_prob=prob.yes_prob,
        )
        results.append(
            {
                "ticker": market.ticker,
                "category": market.market_category.value if market.market_category else (market.category or "uncategorized"),
                "direction": signal.direction,
                "confidence": round(signal.confidence, 3),
                "estimated_prob": round(signal.estimated_prob, 3),
                "edge_cents": signal.edge_cents,
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
    for r in results:
        table.add_row(
            r["ticker"],
            r["category"],
            r["direction"],
            f"{r['confidence']:.1%}",
            f"{r['estimated_prob']:.1%}",
            f"{r['edge_cents']}c",
        )
    console.print(table)


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

    estimated_prob = 0.5
    edge_estimate = 0.0
    market_price_cents = price
    market_open_interest = 0

    try:
        client = KalshiClient()
        service = MarketService(client)

        async def _fetch_trade_data():
            m = await service.get_market(ticker)
            o = await service.get_orderbook(ticker)
            await client.close()
            return m, o

        market, orderbook = asyncio.run(_fetch_trade_data())
        prob = implied_probability(orderbook)
        market_price_cents = prob.mid_price_cents
        estimated_prob = prob.yes_prob if direction.lower() == "yes" else prob.no_prob
        edge_estimate = abs(estimated_prob - (market_price_cents / 100.0))
        market_open_interest = market.open_interest
    except Exception:
        # Without live data, fall through with defaults that will likely
        # fail liquidity and edge checks -- caller should ensure API connectivity.
        pass

    trade_request = TradeRequest(
        ticker=ticker,
        direction=direction,
        quantity=quantity,
        price_cents=price,
        estimated_prob=estimated_prob,
        confidence=0.5,
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
        confidence=0.5,
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

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    if result["outcome"] == "executed":
        console.print(
            f"[green]Trade executed[/green]: {ticker} {direction} -- sized ${sized / 100:.2f}"
        )
    else:
        console.print(f"[red]Trade rejected[/red]: {ticker} -- {result['reason']}")


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


def _python_version_ok() -> tuple[bool, str, tuple[int, int]]:
    """Check if the running Python version is compatible (3.12.x only)."""
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    return (major, minor) == (3, 12), version_str, (major, minor)


@app.command()
def bootstrap(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate without writing to DB or keyring")
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

    # Step 1: Check Python version (3.12.x -- chroma-hnswlib has no wheels for 3.13+)
    py_ok, version_str, _py_version_tuple = _python_version_ok()
    steps["python_version"] = version_str
    steps["python_version_ok"] = py_ok

    if not py_ok:
        if json_output:
            json_lib.dump(
                {"error": f"Python {version_str} -- 3.12.x required (chromadb dependency)", "steps": steps},
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

    # Step 3: Verify keyring access
    mgr = AuthManager()
    keyring_ok = mgr.keyring_available
    steps["keyring_available"] = keyring_ok

    # Step 4: Run auth login flow (interactive -- skipped in dry-run/JSON mode)
    if not dry_run and not json_output:
        if not keyring_ok:
            console.print(
                "\n[yellow]Keyring unavailable (headless Linux?). Credentials will be stored in ~/.traderbot/.env[/yellow]"
            )
            console.print(
                "[yellow]For secure storage, install and unlock gnome-keyring with a D-Bus session.[/yellow]"
            )
        console.print("\n[bold]Credential Setup[/bold]")
        console.print("Enter your API credentials (press Enter to skip any field):")
        from traderbot.auth import _ALL_SERVICES, KeyringUnavailableError

        env_lines: list[str] = []
        for service_name, keys in _ALL_SERVICES.items():
            for key in keys:
                value = typer.prompt(f"  {service_name}.{key}", default="", show_default=False)
                if value:
                    if keyring_ok:
                        try:
                            mgr.set_credential(service_name, key, value)
                            console.print(f"[green]Stored in keyring:[/green] {service_name}.{key}")
                        except (KeyringUnavailableError, Exception) as exc:
                            env_key = f"{service_name.upper()}_{key.upper()}"
                            env_lines.append(f"{env_key}={value}")
                            console.print(
                                f"[yellow]Keyring failed ({exc}), saved to .env:[/yellow] {env_key}"
                            )
                    else:
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
        with get_connection(db_path) as conn:
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
        console.print(f"  [green]+[/green] Python {steps['python_version']} (= 3.12)")
    else:
        console.print(f"  [red]x[/red] Python {steps['python_version']} (requires = 3.12)")

    console.print("\n[bold]2. Config Directory[/bold]")
    if config_dir_exists or dry_run:
        console.print(f"  [green]+[/green] {config_dir}")
    else:
        console.print(f"  [green]+[/green] Created {config_dir}")

    console.print("\n[bold]3. Keyring Access[/bold]")
    if keyring_ok:
        console.print("  [green]+[/green] OS keyring available")
    else:
        console.print("  [red]x[/red] Keyring unavailable -- use .env fallback")

    console.print("\n[bold]4. Credentials[/bold]")
    for service_name, keys in sorted(status.items()):
        for key, ok in keys.items():
            mark = "[green]+[/green]" if ok else "[red]x[/red]"
            console.print(f"  {mark} {service_name}.{key}")

    console.print("\n[bold]5. Database[/bold]")
    if dry_run:
        console.print(f"  (dry-run) {db_path}")
    else:
        console.print(f"  [green]+[/green] {db_path}")

    console.print("\n" + "=" * 40)
    if all_ok:
        console.print("[bold green]Bootstrap complete![/bold green]")
        console.print("\nNext steps:")
        console.print("  [cyan]traderbot scan[/cyan]               -- list open markets")
        console.print("  [cyan]traderbot backtest --strategy momentum[/cyan] -- run a backtest")
    else:
        console.print("[bold yellow]Bootstrap partially complete.[/bold yellow]")
        if missing:
            console.print(f"  Missing credentials: {', '.join(missing)}")
            console.print(
                "  Run [bold]traderbot auth login[/bold] to configure missing credentials."
            )


@app.command()
def heartbeat(
    db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report only -- no state changes")
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
        result = _with_db(db_path, _run)
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

    console.print(f"\n[bold]Heartbeat[/bold] -- {result.timestamp.isoformat()}")
    console.print(f"  Steps completed: {', '.join(result.steps_completed)}")

    console.print("\n[bold]Performance[/bold]")
    pnl_str = f"{perf.total_pnl_cents / 100:+.2f}"
    console.print(
        f"  Trades: {perf.trade_count}  Win rate: {perf.win_rate:.0%}  P&L: {pnl_str} USD"
    )
    if perf.deviation_flag:
        console.print(f"  [yellow]![/yellow] {perf.deviation_flag}")

    console.print("\n[bold]Decisions[/bold]")
    console.print(
        f"  Closed: {decision.closed_count}  "
        f"Correct: {decision.correct_predictions}  "
        f"Accuracy: {decision.prediction_accuracy:.0%}"
    )
    if decision.pending_review:
        console.print(f"  Open: {decision.open_count} -- {', '.join(decision.pending_review[:5])}")

    console.print("\n[bold]Adaptation[/bold]")
    if adapt.updated:
        console.print(
            f"  Edge threshold: {adapt.direction} "
            f"(magnitude={adapt.magnitude:.4f}, "
            f"confidence={adapt.confidence:.2f})"
        )
        console.print(f"  Method: {adapt.method}")
    else:
        console.print(f"  No update -- {adapt.skipped_reason}")

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
            console.print(f"  [yellow]![/yellow] {alert}")
        if cb.level != "NORMAL":
            console.print(f"  [yellow]![/yellow] Circuit breaker: {cb.level} -- {cb.reason}")


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
        typer.Option("--source", help="Filter by source: newsapi, twitter, reddit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch and display news for tracked markets."""
    from traderbot.news.cache_paths import get_news_cache_path
    from traderbot.news.classifier import NewsClassifier
    from traderbot.news.models import NewsCategory, NewsItem, NewsSource
    from traderbot.news.sentiment_scorer import SentimentScorer
    from traderbot.news.sources import NewsAggregator
    from traderbot.profiles.config import resolve_newsapi_key
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

    # Build category filter from profile
    category_filter: list[NewsCategory] | None = None
    if profile is not None and profile.enabled_categories:
        category_filter = profile.enabled_categories

    # Validate --source
    source_filter: NewsSource | None = None
    if source is not None:
        try:
            source_filter = NewsSource(source.lower())
        except ValueError:
            valid = ", ".join(s.value for s in NewsSource)
            if json_output:
                json_lib.dump({"error": f"Invalid source: {source}. Valid: {valid}"}, sys.stdout)
            else:
                err_console.print(f"[red]Invalid source:[/red] {source}. Valid: {valid}")
            raise typer.Exit(code=1) from None

    # Resolve API keys via profile-aware chain
    newsapi_key = resolve_newsapi_key(profile)
    twitter_key = os.environ.get("TWITTER_API_KEY")

    if not newsapi_key and not twitter_key:
        if json_output:
            json_lib.dump(
                {
                    "error": "No API keys configured. Set NEWSAPI_KEY and/or TWITTER_API_KEY environment variables or profile credentials."
                },
                sys.stdout,
            )
        else:
            console.print(
                "[red]No API keys configured.[/red] Set NEWSAPI_KEY and/or TWITTER_API_KEY environment variables or profile credentials."
            )
            console.print("Reddit RSS feeds work without keys -- try [cyan]--source reddit[/cyan].")
        return

    # Profile-aware news cache path
    cache_path = get_news_cache_path(profile)
    logger.debug("News cache path: %s", cache_path)

    # Map source filter for aggregator -- NewsSource is now a single canonical enum
    async def _fetch() -> list[NewsItem]:
        async with NewsAggregator(
            newsapi_key=newsapi_key, twitter_api_key=twitter_key
        ) as aggregator:
            if source_filter is not None:
                return await aggregator.fetch_recent(source_filter, limit=limit)
            return await aggregator.fetch_all(limit=limit)

    try:
        items = asyncio.run(_fetch())
    except Exception:
        if json_output:
            json_lib.dump([], sys.stdout)
        else:
            console.print("[red]Failed to fetch news.[/red]")
        return

    # Classify items
    classifier = NewsClassifier()
    scorer = SentimentScorer()
    classified_items: list[dict] = []
    for item in items:
        classified = classifier.classify(item, category_filter=category_filter)
        if classified is None:
            continue
        # Filter by --category flag if specified
        if category_enum is not None and classified.category != category_enum:
            continue
        sentiment = scorer.score(item.title, item.source, item.id)
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
        json_lib.dump(output, sys.stdout, default=str)
        return

    if not classified_items:
        console.print("No news items found.")
        return

    table = Table(title="News Feed")
    table.add_column("Title", style="white", max_width=50)
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
        table.add_row(title, item.source.value, c.category.value, published, score_str)
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
) -> None:
    """Run a paper trading session against the Kalshi demo API.

    Connects to the demo API, fetches open markets, runs the specified
    strategy through risk checks, and tracks simulated positions and P&L.
    Press Ctrl+C to stop early and see final results.
    """
    import asyncio
    import time

    from traderbot.kalshi.client import KalshiClient
    from traderbot.kalshi.demo import DemoAdapter
    from traderbot.kalshi.markets import MarketService
    from traderbot.simulation.engine import Signal
    from traderbot.simulation.paper_trader import PaperTrader
    from traderbot.simulation.strategies import get_strategy

    console = Console()
    err_console = Console(stderr=True)

    strat = get_strategy(strategy)

    try:
        demo = DemoAdapter()
    except Exception:
        if json_output:
            json_lib.dump({"error": "Demo API connection required for paper trading"}, sys.stdout)
        else:
            console.print("[red]Demo API connection required for paper trading.[/red]")
        return

    from traderbot.db import get_connection, init_schema
    from traderbot.profiles import get_current_profile

    profile = get_current_profile()
    client = demo.get_client()
    market_service = MarketService(client)

    with get_connection(db_path) as conn:
        init_schema(conn)
        trader = PaperTrader(demo, conn, profile=profile)

        console.print(f"[bold]Paper Trading[/bold] -- {strategy} ({duration}min)")
        console.print(f"  Starting cash: ${trader.get_portfolio().cash_cents / 100:.2f}")

        start_time = time.time()
        end_time = start_time + duration * 60
        iteration = 0

        try:
            while time.time() < end_time:
                iteration += 1
                try:
                    lm_client = KalshiClient()
                    lm_svc = MarketService(lm_client)

                    async def _fetch_paper_markets():
                        m = await lm_svc.list_markets(limit=5, status="open")
                        await lm_client.close()
                        return m

                    markets = asyncio.run(_fetch_paper_markets())
                except Exception:
                    console.print("[yellow]Could not fetch markets, retrying...[/yellow]")
                    time.sleep(30)
                    continue

                for market in markets:
                    try:
                        ob_client = KalshiClient()
                        ob_svc = MarketService(ob_client)

                        async def _fetch_paper_ob():
                            ob = await ob_svc.get_orderbook(market.ticker)
                            await ob_client.close()
                            return ob

                        orderbook = asyncio.run(_fetch_paper_ob())

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
                                    f"{result.quantity}x {sig.ticker} @ {result.price_cents}c"
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

    decisions = _with_db(db_path, lambda conn: list_by_date_range(conn, start=start_dt, end=end_dt))

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

    _with_db(db_path, _run)


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
        "kalshi": ["api_key", "private_key_pem"],
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
            mark = "[green]+[/green]" if ok else "[red]x[/red]"
            table.add_row(service_name, key, mark)
    console.print(table)

    missing = [f"{s}.{k}" for s, keys in status.items() for k, ok in keys.items() if not ok]
    if missing:
        console.print(f"[yellow]Missing credentials:[/yellow] {', '.join(missing)}")
        console.print("Run [bold]traderbot auth login[/bold] to configure.")


@update_app.command("configure")
def update_configure(
    enabled: Annotated[bool | None, typer.Option(help="Enable/disable update checking")] = None,
    check_on_startup: Annotated[bool | None, typer.Option(help="Check on startup")] = None,
    check_interval_hours: Annotated[int | None, typer.Option(help="Hours between checks")] = None,
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
    if check_interval_hours is not None:
        config.check_interval_hours = check_interval_hours
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
    name: str,
    mode: Annotated[str, typer.Option(help="Trading mode: paper or live")] = "paper",
    description: Annotated[str, typer.Option(help="Profile description")] = "",
    categories: Annotated[str, typer.Option(help="Comma-separated market categories")] = "",
    risk_multiplier: Annotated[float, typer.Option(help="Risk multiplier (0-1)")] = 1.0,
    max_position_pct: Annotated[
        float | None, typer.Option(help="Max position per market %")
    ] = None,
    max_daily_loss_pct: Annotated[float | None, typer.Option(help="Max daily loss %")] = None,
    max_drawdown_pct: Annotated[float | None, typer.Option(help="Max drawdown %")] = None,
    max_open_positions: Annotated[int | None, typer.Option(help="Max open positions")] = None,
    min_liquidity: Annotated[int | None, typer.Option(help="Min liquidity threshold")] = None,
    min_edge_pct: Annotated[float | None, typer.Option(help="Min edge %")] = None,
) -> None:
    """Create a new trading profile with risk parameters."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.models import TradingProfile
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.risk.limits import HARD_LIMITS

    console = Console()

    # Validate mode
    if mode not in ("paper", "live"):
        console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
        raise typer.Exit(1)

    # Parse categories
    enabled_categories = []
    if categories:
        try:
            enabled_categories = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None

    # Use HARD_LIMITS as defaults for unspecified params
    profile_data = {
        "name": name,
        "mode": mode,
        "description": description or f"{name} trading profile",
        "enabled_categories": enabled_categories,
        "risk_multiplier": risk_multiplier,
        "max_position_per_market_pct": max_position_pct
        or HARD_LIMITS["max_position_per_market_pct"],
        "max_daily_loss_pct": max_daily_loss_pct or HARD_LIMITS["max_daily_loss_pct"],
        "max_drawdown_pct": max_drawdown_pct or HARD_LIMITS["max_drawdown_pct"],
        "max_open_positions": max_open_positions or int(HARD_LIMITS["max_open_positions"]),
        "min_liquidity_threshold": min_liquidity or int(HARD_LIMITS["min_liquidity_threshold"]),
        "min_edge_pct": min_edge_pct or HARD_LIMITS["min_edge_pct"],
    }

    try:
        profile = TradingProfile(**profile_data)
        registry = ProfileRegistry()
        registry.create_profile(profile)
        console.print(f"[green]+[/green] Created profile '{name}' in {mode} mode")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


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
                console.print(f"  - {cat.value}")
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
    console.print(f"[green]+[/green] Deleted profile '{name}'")

    if not keep_data:
        console.print("[yellow]Note:[/yellow] Data directories were also deleted")


def _resolve_agent_path(agent_id: str) -> Path | None:
    """Resolve agent workspace path using OpenClaw multi-agent layout.

    Search order:
    1. Explicit workspace from openclaw.json agents.list
    2. ~/.openclaw/workspace-<agentId>/ (OpenClaw per-agent workspace)
    3. ~/.openclaw/workspace/<agentId>/ (subdirectory layout)
    4. ~/.openclaw/workspace/ (default workspace, if IDENTITY.md/TOOLS.md present)
    5. ~/.openclaw/agents/<agentId>/ (agent state directory)
    6. .openclaw/workspace/<agentId>/ (project-local, legacy)
    """
    from pathlib import Path

    oc_config = Path.home() / ".openclaw" / "openclaw.json"
    if oc_config.exists():
        try:
            import json as _json

            cfg = _json.loads(oc_config.read_text())
            for entry in cfg.get("agents", {}).get("list", []):
                if entry.get("id") == agent_id and entry.get("workspace"):
                    p = Path(entry["workspace"]).expanduser()
                    if p.exists() and p.is_dir():
                        return p
        except Exception:
            pass

    candidates = [
        Path.home() / ".openclaw" / f"workspace-{agent_id}",
        Path.home() / ".openclaw" / "workspace" / agent_id,
        Path.home() / ".openclaw" / "workspace",
        Path.home() / ".openclaw" / "agents" / agent_id,
        Path.cwd() / ".openclaw" / "workspace" / agent_id,
    ]
    default_ws = Path.home() / ".openclaw" / "workspace"
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and ((candidate / "IDENTITY.md").exists() or (candidate / "TOOLS.md").exists()):
            if candidate == default_ws and agent_id != "main" and (default_ws / agent_id).exists() and (default_ws / agent_id / "IDENTITY.md").exists():
                continue
            return candidate
    return None


@profile_app.command("assign")
def profile_assign(
    profile_name: str,
    agent_id: str,
    non_interactive: bool = typer.Option(
        False, "--non-interactive", "-n", help="Skip interactive prompts (use defaults)"
    ),
    token_only: bool = typer.Option(
        False, "--token-only", help="Output only the raw token (for scripting)"
    ),
) -> None:
    """Assign a token to an agent for profile access."""
    from traderbot.profiles.injection import inject_token, propagate_workspace_files
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.profiles.tokens import assign_token, generate_token

    registry = ProfileRegistry()

    if not registry.profile_exists(profile_name):
        console = Console()
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    profile = registry.get_profile(profile_name)

    try:
        token = generate_token()
        assign_token(profile_name, agent_id, token)

        if token_only:
            print(token)
        else:
            console = Console()
            console.print(
                f"[green]+[/green] Assigned token to profile '{profile_name}' for agent '{agent_id}'"
            )
            console.print(f"Token: [bold]{_mask_token(token)}[/bold]")

        try:
            agent_path = _resolve_agent_path(agent_id)
            if not agent_path or not agent_path.exists():
                if not token_only:
                    console.print(
                        f"[yellow]Warning:[/yellow] Agent directory not found for '{agent_id}'"
                    )
                    console.print("Token assigned but not injected into TOOLS.md")
            else:
                propagate_workspace_files(profile, agent_path, interactive=not non_interactive)
                inject_token(str(agent_path), token)
                if not token_only:
                    console.print(
                        f"[green]+[/green] Workspace files and token injected into {agent_id}/"
                    )
        except FileNotFoundError:
            if not token_only:
                console.print("[yellow]Warning:[/yellow] Agent directory not found")
                console.print("Token assigned but not injected into TOOLS.md")
        except Exception as e:
            if not token_only:
                console.print(f"[yellow]Warning:[/yellow] Failed to inject token into TOOLS.md: {e}")
                console.print("Token assigned but not injected")
    except ValueError as e:
        if token_only:
            print(f"ERROR: {e}", file=sys.stderr)
            raise typer.Exit(1) from None
        console = Console()
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


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
    console.print(f"[green]+[/green] Revoked token for profile '{profile_name}'")

    # Remove token from agent's TOOLS.md
    if agent_id:
        try:
            agent_path = _resolve_agent_path(agent_id)
            if agent_path and agent_path.exists():
                remove_token_from_tools(str(agent_path))
                console.print(f"[green]+[/green] Token removed from {agent_id}/TOOLS.md")
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
    name: str,
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
) -> None:
    """Update specific fields of an existing profile."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

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

    if not update_kwargs:
        console.print("[yellow]Warning:[/yellow] No fields to update")
        return

    try:
        registry.update_profile(name, **update_kwargs)
        console.print(f"[green]+[/green] Updated profile '{name}'")
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


@profile_app.command("set-auth")
def profile_set_auth(
    profile_name: str,
    service: str,
    key: str,
) -> None:
    """Store a credential for a profile (prompts for secret)."""
    from traderbot.profiles.auth import ProfileAuthStore
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    profile = registry.get_profile(profile_name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    secret = typer.prompt("Secret", hide_input=True)

    auth_store = ProfileAuthStore(profile)
    auth_store.set_credentials(service, key, secret)
    console.print(
        f"[green]+[/green] Stored credentials for '{service}' on profile '{profile_name}'"
    )


@profile_app.command("auth")
def profile_auth(
    profile_name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show configured credentials for a profile."""
    from traderbot.profiles.auth import ProfileAuthStore
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    profile = registry.get_profile(profile_name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    auth_store = ProfileAuthStore(profile)
    services = auth_store.list_services()

    if not services:
        if not json_output:
            console.print(
                f"[yellow]No credentials configured for profile '{profile_name}'[/yellow]"
            )
        else:
            print("[]")
        return

    if json_output:
        creds_list = []
        for svc in services:
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

        for svc in services:
            creds = auth_store.get_credentials(svc)
            if creds:
                masked_key = creds[0][:8] + "..." if len(creds[0]) > 8 else "***"
                table.add_row(svc, masked_key)

        console.print(table)



def _wait_for_gateway(max_attempts: int = 15) -> bool:
    """Wait for the OpenClaw gateway to accept connections."""
    import json as _json
    import socket

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    port = 18789
    if config_path.exists():
        try:
            cfg = _json.loads(config_path.read_text())
            port = cfg.get("gateway", {}).get("port", 18789)
        except (ValueError, KeyError):
            pass

    for attempt in range(max_attempts):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError):
            import time
            time.sleep(2)
    return False


_OPENCLAW_EXTRA_PATHS = [
    str(Path.home() / ".npm-global" / "bin"),
    str(Path.home() / ".local" / "bin"),
    "/usr/local/bin",
    "/opt/homebrew/bin",
]


def _find_openclaw() -> str | None:
    """Find openclaw binary, checking expanded PATH locations."""
    import shutil

    for p in _OPENCLAW_EXTRA_PATHS:
        candidate = Path(p) / "openclaw"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("openclaw")


def _openclaw_env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    extra = ":".join(_OPENCLAW_EXTRA_PATHS)
    env["PATH"] = f"{extra}:{env.get('PATH', '')}"
    return env


def _run_openclaw_cron_add(args: list[str]) -> tuple[int, str]:
    """Run `openclaw cron add` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "add", *args],
            capture_output=True,
            text=True,
            timeout=30,
            env=_openclaw_env(),
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron add timed out"


TRADERBOT_CRON_JOB_NAMES = frozenset({"decision_loop", "heartbeat_loop"})
TRADERBOT_EVENT_JOB_NAMES = frozenset({"news_loop"})


def _run_openclaw_cron_list() -> tuple[int, str]:
    """Run `openclaw cron list --json` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_openclaw_env(),
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron list timed out"


def _run_openclaw_cron_show(job_id: str) -> tuple[int, str]:
    """Run `openclaw cron show <job_id> --json` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "show", job_id, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_openclaw_env(),
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron list timed out"


def _run_openclaw_cron_show(job_id: str) -> tuple[int, str]:
    """Run `openclaw cron show <job_id> --json` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "show", job_id, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_openclaw_env(),
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron show timed out"


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
        if not _find_openclaw():
            console.print("[red]Error:[/red] openclaw CLI not found")
            console.print("Install OpenClaw: https://github.com/openclaw/openclaw")
            raise typer.Exit(1)

        console.print("[dim]Waiting for OpenClaw gateway...[/dim]")
        if not _wait_for_gateway():
            console.print("[yellow]Warning:[/yellow] Gateway not responding on port 18789. Registration may fail.")

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

    if json_output:
        print(json_lib.dumps({"agent_id": agent_id, "loops": results}, indent=2))
        return

    console.print(f"\n[bold]Cron Registration for Agent '{agent_id}'[/bold]\n")

    for r in results:
        name = r["name"]
        if r["registered"]:
            console.print(f"  [green]+[/green] {name}")
        else:
            console.print(f"  [red]x[/red] {name}: {r.get('error', 'unknown error')}")

    failed = [r for r in results if not r["registered"]]
    if failed:
        console.print(f"\n[yellow]{len(failed)} loop(s) failed to register.[/yellow]")
        raise typer.Exit(1)

    console.print("\n[green]All loops registered successfully.[/green]")

    if not dry_run and not failed:
        list_exit_code, list_output = _run_openclaw_cron_list()
        if list_exit_code == 0:
            try:
                parsed = json_lib.loads(list_output)
                if isinstance(parsed, dict) and "jobs" in parsed:
                    registered_jobs = parsed["jobs"]
                elif isinstance(parsed, list):
                    registered_jobs = parsed
                else:
                    registered_jobs = []
                reg_names = {j.get("name", "") for j in registered_jobs if isinstance(j, dict)}
                missing_after = TRADERBOT_CRON_JOB_NAMES - reg_names
                if missing_after:
                    console.print(f"\n[yellow]Warning:[/yellow] Jobs registered but not found in cron list: {', '.join(sorted(missing_after))}")
                    console.print("[dim]OpenClaw may need a moment to persist jobs. Run `traderbot cron status` to verify.[/dim]")
                else:
                    for j in registered_jobs:
                        if isinstance(j, dict) and j.get("name", "") in TRADERBOT_CRON_JOB_NAMES:
                            status = j.get("status", "unknown")
                            if status in ("error", "disabled"):
                                console.print(f"[yellow]  ![/yellow] {j['name']}: status={status}")
            except (json_lib.JSONDecodeError, ValueError):
                pass


@cron_app.command("status")
def cron_status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
    agent_id: Annotated[
        str | None,
        typer.Option("--agent", help="Filter to jobs for a specific agent ID"),
    ] = None,
) -> None:
    """Check status of TraderBot cron loops registered with OpenClaw."""
    from traderbot.cron_loops import DECISION_LOOP_CRON, HEARTBEAT_LOOP_CRON

    console = Console()

    if not _find_openclaw():
        console.print("[red]Error:[/red] openclaw CLI not found")
        console.print("Install OpenClaw: https://github.com/openclaw/openclaw")
        raise typer.Exit(1)

    expected_loops: dict[str, dict[str, str]] = {
        "decision_loop": {
            "schedule": DECISION_LOOP_CRON,
            "session": "isolated",
            "kind": "agentTurn",
        },
        "heartbeat_loop": {
            "schedule": HEARTBEAT_LOOP_CRON,
            "session": "isolated",
            "kind": "agentTurn",
        },
        "news_loop": {
            "schedule": "event-driven",
            "session": "main",
            "kind": "systemEvent",
        },
    }

    exit_code, output = _run_openclaw_cron_list()

    if exit_code == -1:
        console.print("[red]Error:[/red] openclaw CLI not found in PATH")
        raise typer.Exit(1)
    if exit_code == -2:
        console.print("[red]Error:[/red] openclaw cron list timed out")
        raise typer.Exit(1)
    if exit_code != 0:
        console.print(f"[red]Error:[/red] openclaw cron list failed (exit {exit_code}): {output}")
        raise typer.Exit(1)

    try:
        parsed = json_lib.loads(output)
    except (json_lib.JSONDecodeError, ValueError):
        if not output.strip():
            parsed = {}
        else:
            console.print(f"[red]Error:[/red] Failed to parse openclaw cron list output: {output[:200]}")
            raise typer.Exit(1)

    # openclaw cron list --json returns {"jobs": [...], "total": N, ...}
    # not a bare array — unwrap the "jobs" key if present
    if isinstance(parsed, dict) and "jobs" in parsed:
        all_jobs = parsed["jobs"]
    elif isinstance(parsed, list):
        all_jobs = parsed
    else:
        all_jobs = []

    all_traderbot_names = TRADERBOT_CRON_JOB_NAMES | TRADERBOT_EVENT_JOB_NAMES
    traderbot_jobs = [
        j for j in all_jobs
        if j.get("name", "") in all_traderbot_names
        if agent_id is None or j.get("agentId", j.get("agent", "")) == agent_id
    ]

    registered_names = {j["name"] for j in traderbot_jobs if "name" in j}
    missing_cron = TRADERBOT_CRON_JOB_NAMES - registered_names
    extra_tb = registered_names - all_traderbot_names

    status_by_name: dict[str, str] = {}
    for j in traderbot_jobs:
        name = j.get("name", "")
        status_by_name[name] = j.get("status", "unknown")

    loop_results: list[dict[str, str | bool]] = []
    for name, meta in expected_loops.items():
        result: dict[str, str | bool] = {
            "name": name,
            "expected_schedule": meta["schedule"],
            "expected_session": meta["session"],
            "expected_kind": meta["kind"],
        }
        if name in TRADERBOT_EVENT_JOB_NAMES and name not in registered_names:
            result["registered"] = False
            result["status"] = "event-driven"
            result["healthy"] = True
        elif name in registered_names:
            status_val = status_by_name.get(name, "unknown")
            result["registered"] = True
            result["status"] = status_val
            result["healthy"] = status_val in ("ok", "idle", "running")
        else:
            result["registered"] = False
            result["status"] = "missing"
            result["healthy"] = False
        loop_results.append(result)

    for name in extra_tb:
        match = next(j for j in traderbot_jobs if j.get("name") == name)
        loop_results.append({
            "name": name,
            "registered": True,
            "status": match.get("status", "unknown"),
            "healthy": match.get("status", "unknown") in ("ok", "idle", "running"),
            "expected_schedule": "n/a (extra)",
        })

    if json_output:
        has_issues = any(not r.get("healthy", True) for r in loop_results) or bool(missing_cron)
        print(json_lib.dumps({
            "agent_id": agent_id,
            "loops": loop_results,
            "all_healthy": not has_issues,
            "missing": sorted(missing_cron),
        }, indent=2))
        if has_issues:
            raise typer.Exit(1)
        return

    status_colors = {
        "ok": "green",
        "running": "blue",
        "idle": "dim",
        "event-driven": "cyan",
    }
    console.print("\n[bold]TraderBot Cron Status[/bold]\n")

    for r in loop_results:
        name = r["name"]
        if not r["registered"]:
            if r.get("status") == "event-driven":
                console.print(f"  [cyan]event-driven[/cyan]  {name}  [dim](not in cron list)[/dim]")
            else:
                console.print(f"  [red]MISSING[/red]  {name}")
        elif r.get("healthy"):
            status = str(r.get("status", "?"))
            color = status_colors.get(status, "green")
            console.print(f"  [{color}]{status}[/{color}]  {name}")
        else:
            console.print(f"  [yellow]{r.get('status', 'unknown'):>10}[/yellow]  {name}")

    if missing_cron:
        console.print(f"\n[yellow]Missing loops: {', '.join(sorted(missing_cron))}[/yellow]")
        console.print("[dim]Run `traderbot cron setup --agent <id>` to register missing loops.[/dim]")

    all_healthy = all(r.get("healthy", False) for r in loop_results if r["registered"]) and not missing_cron
    if all_healthy:
        console.print("\n[green]All registered loops are healthy.[/green]")
    elif not missing_cron:
        console.print("\n[yellow]Some loops have issues. Check `openclaw cron show <job-id> --json` for details.[/yellow]")

    has_issues = not all_healthy
    if has_issues:
        raise typer.Exit(1)


def _check_updates_on_startup() -> None:
    """Check for updates on startup if configured."""
    try:
        from traderbot.update_config import UpdateConfig
        from traderbot.updater import check_for_updates

        config = UpdateConfig.load()
        if not config.enabled or not config.check_on_startup:
            return

        result = check_for_updates(check_interval_hours=config.check_interval_hours)
        if result:
            Console().print(
                f"[dim]Update available: v{result['current']} -> v{result['latest']}. "
                f"Run 'traderbot update apply' to update.[/dim]"
            )
    except Exception:
        pass


@app.command()
def uninstall(
    remove_data: Annotated[
        bool | None,
        typer.Option("--remove-data", help="Remove user data too (profiles, DBs, .env)"),
    ] = None,
) -> None:
    """Remove all TraderBot system files, services, and OpenClaw integration.

    System files are always removed (install dir, symlink, services, cron).
    User data (profiles, DBs, .env, keys) is preserved unless --remove-data is set
    or you confirm interactively.
    """
    import platform
    import subprocess

    console = Console()
    install_dir = Path.home() / "traderbot"
    data_dir = Path.home() / ".traderbot"
    symlink = Path("/usr/local/bin/traderbot")

    removed: list[str] = []
    skipped: list[str] = []

    console.print("\n[bold red]TraderBot Uninstaller[/bold red]\n")

    # --- System services ---
    console.print("[bold]Step 1: Stop and remove services[/bold]")
    if platform.system() == "Darwin":
        daemon_dir = Path("/Library/LaunchDaemons")
        plists = list(daemon_dir.glob("com.traderbot.agent.*.plist")) if daemon_dir.exists() else []
        for plist in plists:
            label = plist.stem
            subprocess.run(["sudo", "launchctl", "bootout", f"system/{label}"], capture_output=True)
            subprocess.run(["sudo", "rm", "-f", str(plist)], capture_output=True)
            removed.append(str(plist))
        if not plists:
            skipped.append("No launchd plists found")
    else:
        service_dir = Path("/etc/systemd/system")
        services = list(service_dir.glob("traderbot-agent@*.service")) if service_dir.exists() else []
        for svc in services:
            unit = svc.name
            subprocess.run(["sudo", "systemctl", "stop", unit], capture_output=True)
            subprocess.run(["sudo", "systemctl", "disable", unit], capture_output=True)
            subprocess.run(["sudo", "rm", "-f", str(svc)], capture_output=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
            removed.append(str(svc))
        if not services:
            skipped.append("No systemd services found")

    # --- OpenClaw cron entries ---
    console.print("[bold]Step 2: Remove OpenClaw cron entries[/bold]")
    if _find_openclaw():
        for loop_name in ["decision_loop", "heartbeat_loop", "news_loop"]:
            result = subprocess.run(
                ["openclaw", "cron", "remove", "--name", loop_name],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                removed.append(f"cron:{loop_name}")
            else:
                skipped.append(f"cron:{loop_name} (not found or failed)")
    else:
        skipped.append("OpenClaw not found (cron entries must be removed manually)")

    # --- OpenClaw agent config ---
    console.print("[bold]Step 3: Clean TraderBot from OpenClaw agents[/bold]")
    oc_config = Path.home() / ".openclaw" / "openclaw.json"
    if oc_config.exists():
        try:
            config_data = json_lib.loads(oc_config.read_text())
            agents_list = config_data.get("agents", {}).get("list", [])
            cleaned = 0
            for agent in agents_list:
                if "heartbeat" in agent and agent["heartbeat"].get("lightContext"):
                    agent.pop("heartbeat", None)
                    cleaned += 1
            if cleaned:
                config_data["agents"]["list"] = agents_list
                oc_config.write_text(json_lib.dumps(config_data, indent=2) + "\n")
                removed.append(f"openclaw.json (cleaned heartbeat from {cleaned} agent(s))")
            else:
                skipped.append("No TraderBot heartbeat config found in agents")
        except Exception as e:
            skipped.append(f"openclaw.json parse error: {e}")
    else:
        skipped.append("No openclaw.json found")

    # --- Symlink ---
    console.print("[bold]Step 4: Remove symlink[/bold]")
    if symlink.is_symlink() or symlink.exists():
        try:
            symlink.unlink()
            removed.append(str(symlink))
        except PermissionError:
            subprocess.run(["sudo", "rm", "-f", str(symlink)], capture_output=True)
            removed.append(str(symlink))
    else:
        skipped.append("No /usr/local/bin/traderbot symlink")

    # --- Install directory ---
    console.print("[bold]Step 5: Remove install directory[/bold]")
    if install_dir.exists():
        shutil.rmtree(install_dir)
        removed.append(str(install_dir))
    else:
        skipped.append(f"No install dir at {install_dir}")

    # --- User data ---
    console.print("[bold]Step 6: User data[/bold]")
    if remove_data is None:
        console.print(f"  User data at [cyan]{data_dir}[/cyan] contains profiles, DBs, .env, and PEM keys.")
        remove_data = typer.confirm("  Remove all user data too?", default=False)

    if remove_data:
        if data_dir.exists():
            shutil.rmtree(data_dir)
            removed.append(str(data_dir))
        else:
            skipped.append(f"No data dir at {data_dir}")
    else:
        skipped.append(f"User data preserved at {data_dir}")

    # --- Summary ---
    console.print("\n[bold]Uninstall Summary[/bold]\n")
    if removed:
        console.print("[green]Removed:[/green]")
        for item in removed:
            console.print(f"  + {item}")
    if skipped:
        console.print("[dim]Skipped:[/dim]")
        for item in skipped:
            console.print(f"  - {item}")

    console.print("\n[bold green]TraderBot uninstalled.[/bold green]")
    if not remove_data:
        console.print(f"[dim]User data preserved at {data_dir}. Remove manually if desired.[/dim]")


def main() -> None:
    """Entry point for the traderbot CLI."""
    _check_updates_on_startup()
    app()


if __name__ == "__main__":
    main()
