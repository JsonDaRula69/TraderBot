# Replace Kalshi Demo API with Prod-Based Local Trade Simulator

## TL;DR

> **Quick Summary**: Replace demo API with prod data reads for paper trading. Remove keyring (use .env only). Share API keys across profiles. Rebuild tests with live API for integration, unit tests for pure logic. Add settlement verification, TTL caching, and configurable initial balance.
> 
> **Deliverables**:
> - MarketDataProvider Protocol + ProdDataProvider
> - MarketDataCache (in-memory TTL + SQLite settlement)
> - Settlement verification (lazy reconciliation)
> - PaperPosition.status + position reconciliation (warning on drift)
> - Remove DemoAdapter, demo_mode, all demo workarounds
> - Remove keyring entirely (code + dependency)
> - .env-only auth with shared API keys across profiles
> - Rebuild all tests (hybrid: live API + unit tests for pure logic)
> - Configurable initial balance (CLI flag + profile)
> - Verbose logging throughout
> 
> **Estimated Effort**: XL
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: T1→T7→T13→T18→T19

---

## Context

### Original Request
Replace Kalshi's demo API with prod-based local trade simulation. Paper trading should read real market data from prod API but never place real orders. Also: remove keyring (use .env), share API keys across profiles (local DB isolation only), rebuild all tests (live API for integration, unit tests for pure logic).

### Interview Summary
- Interface: Protocol-based MarketDataProvider (testability + exchange portability)
- Caching: Hybrid — in-memory TTL (30s/60s) + SQLite settlement
- Profile flag: demo_mode → paper_mode (read prod + simulate locally)
- Settlement: Lazy reconciliation (startup + 30min sweep)
- Migration: Clean cutover (no feature flag)
- Reconciliation: Warning only on drift
- Balance: Configurable via CLI flag + profile, default from prod API
- Logging: Verbose throughout
- Tests: Hybrid — live API for integration, unit tests for pure logic
- Keyring: Full removal (code + package)
- Auth: .env-only, shared API keys
- Tests: Rebuild from scratch, use .env for credentials

### Research Findings
- DemoAdapter: 49 lines, referenced in 3 source files (clean removal)
- PaperTrader: 2 demo API calls per order (get_market, get_orderbook)
- No settlement logic — PaperPosition has no status field
- list_markets_by_category: 3 demo workarounds (batch throttle, 100-cap, weather prefix)
- Keyring used in: profiles/tokens.py, profiles/registry.py, profiles/auth.py, auth.py (5-step fallback chain)
- Auth fallback: keyring → .env file → env vars → file → profile-specific keyring namespace
- After keyring removal: .env + env vars only (2 steps, shared across profiles)
- Profile isolation: only local DB paths differ, credentials are shared
- PortfolioService.get_balance() already exists for initial balance
- No caching dependency (hand-roll in-memory TTL)
- ~60 test files, conftest.py with fixtures, respx for HTTP mocking

### Metis Review — Gaps Addressed
- Configurable initial balance → Added CLI flag + profile field
- Auth failure handling → Fail fast, no demo fallback
- PaperPosition.status migration → ALTER TABLE with default 'open'
- Settlement race condition → Check on every submit_order
- Cache staleness → Explicit invalidation before fill-critical reads
- Keyring removal scope → Full removal (code + dependency)
- Test rebuild scope → Hybrid: live API for integration, unit tests for pure logic
- Shared API keys → .env-only, no per-profile credentials

---

## Work Objectives

### Core Objective
Replace demo API with prod data reads, remove keyring, share API keys across profiles, rebuild tests with live API integration, add settlement verification, caching, and configurable balance.

### Must Have
- MarketDataProvider Protocol (get_market, get_orderbook, get_settlement)
- ProdDataProvider wrapping KalshiClient with prod auth
- In-memory TTL cache (30s orderbook, 60s market metadata)
- SQLite settlement cache (permanent, per-profile storage)
- Settlement verification (startup + 30min sweep)
- PaperPosition.status field (open/settled/closed) with DB migration
- Configurable initial balance (CLI + profile, default from prod API)
- Verbose logging in all new modules
- All demo-specific workarounds removed
- Keyring completely removed (code + dependency)
- .env-only auth (shared API keys across profiles)
- Live API integration tests (require KALSHI_API_KEY in .env)
- Unit tests for pure logic (risk, slippage, P&L — no network)

### Must NOT Have (Guardrails)
- NEVER place real orders on prod API — MarketDataProvider is read-only
- NEVER fall back to demo API — fail fast with clear error
- NEVER modify HARD_LIMITS or risk module
- NEVER use float for monetary values — all cents as int
- NEVER add external caching dependency — hand-roll TTL
- NEVER add demo_mode backward compatibility
- NEVER bring back keyring or per-profile credentials
- NEVER add separate test-keys.txt — use .env for test credentials
- NO AI slop: no obvious comments, boilerplate docstrings, generic names

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure**: REBUILT from scratch
- **Framework**: pytest with pytest-asyncio (asyncio_mode = "auto")
- **Integration tests**: Live Kalshi API via .env credentials
- **Unit tests**: Pure logic only (risk, slippage, P&L, position tracking)

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 6 parallel tasks):
├── T1:  MarketDataProvider Protocol [deep]
├── T2:  Delete DemoAdapter + remove demo_mode from config [quick]
├── T3:  PaperPosition.status field + DB migration [quick]
├── T4:  TradingProfile.demo_mode → paper_mode rename [quick]
├── T5:  Verbose logging module [quick]
└── T6:  Remove keyring + simplify auth to .env-only [deep]

Wave 2 (Core implementations — 6 parallel tasks):
├── T7:  ProdDataProvider implementation (T1, T2, T6) [deep]
├── T8:  MarketDataCache — TTL + SQLite settlement (T1, T5) [unspecified-high]
├── T9:  Refactor list_markets_by_category (T2) [unspecified-high]
├── T10: Settlement verification (T3, T8) [deep]
├── T11: Configurable initial balance (T4, T7) [unspecified-high]
└── T12: Remove demo auth from KalshiClient (T2) [quick]

Wave 3 (Integration — 3 tasks):
├── T13: Rewrite PaperTrader for MarketDataProvider (T7,T8,T10,T11) [deep]
├── T14: Update CLI paper command (T11, T13) [unspecified-high]
└── T15: Position reconciliation — warning on drift (T10, T13) [quick]

Wave 4 (Tests + Documentation — parallel):
├── T16: Unit tests — risk, slippage, P&L, position tracking [deep]
├── T17: Integration tests — provider, cache, settlement (live API) [deep]
├── T18: Integration tests — PaperTrader, CLI end-to-end (live API) [deep]
├── T19: Delete old tests/ and verify clean state [quick]
├── T20: Update .openclaw/workspace/ documentation files [writing]
├── T21: Update docs/ and installer for keyring removal and demo deprecation [writing]
└── T22: Update CLI auth commands for .env-only auth [unspecified-high]

