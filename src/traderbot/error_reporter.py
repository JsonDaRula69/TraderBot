"""Centralized error reporting for logs and CLI output.

Provides consistent formatting, log-level routing, and per-module error
suppression so that callers never need to decide how to present an error
individually.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from traderbot.exceptions import TraderBotError
from traderbot.logging_config import operation_id_var

logger = logging.getLogger(__name__)

_CRITICAL_THRESHOLD = 5000

_SILENT_MODULES_ENV = "TRADERBOT_SILENT_MODULES"


def report_error(
    error: BaseException,
    context: dict[str, Any] | None = None,
    log: logging.Logger | None = None,
) -> str:
    """Log *error* at the appropriate level and return a formatted string.

    Parameters
    ----------
    error:
        The exception to report.  :class:`TraderBotError` instances are
        routed by ``error_code``; plain exceptions become ``WARNING``.
    context:
        Optional dict merged into the log message as ``key=value`` pairs.
    log:
        Logger to emit on.  Falls back to this module's logger.

    Returns
    -------
    str
        The user-facing formatted error string.
    """
    if log is None:
        log = logger

    msg = format_error_for_user(error)
    extra: dict[str, Any] = {}

    cid = operation_id_var.get("")
    if cid:
        extra["operation_id"] = cid

    if context:
        extra.update(context)

    if isinstance(error, TraderBotError):
        if error.error_code >= _CRITICAL_THRESHOLD:
            log.critical(msg, extra=extra or None)
        else:
            log.error(msg, extra=extra or None)
    else:
        if extra:
            msg = f"{msg} | " + " ".join(f"{k}={v}" for k, v in extra.items())
        log.warning(msg)

    return msg


def format_error_for_user(error: BaseException) -> str:
    """Return a human-readable error string.

    - :class:`TraderBotError` with ``error_code``: ``[E{code}] {message}``
    - :class:`TraderBotError` without ``error_code``: ``{message}``
    - Other exceptions: ``str(error)``
    """
    if isinstance(error, TraderBotError):
        if error.error_code:
            return f"[E{error.error_code}] {error.message}"
        return error.message
    return str(error)


def format_cli_error(error: BaseException) -> str:
    """Return a Rich-markup-formatted error string for CLI output.

    - :class:`TraderBotError` with ``error_code``:
      ``[red]Error [E{code}]:[/red] {message}``
    - :class:`TraderBotError` without ``error_code``:
      ``[red]Error:[/red] {message}``
    - Other exceptions: ``[red]Error:[/red] {message}``
    """
    if isinstance(error, TraderBotError) and error.error_code:
        return f"[red]Error [E{error.error_code}]:[/red] {error.message}"
    return f"[red]Error:[/red] {error}"


def should_silently_fail(module_name: str) -> bool:
    """Check whether errors from *module_name* should be suppressed.

    Reads the ``TRADERBOT_SILENT_MODULES`` environment variable, a
    comma-separated list of module name prefixes.  Returns ``True`` only
    when the module is explicitly listed.

    Default is ``False`` — errors are never silently suppressed unless
    explicitly configured.
    """
    raw = os.environ.get(_SILENT_MODULES_ENV, "")
    if not raw:
        return False
    modules = [m.strip() for m in raw.split(",") if m.strip()]
    return module_name in modules
