"""Structured logging helpers for TraderBot."""

import logging
import sys

_root_logger_configured = False


def configure_root_logger(level: int = logging.INFO) -> None:
    """Configure the root logger with a stderr StreamHandler."""
    global _root_logger_configured
    if _root_logger_configured:
        return

    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)

    _root_logger_configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given name."""
    configure_root_logger()
    return logging.getLogger(name)


def _format_details(details: dict) -> str:
    if not details:
        return ""
    return " | " + " ".join(f"{k}={v}" for k, v in details.items())


def log_market_event(
    logger: logging.Logger, event_type: str, ticker: str, **details
) -> None:
    """Log a market event."""
    logger.info("market | %s | %s%s", event_type, ticker, _format_details(details))


def log_cache_event(
    logger: logging.Logger, event_type: str, ticker: str, hit: bool, **details
) -> None:
    """Log a cache event."""
    logger.debug(
        "cache | %s | %s | hit=%s%s", event_type, ticker, hit, _format_details(details)
    )


def log_settlement_event(
    logger: logging.Logger, ticker: str, outcome: bool, **details
) -> None:
    """Log a settlement event."""
    logger.info(
        "settlement | %s | outcome=%s%s", ticker, outcome, _format_details(details)
    )


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
