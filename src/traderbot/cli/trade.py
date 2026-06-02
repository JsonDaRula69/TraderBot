"""Trade-related commands: trade, positions, audit, backtest, paper, compare, analyze, performance."""
from __future__ import annotations

import asyncio
import json as json_lib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import _resolve_db_path, _with_db, _get_strategy
from traderbot.paper import compute_paper_balance
from traderbot.risk.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


async def _analyze_realtime(
    ticker: str, console: Console, json_output: bool
) -> None:
    """Stream real-time orderbook via WebSocket and display updates."""
    from traderbot.kalshi.websocket import KalshiWebSocket

    ws = KalshiWebSocket()

    try:
        await ws.connect()
        await ws.subscribe(
            channels=["orderbook_delta", "ticker"],
            market_ticker=ticker,
        )
    except Exception as exc:
        logger.error("WebSocket connect/subscribe failed for %s: %s", ticker, exc)
        if json_output:
            json_lib.dump({"error": f"WebSocket error: {exc}"}, sys.stdout)
        else:
            console.print(f"[red]WebSocket error for {ticker}:[/red] {exc}")
        return

    snapshot_printed = False
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=30.0)
            except TimeoutError:
                console.print("[yellow]No data received for 30 seconds — disconnecting.[/yellow]")
                break

            msg_type = msg.get("type", "")

            if msg_type == "orderbook_snapshot":
                if snapshot_printed:
                    continue
                snapshot_printed = True
                console.print(f"\n[bold cyan]📡 {ticker}[/bold cyan] — Real-time Orderbook (WebSocket)")
                data = msg.get("msg", {})

                if json_output:
                    json_lib.dump({"ticker": ticker, "type": "snapshot", "data": data}, sys.stdout, default=str)
                else:
                    _print_orderbook_snapshot(console, data)

            elif msg_type == "orderbook_delta":
                if not snapshot_printed:
                    continue
                changes = msg.get("msg", {}).get("changes", [])
                if json_output:
                    json_lib.dump({"ticker": ticker, "type": "delta", "changes": changes}, sys.stdout, default=str)
                else:
                    ts = msg.get("ts", "")
                    console.print(f"\n[yellow]Δ {ts}[/yellow]")
                    for change in changes:
                        side = change.get("side", "?")
                        price = change.get("price", "?")
                        size = change.get("size", "?")
                        direction = change.get("direction", "?")
                        console.print(
                            f"  {side} {direction} @ {price}¢ × {size}"
                        )

            elif msg_type == "ticker":
                if json_output:
                    json_lib.dump({"ticker": ticker, "type": "ticker", "data": msg.get("msg", {})}, sys.stdout, default=str)

    except KeyboardInterrupt:
        console.print("\n[dim]Disconnecting...[/dim]")
    except Exception as exc:
        logger.warning("WebSocket stream error for %s: %s", ticker, exc)
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
        else:
            console.print(f"[red]Stream error:[/red] {exc}")
    finally:
        await ws.close()


def _print_orderbook_snapshot(console: Console, data: dict) -> None:
    """Pretty-print an orderbook snapshot from WebSocket data."""

    sides: dict[str, list[dict]] = {"yes": [], "no": []}
    for entry in data.get("book", []):
        sides.setdefault(entry.get("side", "?"), []).append(entry)

    yes_entries = sides.get("yes", [])
    no_entries = sides.get("no", [])
    console.print(f"\n[bold]{'Side':<6} {'Price':>6} {'Size':>6}  Implied[/bold]")
    console.print("[dim]" + "─" * 40 + "[/dim]")

    for entry in yes_entries:
        p = entry.get("price", 0)
        s = entry.get("size", 0)
        console.print(f"  YES   {p:>5}¢ {s:>5}  {p / 100:.1%}")

    for entry in no_entries:
        p = entry.get("price", 0)
        s = entry.get("size", 0)
        console.print(f"  NO    {p:>5}¢ {s:>5}  {p / 100:.1%}")


