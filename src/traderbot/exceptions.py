"""Domain-specific exception hierarchy for TraderBot.

All exceptions derive from :class:`TraderBotError` so callers can catch the
entire domain with a single ``except TraderBotError`` clause.
"""

from __future__ import annotations


class TraderBotError(Exception):
    """Root exception for the TraderBot domain.

    Parameters
    ----------
    message : str
        Human-readable description of the error (default ``""``).
    """

    def __init__(self, message: str = "") -> None:
        self.message: str = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class ConfigurationError(TraderBotError):
    """Raised when required configuration is missing or invalid.

    Examples: missing environment variables, invalid key paths,
    unparsable settings files.
    """


class AuthenticationError(TraderBotError):
    """Raised when API authentication or authorization fails.

    Examples: invalid credentials, expired tokens, HTTP 401 / 403.
    """


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
    ) -> None:
        self.retry_after_seconds: float | int | None = retry_after_seconds
        super().__init__(message)


class DataError(TraderBotError):
    """Raised when fetching or processing external data fails.

    Examples: empty responses, malformed JSON, upstream provider errors,
    network timeouts from data sources.
    """


class ValidationError(TraderBotError):
    """Raised when input fails domain validation before any I/O occurs.

    Examples: invalid ticker format, negative quantity, out-of-range prices.
    """
