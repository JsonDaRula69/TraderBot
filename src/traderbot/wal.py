"""Write-Ahead Log protocol for crash-safe trade execution."""

from __future__ import annotations

import contextlib
import fcntl
import logging
import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderbot.paths import get_workspace_dir

logger = logging.getLogger(__name__)


def _default_session_state_path() -> Path:
    return get_workspace_dir() / "SESSION-STATE.md"


DEFAULT_SESSION_STATE_PATH = _default_session_state_path()


class WalStatus(StrEnum):
    """Status values for WAL entries."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class WalAction(StrEnum):
    """Trade action types."""

    BUY = "BUY"
    SELL = "SELL"


class WalEntry(BaseModel):
    """A single WAL intent entry representing a pending trade action."""

    model_config = ConfigDict(strict=True, extra="forbid")

    intent_id: str
    timestamp: datetime
    action: WalAction
    ticker: str
    direction: Literal["yes", "no"]
    quantity: Annotated[int, Field(ge=1)]
    price_cents: Annotated[int, Field(ge=1, description="Price in cents")]
    reason: str
    signal: str = ""
    risk_checks: str = ""
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    status: WalStatus = WalStatus.PENDING


class ConcurrentWriteError(Exception):
    """Raised when another writer is actively writing to the WAL."""


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


def _new_intent_id() -> str:
    """Generate a unique intent ID."""
    return f"WAL-{uuid.uuid4().hex[:8].upper()}"


def _parse_section(content: str, section_header: str) -> tuple[int, int]:
    """Find start and end line indices for a markdown section.

    Returns (start, end) where start is the line after the header
    and end is the line before the next ## header (or EOF).
    """
    lines = content.splitlines()
    start = -1
    end = len(lines)

    for i, line in enumerate(lines):
        if line.strip().startswith(section_header):
            start = i
            break

    if start == -1:
        return -1, -1

    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("## ") and not lines[i].strip().startswith(section_header):
            end = i
            break

    return start, end


def _entry_to_markdown(entry: WalEntry) -> str:
    """Render a WAL entry as markdown for the Pending Actions section."""
    action_str = f"{entry.action.value} {entry.direction.upper()}"
    lines = [
        f"### {entry.intent_id}",
        f"- Timestamp: {entry.timestamp.isoformat()}",
        f"- Action: {action_str} {entry.quantity} {entry.ticker} @ {entry.price_cents}¢",
        f"- Reason: {entry.reason}",
        f"- Signal: {entry.signal or '(none)'}",
        f"- Risk: {entry.risk_checks or '(none)'}",
        f"- Confidence: {entry.confidence:.2f}",
        f"- Status: {entry.status.value}",
    ]
    return "\n".join(lines)


def _parse_entries(content: str) -> list[WalEntry]:
    """Parse WAL entries from the Pending Actions section of SESSION-STATE.md."""
    entries: list[WalEntry] = []
    # Match: ### WAL-XXXXX header followed by key-value bullet lines
    pattern = re.compile(
        r"###\s+(WAL-[A-Z0-9]+)\s*\n"
        r"(?:-\s+Timestamp:\s*(.+?)\s*\n)?"
        r"-\s+Action:\s+(BUY|SELL)\s+(YES|NO)\s+(\d+)\s+(\S+)\s+@\s+(\d+)¢\s*\n"
        r"(?:-\s+Reason:\s*(.+?)\s*\n)?"
        r"(?:-\s+Signal:\s*(.+?)\s*\n)?"
        r"(?:-\s+Risk:\s*(.+?)\s*\n)?"
        r"(?:-\s+Confidence:\s*([\d.]+)\s*\n)?"
        r"-\s+Status:\s*(PENDING|COMPLETED|CANCELLED|EXPIRED)\s*\n?",
        re.MULTILINE,
    )

    for m in pattern.finditer(content):
        try:
            entry = WalEntry(
                intent_id=m.group(1),
                timestamp=datetime.fromisoformat(m.group(2)) if m.group(2) else datetime.now(UTC),
                action=WalAction(m.group(3)),
                direction=m.group(4).lower(),
                quantity=int(m.group(5)),
                ticker=m.group(6),
                price_cents=int(m.group(7)),
                reason=m.group(8) or "",
                signal=m.group(9) or "",
                risk_checks=m.group(10) or "",
                confidence=float(m.group(11)) if m.group(11) else 0.5,
                status=WalStatus(m.group(12)),
            )
            entries.append(entry)
        except (ValueError, TypeError):
            logger.warning("Failed to parse WAL entry %s, skipping", m.group(1))
            continue

    return entries


def _read_file_locked(path: Path) -> str:
    """Read file contents with a shared lock to detect concurrent writers."""
    if not path.exists():
        return ""
    with open(path) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        content = f.read()
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return content


def _ensure_pending_actions_section(content: str) -> str:
    """Ensure the content has a ## Pending Actions section."""
    if "## Pending Actions" in content:
        return content
    if "## WAL Entries" in content:
        section = "## Pending Actions\n\n(none)\n\n"
        return content.replace("## WAL Entries", section + "## WAL Entries")
    return content + "\n\n## Pending Actions\n\n(none)\n"


