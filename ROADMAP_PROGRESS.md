# TraderBot Roadmap Progress

**Last updated**: v0.08.32 (2026-04-26)
**Current focus**: All phases complete

---

## Phase 1: Kalshi Data Foundation — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Pydantic models | `kalshi/models.py` | ✅ Done | 18 models with model_config, all strict=True, extra=forbid |
| SDK wrapper | `kalshi/client.py` | ✅ Done | JWT auth via cryptography+PyJWT, httpx async, retry+backoff, rate limiting |
| Market data | `kalshi/markets.py` | ✅ Done | list_markets, get_market, get_orderbook, get_recent_trades |
| Historical data | `kalshi/history.py` | ✅ Done | get_cutoffs, get_historical_trades, get_settled_markets |
| WebSocket | `kalshi/websocket.py` | ✅ Done | MarketStream with auth, subscribe/unsubscribe, auto-reconnect |
| Demo adapter | `kalshi/demo.py` | ✅ Done | DemoAdapter for demo API |
| Shared helpers | `kalshi/_normalize.py` | ✅ Done | Extracted from markets.py/history.py (DRY) |
| Order placement | `kalshi/trading.py` | ✅ Done | place_order, cancel_order, get_order, list_orders via TradingService |

**Tests**: 445 total (all phases), 99% coverage

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

**Tests**: 445 total (all phases), circuit_breaker 100%, limits 97%, sizing 100%

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
| CLI entry point | `cli.py` | ✅ Done | Typer CLI with 15 commands, --json flag, Rich output |
| Skill definition | `skills/traderbot/SKILL.md` | ✅ Done | OpenClaw skill with commands, triggers, cron architecture |
| Workspace setup | `.openclaw/workspace/` | ✅ Done | AGENTS.md, SESSION-STATE.md, HEARTBEAT.md, USER.md, .learnings/ |
| DB positions | `db/positions.py` | ✅ Done | SQLite position tracking with upsert/query |
| DB decisions | `db/decisions.py` | ✅ Done | SQLite decision audit with filtering |

**Version**: v0.04.09 | **Tests**: 41 CLI tests + 77 analysis + 17 trading passing

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

**Version**: v0.04.09 | **Tests**: 77 analysis tests + 41 CLI tests + 17 trading passing

**Success criteria met**:
- [x] `traderbot analyze <ticker>` returns statistical indicators and edge estimate
- [x] `traderbot signals` command available (requires tracked markets)
- [x] Brier score computed for historical prediction accuracy
- [x] Indicators work correctly for binary/fixed-expiry instruments

---

## Phase 5: Simulation Engine — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Backtest engine | `simulation/engine.py` | ✅ Done | BacktestEngine with Strategy Protocol, risk gate integration |
| Data loader | `simulation/data_loader.py` | ✅ Done | DataLoader with caching, quality metrics, retry |
| Models | `simulation/models.py` | ✅ Done | BacktestConfig, BacktestTrade, BacktestResult, Context, Strategy Protocol |
| Paper trader | `simulation/paper_trader.py` | ✅ Done | PaperTrader composing with DemoAdapter, slippage model |
| Performance | `simulation/performance.py` | ✅ Done | Portfolio metrics + prediction-market metrics, compare_strategies |
| Strategy profiles | `simulation/profiles.py` | ✅ Done | StrategyProfile, PRESETS, run_profiles, multi-profile backtest |
| Auth management | `auth.py`, `kalshi/config.py` | ✅ Done | AuthManager + keyring, traderbot auth CLI |
| CLI commands | `cli.py` | ✅ Done | backtest, paper, performance, compare, bootstrap commands |
| Integration tests | `tests/test_simulation_integration.py` | ✅ Done | 35 tests — E2E pipeline, CLI, risk, edge cases |

**Version**: v0.05.00 | **Tests**: 685 total | **Coverage**: 99%

**Success criteria met**:
- [x] `traderbot backtest --strategy momentum` runs historical backtest
- [x] `traderbot paper --strategy momentum` runs paper trading with DemoAdapter
- [x] `traderbot performance` shows metrics with Rich table
- [x] `traderbot compare --profiles Conservative,Moderate,Aggressive` compares profiles
- [x] `traderbot bootstrap` sets up new user environment
- [x] All profiles respect HARD_LIMITS (risk_multiplier scales within, never overrides)
- [x] StrategyProfile with Conservative/Moderate/Aggressive presets

---