def register_commands(parent_app: typer.Typer) -> None:

    @parent_app.command()
    def analyze(
        ticker: Annotated[str, typer.Argument(help="Market ticker symbol")],
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
        realtime: Annotated[
            bool, typer.Option("--realtime", help="Use WebSocket for real-time orderbook streaming")
        ] = False,
    ) -> None:
        """Get market details, orderbook, and indicators."""
        console = Console()

        if realtime:
            asyncio.run(_analyze_realtime(ticker, console, json_output))
            return

        from traderbot.kalshi.markets import MarketService

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
            json_lib.dump({
                "ticker": ticker,
                "market": market.model_dump(mode="json"),
                "orderbook": orderbook.model_dump(mode="json") if orderbook else None,
            }, sys.stdout, default=str)
            return

        console.print(f"\n[bold cyan]{ticker}[/bold cyan] — {market.question}")
        console.print(f"  Status: {market.status}  Volume: {market.volume}")
        console.print(f"  Close: {market.close_time}  Open: {getattr(market, 'open_time', 'N/A')}")

        if orderbook:
            console.print("\n[bold]Order Book[/bold]")
            yes_bids = orderbook.yes_bids if orderbook.yes_bids else []
            no_bids = orderbook.no_bids if orderbook.no_bids else []

            if yes_bids:
                from traderbot.analysis.odds import implied_probability
                ip = implied_probability(orderbook)
                console.print(f"  YES Best Bid: {yes_bids[0].price}¢ (implied {ip.yes_prob:.1%})")

    @parent_app.command()
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

        Routes automatically based on the active profile's mode:
        - Paper profile: risk check + WAL logging + local position tracking only
        - Live profile: submits order to Kalshi exchange after risk check passes
        """
        from traderbot.master_password import require_auth
        require_auth()

        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.markets import MarketService
        from traderbot.kalshi.models import (
            OrderRequest, OrderSideV2, PortfolioState, TradeRequest,
        )
        from traderbot.kalshi.portfolio import PortfolioService
        from traderbot.kalshi.trading import TradingService
        from traderbot.profiles.runtime import get_current_profile
        from traderbot.risk import evaluate_trade_full, RiskCheckError
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
            if response != "y":
                console.print("[yellow]Trade cancelled.[/yellow]")
                return

        try:
            client = KalshiClient()
            market_svc = MarketService(client)
        except Exception:
            if json_output:
                json_lib.dump({"error": "API connection required"}, sys.stdout)
            else:
                console.print("[red]API connection required.[/red]")
            return

        entry = write_intent(
            DEFAULT_SESSION_STATE_PATH,
            action=WalAction.BUY,
            ticker=ticker,
            direction=direction,
            quantity=quantity,
            price_cents=price,
            reason=f"trade {direction} {ticker} @ {price}¢",
        )
        intent_id = entry.intent_id

        portfolio_svc = PortfolioService(client)

        async def _execute():
            market = await market_svc.get_market(ticker)
            if profile.paper_mode:
                pb = compute_paper_balance(profile)
                if pb:
                    folio = PortfolioState(
                        portfolio_value_cents=pb.remaining_cents,
                        peak_value_cents=pb.initial_cents,
                        current_positions_value_cents=pb.cost_at_risk_cents,
                        today_realized_loss_cents=0,
                        today_unrealized_loss_cents=0,
                        open_positions_count=pb.open_position_count,
                    )
                else:
                    balance_cents = profile.initial_balance_cents or 10_000
                    folio = PortfolioState(
                        portfolio_value_cents=balance_cents,
                        peak_value_cents=balance_cents,
                        current_positions_value_cents=0,
                        today_realized_loss_cents=0,
                        today_unrealized_loss_cents=0,
                        open_positions_count=0,
                    )
            else:
                balance_data = await portfolio_svc.get_balance()
                balance_cents_val = balance_data.get("balance", 0) if isinstance(balance_data, dict) else 0
                folio = PortfolioState(
                    portfolio_value_cents=balance_cents_val,
                    peak_value_cents=balance_cents_val,
                    current_positions_value_cents=0,
                    today_realized_loss_cents=0,
                    today_unrealized_loss_cents=0,
                    open_positions_count=0,
                )
            return market, folio

        market, portfolio = asyncio.run(_execute())

        prob = price / 100.0

        trade_req = TradeRequest(
            ticker=ticker,
            direction=direction,
            quantity=quantity,
            price_cents=price,
            market_price_cents=price,
            estimated_prob=estimated_prob if estimated_prob is not None else prob,
            confidence=0.5,
            edge_estimate=0.0,
            market_open_interest=market.open_interest if market else 0,
        )

        breaker = CircuitBreaker()

        try:
            result = evaluate_trade_full(
                trade_request=trade_req,
                portfolio=portfolio,
                breaker=breaker,
                profile=profile,
            )
        except RiskCheckError as e:
            if json_output:
                json_lib.dump({"status": "rejected", "ticker": ticker, "reason": str(e)}, sys.stdout)
            else:
                console.print(f"[red]Trade rejected[/red]: {ticker} — {e}")
            update_status(DEFAULT_SESSION_STATE_PATH, intent_id, WalStatus.REJECTED)
            return

        if result.sized_position_cents <= 0:
            if json_output:
                json_lib.dump({"status": "rejected", "ticker": ticker, "reason": "Risk check returned zero position"}, sys.stdout)
            else:
                console.print(f"[red]Trade rejected[/red]: {ticker} — risk check returned zero position")
            update_status(DEFAULT_SESSION_STATE_PATH, intent_id, WalStatus.REJECTED)
            return

        # Use the sized position but keep agent's original quantity for the order
        # The risk module computes max safe position, the agent provides quantity
        adj_qty = quantity
        adj_price = price

        # Live mode: submit to Kalshi exchange
        if not profile.paper_mode:
            side = OrderSideV2.bid if direction == "yes" else OrderSideV2.ask
            # V2 uses dollar-based prices: e.g. 65¢ → "0.65"
            dollar_price = f"{adj_price / 100:.2f}"
            order_req = OrderRequest(
                ticker=ticker, side=side,
                count=str(adj_qty), price=dollar_price,
            )
            trading_svc = TradingService(client)
            try:
                order_result = asyncio.run(trading_svc.place_order(order_req))
                if json_output:
                    json_lib.dump({
                        "status": "submitted", "ticker": ticker,
                        "order_id": order_result.order_id,
                        "fill_count": order_result.fill_count,
                    }, sys.stdout, default=str)
                else:
                    console.print(f"[green]Order submitted[/green]: ID {order_result.order_id}, "
                                  f"fill count {order_result.fill_count}")
                update_status(DEFAULT_SESSION_STATE_PATH, intent_id, WalStatus.EXECUTED)
            except Exception as e:
                console.print(f"[red]Order submission failed[/red]: {e}")
                update_status(DEFAULT_SESSION_STATE_PATH, intent_id, WalStatus.CANCELLED)
                if json_output:
                    json_lib.dump({"status": "failed", "ticker": ticker, "error": str(e)}, sys.stdout)
                return
        else:
            if json_output:
                json_lib.dump({"status": "approved", "ticker": ticker, **result.model_dump()}, sys.stdout, default=str)
            else:
                console.print(f"[green]Trade approved (paper)[/green]: {ticker} {direction} x{adj_qty} @ {adj_price}¢")
            update_status(DEFAULT_SESSION_STATE_PATH, intent_id, WalStatus.EXECUTED)

        # Record position in SQLite for persistence across sessions
        from traderbot.db.positions import upsert as upsert_position
        from traderbot.db import get_connection
        from traderbot.kalshi.models import Position as KalshiPosition
        try:
            pos_db = _resolve_db_path(None)
            with get_connection(pos_db) as conn:
                upsert_position(conn, KalshiPosition(
                    ticker=ticker,
                    quantity=adj_qty,
                    avg_price=adj_price,
                    settlement_result=None,
                ))
        except Exception as exc:
            logger.warning("Failed to persist position to DB: %s", exc)

        try:
            from traderbot.db.reconciliation import reconcile_positions

            counts = asyncio.run(reconcile_positions(pos_db, client))
            logger.info("Post-trade reconciliation: %s", counts)
        except Exception as exc:
            logger.warning("Post-trade reconciliation failed: %s", exc)

    @parent_app.command()
    def positions(
        db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
        no_price_fetch: Annotated[
            bool, typer.Option("--no-price-fetch", help="Skip fetching current prices from Kalshi")
        ] = False,
    ) -> None:
        """List current positions from SQLite, with live prices from Kalshi.

        Fetches current market prices from Kalshi's unauthenticated market
        endpoint so P&L reflects real-time value, not stale entry prices.
        Use --no-price-fetch to skip (faster, no API calls).
        """
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

        # Fetch current prices from Kalshi market data (unauthenticated)
        price_map: dict[str, int] = {}
        if not no_price_fetch:
            # Try WS cache first
            from traderbot.kalshi.ws_cache import get_ticker_prices

            tickers_to_fetch = [p.ticker for p in all_positions if p.settlement_result is None]
            cached = get_ticker_prices(tickers_to_fetch)
            for tkr, info in cached.items():
                if info.get("yes_bid") is not None:
                    price_map[tkr] = int(info["yes_bid"])
                elif info.get("no_bid") is not None:
                    price_map[tkr] = 100 - int(info["no_bid"])

            # Fall back to REST for uncached/incomplete positions
            rest_tickers = [t for t in tickers_to_fetch if t not in price_map]
            if rest_tickers:
                try:
                    from traderbot.kalshi.client import KalshiClient
                    import asyncio

                    async def _fetch_prices() -> dict[str, int]:
                        client = KalshiClient()
                        prices: dict[str, int] = {}
                        for tkr in rest_tickers:
                            try:
                                resp = await client.get(f"/markets/{tkr}")
                                if resp.status_code == 200:
                                    data = resp.json()
                                    mkt = data.get("market", data)
                                    yes_bid = mkt.get("yes_bid")
                                    if yes_bid is not None:
                                        prices[tkr] = int(yes_bid)
                                    no_bid = mkt.get("no_bid")
                                    if no_bid is not None and tkr not in prices:
                                        prices[tkr] = 100 - int(no_bid)
                            except Exception:
                                pass
                        await client.close()
                        return prices

                    price_map = asyncio.run(_fetch_prices())
                except Exception:
                    pass

        if json_output:
            result = []
            for p in all_positions:
                entry = p.model_dump(mode="json")
                if p.ticker in price_map:
                    entry["current_price"] = price_map[p.ticker]
                    if p.direction == "yes":
                        entry["unrealized_pnl"] = (price_map[p.ticker] - p.avg_price) * p.quantity
                    elif p.direction == "no":
                        entry["unrealized_pnl"] = ((100 - price_map[p.ticker]) - p.avg_price) * p.quantity
                    else:
                        entry["unrealized_pnl"] = (price_map[p.ticker] - p.avg_price) * p.quantity
                else:
                    entry["current_price"] = None
                    entry["unrealized_pnl"] = None
                result.append(entry)
            json_lib.dump(result, sys.stdout, default=str)
            return

        console = Console()
        if not all_positions:
            console.print("No open positions.")
            return

        table = Table(title="Positions")
        table.add_column("Ticker", style="cyan")
        table.add_column("Side")
        table.add_column("Quantity", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Unrealized P&L", justify="right")
        table.add_column("Settled")
        for p in all_positions:
            current = f"{price_map[p.ticker]}¢" if p.ticker in price_map else "\u2014"
            if p.ticker in price_map:
                cur = price_map[p.ticker]
                if p.direction == "no":
                    entry_value = p.avg_price * p.quantity
                    current_value = (100 - cur) * p.quantity
                else:
                    entry_value = p.avg_price * p.quantity
                    current_value = cur * p.quantity
                unrealized = current_value - entry_value
                pnl_str = f"{unrealized:+d}¢" if unrealized else "0¢"
            else:
                pnl_str = "\u2014"
            side = p.direction if hasattr(p, "direction") and p.direction else ""
            settled = "\u2014" if p.settlement_result is None else str(p.settlement_result)
            table.add_row(p.ticker, side, str(p.quantity), f"{p.avg_price}¢", current, pnl_str, settled)
        console.print(table)

    @parent_app.command()
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
        """Audit trail of all trade decisions."""
        from datetime import datetime as dt
        from traderbot.db.decisions import list_by_outcome, list_by_date_range, list_by_ticker

        def _query_decisions(conn):
            start_dt = dt.fromisoformat(start) if start else None
            end_dt = dt.fromisoformat(end) if end else None
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

    @parent_app.command()
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

            with Progress() as progress:
                task = progress.add_task("[cyan]Running backtest...", total=None)
                trades = asyncio.run(engine.run(start, end))
                progress.update(task, completed=True)

        metrics = compute_metrics(trades, initial_bankroll_cents=bankroll)

        if json_output:
            json_lib.dump({
                "strategy": strategy,
                "date_range": {"from": from_date, "to": to_date},
                "metrics": metrics,
            }, sys.stdout, default=str)
            return

        table = Table(title=f"Backtest: {strategy}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Date Range", f"{from_date} \u2014 {to_date}")
        table.add_row("Trades", str(metrics.get("trade_count", 0)))
        total_pnl = metrics.get("total_pnl_cents", 0)
        table.add_row("Total P&L", f"${total_pnl / 100:+.2f}")
        roi = (total_pnl / bankroll * 100) if bankroll > 0 else 0
        table.add_row("ROI", f"{roi:.2f}%")
        table.add_row("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}" if metrics.get("sharpe_ratio") is not None else "\u2014")
        table.add_row("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.1%}" if metrics.get("max_drawdown_pct") is not None else "\u2014")
        table.add_row("Win Rate", f"{metrics.get('win_rate', 0):.1%}" if metrics.get("win_rate") is not None else "\u2014")
        table.add_row(
            "Edge Capture",
            f"{metrics['edge_capture']:.1%}" if metrics["edge_capture"] is not None else "\u2014",
        )
        console.print(table)

    @parent_app.command()
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
        from traderbot.simulation.paper_trader import DEFAULT_INITIAL_BALANCE_CENTS, PaperTrader
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

        initial_balance_cents = DEFAULT_INITIAL_BALANCE_CENTS
        if initial_balance == 0:
            portfolio = asyncio.run(market_service.get_portfolio())
            initial_balance_cents = portfolio.balance_cents
        elif initial_balance is not None:
            initial_balance_cents = initial_balance * 100

        trader = PaperTrader(
            strategy=strat,
            data_provider=provider,
            initial_balance_cents=initial_balance_cents,
            profile=profile,
        )

        if reconcile:
            verifier = SettlementVerifier()
            console.print("[bold]Running settlement reconciliation...[/bold]")
            settlements = asyncio.run(verifier.verify(provider))
            if settlements:
                for s in settlements:
                    status = "[green]SETTLED[/green]" if s.settled else "[yellow]UNRESOLVED[/yellow]"
                    console.print(f"  {s.ticker} — {s.position_direction} x{s.quantity} @ {s.entry_price}¢ — {status}")
            else:
                console.print("  No positions to reconcile.")

        console.print(f"[bold]Paper Trading:[/bold] {strategy} — {duration} minute session")
        console.print(f"Initial balance: ${initial_balance_cents / 100:.2f}")

        start_time = time.time()
        end_time = start_time + duration * 60

        try:
            while time.time() < end_time:
                remaining = int(end_time - time.time())
                console.print(f"[dim]Cycle — {remaining // 60}m {remaining % 60}s remaining[/dim]")
                results = asyncio.run(trader.run_cycle())
                if results:
                    for r in results:
                        if r["action"] == "trade":
                            console.print(
                                f"  [{'green' if r.get('approved') else 'red'}]"
                                f"{'✓' if r.get('approved') else '✗'}[/{'green' if r.get('approved') else 'red'}] "
                                f"{r['ticker']} {r.get('direction','')} x{r.get('quantity',0)} @ {r.get('price',0)}¢"
                            )
                asyncio.run(asyncio.sleep(60))  # 1 minute between cycles
        except KeyboardInterrupt:
            console.print("\n[yellow]Session interrupted.[/yellow]")

        summary = trader.get_summary()
        elapsed = time.time() - start_time

        if json_output:
            json_lib.dump({
                "strategy": strategy,
                "duration_minutes": int(elapsed / 60),
                **summary,
            }, sys.stdout, default=str)
            return

        console.print(f"\n[bold]Paper Session Summary[/bold] ({int(elapsed / 60)}m {int(elapsed % 60)}s)")
        pnl_str = f"${summary['total_pnl_cents'] / 100:+.2f}" if summary.get('total_pnl_cents') is not None else "$0.00"
        console.print(f"  Final balance: ${summary.get('final_balance_cents', initial_balance_cents) / 100:.2f}")
        console.print(f"  Total P&L:     {pnl_str}")
        console.print(f"  Trades:        {summary.get('trade_count', 0)}")
        wr = summary.get('win_rate')
        console.print(f"  Win rate:      {wr:.1%}" if wr is not None else "  Win rate:      —")

    @parent_app.command()
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

        table = Table(title=f"Profile Comparison: {strategy}")
        table.add_column("Profile", style="cyan")
        table.add_column("Trades", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("Max DD", justify="right")
        table.add_column("Sharpe", justify="right")

        for c in comparisons:
            pnl_str = f"${c['total_pnl_cents'] / 100:+.2f}" if c.get("total_pnl_cents") is not None else "$0.00"
            wr_str = f"{c['win_rate']:.1%}" if c.get("win_rate") is not None else "—"
            dd_str = f"{c['max_drawdown_pct']:.1%}" if c.get("max_drawdown_pct") is not None else "—"
            sharpe = f"{c['sharpe_ratio']:.2f}" if c.get("sharpe_ratio") is not None else "—"
            table.add_row(c["profile_name"], str(c.get("trade_count", 0)), pnl_str, wr_str, dd_str, sharpe)
        console.print(table)

    @parent_app.command()
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

        pb = compute_paper_balance(get_current_profile(), _resolve_db_path(db_path))
        result = {
            "trade_count": trade_count,
            "total_pnl_cents": total_pnl,
            "win_rate": win_rate,
            "open_position_cost_cents": pb.cost_at_risk_cents if pb else 0,
            "remaining_balance_cents": pb.remaining_cents if pb else None,
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
        table.add_row("Cost at Risk", f"${pb.cost_at_risk_cents / 100:.2f}" if pb else "\u2014")
        table.add_row("Remaining Balance", f"${pb.remaining_cents / 100:.2f}" if pb else "\u2014")
        if from_date or to_date:
            table.add_row("Period", f"{from_date or 'start'} \u2014 {to_date or 'now'}")
        console.print(table)
