# TraderBot Roadmap Progress

**Last updated**: v0.00.08 (2026-04-21)
**Current focus**: Phase 3 — CLI & OpenClaw Skill

---

## Phase 1: Kalshi Data Foundation — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Pydantic models | `kalshi/models.py` | ✅ Done | 14 models, strict=True, extra=forbid |
| SDK wrapper | `kalshi/client.py` | ✅ Done | JWT auth via cryptography+PyJWT, httpx async, retry+backoff, rate limiting |
| Market data | `kalshi/markets.py` | ✅ Done | list_markets, get_market, get_orderbook, get_recent_trades |
| Historical data | `kalshi/history.py` | ✅ Done | get_cutoffs, get_historical_trades, get_settled_markets |
| WebSocket | `kalshi/websocket.py` | ✅ Done | auth, subscribe/unsubscribe, auto-reconnect with exponential backoff |
| Demo adapter | `kalshi/demo.py` | ✅ Done | DemoAdapterFactory for demo API |
| Shared helpers | `kalshi/_normalize.py` | ✅ Done | Extracted from markets.py/history.py (DRY) |

**Tests**: 270 passing, 97% coverage

**Success criteria met**:
- [x] All API responses parsed into validated Pydantic models
- [x] Demo mode works against demo-api.kalshi.co
- [ ] `traderbot scan` returns open markets (CLI not wired yet)
- [ ] `traderbot analyze <ticker>` returns details + orderbook (CLI not wired yet)
- [ ] WebSocket maintains persistent connection (tested with mocks only)

---

## Phase 2: Risk Module — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Hard limits | `risk/limits.py` | ✅ Done | 6 checks, HARD_LIMITS immutable via MappingProxyType |
| Position sizing | `risk/sizing.py` | ✅ Done | Kelly criterion, fractional Kelly [0.1, 0.5], confidence scaling |
| Circuit breaker | `risk/circuit_breaker.py` | ✅ Done | 3-tier SLOW/HALT/FULL_STOP, JSON persistence, position_size_multiplier |
| Audit trail | `risk/audit.py` | ✅ Done | JSONL append-only, filtering by date/ticker/outcome |
| Risk gate | `risk/__init__.py` | ✅ Done | evaluate_trade(): breaker → limits → sizing pipeline |

**Tests**: 270 passing, 100% coverage on risk modules

**Success criteria met**:
- [x] Risk module rejects trades that violate any hard limit
- [x] Circuit breaker activates at correct thresholds (1%/2%/10%)
- [x] Kelly sizing produces mathematically correct results
- [x] Every decision logged with full context (audit.py)
- [x] Risk module cannot be bypassed (HARD_LIMITS frozen, no config reading)

---

## Phase 3: CLI & OpenClaw Skill — 🔲 NOT STARTED

| Component | File | Status | Notes |
|---|---|---|---|
| CLI entry point | `cli.py` | 🔲 Pending | argparse/typer CLI for all commands |
| Skill definition | `skills/traderbot/SKILL.md` | 🔲 Pending | OpenClaw skill with commands, triggers, env |
| Workspace setup | `.openclaw/workspace/` | 🔲 Pending | AGENTS.md, SESSION-STATE.md, HEARTBEAT.md templates |
| DB positions | `db/positions.py` | 🔲 Pending | SQLite position tracking |
| DB decisions | `db/decisions.py` | 🔲 Pending | SQLite decision audit |

**Version target**: v0.03.00
**Dependencies**: Phase 1, Phase 2

---

## Phase 4: Analysis Engine — 🔲 NOT STARTED

| Component | File | Status |
|---|---|---|
| Indicators | `analysis/indicators.py` | 🔲 Pending |
| Probability/edge | `analysis/odds.py` | 🔲 Pending |
| Portfolio analytics | `analysis/portfolio.py` | 🔲 Pending |
| Signal combining | `analysis/signals.py` | 🔲 Pending |

**Version target**: v0.04.00 | **Dependencies**: Phase 1

---

## Phase 5: Simulation Engine — 🔲 NOT STARTED

| Component | File | Status |
|---|---|---|
| Backtest engine | `simulation/engine.py` | 🔲 Pending |
| Data loader | `simulation/data_loader.py` | 🔲 Pending |
| Paper trader | `simulation/paper_trader.py` | 🔲 Pending |
| Performance | `simulation/performance.py` | 🔲 Pending |

**Version target**: v0.05.00 | **Dependencies**: Phase 1, 2, 4

---

## Phase 6: Decision Logging & Self-Learning — 🔲 NOT STARTED

| Component | File | Status |
|---|---|---|
| Decision DB | `db/decisions.py` | 🔲 Pending |
| Learnings | `db/learnings.py` | 🔲 Pending |
| WAL protocol | (in Decision Loop) | 🔲 Pending |
| Workspace files | `.openclaw/workspace/` | 🔲 Pending |

**Version target**: v0.06.00 | **Dependencies**: Phase 2, 3

---

## Phase 7: News & Sentiment Pipeline — 🔲 NOT STARTED

| Component | File | Status |
|---|---|---|
| Sources | `news/sources.py` | 🔲 Pending |
| Classifier | `news/classifier.py` | 🔲 Pending |
| Sentiment | `news/sentiment_scorer.py` | 🔲 Pending |
| Impact | `news/impact_assessor.py` | 🔲 Pending |

**Version target**: v0.07.00 | **Dependencies**: Phase 1

---

## Phase 8: Adaptation Engine & Full Autonomy — 🔲 NOT STARTED

| Component | File | Status |
|---|---|---|
| Bayesian adapter | `simulation/adaptation.py` | 🔲 Pending |
| Heartbeat | (in Decision Loop) | 🔲 Pending |
| Three-loop system | (OpenClaw crons) | 🔲 Pending |

**Version target**: v0.08.00 | **Dependencies**: Phase 5, 6, 7

---

## Bug Class Taxonomy

| Bug Class | Abstract Pattern | Custom Check |
|---|---|---|
| Float for monetary cents | Module uses `float` for currency values that should be `int` (cents) | Verify all money-related Pydantic model fields use `int` |
| Risk limit bypass via config | Risk limits read from config/env instead of compiled in | Verify `risk/` has no `os.environ`, `json.load()`, config-reading code |
| Strategy logic in toolkit | Toolkit computes signal strength or generates recommendation | Verify no function returns buy/sell/hold signal |
| Pydantic strict mode violation | Model accepts extra fields or coerces types silently | Verify all models have `ConfigDict(strict=True, extra="forbid")` |
| Circuit breaker not persistent | Breaker state in memory only, lost on restart | Verify state written to JSON file on trigger |
| Breaker multiplier ignored | evaluate_trade doesn't apply position_size_multiplier from SLOW level | Verify breaker multiplier applied to sized result |
| Duplicate normalize functions | Copy-pasted helpers across modules will diverge | Verify shared helpers in single module |
| IntEnum strict deserialization | JSON stores IntEnum as int, strict Pydantic rejects it | Verify _load_state converts int→IntEnum before model_validate |

---

## Metrics Snapshot

| Metric | Value |
|---|---|
| Version | 0.00.08 |
| Total tests | 270 |
| Coverage | 97% |
| Ruff errors | 0 |
| Pydantic models | 17 (all strict=True, extra=forbid) |
| Risk module lines | 198 |
| Kalshi module lines | 463 |