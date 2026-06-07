"""Tests for domain-specific exception hierarchy in traderbot.exceptions."""

from __future__ import annotations

import pytest

from traderbot.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataError,
    ErrorCodes,
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

    def test_error_code_defaults_to_zero(self) -> None:
        """error_code must default to 0."""
        exc = TraderBotError("test")
        assert exc.error_code == 0

    def test_error_code_stored_from_keyword(self) -> None:
        """error_code keyword must be stored."""
        exc = TraderBotError("test", error_code=1000)
        assert exc.error_code == 1000

    def test_str_with_error_code_returns_formatted(self) -> None:
        """str(exc) must return '[E{code}] {message}' when error_code is set."""
        exc = TraderBotError("test", error_code=1000)
        assert str(exc) == "[E1000] test"

    def test_str_without_error_code_returns_message(self) -> None:
        """str(exc) must return plain message when error_code is 0."""
        exc = TraderBotError("test")
        assert str(exc) == "test"

    def test_error_code_backward_compatible(self) -> None:
        """TraderBotError("test") must still work without error_code."""
        exc = TraderBotError("test")
        assert exc.message == "test"
        assert exc.error_code == 0
        assert str(exc) == "test"


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
        assert str(exc) == "[E1000] bad config"

    def test_str_without_error_code_returns_message(self) -> None:
        exc = ConfigurationError("bad config", error_code=0)
        assert str(exc) == "bad config"

    def test_default_error_code(self) -> None:
        exc = ConfigurationError("test")
        assert exc.error_code == ErrorCodes.CONFIGURATION


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
        assert str(exc) == "[E2000] auth failed"

    def test_str_without_error_code_returns_message(self) -> None:
        exc = AuthenticationError("auth failed", error_code=0)
        assert str(exc) == "auth failed"

    def test_default_error_code(self) -> None:
        exc = AuthenticationError("test")
        assert exc.error_code == ErrorCodes.AUTHENTICATION


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
        assert str(exc) == "[E3000] 429"

    def test_str_without_error_code_returns_message(self) -> None:
        exc = RateLimitError("429", error_code=0)
        assert str(exc) == "429"

    def test_default_error_code(self) -> None:
        exc = RateLimitError("rate limited")
        assert exc.error_code == ErrorCodes.RATE_LIMIT

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
        assert str(exc) == "[E4000] data failure"

    def test_str_without_error_code_returns_message(self) -> None:
        exc = DataError("data failure", error_code=0)
        assert str(exc) == "data failure"

    def test_default_error_code(self) -> None:
        exc = DataError("test")
        assert exc.error_code == ErrorCodes.DATA


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
        assert str(exc) == "[E5000] bad input"

    def test_str_without_error_code_returns_message(self) -> None:
        exc = ValidationError("bad input", error_code=0)
        assert str(exc) == "bad input"

    def test_default_error_code(self) -> None:
        exc = ValidationError("test")
        assert exc.error_code == ErrorCodes.VALIDATION


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


class TestErrorCodes:
    """ErrorCodes namespace provides centralized error code constants."""

    def test_all_codes_are_ints(self) -> None:
        for name in [
            "CONFIGURATION", "AUTHENTICATION", "RATE_LIMIT", "DATA",
            "VALIDATION", "RISK_CHECK", "PRODUCTION_API", "CERT_PINNING",
            "NEWS_API", "NWS_CLIENT", "CONCURRENT_WRITE", "BACKTEST",
            "TOKEN_ALREADY_ASSIGNED", "LLM", "OLLAMA_CONNECTION", "NEWS_BUDGET",
        ]:
            assert isinstance(getattr(ErrorCodes, name), int), f"ErrorCodes.{name} must be int"

    def test_all_codes_are_unique(self) -> None:
        codes = [
            ErrorCodes.CONFIGURATION, ErrorCodes.AUTHENTICATION, ErrorCodes.RATE_LIMIT,
            ErrorCodes.DATA, ErrorCodes.VALIDATION, ErrorCodes.RISK_CHECK,
            ErrorCodes.PRODUCTION_API, ErrorCodes.CERT_PINNING, ErrorCodes.NEWS_API,
            ErrorCodes.NWS_CLIENT, ErrorCodes.CONCURRENT_WRITE, ErrorCodes.BACKTEST,
            ErrorCodes.TOKEN_ALREADY_ASSIGNED, ErrorCodes.LLM,
            ErrorCodes.OLLAMA_CONNECTION, ErrorCodes.NEWS_BUDGET,
        ]
        assert len(codes) == len(set(codes)), "All error codes must be unique"


