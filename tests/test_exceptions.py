"""Tests for domain-specific exception hierarchy in traderbot.exceptions."""

from __future__ import annotations

import pytest

from traderbot.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataError,
    RateLimitError,
    TraderBotError,
    ValidationError,
)


class TestTraderBotError:
    """Base exception class — the root of the domain hierarchy."""

    def test_is_exception_subclass(self) -> None:
        """TraderBotError must inherit from Exception."""
        assert issubclass(TraderBotError, Exception)

    def test_message_defaults_to_empty_string(self) -> None:
        """Message parameter must default to '' when no argument is passed."""
        exc = TraderBotError()
        assert exc.message == ""

    def test_message_stored_from_positional(self) -> None:
        """Positional argument must be stored as the message attribute."""
        exc = TraderBotError("something went wrong")
        assert exc.message == "something went wrong"

    def test_message_stored_from_keyword(self) -> None:
        """Keyword argument must be stored as the message attribute."""
        exc = TraderBotError(message="explicit keyword")
        assert exc.message == "explicit keyword"

    def test_str_returns_message(self) -> None:
        """str(exc) must return the message attribute."""
        exc = TraderBotError("boom")
        assert str(exc) == "boom"

    def test_str_without_message_returns_empty(self) -> None:
        """str(exc) must return '' when no message is set."""
        exc = TraderBotError()
        assert str(exc) == ""


class TestConfigurationError:
    """ConfigurationError signals missing or invalid configuration."""

    def test_inherits_from_trader_bot_error(self) -> None:
        assert issubclass(ConfigurationError, TraderBotError)

    def test_is_catchable_as_trader_bot_error(self) -> None:
        exc = ConfigurationError("missing API key")
        assert isinstance(exc, TraderBotError)

    def test_is_catchable_as_exception(self) -> None:
        exc = ConfigurationError("missing API key")
        assert isinstance(exc, Exception)

    def test_message_defaults_to_empty_string(self) -> None:
        exc = ConfigurationError()
        assert exc.message == ""

    def test_message_stored(self) -> None:
        exc = ConfigurationError("KALSHI_API_KEY not set")
        assert exc.message == "KALSHI_API_KEY not set"

    def test_str_returns_message(self) -> None:
        exc = ConfigurationError("bad config")
        assert str(exc) == "bad config"


class TestAuthenticationError:
    """AuthenticationError signals credential or auth failures."""

    def test_inherits_from_trader_bot_error(self) -> None:
        assert issubclass(AuthenticationError, TraderBotError)

    def test_is_catchable_as_trader_bot_error(self) -> None:
        exc = AuthenticationError("invalid token")
        assert isinstance(exc, TraderBotError)

    def test_message_defaults_to_empty_string(self) -> None:
        exc = AuthenticationError()
        assert exc.message == ""

    def test_message_stored(self) -> None:
        exc = AuthenticationError("HTTP 401 from Kalshi")
        assert exc.message == "HTTP 401 from Kalshi"

    def test_str_returns_message(self) -> None:
        exc = AuthenticationError("auth failed")
        assert str(exc) == "auth failed"


class TestRateLimitError:
    """RateLimitError signals HTTP 429 or rate-limit exceeded conditions."""

    def test_inherits_from_trader_bot_error(self) -> None:
        assert issubclass(RateLimitError, TraderBotError)

    def test_is_catchable_as_trader_bot_error(self) -> None:
        exc = RateLimitError("too many requests")
        assert isinstance(exc, TraderBotError)

    def test_message_defaults_to_empty_string(self) -> None:
        exc = RateLimitError()
        assert exc.message == ""

    def test_message_stored(self) -> None:
        exc = RateLimitError("Kalshi rate limit exceeded")
        assert exc.message == "Kalshi rate limit exceeded"

    def test_str_returns_message(self) -> None:
        exc = RateLimitError("429")
        assert str(exc) == "429"

    def test_retry_after_seconds_defaults_to_none(self) -> None:
        """When no retry_after is passed, retry_after_seconds must be None."""
        exc = RateLimitError("rate limited")
        assert exc.retry_after_seconds is None

    def test_retry_after_seconds_stored(self) -> None:
        """retry_after_seconds keyword must be stored."""
        exc = RateLimitError("rate limited", retry_after_seconds=30.0)
        assert exc.retry_after_seconds == 30.0

    def test_retry_after_seconds_as_int(self) -> None:
        """retry_after_seconds may be an int (converted to float)."""
        exc = RateLimitError("rate limited", retry_after_seconds=5)
        # Accept both int and float — the attribute just stores the value
        assert exc.retry_after_seconds == 5


class TestDataError:
    """DataError signals data-fetch or processing failures."""

    def test_inherits_from_trader_bot_error(self) -> None:
        assert issubclass(DataError, TraderBotError)

    def test_is_catchable_as_trader_bot_error(self) -> None:
        exc = DataError("FRED data unavailable")
        assert isinstance(exc, TraderBotError)

    def test_message_defaults_to_empty_string(self) -> None:
        exc = DataError()
        assert exc.message == ""

    def test_message_stored(self) -> None:
        exc = DataError("empty response from provider")
        assert exc.message == "empty response from provider"

    def test_str_returns_message(self) -> None:
        exc = DataError("data failure")
        assert str(exc) == "data failure"


class TestValidationError:
    """ValidationError signals input validation failures."""

    def test_inherits_from_trader_bot_error(self) -> None:
        assert issubclass(ValidationError, TraderBotError)

    def test_is_catchable_as_trader_bot_error(self) -> None:
        exc = ValidationError("invalid ticker")
        assert isinstance(exc, TraderBotError)

    def test_message_defaults_to_empty_string(self) -> None:
        exc = ValidationError()
        assert exc.message == ""

    def test_message_stored(self) -> None:
        exc = ValidationError("quantity must be positive")
        assert exc.message == "quantity must be positive"

    def test_str_returns_message(self) -> None:
        exc = ValidationError("bad input")
        assert str(exc) == "bad input"


class TestExceptionHierarchy:
    """Cross-class structural constraints."""

    def test_all_subclasses_are_distinct(self) -> None:
        """Ensure no accidental merging of exception types."""
        subclasses = {
            ConfigurationError,
            AuthenticationError,
            RateLimitError,
            DataError,
            ValidationError,
        }
        assert len(subclasses) == 5

    @pytest.mark.parametrize(
        "exc_cls",
        [
            ConfigurationError,
            AuthenticationError,
            RateLimitError,
            DataError,
            ValidationError,
        ],
    )
    def test_each_is_trader_bot_error(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, TraderBotError)

    def test_catch_all_domain_errors_with_base(self) -> None:
        """All domain exceptions must be catchable via TraderBotError."""
        errors = [
            ConfigurationError("a"),
            AuthenticationError("b"),
            RateLimitError("c"),
            DataError("d"),
            ValidationError("e"),
        ]
        caught = []
        for exc in errors:
            try:
                raise exc
            except TraderBotError:
                caught.append(type(exc).__name__)
        assert len(caught) == 5
