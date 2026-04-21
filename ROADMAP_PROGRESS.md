# TraderBot Roadmap Progress

**Last updated**: v0.04.01 (2026-04-21)
**Current focus**: Phase 5 — Simulation Engine

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
- [x] `traderbot scan` returns open markets (CLI wired in Phase 3)
- [x] `traderbot analyze <ticker>` returns details + orderbook + indicators (CLI wired in Phase 4)
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

## Phase 3: CLI & OpenClaw Skill — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| CLI entry point | `cli.py` | ✅ Done | Typer CLI with 14 commands, --json flag, Rich output |
| Skill definition | `skills/traderbot/SKILL.md` | ✅ Done | OpenClaw skill with commands, triggers, cron architecture |
| Workspace setup | `.openclaw/workspace/` | ✅ Done | AGENTS.md, SESSION-STATE.md, HEARTBEAT.md, USER.md, .learnings/ |
| DB positions | `db/positions.py` | ✅ Done | SQLite position tracking with upsert/query |
| DB decisions | `db/decisions.py` | ✅ Done | SQLite decision audit with filtering |

**Version**: v0.03.xx | **Tests**: 21 CLI tests passing

**Success criteria met**:
- [x] `traderbot scan`, `traderbot analyze`, `traderbot positions` work from CLI
- [x] `traderbot trade` places orders through risk checks
- [x] OpenClaw skill definition with commands, triggers, env requirements
- [x] Position state persists across CLI invocations (SQLite)
- [x] `traderbot audit` shows full decision history with filters

---

## Phase 4: Analysis Engine — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Indicators | `analysis/indicators.py` | ✅ Done | sma, ema, rsi, bollinger_bands, volume_weighted_price |
| Probability/edge | `analysis/odds.py` | ✅ Done | implied_probability, detect_edge, compute_kelly_inputs, expected_value |
| Portfolio analytics | `analysis/portfolio.py` | ✅ Done | win_rate, brier_score, calibration_curve, sharpe_ratio, max_drawdown, calmar_ratio, edge_realization |
| Signal combining | `analysis/signals.py` | ✅ Done | combine_signals, generate_signal, default_weights |
| CLI integration | `cli.py` | ✅ Done | analyze shows implied prob/spread; signals command added |

**Version**: v0.04.xx | **Tests**: 77 analysis tests + 21 CLI tests passing

**Success criteria met**:
- [x] `traderbot analyze <ticker>` returns statistical indicators and edge estimate
- [x] `traderbot signals` command available (requires tracked markets)
- [x] Brier score computed for historical prediction accuracy
- [x] Indicators work correctly for binary/fixed-expiry instruments

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
| Decision DB | `db/decisions.py` | ✅ Done (in Phase 3) |
| Learnings | `db/learnings.py` | 🔲 Pending |
| WAL protocol | (in Decision Loop) | 🔲 Pending |
| Workspace files | `.openclaw/workspace/` | ✅ Done (in Phase 3) |

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
| Version | 0.04.01 |
| Total tests | 390 |
| Coverage | ~97% |
| Ruff errors | 0 |
| Pydantic models | 23+ (all strict=True, extra=forbid) |
| Risk module lines | 198 |
| Kalshi module lines | 463 |
| Analysis module lines | ~400 |
| CLI commands | 14 |