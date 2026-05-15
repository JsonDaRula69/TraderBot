# Simulation & Backtesting

How TraderBot tests strategies before risking real money — and how it learns from results.

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

1. Fetch resolved markets via `GET /historical/markets` with time range
2. For each market, fetch trade history via `GET /historical/trades`
3. Paginate through trades (1000 per page) to build complete timeline
4. Cache locally in SQLite — avoid re-fetching on repeated backtests

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

1. Reads real market data from Kalshi's prod API — all orders simulated locally
2. Tracks fills, slippage, and P&L against live market prices without submitting any real orders
3. Records decisions in the same audit trail format

Paper trading is the bridge between backtesting and live trading. It validates that the strategy works when connected to a real API with real latency, real orderbook dynamics, and real fill mechanics — but with no money at risk. All orders are simulated locally; no trades are submitted to the exchange.

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
| **Sharpe Ratio** | Risk-adjusted return (annualized, Bessel-corrected) | mean(excess_return) / std(excess_return, ddof=1) × √252 |
| **Max Drawdown** | Largest peak-to-trough decline | max(peak - trough) / peak |
| **Calmar Ratio** | Return vs. max drawdown | annualized_return / max_drawdown |
| **Edge Realization** | Predicted edge vs. actual outcome | mean(predicted_edge - actual_edge) |

### Prediction Market Specific Metrics

| Metric | Description | Computation |
163:|---|---|---|
| **Brier Score** | Accuracy of probability estimates (lower = better) | Mean of (predicted_prob - actual_outcome)² across all closed trades. For yes positions, predicted = entry_price/100; for no positions, predicted = 1 - entry_price/100. Actual = 1 if profitable, 0 if loss. |
| **Calibration** | When we estimate 70% probability, do we win ~70% of the time? | Group predictions into probability bins, compare predicted vs. observed frequencies |
| **Edge capture** | What fraction of identified edge do we actually capture after slippage? | mean(realized_edge) / mean(predicted_edge) |
| **Fill rate** | What % of our orders actually get filled? | filled_orders / total_orders |

### Strategy Comparison

`traderbot compare strategy_a strategy_b` runs both strategies on the same historical data and produces a side-by-side comparison across all metrics.

## Strategy Profiles

`simulation/profiles.py` — predefined strategy profiles for multi-profile backtesting and comparison.

### StrategyProfile Model

Each profile defines how a strategy scales risk limits and weights different signal sources:

```python
class StrategyProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str                          # Human-readable profile name
    risk_multiplier: float             # Scales within HARD_LIMITS, never overrides
    signal_weights: dict[str, float]   # Weights for signal sources (statistical, sentiment, etc.)
    category_focus: list[str]           # Market categories this profile prioritizes
    description: str                   # What this profile is designed for
```

**Critical constraint**: `risk_multiplier` NEVER overrides `HARD_LIMITS`. For ceiling-type limits, the effective limit is `min(risk_multiplier * HARD_LIMITS[key], HARD_LIMITS[key])`. For floor-type limits (min_liquidity, min_edge), the effective limit uses `max()` so the multiplier cannot make the floor less restrictive.

### Preset Profiles

| Profile | `risk_multiplier` | Signal Weights | Category Focus | Purpose |
|---|---|---|---|---|---|
| **Conservative** | 0.5x | statistical: 0.8, sentiment: 0.2 | economics, politics | Capital preservation; minimizes losses |
| **Moderate** | 1.0x | statistical: 0.5, sentiment: 0.5 | economics, politics, science_and_technology | Balanced approach; default profile |
| **Aggressive** | 0.8x | statistical: 0.3, sentiment: 0.7 | economics, politics, science_and_technology, sports, entertainment | Seeks higher returns; tolerates more volatility |

- **Conservative (0.5x)**: Halves all position sizes relative to hard limits. Heavy statistical signal weight. Designed for capital preservation.
- **Moderate (1.0x)**: Operates at full hard limits. Equal signal weighting. The default profile.
- **Aggressive (0.8x)**: Caps at 80% of hard limits (not above — the multiplier reduces, never exceeds). Higher sentiment weight. Designed for higher returns at controlled risk.

### Validation

`StrategyProfile` validates that:
- `risk_multiplier` is in range (0, 1.0] — never exceeds 1.0
- `signal_weights` has at least one non-zero weight
- All weight values are non-negative
- `category_focus` is non-empty

### Multi-Profile Backtesting

`BacktestEngine.run_profiles()` runs the same historical data through multiple profiles simultaneously:

```python
def run_profiles(
    self,
    profiles: list[StrategyProfile],
    start: date,
    end: date,
) -> dict[str, BacktestResult]:
    """Run multiple profiles on same historical period for comparison."""
```

Results are keyed by profile name, enabling side-by-side comparison:
- Win rate by profile
- Sharpe ratio by profile
- Maximum drawdown by profile
- Fill rate by profile

The `traderbot compare` CLI command uses `run_profiles()` to produce comparison output.

## Bootstrap Calibration

`traderbot bootstrap` — calibrates strategy parameters against historical data before live trading.

### Purpose

Before running a strategy with real parameters, bootstrap calibration:
1. Validates that historical data is sufficient for reliable backtesting
2. Fits calibration parameters (e.g., probability thresholds, signal weights) to historical outcomes
3. Produces a calibration report showing fit quality

### Bootstrap Command Spec

```
traderbot bootstrap [--from DATE] [--to DATE] [--profile NAME] [--db-path PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--from` | 30 days ago | Start of calibration window |
| `--to` | today | End of calibration window |
| `--profile` | Moderate | Profile to calibrate |
| `--db-path` | `.traderbot/db.sqlite` | Path to SQLite database |

### Output

- Calibration report with fit quality per parameter
- Recommended parameter values based on historical fit
- Warnings if data is insufficient (< 30 days)
- Warm-up period indicator for indicator stability

### Warm-Up Period Handling

Indicators (SMA, EMA, RSI, Bollinger) require sufficient data points before producing stable values. The bootstrap engine handles this:

- For SMA/EMA: uses `min(period, len(prices))` windows for shorter lookback when data is insufficient
- For RSI: skips the first `period` data points (warm-up)
- Bootstrap logs a WARNING when using partial data (date range < 30 days)
- Bootstrap never crashes on insufficient data — it proceeds with what's available and reports the date range used

### Per-Horizon Calibration

Inspired by production implementations (cf. MarketRegimeNet's temperature scaling):
- Calibration fits are computed per time horizon (daily, weekly, monthly)
- Each horizon gets independent fit parameters (Brier score, calibration slope)
- Calibration parameters are stored in `SESSION-STATE.md` for the heartbeat loop to review

## Backtesting Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| **Survivorship bias** | We only see markets that existed, not ones that were delisted | Include all historical markets, including low-volume ones |
| **Look-ahead bias** | Strategy might implicitly use future information | Strict chronological replay; no peeking at settlement before it happens |
| **Execution assumptions** | Backtest assumes instant fills at trade price | Model slippage: use worst-case fill within spread |
| **Market impact** | Small markets move when large orders enter | Flag markets where our order would exceed 5% of daily volume |
| **News data gaps** | Historical news is harder to reconstruct than trades | Note this limitation; sentiment signals may be less reliable in backtests |