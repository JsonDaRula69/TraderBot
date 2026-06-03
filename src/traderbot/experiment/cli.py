"""CLI sub-app for experiment management (Typer).

Supports 5 subcommands: populate, verify, run, results, list-treatments.
Default output is JSON for agent consumption. Exit codes:
  0 = success (or no improvement detected)
  1 = failure
  2 = statistically significant improvement detected
"""

from __future__ import annotations

import json as json_lib
import logging
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from traderbot.experiment.harness import Harness
from traderbot.experiment.populate import populate_cmd
from traderbot.llm.client import LLMClient
from traderbot.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".traderbot" / "experiments" / "experiment.db"

experiment_app = typer.Typer(
    name="experiment",
    help="A/B test experiment harness: populate, run, score, and list treatments.",
    rich_markup_mode="rich",
)

err_console = Console(stderr=True)
_output_console = Console()


def _resolve_db(db_path: Path | None) -> Path:
    """Resolve DB path with default fallback, ensuring parent dir exists."""
    resolved = db_path or _DEFAULT_DB
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_json(data: dict) -> None:
    """Write JSON to stdout."""
    json_lib.dump(data, sys.stdout, indent=2, default=str)
    print()


@experiment_app.callback()
def experiment_callback(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON (default for agent consumption)"),
    ] = True,
) -> None:
    """Experiment management: A/B test harness for prediction-market treatments."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output


@experiment_app.command("populate")
def experiment_populate(
    ctx: typer.Context,
    category: Annotated[
        str,
        typer.Option("--category", "-c", help="Market category prefix (e.g. KXHIGH)"),
    ] = "KXHIGH",
    max_markets: Annotated[
        int,
        typer.Option("--max-markets", "-m", help="Maximum number of markets to fetch"),
    ] = 200,
    db: Annotated[
        Path,
        typer.Option("--db", "-d", help="Database path", envvar="EXPERIMENT_DB"),
    ] = _DEFAULT_DB,
) -> None:
    """Populate the experiment database with market data from Kalshi + Open-Meteo."""
    is_json = ctx.parent.obj.get("json_output", True) if ctx.parent else True

    db_path = _resolve_db(db)

    try:
        count = populate_cmd(db_path=str(db_path), max_markets=max_markets, category=category)
    except Exception as e:
        if is_json:
            _write_json({"status": "error", "error": str(e)})
        else:
            err_console.print(f"[red]Populate failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    if is_json:
        _write_json({"status": "ok", "db": str(db_path), "markets_stored": count})
    else:
        _output_console.print(f"[green]Populate completed:[/green] {count} markets stored")


@experiment_app.command("verify")
def experiment_verify(
    ctx: typer.Context,
    db: Annotated[
        Path,
        typer.Option("--db", "-d", help="Database path", envvar="EXPERIMENT_DB"),
    ] = _DEFAULT_DB,
) -> None:
    """Verify experiment database: market counts, forecast/price coverage."""
    is_json = ctx.parent.obj.get("json_output", True) if ctx.parent else True

    db_path = _resolve_db(db)
    if not db_path.exists():
        output = {"status": "error", "error": f"Database not found: {db_path}"}
        if is_json:
            _write_json(output)
        else:
            _output_console.print(f"[red]Database not found:[/red] {db_path}")
        raise typer.Exit(code=1)

    try:
        conn = sqlite3.connect(str(db_path))
        from traderbot.db.experiment_schema import create_tables

        create_tables(conn)

        market_count = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        forecast_tickers = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM forecast_snapshots"
        ).fetchone()[0]
        price_tickers = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM market_prices WHERE timestep = 0"
        ).fetchone()[0]
        settled = conn.execute(
            "SELECT COUNT(*) FROM markets WHERE settlement_result IS NOT NULL"
        ).fetchone()[0]
        conn.close()
    except Exception as e:
        err_console.print(f"[red]Verification failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    result = {
        "status": "ok",
        "db": str(db_path),
        "markets": market_count,
        "forecast_coverage": forecast_tickers,
        "price_coverage": price_tickers,
        "settled": settled,
    }

    if is_json:
        _write_json(result)
    else:
        _output_console.print("[green]Data verification:[/green]")
        _output_console.print(f"  Markets: {market_count}")
        _output_console.print(f"  Forecast coverage: {forecast_tickers}")
        _output_console.print(f"  Price coverage: {price_tickers}")
        _output_console.print(f"  Settled: {settled}")


@experiment_app.command("run")
def experiment_run(
    treatments: Annotated[
        str | None,
        typer.Option(
            "--treatments", "-t", help="Comma-separated treatment names (registered in registry)"
        ),
    ] = None,
    control: Annotated[
        str | None,
        typer.Option("--control", help="Control treatment name (default: control)"),
    ] = "control",
    replicates: Annotated[
        int,
        typer.Option("--replicates", "-r", help="Number of replicates per market"),
    ] = 3,
    seed: Annotated[
        int,
        typer.Option("--seed", "-s", help="Random seed for market selection"),
    ] = 42,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="LLM model identifier"),
    ] = "glm-5.1:cloud",
    db: Annotated[
        Path,
        typer.Option("--db", "-d", help="Database path", envvar="EXPERIMENT_DB"),
    ] = _DEFAULT_DB,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional path to write results JSON"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--output-format", help="Output format: json or text"),
    ] = "json",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate treatments and preview without LLM calls"),
    ] = False,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Unique run identifier (auto-generated if omitted)"),
    ] = None,
) -> None:
    """Run a within-subjects experiment over prediction-market treatments.

    After the harness completes, results are automatically scored via
    score_run() and output to stdout (and optionally to --output).
    """
    is_json = output_format == "json"
    _run_id = run_id or str(uuid.uuid4())
    db_path = _resolve_db(db)

    try:
        from traderbot.experiment.registry import discover_treatments, get_treatment
    except ImportError as err:
        err_console.print("[red]Error:[/red] experiment registry module not available")
        raise typer.Exit(code=1) from err

    discovered = discover_treatments()
    for _class_name, cls in discovered.items():
        from traderbot.experiment.registry import register_treatment

        register_treatment(cls().name, cls)

    control_cls = get_treatment(control)
    if not control_cls:
        err_console.print(f"[red]Control treatment '{control}' not found in registry[/red]")
        raise typer.Exit(code=1)

    treatment_instances = [control_cls()]

    if treatments:
        for name in (t.strip() for t in treatments.split(",") if t.strip()):
            cls = get_treatment(name)
            if not cls:
                err_console.print(f"[red]Treatment '{name}' not found in registry[/red]")
                raise typer.Exit(code=1)
            treatment_instances.append(cls())

    if dry_run:
        _dry_run_preview(treatment_instances, db_path, seed, is_json)
        return

    if not db_path.exists():
        err_console.print(
            f"[red]Database not found:[/red] {db_path}. Run 'experiment populate' first."
        )
        raise typer.Exit(code=1)

    provider = OllamaProvider(model=model)
    llm_client = LLMClient(provider=provider)

    conn = sqlite3.connect(str(db_path))
    try:
        from traderbot.db.experiment_schema import create_tables

        create_tables(conn)

        harness = Harness(
            conn,
            llm_client,
            seed=seed,
        )

        markets_per_cell = 2
        harness.run(
            treatment_instances,
            run_id=_run_id,
            replicates=replicates,
            markets_per_cell=markets_per_cell,
        )
    except Exception as e:
        conn.close()
        err_console.print(f"[red]Harness run failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    conn.close()

    try:
        from traderbot.experiment.results import ExperimentResults, score_run

        result_list: list[ExperimentResults] = score_run(str(db_path), _run_id)  # type: ignore[arg-type]
    except ImportError:
        _output_console.print(
            "[yellow]Warning:[/yellow] results module not available — skipping scoring"
        )
        result_list = []

    response: dict = {
        "status": "completed",
        "run_id": _run_id,
        "db": str(db_path),
        "treatments": [t.name for t in treatment_instances],
    }

    any_improvement = False
    if result_list:
        response["results"] = [r.to_json() for r in result_list]
        any_improvement = any(r.improvement for r in result_list)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_lib.dumps(response, indent=2, default=str))

    exit_code = 2 if any_improvement else 0

    if is_json:
        _write_json(response)
    else:
        _output_console.print(f"[green]Run completed:[/green] {_run_id}")
        for r in result_list:
            _output_console.print(r.summary())

    raise typer.Exit(code=exit_code)


def _dry_run_preview(
    treatments: list,
    db_path: Path,
    seed: int,
    is_json: bool,
) -> None:
    """Validate treatments and show market selection preview without LLM calls."""
    try:
        from traderbot.experiment.registry import discover_treatments

        discover_treatments()
    except ImportError:
        pass

    preview = {
        "status": "dry_run",
        "treatments": [t.name for t in treatments],
        "db": str(db_path),
        "seed": seed,
    }

    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            from traderbot.db.experiment_schema import create_tables

            create_tables(conn)
            from traderbot.experiment.methodologies.db_utils import select_markets

            cells = select_markets(conn, markets_per_cell=2, seed=seed)
            conn.close()
            preview["market_preview"] = {
                "stratum_cells": len(cells),
                "total_markets": sum(len(v) for v in cells.values()),
            }
        except (ImportError, Exception):
            preview["market_preview"] = "market_selector not available"

    if is_json:
        _write_json(preview)
    else:
        _output_console.print("[green]Dry-run validation passed.[/green]")
        _output_console.print(f"  Treatments ({len(treatments)}): {[t.name for t in treatments]}")
        _output_console.print(f"  DB: {db_path}")
        _output_console.print(f"  Seed: {seed}")
        if "market_preview" in preview and isinstance(preview["market_preview"], dict):
            _output_console.print(
                f"  Market preview: {preview['market_preview']['stratum_cells']} cells, "
                f"{preview['market_preview']['total_markets']} markets"
            )


@experiment_app.command("results")
def experiment_results(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID to score (required)"),
    ],
    db: Annotated[
        Path,
        typer.Option("--db", "-d", help="Database path", envvar="EXPERIMENT_DB"),
    ] = _DEFAULT_DB,
    output_format: Annotated[
        str,
        typer.Option("--output-format", help="Output format: json or text"),
    ] = "json",
) -> None:
    """Regenerate results for a completed experiment run from the database."""
    is_json = output_format == "json"
    db_path = _resolve_db(db)

    if not db_path.exists():
        output = {"status": "error", "error": f"Database not found: {db_path}"}
        if is_json:
            _write_json(output)
        else:
            _output_console.print(f"[red]Database not found:[/red] {db_path}")
        raise typer.Exit(code=1)

    try:
        from traderbot.experiment.results import ExperimentResults, score_run

        result_list: list[ExperimentResults] = score_run(str(db_path), run_id)  # type: ignore[arg-type]
    except ImportError as e:
        err_console.print("[red]Error:[/red] results module not available")
        raise typer.Exit(code=1) from e
    except Exception as e:
        err_console.print(f"[red]Scoring failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    if not result_list:
        err_console.print(f"[red]No results found for run_id:[/red] {run_id}")
        raise typer.Exit(code=1)

    any_improvement = any(r.improvement for r in result_list)

    if is_json:
        _write_json({"results": [r.to_json() for r in result_list]})
    else:
        for r in result_list:
            _output_console.print(r.summary())

    exit_code = 2 if any_improvement else 0
    raise typer.Exit(code=exit_code)


@experiment_app.command("list-treatments")
def experiment_list_treatments(
    output_format: Annotated[
        str,
        typer.Option("--output-format", help="Output format: json or text"),
    ] = "json",
) -> None:
    """List available treatments from the registry (auto-discovered)."""
    is_json = output_format == "json"

    try:
        from traderbot.experiment.registry import discover_treatments, list_treatments

        discovered = discover_treatments()
        for _class_name, cls in discovered.items():
            from traderbot.experiment.registry import register_treatment

            register_treatment(cls().name, cls)

        names = list_treatments()
    except ImportError as err:
        err_console.print("[red]Error:[/red] experiment registry module not available")
        raise typer.Exit(code=1) from err

    if is_json:
        _write_json({"treatments": names, "count": len(names)})
    else:
        if not names:
            _output_console.print("[yellow]No treatments registered.[/yellow]")
        else:
            _output_console.print("[green]Available treatments:[/green]")
            for name in names:
                _output_console.print(f"  • {name}")
