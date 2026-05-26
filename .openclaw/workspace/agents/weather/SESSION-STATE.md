# Session State - Vane

## Active Positions

| Ticker | Side | Quantity | Avg Price | Current Price | P&L | Conviction | Settlement |
|---|---|---|---|---|---|---|---|
| _(none)_ | — | — | — | — | — | — | — |

**Conviction values:** HIGH (model convergence < 0.5 SD), MODERATE (0.5-1.5 SD), LOW (1.5+ SD)

## Tracked Markets

| Ticker | Subcategory | Horizon | Status | Last Analysis | Edge | Decision |
|---|---|---|---|---|---|---|
| _(none)_ | — | — | — | — | — | — |

**Subcategory values:** TEMPERATURE, PRECIPITATION, HURRICANE, INDEX, OTHER
**Horizon values:** 0-3D, 4-7D, 8-14D, 14D+
**Status values:** SCAN, ANALYZED, SIGNAL_CHECKED, TRADED, SETTLED, SKIPPED
**Decision values:** TRADED, SKIPPED (reason), HELD (existing), EXITED

## Pending Actions

- (no pending actions)

## Completed Actions

_First boot. No activity yet._

## Model Consensus History

| Timestamp | GFS Mean | ECMWF Mean | CMC Mean | Spread | Assessment |
|---|---|---|---|---|---|
| _(none)_ | — | — | — | — | — |

**Assessment values:** CONVERGED (< 0.5 SD), NEUTRAL (0.5-1.5 SD), DIVERGED (> 1.5 SD)

Record model consensus every decision cycle. If divergence persists > 6h, surface to sysadmin.

## Weather Event Status

- Active high-impact events: none
- NHC advisories: none
- NWS warnings: none
- Emergency declarations: none
- Event cadence: STANDARD (5 min)

**Cadence values:** STANDARD (5 min), HIGH_IMPACT (1 min)

## Data Source Health

| Source | Status | Last Good | Failures |
|---|---|---|---|
| GFS ensemble | — | — | 0 |
| ECMWF ensemble | — | — | 0 |
| CMC ensemble | — | — | 0 |
| CPC outlook | — | — | 0 |
| NHC advisories | — | — | 0 |
| NWS warnings | — | — | 0 |

**Status values:** OK, DEGRADED, FAILED

## Learnings Log

_No learnings logged yet._

## Errors Log

_No errors logged yet._

## Data Sources Used

- `traderbot scan --category weather --json` — market discovery
- `traderbot analyze TICKER --json` — orderbook + implied probability
- `traderbot data-points weather --json` — GFS/ECMWF/CMC ensemble, CPC, NHC, NWS
- `traderbot news-context weather --json` — pre-trade context
- `traderbot signals --category weather --json` — blended signals
- `traderbot sentiment TICKER --json` — supplementary sentiment
