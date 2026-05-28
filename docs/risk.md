# Risk Management

The risk module is the **immutable guardrail layer**. It enforces hard limits that the agent cannot override. Even if the LLM "decides" to break a rule, the execution layer will reject the order.

## Design Principle: Code Over Configuration

Risk limits are **compiled into the module**, not read from a config file the agent can modify. Changing any hard limit requires human approval and a code change — not an API call or a clever prompt.

This solves the emotional bias problem: the agent can feel "really confident" about a trade, but the risk module doesn't care about confidence. It cares about position size, exposure, and losses.

## Hard Limits

```python
# risk/limits.py — IMMUTABLE without explicit human approval
# Wrapped in MappingProxyType to prevent runtime modification
HARD_LIMITS = {
    "max_position_per_market_pct": 0.05,    # Never >5% of portfolio in one market
    "max_daily_loss_pct": 0.02,              # Stop trading if down 2% today
    "max_drawdown_pct": 0.10,                # Halt ALL trading if down 10% from peak
    "min_liquidity_threshold": 500,           # Don't trade if open_interest < 500
    "max_open_positions": 20,                # Concentration limit
    "min_edge_pct": 0.03,                     # Must have 3%+ edge to trade
}
```

### Per-Market Position Limit

No single market can consume more than 5% of total portfolio value. This prevents concentration risk — even if the agent identifies a "certain thing," it cannot over-commit.

**Check**: `current_position_value(ticker) + order_value <= portfolio_value * 0.05`

### Daily Loss Circuit Breaker

If the portfolio loses more than 2% in a single day, trading halts. This prevents tilt — the tendency to chase losses with increasingly risky bets. Trading resumes automatically when the daily loss drops below the threshold on the next `check()` call.

**Check**: `today_realized_loss + today_unrealized_loss <= portfolio_value * 0.02`

### Maximum Drawdown (Nuclear Option)

If the portfolio drops 10% from its historical high, ALL trading stops. The agent cannot resume without explicit human intervention. This is the last line of defense against catastrophic loss.

**Check**: `(peak_value - current_value) / peak_value <= 0.10`

**Action on trigger**: Write to `SESSION-STATE.md` that trading is halted. The Heartbeat Loop will not restart trading. Only a human can clear this flag.

### Minimum Liquidity Threshold

Markets with open interest below 500 contracts are excluded. Illiquid markets have wider spreads, worse fills, and are harder to exit in a downturn.

**Check**: `market.open_interest >= 500`

### Minimum Edge

The agent must identify at least 3% edge (difference between estimated probability and market price) before entering a trade. This filters out marginal opportunities where transaction costs and slippage eat the edge.

**Check**: `abs(estimated_prob - market_price) >= 0.03`

## The evaluate_trade() Pipeline

The central risk gate is `evaluate_trade()` in `risk/__init__.py`. It orchestrates the full check sequence and returns either a sized position or a `RiskCheckError`. The companion `evaluate_trade_full()` returns a `TradeResult` preserving both the sized position and the trade direction.

### Pipeline Flow

```
evaluate_trade(trade_request, portfolio, breaker, profile=None)
│
├── 1. Category filter (profile-aware only)
│   └── If profile.is_category_enabled(market_category) is False → return 0
│
├── 2. Circuit breaker state check
│   ├── Compute daily_loss_pct and drawdown_pct from portfolio
│   ├── breaker.check(daily_loss_pct, drawdown_pct)
│   └── If breaker.can_trade is False → return 0
│
├── 3. Compute effective limits
│   ├── With profile: AgentRiskLimits(profile) — min(profile, HARD_LIMITS) for max thresholds
│   │                   max(profile, HARD_LIMITS) for min thresholds
│   └── Without profile: dict(HARD_LIMITS) directly
│
├── 4. Run all limit checks (run_all_checks)
│   ├── check_position_limit
│   ├── check_daily_loss
│   ├── check_drawdown
│   ├── check_liquidity
│   ├── check_max_open_positions
│   └── If any fail → raise RiskCheckError with details
│
├── 5. Kelly sizing (sized_position_for_trade)
│   ├── Compute odds from price
│   ├── fractional_kelly(prob, odds, 0.5)
│   ├── confidence_scaled_size(kelly_fraction, confidence, bankroll)
│   └── min(sized, max_position_cents)
│
└── 6. Apply multipliers
    ├── × breaker.get_state().position_size_multiplier
    ├── × profile.risk_multiplier (or 1.0 if no profile)
    └── Return sized position in cents
```

### Return Values

| Function | Return Type | Notes |
|---|---|---|
| `evaluate_trade()` | `int` | Sized position in cents (0 = rejected) |
| `evaluate_trade_full()` | `TradeResult` | `sized_position_cents: int` + `direction: "yes"\|"no"` |

