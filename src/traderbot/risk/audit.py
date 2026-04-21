"""Append-only JSONL audit trail for trade decisions."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from traderbot.kalshi.models import Decision


class AuditLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or Path.home() / ".traderbot" / "audit"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_decision(self, decision: Decision) -> None:
        date_str = decision.timestamp.strftime("%Y-%m-%d")
        log_file = self._log_dir / f"{date_str}.jsonl"
        line = decision.model_dump_json() + "\n"
        with self._lock, log_file.open("a", encoding="utf-8") as f:
            f.write(line)

    def get_decisions(
        self,
        ticker: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        outcome: str | None = None,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        for log_file in self._log_files_in_range(start, end):
            for line in log_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = Decision.model_validate_json(line)
                if ticker and d.ticker != ticker:
                    continue
                if start and d.timestamp < start:
                    continue
                if end and d.timestamp > end:
                    continue
                if outcome and d.outcome != outcome:
                    continue
                decisions.append(d)
        return decisions

    def get_all_decisions(self) -> list[Decision]:
        decisions: list[Decision] = []
        for log_file in sorted(self._log_dir.glob("*.jsonl")):
            for line in log_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                decisions.append(Decision.model_validate_json(line))
        return decisions

    def _log_files_in_range(self, start: datetime | None, end: datetime | None) -> list[Path]:
        files = sorted(self._log_dir.glob("*.jsonl"))
        if not start and not end:
            return files
        result: list[Path] = []
        for f in files:
            date_str = f.stem
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                continue
            start_normalized = start.replace(tzinfo=UTC) if start and start.tzinfo is None else start
            end_normalized = end.replace(tzinfo=UTC) if end and end.tzinfo is None else end
            if start_normalized and file_date < start_normalized.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            if end_normalized and file_date > end_normalized.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            result.append(f)
        return result
