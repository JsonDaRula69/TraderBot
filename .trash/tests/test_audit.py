from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from traderbot.kalshi.models import Decision
from traderbot.risk.audit import AuditLogger


def make_decision(
    ticker: str = "KXBTCD-26MAR31-T55000",
    outcome: str = "executed",
    ts: datetime | None = None,
    rejection_reason: str | None = None,
) -> Decision:
    return Decision(
        timestamp=ts or datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        ticker=ticker,
        direction="yes",
        quantity=10,
        price=65,
        signal_strength=0.8,
        confidence=0.75,
        edge_estimate=5.0,
        risk_checks={"position_limit": True, "daily_loss": True},
        outcome=outcome,
        rejection_reason=rejection_reason,
    )


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "audit"


@pytest.fixture
def logger(log_dir: Path) -> AuditLogger:
    return AuditLogger(log_dir=log_dir)


class TestLogDecision:
    def test_writes_to_file(self, logger: AuditLogger, log_dir: Path) -> None:
        d = make_decision()
        logger.log_decision(d)
        log_file = log_dir / "2026-01-15.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_appends_multiple(self, logger: AuditLogger, log_dir: Path) -> None:
        d1 = make_decision()
        d2 = make_decision(ticker="KXETH-26MAR31-T3000")
        logger.log_decision(d1)
        logger.log_decision(d2)
        lines = (log_dir / "2026-01-15.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2


class TestGetDecisions:
    def test_returns_all(self, logger: AuditLogger) -> None:
        d = make_decision()
        logger.log_decision(d)
        results = logger.get_decisions()
        assert len(results) == 1
        assert results[0].ticker == d.ticker

    def test_filter_by_ticker(self, logger: AuditLogger) -> None:
        logger.log_decision(make_decision(ticker="TICKER_A"))
        logger.log_decision(make_decision(ticker="TICKER_B"))
        results = logger.get_decisions(ticker="TICKER_A")
        assert len(results) == 1
        assert results[0].ticker == "TICKER_A"

    def test_filter_by_outcome(self, logger: AuditLogger) -> None:
        logger.log_decision(make_decision(outcome="executed"))
        logger.log_decision(make_decision(outcome="rejected", rejection_reason="position_limit"))
        results = logger.get_decisions(outcome="rejected")
        assert len(results) == 1
        assert results[0].outcome == "rejected"

    def test_filter_by_date_range(self, logger: AuditLogger) -> None:
        d1 = make_decision(ts=datetime(2026, 1, 10, 12, 0, tzinfo=UTC))
        d2 = make_decision(ts=datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        d3 = make_decision(ts=datetime(2026, 1, 20, 12, 0, tzinfo=UTC))
        logger.log_decision(d1)
        logger.log_decision(d2)
        logger.log_decision(d3)
        start = datetime(2026, 1, 12, tzinfo=UTC)
        end = datetime(2026, 1, 17, tzinfo=UTC)
        results = logger.get_decisions(start=start, end=end)
        assert len(results) == 1

    def test_empty_results_when_no_match(self, logger: AuditLogger) -> None:
        logger.log_decision(make_decision(ticker="TICKER_A"))
        results = logger.get_decisions(ticker="NONEXISTENT")
        assert results == []


class TestRoundtrip:
    def test_logged_equals_loaded(self, logger: AuditLogger) -> None:
        original = make_decision()
        logger.log_decision(original)
        loaded = logger.get_decisions()[0]
        assert loaded.timestamp == original.timestamp
        assert loaded.ticker == original.ticker
        assert loaded.direction == original.direction
        assert loaded.quantity == original.quantity
        assert loaded.price == original.price
        assert loaded.signal_strength == original.signal_strength
        assert loaded.confidence == original.confidence
        assert loaded.edge_estimate == original.edge_estimate
        assert loaded.risk_checks == original.risk_checks
        assert loaded.outcome == original.outcome
        assert loaded.rejection_reason == original.rejection_reason
        assert loaded.actual_result == original.actual_result


class TestRejectedDecisions:
    def test_executed_decision_logged(self, logger: AuditLogger) -> None:
        d = make_decision(outcome="executed")
        logger.log_decision(d)
        results = logger.get_decisions()
        assert results[0].outcome == "executed"

    def test_rejected_decision_logged(self, logger: AuditLogger) -> None:
        d = make_decision(outcome="rejected", rejection_reason="position_limit")
        logger.log_decision(d)
        results = logger.get_decisions()
        assert results[0].outcome == "rejected"
        assert results[0].rejection_reason == "position_limit"


class TestDirectoryCreation:
    def test_missing_dir_created(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "nested" / "audit"
        AuditLogger(log_dir=log_dir)
        assert log_dir.exists()


class TestGetAllDecisions:
    def test_reads_across_days(self, logger: AuditLogger) -> None:
        d1 = make_decision(ts=datetime(2026, 1, 10, 12, 0, tzinfo=UTC))
        d2 = make_decision(ts=datetime(2026, 1, 11, 12, 0, tzinfo=UTC))
        logger.log_decision(d1)
        logger.log_decision(d2)
        results = logger.get_all_decisions()
        assert len(results) == 2

    def test_skips_blank_lines(self, log_dir: Path) -> None:
        d = make_decision()
        json_line = d.model_dump_json()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "2026-01-15.jsonl"
        log_file.write_text(f"\n{json_line}\n\n", encoding="utf-8")
        logger = AuditLogger(log_dir=log_dir)
        results = logger.get_all_decisions()
        assert len(results) == 1


class TestBlankLinesInQuery:
    def test_query_skips_blank_lines(self, log_dir: Path) -> None:
        d = make_decision()
        json_line = d.model_dump_json()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "2026-01-15.jsonl"
        log_file.write_text(f"{json_line}\n\n{json_line}\n", encoding="utf-8")
        logger = AuditLogger(log_dir=log_dir)
        results = logger.get_decisions()
        assert len(results) == 2


class TestTimestampFilterInFile:
    def test_query_skips_entries_before_start(self, log_dir: Path) -> None:
        early = make_decision(ts=datetime(2026, 1, 15, 8, 0, tzinfo=UTC))
        late = make_decision(ts=datetime(2026, 1, 15, 16, 0, tzinfo=UTC))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "2026-01-15.jsonl"
        log_file.write_text(
            early.model_dump_json() + "\n" + late.model_dump_json() + "\n",
            encoding="utf-8",
        )
        logger = AuditLogger(log_dir=log_dir)
        results = logger.get_decisions(start=datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        assert len(results) == 1
        assert results[0].timestamp == late.timestamp

    def test_query_skips_entries_after_end(self, log_dir: Path) -> None:
        early = make_decision(ts=datetime(2026, 1, 15, 8, 0, tzinfo=UTC))
        late = make_decision(ts=datetime(2026, 1, 15, 16, 0, tzinfo=UTC))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "2026-01-15.jsonl"
        log_file.write_text(
            early.model_dump_json() + "\n" + late.model_dump_json() + "\n",
            encoding="utf-8",
        )
        logger = AuditLogger(log_dir=log_dir)
        results = logger.get_decisions(end=datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        assert len(results) == 1
        assert results[0].timestamp == early.timestamp


class TestBadFilenameFilter:
    def test_skips_files_with_bad_date_names(self, log_dir: Path) -> None:
        d = make_decision(ts=datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "not-a-date.jsonl").write_text(d.model_dump_json() + "\n", encoding="utf-8")
        valid_file = log_dir / "2026-01-15.jsonl"
        valid_file.write_text(d.model_dump_json() + "\n", encoding="utf-8")
        logger = AuditLogger(log_dir=log_dir)
        results = logger.get_decisions(start=datetime(2026, 1, 1, tzinfo=UTC))
        assert len(results) == 1