class TestMigratedOrphanExceptions:
    """All formerly-orphan exceptions now inherit from TraderBotError."""

    def test_risk_check_error_inherits_trader_bot_error(self) -> None:
        from traderbot.risk import RiskCheckError

        assert issubclass(RiskCheckError, TraderBotError)

    def test_risk_check_error_catchable(self) -> None:
        from traderbot.kalshi.models import RiskCheckResult
        from traderbot.risk import RiskCheckError

        failure = RiskCheckResult(
            limit_name="max_position",
            passed=False,
            current_value=10,
            limit_value=5,
            rejection_reason="over limit",
        )
        exc = RiskCheckError("TICK", [failure])
        assert isinstance(exc, TraderBotError)
        assert exc.ticker == "TICK"
        assert exc.failures == [failure]
        assert "E6000" in str(exc)

    def test_risk_check_error_error_code(self) -> None:
        from traderbot.kalshi.models import RiskCheckResult
        from traderbot.risk import RiskCheckError

        failure = RiskCheckResult(
            limit_name="max_position",
            passed=False,
            current_value=10,
            limit_value=5,
            rejection_reason="over limit",
        )
        exc = RiskCheckError("TICK", [failure])
        assert exc.error_code == ErrorCodes.RISK_CHECK

    def test_prod_api_error_inherits_trader_bot_error(self) -> None:
        from traderbot.kalshi.provider import ProdAPIError

        assert issubclass(ProdAPIError, TraderBotError)
        exc = ProdAPIError("api failure")
        assert isinstance(exc, TraderBotError)
        assert "[E7000]" in str(exc)

    def test_cert_pinning_error_inherits_trader_bot_error(self) -> None:
        from traderbot.kalshi.pinning import CertPinningError

        assert issubclass(CertPinningError, TraderBotError)
        exc = CertPinningError("pin mismatch")
        assert isinstance(exc, TraderBotError)
        assert "[E7100]" in str(exc)

    def test_news_api_error_inherits_trader_bot_error(self) -> None:
        from traderbot.news.sources import NewsAPIError

        assert issubclass(NewsAPIError, TraderBotError)
        assert issubclass(NewsAPIError, DataError)
        exc = NewsAPIError("http 500")
        assert isinstance(exc, TraderBotError)
        assert isinstance(exc, DataError)
        assert "[E8000]" in str(exc)

    def test_news_api_auth_error_inherits_authentication_error(self) -> None:
        from traderbot.news.sources import NewsAPIAuthError

        assert issubclass(NewsAPIAuthError, TraderBotError)
        assert issubclass(NewsAPIAuthError, AuthenticationError)
        exc = NewsAPIAuthError("invalid key")
        assert isinstance(exc, TraderBotError)
        assert isinstance(exc, AuthenticationError)
        assert "[E2000]" in str(exc)

    def test_news_api_budget_exceeded_inherits_rate_limit_error(self) -> None:
        from traderbot.news.sources import NewsAPIBudgetExceededError

        assert issubclass(NewsAPIBudgetExceededError, TraderBotError)
        assert issubclass(NewsAPIBudgetExceededError, RateLimitError)
        exc = NewsAPIBudgetExceededError("budget exhausted")
        assert isinstance(exc, TraderBotError)
        assert isinstance(exc, RateLimitError)
        assert "[E8200]" in str(exc)

    def test_concurrent_write_error_inherits_trader_bot_error(self) -> None:
        from traderbot.wal import ConcurrentWriteError

        assert issubclass(ConcurrentWriteError, TraderBotError)
        exc = ConcurrentWriteError("write collision")
        assert isinstance(exc, TraderBotError)
        assert "[E9000]" in str(exc)

    def test_backtest_error_inherits_trader_bot_error(self) -> None:
        from traderbot.simulation.engine import BacktestError

        assert issubclass(BacktestError, TraderBotError)
        exc = BacktestError("invalid state")
        assert isinstance(exc, TraderBotError)
        assert "[E10000]" in str(exc)

    def test_nws_client_error_inherits_data_error(self) -> None:
        from traderbot.data.weather.nws_client import NwsClientError

        assert issubclass(NwsClientError, TraderBotError)
        assert issubclass(NwsClientError, DataError)
        exc = NwsClientError("nws failure")
        assert isinstance(exc, TraderBotError)
        assert isinstance(exc, DataError)
        assert "[E8100]" in str(exc)

    def test_llm_client_error_inherits_trader_bot_error(self) -> None:
        from traderbot.llm.client import LLMClientError

        assert issubclass(LLMClientError, TraderBotError)
        exc = LLMClientError("retry exhausted")
        assert isinstance(exc, TraderBotError)
        assert "[E12000]" in str(exc)

    def test_ollama_connection_error_inherits_trader_bot_error(self) -> None:
        from traderbot.llm.ollama import OllamaConnectionError

        assert issubclass(OllamaConnectionError, TraderBotError)
        exc = OllamaConnectionError("cannot connect")
        assert isinstance(exc, TraderBotError)
        assert "[E1200]" in str(exc)

    def test_token_already_assigned_inherits_validation_error(self) -> None:
        from traderbot.profiles.tokens import TokenAlreadyAssignedError

        assert issubclass(TokenAlreadyAssignedError, TraderBotError)
        assert issubclass(TokenAlreadyAssignedError, ValidationError)
        exc = TokenAlreadyAssignedError("weather-agent")
        assert isinstance(exc, TraderBotError)
        assert isinstance(exc, ValidationError)
        assert exc.profile_name == "weather-agent"
        assert "[E11000]" in str(exc)

    def test_all_orphans_catchable_as_trader_bot_error(self) -> None:
        """Catching TraderBotError must catch every migrated exception."""
        from traderbot.data.weather.nws_client import NwsClientError
        from traderbot.kalshi.models import RiskCheckResult
        from traderbot.kalshi.pinning import CertPinningError
        from traderbot.kalshi.provider import ProdAPIError
        from traderbot.llm.client import LLMClientError
        from traderbot.llm.ollama import OllamaConnectionError
        from traderbot.news.sources import (
            NewsAPIAuthError,
            NewsAPIBudgetExceededError,
            NewsAPIError,
        )
        from traderbot.profiles.tokens import TokenAlreadyAssignedError
        from traderbot.risk import RiskCheckError
        from traderbot.simulation.engine import BacktestError
        from traderbot.wal import ConcurrentWriteError

        failure = RiskCheckResult(
            limit_name="test", passed=False, current_value=1, limit_value=2,
            rejection_reason="failed",
        )
        errors = [
            RiskCheckError("TICK", [failure]),
            ProdAPIError("api fail"),
            CertPinningError("pin fail"),
            NewsAPIError("news fail"),
            NewsAPIAuthError("auth fail"),
            NewsAPIBudgetExceededError("budget fail"),
            ConcurrentWriteError("write fail"),
            BacktestError("backtest fail"),
            NwsClientError("nws fail"),
            LLMClientError("llm fail"),
            OllamaConnectionError("ollama fail"),
            TokenAlreadyAssignedError("profile1"),
        ]
        caught = []
        for exc in errors:
            try:
                raise exc
            except TraderBotError:
                caught.append(type(exc).__name__)
        assert len(caught) == 12

    def test_risk_check_error_custom_error_code(self) -> None:
        """RiskCheckError can accept a custom error code."""
        from traderbot.kalshi.models import RiskCheckResult
        from traderbot.risk import RiskCheckError

        failure = RiskCheckResult(
            limit_name="test", passed=False, current_value=1, limit_value=2,
            rejection_reason="failed",
        )
        exc = RiskCheckError("TICK", [failure], error_code=9999)
        assert exc.error_code == 9999
        assert "[E9999]" in str(exc)

    def test_token_already_assigned_custom_error_code(self) -> None:
        """TokenAlreadyAssignedError can accept a custom error code."""
        from traderbot.profiles.tokens import TokenAlreadyAssignedError

        exc = TokenAlreadyAssignedError("my-profile", error_code=5555)
        assert exc.error_code == 5555
        assert "[E5555]" in str(exc)


