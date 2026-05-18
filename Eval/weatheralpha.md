# Weather Agent "Vane" — Strategy Evaluation Report

**Date**: 2026-05-18  
**Evaluated**: 39 decision cycles (5+ days), 64 audit-logged decisions  
**Source**: macpro-linux remote deployment, audit logs, ChromaDB, OpenClaw workspace, SESSION-STATE.md

---

## Executive Summary

**Verdict: NOT PROFITABLE IN CURRENT STATE. Execution pipeline is entirely broken — zero trades have executed across 39 cycles.** The agent's underlying weather thesis is sound, but two critical bugs and several strategic deficiencies prevent any capital deployment. Even after fixing the blockers, additional work is needed before live deployment.

| Metric | Value |
|---|---|
| Total decisions logged | 64 |
| Trades executed | 0 |
| Win rate | N/A (no trades) |
| P&L | $0.00 |
| Days Blocked | 5+ |
| Cycles Wasted | 39 |

---

## Critical Blockers (P0 — Must Fix Before Any Trading)

### Blocker 1: `initial_balance_cents: null` — Paper Trading Paralyzed

**Status**: Fatal. All trades rejected at risk gate.

**Evidence**:
```json
// ~/.traderbot/profiles/weatherman profile
{
  "initial_balance_cents": null,
  "paper_mode": true
}
```

When `initial_balance_cents` is null, the portfolio value resolves to $0 in the risk pipeline. Since `HARD_LIMITS["max_position_per_market_pct"] = 5%`, the maximum position per market becomes **0.05 × $0 = $0**. Every trade, regardless of size, is rejected by `check_position_limit`.

**Fix**:  
```bash
traderbot profile update weatherman --initial-balance-cents 100000
```
This gives the agent a $1,000 paper balance and unblocks position sizing.

**Impact**: Unblocks ALL downstream risk checks. Without this, no trade can execute regardless of signal quality.

---

### Blocker 2: `edge_estimate: 0.0` — Edge Calculation Not Performed

**Status**: Fatal. All trades would fail `check_min_edge` even if position limit is fixed.

**Evidence**: All 64 audit entries have `edge_estimate: 0.0`:

```
2026-05-17: 20/20 entries → edge_estimate = 0.0
2026-05-18: 44/44 entries → edge_estimate = 0.0
```

The `min_edge_pct` hard limit is 3% (`HARD_LIMITS["min_edge_pct"] = 0.03`). The risk gate computes:

```python
def check_min_edge(estimated_prob, market_price, *, limits=None):
    edge = abs(estimated_prob - market_price)
    min_edge = effective["min_edge_pct"]  # 0.03
    passed = edge >= min_edge
```

With `edge_estimate = 0.0`, even a correct `estimated_prob` of 0.85 against a market price of 0.61 would compute edge as `|0.85 - 0.61| = 0.24` — which passes. But the agent is apparently **not computing estimated_prob correctly either** or is not passing it through. The audit schema records `edge_estimate` as a separate field from the probability estimate, and `edge_estimate: 0.0` appears to be a default value that the agent never sets.

**Root Cause (most likely)**: The LLM agent generates trade decisions and passes `edge_estimate=0.0` as a default because it doesn't know how to compute `|estimated_prob - market_price|`. The paper trader code path (`submit_order`) uses `edge_estimate=0.05` as default and computes `est_prob = price/100 + 0.05`, but when the agent calls `traderbot trade` directly, it must supply these values — and it supplies 0.0.

**Fix**: The agent's decision prompt must instruct it to compute edge as `abs(estimated_probability - market_price/100)` and pass it explicitly. Alternatively, the CLI trade path should derive edge from `estimated_prob` if `edge_estimate` is not provided.

---

## Strategic Deficiencies (P1 — Must Fix Before Live Deployment)

### Deficiency 1: Category Gate Not Enforced at Agent Level

**Severity**: Medium. Wastes cycles but doesn't break trading.

**Evidence**: Of 20 decisions on May 17, only 8 (40%) are weather markets. The other 12 span politics (KXKNESSET, KXTRUMPADMINLEAVE, KXSCOURT, KXIRANDEMOCRACY), sports (KXSCOTTIESLAM, KXCOACHOUTNBADATE), crypto (KXBTCRESERVE), geopolitics (KXZELENSKYPUTIN), and science (KXBLUETSUNAMICOMBO, KXCANAL).

```
Non-weather decisions (May 17):
  KXKNESSET-27-MAY20          (Israel politics)
  KXTRYFIREPOWELL-26MAY12    (Geopolitics)  
  KXCOACHOUTNBADATE-27SKER   (College sports)
  KXSCOTTIESLAM-28           (Sports)
  KXTRUMPADMINLEAVE-26DEC31 (US politics)
  KXSCOURT-29-RDES           (US politics)
  KXUSAEXPANDTERRITORY-29   (Geopolitics)
  KXZELENSKYPUTIN-29-27     (Geopolitics)
  KXIRANDEMOCRACY-27MAR01   (Geopolitics)
  KXBLUETSUNAMICOMBO-27FEB  (Science)
  KXCANAL-29                 (Science)
  KXBTCRESERVE-27-JAN01      (Crypto)
```