On limit check failure, `evaluate_trade_full()` raises `RiskCheckError(ticker, failures)` with details about which check(s) failed and why.

## Position Sizing

### Fractional Kelly Criterion

Position sizing uses half-Kelly (0.5 × f*) to balance growth against variance:

```python
# risk/sizing.py

def kelly_criterion(prob: float, odds: float) -> float:
    """f* = (b*p - q) / b where q = 1-p"""
    q = 1 - prob
    f = (odds * prob - q) / odds
    return max(0.0, f)

def fractional_kelly(prob, odds, fraction=0.5) -> float:
    return max(0.0, kelly_criterion(prob, odds)) * fraction

def confidence_scaled_size(kelly_fraction, confidence, bankroll_cents) -> int:
    return int(kelly_fraction * max(0.0, min(1.0, confidence)) * bankroll_cents)

def sized_position_for_trade(prob, odds, confidence, bankroll_cents, max_position_cents) -> int:
    sized = confidence_scaled_size(fractional_kelly(prob, odds, 0.5), confidence, bankroll_cents)
    return min(sized, max_position_cents)
```

The sized position is then scaled by the circuit breaker's `position_size_multiplier` and the profile's `risk_multiplier` in `evaluate_trade_full()`.

## Circuit Breaker Implementation

Three-tier system with increasing severity:

| Level | Value | Trigger | Effect | Recovery |
|---|---|---|---|---|
| **NORMAL** | 0 | Daily loss ≤ 1% | Full position sizing | Default state |
| **SLOW** | 1 | Daily loss > 1% | `position_size_multiplier = 0.5` | Automatic on next `check()` when loss drops below threshold |
| **HALT** | 2 | Daily loss > 2% | `can_trade = False`, no new trades | Automatic on next `check()` when loss drops below threshold |
| **FULL_STOP** | 3 | Drawdown > 10% | `position_size_multiplier = 0.0`, `can_trade = False` | **Manual only** — requires `traderbot resume` or manual flag clear |

The circuit breaker state persists in `circuit_breaker_state.json` under the data directory (`~/.traderbot/`). The state file is protected with an HMAC-SHA256 signature to prevent tampering. Any modification to the state file (e.g., resetting FULL_STOP to NORMAL) will fail verification and raise a `SecurityError`. On restart, the agent verifies the HMAC signature before reading the persisted state.

### Circuit Breaker State Model

```python
class CircuitBreakerState(BaseModel):
    level: BreakerLevel = BreakerLevel.NORMAL
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    position_size_multiplier: float = 1.0
    can_trade: bool = True
    reason: str = ""
```

## AgentRiskLimits

Per-agent risk limits wrap a `TradingProfile` and enforce `HARD_LIMITS` as an absolute ceiling. For maximum thresholds (position size, daily loss, drawdown, open positions), the effective limit is `min(profile_param, HARD_LIMITS[key])`. For minimum thresholds (liquidity, edge), the effective limit is `max(profile_param, HARD_LIMITS[key])`. The more restrictive value always wins.

```python
class AgentRiskLimits:
    def __init__(self, profile: TradingProfile) -> None:
        self._profile = profile

    @property
    def max_position_per_market_pct(self) -> float:  # min(profile, HARD_LIMITS)
    @property
    def max_daily_loss_pct(self) -> float:            # min(profile, HARD_LIMITS)
    @property
    def max_drawdown_pct(self) -> float:              # min(profile, HARD_LIMITS)
    @property
    def max_open_positions(self) -> int:                # min(profile, HARD_LIMITS)
    @property
    def min_liquidity_threshold(self) -> int:          # max(profile, HARD_LIMITS)
    @property
    def min_edge_pct(self) -> float:                   # max(profile, HARD_LIMITS)
```

The ceiling enforcement is the core security guarantee: an agent cannot exceed `HARD_LIMITS` by setting aggressive profile parameters.

## WAL Protocol (Write-Ahead Log)

The `wal.py` module implements a crash-safe write-ahead log for trade execution. Every trade intent is written to `SESSION-STATE.md` **before** execution, so the system can recover from crashes.

### WalStatus Enum

```python
class WalStatus(StrEnum):
    PENDING = "PENDING"       # Intent written, awaiting execution
    COMPLETED = "COMPLETED"   # Position confirmed on exchange
    REJECTED = "REJECTED"     # Risk check or exchange rejected
    EXECUTED = "EXECUTED"      # Order placed on exchange (awaiting fill)
    CANCELLED = "CANCELLED"    # Intent cancelled before execution
    EXPIRED = "EXPIRED"        # Intent timed out before execution
```

