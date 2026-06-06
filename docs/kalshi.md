# Kalshi Exchange Integration

Everything about connecting to Kalshi's API — authentication, endpoints, data access, and constraints.

## API Overview

| Detail | Value |
|---|---|
| **Base URL (production)** | `https://external-api.kalshi.com/trade-api/v2` |
| **Auth method** | RSA-PSS signed headers (KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP) |
| **Rate limit** | Token-budget model (configurable via `KALSHI_READ_BUDGET_TOKENS` and `KALSHI_WRITE_BUDGET_TOKENS` env vars). Effective request rate = budget_tokens / endpoint_cost (default cost=10 tokens per request, so 200 read tokens/sec = 20 RPS, 100 write tokens/sec = 10 RPS). Configure the *token refill rate*, not the desired requests-per-second. |
| **Docs** | [docs.kalshi.com](https://docs.kalshi.com) |

## Authentication

Kalshi uses per-request RSA-PSS signing. Each request includes three HTTP headers: `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, and `KALSHI-ACCESS-TIMESTAMP`. The signature is computed by signing `{timestamp_ms}{METHOD}{path}` with RSA-PSS/SHA256/MGF1. A cryptographically secure nonce is also included to prevent replay attacks.

**Required environment variables:**
```bash
KALSHI_API_KEY=your_key_id                # Identifies the user — not secret
KALSHI_PRIVATE_KEY_PEM=-----BEGIN...      # PEM-encoded RSA private key — never commit
```

Our `kalshi/signing.py` implements `auth_headers()` which generates the three required headers per request. `kalshi/client.py` calls this on every HTTP request — no session tokens or login step needed.

## TLS Certificate Pinning

To defend against corporate MITM proxies or compromised CAs, TraderBot pins Kalshi's TLS certificate by its Subject Public Key Info (SPKI) hash:

- **Production pin**: `Iu/+7wHLhGRvN84Vr2fyW7omLlvfmIcGNnaUf9uTkwA=`
- **Implementation**: `kalshi/pinning.py` — `PinnedSSLContext` subclass
- **Integration**: Both `KalshiClient` (httpx) and `KalshiWebSocket` (websockets) use the pinned SSL context

If the pin does not match, the connection is aborted with a `SecurityError`. If Kalshi rotates certificates, the pin constant in `kalshi/pinning.py` must be updated manually.

## Key Endpoints

### Market Data (public, no auth required)

| Endpoint | Description | Key Parameters |
|---|---|---|---|
| `GET /markets` | List all markets | `limit`, `cursor`, `event_ticker`, `series_ticker`, `status`, `min_close_ts`, `max_close_ts` |
| `GET /markets/{ticker}` | Single market detail | — |
| `GET /markets/{ticker}/orderbook` | Current order book | `depth` |
| `GET /markets/trades` | Recent trades | `ticker` (required), `limit`, `cursor` |
| `GET /events` | List events (groups of markets) | `limit`, `cursor`, `with_nested_markets` |
| `GET /events/{event_ticker}` | Single event detail | — |
| `GET /series` | List series by category | `category` (case-sensitive, title-case) |
| `GET /series/{series_ticker}` | Single series detail | — |

### Trading (auth required)

| Endpoint | Description |
|---|---|
| `POST /portfolio/events/orders` | Place a new order |
| `DELETE /portfolio/events/orders/{order_id}` | Cancel an order |
| `GET /portfolio/events/orders` | List resting orders |
| `GET /portfolio/events/fills` | List filled orders |

### Portfolio (auth required)

| Endpoint | Description |
|---|---|
| `GET /portfolio/balance` | Account balance |
| `GET /portfolio/positions` | Current positions |
| `GET /portfolio/settlements` | Settlement history |

### WebSocket Streams

| Stream | Description |
|---|---|
| `wss://external-api.kalshi.com/trade-api/ws/v2` | Production real-time data |

WebSocket auth is sent as HTTP headers during the handshake (same RSA-PSS signing as REST). Subscribe format: `{"id": N, "cmd": "subscribe", "params": {"channels": ["ticker"], "market_ticker": "XXX"}}`.

## Historical Data

Kalshi partitions data into **live** and **historical** tiers. Live endpoints return current/recent data; historical endpoints serve older settled data. This partitioning keeps the live API fast.

### Historical Endpoints

| Endpoint | Description | Key Parameters |
|---|---|---|
| `GET /historical/markets` | Settled markets | `min_settled_ts`, `max_settled_ts`, `event_ticker` |
| `GET /historical/markets/{ticker}` | Single historical market | — |
| `GET /historical/trades` | Historical trades | `min_ts`, `max_ts`, `ticker`, `limit` (max 1000) |
| `GET /historical/orders` | Canceled/executed orders | `min_ts`, `max_ts`, `ticker` |

> Note: The `/historical/cutoff` endpoint and `CutoffTimestamps` model were removed in v0.10.166. Historical queries now fetch directly without a cutoff check.

### Backtesting Data Strategy

Kalshi does **not** provide pre-aggregated candlestick/OHLCV data. To reconstruct price series:

1. Fetch resolved markets via `GET /historical/markets` with time range — includes settlement outcome
2. Fetch trade history via `GET /historical/trades` with time range filters
3. Paginate through trades (1000 per page) to build complete trade timeline
4. Aggregate trades into candles at desired resolution (1min, 5min, 1hr, etc.)
5. Store locally in SQLite to avoid re-fetching

**Data volume consideration**: Popular markets can have tens of thousands of trades. Plan for pagination and local caching.

## Client Architecture

Our `kalshi/client.py` implements direct HTTP calls with:

- **Per-request RSA-PSS auth** — `auth_headers()` signs each request via `signing.py`
- **Automatic retry** with exponential backoff (handles transient 5xx errors)
- **Token bucket rate limiter** — `TokenBucketRateLimiter` with async `acquire()`. Default 20 rps (configurable). Burst capacity = 2× rate. Acquire blocks via `asyncio.sleep(1/rate)`.
- **Type normalization** — `_normalize.py` bridges V1/V2 API differences: `_to_cents()` (dollars→cents), `_map_category()` (16 raw strings→14 `MarketCategory` enum values), `_normalize_market()` (handles `_fp` suffix, `title` vs `question`, `state` vs `status`)
- **MarketDataCache** — TTL-gated in-memory cache (30s orderbook, 60s market) with SQLite settlement store

### Provider Layer

The `provider.py` module defines a `MarketDataProvider` protocol with immutable snapshot types:

| Symbol | Description |
|---|---|
| `MarketSnapshot` | Immutable market state: ticker, status, open_interest_cents, close_time, settlement_result |
| `OrderBookSnapshot` | Immutable order book with yes/no bid levels |
| `SettlementResult` | Settlement outcome: ticker, outcome (bool), settled_at |
| `ProdDataProvider` | Production impl — backs to `KalshiClient` + optional `MarketDataCache`. Supports batch methods with semaphore-limited concurrency (5 concurrent, 200ms delay between chunks) |
| `MockDataProvider` | Pre-configured dicts for tests and simulation |

### Service Layer

| Service | Exported? | Methods |
|---|---|---|
| `MarketService` | Yes | `get_market`, `get_orderbook`, `get_portfolio`, `list_markets` |
| `EventsService` | Yes | `get_events` (paginated, filterable by state), `get_event` |
| `ExchangeService` | Yes | `get_status` — returns `ExchangeStatus(is_open, description, active_markets)` |
| `PortfolioService` | Yes | `get_balance`, `get_cached_balance` (hourly TTL with stale-on-error), `get_positions`, `get_fills`, `get_settlements` |
| `TradingService` | Yes | `place_order`, `cancel_order`, `get_orders` |
| `HistoryService` | Internal | `get_cutoffs`, `get_historical_trades`, `get_settled_markets` |

### Caching Architecture

Three-tier caching for market data:

| Tier | Module | TTL | Content |
|---|---|---|---|
| **In-memory TTL** | `cache.py` | 30s (orderbook), 60s (market) | Request-level market/orderbook snapshots + SQLite settlement store |
| **WebSocket daemon** | `ws_daemon.py` | Real-time (WebSocket push) | Persistent daemon subscribing to `market_lifecycle_v2` and `ticker` channels; writes `event_category_cache.json` |
| **WebSocket cache reader** | `ws_cache.py` | 30s ticker TTL | Read-side accessors: `get_ticker_price()`, `get_ticker_prices()`, `get_cache_stats()` |

The WebSocket daemon runs as a standalone process (`python -m traderbot.kalshi.ws_daemon`) with exponential reconnect backoff (5s initial, 60s max). It seeds the event→category mapping from the REST API on startup.

```python
# Intended usage pattern
from traderbot.kalshi import KalshiClient

client = KalshiClient()  # reads env vars automatically
markets = await client.list_markets(status="active")
orderbook = await client.get_orderbook("KXBTCD-26MAR31-T55000")
result = await client.place_order(ticker="KXBTCD-26MAR31-T55000", side="bid", price="0.55", count="10")
```

## Market Data Model

Key Pydantic models in `kalshi/models.py`:

- **Market** (V2): ticker, title, status, close_time (ISO datetime), last_price_cents, yes_bid_cents, yes_ask_cents, no_bid_cents, no_ask_cents, volume_fp, open_interest_fp
- **MarketV2**: Raw V2 API response model before normalization
- **OrderBook**: yes/no bids with depth (nested under `orderbook_fp`; Kalshi order books expose bids only, no asks)
- **Trade**: timestamp, price, quantity, side
- **Order**: id, ticker, side, price, quantity, status, created_time
- **Position**: ticker, quantity, avg_price, settlement_result
- **Fill**: order_id, ticker, side, price, quantity, timestamp
- **OrderRequest**: ticker, side (OrderSideV2), count (string), price (string), client_order_id, time_in_force

## Constraints

- **No shorting** — Kalshi is a binary options exchange; you buy Yes or No contracts
- **Fixed expiry** — every market has a defined settlement date; no perpetual positions
- **Binary outcomes** — contracts settle at $1 (correct) or $0 (incorrect)
- **Minimum order size** — 1 contract (typically $1 notional)
- **Settlement delay** — markets resolve after the event, not in real-time