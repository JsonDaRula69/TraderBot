"""Data pipeline commands: forecasts, signals, and historical bias."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import asyncio
import json as json_lib
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import err_console

data_app = typer.Typer(
    name="data",
    help="Data pipeline: weather forecasts, signals, and historical bias.",
    rich_markup_mode="rich",
)


@data_app.command("forecasts")
def forecasts_cmd(
    cities: Annotated[
        str,
        typer.Option(
            "--cities",
            help="Comma-separated city codes (e.g. NYC,LA,CHI)",
        ),
    ] = "NYC,LA,CHI",
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List recent weather forecasts with NWS + GFS/ECMWF/GEM ensemble data."""
    from traderbot.data.weather.provider import WeatherDataProvider

    console = Console()
    city_list = [c.strip().upper() for c in cities.split(",") if c.strip()]

    try:
        provider = WeatherDataProvider()
        forecasts = asyncio.run(provider.get_forecasts(city_list))
        # Fetch ensemble consensus for each city
        consensus_map: dict[str, dict] = {}
        for city in forecasts:
            try:
                cons = asyncio.run(provider.get_model_consensus(city))
                consensus_map[city] = {
                    "models_used": cons.models_used,
                    "mean_temp": cons.mean_temp,
                    "std_dev": cons.std_dev,
                    "spread": cons.spread,
                    "agreement_score": cons.agreement_score,
                }
            except Exception as exc:
                logger.debug("No ensemble data for %s: %s", city, exc)
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
        else:
            err_console.print(f"[red]Failed to fetch forecasts:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if json_output:
        result: dict[str, dict] = {}
        for city, fc in forecasts.items():
            entry = fc.model_dump(mode="json")
            if city in consensus_map:
                entry["ensemble"] = consensus_map[city]
            result[city] = entry
        json_lib.dump(result, sys.stdout, default=str)
        return

    table = Table(title="Weather Forecasts")
    table.add_column("City", style="cyan")
    table.add_column("NWS High (°F)", justify="right")
    table.add_column("GFS High (°F)", justify="right")
    table.add_column("ECMWF High (°F)", justify="right")
    table.add_column("GEM High (°F)", justify="right")
    table.add_column("Spread (°F)", justify="right")
    table.add_column("Agreement", justify="right")
    for city, fc in forecasts.items():
        ens = consensus_map.get(city, {})
        models = ens.get("models_used", [])
        gfs = fc.temperature_high if "gfs_seamless" in models else "N/A"
        ecmwf = fc.temperature_high if "ecmwf_ifens" in models else "N/A"
        gem = fc.temperature_high if "gem_global" in models else "N/A"
        table.add_row(
            city,
            str(fc.temperature_high),
            str(gfs),
            str(ecmwf),
            str(gem),
            str(ens.get("spread", "N/A")),
            f"{ens.get('agreement_score', 'N/A'):.2f}" if isinstance(ens.get("agreement_score"), float) else "N/A",
        )
    console.print(table)


@data_app.command("signals")
def signals_cmd(
    category: Annotated[
        str,
        typer.Option("--category", help="Market category (default: weather)"),
    ] = "weather",
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Compute and display trading signals from weather data."""
    from traderbot.data.weather.provider import WeatherDataProvider
    from traderbot.data.weather.signals import WeatherSignalEngine

    console = Console()
    cities = ["New York", "Chicago", "Los Angeles", "Phoenix", "Seattle",
              "Denver", "Houston", "Miami", "Atlanta", "Boston",
              "Dallas", "Philadelphia", "Minneapolis", "Detroit", "San Francisco"]

    try:
        provider = WeatherDataProvider()
        forecasts = asyncio.run(provider.get_forecasts(cities))
        engine = WeatherSignalEngine()
        results = engine.compute_signals(forecasts=forecasts, markets={})
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
        else:
            err_console.print(f"[red]Signal computation failed:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if json_output:
        json_lib.dump(results, sys.stdout, default=str)
        return

    if not results:
        console.print("[yellow]No signals computed.[/yellow]")
        return

    table = Table(title="Weather Signals")
    table.add_column("Ticker", style="cyan")
    table.add_column("Direction", style="bold")
    table.add_column("Est. Prob", justify="right")
    table.add_column("Market Prob", justify="right")
    table.add_column("Edge (¢)", justify="right")
    table.add_column("Confidence", justify="right")
    for r in results:
        direction = r.get("direction", "neutral")
        direction_style = {"yes": "green", "no": "red", "neutral": "yellow"}.get(
            direction, ""
        )
        table.add_row(
            r.get("ticker", "?"),
            f"[{direction_style}]{direction}[/{direction_style}]",
            f'{r.get("estimated_prob", 0):.3f}',
            f'{r.get("market_prob", 0):.3f}',
            str(r.get("edge_cents", 0)),
            f'{r.get("confidence", 0):.2f}',
        )
    console.print(table)


@data_app.command("bias")
def bias_cmd(
    city: Annotated[
        str, typer.Argument(help="City code (e.g. NYC, CHI, LA)")
    ],
    days: Annotated[
        int, typer.Option("--days", help="Days of history to analyze (default: 90)")
    ] = 90,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Show historical forecast bias for a city."""
    from traderbot.data.weather.provider import WeatherDataProvider
    from traderbot.db import get_connection
    from traderbot.db.forecast_bias import init_table

    console = Console()
    city_code = city.strip().upper()

    # Ensure forecast_bias table exists
    try:
        with get_connection() as conn:
            init_table(conn)
    except Exception:
        pass

    try:
        provider = WeatherDataProvider()
        result = asyncio.run(
            provider.get_historical_bias(city=city_code, days=days)
        )
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
        else:
            err_console.print(f"[red]Bias analysis failed:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    direction = result.get("bias_direction", "")
    direction_style = {
        "over": "red",
        "under": "blue",
        "neutral": "yellow",
    }.get(direction, "")

    table = Table(
        title=f"Historical Forecast Bias — {result.get('city', city_code)}"
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Mean Error (°F)", f'{result.get("mean_error", 0):+.2f}')
    table.add_row("MAE (°F)", f'{result.get("mae", 0):.2f}')
    table.add_row(
        "Direction",
        f"[{direction_style}]{direction}[/{direction_style}]",
    )
    table.add_row("Sample Size", str(result.get("sample_size", 0)))
    console.print(table)
