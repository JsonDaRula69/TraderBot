# Simulation & Backtesting

How BetBot tests strategies before risking real money — and how it learns from results.

## Why Custom Backtesting?

Stock market frameworks (backtrader, zipline, vectorbt) don't fit prediction markets because:

- **Binary outcomes**: Contracts settle at $0 or $1, not continuous price curves
- **Fixed expiry**: Every market has a hard settlement date; no holding indefinitely
- **No shorting**: You buy Yes or No — there's no short-sell mechanism
- **Event-driven pricing**: News moves prices in discontinuous jumps, not gradual trends
- **Different risk model**: Maximum loss is the purchase price; maximum gain is (1 - purchase price) per contract

We build a custom event-driven engine optimized for these characteristics.

## Backtest Engine

`simulation/engine.py` — event-driven backtester for binary outcome instruments.

### Architecture

```
Historical Data (Kalshi API)
        │
        ▼
  ┌─────────────┐
  │ data_loader │ ── Fetch markets, trades, outcomes from historical API
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │   engine    │ ── Replay events chronologically, apply strategy
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ performance │ ── Compute metrics, compare strategies
  └─────────────┘
```

### Event Types

The engine processes events in chronological order:

| Event | Source | Action |
|---|---|---|
| **Market Open** | `historical/markets` | Initialize tracking, compute initial signals |
| **Trade** | `historical/trades` | Update price, check for signal triggers |
| **News** | External (if available) | Update sentiment, potentially trigger re-evaluation |
| **Market Settle** | `historical/markets` (outcome) | Record P&L, compare to prediction, update statistics |

### Strategy Interface

Strategies implement a simple protocol:

```python
class Strategy(Protocol):
    def on_market_open(self, market: Market, context: Context) -> list[Signal]:
        """Called when a new market opens. Return signals to act on."""
        ...

    def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
        """Called on each trade tick. Return signals if conditions met."""
        ...

    def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
        """Called when a market settles. Update internal state."""
        ...
```

The engine replays historical events through the strategy, tracking simulated positions, fills, and P&L as if the strategy had run live.

### Context Object

The `Context` provides the strategy with read-only access to:

- **Current portfolio**: positions, cash, total value
- **Market data**: orderbook snapshot, recent trades
- **Sentiment**: current news sentiment for relevant categories
- **Risk state**: current circuit breaker level, daily P&L

The strategy can read but **cannot bypass** risk limits. The engine enforces the same `risk/limits` checks during backtesting as during live trading.

## Data Loading

`simulation/data_loader.py` — fetches and caches historical data from Kalshi.

### Loading Workflow

1. Call `GET /historical/cutoff` to get the live/historical boundary
2. Fetch resolved markets via `GET /historical/markets` with time range
3. For each market, fetch trade history via `GET /historical/trades`
4. Paginate through trades (1000 per page) to build complete timeline
5. Cache locally in SQLite — avoid re-fetching on repeated backtests

### Caching Strategy

Historical data doesn't change — settled markets and their trades are immutable. Cache aggressively.

```python
class DataLoader:
    async def get_markets(self, start: date, end: date) -> list[Market]:
        """Fetches from cache first, falls back to API."""

    async def get_trades(self, ticker: str) -> list[Trade]:
        """Fetches from cache first, paginates API if needed."""

    async def get_outcomes(self, tickers: list[str]) -> dict[str, bool]:
        """Returns settlement results for a list of markets."""
```

### Data Quality Checks

Before running a backtest, the loader validates:

- **Completeness**: Are there gaps in the trade timeline? (Missing hours/days)
- **Settlement consistency**: Do trade prices make sense given the outcome?
- **Liquidity**: Did the market have sufficient volume to be tradeable?

Markets or periods that fail quality checks are flagged in results.

## Paper Trading

`simulation/paper_trader.py` — simulates execution against live market data without real money.

### How It Works

1. Connects to Kalshi's **demo API** (`demo-api.kalshi.co`)
2. Submits orders via the demo API (identical flow to production)
3. Tracks fills, slippage, and P&L just like real trading
4. Records decisions in the same audit trail format

Paper trading is the bridge between backtesting and live trading. It validates that the strategy works when connected to a real API with real latency, real orderbook dynamics, and real fill mechanics — but with no money at risk.

### Transition to Live

When a strategy passes paper trading validation:

1. Review paper trading P&L and decision quality
2. Start live trading at reduced position size (25% of normal)
3. Monitor for 1 week at reduced size
4. If metrics match paper results, scale to full size

## Performance Metrics

`simulation/performance.py` — standardized metrics for strategy evaluation.

### Core Metrics

| Metric | Description | Formula |
|---|---|---|
| **Win Rate** | % of trades that were profitable | winning_trades / total_trades |
| **Avg P&L per Trade** | Mean profit/loss across all trades | sum(pnl) / n_trades |
| **Sharpe Ratio** | Risk-adjusted return (annualized) | mean(excess_return) / std(excess_return) × √252 |
| **Max Drawdown** | Largest peak-to-trough decline | max(peak - trough) / peak |
| **Calmar Ratio** | Return vs. max drawdown | annualized_return / max_drawdown |
| **Edge Realization** | Predicted edge vs. actual outcome | mean(predicted_edge - actual_edge) |

### Prediction Market Specific Metrics

| Metric | Description |
|---|---|
| **Brier Score** | Accuracy of probability estimates (lower = better) |
| **Calibration** | When we estimate 70% probability, do we win ~70% of the time? |
| **Edge capture** | What fraction of identified edge do we actually capture after slippage? |
| **Fill rate** | What % of our orders actually get filled? |

### Strategy Comparison

`betbot compare strategy_a strategy_b` runs both strategies on the same historical data and produces a side-by-side comparison across all metrics.

## Backtesting Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| **Survivorship bias** | We only see markets that existed, not ones that were delisted | Include all historical markets, including low-volume ones |
| **Look-ahead bias** | Strategy might implicitly use future information | Strict chronological replay; no peeking at settlement before it happens |
| **Execution assumptions** | Backtest assumes instant fills at trade price | Model slippage: use worst-case fill within spread |
| **Market impact** | Small markets move when large orders enter | Flag markets where our order would exceed 5% of daily volume |
| **News data gaps** | Historical news is harder to reconstruct than trades | Note this limitation; sentiment signals may be less reliable in backtests |