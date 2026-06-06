"""Tests for traderbot.error_reporter — centralized error reporting utility."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from traderbot.error_reporter import (
    format_cli_error,
    format_error_for_user,
    report_error,
    should_silently_fail,
)
from traderbot.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataError,
    TraderBotError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# format_error_for_user
# ---------------------------------------------------------------------------


class TestFormatErrorForUser:
    """format_error_for_user returns human-readable error strings."""

    def test_traderbot_error_with_code(self) -> None:
        exc = TraderBotError("auth failed", error_code=1001)
        assert format_error_for_user(exc) == "[E1001] auth failed"

    def test_traderbot_error_without_code(self) -> None:
        exc = TraderBotError("plain error")
        assert format_error_for_user(exc) == "plain error"

    def test_traderbot_error_zero_code(self) -> None:
        exc = TraderBotError("zero code", error_code=0)
        assert format_error_for_user(exc) == "zero code"

    def test_subclass_with_code(self) -> None:
        exc = ConfigurationError("missing key", error_code=2001)
        assert format_error_for_user(exc) == "[E2001] missing key"

    def test_subclass_with_default_code(self) -> None:
        exc = AuthenticationError("bad token")
        # AuthenticationError defaults to error_code=2000
        assert format_error_for_user(exc) == "[E2000] bad token"

    def test_subclass_explicit_no_code(self) -> None:
        exc = AuthenticationError("no code", error_code=0)
        assert format_error_for_user(exc) == "no code"

    def test_standard_exception(self) -> None:
        exc = ValueError("something went wrong")
        assert format_error_for_user(exc) == "something went wrong"

    def test_runtime_error(self) -> None:
        exc = RuntimeError("unexpected state")
        assert format_error_for_user(exc) == "unexpected state"

    def test_empty_message(self) -> None:
        exc = TraderBotError()
        assert format_error_for_user(exc) == ""

    def test_empty_standard_exception(self) -> None:
        exc = ValueError()
        assert format_error_for_user(exc) == ""


# ---------------------------------------------------------------------------
# format_cli_error
# ---------------------------------------------------------------------------


class TestFormatCliError:
    """format_cli_error returns Rich-markup-formatted strings."""

    def test_traderbot_error_with_code(self) -> None:
        exc = TraderBotError("auth failed", error_code=1001)
        assert format_cli_error(exc) == "[red]Error [E1001]:[/red] auth failed"

    def test_traderbot_error_without_code(self) -> None:
        exc = TraderBotError("plain error")
        assert format_cli_error(exc) == "[red]Error:[/red] plain error"

    def test_traderbot_error_zero_code(self) -> None:
        exc = TraderBotError("zero code", error_code=0)
        assert format_cli_error(exc) == "[red]Error:[/red] zero code"

    def test_subclass_with_code(self) -> None:
        exc = DataError("provider down", error_code=3001)
        assert format_cli_error(exc) == "[red]Error [E3001]:[/red] provider down"

    def test_subclass_with_default_code(self) -> None:
        exc = ValidationError("bad input")
        # ValidationError defaults to error_code=5000
        assert format_cli_error(exc) == "[red]Error [E5000]:[/red] bad input"

    def test_subclass_explicit_no_code(self) -> None:
        exc = ValidationError("no code", error_code=0)
        assert format_cli_error(exc) == "[red]Error:[/red] no code"

    def test_standard_exception(self) -> None:
        exc = ValueError("something went wrong")
        assert format_cli_error(exc) == "[red]Error:[/red] something went wrong"

    def test_runtime_error(self) -> None:
        exc = RuntimeError("unexpected state")
        assert format_cli_error(exc) == "[red]Error:[/red] unexpected state"


# ---------------------------------------------------------------------------
# should_silently_fail
# ---------------------------------------------------------------------------


class TestShouldSilentlyFail:
    """should_silently_fail reads TRADERBOT_SILENT_MODULES env var."""

    def test_defaults_to_false(self, monkeypatch) -> None:
        monkeypatch.delenv("TRADERBOT_SILENT_MODULES", raising=False)
        assert should_silently_fail("traderbot.kalshi") is False

    def test_empty_env_defaults_to_false(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "")
        assert should_silently_fail("traderbot.kalshi") is False

    def test_matching_module_returns_true(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "traderbot.kalshi,traderbot.news")
        assert should_silently_fail("traderbot.kalshi") is True

    def test_non_matching_module_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "traderbot.news")
        assert should_silently_fail("traderbot.kalshi") is False

    def test_whitespace_handling(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", " traderbot.kalshi , traderbot.risk ")
        assert should_silently_fail("traderbot.kalshi") is True
        assert should_silently_fail("traderbot.risk") is True

    def test_single_module(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "traderbot.news")
        assert should_silently_fail("traderbot.news") is True
        assert should_silently_fail("traderbot.kalshi") is False

    def test_trailing_commas(self, monkeypatch) -> None:
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "traderbot.kalshi,,traderbot.news,")
        assert should_silently_fail("traderbot.kalshi") is True
        assert should_silently_fail("traderbot.news") is True

    def test_exact_match_required(self, monkeypatch) -> None:
        """Module names are matched exactly, not prefix-style."""
        monkeypatch.setenv("TRADERBOT_SILENT_MODULES", "traderbot.kalshi")
        assert should_silently_fail("traderbot.kalshi.client") is False
        assert should_silently_fail("traderbot") is False


# ---------------------------------------------------------------------------
# report_error
# ---------------------------------------------------------------------------


class TestReportError:
    """report_error logs at the appropriate level and returns formatted string."""

    def test_traderbot_error_critical_threshold(self) -> None:
        """TraderBotError with error_code >= 5000 logs CRITICAL."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("fatal failure", error_code=5000)
        result = report_error(exc, log=mock_logger)
        mock_logger.critical.assert_called_once()
        assert result == "[E5000] fatal failure"

    def test_traderbot_error_above_critical_threshold(self) -> None:
        """TraderBotError with error_code > 5000 logs CRITICAL."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("very fatal", error_code=9999)
        report_error(exc, log=mock_logger)
        mock_logger.critical.assert_called_once()

    def test_traderbot_error_below_critical_logs_error(self) -> None:
        """TraderBotError with error_code < 5000 logs ERROR."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("recoverable", error_code=4000)
        result = report_error(exc, log=mock_logger)
        mock_logger.error.assert_called_once()
        assert result == "[E4000] recoverable"

    def test_traderbot_error_zero_code_logs_error(self) -> None:
        """TraderBotError with error_code 0 logs ERROR."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("no code")
        result = report_error(exc, log=mock_logger)
        mock_logger.error.assert_called_once()
        assert result == "no code"

    def test_standard_exception_logs_warning(self) -> None:
        """Non-TraderBotError exceptions log at WARNING level."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = ValueError("bad value")
        report_error(exc, log=mock_logger)
        mock_logger.warning.assert_called_once()

    def test_runtime_error_logs_warning(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        exc = RuntimeError("unexpected")
        report_error(exc, log=mock_logger)
        mock_logger.warning.assert_called_once()

    def test_subclass_critical(self) -> None:
        """Subclass of TraderBotError with high error_code logs CRITICAL."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = ConfigurationError("fatal config", error_code=6000)
        report_error(exc, log=mock_logger)
        mock_logger.critical.assert_called_once()

    def test_subclass_error(self) -> None:
        """Subclass of TraderBotError with low error_code logs ERROR."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = AuthenticationError("bad creds", error_code=1001)
        result = report_error(exc, log=mock_logger)
        mock_logger.error.assert_called_once()
        assert result == "[E1001] bad creds"

    def test_context_included_in_log(self) -> None:
        """Context dict is passed as extra to logger."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("test", error_code=100)
        report_error(exc, context={"ticker": "BTC-24H"}, log=mock_logger)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1].get("extra") == {"ticker": "BTC-24H"}

    def test_context_empty_dict_not_passed(self) -> None:
        """Empty context dict should not add extra."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("test", error_code=100)
        report_error(exc, context={}, log=mock_logger)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1].get("extra") is None

    def test_context_none_not_passed(self) -> None:
        """None context should not add extra."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("test", error_code=100)
        report_error(exc, context=None, log=mock_logger)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1].get("extra") is None

    def test_correlation_id_in_extra(self) -> None:
        """When operation_id_var is set, it's included in extra."""
        from traderbot.logging_config import correlation_id

        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("with correlation", error_code=200)
        with correlation_id("op-456"):
            report_error(exc, log=mock_logger)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1]["extra"]["operation_id"] == "op-456"

    def test_correlation_id_with_context(self) -> None:
        """Both correlation_id and context are merged into extra."""
        from traderbot.logging_config import correlation_id

        mock_logger = MagicMock(spec=logging.Logger)
        exc = TraderBotError("combined", error_code=300)
        with correlation_id("op-789"):
            report_error(exc, context={"ticker": "ETH-24H"}, log=mock_logger)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1]["extra"]["operation_id"] == "op-789"
        assert call_kwargs[1]["extra"]["ticker"] == "ETH-24H"

    def test_default_logger(self) -> None:
        """Uses module logger when none specified."""
        exc = TraderBotError("default logger test", error_code=100)
        result = report_error(exc)
        assert result == "[E100] default logger test"

    def test_warning_with_context_appends_to_message(self) -> None:
        """Non-TraderBotError with context appends key=value to message."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = ValueError("bad value")
        report_error(exc, context={"key": "val"}, log=mock_logger)
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        logged_msg = call_args[0][0]
        assert "bad value" in logged_msg
        assert "key=val" in logged_msg

    def test_warning_without_context(self) -> None:
        """Non-TraderBotError without context uses plain message."""
        mock_logger = MagicMock(spec=logging.Logger)
        exc = ValueError("simple error")
        report_error(exc, log=mock_logger)
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "simple error"

    def test_returns_formatted_string(self) -> None:
        """Return value matches format_error_for_user output."""
        exc = TraderBotError("test msg", error_code=42)
        mock_logger = MagicMock(spec=logging.Logger)
        result = report_error(exc, log=mock_logger)
        assert result == format_error_for_user(exc)