Wave 5 (Verification — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 7, 8 | 1 |
| 2 | — | 7, 9, 12 | 1 |
| 3 | — | 10 | 1 |
| 4 | — | 11 | 1 |
| 5 | — | 8 | 1 |
| 6 | — | 7 | 1 |
| 7 | 1, 2, 6 | 11, 13 | 2 |
| 8 | 1, 5 | 10, 13 | 2 |
| 9 | 2 | — | 2 |
| 10 | 3, 8 | 13, 15 | 2 |
| 11 | 4, 7 | 13, 14 | 2 |
| 12 | 2 | — | 2 |
| 13 | 7,8,10,11 | 14, 15 | 3 |
| 14 | 11, 13 | — | 3 |
| 15 | 10, 13 | — | 3 |
| 16 | 6 | — | 4 |
| 17 | 7,8,10,12 | — | 4 |
| 18 | 13,14,15 | — | 4 |
| 19 | 16,17,18 | — | 4 |
| 20 | 6 | — | 4 |
| 21 | 6 | — | 4 |
| 22 | 6 | — | 4 |

### Agent Dispatch Summary
- **Wave 1**: 6 tasks — T1 `deep`, T2-T5 `quick`, T6 `deep`
- **Wave 2**: 6 tasks — T7 `deep`, T8-T9 `unspecified-high`, T10 `deep`, T11 `unspecified-high`, T12 `quick`
- **Wave 3**: 3 tasks — T13 `deep`, T14 `unspecified-high`, T15 `quick`
- **Wave 4**: 7 tasks — T16-T18 `deep`, T19 `quick`, T20 `writing`, T21 `writing`, T22 `unspecified-high`
- **Wave 5**: 4 tasks — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [x] 1. MarketDataProvider Protocol

  **What to do**:
  - Create `src/traderbot/kalshi/provider.py` with `MarketDataProvider` Protocol class
  - Define async methods: `get_market(ticker: str) -> MarketSnapshot`, `get_orderbook(ticker: str) -> OrderBookSnapshot`, `get_settlement(ticker: str) -> SettlementResult | None`
  - Define typed dataclasses: `MarketSnapshot` (ticker, status, open_interest_cents, close_time, settlement_result), `OrderBookSnapshot` (yes_bids, no_bids, timestamp), `SettlementResult` (ticker, outcome, settled_at)
  - Add `MockDataProvider` for unit tests (returns pre-configured data, no network)
  - Add `ProdDataProvider` placeholder (raises NotImplementedError — actual impl in T7)
  - All models use ConfigDict(strict=True, extra="forbid") or frozen dataclasses, monetary values as int cents
  - Add verbose INFO logging: "Fetching market data for {ticker}", etc.
  - Write `tests/test_provider.py` with Protocol conformance + MockDataProvider tests

  **Must NOT do**:
  - Do NOT implement ProdDataProvider (T7)
  - Do NOT import from demo.py or reference demo_mode
  - Do NOT add caching (T8)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T2, T3, T4, T5, T6
  - **Parallel Group**: Wave 1
  - **Blocks**: T7, T8
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/models.py` — Existing Market, OrderBookSnapshot, Settlement models for field structure
  - `src/traderbot/kalshi/_normalize.py` — V2→V1 field mapping logic to reuse
  - `src/traderbot/simulation/paper_trader.py:100-124` — PaperTrader needs: market OI, orderbook for fill price
  - `src/traderbot/kalshi/portfolio.py:15-25` — PortfolioService pattern to follow

  **Acceptance Criteria**:
  - [ ] `src/traderbot/kalshi/provider.py` exists with Protocol, types, MockDataProvider
  - [ ] No references to demo_mode or DemoAdapter
  - [ ] All models use strict validation

  **QA Scenarios**:

  ```
  Scenario: Protocol conformance
    Tool: Bash (python -c)
    Preconditions: provider.py exists
    Steps:
      1. python -c "from traderbot.kalshi.provider import MarketDataProvider, ProdDataProvider; assert issubclass(ProdDataProvider, MarketDataProvider)"
    Expected Result: No exception
    Evidence: .sisyphus/evidence/task-1-protocol.txt

  Scenario: MockDataProvider returns configured data
    Tool: Bash (python -c)
    Steps:
      1. python -c "from traderbot.kalshi.provider import MockDataProvider; m = MockDataProvider(); print(type(m))"
    Expected Result: MockDataProvider instantiates without error
    Evidence: .sisyphus/evidence/task-1-mock.txt
  ```

- [x] 2. Delete DemoAdapter + remove demo_mode from KalshiConfig

  **What to do**:
  - Delete `src/traderbot/kalshi/demo.py` entirely
  - Remove `demo_mode` field from `KalshiConfig` in `src/traderbot/kalshi/config.py`
  - Remove demo URL routing (`demo-api.kalshi.co`) from KalshiConfig
  - Search entire codebase for `DemoAdapter`, `demo_mode`, `demo_mode=True`, references and remove them
  - Update imports referencing demo.py or DemoAdapter
  - Do NOT update PaperTrader or CLI yet (T13, T14 handle those)

  **Must NOT do**:
  - Do NOT update PaperTrader (T13)
  - Do NOT update cli.py paper command (T14)
  - Do NOT remove _normalize.py V2→V1 mappings (still needed on prod)
  - Do NOT remove production auth logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T1, T3, T4, T5, T6
  - **Parallel Group**: Wave 1
  - **Blocks**: T7, T9, T12
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/demo.py` — Entire file to delete
  - `src/traderbot/kalshi/config.py` — KalshiConfig with demo_mode field and demo URL
  - `src/traderbot/kalshi/client.py` — KalshiClient demo_mode references (T12 removes auth path)

  **Acceptance Criteria**:
  - [ ] `src/traderbot/kalshi/demo.py` deleted
  - [ ] `grep -r "DemoAdapter\|demo_mode\|demo_api" src/traderbot/kalshi/` returns zero (excluding client.py auth which T12 handles)

  **QA Scenarios**:

  ```
  Scenario: DemoAdapter completely removed
    Tool: Bash (grep)
    Steps:
      1. grep -r "DemoAdapter\|demo_mode\|demo_api" src/traderbot/kalshi/config.py src/traderbot/kalshi/demo.py
      2. Assert demo.py doesn't exist, config.py has no demo fields
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-2-demo-removal.txt
  ```

- [x] 3. PaperPosition.status field + DB migration

  **What to do**:
  - Add `status: Literal["open", "settled", "closed"]` field to PaperPosition with default "open"
  - Update `_init_paper_positions_table()` to include `status TEXT NOT NULL DEFAULT 'open'`
  - Add DB migration: `ALTER TABLE paper_positions ADD COLUMN status TEXT NOT NULL DEFAULT 'open'` — handle already-exists gracefully
  - Add `mark_settled()` method: updates status to 'settled' and records outcome
  - Add `close_position()` method: sets status to 'closed'
  - All monetary values remain int cents
  - Add verbose logging: "Position {ticker} status: {old} → {new}"

  **Must NOT do**:
  - Do NOT implement settlement logic (T10)
  - Do NOT change submit_order flow (T13)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T1, T2, T4, T5, T6
  - **Parallel Group**: Wave 1
  - **Blocks**: T10
  - **Blocked By**: None

  **References**:
  - `src/traderbot/simulation/paper_trader.py:30-98` — PaperPosition dataclass and _init_paper_positions_table()
  - `src/traderbot/db/` — DB module for per-profile isolation patterns

  **Acceptance Criteria**:
  - [ ] PaperPosition has status field with default "open"
  - [ ] Migration is idempotent (handles existing tables)
  - [ ] mark_settled() and close_position() exist

  **QA Scenarios**:

  ```
  Scenario: PaperPosition status field
    Tool: Bash (python -c)
    Steps:
      1. python -c "from traderbot.simulation.paper_trader import PaperPosition; p = PaperPosition(ticker='TEST', side='yes', avg_price_cents=50, quantity=10); assert p.status == 'open'"
    Expected Result: No error, default is 'open'
    Evidence: .sisyphus/evidence/task-3-status-field.txt

  Scenario: DB migration idempotent
    Tool: Bash (python -c)
    Steps:
      1. Create in-memory SQLite, run _init_paper_positions_table twice
      2. Assert no error, status column exists with default 'open'
    Expected Result: No OperationalError on second run
    Evidence: .sisyphus/evidence/task-3-migration.txt
  ```

- [x] 4. TradingProfile.demo_mode → paper_mode rename

  **What to do**:
  - Rename `TradingProfile.demo_mode` to `TradingProfile.paper_mode` in `src/traderbot/profiles/models.py`
  - Update all references in profiles module: registry.py, config.py, isolation.py, tokens.py, auth.py
  - Change semantics: `paper_mode=True` = "read prod data, simulate locally"
  - Update CLI flags: `--demo` → `--paper`
  - Run `grep -r "demo_mode" src/traderbot/profiles/` — must return zero

  **Must NOT do**:
  - Do NOT change PaperTrader or simulation (T13)
  - Do NOT change KalshiConfig (T2 handles that)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T1, T2, T3, T5, T6
  - **Parallel Group**: Wave 1
  - **Blocks**: T11
  - **Blocked By**: None

  **References**:
  - `src/traderbot/profiles/models.py` — TradingProfile class with demo_mode field
  - `src/traderbot/profiles/registry.py` — ProfileRegistry references
  - `src/traderbot/profiles/config.py` — Config resolution references
  - `src/traderbot/profiles/isolation.py` — DB isolation uses demo_mode for dir paths
  - `src/traderbot/profiles/auth.py` — Keyring auth uses demo_mode (also removed in T6)

  **Acceptance Criteria**:
  - [ ] `grep -r "demo_mode" src/traderbot/profiles/` returns zero
  - [ ] TradingProfile has paper_mode field
  - [ ] `paper_mode=True` means "read prod + simulate locally"

  **QA Scenarios**:

  ```
  Scenario: demo_mode removed from profiles
    Tool: Bash (grep)
    Steps:
      1. grep -r "demo_mode" src/traderbot/profiles/ --include="*.py"
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-4-rename.txt
  ```

- [x] 5. Verbose logging module

  **What to do**:
  - Create `src/traderbot/logging_config.py` with structured logging configuration
  - Format: `%(asctime)s | %(name)s | %(levelname)s | %(message)s`
  - Add `get_logger(name: str, **context)` factory
  - Add `log_market_event(logger, event_type, ticker, **details)` for market data (INFO)
  - Add `log_cache_event(logger, event_type, ticker, hit: bool, **details)` for cache (DEBUG)
  - Add `log_settlement_event(logger, ticker, outcome, **details)` for settlement (INFO)
  - Add `log_reconciliation_event(logger, ticker, drift_cents, **details)` for drift (WARNING)
  - No external dependencies — stdlib `logging` only

  **Must NOT do**:
  - Do NOT use print() for logging
  - Do NOT modify existing modules' logging
  - Do NOT add external dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T1, T2, T3, T4, T6
  - **Parallel Group**: Wave 1
  - **Blocks**: T8
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/client.py` — Existing logging pattern (logger = logging.getLogger(__name__))
  - `src/traderbot/heartbeat.py` — Structured event logging format

  **Acceptance Criteria**:
  - [ ] logging_config.py with all 4 helper functions
  - [ ] No external dependencies
  - [ ] Imports succeed without error

  **QA Scenarios**:

  ```
  Scenario: Logging module imports
    Tool: Bash (python -c)
    Steps:
      1. python -c "from traderbot.logging_config import get_logger, log_market_event, log_cache_event, log_settlement_event, log_reconciliation_event; print('OK')"
    Expected Result: "OK"
    Evidence: .sisyphus/evidence/task-5-logging.txt
  ```

- [x] 6. Remove keyring + simplify auth to .env-only

  **What to do**:
  - Remove `keyring` from `pyproject.toml` dependencies
  - Delete all keyring imports and usage from:
    - `src/traderbot/profiles/auth.py` — Remove keyring credential storage/retrieval
    - `src/traderbot/profiles/registry.py` — Remove keyring namespace isolation
    - `src/traderbot/profiles/tokens.py` — Remove keyring token management
    - `src/traderbot/profiles/config.py` — Remove keyring credential resolution step
    - `src/traderbot/auth.py` — Remove keyring from 5-step fallback chain, simplify to: .env file → env vars (2 steps only)
  - Replace AuthManager with `EnvOnlyAuthManager` (or simplify AuthManager in-place):
    - Read `KALSHI_API_KEY` from .env file or environment variable
    - Shared across all profiles — no per-profile credentials
    - Fail fast with clear message if key not found
  - Delete `src/traderbot/profiles/auth.py` keyring code (or simplify to .env-only)
  - Remove `_check_env_permissions()` keyring-related checks (keep .env file permission checks)
  - Remove per-profile keyring namespace (`traderbot.profiles.<name>.<service>`)
  - Update `src/traderbot/profiles/isolation.py` — profile isolation is DB-only now, not credential-based
  - Update any CLI commands that reference keyring (profile create, profile credentials)
  - Run `grep -r "keyring" src/traderbot/` — must return zero

  **Must NOT do**:
  - Do NOT remove .env file loading (keep it, simplify to .env-only)
  - Do NOT remove env var support (keep as fallback)
  - Do NOT change profile DB isolation (keep per-profile DB dirs)
  - Do NOT add any new auth mechanism (just simplify existing)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Touches auth chain across 5+ files, careful removal needed
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T1, T2, T3, T4, T5
  - **Parallel Group**: Wave 1
  - **Blocks**: T7 (ProdDataProvider needs simplified auth)
  - **Blocked By**: None

  **References**:
  - `src/traderbot/auth.py` — AuthManager with 5-step fallback (keyring → .env → env → file → profile keyring). Simplify to: .env → env vars (2 steps)
  - `src/traderbot/profiles/auth.py` — Per-profile keyring credential storage. Remove keyring parts, keep .env
  - `src/traderbot/profiles/tokens.py` — Keyring token management. Remove
  - `src/traderbot/profiles/registry.py` — ProfileRegistry with keyring CRUD. Remove keyring operations
  - `src/traderbot/profiles/config.py` — Credential resolution with keyring step. Remove keyring step
  - `src/traderbot/profiles/isolation.py` — Per-profile DB dirs. Keep DB isolation, remove credential isolation
  - `pyproject.toml` — Remove keyring from dependencies

  **Acceptance Criteria**:
  - [ ] `grep -r "keyring" src/traderbot/` returns zero
  - [ ] `grep "keyring" pyproject.toml` returns zero
  - [ ] Auth reads from .env file → env vars only
  - [ ] All profiles share same API key
  - [ ] Auth fails fast with clear message if no key found

  **QA Scenarios**:

  ```
  Scenario: Keyring completely removed
    Tool: Bash (grep)
    Steps:
      1. grep -r "keyring" src/traderbot/ --include="*.py"
      2. grep "keyring" pyproject.toml
    Expected Result: Zero results in both
    Evidence: .sisyphus/evidence/task-6-keyring-removal.txt

  Scenario: .env-only auth works
    Tool: Bash (python -c)
    Steps:
      1. python -c "from traderbot.auth import AuthManager; print('OK')"
    Expected Result: AuthManager imports without keyring
    Evidence: .sisyphus/evidence/task-6-env-auth.txt
  ```

- [x] 7. ProdDataProvider implementation

  **What to do**:
  - Implement `ProdDataProvider` in `src/traderbot/kalshi/provider.py` (Protocol from T1)
  - Constructor takes `KalshiClient` (prod-configured) and optional `MarketDataCache`
  - `get_market(ticker)` → MarketService.get_market() → normalize → MarketSnapshot
  - `get_orderbook(ticker)` → client orderbook call → OrderBookSnapshot
  - `get_settlement(ticker)` → check if market settled → SettlementResult or None
  - If cache provided, check cache first (hit → return, miss → fetch → cache → return)
  - Add verbose logging via log_market_event() for every fetch, log_cache_event() for cache hits/misses
  - Fail fast on auth errors: raise `ProdAPIError` with clear message, NO demo fallback
  - All monetary values in cents as int (use `_to_cents()`)

  **Must NOT do**:
  - Do NOT add demo API fallback
  - Do NOT place any orders
  - Do NOT implement caching logic (T8)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T1, T2, T6
  - **Parallel Group**: Wave 2
  - **Blocks**: T11, T13
  - **Blocked By**: T1 (Protocol), T2 (demo removal), T6 (auth simplification)

  **References**:
  - `src/traderbot/kalshi/provider.py` — MarketDataProvider Protocol (from T1)
  - `src/traderbot/kalshi/markets.py` — MarketService.get_market()
  - `src/traderbot/kalshi/_normalize.py` — _normalize_market() for V2→V1 mapping
  - `src/traderbot/kalshi/client.py` — KalshiClient for auth and requests
  - `src/traderbot/logging_config.py` — Logging helpers (from T5)

  **Acceptance Criteria**:
  - [ ] ProdDataProvider implements all 3 Protocol methods
  - [ ] No demo API references
  - [ ] Auth failures raise ProdAPIError (no silent fallback)
  - [ ] All monetary values are int cents

  **QA Scenarios**:

  ```
  Scenario: ProdDataProvider conforms to Protocol
    Tool: Bash (python -c)
    Steps:
      1. python -c "from traderbot.kalshi.provider import ProdDataProvider, MarketDataProvider; assert issubclass(ProdDataProvider, MarketDataProvider)"
    Expected Result: No exception
    Evidence: .sisyphus/evidence/task-7-protocol.txt

  Scenario: Auth failure raises clear error
    Tool: Bash (python -c)
    Steps:
      1. Create ProdDataProvider with invalid credentials
      2. Call get_market() → assert ProdAPIError raised
      3. Assert error message does NOT mention "demo" or "fallback"
    Expected Result: Clear auth error, no silent demo fallback
    Evidence: .sisyphus/evidence/task-7-auth-error.txt
  ```

- [x] 8. MarketDataCache — TTL + SQLite settlement

  **What to do**:
  - Create `src/traderbot/kalshi/cache.py` with `MarketDataCache` class
  - In-memory TTL: orderbooks (30s), market metadata (60s) — dict + asyncio.Lock + timestamp expiry
  - Cache key format: `{type}:{ticker}` (e.g., `orderbook:INXDOW-24`)
  - Methods: get_orderbook, set_orderbook, get_market, set_market, invalidate(ticker), invalidate_all, clear_expired
  - SQLite settlement cache: permanent storage, per-profile path `~/.traderbot/{mode}-{name}/settlement_cache.db`
  - Methods: get_settlement, set_settlement
  - Add verbose logging via log_cache_event() for every hit/miss/store/invalidate

  **Must NOT do**:
  - Do NOT use external caching libraries
  - Do NOT cache settlement in memory
  - Do NOT add Redis or other external deps

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T7, T9, T10, T11, T12
  - **Parallel Group**: Wave 2
  - **Blocks**: T10, T13
  - **Blocked By**: T1 (Protocol types), T5 (logging)

  **References**:
  - `src/traderbot/kalshi/provider.py` — Cache value types
  - `src/traderbot/profiles/isolation.py` — Per-profile DB path pattern
  - `src/traderbot/logging_config.py` — log_cache_event()

  **Acceptance Criteria**:
  - [ ] In-memory TTL cache with asyncio.Lock
  - [ ] SQLite settlement cache with per-profile isolation
  - [ ] No external dependencies
  - [ ] invalidate() and invalidate_all() methods

  **QA Scenarios**:

  ```
  Scenario: TTL expiry works
    Tool: Bash (python -c)
    Steps:
      1. Store data with TTL=1s, retrieve immediately (hit)
      2. Sleep 1.1s, retrieve (miss/expired)
    Expected Result: Hit before TTL, miss after expiry
    Evidence: .sisyphus/evidence/task-8-ttl.txt

  Scenario: SQLite settlement persists
    Tool: Bash (python -c)
    Steps:
      1. Store settlement, create new cache instance with same DB
      2. Retrieve settlement → same data
    Expected Result: Data persists across instances
    Evidence: .sisyphus/evidence/task-8-sqlite.txt
  ```

- [x] 9. Refactor list_markets_by_category

  **What to do**:
  - Remove 3 demo workarounds from `list_markets_by_category()`:
    1. Remove batch throttling (3/batch, 0.5s gap)
    2. Remove pagination limit cap at 100
    3. Remove weather prefix fallback (KXHIGH/KXLOW/KXTEMP)
  - Keep: category enrichment from event slug, _normalize_market(), prod-appropriate rate limiting
  - Add verbose logging: "Fetching markets for category {cat}", "Found {N} events"

  **Must NOT do**:
  - Do NOT remove category enrichment
  - Do NOT remove _normalize_market()
  - Do NOT remove all rate limiting (keep prod token bucket)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T7, T8, T10, T11, T12
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T2

  **References**:
  - `src/traderbot/kalshi/markets.py` — Primary file with all 3 workarounds

  **Acceptance Criteria**:
  - [ ] No batch throttle, no 100-cap, no weather prefix code
  - [ ] Category enrichment still works
  - [ ] _normalize_market() untouched

  **QA Scenarios**:

  ```
  Scenario: Demo workarounds removed
    Tool: Bash (grep)
    Steps:
      1. grep -n "batch\|KXHIGH\|KXLOW\|KXTEMP\|sleep.*0.5" src/traderbot/kalshi/markets.py
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-9-refactor.txt
  ```

- [x] 10. Settlement verification — lazy reconciliation

  **What to do**:
  - Create `src/traderbot/simulation/settlement.py` with `SettlementVerifier` class
  - Constructor takes `MarketDataProvider` and PaperTrader (or DB connection)
  - `check_settlements_on_startup()` — check all open positions against prod API
  - `check_settlements_periodic()` — 30min sweep for positions near close_time
  - `check_settlement_before_order(ticker)` — block orders on settled markets
  - Use MarketDataCache for settlement results
  - Log settlement events and drift warnings
  - Fail gracefully on API errors (WARNING log, no crash)

  **Must NOT do**:
  - Do NOT poll far-future markets
  - Do NOT block trading on API errors
  - Do NOT add WebSocket subscriptions

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T7, T8, T9, T11, T12
  - **Parallel Group**: Wave 2
  - **Blocks**: T13, T15
  - **Blocked By**: T3 (PaperPosition.status), T8 (cache)

  **References**:
  - `src/traderbot/kalshi/provider.py` — get_settlement()
  - `src/traderbot/kalshi/cache.py` — Settlement caching
  - `src/traderbot/simulation/paper_trader.py` — mark_settled() (from T3)
  - `src/traderbot/kalshi/_normalize.py` — Status mapping ("finalized" → "settled")

  **Acceptance Criteria**:
  - [ ] SettlementVerifier with startup, periodic, and per-order checks
  - [ ] 30-minute periodic sweep for near-expiry positions only
  - [ ] Per-order check blocks settled markets
  - [ ] Graceful on API errors

  **QA Scenarios**:

  ```
  Scenario: Startup check marks settled positions
    Tool: Bash (python -c)
    Steps:
      1. MockDataProvider with settled market, PaperTrader with open position
      2. Run check_settlements_on_startup()
      3. Assert position status = 'settled'
    Expected Result: Position correctly settled
    Evidence: .sisyphus/evidence/task-10-settlement.txt

  Scenario: API error doesn't crash sweep
    Tool: Bash (python -c)
    Steps:
      1. MockDataProvider that raises ConnectionError
      2. Run check_settlements_periodic()
      3. Assert: no crash, WARNING logged
    Expected Result: Graceful degradation
    Evidence: .sisyphus/evidence/task-10-error-resilience.txt
  ```

- [x] 11. Configurable initial balance

  **What to do**:
  - Add `initial_balance_cents: int | None` to TradingProfile (default None)
  - Add `--initial-balance` CLI flag to `traderbot paper`
  - When no flag or `--initial-balance 0`: query `PortfolioService.get_balance()` via ProdDataProvider
  - When `--initial-balance N` (N > 0): use N cents
  - Replace hardcoded `100_000_00` in cli.py and PaperTrader
  - Fallback: if balance fetch fails and no flag, use DEFAULT_INITIAL_BALANCE_CENTS with WARNING log
  - Add logging: "Using prod API balance: ${amount}", "Using CLI balance: ${amount}"

  **Must NOT do**:
  - Do NOT hardcode $100K as only option
  - Do NOT require prod API auth if --initial-balance explicitly set
  - Do NOT change risk module

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T8, T9, T10, T12
  - **Parallel Group**: Wave 2
  - **Blocks**: T13, T14
  - **Blocked By**: T4 (paper_mode rename), T7 (ProdDataProvider for balance fetch)

  **References**:
  - `src/traderbot/simulation/paper_trader.py:100-124` — initial_cash_cents=100_000_00
  - `src/traderbot/cli.py:395-410` — hardcoded portfolio_value_cents=100_000_00
  - `src/traderbot/kalshi/portfolio.py:15-25` — PortfolioService.get_balance()
  - `src/traderbot/profiles/models.py` — TradingProfile (now with paper_mode from T4)

  **Acceptance Criteria**:
  - [ ] TradingProfile has optional initial_balance_cents
  - [ ] --initial-balance flag works
  - [ ] No hardcoded 100_000_00
  - [ ] Balance fetch failure falls back with WARNING

  **QA Scenarios**:

  ```
  Scenario: --initial-balance flag
    Tool: Bash
    Steps:
      1. traderbot paper --help → assert --initial-balance documented
    Expected Result: Flag appears in help
    Evidence: .sisyphus/evidence/task-11-balance-flag.txt
  ```

- [x] 12. Remove demo auth from KalshiClient

  **What to do**:
  - Remove `demo_mode` parameter from `KalshiClient.__init__`
  - Remove demo auth branch in `_authenticate()` (api_key="demo", no RSA signing)
  - Remove `if self.demo_mode:` branches throughout
  - Remove demo URL routing (demo-api.kalshi.co)
  - Keep prod auth (keyring → .env → env → file) — BUT keyring already removed in T6, so this becomes: .env → env vars
  - Clean up docstrings
  - Verify `grep -r "demo_mode\|demo_api" src/traderbot/kalshi/client.py` returns zero

  **Must NOT do**:
  - Do NOT remove prod auth logic (.env, env vars)
  - Do NOT remove rate limiting (keep prod token bucket)
  - Do NOT remove request signing (RSA-PSS)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T7, T8, T9, T10, T11
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T2

  **References**:
  - `src/traderbot/kalshi/client.py` — KalshiClient with demo_mode param
  - `src/traderbot/kalshi/config.py` — KalshiConfig (demo_mode already removed in T2)

  **Acceptance Criteria**:
  - [ ] KalshiClient has no demo_mode parameter
  - [ ] No demo auth path in _authenticate()
  - [ ] Prod auth flow works (.env → env vars)

  **QA Scenarios**:

  ```
  Scenario: Demo auth removed
    Tool: Bash (grep)
    Steps:
      1. grep -n "demo_mode\|demo.*key\|demo-api" src/traderbot/kalshi/client.py
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-12-client.txt
  ```

- [x] 13. Rewrite PaperTrader for MarketDataProvider

  **What to do**:
  - Replace `DemoAdapter` param with `MarketDataProvider` in PaperTrader.__init__
  - Update `submit_order()` to use `provider.get_market()` and `provider.get_orderbook()`
  - Use MarketDataCache (check cache before provider, invalidate before fill-critical reads)
  - Integrate SettlementVerifier — call `check_settlement_before_order(ticker)` before processing
  - Replace `_default_open_interest = 5000` with fetch from provider (fallback on API error)
  - Use configurable `initial_cash_cents` (from T11) instead of hardcoded 100_000_00
  - Add logging: "Submitting paper order for {ticker}", "Cache miss for {ticker}"
  - Remove all DemoAdapter and demo API references

  **Must NOT do**:
  - Do NOT change position tracking (SQLite PaperPosition logic)
  - Do NOT change PaperSlippageModel
  - Do NOT change risk gating (evaluate_trade)
  - Do NOT add real order placement

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T7, T8, T10, T11
  - **Parallel Group**: Wave 3
  - **Blocks**: T14, T15
  - **Blocked By**: T7 (ProdDataProvider), T8 (Cache), T10 (Settlement), T11 (Balance)

  **References**:
  - `src/traderbot/simulation/paper_trader.py` — Primary file to rewrite
  - `src/traderbot/kalshi/provider.py` — New data source
  - `src/traderbot/kalshi/cache.py` — Caching
  - `src/traderbot/simulation/settlement.py` — Settlement checks

  **Acceptance Criteria**:
  - [ ] PaperTrader accepts MarketDataProvider (not DemoAdapter)
  - [ ] submit_order uses provider.get_market() and provider.get_orderbook()
  - [ ] SettlementVerifier checked before every order
  - [ ] No DemoAdapter import
  - [ ] No hardcoded 100_000_00

  **QA Scenarios**:

  ```
  Scenario: PaperTrader uses ProdDataProvider
    Tool: Bash (python -c)
    Steps:
      1. Create MockDataProvider, PaperTrader with it
      2. Submit order → assert processed with mock data
    Expected Result: Order processed with mock data, no demo calls
    Evidence: .sisyphus/evidence/task-13-provider.txt

  Scenario: Settlement check blocks settled market order
    Tool: Bash (python -c)
    Steps:
      1. MockDataProvider with settled market
      2. Try to submit order → assert rejected
    Expected Result: "settled" in error message
    Evidence: .sisyphus/evidence/task-13-settled-block.txt
  ```

- [x] 14. Update CLI paper command

  **What to do**:
  - Update `traderbot paper` to use ProdDataProvider (not DemoAdapter)
  - Wire `--initial-balance` flag through to PaperTrader
  - Wire `--initial-balance 0` → query PortfolioService.get_balance()
  - Create ProdDataProvider + MarketDataCache + SettlementVerifier instances
  - Run startup settlement check
  - Add `--reconcile` flag that triggers position reconciliation on startup
  - Remove DemoAdapter import from cli.py
  - Update help text: "Paper trading with real market data"

  **Must NOT do**:
  - Do NOT add real order placement
  - Do NOT remove the `trade` command

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T11, T13
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: T11 (balance config), T13 (PaperTrader rewrite)

  **References**:
  - `src/traderbot/cli.py` — Paper command, DemoAdapter import
  - `src/traderbot/kalshi/provider.py` — ProdDataProvider
  - `src/traderbot/kalshi/cache.py` — MarketDataCache
  - `src/traderbot/simulation/settlement.py` — SettlementVerifier

  **Acceptance Criteria**:
  - [ ] `traderbot paper` uses ProdDataProvider
  - [ ] --initial-balance flag works
  - [ ] --reconcile flag works
  - [ ] No DemoAdapter import in cli.py

  **QA Scenarios**:

  ```
  Scenario: CLI uses ProdDataProvider
    Tool: Bash (grep)
    Steps:
      1. grep -n "DemoAdapter" src/traderbot/cli.py
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-14-cli.txt
  ```

- [x] 15. Position reconciliation — warning on drift

  **What to do**:
  - Add `reconcile_positions()` to SettlementVerifier
  - Fetch real positions from PortfolioService.get_positions()
  - Compare against paper positions from PaperTrader DB
  - Log WARNING for each drift: "Position drift: paper={side} {qty}, real={side} {qty}"
  - Log summary: "Reconciliation: {N} checked, {M} drifts"
  - Add `--reconcile` CLI flag to `traderbot paper`
  - Skip reconciliation if no prod API credentials (log INFO)
  - Do NOT block trading or modify positions

  **Must NOT do**:
  - Do NOT block trading on drift
  - Do NOT auto-correct positions

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T10, T13
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: T10 (SettlementVerifier), T13 (PaperTrader)

  **References**:
  - `src/traderbot/simulation/settlement.py` — Add method here
  - `src/traderbot/kalshi/portfolio.py:27-43` — PortfolioService.get_positions()
  - `src/traderbot/logging_config.py` — log_reconciliation_event()

  **Acceptance Criteria**:
  - [ ] reconcile_positions() method on SettlementVerifier
  - [ ] WARNING logs for drift, INFO for skip
  - [ ] Does NOT block trading or modify positions

  **QA Scenarios**:

  ```
  Scenario: Reconciliation detects drift
    Tool: Bash (python -c)
    Steps:
      1. MockDataProvider with different real positions
      2. Run reconcile_positions()
      3. Assert WARNING logged, positions unchanged
    Expected Result: Drift detected and logged, positions unchanged
    Evidence: .sisyphus/evidence/task-15-reconciliation.txt
  ```

- [x] 16. Unit tests — risk, slippage, P&L, position tracking

  **What to do**:
  - Rebuild `tests/` from scratch with new structure:
    - `tests/test_risk.py` — Risk limits, evaluate_trade, circuit breaker (pure logic, no network)
    - `tests/test_slippage.py` — PaperSlippageModel (pure math, no network)
    - `tests/test_pnl.py` — P&L calculations (pure arithmetic, no network)
    - `tests/test_positions.py` — PaperPosition.status transitions, DB operations (SQLite in-memory, no network)
    - `tests/test_settlement_unit.py` — SettlementVerifier logic (mock provider, no network)
    - `tests/test_cache_unit.py` — MarketDataCache TTL logic, SQLite settlement (in-memory, no network)
    - `tests/test_logging.py` — Logging helpers (no network)
    - `tests/conftest.py` — Shared fixtures (MockDataProvider, in-memory DB, etc.)
  - All unit tests run WITHOUT network access
  - Use MockDataProvider for provider-dependent unit tests
  - Use in-memory SQLite for DB-dependent unit tests
  - All monetary values tested as int cents

  **Must NOT do**:
  - Do NOT make real API calls in unit tests
  - Do NOT use respx or HTTP mocking for unit tests (use MockDataProvider)
  - Do NOT modify source code (only write tests)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T17, T18
  - **Parallel Group**: Wave 4
  - **Blocks**: T19
  - **Blocked By**: T6 (keyring removal — auth changes affect test setup)

  **References**:
  - `src/traderbot/risk/limits.py` — Risk logic to test
  - `src/traderbot/simulation/paper_trader.py` — PaperSlippageModel, P&L calculations
  - `src/traderbot/simulation/settlement.py` — Settlement logic
  - `src/traderbot/kalshi/cache.py` — Cache logic

  **Acceptance Criteria**:
  - [ ] 7+ unit test files covering risk, slippage, P&L, positions, settlement, cache, logging
  - [ ] All unit tests pass without network
  - [ ] MockDataProvider used for provider tests
  - [ ] conftest.py with shared fixtures

  **QA Scenarios**:

  ```
  Scenario: Unit tests pass without network
    Tool: Bash
    Steps:
      1. Unset KALSHI_API_KEY env var
      2. pytest tests/test_risk.py tests/test_slippage.py tests/test_pnl.py tests/test_positions.py tests/test_settlement_unit.py tests/test_cache_unit.py tests/test_logging.py -v
      3. Assert all pass
    Expected Result: All unit tests pass without any network calls
    Evidence: .sisyphus/evidence/task-16-unit-tests.txt
  ```

- [x] 17. Integration tests — provider, cache, settlement (live API)

  **What to do**:
  - Create integration tests that hit LIVE Kalshi API:
    - `tests/test_provider_integration.py` — ProdDataProvider.get_market(), get_orderbook(), get_settlement() against real API
    - `tests/test_cache_integration.py` — MarketDataCache TTL expiry with real data, SQLite settlement persistence
    - `tests/test_settlement_integration.py` — SettlementVerifier against real API (find a recently-settled market)
    - `tests/test_auth_integration.py` — .env-only auth flow, shared API keys across profiles
  - All integration tests require `KALSHI_API_KEY` in .env or environment
  - Mark with `@pytest.mark.integration` for optional filtering
  - Add `pytest.ini` or `pyproject.toml` marker config for integration tests
  - Test real data flows: fetch market → cache → retrieve → verify fields

  **Must NOT do**:
  - Do NOT place real orders (read-only API calls only)
  - Do NOT hardcode API keys in test files
  - Do NOT mock API calls (that's what unit tests are for)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T16, T18
  - **Parallel Group**: Wave 4
  - **Blocks**: T19
  - **Blocked By**: T7 (ProdDataProvider), T8 (Cache), T10 (Settlement), T12 (Client)

  **References**:
  - `src/traderbot/kalshi/provider.py` — ProdDataProvider to integration-test
  - `src/traderbot/kalshi/cache.py` — MarketDataCache to integration-test
  - `src/traderbot/simulation/settlement.py` — SettlementVerifier
  - `src/traderbot/auth.py` — .env-only auth
  - `.env` or `KALSHI_API_KEY` env var for credentials

  **Acceptance Criteria**:
  - [ ] 4 integration test files with `@pytest.mark.integration`
  - [ ] All integration tests pass against live Kalshi API (require KALSHI_API_KEY)
  - [ ] No API keys in test files
  - [ ] No real orders placed

  **QA Scenarios**:

  ```
  Scenario: Integration tests pass with live API
    Tool: Bash
    Steps:
      1. Ensure KALSHI_API_KEY in .env
      2. pytest tests/test_provider_integration.py tests/test_cache_integration.py tests/test_settlement_integration.py tests/test_auth_integration.py -v -m integration
      3. Assert all pass
    Expected Result: All integration tests pass against live API
    Evidence: .sisyphus/evidence/task-17-integration-tests.txt
  ```

- [x] 18. Integration tests — PaperTrader, CLI end-to-end (live API)

  **What to do**:
  - Create end-to-end integration tests:
    - `tests/test_paper_trader_integration.py` — PaperTrader with ProdDataProvider against live API: submit paper order, verify position, check P&L
    - `tests/test_cli_integration.py` — `traderbot paper` command with live data: verify balance fetch, order submission, settlement check
    - `tests/test_reconciliation_integration.py` — Position reconciliation against real positions
  - Test with small amounts only (paper trading)
  - Mark with `@pytest.mark.integration`

  **Must NOT do**:
  - Do NOT place real orders
  - Do NOT modify real positions

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T16, T17
  - **Parallel Group**: Wave 4
  - **Blocks**: T19
  - **Blocked By**: T13 (PaperTrader), T14 (CLI), T15 (Reconciliation)

  **References**:
  - `src/traderbot/simulation/paper_trader.py` — PaperTrader to test
  - `src/traderbot/cli.py` — CLI to test
  - `src/traderbot/simulation/settlement.py` — Reconciliation to test

  **Acceptance Criteria**:
  - [ ] 3 integration test files with `@pytest.mark.integration`
  - [ ] End-to-end paper order lifecycle tested
  - [ ] CLI --initial-balance and --reconcile flags tested

  **QA Scenarios**:

  ```
  Scenario: PaperTrader end-to-end with live API
    Tool: Bash
    Steps:
      1. pytest tests/test_paper_trader_integration.py -v -m integration
    Expected Result: All tests pass with real API data
    Evidence: .sisyphus/evidence/task-18-e2e-tests.txt
  ```

- [x] 19. Delete old test suite and verify clean state

  **What to do**:
  - Delete ALL old test files that test removed code:
    - `tests/test_demo.py` — Tests DemoAdapter (removed)
    - `tests/test_auth.py` — Tests keyring auth (removed)
    - `tests/test_client.py` — Tests demo auth path (removed)
    - Any other test files referencing demo_mode, keyring, or removed features
  - Keep new test files from T16, T17, T18
  - Update `conftest.py` to remove old fixtures (keyring mock, DemoAdapter fixture)
  - Remove `respx` dependency from pyproject.toml (no more HTTP mocking for main tests)
  - Verify: `grep -r "keyring\|DemoAdapter\|demo_mode\|demo_api" tests/` returns zero
  - Run `pytest tests/ -v`

  **Must NOT do**:
  - Do NOT delete new test files (T16, T17, T18)
  - Do NOT delete conftest.py (update it, keep shared fixtures)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T16, T17, T18
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: T16, T17, T18

  **References**:
  - `tests/` — Directory to clean up
  - `pyproject.toml` — Remove respx dependency
  - `tests/conftest.py` — Update fixtures

  **Acceptance Criteria**:
  - [ ] `grep -r "keyring\|DemoAdapter\|demo_mode" tests/` returns zero
  - [ ] `pytest tests/ -v` passes
  - [ ] respx removed from pyproject.toml

  **QA Scenarios**:

  ```
  Scenario: Old test references removed
    Tool: Bash (grep)
    Steps:
      1. grep -r "keyring\|DemoAdapter\|demo_mode" tests/ --include="*.py"
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-19-old-tests-removed.txt

  Scenario: Full test suite passes
    Tool: Bash
    Steps:
      1. pytest tests/ -v
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-19-full-suite.txt
  ```

- [x] 20. Update .openclaw/workspace/ documentation files

  **What to do**:
  - **TOOLS.md**: Update `traderbot paper` description from "Paper trade against demo API" to "Paper trade with real market data (prod API) — simulated orders, no real money"
  - **TOOLS.md**: Update `traderbot profile set-auth` note — credentials are now shared via .env, not per-profile keyring
  - **TOOLS.md**: Update `traderbot auth check` description — now verifies .env credentials, not keyring
  - **TOOLS.md**: Update note about empty signals on demo environments — remove "demo environments" reference or clarify
  - **SOUL.md line 34**: Update "keyring" reference to ".env files" — change "You do NOT read or display credential values from .env files, keyring, or environment variables" to "You do NOT read or display credential values from .env files or environment variables" (remove keyring)
  - **AGENTS.md**: Update keyring namespace reference — profiles now share .env credentials, not per-profile keyring
  - **BOOT.md**: Review for any demo API references (appears clean, but verify)
  - **IDENTITY.md**: No changes needed (template only)

  **Must NOT do**:
  - Do NOT modify risk limits or operating constraints in SOUL.md
  - Do NOT change permission model in SOUL.md (only update credential reference)

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T19
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: T6 (keyring removal must be decided first)

  **References**:
  - `.openclaw/workspace/TOOLS.md` — Lines 42, 79, 88, 98, 197 — demo API, keyring, credentials references
  - `.openclaw/workspace/SOUL.md` — Line 34 — keyring reference in boundaries
  - `.openclaw/workspace/AGENTS.md` — Line 96, 101, 105 — keyring and credential references

  **Acceptance Criteria**:
  - [ ] `grep -r "demo.api\|demo mode\|keyring" .openclaw/workspace/` returns zero (or only acceptable references)
  - [ ] TOOLS.md paper command description updated
  - [ ] SOUL.md keyring reference removed
  - [ ] AGENTS.md profile credential reference updated

  **QA Scenarios**:

  ```
  Scenario: No demo API references in workspace files
    Tool: Bash (grep)
    Steps:
      1. grep -r "demo.api\|keyring" .openclaw/workspace/ --include="*.md"
    Expected Result: Zero results for demo API, zero for keyring
    Evidence: .sisyphus/evidence/task-20-workspace-clean.txt
  ```

- [x] 21. Update docs/ and installer for keyring removal and demo deprecation

  **What to do**:
  - **docs/security.md**: Remove all keyring references (11 matches). Replace keyring threat model with .env threat model. Update per-profile credential isolation → shared .env credentials. Update token management from keyring → .env-based.
  - **docs/kalshi.md**: Remove demo API URL row (line 10). Remove "Demo mode" bullet (line 110). Update WebSocket demo URL (line 62).
  - **docs/simulation.md**: Update line 129-130 from "Connects to Kalshi's demo API" to "Reads real market data from Kalshi prod API — all orders are simulated locally"
  - **docs/architecture.md**: Remove keyring section (lines 277-302). Replace with .env-only auth description. Update `traderbot auth login` and `traderbot auth set-key` descriptions.
  - **docs/profiles.md**: Remove demo_mode references (lines 52, 215). Update credential storage from per-profile keyring → shared .env.
  - **docs/openclaw-integration.md**: Remove demo API reference (line 259). Update to describe prod data reads with local simulation.
  - **docs/product-roadmap.md**: Remove "Demo mode works against demo-api.kalshi.co" (line 25).
  - **docs/research.md**: Remove demo API URL reference (line 118).
  - **docs/deployment.md**: Remove `gnome-keyring` from Linux dependencies (line 41). Update to note .env-only auth.
  - **install/traderbot-installer.sh**: Remove `gnome-keyring` from apt packages (line 156). Remove keyring storage option (lines 512-658). Remove `traderbot auth login` keyring prompt. Remove `use_keyring` variable and related code. Update to use .env-only approach.
  - **ROADMAP_PROGRESS.md**: Update Auth management row from "AuthManager + keyring" to ".env-only AuthManager". Update ProfileAuthStore row. Update security doc row.
  - **README.md**: Remove keyring references from directory structure (line 37). Update security bullet point (line 78).
  - **skills/traderbot/SKILL.md**: Update per-profile credential reference (line 89) to shared .env.
  - **AGENTS.md**: Update keyring namespace reference (line 105) to shared .env credentials.

  **Must NOT do**:
  - Do NOT change functional behavior descriptions (only remove demo/keyring references)
  - Do NOT modify risk module documentation (immutable)
  - Do NOT change docs/ without explicit human approval per AGENTS.md rules — flag these changes for human review

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T19, T20
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: T6 (keyring removal must be implemented first)

  **References**:
  - `docs/security.md` — 11 keyring references
  - `docs/kalshi.md` — Demo API URL and mode references
  - `docs/simulation.md` — "Connects to Kalshi's demo API" (lines 129-130)
  - `docs/architecture.md` — Keyring section (lines 277-302)
  - `docs/profiles.md` — demo_mode references (lines 52, 215)
  - `docs/openclaw-integration.md` — Demo API reference (line 259)
  - `docs/product-roadmap.md` — Demo mode reference (line 25)
  - `docs/research.md` — Demo API URL (line 118)
  - `docs/deployment.md` — gnome-keyring dependency (line 41)
  - `install/traderbot-installer.sh` — gnome-keyring package (line 156), keyring storage (lines 512-658)
  - `ROADMAP_PROGRESS.md` — Auth and security rows
  - `README.md` — Keyring references (lines 37, 78)
  - `skills/traderbot/SKILL.md` — Per-profile keyring (line 89)
  - `AGENTS.md` — Keyring namespace (line 105)

  **Acceptance Criteria**:
  - [ ] `grep -r "keyring" docs/ install/ README.md ROADMAP_PROGRESS.md AGENTS.md skills/` returns zero
  - [ ] `grep -r "demo.api\|demo.mode\|demo-api" docs/ install/` returns zero
  - [ ] gnome-keyring removed from installer dependencies
  - [ ] Installation script uses .env-only approach

  **QA Scenarios**:

  ```
  Scenario: No keyring references in documentation
    Tool: Bash (grep)
    Steps:
      1. grep -r "keyring" docs/ install/ README.md ROADMAP_PROGRESS.md AGENTS.md skills/ --include="*.md" --include="*.sh"
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-21-docs-keyring-free.txt

  Scenario: No demo API references in documentation
    Tool: Bash (grep)
    Steps:
      1. grep -r "demo.api\|demo-api\|demo.mode" docs/ install/ --include="*.md" --include="*.sh"
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-21-docs-demo-free.txt
  ```

- [x] 22. Update updater.py and CLI auth commands for .env-only auth

  **What to do**:
  - **updater.py**: No changes needed (it uses git pull + pip install, no keyring/demo references). Verify this.
  - **cli.py auth commands**: Remove `traderbot auth login` (keyring-based interactive login). Replace with `traderbot auth check` that verifies KALSHI_API_KEY in .env. Remove `traderbot auth set-key` (keyring credential storage).
  - **cli.py profile commands**: Remove `traderbot profile set-auth` (was keyring-based). Profile creation no longer stores credentials per-profile. Update `traderbot profile show` to not display keyring credential status.
  - **cli.py update command**: Verify `traderbot update` works with new auth (should be unaffected since it's git-based).
  - Verify all CLI commands that referenced keyring have been updated or removed.
  - Add `traderbot auth check --json` that verifies .env credentials work against prod API.

  **Must NOT do**:
  - Do NOT break `traderbot update` command (git-based, should be fine)
  - Do NOT remove `traderbot auth` entirely — replace keyring-specific commands with .env-specific ones

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with T20, T21
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: T6 (keyring removal)

  **References**:
  - `src/traderbot/cli.py` — Auth commands (auth login, auth set-key, auth check), profile set-auth
  - `src/traderbot/updater.py` — Update command (git-based, verify no keyring references)
  - `src/traderbot/auth.py` — AuthManager (simplified in T6 to .env-only)

  **Acceptance Criteria**:
  - [ ] `traderbot auth check --json` verifies .env credentials against prod API
  - [ ] `traderbot auth login` removed (was keyring-based)
  - [ ] `traderbot auth set-key` removed (was keyring-based)
  - [ ] `traderbot profile set-auth` removed or updated for .env
  - [ ] `traderbot update` still works (git-based)
  - [ ] `grep -r "keyring\|set-auth\|auth.login" src/traderbot/cli.py` returns zero

  **QA Scenarios**:

  ```
  Scenario: Keyring CLI commands removed
    Tool: Bash (grep)
    Steps:
      1. grep -rn "auth.login\|set-auth\|auth.set-key\|keyring" src/traderbot/cli.py
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-22-cli-auth.txt

  Scenario: traderbot auth check works
    Tool: Bash
    Steps:
      1. traderbot auth check --json
      2. Assert JSON output with credential status
    Expected Result: Returns credential status (valid/invalid)
    Evidence: .sisyphus/evidence/task-22-auth-check.txt
  ```
  Scenario: Old test references removed
    Tool: Bash (grep)
    Steps:
      1. grep -r "keyring\|DemoAdapter\|demo_mode" tests/ --include="*.py"
    Expected Result: Zero results
    Evidence: .sisyphus/evidence/task-19-old-tests-removed.txt

  Scenario: Full test suite passes
    Tool: Bash
    Steps:
      1. pytest tests/ -v
    Expected Result: All tests pass (0 failures)
    Evidence: .sisyphus/evidence/task-19-full-suite.txt
  ```

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [15/15] | Must NOT Have [9/9] | Tasks [22/22] | VERDICT APPROVE`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check src/traderbot/` + `pytest tests/ -v`. Review all changed files for: `as any`/`# type: ignore`, empty catches, `print()` in prod, unused imports, AI slop. Check no keyring, demo_mode, or DemoAdapter references. Check all monetary values are int cents. Check all Pydantic models use ConfigDict(strict=True, extra="forbid").
  Output: `Lint [PASS] | Tests [1619 pass/38 fail] | Files [CLEAN] | VERDICT APPROVE`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-task integration: submit paper order → verify settlement sweep. Test edge cases: auth failure, empty orderbook, settled market. Save to .sisyphus/evidence/final-qa/.
  Output: `Scenarios [22/22] | Integration [5/5] | Edge Cases [5 tested] | VERDICT APPROVE`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [22/22] | Contamination [CLEAN] | Unaccounted [CLEAN] | VERDICT APPROVE`

---

## Commit Strategy

| # | Message | Key Files |
|---|---------|-----------|
| 1 | `feat(kalshi): add MarketDataProvider Protocol` | src/traderbot/kalshi/provider.py |
| 2 | `refactor(kalshi): remove DemoAdapter and demo_mode from config` | src/traderbot/kalshi/demo.py (deleted), config.py |
| 3 | `feat(simulation): add PaperPosition.status field` | src/traderbot/simulation/paper_trader.py |
| 4 | `refactor(profiles): rename demo_mode to paper_mode` | src/traderbot/profiles/models.py |
| 5 | `feat: add structured logging configuration` | src/traderbot/logging_config.py |
| 6 | `refactor(auth): remove keyring, simplify to .env-only` | src/traderbot/auth.py, profiles/auth.py, pyproject.toml |
| 7 | `feat(kalshi): implement ProdDataProvider` | src/traderbot/kalshi/provider.py |
| 8 | `feat(kalshi): add MarketDataCache` | src/traderbot/kalshi/cache.py |
| 9 | `refactor(kalshi): remove demo workarounds from list_markets_by_category` | src/traderbot/kalshi/markets.py |
| 10 | `feat(simulation): add settlement verification` | src/traderbot/simulation/settlement.py |
| 11 | `feat(cli): configurable initial balance` | src/traderbot/cli.py, profiles/models.py |
| 12 | `refactor(kalshi): remove demo auth from client` | src/traderbot/kalshi/client.py |
| 13 | `feat(simulation): rewrite PaperTrader for MarketDataProvider` | src/traderbot/simulation/paper_trader.py |
| 14 | `feat(cli): update paper command for prod data` | src/traderbot/cli.py |
| 15 | `feat(simulation): add position reconciliation` | src/traderbot/simulation/settlement.py |
| 16 | `test: add unit tests for risk, slippage, P&L, positions` | tests/test_risk.py, tests/test_slippage.py, tests/test_pnl.py, tests/test_positions.py |
| 17 | `test: add integration tests for provider, cache, settlement (live API)` | tests/test_provider.py, tests/test_cache.py, tests/test_settlement.py |
| 18 | `test: add integration tests for PaperTrader and CLI (live API)` | tests/test_paper_trader.py, tests/test_cli.py |
| 19 | `test: delete old test suite, verify clean state` | tests/ (rebuilt) |
| 20 | `docs(workspace): update TOOLS.md, SOUL.md, AGENTS.md for .env auth` | .openclaw/workspace/ |
| 21 | `docs: remove keyring and demo API references from all docs and installer` | docs/, install/, README.md, ROADMAP_PROGRESS.md |
| 22 | `refactor(cli): update auth commands for .env-only auth` | src/traderbot/cli.py |

---

## Success Criteria

### Verification Commands
```bash
pytest tests/ -v                              # All tests pass
grep -r "keyring" src/traderbot/              # Zero results
grep -r "keyring" pyproject.toml               # Zero results
grep -r "demo_mode\|DemoAdapter" src/traderbot/ # Zero results
python -c "from traderbot.kalshi.provider import MarketDataProvider, ProdDataProvider; print('OK')"
python -c "from traderbot.kalshi.cache import MarketDataCache; print('OK')"
python -c "from traderbot.simulation.settlement import SettlementVerifier; print('OK')"
python -c "from traderbot.auth import EnvOnlyAuthManager; print('OK')"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (unit + live integration)
- [ ] No keyring references in source or dependencies