## Phase 6: Decision Logging & Self-Learning — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Learnings DB | `db/learnings.py` | ✅ Done | Pattern tracking with 5 categories, promotion, feature requests |
| Vector store | `db/vectors.py` | ✅ Done | ChromaDB wrapper with optional dependency, 3 collections |
| Adaptation models | `simulation/adaptation.py` | ✅ Done | Prior, Posterior, AdaptationConfig, StrategyAdjustment |
| WAL protocol | `wal.py` | ✅ Done | Write-ahead log with concurrent write rejection |
| Pattern promotion | `learning.py` | ✅ Done | scan_for_promotions, promote_learning, run_promotion_cycle |
| Feature requests | `db/learnings.py` + `learning.py` | ✅ Done | FEATURE_REQUESTS.md flow, PENDING_REVIEW status |
| Learnings CLI | `cli.py` | ✅ Done | traderbot learnings with filters, --promote, --json |
| Integration tests | `tests/test_learning_integration.py` | ✅ Done | 32 tests — lifecycle, crash recovery, criteria enforcement |

**Version**: v0.06.00 | **Tests**: 910 total | **Coverage**: 99%

**Success criteria met**:
- [x] `traderbot learnings` shows pattern tracking with filters
- [x] `traderbot learnings --status active` filters by status
- [x] `traderbot learnings --category risk` filters by category
- [x] `traderbot learnings --promote <key>` triggers manual promotion
- [x] WAL protocol writes before trade execution, updates after
- [x] Pattern promotion: recurrence >= 3, 2+ tasks, 30-day window
- [x] Feature requests promoted to PENDING_REVIEW (never auto-committed)
- [x] All Pydantic models use ConfigDict(strict=True, extra="forbid")

---

## Phase 7: News & Sentiment Pipeline — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Sources | `news/sources.py` | ✅ Done | NewsAPI (httpx+retry), Reddit RSS (feedparser), Twitter stub demoted |
| Classifier | `news/classifier.py` | ✅ Done | Hybrid keyword + Voyage semantic, CategoryAnalyzer protocol |
| Sentiment | `news/sentiment_scorer.py` | ✅ Done | VADER primary, TextBlob fallback, Voyage uplift |
| Impact | `news/impact_assessor.py` | ✅ Done | 5-factor weighted scoring, ImpactWeights Pydantic model with sum=1.0 |
| Embeddings | `news/embeddings.py` | ✅ Done | VoyageClient with lazy init, rate limiting, batch API |
| Models | `news/models.py` | ✅ Done | NewsItem, ClassifiedNews, SentimentResult, ImpactAssessment |
| CLI news | `cli.py` | ✅ Done | `traderbot news --json`, profile-aware API key resolution |
| CLI sentiment | `cli.py` | ✅ Done | `traderbot sentiment --json`, category filtering |
| Profile-aware | `news/` + `cli.py` | ✅ Done | ProfileAuthStore API keys, enabled_categories filtering |
| News signal | `analysis/signals.py` | ✅ Done | Sentiment as 4th signal source in generate_signal() |

**Version**: v0.08.32 | **Tests**: 1544 total | **Dependencies**: Phase 1, 9

**Success criteria met**:
- [x] News pipeline aggregates from NewsAPI + Reddit RSS
- [x] Twitter source demoted (stub, last priority)
- [x] Sentiment scored via VADER + TextBlob + Voyage uplift
- [x] Impact assessed with 5-factor weighted model (sum=1.0 validated)
- [x] MarketCategory enum unified — single source in kalshi/models.py
- [x] Profile-aware: API key resolution, category filtering, per-profile paths
- [x] `traderbot news --category economics --json` works
- [x] `generate_signal()` accepts optional `news_sentiment` as 4th source

---

## Phase 8: Adaptation Engine & Full Autonomy — ✅ COMPLETE

| Component | File | Status | Notes |
|---|---|---|---|
| Bayesian adapter | `simulation/adaptation.py` | ✅ Done | Full BayesianAdapter with 7 guardrails |
| Adapter persistence | `simulation/adapter_state.py` | ✅ Done | JSON persistence with atomic writes, schema versioning |
| Heartbeat | `heartbeat.py` | ✅ Done | 7-step cycle, CLI `traderbot heartbeat --json` |
| Learning | `learning.py` + `db/learnings.py` | ✅ Done | Pattern promotion, feature requests |
| Heartbeat persistence | `heartbeat.py` | ✅ Done | state_path wiring, profile-aware paths |
| Three-loop system | `.openclaw/` crons | ✅ Done | 5 cron tasks defined in HEARTBEAT.md |

**Version**: v0.08.32 | **Tests**: 1544 total | **Dependencies**: Phase 5, 6, 7, 9

