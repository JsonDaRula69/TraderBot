from __future__ import annotations

from traderbot.kalshi._transport import KALSHI_ENVIRONMENTS, Environment, KalshiTransport
from traderbot.kalshi.errors import (
    AuthenticationError,
    ConfigurationError,
    KalshiAPIError,
    KalshiError,
    RateLimitError,
    RetryExhaustedError,
)


class KalshiClient(KalshiTransport):
    pass


__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "Environment",
    "KALSHI_ENVIRONMENTS",
    "KalshiAPIError",
    "KalshiClient",
    "KalshiError",
    "RateLimitError",
    "RetryExhaustedError",
]
