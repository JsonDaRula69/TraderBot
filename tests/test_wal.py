"""Tests for WAL (Write-Ahead Log) protocol."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from traderbot.wal import (
    ConcurrentWriteError,
    WalAction,
    WalEntry,
    WalStatus,
    reconcile,
    scan_pending,
    update_status,
    write_intent,
)

TEMPLATE_SESSION_STATE = """\
# TraderBot Session State

## Active Context

**Last Updated**: (not yet initialized)

## Pending Actions

(none)

## WAL Entries

| Timestamp | Ticker | Direction | Quantity | Price | Reason |
|---|---|---|---|---|---|
| (none) | | | | | |
"""


@pytest.fixture
def session_state_path(tmp_path: Path) -> Path:
    """Create a temporary SESSION-STATE.md for testing."""
    path = tmp_path / "SESSION-STATE.md"
    path.write_text(TEMPLATE_SESSION_STATE)
    return path


class TestWalEntry:
    def test_valid_entry(self):
        entry = WalEntry(
            intent_id="WAL-ABCD1234",
            timestamp=datetime.now(UTC),
            action=WalAction.BUY,
            ticker="KXBTCD-26MAR31-T55000",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="Statistical edge 8.2%",
            signal="momentum_reversal",
            risk_checks="position 2.1% of portfolio within 5% limit",
            confidence=0.72,
        )
        assert entry.status == WalStatus.PENDING
        assert entry.action == WalAction.BUY

    def test_strict_config_rejects_extra_fields(self):
        with pytest.raises(Exception):
            WalEntry(
                intent_id="WAL-ABCD1234",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KX",
                direction="yes",
                quantity=1,
                price_cents=50,
                reason="test",
                extra_field="not_allowed",
            )

    def test_invalid_status_rejected(self):
        with pytest.raises(Exception):
            WalEntry(
                intent_id="WAL-ABCD1234",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KX",
                direction="yes",
                quantity=1,
                price_cents=50,
                reason="test",
                status="INVALID",
            )

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            WalEntry(
                intent_id="WAL-ABCD1234",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KX",
                direction="yes",
                quantity=1,
                price_cents=50,
                reason="test",
                confidence=1.5,
            )

    def test_quantity_must_be_positive(self):
        with pytest.raises(Exception):
            WalEntry(
                intent_id="WAL-ABCD1234",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KX",
                direction="yes",
                quantity=0,
                price_cents=50,
                reason="test",
            )

    def test_price_must_be_positive(self):
        with pytest.raises(Exception):
            WalEntry(
                intent_id="WAL-ABCD1234",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KX",
                direction="yes",
                quantity=1,
                price_cents=0,
                reason="test",
            )


class TestWriteIntent:
    def test_write_creates_entry(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC-26MAR31-T55000",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="Statistical edge 8.2%",
            signal="momentum_reversal",
            risk_checks="within limits",
            confidence=0.72,
        )
        assert entry.intent_id.startswith("WAL-")
        assert entry.status == WalStatus.PENDING
        assert entry.ticker == "KXBTC-26MAR31-T55000"

        content = session_state_path.read_text()
        assert entry.intent_id in content
        assert "BUY YES" in content
        assert "55¢" in content

    def test_write_with_prebuilt_entry(self, session_state_path: Path):
        entry = WalEntry(
            intent_id="WAL-PREBUILT",
            timestamp=datetime.now(UTC),
            action=WalAction.SELL,
            ticker="KXETH-26JUN30-T3000",
            direction="no",
            quantity=5,
            price_cents=40,
            reason="Overvalued",
        )
        result = write_intent(session_state_path, entry)
        assert result.intent_id == "WAL-PREBUILT"

    def test_write_missing_kwargs_raises(self, session_state_path: Path):
        with pytest.raises(ValueError):
            write_intent(session_state_path, action=WalAction.BUY, ticker="KX")

    def test_ensures_pending_actions_section(self, tmp_path: Path):
        path = tmp_path / "SESSION-STATE.md"
        path.write_text("# TraderBot Session State\n\n## WAL Entries\n\n| none |\n")

        entry = write_intent(
            path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=1,
            price_cents=50,
            reason="test",
        )
        content = path.read_text()
        assert "## Pending Actions" in content
        assert entry.intent_id in content

    def test_multiple_writes(self, session_state_path: Path):
        e1 = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="first",
        )
        e2 = write_intent(
            session_state_path,
            action=WalAction.SELL,
            ticker="KXETH",
            direction="no",
            quantity=5,
            price_cents=40,
            reason="second",
        )
        content = session_state_path.read_text()
        assert e1.intent_id in content
        assert e2.intent_id in content


class TestUpdateStatus:
    def test_update_to_completed(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        result = update_status(session_state_path, entry.intent_id, WalStatus.COMPLETED)
        assert result is True

        content = session_state_path.read_text()
        assert "Status: COMPLETED" in content

    def test_update_to_cancelled(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        update_status(session_state_path, entry.intent_id, WalStatus.CANCELLED)
        content = session_state_path.read_text()
        assert "Status: CANCELLED" in content

    def test_update_nonexistent_returns_false(self, session_state_path: Path):
        result = update_status(session_state_path, "WAL-NONEXIST", WalStatus.COMPLETED)
        assert result is False

    def test_update_missing_file_returns_false(self, tmp_path: Path):
        result = update_status(tmp_path / "nonexistent.md", "WAL-1", WalStatus.COMPLETED)
        assert result is False


class TestScanPending:
    def test_scan_finds_pending(self, session_state_path: Path):
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        pending = scan_pending(session_state_path)
        assert len(pending) == 1
        assert pending[0].status == WalStatus.PENDING
        assert pending[0].ticker == "KXBTC"

    def test_scan_excludes_non_pending(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        update_status(session_state_path, entry.intent_id, WalStatus.COMPLETED)
        pending = scan_pending(session_state_path)
        assert len(pending) == 0

    def test_scan_empty_file(self, session_state_path: Path):
        pending = scan_pending(session_state_path)
        assert len(pending) == 0

    def test_scan_missing_file(self, tmp_path: Path):
        pending = scan_pending(tmp_path / "nonexistent.md")
        assert len(pending) == 0

    def test_scan_multiple_pending(self, session_state_path: Path):
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="first",
        )
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXETH",
            direction="no",
            quantity=5,
            price_cents=40,
            reason="second",
        )
        pending = scan_pending(session_state_path)
        assert len(pending) == 2

    def test_scan_mixed_statuses(self, session_state_path: Path):
        e1 = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="first",
        )
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXETH",
            direction="no",
            quantity=5,
            price_cents=40,
            reason="second",
        )
        update_status(session_state_path, e1.intent_id, WalStatus.CANCELLED)
        pending = scan_pending(session_state_path)
        assert len(pending) == 1
        assert pending[0].ticker == "KXETH"


class TestReconcile:
    def test_reconcile_matching_position(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        positions = {"KXBTC": {"yes": 10, "no": 0}}
        updated = reconcile(session_state_path, positions)
        assert len(updated) == 1
        assert updated[0].status == WalStatus.COMPLETED
        assert updated[0].intent_id == entry.intent_id

    def test_reconcile_missing_position(self, session_state_path: Path):
        entry = write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        updated = reconcile(session_state_path, {})
        assert len(updated) == 1
        assert updated[0].status == WalStatus.CANCELLED

    def test_reconcile_insufficient_quantity(self, session_state_path: Path):
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        positions = {"KXBTC": {"yes": 5, "no": 0}}
        updated = reconcile(session_state_path, positions)
        assert len(updated) == 1
        assert updated[0].status == WalStatus.CANCELLED

    def test_reconcile_wrong_direction(self, session_state_path: Path):
        write_intent(
            session_state_path,
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="test",
        )
        positions = {"KXBTC": {"yes": 0, "no": 10}}
        updated = reconcile(session_state_path, positions)
        assert len(updated) == 1
        assert updated[0].status == WalStatus.CANCELLED

    def test_reconcile_no_pending(self, session_state_path: Path):
        positions = {"KXBTC": {"yes": 10, "no": 0}}
        updated = reconcile(session_state_path, positions)
        assert len(updated) == 0


class TestConcurrentWrite:
    def test_concurrent_write_detected(self, session_state_path: Path):
        import portalocker

        acquired = threading.Event()
        proceed = threading.Event()
        errors: list[Exception | None] = [None, None]

        def holding_writer():
            try:
                lock = portalocker.Lock(
                    session_state_path,
                    mode="r+",
                    flags=portalocker.LockFlags.EXCLUSIVE | portalocker.LockFlags.NON_BLOCKING,
                )
                lock.acquire()
                acquired.set()
                proceed.wait(timeout=3)
                lock.release()
            except Exception:
                acquired.set()

        def competing_writer():
            try:
                acquired.wait(timeout=2)
                write_intent(
                    session_state_path,
                    action=WalAction.BUY,
                    ticker="KXBTC",
                    direction="yes",
                    quantity=1,
                    price_cents=50,
                    reason="competing",
                )
            except ConcurrentWriteError as exc:
                errors[1] = exc
            except Exception as exc:
                errors[1] = exc

        t1 = threading.Thread(target=holding_writer)
        t2 = threading.Thread(target=competing_writer)
        t1.start()
        t2.start()
        t2.join(timeout=5)
        proceed.set()
        t1.join(timeout=5)

        assert isinstance(errors[1], ConcurrentWriteError)


class TestWalEntryModel:
    def test_monetary_values_as_int(self):
        entry = WalEntry(
            intent_id="WAL-TEST1",
            timestamp=datetime.now(UTC),
            action=WalAction.BUY,
            ticker="KXBTC",
            direction="yes",
            quantity=10,
            price_cents=5500,
            reason="test",
        )
        assert isinstance(entry.price_cents, int)
        assert entry.price_cents == 5500

    def test_all_statuses(self):
        for status in WalStatus:
            entry = WalEntry(
                intent_id=f"WAL-{status.value}",
                timestamp=datetime.now(UTC),
                action=WalAction.BUY,
                ticker="KXBTC",
                direction="yes",
                quantity=1,
                price_cents=50,
                reason="test",
                status=status,
            )
            assert entry.status == status

    def test_sell_action(self):
        entry = WalEntry(
            intent_id="WAL-SELL1",
            timestamp=datetime.now(UTC),
            action=WalAction.SELL,
            ticker="KXBTC",
            direction="no",
            quantity=5,
            price_cents=45,
            reason="test",
        )
        assert entry.action == WalAction.SELL
        assert entry.direction == "no"


class TestWALFdSafety:
    def test_wal_append_entry_file_open_failure(self, tmp_path: Path) -> None:
        """If open() raises, append_entry should not reference unbound fd."""
        import unittest.mock

        entry = WalEntry(
            intent_id="WAL-FDTEST1",
            timestamp=datetime.now(UTC),
            action=WalAction.BUY,
            ticker="KX-TEST",
            direction="yes",
            quantity=1,
            price_cents=50,
            reason="test",
        )
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text(
            "# Session State\n\n## Pending Actions\n\n(none)\n\n## Completed Actions\n\n(none)\n"
        )
        with unittest.mock.patch("builtins.open", side_effect=OSError("permission denied")):
            with pytest.raises(OSError, match="permission denied"):
                write_intent(session_file, entry)

    def test_wal_update_status_closes_fd(self, tmp_path: Path) -> None:
        """update_status must always close the file descriptor, even on error paths."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text(
            "# Session State\n\n## Pending Actions\n\n"
            "### intent-1\n- Action: BUY\n- Direction: yes\n- Status: PENDING\n\n"
            "## Completed Actions\n\n(none)\n"
        )

        result = update_status(session_file, "intent-1", WalStatus.COMPLETED)

        fd_after = open(session_file)  # noqa: SIM115
        content_after = fd_after.read()
        fd_after.close()

        assert result is True
        assert "Status: COMPLETED" in content_after
