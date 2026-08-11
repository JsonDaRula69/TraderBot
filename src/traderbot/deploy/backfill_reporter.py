from __future__ import annotations

import sys
from typing import Protocol

from rich.console import Console
from rich.table import Table

from traderbot.deploy.backfill_models import BackfillResult


class ResultReporter(Protocol):
    def render(self, result: BackfillResult) -> None: ...


class NullReporter:
    def render(self, result: BackfillResult) -> None:
        _ = result


class JsonReporter:
    def render(self, result: BackfillResult) -> None:
        _ = sys.stdout.write(result.model_dump_json() + "\n")


class RichReporter:
    def __init__(self, console: Console | None = None) -> None:
        self._console: Console = Console(stderr=True) if console is None else console

    def render(self, result: BackfillResult) -> None:
        table = Table(title=f"TraderBot Backfill: {result.status}")
        table.add_column("Dataset")
        table.add_column("Seen", justify="right")
        table.add_column("Inserted", justify="right")
        table.add_column("Duplicate", justify="right")
        rows = (
            ("weather forecasts", result.collector.weather_forecasts),
            ("NWS forecasts", result.collector.nws_forecasts),
            ("weather observations", result.collector.weather_observations),
            ("Kalshi markets", result.kalshi.markets),
            ("Kalshi candlesticks", result.kalshi.candlesticks),
            ("Kalshi forecast history", result.kalshi.forecast_history),
        )
        for name, counts in rows:
            table.add_row(name, str(counts.seen), str(counts.inserted), str(counts.duplicate))
        self._console.print(table)
        for warning in result.warnings:
            self._console.print(f"Warning: {warning}")
        for failure in result.failures:
            item = "" if failure.item is None else f" ({failure.item})"
            self._console.print(f"Failure: {failure.code}{item}: {failure.detail}")


__all__ = ["JsonReporter", "NullReporter", "ResultReporter", "RichReporter"]
