"""Data pipeline commands: forecasts, signals, and historical bias."""

import asyncio
import json as json_lib
import logging
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import report_cli_error

logger = logging.getLogger(__name__)

from traderbot.data.models import CityForecast

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
    station: Annotated[
        str | None,
        typer.Option(
            "--station",
            help="ICAO airport station code (e.g. KLGA, KLAX) — overrides city-center coords",
        ),
    ] = None,
    offset: Annotated[
        int,
        typer.Option(
            "--offset",
            help="Day offset into forecast: 0=current, 1=tomorrow day, etc.",
        ),
    ] = 0,
    all_periods: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Return ALL NWS forecast periods (D+0 through D+6 or more)",
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """List weather forecasts with NWS + GFS/ECMWF/GEM ensemble data.

    Use --offset to request a specific forecast period (0 = current, 1 = tomorrow day, etc.).
    Use --all to return all available NWS forecast periods.
    """
    from traderbot.data.weather.provider import WeatherDataProvider

    console = Console()
    city_list = [c.strip().upper() for c in cities.split(",") if c.strip()]

    try:

        async def _run() -> (
            tuple[dict[str, CityForecast], dict[str, dict]] | dict[str, list[CityForecast]]
        ):
            provider = WeatherDataProvider()
            try:
                if all_periods:
                    return await provider.get_all_forecasts(city_list, station=station)

                forecasts = await provider.get_forecasts(city_list, station=station, offset=offset)
                # Fetch ensemble consensus for each city
                consensus_map: dict[str, dict] = {}
                for city in forecasts:
                    try:
                        cons = await provider.get_model_consensus(city, offset=offset)
                        consensus_map[city] = {
                            "models_used": cons.models_used,
                            "mean_temp": cons.mean_temp,
                            "std_dev": cons.std_dev,
                            "spread": cons.spread,
                            "agreement_score": cons.agreement_score,
                        }
                    except Exception as exc:
                        logger.debug("No ensemble data for %s: %s", city, exc)
                return forecasts, consensus_map
            finally:
                await provider.close()

        result = asyncio.run(_run())

        if all_periods:
            all_forecasts = result  # type: dict[str, list[CityForecast]]
            if json_output:
                json_result: dict[str, list[dict]] = {}
                for city, periods in all_forecasts.items():
                    json_result[city] = [fc.model_dump(mode="json") for fc in periods]
                json_lib.dump(json_result, sys.stdout, default=str)
            else:
                for city, periods in all_forecasts.items():
                    console.print(f"\n[bold cyan]{city}[/bold cyan] — {len(periods)} periods")
                    for i, fc in enumerate(periods):
                        console.print(
                            f"  [{i}] {fc.date}  High: {fc.high_temp_f}°F  Low: {fc.low_temp_f}°F  "
                            f"Precip: {fc.precip_prob:.0%}  Wind: {fc.wind_speed} mph"
                        )
            return

        forecasts, consensus_map = result  # type: dict[str, CityForecast], dict[str, dict]
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            raise typer.Exit(code=1) from None
        report_cli_error(f"Failed to fetch forecasts: {exc}")

    if json_output:
        result: dict[str, dict] = {}
        for city, fc in forecasts.items():
            entry = fc.model_dump(mode="json")
            if city in consensus_map:
                entry["ensemble"] = consensus_map[city]
            result[city] = entry
        json_lib.dump(result, sys.stdout, default=str)
        return

    table = Table(title=f"Weather Forecasts (offset={offset})")
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
        gfs = fc.high_temp_f if "gfs_seamless" in models else "N/A"
        ecmwf = fc.high_temp_f if "ecmwf_ifs" in models else "N/A"
        gem = fc.high_temp_f if "gem_global" in models else "N/A"
        table.add_row(
            city,
            str(fc.high_temp_f),
            str(gfs),
            str(ecmwf),
            str(gem),
            str(ens.get("spread", "N/A")),
            f"{ens.get('agreement_score', 'N/A'):.2f}"
            if isinstance(ens.get("agreement_score"), float)
            else "N/A",
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
    cities = [
        "New York",
        "Chicago",
        "Los Angeles",
        "Phoenix",
        "Seattle",
        "Denver",
        "Houston",
        "Miami",
        "Atlanta",
        "Boston",
        "Dallas",
        "Philadelphia",
        "Minneapolis",
        "Detroit",
        "San Francisco",
    ]

    try:

        async def _run() -> dict[str, dict]:
            provider = WeatherDataProvider()
            try:
                forecasts = await provider.get_forecasts(cities)
            finally:
                await provider.close()
            engine = WeatherSignalEngine()
            return engine.compute_signals(forecasts=forecasts, markets={})

        results = asyncio.run(_run())
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            raise typer.Exit(code=1) from None
        report_cli_error(f"Signal computation failed: {exc}")

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
        direction_style = {"yes": "green", "no": "red", "neutral": "yellow"}.get(direction, "")
        table.add_row(
            r.get("ticker", "?"),
            f"[{direction_style}]{direction}[/{direction_style}]",
            f"{r.get('estimated_prob', 0):.3f}",
            f"{r.get('market_prob', 0):.3f}",
            str(r.get("edge_cents", 0)),
            f"{r.get('confidence', 0):.2f}",
        )
    console.print(table)


@data_app.command("bias")
def bias_cmd(
    city: Annotated[str, typer.Argument(help="City code (e.g. NYC, CHI, LA)")],
    days: Annotated[
        int, typer.Option("--days", help="Days of history to analyze (default: 90)")
    ] = 90,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Show historical forecast bias for a city."""
    from traderbot.data.weather.provider import WeatherDataProvider, _resolve_city
    from traderbot.db import get_connection
    from traderbot.db.forecast_bias import init_table

    console = Console()
    city_code = city.strip().upper()

    # Resolve short codes (NYC, LA, etc.) to full city names so the query
    # matches what record-bias stores (e.g. "New York", not "NYC").
    resolved = _resolve_city(city_code)
    if resolved is None:
        report_cli_error(f"Unknown city code: {city_code}")
        raise typer.Exit(code=1)
    city_name = resolved

    # Ensure forecast_bias table exists
    try:
        with get_connection() as conn:
            init_table(conn)
    except Exception:
        logger.debug("Failed to initialize learnings table, continuing")

    try:

        async def _run() -> dict:
            provider = WeatherDataProvider()
            try:
                report = await provider.get_historical_bias(city=city_name, days=days)
                return report.model_dump()
            finally:
                await provider.close()

        result = asyncio.run(_run())
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            raise typer.Exit(code=1) from None
        report_cli_error(f"Bias analysis failed: {exc}")

    if json_output:
        json_lib.dump(result, sys.stdout, default=str)
        return

    mean_err = result.get("mean_error", 0.0)
    direction = "over" if mean_err > 0 else ("under" if mean_err < 0 else "neutral")
    direction_style = {
        "over": "red",
        "under": "blue",
        "neutral": "yellow",
    }.get(direction, "")

    table = Table(title=f"Historical Forecast Bias — {result.get('city', city_name)}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Mean Error (°F)", f"{mean_err:+.2f}")
    table.add_row("MAE (°F)", f"{result.get('mean_abs_error', 0):.2f}")
    table.add_row(
        "Direction",
        f"[{direction_style}]{direction}[/{direction_style}]",
    )
    table.add_row("Sample Size", str(result.get("total_comparisons", 0)))
    console.print(table)


@data_app.command("record-bias")
def record_bias_cmd(
    city: Annotated[
        str,
        typer.Option("--city", help="City code (e.g. NYC, CHI, LA). Repeatable."),
    ] = "NYC",
    forecast_date: Annotated[
        str | None,
        typer.Option("--date", help="Forecast date in YYYY-MM-DD format (default: today)"),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Record forecast bias by comparing NWS forecasts to actual temperatures.

    Fetches the NWS forecast and the actual high temperature from Open-Meteo
    for each city, then records the comparison in the forecast_bias SQLite
    table for bias tracking and adjustment.
    """
    console = Console()
    from datetime import UTC, datetime

    from traderbot.data.weather.provider import _CITY_MAP, WeatherDataProvider, _resolve_city

    city_codes = [c.strip().upper() for c in city.split(",") if c.strip()]
    target_date = forecast_date or datetime.now(UTC).strftime("%Y-%m-%d")

    try:

        async def _run() -> list[dict]:
            async def _fetch_actual(lat: float, lon: float) -> float | None:
                import httpx

                archive_url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max",
                    "start_date": target_date,
                    "end_date": target_date,
                    "temperature_unit": "fahrenheit",
                    "timezone": "America/New_York",
                }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(archive_url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    daily = data.get("daily", {})
                    actual_temps = daily.get("temperature_2m_max", [])
                    return actual_temps[0] if actual_temps else None

            provider = WeatherDataProvider()
            try:
                results: list[dict] = []
                for cc in city_codes:
                    resolved = _resolve_city(cc)
                    if resolved is None or resolved not in _CITY_MAP:
                        logger.warning("Unknown city: %s", cc)
                        results.append({"city": cc, "status": "skipped", "reason": "unknown city"})
                        continue

                    # Fetch NWS forecast
                    forecasts = await provider.get_forecasts([resolved])
                    fc = forecasts.get(resolved)
                    forecast_high = fc.high_temp_f if fc else None

                    # Fetch actual temperature from Open-Meteo archive API
                    lat, lon = _CITY_MAP[resolved]
                    actual_high = await _fetch_actual(lat, lon)

                    if forecast_high is None or actual_high is None:
                        logger.warning(
                            "Missing data for %s: forecast=%s actual=%s",
                            cc,
                            forecast_high,
                            actual_high,
                        )
                        results.append(
                            {
                                "city": cc,
                                "status": "skipped",
                                "reason": "missing forecast or actual data",
                            }
                        )
                        continue

                    from traderbot.db import get_connection as _get_conn

                    with _get_conn() as conn:
                        from traderbot.db.forecast_bias import (
                            init_table as _init_bias_table,
                        )
                        from traderbot.db.forecast_bias import (
                            record_forecast as _record,
                        )

                        _init_bias_table(conn)
                        _record(
                            conn,
                            city=resolved,
                            forecast_high_f=forecast_high,
                            actual_high_f=actual_high,
                        )
                        results.append(
                            {
                                "city": cc,
                                "status": "recorded",
                                "forecast_high_f": forecast_high,
                                "actual_high_f": actual_high,
                                "error_f": actual_high - forecast_high,
                            }
                        )
                return results
            finally:
                await provider.close()

        results = asyncio.run(_run())
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            raise typer.Exit(code=1) from None
        report_cli_error(f"Record bias failed: {exc}")

    if json_output:
        json_lib.dump({"results": results}, sys.stdout, default=str)
        return

    console.print("[bold]Forecast Bias Recording[/bold]")
    for r in results:
        status_style = "green" if r["status"] == "recorded" else "yellow"
        console.print(f"  [{status_style}]{r['city']}: {r['status']}[/{status_style}]")
        if r["status"] == "recorded":
            console.print(
                f"    Forecast: {r['forecast_high_f']}°F  Actual: {r['actual_high_f']}°F  Error: {r['error_f']:+.1f}°F"
            )


@data_app.command("settle")
def settle_paper_cmd(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be settled without writing")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption")
    ] = False,
) -> None:
    """Check open paper positions against settlement data and mark won/lost."""
    from traderbot.db import get_connection
    from traderbot.db.positions import init_table
    from traderbot.db.positions import list_open_positions as _list_open
    from traderbot.paths import _resolve_db_path
    from traderbot.simulation.settlement import auto_settle_paper_positions

    if dry_run:
        console = Console()
        conn_path = _resolve_db_path(None)
        with get_connection(conn_path) as conn:
            init_table(conn)
            positions = _list_open(conn)

        if json_output:
            result = {
                "dry_run": True,
                "open_count": len(positions),
                "positions": [
                    {
                        "ticker": p.ticker,
                        "quantity": p.quantity,
                        "avg_price": p.avg_price,
                    }
                    for p in positions
                ],
            }
            json_lib.dump(result, sys.stdout, default=str)
            return

        if not positions:
            console.print("[green]No open positions to settle.[/green]")
            return

        table = Table(title="Open Positions (dry-run)")
        table.add_column("Ticker", style="cyan")
        table.add_column("Quantity", justify="right")
        table.add_column("Avg Price (¢)", justify="right")
        for p in positions:
            table.add_row(p.ticker, str(p.quantity), str(p.avg_price))
        console.print(table)
        console.print(
            f"\n[yellow]{len(positions)} positions would be checked for settlement.[/yellow]"
        )
        return

    try:
        settled = auto_settle_paper_positions(profile=None)
    except Exception as exc:
        if json_output:
            json_lib.dump({"error": str(exc)}, sys.stdout)
            raise typer.Exit(code=1) from None
        report_cli_error(f"Settlement failed: {exc}")

    if json_output:
        json_lib.dump({"settled": settled}, sys.stdout)
        return

    console = Console()
    if settled == 0:
        console.print("[yellow]No positions settled.[/yellow]")
    else:
        console.print(f"[green]Settled {settled} position(s).[/green]")