### WalAction Enum

```python
class WalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
```

### WalEntry Model

```python
class WalEntry(BaseModel):
    intent_id: str                          # WAL-XXXXXXXX format
    timestamp: datetime                     # UTC ISO format
    action: WalAction                       # BUY or SELL
    ticker: str                             # Market ticker
    direction: Literal["yes", "no"]         # Contract direction
    quantity: int (>= 1)                    # Number of contracts
    price_cents: int (>= 1)                # Price in cents
    reason: str                             # Trade rationale
    signal: str = ""                         # Signal source
    risk_checks: str = ""                    # Risk check summary
    confidence: float (0.0-1.0) = 0.5      # Confidence score
    status: WalStatus = WalStatus.PENDING   # Current status
```

### Core Operations

| Operation | Function | Description |
|---|---|---|
| Write intent | `write_intent()` | Creates a PENDING entry in SESSION-STATE.md with exclusive file lock |
| Update status | `update_status()` | Transitions entry status (PENDING → EXECUTED/REJECTED/CANCELLED) |
| Scan pending | `scan_pending()` | Recovery: finds all PENDING entries after a crash |
| Reconcile | `reconcile()` | Matches PENDING intents against actual positions → COMPLETED or CANCELLED |

The WAL uses `portalocker` for exclusive/shared file locking to prevent concurrent write conflicts. If another writer holds the lock, `ConcurrentWriteError` is raised.

### Crash Recovery Flow

1. On startup, call `scan_pending(SESSION-STATE.md)` to find all PENDING entries
2. For each pending entry, check if the corresponding position exists on the exchange
3. If position matches intent → `update_status(COMPLETED)`
4. If position doesn't match → `update_status(CANCELLED)`
5. Resume normal operations

## Reconciliation Module

The `db/reconciliation.py` module syncs local position data with the Kalshi API:

### `reconcile_positions(db_path, kalshi_client)`

Syncs open positions between local DB and Kalshi:
- **Position not on Kalshi** → mark as closed (delete from local DB)
- **Different fill data** → update quantity and avg_price
- **New position on Kalshi** → insert into local DB
- **Fill data** → update avg_price with weighted fill prices

Returns: `{"updated": int, "closed": int, "added": int}`

### `reconcile_settlements(db_path, kalshi_client)`

Syncs settlement data from Kalshi:
- For each settlement, update local position's `settlement_result` and `pnl_cents`
- Skips tickers not in local DB

Returns: `{"settled": int, "skipped": int}`

### `reconcile_all(db_path, kalshi_client)`

Runs both position and settlement reconciliation:

Returns: `{"positions": {...}, "settlements": {...}}`

## Audit Trail

Every trade decision — whether executed or rejected — is logged to `db/decisions` as append-only JSONL:

```python
class Decision(BaseModel):
    timestamp: datetime
    ticker: str
    direction: Literal["yes", "no", "neutral"]
    quantity: int
    price: int                          # Price in cents (int, not float)
    signal_strength: float             # 0-1
    confidence: float                  # 0-1
    edge_estimate: float               # estimated edge as probability difference
    risk_checks: dict[str, bool]       # each limit check and its result
    outcome: Literal["executed", "rejected", "held"]
    rejection_reason: str | None       # if rejected, which limit failed
    actual_result: bool | None         # true/false for binary market settlement
```

The `AuditLogger` writes one JSONL file per day (`YYYY-MM-DD.jsonl`) and supports filtering by ticker, date range, and outcome.

## Anti-Bias Design Decisions

| Bias | How TraderBot Prevents It |
|---|---|
| **Overconfidence** | Hard position limits regardless of confidence score |
| **Loss chasing** | Daily loss circuit breaker halts trading after 2% loss |
| **Recency bias** | Heartbeat reviews full history, not just recent wins |
| **Confirmation bias** | Signals combine statistical + sentiment with independent scoring |
| **Gambler's fallacy** | Each market evaluated independently; no "due for a win" logic |
| **Survivorship bias** | Audit trail includes rejected trades, not just executed ones |
| **Anchoring** | Odds model computes fresh probability each cycle; doesn't anchor to prior estimate |

## Human Override

The human can:
- **Halt trading** at any time via `traderbot halt` — sets the Level 3 breaker
- **Adjust risk appetite** via `USER.md` — changes what the agent considers, not hard limits
- **Approve specific trades** above a threshold — agent can be configured to ask for human approval on positions above a certain size
- **Clear the full-stop breaker** — the only way to resume trading after 10% drawdown

The human **cannot**:
- Disable risk limits via agent conversation
- Modify `HARD_LIMITS` without a code change
- Skip the audit trail