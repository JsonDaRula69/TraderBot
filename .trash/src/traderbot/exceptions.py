"""Domain-specific exception hierarchy for TraderBot.

All exceptions derive from :class:`TraderBotError` so callers can catch the
entire domain with a single ``except TraderBotError`` clause.
"""

from __future__ import annotations


class ErrorCodes:
    """Centralized error code registry.

    Each domain exception has a unique numeric code for programmatic
    identification.  Codes are grouped by category in 1000 increments.
    """

    CONFIGURATION = 1000
    AUTHENTICATION = 2000
    RATE_LIMIT = 3000
    DATA = 4000
    VALIDATION = 5000
    RISK_CHECK = 6000
    PRODUCTION_API = 7000
    CERT_PINNING = 7100
    NEWS_API = 8000
    NWS_CLIENT = 8100
    CONCURRENT_WRITE = 9000
    BACKTEST = 10000
    TOKEN_ALREADY_ASSIGNED = 11000
    LLM = 12000
    OLLAMA_CONNECTION = 1200
    NEWS_BUDGET = 8200


class TraderBotError(Exception):
    """Root exception for the TraderBot domain.

    Parameters
    ----------
    message : str
        Human-readable description of the error (default ``""``).
    error_code : int
        Numeric error code for programmatic handling (default ``0``).
        When non-zero, ``str(exc)`` returns ``[E{code}] {message}``.
    """

    def __init__(self, message: str = "", error_code: int = 0) -> None:
        self.message: str = message
        self.error_code: int = error_code
        super().__init__(message)

    def __str__(self) -> str:
        if self.error_code:
            return f"[E{self.error_code}] {self.message}"
        return self.message


class ConfigurationError(TraderBotError):
    """Raised when required configuration is missing or invalid.

    Examples: missing environment variables, invalid key paths,
    unparsable settings files.
    """

    def __init__(
        self, message: str = "", error_code: int = ErrorCodes.CONFIGURATION, **kwargs
    ) -> None:
        super().__init__(message, error_code=error_code, **kwargs)


class AuthenticationError(TraderBotError):
    """Raised when API authentication or authorization fails.

    Examples: invalid credentials, expired tokens, HTTP 401 / 403.
    """

    def __init__(
        self, message: str = "", error_code: int = ErrorCodes.AUTHENTICATION, **kwargs
    ) -> None:
        super().__init__(message, error_code=error_code, **kwargs)


class RateLimitError(TraderBotError):
    """Raised when an external API returns HTTP 429 or a rate-limit window closes.

    Parameters
    ----------
    message : str
        Error description.
    retry_after_seconds : float | int | None
        Seconds until the rate-limit window resets, if the API provided
        a ``Retry-After`` header (default ``None``).
    """

    def __init__(
        self,
        message: str = "",
        retry_after_seconds: float | int | None = None,
        error_code: int = ErrorCodes.RATE_LIMIT,
    ) -> None:
        self.retry_after_seconds: float | int | None = retry_after_seconds
        super().__init__(message, error_code=error_code)


class DataError(TraderBotError):
    """Raised when fetching or processing external data fails.

    Examples: empty responses, malformed JSON, upstream provider errors,
    network timeouts from data sources.
    """

    def __init__(self, message: str = "", error_code: int = ErrorCodes.DATA, **kwargs) -> None:
        super().__init__(message, error_code=error_code, **kwargs)


class ValidationError(TraderBotError):
    """Raised when input fails domain validation before any I/O occurs.

    Examples: invalid ticker format, negative quantity, out-of-range prices.
    """

    def __init__(
        self, message: str = "", error_code: int = ErrorCodes.VALIDATION, **kwargs
    ) -> None:
        super().__init__(message, error_code=error_code, **kwargs)