**Success criteria met**:
- [x] BayesianAdapter persists state across restarts (atomic JSON writes)
- [x] Heartbeat creates adapter with state_path
- [x] Profile-aware state paths (profile.base_dir/adaptation_state.json)
- [x] `traderbot heartbeat --json` reflects adaptation state
- [x] Cooldown, drift detection, variance reset all work with persistence

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
| StrEnum strict deserialization | JSON stores StrEnum as str, strict Pydantic rejects implicit coercion | Verify _parse_* helpers convert raw str→StrEnum before model_validate (e.g., OrderSide("yes")) |
| Duplicate enum definitions | Multiple modules define same enum with different values | Verify single canonical enum in one module, all others import it |
| Unvalidated float weights | Impact or scoring weights stored as bare floats, no sum constraint | Verify Pydantic model with model_validator enforcing sum=1.0 |

---

## Metrics Snapshot

| Metric | Value |
|---|---|
| Version | 0.08.32 |
| Total tests | 1544 |
| Coverage | 99% |
| Ruff errors | 0 |
| Pydantic models | 30+ (all strict=True, extra=forbid) |
| CLI commands | 24+ |
| Self-learning modules | 3 (learnings, wal, learning) |

---

## Agent Profile Binding (Phase 9) — ✅ COMPLETE

Multi-agent deployment with token-based profile binding, per-profile data isolation, risk limits, and market category filtering.

| Component | File | Status | Notes |
|---|---|---|---|
| TradingProfile model | `profiles/models.py` | ✅ Done | Pydantic model with HARD_LIMITS validation, category filtering |
| ProfileRegistry | `profiles/registry.py` | ✅ Done | Keyring CRUD with encrypted storage |
| Token module | `profiles/tokens.py` | ✅ Done | 72-bit entropy tokens, assign/resolve/revoke |
| AgentRiskLimits | `risk/agent_limits.py` | ✅ Done | HARD_LIMITS ceiling enforcement at runtime |
| ProfileAuthStore | `profiles/auth.py` | ✅ Done | Per-profile keyring namespace with fallback chain |
| Agent discovery | `profiles/discovery.py` | ✅ Done | OpenClaw workspace scanning from IDENTITY.md |
| Token injection | `profiles/injection.py` | ✅ Done | Atomic TOOLS.md injection, backup on write |
| Profile-aware config | `profiles/config.py` | ✅ Done | Credential resolution chain: profile → global → env |
| Profile-aware evaluate_trade | `risk/__init__.py` | ✅ Done | Category filter + AgentRiskLimits in risk gate |
| Profile CLI | `cli.py` (profile cmds) | ✅ Done | create/list/show/delete/assign/revoke/discover-agents/set-auth |
| Data isolation | `profiles/isolation.py` | ✅ Done | Per-profile paths for DB, ChromaDB, audit |
| Runtime resolution | `profiles/runtime.py` | ✅ Done | get_current_profile(), load_profile_config(), get_runtime_context() |
| Systemd template | `services/traderbot-agent@.service` | ✅ Done | User-level systemd service template |
| Launchd plist | `services/com.traderbot.agent.plist` | ✅ Done | User-level launchd plist template |
| Installer | `traderbot-installer.sh` | ✅ Done | OS detection, dependency install, persistence setup, config flow |
| docs/profiles.md | `docs/profiles.md` | ✅ Done | Profile system architecture, TradingProfile, registry, token handshake |
| docs/risk.md update | `docs/risk.md` | ✅ Done | AgentRiskLimits, profile-aware evaluate_trade(), category filtering |
| docs/deployment.md | `docs/deployment.md` | ✅ Done | Ubuntu + macOS install, persistence, profile-agent flow |
| docs/security.md | `docs/security.md` | ✅ Done | Threat model, token security, keyring encryption, enforcement layers |
| docs/api.md update | `docs/api.md` | ✅ Done | CLI profile commands reference |
| README.md update | `README.md` | ✅ Done | Multi-agent deployment section, project structure |
| AGENTS.md update | `AGENTS.md` | ✅ Done | Profile-aware trading rules, TRADERBOT_PROFILE_TOKEN |
| SKILL.md update | `skills/traderbot/SKILL.md` | ✅ Done | Profile commands, TRADERBOT_PROFILE_TOKEN env var |

**Version**: v0.07.00 | **Tests**: Additional tests in `tests/profiles/`, `tests/risk/`

**Success criteria met**:
- [x] `traderbot profile create/list/show/delete/assign/revoke` all work
- [x] Agent with token resolves to correct profile, isolated data dirs
- [x] Profile with risk_multiplier 0.5 → trades sized at 50% of HARD_LIMITS
- [x] Profile with categories [Economics, Politics] → Sports trade rejected
- [x] Profile with own Kalshi API key → uses that instead of global
- [x] Agent cannot change profile, token, or risk params at runtime
- [x] Installer runs on Ubuntu + macOS, sets up persistence, injects tokens
- [x] All docs rebuilt and accurate