# Risk Management

The risk module is the **immutable guardrail layer**. It enforces hard limits that the agent cannot override. Even if the LLM "decides" to break a rule, the execution layer will reject the order.

## Design Principle: Code Over Configuration

Risk limits are **compiled into the module**, not read from a config file the agent can modify. Changing any hard limit requires human approval and a code change — not an API call or a clever prompt.

This solves the emotional bias problem: the agent can feel "really confident" about a trade, but the risk module doesn't care about confidence. It cares about position size, exposure, and losses.

## Hard Limits

```python
# risk/limits.py — IMMUTABLE without explicit human approval
HARD_LIMITS = {
    "max_position_per_market_pct": 0.05,    # Never >5% of portfolio in one market
    "max_daily_loss_pct": 0.02,              # Stop trading if down 2% today
    "max_drawdown_pct": 0.10,                # Halt ALL trading if down 10% from peak
    "min_liquidity_threshold": 1000,          # Don't trade if open_interest < 1000
    "max_open_positions": 20,                # Concentration limit
    "min_edge_pct": 0.03,                     # Must have 3%+ edge to trade
}
```

### Per-Market Position Limit

No single market can consume more than 5% of total portfolio value. This prevents concentration risk — even if the agent identifies a "certain thing," it cannot over-commit.

**Check**: `current_position_value(ticker) + order_value <= portfolio_value * 0.05`

### Daily Loss Circuit Breaker

If the portfolio loses more than 2% in a single day, trading halts until the next market open. This prevents tilt — the tendency to chase losses with increasingly risky bets.

**Check**: `today_realized_loss + today_unrealized_loss <= portfolio_value * 0.02`

### Maximum Drawdown (Nuclear Option)

If the portfolio drops 10% from its historical high, ALL trading stops. The agent cannot resume without explicit human intervention. This is the last line of defense against catastrophic loss.

**Check**: `(peak_value - current_value) / peak_value <= 0.10`

**Action on trigger**: Write to `SESSION-STATE.md` that trading is halted. The Heartbeat Loop will not restart trading. Only a human can clear this flag.

### Minimum Liquidity Threshold

Markets with open interest below 1,000 contracts are excluded. Illiquid markets have wider spreads, worse fills, and are harder to exit in a downturn.

**Check**: `market.open_interest >= 1000`

### Minimum Edge

The agent must identify at least 3% edge (difference between estimated probability and market price) before entering a trade. This filters out marginal opportunities where transaction costs and slippage eat the edge.

**Check**: `abs(estimated_prob - market_price) >= 0.03`

## Position Sizing

The toolkit provides sizing models, but the **agent chooses** which model and parameters to use (within guard rails).

### Full Kelly Criterion

```
f* = (bp - q) / b

where:
  f* = fraction of bankroll to risk
  b = odds received (net fractional odds)
  p = probability of winning
  q = 1 - p
```

Full Kelly is mathematically optimal for long-run growth but extremely volatile. **Never used directly** — always fractional.

### Fractional Kelly

Default: half-Kelly (0.5 × f*). Reduces variance at the cost of slightly slower growth.

The agent can adjust the Kelly fraction, but the toolkit enforces:
- Kelly fraction range: [0.1, 0.5] — never below 10% (too timid), never above 50% (too aggressive)
- Resulting position must still pass per-market limit check

### Confidence Scaling

The agent provides a confidence score (0-1) for each trade signal. This scales the Kelly output:

```
sized_position = kelly_fraction * confidence * bankroll
```

The toolkit caps confidence-scaled positions at the per-market limit regardless of how confident the agent claims to be.

## Circuit Breaker Implementation

Three-tier system with increasing severity:

| Level | Trigger | Action | Recovery |
|---|---|---|---|
| **Level 1: Slow** | Daily loss > 1% | Reduce position sizes by 50% | Automatic at next market open |
| **Level 2: Halt** | Daily loss > 2% | No new trades; existing positions held | Automatic at next market open |
| **Level 3: Full Stop** | Drawdown > 10% | All trading halted; notify human | **Manual only** — human must clear flag |

The circuit breaker state persists in `SESSION-STATE.md`. On restart, the agent reads the state and respects any active breaker.

## Audit Trail

Every trade decision — whether executed or rejected — is logged to `db/decisions`:

```python
class Decision(BaseModel):
    timestamp: datetime
    ticker: str
    direction: Literal["yes", "no", "hold"]
    quantity: int
    price: float
    signal_strength: float          # 0-1
    confidence: float               # 0-1
    edge_estimate: float            # estimated edge in cents
    risk_checks: dict[str, bool]    # each limit check and its result
    outcome: Literal["executed", "rejected", "held"]
    rejection_reason: str | None    # if rejected, which limit failed
    actual_result: float | None     # filled after market settles
```

This enables the Heartbeat Loop to compare predicted edge vs. actual outcomes, driving the self-learning mechanism.

## Anti-Bias Design Decisions

| Bias | How BetBot Prevents It |
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
- **Halt trading** at any time via `betbot halt` — sets the Level 3 breaker
- **Adjust risk appetite** via `USER.md` — changes what the agent considers, not hard limits
- **Approve specific trades** above a threshold — agent can be configured to ask for human approval on positions above a certain size
- **Clear the full-stop breaker** — the only way to resume trading after 10% drawdown

The human **cannot**:
- Disable risk limits via agent conversation
- Modify `HARD_LIMITS` without a code change
- Skip the audit trail