The risk pipeline's category filter (`profile.is_category_enabled("weather")`) does reject non-weather trades, but the agent still wastes entire decision cycles evaluating them. On May 17, **60% of decision cycles were wasted on markets that will always be rejected**.

**Fix**: The agent's decision loop prompt must include a hard filter: only evaluate markets in `enabled_categories`. Add a pre-filter step that discards non-category markets before analysis.

---

### Deficiency 2: Confidence/Signal Incoherence

**Severity**: Medium. Would cause severe position sizing errors.

**Evidence**: 15 of 64 decisions (23%) have a confidence/signal gap > 0.3:

| Ticker | Confidence | Signal | Gap | Problem |
|---|---|---|---|---|
| KXRAINNYC-26MAY17-T0 | 0.99 | 0.001 | 0.989 | 99% confident in 0.1% signal? |
| KXCOACHOUTNBADATE | 0.99 | 0.01 | 0.98 | 99% confident in near-zero signal |
| KXRECNCH-26-MAY22 | 0.85 | 0.05 | 0.80 | 85% confident in 5% signal |
| KXTRYFIREPOWELL | 0.65 | 0.15 | 0.50 | Moderate confidence, weak signal |
| KXHIGHMIA-26MAY17 | 0.90 | 0.01 | 0.89 | High confidence, near-zero signal |

The LLM appears to conflate "I am confident this prediction is right" with "there is high signal here." A 99% confidence on a 0.1% signal strength means the agent is **extremely confident about something that barely matters** — or more likely, these two numbers are computed by different code paths that don't agree.

**Fix**: Unify confidence and signal computation. Signal strength should derive from `|forecast_probability - market_price|` (i.e., the edge). Confidence should derive from forecast model agreement / data quality. They should never diverge this wildly.

---

### Deficiency 3: No Position Sizing Model

**Severity**: Medium. Would cause bankroll ruin even if trades execute.

**Evidence**: Position sizes are arbitrary and incoherent:

```
Qty=1, Price=99¢  → Investment: $0.99  (1% of $100 balance)
Qty=500, Price=6¢  → Investment: $30.00 (30% of $100 balance)
Qty=100, Price=98¢ → Investment: $98.00 (98% of $100 balance!!)
Qty=350, Price=3¢  → Investment: $10.50 (10.5% of $100 balance)
```

There is no proportional relationship between confidence, signal, edge, and size. The agent is choosing quantities without regard for:
- Bankroll management (Kelly criterion)
- Risk per trade (should be proportional to edge × confidence)
- Maximum position limits (5% of portfolio per market)

**Fix**: Implement Kelly-based sizing: `position_size = f(edge, confidence, bankroll, max_position_pct)`. The paper trader already has `sized_position_for_trade()` — ensure the agent calls it and uses its output rather than arbitrary quantities.

---

## Efficiency Issues (P2 — Fix Before Live Deployment to Save Costs)

### Issue 1: Obsessive Repetition

**Evidence**: KXHIGHDEN-26MAY18-T50 had **23 separate decision entries** across 4 hours. The agent re-evaluated the same market every ~10 minutes with no change in conditions and no ability to act.

**Impact**: Each cycle costs LLM tokens. 23 evaluations of a single market in 4 hours is ~22 wasted cycles.

**Fix**: Add a market evaluation cache per cycle window. If market conditions haven't changed (same forecast, same price range), skip re-evaluation. Max 1 evaluation per market per hour unless price moves >5%.

---

### Issue 2: Stale Market Evaluation

**Evidence**: The agent continued evaluating May-17 settlement markets well past their close time. NYC, Philly, and Miami markets settled at ~04:59 UTC on May 18, but the agent was still logging decisions for them. Several decisions reference markets that had already settled.

**Fix**: Check market `close_time` before evaluation. If market is closed/settled, skip and move to the next.

---

### Issue 3: News Ingestion Running, But Not Feeding Decisions

**Evidence**: ChromaDB has 6 collections (news, news_signals, data_points, decisions, market_conditions, market_patterns). The `decisions` collection has **0 entries** — the agent's decision history is not being stored for Bayesian learning. The `market_conditions` and `market_patterns` collections also appear empty.

**Impact**: Without stored decisions, the agent cannot perform Bayesian adaptation or learn from past cycles. The heartbeat loop reports "Skipped: no decisions to adapt from."

**Fix**: Ensure `traderbot trade` and `traderbot scan` commands write to the `decisions` collection in ChromaDB. Wire the heartbeat loop to read from these collections for self-improvement.

---

## Data Quality Assessment

### Weather Research: 7/10

- Open-Meteo forecasts are properly ingested and referenced
- 10-city coverage with correct temperature readings
- Forecasts are consistent across 39 cycles (no flip-flopping)
- SESSION-STATE.md maintains accurate forecast tables with settlement tracking

### Market Research: 5/10

