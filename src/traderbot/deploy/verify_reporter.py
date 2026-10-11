"""Render verification results as JSON or Rich output."""

from __future__ import annotations

import sys
from typing import Protocol, final

from rich.console import Console
from rich.table import Table

from traderbot.deploy.verify_models import VerificationResult


class ResultReporter(Protocol):
    def render(self, result: VerificationResult) -> None: ...


@final
class JsonReporter:
    def render(self, result: VerificationResult) -> None:
        _ = sys.stdout.write(result.model_dump_json() + "\n")


@final
class RichReporter:
    def __init__(self, console: Console | None = None) -> None:
        self._console: Console = Console(stderr=True) if console is None else console

    def render(self, result: VerificationResult) -> None:
        table = Table(title=f"TraderBot Verification: {result.overall}")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Action")
        table.add_column("Elapsed", justify="right")
        table.add_column("Message")
        for check in result.checks:
            table.add_row(
                check.id,
                check.status,
                check.action,
                f"{check.elapsed_ms} ms",
                check.message,
            )
        self._console.print(table)


__all__ = ["JsonReporter", "ResultReporter", "RichReporter"]
