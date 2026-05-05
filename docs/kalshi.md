# Kalshi Exchange Integration

Everything about connecting to Kalshi's API — authentication, endpoints, data access, and constraints.

## API Overview

| Detail | Value |
|---|---|
| **Base URL (production)** | `https://api.elections.kalshi.com/trade-api/v2` |
| **Base URL (demo)** | `https://demo-api.kalshi.co/trade-api/v2` |
| **Auth method** | RSA-PSS signed headers (KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP) |
| **Rate limit** | ~10 requests/second |
| **Docs** | [docs.kalshi.com](https://docs.kalshi.com) |

## Authentication

Kalshi uses per-request RSA-PSS signing. Each request includes three HTTP headers: `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, and `KALSHI-ACCESS-TIMESTAMP`. The signature is computed by signing `{timestamp_ms}{METHOD}{path}` with RSA-PSS/SHA256/MGF1.

**Required environment variables:**
```bash
KALSHI_API_KEY=your_key_id                # Identifies the user — not secret
KALSHI_PRIVATE_KEY_PEM=-----BEGIN...      # PEM-encoded RSA private key — never commit
```

Our `kalshi/signing.py` implements `auth_headers()` which generates the three required headers per request. `kalshi/client.py` calls this on every HTTP request — no session tokens or login step needed.

## Key Endpoints

### Market Data (public, no auth required)

| Endpoint | Description | Key Parameters |
|---|---|---|
| `GET /markets` | List all markets | `limit`, `cursor`, `event_ticker`, `series_ticker`, `min_close_ts`, `max_close_ts` |
| `GET /markets/{ticker}` | Single market detail | — |
| `GET /markets/{ticker}/orderbook` | Current order book | `depth` |
| `GET /markets/trades` | Recent trades | `ticker` (required), `limit`, `cursor` |
| `GET /events` | List events (groups of markets) | `limit`, `cursor`, `state` |
| `GET /events/{event_ticker}` | Single event detail | — |

### Trading (auth required)

| Endpoint | Description |
|---|---|
| `POST /portfolio/orders` | Place a new order |
| `DELETE /portfolio/orders/{order_id}` | Cancel an order |
| `GET /portfolio/orders` | List resting orders |
| `GET /portfolio/fills` | List filled orders |

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
| `wss://demo-api.kalshi.co/trade-api/ws/v2` | Demo real-time data |

WebSocket auth is sent as HTTP headers during the handshake (same RSA-PSS signing as REST). Subscribe format: `{"id": N, "cmd": "subscribe", "params": {"channels": ["ticker"], "market_ticker": "XXX"}}`.

## Historical Data

Kalshi partitions data into **live** and **historical** tiers. Live endpoints return current/recent data; historical endpoints serve older settled data. This partitioning keeps the live API fast.

### Determining the Cutoff

Before querying historical data, call the cutoff endpoint:

```
GET /historical/cutoff
```

Returns timestamps for each data type (market_settled_ts, trade_cutoff_ts, order_cutoff_ts). Data older than these timestamps must be fetched from historical endpoints.

### Historical Endpoints

| Endpoint | Description | Key Parameters |
|---|---|---|
| `GET /historical/cutoff` | Cutoff timestamps | — |
| `GET /historical/markets` | Settled markets before cutoff | `min_settled_ts`, `max_settled_ts`, `event_ticker` |
| `GET /historical/markets/{ticker}` | Single historical market | — |
| `GET /historical/trades` | Trades filled before cutoff | `min_ts`, `max_ts`, `ticker`, `limit` (max 1000) |
| `GET /historical/orders` | Canceled/executed orders before cutoff | `min_ts`, `max_ts`, `ticker` |

### Backtesting Data Strategy

Kalshi does **not** provide pre-aggregated candlestick/OHLCV data. To reconstruct price series:

1. Fetch resolved markets via `GET /historical/markets` — includes settlement outcome
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
- **Demo mode** — swaps base URL to demo API for paper trading

```python
# Intended usage pattern
from traderbot.kalshi import KalshiClient

client = KalshiClient()  # reads env vars automatically
markets = await client.list_markets(state="open")
orderbook = await client.get_orderbook("KXBTCD-26MAR31-T55000")
result = await client.place_order(ticker="KXBTCD-26MAR31-T55000", action="buy", side="yes", yes_price=55, count=10)
```

## Market Data Model

Key Pydantic models in `kalshi/models.py`:

- **Market**: ticker, question, outcome prices, volume, open_interest, close_time, status
- **OrderBook**: yes/no bids and asks with depth
- **Trade**: timestamp, price, quantity, side
- **Order**: id, ticker, side, price, quantity, status, created_time
- **Position**: ticker, quantity, avg_price, settlement_result
- **Fill**: order_id, ticker, side, price, quantity, timestamp

## Constraints

- **No shorting** — Kalshi is a binary options exchange; you buy Yes or No contracts
- **Fixed expiry** — every market has a defined settlement date; no perpetual positions
- **Binary outcomes** — contracts settle at $1 (correct) or $0 (incorrect)
- **Minimum order size** — 1 contract (typically $1 notional)
- **Settlement delay** — markets resolve after the event, not in real-time