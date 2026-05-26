# Kalshi Exchange Integration

Everything about connecting to Kalshi's API — authentication, endpoints, data access, and constraints.

## API Overview

| Detail | Value |
|---|---|
| **Base URL (production)** | `https://api.elections.kalshi.com/trade-api/v2` |
| **Auth method** | RSA-PSS signed headers (KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP) |
| **Rate limit** | Default 20 rps (configurable via `KALSHI_RATE_LIMIT_RPS` env var) |
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
| `wss://api.elections.kalshi.com/trade-api/ws/v2` | Production real-time data |

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

## Client Usage

Our `kalshi/client.py` implements direct HTTP calls with:

- **Per-request RSA-PSS auth** — `auth_headers()` signs each request via `signing.py`
- **Automatic retry** with exponential backoff (handles transient 5xx errors)
- **Token bucket rate limiter** — respects configured req/sec, queues requests when approaching limit
- **Type normalization** — converts raw API responses to our Pydantic models

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