def write_intent(
    session_state_path: Path,
    entry: WalEntry | None = None,
    *,
    action: WalAction | None = None,
    ticker: str | None = None,
    direction: str | None = None,
    quantity: int | None = None,
    price_cents: int | None = None,
    reason: str | None = None,
    signal: str = "",
    risk_checks: str = "",
    confidence: float = 0.5,
) -> WalEntry:
    """Write a pending action intent to SESSION-STATE.md.

    Accepts either a pre-built WalEntry or keyword arguments to construct one.
    Uses file locking to detect concurrent writers — if an exclusive lock cannot
    be obtained, raises ConcurrentWriteError.

    Returns the written WalEntry (with generated intent_id/timestamp if needed).
    """
    path = Path(session_state_path)

    if entry is None:
        required = (action, ticker, direction, quantity, price_cents, reason)
        if any(v is None for v in required):
            raise ValueError("Must provide either entry or all required keyword args")
        entry = WalEntry(
            intent_id=_new_intent_id(),
            timestamp=datetime.now(UTC),
            action=action,  # validated non-None above
            ticker=ticker,  # validated non-None above
            direction=direction,  # validated non-None above
            quantity=quantity,  # validated non-None above
            price_cents=price_cents,  # validated non-None above
            reason=reason,  # validated non-None above
            signal=signal,
            risk_checks=risk_checks,
            confidence=confidence,
        )
    elif entry.intent_id == "":
        entry = entry.model_copy(update={"intent_id": _new_intent_id()})
    if entry.timestamp.year == 1:
        entry = entry.model_copy(update={"timestamp": datetime.now(UTC)})

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "# Session State\n\n## Pending Actions\n\n(none)\n\n## Completed Actions\n\n(none)\n"
        )
        path.chmod(0o600)
    fd = open(path, "r+")  # noqa: SIM115 - fcntl.flock requires manual fd
    fd_closed = False
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            fd.close()
            fd_closed = True
            logger.error("Concurrent WAL writer detected — rejecting write for %s", entry.intent_id)
            raise ConcurrentWriteError(
                f"Another writer is actively writing to {path}. Write rejected for {entry.intent_id}"
            ) from err

        fd.seek(0)
        content = fd.read()

        content = _ensure_pending_actions_section(content)
        content = content.replace("(none)\n\n## ", "\n## ")
        content = content.replace("(none)\n\n", "\n")
        content = re.sub(
            r"(## Pending Actions)\s*\n\s*\(none\)\s*\n",
            r"\1\n\n",
            content,
        )

        entry_md = _entry_to_markdown(entry)
        lines = content.splitlines()
        insert_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "## Pending Actions":
                insert_idx = i + 1
                break

        if insert_idx == -1:
            for i, line in enumerate(lines):
                if line.strip() == "## Pending Actions":
                    insert_idx = i + 1
                    break

        while insert_idx < len(lines) and lines[insert_idx].strip() == "":
            insert_idx += 1

        section_end = len(lines)
        for i in range(insert_idx, len(lines)):
            if lines[i].strip().startswith("## "):
                section_end = i
                break

        lines.insert(section_end, entry_md)

        fd.seek(0)
        fd.truncate()
        fd.write("\n".join(lines))
        fd.flush()
    finally:
        if not fd_closed:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()

    logger.info(
        "WAL intent written: %s %s %s %s",
        entry.action.value,
        entry.direction,
        entry.ticker,
        entry.intent_id,
    )
    return entry


def update_status(session_state_path: Path, intent_id: str, status: WalStatus) -> bool:
    """Update the status of a WAL entry by intent_id.

    Returns True if the entry was found and updated, False otherwise.
    """
    path = Path(session_state_path)
    if not path.exists():
        logger.warning("SESSION-STATE.md not found at %s", path)
        return False

    fd = open(path, "r+")  # noqa: SIM115 - fcntl.flock requires manual fd
    fd_closed = False
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            fd.close()
            fd_closed = True
            logger.error("Concurrent WAL writer during status update for %s", intent_id)
            raise ConcurrentWriteError(
                f"Another writer is active, cannot update {intent_id}"
            ) from err

        content = fd.read()

        pattern = re.compile(
            rf"(###\s+{re.escape(intent_id)}\s*\n(?:-\s+.*\n)*?- )Status:\s*\w+",
            re.MULTILINE,
        )

        match = pattern.search(content)
        if not match:
            logger.warning("WAL entry %s not found for status update", intent_id)
            return False

        new_content = content[: match.start(1)] + f"Status: {status.value}" + content[match.end() :]

        fd.seek(0)
        fd.truncate()
        fd.write(new_content)
        fd.flush()
    finally:
        if not fd_closed:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()

    logger.info("WAL entry %s status updated to %s", intent_id, status.value)
    return True


def scan_pending(session_state_path: Path) -> list[WalEntry]:
    """Scan for all PENDING WAL entries (crash recovery).

    Returns a list of WalEntry objects with status PENDING.
    """
    path = Path(session_state_path)
    if not path.exists():
        return []

    content = _read_file_locked(path)
    entries = _parse_entries(content)
    return [e for e in entries if e.status == WalStatus.PENDING]


def reconcile(
    session_state_path: Path,
    positions: dict[str, dict[str, int]],
) -> list[WalEntry]:
    """Reconcile pending WAL intents against actual positions.

    positions: dict mapping ticker -> {"quantity": int, "direction": str (as "yes"/"no" count)}

    For each PENDING entry:
    - If the position exists and matches intent → mark COMPLETED
    - If the position doesn't match → mark CANCELLED
    - If position partially matches → mark CANCELLED (partial fills not modeled)

    Returns list of entries that were updated.
    """
    pending = scan_pending(session_state_path)
    updated: list[WalEntry] = []

    for entry in pending:
        pos = positions.get(entry.ticker)
        if pos and pos.get(entry.direction, 0) >= entry.quantity:
            update_status(session_state_path, entry.intent_id, WalStatus.COMPLETED)
            updated.append(entry.model_copy(update={"status": WalStatus.COMPLETED}))
        else:
            update_status(session_state_path, entry.intent_id, WalStatus.CANCELLED)
            updated.append(entry.model_copy(update={"status": WalStatus.CANCELLED}))

    return updated