class TestKalshiClientDeprecationWarnings:
    """Deprecation wrappers in kalshi/client.py must emit DeprecationWarning."""

    def test_configuration_error_warns(self) -> None:
        from traderbot.kalshi.client import ConfigurationError

        with pytest.warns(DeprecationWarning, match="kalshi.client.ConfigurationError"):
            ConfigurationError("test")

    def test_rate_limit_error_warns(self) -> None:
        from traderbot.kalshi.client import RateLimitError

        with pytest.warns(DeprecationWarning, match="kalshi.client.RateLimitError"):
            RateLimitError("test")

    def test_authentication_error_warns(self) -> None:
        from traderbot.kalshi.client import AuthenticationError

        with pytest.warns(DeprecationWarning, match="kalshi.client.AuthenticationError"):
            AuthenticationError("test")

    def test_kalshi_configuration_error_catchable_as_base(self) -> None:
        from traderbot.exceptions import ConfigurationError as BaseConfigError
        from traderbot.kalshi.client import ConfigurationError

        with pytest.warns(DeprecationWarning):
            exc = ConfigurationError("test")
        assert isinstance(exc, BaseConfigError)
        assert isinstance(exc, TraderBotError)

    def test_kalshi_rate_limit_error_catchable_as_base(self) -> None:
        from traderbot.exceptions import RateLimitError as BaseRateLimitError
        from traderbot.kalshi.client import RateLimitError

        with pytest.warns(DeprecationWarning):
            exc = RateLimitError("test")
        assert isinstance(exc, BaseRateLimitError)
        assert isinstance(exc, TraderBotError)

    def test_kalshi_authentication_error_catchable_as_base(self) -> None:
        from traderbot.exceptions import AuthenticationError as BaseAuthError
        from traderbot.kalshi.client import AuthenticationError

        with pytest.warns(DeprecationWarning):
            exc = AuthenticationError("test")
        assert isinstance(exc, BaseAuthError)
        assert isinstance(exc, TraderBotError)

    def test_base_exceptions_catch_kalshi_instances(self) -> None:
        """Catching TraderBotError must catch all kalshi/client.py exceptions."""
        from traderbot.kalshi.client import (
            AuthenticationError,
            ConfigurationError,
            RateLimitError,
        )

        with pytest.warns(DeprecationWarning):
            errors = [
                ConfigurationError("a"),
                RateLimitError("b"),
                AuthenticationError("c"),
            ]
        caught = []
        for exc in errors:
            try:
                raise exc
            except TraderBotError:
                caught.append(type(exc).__name__)
        assert len(caught) == 3
