"""Admin commands: bootstrap, heartbeat, halt, resume, backfill, cache-warm, learnings."""

from __future__ import annotations

import asyncio
import json as json_lib
import logging
import sys
import time
from pathlib import Path
from typing import Annotated

from traderbot.logging_config import configure_root_logger

logger = logging.getLogger(__name__)

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import (
    _python_version_ok,
    report_cli_error,
)
from traderbot.paths import _resolve_db_path, _with_db


def register_commands(parent_app: typer.Typer) -> None:

    @parent_app.command()
    def bootstrap(
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Validate without writing to DB")
        ] = False,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        """One-time setup wizard for new users."""
        configure_root_logger()
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
                    {
                        "error": f"Python {version_str} — 3.12.x required (chromadb dependency)",
                        "steps": steps,
                    },
                    sys.stdout,
                )
                raise typer.Exit(code=1)
            report_cli_error(f"Python {version_str} detected — 3.12.x required for chromadb dependency.")

        # Step 2: Setup data directory
        data_dir = get_data_dir()
        db_path = DB_PATH

        if not dry_run:
            data_dir.mkdir(parents=True, exist_ok=True)
            data_dir.chmod(0o700)
        steps["data_dir"] = str(data_dir)
        steps["data_dir_exists"] = data_dir.exists()

        if not json_output:
            console.print(f"[bold]Data directory:[/bold] {data_dir}")
            if dry_run:
                console.print("[dim][dry-run] Would create data directory[/dim]")
            else:
                console.print(
                    f"  {'[green]✓[/green]' if data_dir.exists() else '[red]✗[/red]'} Created"
                )

        # Step 3: Initialize database
        db_ok = False
        if not dry_run:
            try:
                with get_connection(db_path) as conn:
                    init_schema(conn)
                db_ok = True
            except Exception as e:
                steps["db_error"] = str(e)

        steps["db_path"] = str(db_path)
        steps["db_ok"] = db_ok

        if not json_output:
            if dry_run:
                console.print("[dim][dry-run] Would initialize database[/dim]")
            else:
                console.print(
                    f"  {'[green]✓[/green] Database' if db_ok else '[red]✗[/red] Database'}"
                )
                if not db_ok:
                    console.print(f"    Error: {steps.get('db_error', 'unknown')}")

        # Step 4: Check credentials
        auth_mgr = AuthManager()
        result = auth_mgr.get_credential("kalshi", "api_key")
        kalshi_ok = result is not None and result.value.get_secret_value() is not None
        steps["kalshi_configured"] = kalshi_ok

        if not json_output:
            status = "[green]✓[/green]" if kalshi_ok else "[yellow]⚠[/yellow]"
            console.print(f"  {status} Kalshi credentials")

        # Step 5: System info
        steps["platform"] = platform.system()
        steps["platform_release"] = platform.release()

        logger.info(
            "Bootstrap %s — python=%s py_ok=%s db_ok=%s kalshi=%s",
            "complete" if not dry_run else "dry-run",
            version_str,
            py_ok,
            db_ok,
            kalshi_ok,
        )
        if json_output:
            json_lib.dump(
                {"status": "ok" if (py_ok and db_ok) else "issues_found", "steps": steps},
                sys.stdout,
                default=str,
            )
        else:
            console.print(
                f"\n[{'green' if py_ok and db_ok else 'yellow'}]Bootstrap {'complete' if not dry_run else 'dry-run complete'}[/{'green' if py_ok and db_ok else 'yellow'}]"
            )
            if dry_run:
                console.print("[dim]Run without --dry-run to apply changes[/dim]")

    @parent_app.command()
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
        configure_root_logger()
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

            return asyncio.run(
                run_heartbeat_cycle(
                    conn,
                    heartbeat_path=DEFAULT_HEARTBEAT_PATH,
                    state_path=state_path,
                    dry_run=dry_run,
                )
            )

        try:
            result = _with_db(_resolve_db_path(db_path), _run)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
            if json_output:
                json_lib.dump({"error": str(exc)}, sys.stdout)
                raise typer.Exit(code=1)
            report_cli_error(f"Heartbeat failed: {exc}")

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
            console.print("  [yellow]⚠ Performance deviation detected[/yellow]")

        if decision.closed_count >= 0:
            console.print(
                f"\n[bold]Decisions[/bold] — {decision.open_count} open, "
                f"{decision.closed_count} closed"
            )

        if len(lrn.promoted) > 0:
            console.print(f"\n[bold]Learning Promotion[/bold] — {lrn.promoted_count} promoted")

        if cb.level != "NORMAL":
            console.print(f"  [yellow]⚠[/yellow] Circuit breaker: {cb.level} — {cb.reason}")

        logger.info(
            "Heartbeat complete — steps=%s trades=%d win_rate=%.0f%% pnl=%s promoted=%d cb=%s",
            ", ".join(result.steps_completed),
            perf.trade_count,
            perf.win_rate * 100,
            pnl_str,
            lrn.promoted_count,
            cb.level,
        )

    @parent_app.command()
    def halt(
        force: Annotated[bool, typer.Option("--force", help="Force halt (set FULL_STOP)")] = False,
        recover: Annotated[
            bool,
            typer.Option(
                "--recover", help="Check fresh metrics and auto-recover if conditions improved"
            ),
        ] = False,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        """Check circuit breaker status or force halt. Use --recover to trigger auto-recovery check."""
        configure_root_logger()
        from traderbot.risk.circuit_breaker import CircuitBreaker

        console = Console()
        breaker = CircuitBreaker()

        if force:
            from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreakerState

            logger.warning("Manual halt via CLI — force=%s", force)
            breaker._state = CircuitBreakerState(
                level=BreakerLevel.FULL_STOP,
                can_trade=False,
                position_size_multiplier=0.0,
                reason="Manual halt via CLI",
            )
            breaker._persist_state()

        # Trigger auto-recovery by running breaker.check() with computed metrics
        if recover:
            from traderbot.paper import compute_paper_balance
            from traderbot.profiles.runtime import get_current_profile
            from traderbot.risk.circuit_breaker import BreakerLevel

            profile = get_current_profile()
            pb = compute_paper_balance(profile) if profile else None

            # Mark-to-market: fetch current prices for open positions so drawdown
            # reflects position market value, not just cash at risk.
            if pb and pb.open_position_count > 0:

                async def _fetch_mtm() -> int:
                    from traderbot.db import get_connection
                    from traderbot.db.positions import list_open_positions
                    from traderbot.kalshi.client import KalshiClient
                    from traderbot.kalshi.markets import MarketService
                    from traderbot.paths import _resolve_db_path

                    client = KalshiClient()
                    svc = MarketService(client)
                    resolved = _resolve_db_path(None)
                    with get_connection(resolved) as conn:
                        positions = list_open_positions(conn)
                    mtm = 0
                    for pos in positions:
                        try:
                            market = await svc.get_market(pos.ticker)
                            price_cents = int(float(market.outcome_prices[0]) * 100)
                            mtm += price_cents * pos.quantity
                        except Exception:
                            logger.debug("MTM price parse failed for position %s", pos.ticker)
                    await client.close()
                    return mtm

                pb.mark_to_market_cents = asyncio.run(_fetch_mtm())

            if pb and pb.initial_cents > 0:
                daily_loss_pct = (
                    pb.initial_cents - pb.remaining_cents - pb.settled_payout_cents
                ) / max(pb.initial_cents, 1)
                if daily_loss_pct < 0:
                    daily_loss_pct = 0.0
                portfolio_value = max(pb.portfolio_value_cents, 0)
                drawdown_pct = (pb.initial_cents - portfolio_value) / max(pb.initial_cents, 1)
                if drawdown_pct < 0:
                    drawdown_pct = 0.0
                logger.info(
                    "Recovery check metrics: daily_loss=%.4f drawdown=%.4f initial=%d remaining=%d "
                    "mtm=%d portfolio_value=%d",
                    daily_loss_pct,
                    drawdown_pct,
                    pb.initial_cents,
                    pb.remaining_cents,
                    pb.mark_to_market_cents,
                    portfolio_value,
                )
                breaker.check(daily_loss_pct=daily_loss_pct, drawdown_pct=drawdown_pct)
            else:
                state = breaker.get_state()
                if state.level != BreakerLevel.NORMAL:
                    logger.info("No profile — calling breaker.check(0, 0) for auto-recovery")
                    breaker.check(daily_loss_pct=0.0, drawdown_pct=0.0)

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

    @parent_app.command()
    def resume(
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        """Resume trading after circuit breaker halt. Clears FULL_STOP/HALT state."""
        configure_root_logger()
        from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker, CircuitBreakerState

        console = Console()
        breaker = CircuitBreaker()
        breaker._state = CircuitBreakerState(
            level=BreakerLevel.NORMAL,
            can_trade=True,
            position_size_multiplier=1.0,
            reason="Manual resume via CLI",
        )
        breaker._persist_state()
        logger.warning("Circuit breaker reset to NORMAL — trading resumed")

        if json_output:
            json_lib.dump({"status": "resumed", "level": "NORMAL", "can_trade": True}, sys.stdout)
        else:
            console.print("[green]✓[/green] Trading resumed — circuit breaker cleared")

    @parent_app.command()
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
        configure_root_logger()
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
                        raise typer.Exit(code=1)
                    report_cli_error(f"No active learning found for pattern-key: {promote}")

                learning_id = active_entries[0].id
                result_path = promote_learning(conn, learning_id)
                if result_path is None:
                    logger.warning(
                        "Promotion failed for learning #%d — pattern_key=%s", learning_id, promote
                    )
                    if json_output:
                        json_lib.dump(
                            {"error": f"Promotion failed for learning #{learning_id}"}, sys.stdout
                        )
                        raise typer.Exit(code=1)
                    report_cli_error(f"Promotion failed for learning #{learning_id}")

                promoted_entry = {
                    "learning_id": learning_id,
                    "pattern_key": promote,
                    "promoted_to": str(result_path),
                }
                logger.info(
                    "Promoted pattern '%s' — learning_id=%d → %s", promote, learning_id, result_path
                )
                if json_output:
                    json_lib.dump(promoted_entry, sys.stdout, default=str)
                else:
                    console.print(f"[green]✓[/green] Promoted pattern '{promote}'")
                    console.print(f"    → {result_path}")
                return

            # Query patterns
            status_filter: LearningStatus | None = None
            if status is not None:
                try:
                    status_filter = LearningStatus(status)
                except ValueError:
                    if json_output:
                        json_lib.dump({"error": f"Invalid status: {status}"}, sys.stdout)
                        raise typer.Exit(code=1)
                    report_cli_error(f"Invalid status: {status}")

            category_filter: LearningCategory | None = None
            if category is not None:
                try:
                    category_filter = LearningCategory(category)
                except ValueError:
                    if json_output:
                        json_lib.dump({"error": f"Invalid category: {category}"}, sys.stdout)
                        raise typer.Exit(code=1)
                    report_cli_error(f"Invalid category: {category}")

            patterns = get_patterns(conn, category=category_filter)

            if json_output:
                json_lib.dump(
                    [p.model_dump(mode="json") for p in patterns], sys.stdout, default=str
                )
                return

            if not patterns:
                console.print("[yellow]No patterns found.[/yellow]")
                return

            table = Table(title="Learned Patterns")
            table.add_column("ID", justify="right")
            table.add_column("Category", style="green")
            table.add_column("Status")
            table.add_column("Confidence", justify="right")
            table.add_column("Summary")

            for p in patterns:
                table.add_row(
                    str(p.id),
                    p.category.value if p.category else "",
                    p.status.value,
                    f"{p.confidence:.2f}",
                    p.summary or "",
                )
            console.print(table)

        _with_db(_resolve_db_path(db_path), _run)

    @parent_app.command("check-settlements")
    def check_settlements(
        db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Report only — no DB writes")
        ] = False,
    ) -> None:
        from traderbot.db import get_connection, init_schema
        from traderbot.db.positions import list_all, update_settlement
        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.portfolio import PortfolioService

        console = Console()

        db_path = _resolve_db_path(db_path)
        with get_connection(db_path) as conn:
            init_schema(conn)
            local_positions = list_all(conn)
            local_tickers = {p.ticker for p in local_positions if p.settlement_result is None}

        if not local_tickers:
            if json_output:
                json_lib.dump({"checked": 0, "updated": 0, "positions": []}, sys.stdout)
            else:
                console.print("[dim]No open positions to settle.[/dim]")
            return

        async def _check() -> dict:
            try:
                client = KalshiClient()
                portfolio = PortfolioService(client)
                settlements = await portfolio.get_settlements()
                await client.close()
            except Exception as exc:
                err_msg = str(exc)
                if "401" in err_msg or "Invalid or revoked token" in err_msg:
                    logger.error("Settlements API 401 — Kalshi session token is invalid or revoked")
                    return {
                        "checked": 0,
                        "updated": 0,
                        "positions": [],
                        "error": "Settlements API 401 — run 'traderbot auth set-kalshi' to refresh credentials",
                    }
                logger.error("Settlements check failed: %s", exc)
                return {"checked": 0, "updated": 0, "positions": [], "error": err_msg}

            updated_positions: list[dict] = []
            checked = 0
            updated = 0

            for s in settlements:
                if s.ticker not in local_tickers:
                    continue
                checked += 1

                if s.settlement_price_cents == 100:
                    result = True
                elif s.settlement_price_cents == 0:
                    result = False
                else:
                    result = None

                pnl = s.pnl_cents

                if not dry_run and result is not None:
                    with get_connection(db_path) as conn:
                        did_update = update_settlement(conn, s.ticker, result, pnl)
                        if did_update:
                            updated += 1
                elif dry_run:
                    updated += 1

                updated_positions.append(
                    {
                        "ticker": s.ticker,
                        "result": result,
                        "pnl_cents": pnl,
                        "settled_at": s.settled_at.isoformat() if s.settled_at else None,
                        "dry_run": dry_run,
                    }
                )

            return {"checked": checked, "updated": updated, "positions": updated_positions}

        try:
            result = asyncio.run(_check())
        except Exception as exc:
            if json_output:
                json_lib.dump({"error": str(exc)}, sys.stdout)
                raise typer.Exit(code=1)
            report_cli_error(f"Settlement check failed: {exc}")

        if json_output:
            json_lib.dump(result, sys.stdout, default=str)
            return

        if result["checked"] == 0:
            console.print("[dim]No new settlements found for open positions.[/dim]")
        else:
            console.print(
                f"[green]✓[/green] Settlements checked: {result['checked']} — "
                f"updated: {result['updated']} (dry_run={dry_run})"
            )
            for pos in result["positions"]:
                res_label = (
                    "YES"
                    if pos["result"] is True
                    else "NO"
                    if pos["result"] is False
                    else "UNKNOWN"
                )
                console.print(
                    f"  • {pos['ticker']}: {res_label} — PnL ${pos['pnl_cents'] / 100:.2f}"
                )

    @parent_app.command("reconcile")
    def reconcile_command(
        db_path: Annotated[Path | None, typer.Option("--db", help="Override database path")] = None,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        from traderbot.db import get_connection, init_schema
        from traderbot.db.reconciliation import reconcile_all
        from traderbot.kalshi.client import KalshiClient

        console = Console()
        db = _resolve_db_path(db_path)
        with get_connection(db) as conn:
            init_schema(conn)

        async def _run() -> dict:
            client = KalshiClient()
            counts = await reconcile_all(db, client)
            await client.close()
            return counts

        try:
            result = asyncio.run(_run())
        except Exception as exc:
            if json_output:
                json_lib.dump({"error": str(exc)}, sys.stdout)
                raise typer.Exit(code=1)
            report_cli_error(f"Reconciliation failed: {exc}")

        if json_output:
            json_lib.dump(result, sys.stdout, default=str)
            return

        pos = result.get("positions", {})
        settle = result.get("settlements", {})
        console.print(
            f"[green]✓[/green] Reconciliation complete — "
            f"positions updated={pos.get('updated', 0)} closed={pos.get('closed', 0)} added={pos.get('added', 0)} | "
            f"settlements settled={settle.get('settled', 0)} skipped={settle.get('skipped', 0)}"
        )

    @parent_app.command("cache")
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
            report_cli_error(f"Unknown cache action: {action}. Use 'warm'.")

        async def _warm() -> dict[str, int]:
            from traderbot.kalshi.markets import _event_cache_ts, _event_category_cache

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
            console.print(
                f"[green]✓[/green] Event cache warmed: {result['events']} events across {result['categories']} categories"
            )
