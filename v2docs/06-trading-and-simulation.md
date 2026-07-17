# TraderBot v2 — Trading and Simulation

> This document covers the three-mode trading architecture, paper trading simulation, backtesting, profile-aware MCP routing, and how they interact. Grounded in DD-013, DD-019, DD-021, DD-031, DD-035.

---

## Three-Mode Trading Architecture

Every category agent operates in one of three modes at any given time. The mode is stored in the agent's `TradingProfile` and determines how the MCP server routes tool calls (DD-013, DD-021).

```
Agent calls traderbot__trade(token, ticker, direction, quantity, price)
         │
         ▼
   MCP Server receives tool call
         │
         ▼
   Resolve token → profile → mode
         │
    ┌────┼────────────┐
    │    │             │
 BACKTEST   PAPER      LIVE
    │    │             │
    ▼    ▼             ▼
 SimulationClock   PaperTrader   Kalshi API
 returns historical  simulates     submits order
 fill at sim-time    fill with     to exchange
 price               slippage
    │    │             │
    ▼    ▼             ▼
 backtest DB      paper DB      live DB
 (read-only from  (read-only     (read-write
  paper & live     from live)    + Kalshi sync)
  for reference)
```

**Critical design principle**: The agent uses the same commands and tools regardless of mode. It never needs to track its mode or use different commands. The MCP server is responsible for routing based on the profile's mode setting (DD-021).

---

## Mode-Aware MCP Tool Behavior

| Tool | Backtest | Paper | Live |
|---|---|---|---|
| `traderbot__scan` | Markets open at sim-time | Current markets | Current markets |
| `traderbot__analyze` | Analysis at sim-time | Current analysis | Current analysis |
| `traderbot__*_forecast_prob` | Forecast at sim-time | Current forecast | Current forecast |
| `traderbot__*_accuracy` | Historical accuracy (may be limited for sim-time) | Current accuracy | Current accuracy |
| `traderbot__trade` | Record in backtest DB, return simulated fill at sim-time price | Record in paper DB, return simulated fill with slippage | Submit to Kalshi, record in live DB |
| `traderbot__positions` | Backtest positions | Paper positions | Live positions |
| `traderbot__heartbeat` | Sim-time heartbeat data | Current heartbeat data | Current heartbeat data |
| `traderbot__market_edge` | Market edge at sim-time | Current market edge | Current market edge |
| `traderbot__news_context` | News published before sim-time | Recent news | Recent news |

The `mode` field in the MCP response is informational only — the agent doesn't change its behavior based on it.

---

## Backtesting (DD-019)

Backtesting is **time-lapse behavioral simulation**, not just statistical replay. The goal is to validate the model and allow rapid improvement before risking real or even paper money.

### Key Properties

1. **Time-lapse simulation**: The agent speed-runs the cycles that would have taken place during a 6-month period on a sped-up timeline. This is not just running statistics on historical data — it's simulating the agent's actual decision-making process.

2. **Real market conditions**: The simulation must reflect real market conditions as closely as possible. This means using real market data at each point in time — not just the settlement point. Kalshi market prices fluctuate over time, and WHEN the agent places its trade can dictate its performance metrics.

3. **Data quality matters**: Using same-day forecasts (Tier 1 data) inflates certainty relative to live conditions. The `SimulationClock` must track lead time and adjust data quality metadata accordingly. Day-0-only backtesting is acceptable for initial cycles but must be documented as an approximation.

4. **Same interface, same commands**: The agent uses the same MCP tools and receives the same response format as in paper and live mode. The MCP tool is profile-aware and returns mode-appropriate data.

5. **No cron during backtesting**: The backtesting engine drives the simulation, not the agent's decision loop. The agent participates via `sessions_send` prompts from SysAdmin or the test harness.

### SimulationClock

The `SimulationClock` is the core of time-lapse simulation. It provides:
- `sim_time`: The current simulated timestamp (advances faster than real time)
- `sim_date()`: The current simulated date
- Market state at `sim_time`: Prices, orderbooks, available markets as they were at that point in history
- Data availability: Only data that was actually available at `sim_time` (no look-ahead)

### Historical Data Requirements

| Data | Tier 1 (available now) | Tier 2 (GRIB2 pipeline) |
|---|---|---|
| Weather forecasts | Day-0 only (Open-Meteo, NWS) | Multi-day lead time (GFS, ECMWF) |
| Kalshi market data | Full history via API | Same |
| News with timestamps | Available | Same |
| Bias data | Available | Available |

---

## Paper Trading (DD-021)

Paper trading simulates fills locally. The agent receives real market data (current markets, current forecasts, current news) but orders are not submitted to Kalshi.

### PaperSlippageModel

When an agent places a paper trade:
1. The MCP server receives the trade request
2. Runs risk evaluation against the paper balance
3. Simulates a fill using `PaperSlippageModel` (walks the live orderbook to compute realistic fill price)
4. Records the position in the paper database with simulated fill price and slippage
5. Returns the fill confirmation

