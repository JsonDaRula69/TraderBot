"""Kalshi exchange adapter — v2 (rebuilt from DD-015, DD-016 architecture).

Public API surface for the Phase 2 REST client:

* :class:`KalshiClient` — async REST client with RSA-PSS auth, TLS pinning,
  and token-bucket rate limiting (``traderbot.kalshi.client``).
* :func:`auth_headers` — low-level RSA-PSS request signing
  (``traderbot.kalshi.signing``).
* :func:`create_pinned_ssl_context` — TLS SPKI pinning context
  (``traderbot.kalshi.pinning``).
* :class:`RateLimiter` / :class:`TokenBucketRateLimiter` — token-bucket rate
  limiter (``traderbot.kalshi.rate_limit``).
* Data models (``traderbot.kalshi.models``): MarketCategory, Market, Order,
  Fill, OrderBook, Ticker, and friends.

Credentials come from :class:`traderbot.secrets.store.SecretsStore` — the
client never reads env files or keyring.
"""

from traderbot.kalshi.client import (
    AuthenticationError,
    ConfigurationError,
    Environment,
    KalshiAPIError,
    KalshiClient,
    KalshiError,
    RateLimitError,
)
from traderbot.kalshi.models import (
    CancelResponse,
    CutoffTimestamps,
    Decision,
    Event,
    ExchangeStatus,
    Fill,
    Market,
    MarketCategory,
    MarketListResponse,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderRequest,
    OrderResponse,
    OrderResult,
    OrderSide,
    OrderSideV2,
    OrderStatus,
    OrderType,
    PortfolioState,
    Position,
    RiskCheckResult,
    Settlement,
    Ticker,
    Trade,
    TradeListResponse,
    TradeRequest,
    TradingOrder,
)
from traderbot.kalshi.pinning import CertPinningError, create_pinned_ssl_context
from traderbot.kalshi.rate_limit import RateLimiter, TokenBucketRateLimiter
from traderbot.kalshi.signing import auth_headers, clear_key_cache, sign_request

__all__ = [
    "AuthenticationError",
    "CancelResponse",
    "CertPinningError",
    "ConfigurationError",
    "CutoffTimestamps",
    "Decision",
    "Environment",
    "Event",
    "ExchangeStatus",
    "Fill",
    "KalshiAPIError",
    "KalshiClient",
    "KalshiError",
    "Market",
    "MarketCategory",
    "MarketListResponse",
    "Order",
    "OrderBook",
    "OrderBookLevel",
    "OrderRequest",
    "OrderResponse",
    "OrderResult",
    "OrderSide",
    "OrderSideV2",
    "OrderStatus",
    "OrderType",
    "PortfolioState",
    "Position",
    "RateLimitError",
    "RateLimiter",
    "RiskCheckResult",
    "Settlement",
    "Ticker",
    "TokenBucketRateLimiter",
    "Trade",
    "TradeListResponse",
    "TradeRequest",
    "TradingOrder",
    "auth_headers",
    "clear_key_cache",
    "create_pinned_ssl_context",
    "sign_request",
]