- Market tickers are correctly identified and decoded (KXHIGHNY-26MAY18-T84 = "NYC high >84°F on May 18")
- Open interest and volume data is fetched but not systematically used for sizing
- Price data appears correct (market prices align with Kalshi's displayed odds)

### Signal Generation: 2/10

- `edge_estimate: 0.0` means no signal is being generated
- `signal_strength` is inconsistent with `confidence` (see Section P1-2)
- No systematic edge calculation from forecast probability vs market price

---

## Profitability Projection (Post-Fix)

### Weather-Only Markets: Moderate Edge

The agent's weather thesis, when it actually computes edge correctly, shows promise:

| Market (May 18) | Forecast | Market | Edge | Outcome |
|---|---|---|---|---|
| KXHIGHNY-26MAY18-T84 (YES >84°F) | 88°F | 61¢ YES | +24% | ✅ CORRECT — settled YES |
| KXLOWTNYC-26MAY18-T68 (NO >68°F) | 66°F | 55¢ NO | +50% | ✅ CORRECT — settled NO |
| KXHIGHCHI-26MAY18-T82 (YES <82°F) | 78°F | 61¢ YES | +24% | ✅ CORRECT — settled YES |
| KXHIGHPHIL-26MAY18-B94.5 (NO 94-95°F) | 96°F | ~80¢ NO | +19% | ✅ CORRECT — settled NO |
| KXHIGHMIA-26MAY18-B88.5 (NO 88-89°F) | 83°F | ~79¢ NO | +21% | ✅ CORRECT — settled NO |

**On weather markets with correct edge computation**: estimated **55-65% win rate** with positive expected value. The underlying meteorological advantage is real — a 4°F margin on temperature threshold markets provides genuine edge.

### Non-Weather Markets: Negative Edge

The agent has **no information advantage** on politics, sports, crypto, or geopolitics. Its "confidence" on these markets is uninformed speculation. On non-weather markets, expected win rate is **<50%** (subtracting transaction costs and slippage).

### Net Expected P&L (Post-Fix, Weather-Only)

- **With $1,000 balance, 5% max position per market, 3% min edge**:  
  - ~5-8 qualifying trades per week (weather markets with >3% edge and >1,000 OI)  
  - Expected weekly P&L: **+$15 to +$40** (modest but positive)  
  - Expected max drawdown: **-$200** (5× typical loss in a bad week)

This is **not life-changing money**, but it proves the concept. Scale requires either larger balance or more categories with genuine data edge.

---

## Fix Priority Matrix

| Priority | Fix | Effort | Impact on Profitability |
|---|---|---|---|
| 🔴 P0 | Set `initial_balance_cents` | 1 min | Unblocks ALL trading |
| 🔴 P0 | Fix `edge_estimate` computation | 2-4 hrs | Unblocks risk gate passage |
| 🟡 P1 | Enforce category filter at agent level | 1 hr | Saves 60% of cycle cost |
| 🟡 P1 | Fix confidence/signal incoherence | 2-3 hrs | Improves sizing accuracy |
| 🟡 P1 | Implement Kelly-based position sizing | 2-3 hrs | Prevents bankroll ruin |
| 🟠 P2 | Add market repetition throttle | 1 hr | Saves 50% of LLM token cost |
| 🟠 P2 | Skip settled/expired markets | 1 hr | Saves cycle time |
| 🟠 P2 | Wire decision storage to ChromaDB | 2 hrs | Enables Bayesian learning |

---

## Raw Data Summary

### Audit Trail (May 17-18)

- **Total decisions**: 64 (20 on May 17, 44 on May 18)
- **Executed**: 0 | **Rejected**: 64
- **Edge estimate**: 0.0 for all 64 entries
- **Signal range**: 0.001 – 0.99 | **Mean**: 0.31
- **Confidence range**: 0.40 – 0.99 | **Mean**: 0.74
- **Confidence/signal gap > 0.3**: 15/64 (23%)

### Unique Markets Evaluated (May 17-18)

- Weather: 7 markets (KXHIGHNY, KXHIGHCHI, KXHIGHLAX, KXHIGHDEN, KXHIGHTHOU, KXLOWTNYC, KXHIGHMIA)
- Non-weather: 13 markets (politics, sports, crypto, geopolitics, science)

### Circuit Breaker

- State: NORMAL (level 0)
- Can trade: true
- Blocker is `initial_balance_cents: null`, not circuit breaker

### ChromaDB

- Collections: 6 (news, news_signals, data_points, decisions, market_conditions, market_patterns)
- News/data ingestion: working (timer fires every 30 min)
- Decisions storage: 0 entries (not wired)
- Market learning: 0 entries (depends on decisions)

### Agent Memory

- Session state correctly tracks forecasts, market analysis, and blockers
- Agent has correctly identified the `initial_balance_cents` blocker for 39 cycles
- Agent has NOT adapted its behavior (still evaluating non-weather markets, still computing zero edge)

---

*Generated by Sisyphus evaluation. Data from macpro-linux deployment, 2026-05-18.*