### Paper Balance Computation

Single source of truth:
```
remaining = initial_balance - cost(at open) + settlement_payouts
```

- YES won → +100¢ per contract
- NO won → +100¢ per contract
- Lost → 0¢

### Settlement

| Mode | Settlement Source | Method |
|---|---|---|
| Backtest | Historical data | MCP server checks historical market data at sim-time |
| Paper | Kalshi API + Open-Meteo | `SettlementVerifier` checks settled markets, auto-settles weather bets |
| Live | Kalshi API | `reconcile_settlements` syncs with Kalshi |

---

## Live Trading

Live trading submits orders to the Kalshi exchange via the REST API. The WebSocket provides real-time updates on order status, fills, and position changes.

### Risk Enforcement

All risk limits are **immutable hard limits** enforced by TraderBot's risk module (not configurable by agents):
- `max_position_per_market_pct`: Maximum position size as percentage of portfolio
- `max_daily_loss_pct`: Maximum daily loss as percentage of portfolio
- `max_drawdown_pct`: Maximum drawdown as percentage of portfolio
- `max_open_positions`: Maximum number of concurrent open positions
- `min_liquidity_threshold`: Minimum orderbook liquidity required
- `min_edge_pct`: Minimum estimated edge required to enter a trade

Circuit breaker states:
- **GREEN**: Normal trading
- **YELLOW**: Reduced position sizing
- **RED**: No new positions, close existing at next opportunity
- **FULL_STOP**: All trading suspended

SysAdmin monitors circuit breakers via `traderbot halt --json` every 30 minutes during live trading.

---

## MCP Response Format

All trade responses use the same format regardless of mode:

```json
{
  "status": "filled",
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "direction": "yes",
  "quantity": 5,
  "fill_price_cents": 34,
  "slippage_cents": 1,
  "estimated_prob": 0.38,
  "confidence": 0.72,
  "remaining_balance_cents": 9830,
  "mode": "paper"
}
```

The `mode` field is informational only. The agent doesn't need to change its behavior based on it.

---

## TradingProfile Model

```python
class TradingProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    mode: Literal["backtest", "paper", "live"]  # Added "backtest"
    description: str
    enabled_categories: list[MarketCategory] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=lambda: [
        "scan", "analyze", "trade", "data-points", "news-context",
        "heartbeat", "performance", "audit", "learnings",
    ])
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0)]
    max_position_per_market_pct: Annotated[float, Field(gt=0)]
    max_daily_loss_pct: Annotated[float, Field(gt=0)]
    max_drawdown_pct: Annotated[float, Field(gt=0)]
    max_open_positions: Annotated[int, Field(gt=0)]
    min_liquidity_threshold: Annotated[int, Field(gt=0)]
    min_edge_pct: Annotated[float, Field(gt=0)]
    initial_balance_cents: int | None = 10_000
```

- `mode`: Determines MCP routing behavior (backtest/paper/live)
- `enabled_categories`: Enforced by MCP server — empty list means "all categories permitted" (SysAdmin)
- `permissions`: Fine-grained tool access control (SysAdmin gets management tools, no trading tools)

---

## Module Changes

### What Moves to `trading.py`

| Current | v2 Location |
|---|---|
| `paper.py` → `compute_paper_balance`, `position_value_for_ticker`, `remaining_balance` | `traderbot/trading.py` |
| `simulation/paper_trader.py` → `PaperTrader`, `PaperSlippageModel`, `PaperFill`, `PaperPosition`, `PaperPortfolio` | `traderbot/trading.py` |
| `simulation/settlement.py` → `SettlementVerifier`, `auto_settle_paper_positions`, `_settle_weather_bets` | `traderbot/trading.py` + `traderbot/kalshi/settlement.py` |
| `simulation/settlement.py` → `_parse_kalshi_ticker` | `traderbot/kalshi/models.py` |
| `simulation/performance.py` → metrics | `traderbot/analysis/portfolio.py` |
| `simulation/adaptation.py` → `BayesianAdapter` | `traderbot/analysis/adaptation.py` |
| `cli/trade.py` → trade evaluation, risk checks | `traderbot/trading.py` (service) + `cli/trade.py` (thin handler) |

### What Gets Retired

| Module | Reason |
|---|---|
| `paper.py` | Thin wrapper around DB queries; balance computation moves to `trading.py`, MCP provides endpoint |
| `simulation/profiles.py` | Preset strategy system; v2 uses per-category agent profiles |
| `simulation/settlement.py` | Split between `trading.py` and `kalshi/settlement.py` |
| `analysis/signals.py` (GenericAnalyzer) | Replaced by category-specific toolkits |
| `data/weather/signals.py` (WeatherSignalEngine) | Replaced by weather toolkit tools |
