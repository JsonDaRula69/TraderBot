"""Structured logging helpers for TraderBot."""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING

try:
    import sentry_sdk

    HAS_SENTRY = True
except ImportError:
    HAS_SENTRY = False

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sentry_sdk.types import Event, Hint

_root_logger_configured = False

operation_id_var: ContextVar[str] = ContextVar("operation_id", default="")


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "operation_id": operation_id_var.get(""),
        }
        return json.dumps(obj, ensure_ascii=False)


def _sentry_before_send(event: Event, hint: Hint) -> Event:
    """Add error_code as a Sentry tag for TraderBotError instances."""
    exc_info = hint.get("exc_info")
    if exc_info:
        _exc_type, exc_value, _ = exc_info
        from traderbot.exceptions import TraderBotError

        if isinstance(exc_value, TraderBotError) and exc_value.error_code:
            tags = event.get("tags") or {}
            tags["error_code"] = str(exc_value.error_code)
            event["tags"] = tags
    return event


def init_sentry() -> bool:
    """Initialize Sentry SDK if TRADERBOT_SENTRY_DSN is set.

    Returns True if Sentry was initialized, False otherwise.
    Silently does nothing when the DSN is not set or sentry-sdk is not installed.
    """
    dsn = os.environ.get("TRADERBOT_SENTRY_DSN", "")
    if not dsn or not HAS_SENTRY:
        return False

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        before_send=_sentry_before_send,
    )
    return True


def _configure_module_levels() -> None:
    """Apply per-module log levels from TRADERBOT_LOG_LEVELS env var.

    Format: ``module1=DEBUG,module2=WARNING``
    The module name is matched prefix-style — ``traderbot.kalshi`` covers
    every logger whose name starts with ``traderbot.kalshi``.
    """
    raw = os.environ.get("TRADERBOT_LOG_LEVELS", "")
    if not raw:
        return
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        module, _, level_name = pair.partition("=")
        module = module.strip()
        level_name = level_name.strip()
        numeric = logging.getLevelName(level_name)
        if isinstance(numeric, int):
            logging.getLogger(module).setLevel(numeric)


def configure_root_logger(level: int = logging.INFO) -> None:
    """Configure the root logger with a stderr StreamHandler.

    Respects three environment variables:

    - **TRADERBOT_LOG_FORMAT** - set to ``json`` for JSON-formatted output;
      any other value (or unset) keeps the default pipe-delimited format.
    - **TRADERBOT_LOG_FILE** - path to a log file; enables a
      :class:`~logging.handlers.RotatingFileHandler` (10 MB, 5 backups).
    - **TRADERBOT_LOG_LEVELS** - comma-separated ``module=LEVEL`` pairs
      (e.g. ``traderbot.kalshi=DEBUG,traderbot.risk=WARNING``).
    """
    global _root_logger_configured
    if _root_logger_configured:
        return

    fmt = os.environ.get("TRADERBOT_LOG_FORMAT", "pipe")
    if fmt == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    # StreamHandler on stderr (always present)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    if not root.handlers:
        root.addHandler(sh)
    else:
        # During tests the root may already have handlers; replace formatters
        # only on StreamHandlers we own so caplog still works.
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.handlers.RotatingFileHandler
            ):
                h.setFormatter(formatter)

    # Optional RotatingFileHandler
    log_file = os.environ.get("TRADERBOT_LOG_FILE", "")
    if log_file:
        rfh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        rfh.setFormatter(formatter)
        root.addHandler(rfh)

    # Per-module log level overrides
    _configure_module_levels()

    init_sentry()

    _root_logger_configured = True


@contextlib.contextmanager
def correlation_id(cid: str) -> Iterator[None]:
    """Context manager that sets ``operation_id`` for the duration of *cid*.

    The value is stored in a :class:`~contextvars.ContextVar` so it
    propagates across ``asyncio`` tasks automatically.
    """
    token = operation_id_var.set(cid)
    try:
        yield
    finally:
        operation_id_var.reset(token)


def _format_details(details: dict) -> str:
    if not details:
        return ""
    return " | " + " ".join(f"{k}={v}" for k, v in details.items())


def log_market_event(logger: logging.Logger, event_type: str, ticker: str, **details) -> None:
    """Log a market event."""
    logger.info("market | %s | %s%s", event_type, ticker, _format_details(details))


def log_cache_event(
    logger: logging.Logger, event_type: str, ticker: str, hit: bool, **details
) -> None:
    """Log a cache event."""
    logger.debug("cache | %s | %s | hit=%s%s", event_type, ticker, hit, _format_details(details))


def log_settlement_event(logger: logging.Logger, ticker: str, outcome: bool, **details) -> None:
    """Log a settlement event."""
    logger.info("settlement | %s | outcome=%s%s", ticker, outcome, _format_details(details))


def log_reconciliation_event(
    logger: logging.Logger, ticker: str, drift_cents: int, **details
) -> None:
    """Log a reconciliation event."""
    logger.warning(
        "reconciliation | %s | drift=%s%s",
        ticker,
        drift_cents,
        _format_details(details),
    )
