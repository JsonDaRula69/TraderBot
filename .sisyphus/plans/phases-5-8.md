# TraderBot Phases 5-8 Implementation Plan

## TL;DR

> **Quick Summary**: Implement Phases 5-8 of TraderBot sequentially — Simulation Engine → Decision Logging & Self-Learning → News & Sentiment Pipeline → Adaptation Engine & Full Autonomy. Each phase gets its own minor version milestone (v0.05.00 through v0.08.00) with patch bumps on every commit.
>
> **Deliverables**:
> - Phase 5: `simulation/` module (engine, data_loader, paper_trader, performance, profiles) + bootstrap CLI + CLI commands
> - Phase 6: `db/learnings.py`, `db/vectors.py`, WAL protocol, pattern promotion, FEATURE_REQUESTS.md
> - Phase 7: `news/` module (sources, classifier, sentiment_scorer, impact_assessor, embeddings) + ChromaDB + AnalysisRegistry
> - Phase 8: `simulation/adaptation.py`, heartbeat system, three-loop OpenClaw cron integration
>
> **Estimated Effort**: Large (4 phases, ~25+ new files, ~19+ test files, 41 tasks)
> **Parallel Execution**: NO — phases execute sequentially (Phase 5 → 6 → 7 → 8)
> **Critical Path**: Task 0 (docs) → Phase 5 → Phase 6 → Phase 7 → Phase 8 (each blocks the next; Task 0 blocks ALL)
> **NOTE**: Starting version is v0.04.10 (check `cat VERSION`). Task 0 bumps to v0.04.11. Phase milestones: v0.05.00 → v0.06.00 → v0.07.00 → v0.08.00
>
> **Research-Backed Enhancements** (from production implementation analysis):
> - **Bootstrap calibration**: Per-horizon calibration fits (cf. MarketRegimeNet's temperature scaling via LBFGS)
> - **Multi-agent simulation**: StrategyProfile with per-profile circuit breakers (cf. elastifund's kill rules)
> - **Feature requests**: Capability gap logging with recurrence-based promotion (cf. elastifund's self-improving OS)
> - **Category analysis**: Category-specific risk params and evidence thresholds (cf. Polymarket bot's category P&L breakdown)
> - **Future data sources** (Phase 9+, NOT in this plan): SharpAPI/BetStack (sports), FRED/BLS (economics), NWS/OpenWeatherMap (weather)

---

## Context

### Original Request
Implement Phases 5-8 of the TraderBot product roadmap. Phases must execute one at a time. Must adhere to git versioning guidelines. Must not begin work on future expansion (post-Phase 8).

### Interview Summary
**Key Discussions**:
- User confirmed sequential phase execution (5→6→7→8)
- Git versioning: patch bump every commit, minor bump at phase milestones
- No future expansion work allowed

**Research Findings**:
- `kalshi/history.py` supports `after`/`before` date-range queries and `cursor` pagination — sufficient for backtesting
- `kalshi/demo.py` uses `DemoAdapter` that produces services against demo API — paper trader should compose with this, not duplicate
- CLI already has stub commands for `backtest`, `paper`, `compare`, `performance`, `news`, `sentiment`, `heartbeat`, `learnings`
- `db/decisions.py` has full CRUD with SQLite — existing schema supports Phase 6 extensions
- `.openclaw/workspace/` already has SESSION-STATE.md, HEARTBEAT.md, AGENTS.md, USER.md, .learnings/
- Current version: v0.04.10, 445 tests, 99% coverage
- Pydantic pattern: `model_config = ConfigDict(strict=True, extra="forbid")` on every model
- Monetary values always `int` cents with `Field(ge=0)`
- `risk/limits.py` uses `MappingProxyType` (Python immutable) — HARD_LIMITS cannot be modified at runtime
- `analysis/indicators.py` throws ValueError on empty price lists — bootstrap must warm up indicators
- `docs/self-learning.md:93` already defines `FEATURE_REQUESTS.md` but has no implementation
- No category abstraction exists in analysis/ — all indicators are category-agnostic
- **Production implementation patterns** (from research):
  - Polymarket AI Bot: Category-specific risk params (sports: 6% max spread, politics: 12%), evidence quality thresholds per category (tech: 0.7, sports: 0.55), domain authority scoring
  - Elastifund: Self-improving OS with automated kill rules, Platt scaling for calibration (Brier score 0.2134), semantic decay guardrails
  - MarketRegimeNet: Temperature calibration via LBFGS, per-horizon calibration fits, Kelly Criterion with calibrated probabilities
  - Quant Backtest Framework: Walk-forward validation with GO/NO-GO gates (Sharpe ≥1.0, Win Rate ≥45%, Max DD ≤-15%), Monte Carlo permutation tests
  - Recommended free-tier data sources: SharpAPI (17k req/day sports), FRED API (economics, 2000 req/day), NWS API (weather, unlimited), Polymarket/Metaculus APIs (politics)

### Metis Review
**Identified Gaps** (addressed):
- ChromaDB hosting: Defaulting to local file-based (`.chroma/` directory)
- Voyage API key: Optional with graceful degradation
- Pattern promotion: Human-review-gated notification, NOT auto-edit of AGENTS.md
- WAL format: Markdown in SESSION-STATE.md (matches existing workspace pattern)
- Scope boundaries locked: Binary YES/NO markets only, no multi-leg/options; news sources limited to NewsAPI+Reddit+Twitter; no real-time streaming

---

## Work Objectives

### Core Objective
Implement the remaining 4 phases of TraderBot sequentially, delivering a complete autonomous prediction market trading toolkit with backtesting, self-learning, news/sentiment analysis, and adaptive parameter updating.

### Concrete Deliverables
- `src/traderbot/simulation/` — 4 modules (engine, data_loader, paper_trader, performance)
- `src/traderbot/db/learnings.py` — Pattern tracking with recurrence counts
- `src/traderbot/db/vectors.py` — ChromaDB interface for embedding storage/retrieval
- WAL protocol integration into existing trade flow
- `src/traderbot/news/` — 5 modules (sources, classifier, sentiment_scorer, impact_assessor, embeddings)
- `src/traderbot/simulation/adaptation.py` — Bayesian parameter updating
- Heartbeat CLI command implementation
- Three-loop cron definitions for OpenClaw
- Updated CLI with all command implementations (replacing stubs)
- ~15+ test files maintaining 99% coverage

### Definition of Done
- [ ] `traderbot backtest` produces valid performance metrics from historical data
- [ ] `traderbot paper` executes against demo API with realistic fills
- [ ] `traderbot compare` produces side-by-side strategy comparison
- [ ] `traderbot learnings` shows pattern tracking with recurrence counts
- [ ] `traderbot news` returns relevant news for tracked markets
- [ ] `traderbot sentiment <ticker>` returns sentiment score with confidence
- [ ] `traderbot heartbeat` runs 6-hour self-review cycle
- [ ] All modules have ≥99% test coverage
- [ ] All Pydantic models use `ConfigDict(strict=True, extra="forbid")`
- [ ] All monetary values are `int` (cents)
- [ ] Version bumps: v0.05.00 → v0.06.00 → v0.07.00 → v0.08.00
- [ ] 0 ruff errors

### Must Have
- Docs updated FIRST before any implementation (docs are source of truth per AGENTS.md)
- `VERSION` file and `pyproject.toml` version MUST stay in sync at all times
- Sequential phase execution (5→6→7→8 per product-roadmap.md)
- Every commit increments patch version
- Phase completion bumps minor version
- Dependencies added to `pyproject.toml` BEFORE the task that needs them (feedparser in T10, chromadb in T10, vaderSentiment+textblob in T21, scipy in T26, keyring in T36)
- Risk module immutability preserved (never bypass or modify HARD_LIMITS)
- SQLite remains authoritative write store; ChromaDB is search index only
- VADER/TextBlob fast path works without VOYAGE_API_KEY
- Voyage API calls never block hot path (slow path only, 200-500ms)
- All Pydantic models use ConfigDict(strict=True, extra="forbid")
- All monetary values in cents as int (never float)
- Fail-safe defaults: on error, hold positions, don't trade
- Audit trail for every trade decision with full reasoning
- **`src/traderbot/__init__.py` uses lazy imports** — subpackages are NOT exported at top level. New packages (simulation/, news/, auth) follow the same pattern: each manages its own `__init__.py` exports independently. No task needed to update the top-level `__init__.py`.
- **New test fixtures**: Each task with a test file must create its own fixtures. Shared `conftest.py` only has Kalshi-specific fixtures (market data, orderbook, portfolio state). New modules add fixtures in their own test files or extend `conftest.py` within their task scope.

### Must NOT Have (Guardrails)
- **NO changes to docs/ after Task 0 without explicit human approval** — docs are the source of truth per AGENTS.md
- No modifications to risk/ module hard limits
- No float for monetary values anywhere
- No Voyage API calls on the hot path
- No auto-editing of AGENTS.md (pattern promotion is notification/logged only)
- No work beyond Phase 8 scope (no post-Phase-8 features)
- No multi-leg/options strategies (binary YES/NO only)
- No real-time news streaming (polling only)
- No news sources beyond NewsAPI, Reddit, Twitter
- No Twitter OAuth flow — Twitter stub always returns empty with WARNING when API key unset
- No ChromaDB as authoritative store (search index only)
- No reinforcement learning or evolutionary algorithms
- No external data source integrations beyond NewsAPI/Reddit/Twitter in Phases 5-8 (SharpAPI, FRED, NWS are Phase 9+ scope)
- No AI slop: excessive comments, over-abstraction, generic names

### Resolved Edge Cases (from Metis review)
- **DB migration**: All `init_table()` calls are idempotent (`CREATE TABLE IF NOT EXISTS`) — no separate migration command needed
- **ChromaDB version pin**: `chromadb>=0.4.22,<0.5.0` — pinned range to avoid API breakage (exact version in Task 10)
- **Strategy discovery**: Built-in presets (Conservative, Moderate, Aggressive) shipped with `simulation/profiles.py`; no agent-authored strategy code required
- **BacktestResult trade_count==0**: `win_rate`, `sharpe_ratio`, `brier_score`, `edge_capture` all return `None` when no trades executed (not division by zero)
- **Twitter/X stub**: Always returns empty list with WARNING log when `TWITTER_API_KEY` unset — no OAuth flow attempted
- **Bootstrap insufficient data**: Proceeds with partial data (< 30 days) and logs WARNING with date range used; never crashes
- **Pattern staleness**: `max_age_days=30` enforced in `db/learnings.py` — patterns older than 30 days not eligible for promotion
- **Indicator insufficient history**: SMA/EMA/RSI fallback to shorter period when data < required lookback (existing code already does `min(period, len(prices))`)
- **Signal weights validation**: `StrategyProfile` validates at least one non-zero weight in `signal_weights`
- **Bootstrap empty data**: Returns warning "insufficient data for calibration" with partial results; does NOT fail
- **WAL file access**: Single-agent only constraint — concurrent write attempts MUST log ERROR and reject; no file locking needed
- **Graceful degradation logging**: All fallback paths (Voyage, ChromaDB, news sources) MUST log WARNING-level messages when degrading
- **API credentials**: All external APIs (NewsAPI, Twitter, Reddit, Voyage) optional with graceful degradation; only Kalshi API required

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest with async support, conftest.py)
- **Automated tests**: YES (TDD) — each module gets test-first development
- **Framework**: pytest with pytest-asyncio, pytest-cov
- **If TDD**: Each task follows RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash (`pytest`) — run tests, assert coverage, check ruff
- **CLI commands**: Use Bash (`traderbot`) — invoke command, assert output
- **Integration**: Use Bash (`pytest -m integration`) — verify module integration
- **ChromaDB/Voyage**: Use Bash with `VOYAGE_API_KEY=""` — verify graceful degradation

---

## Execution Strategy

### Sequential Phase Execution

> Per the product-roadmap.md Implementation Principles: "Phase at a time. No parallel phase development."
> Tasks WITHIN a phase can be parallelized, but phases themselves are strictly sequential.

```
═══════════════════════════════════════════════════════════
 PRE-PHASE: Update docs/ with approved changes (v0.04.XX)
═══════════════════════════════════════════════════════════

Wave 0 (Before any implementation — docs source of truth update):
└── Task 0: Update all docs/ files with approved plan changes [deep]

═══════════════════════════════════════════════════════════
 PHASE 5: Simulation Engine (v0.04.10 → v0.05.00+)
═══════════════════════════════════════════════════════════

Wave 5A (Foundation — sequential, data loader first):
├── Task 1: Create simulation/ package + data_loader module [deep]
├── Task 2: Create simulation/engine.py — backtest engine [deep]
├── Task 3: Create simulation/__init__.py with BacktestResult models [quick]
│   (After Task 1: Task 36 can start in parallel with Task 2)
└── Task 36: Create credential management — `traderbot auth` CLI + keyring [deep]

Wave 5B (After Wave 5A — parallel):
├── Task 4: Create simulation/paper_trader.py [deep]
├── Task 5: Create simulation/performance.py [deep]
├── Task 6: Wire backtest/paper/performance CLI (basic) [deep]
└── Task 33: Create StrategyProfile + multi-profile backtesting [deep]

Wave 5B2 (After T33 + T6 — compare CLI):
└── Task 6b: Wire compare CLI command with profile support [deep]

Wave 5C (After Wave 5B2 — tests, bootstrap, integration, and OpenClaw setup):
├── Task 7: Integration tests for simulation pipeline [deep]
├── Task 32: Create `traderbot bootstrap` CLI command [deep]
└── Task 8: Phase 5 completion — version bump to v0.05.00 [quick]

Note: Task 37 (OpenClaw installer) is optional infrastructure — does NOT block Phase 5 completion

═══════════════════════════════════════════════════════════
 PHASE 6: Decision Logging & Self-Learning (v0.05.XX → v0.06.00+)
═══════════════════════════════════════════════════════════

Wave 6A (Foundation — can start after Phase 5 complete):
├── Task 9: Create db/learnings.py — pattern tracking [deep]
├── Task 10: Create db/vectors.py — ChromaDB interface [deep]
└── Task 11: Create simulation/adaptation.py — Pydantic models for priors [quick]

Wave 6B (After Wave 6A — parallel):
├── Task 12: Implement WAL protocol in trade flow [deep]
├── Task 13: Implement pattern promotion logic [deep]
├── Task 14: Wire learnings CLI command + heartbeat stub [deep]
└── Task 34: Implement FEATURE_REQUESTS.md flow in learning system [deep]

Wave 6C (After Wave 6B — integration):
├── Task 15: Integration tests for self-learning pipeline [deep]
└── Task 16: Phase 6 completion — version bump to v0.06.00 [quick]

═══════════════════════════════════════════════════════════
 PHASE 7: News & Sentiment Pipeline (v0.06.XX → v0.07.00+)
═══════════════════════════════════════════════════════════

Wave 7A (Foundation):
├── Task 17: Create news/ package + news/sources.py [deep]
├── Task 18: Create news/embeddings.py — Voyage AI client [deep]
├── Task 19: Create news Pydantic models + ChromaDB collections [quick]
└── Task 35: Create CategoryAnalyzer protocol + MarketCategory enum + AnalysisRegistry [deep]

Wave 7B (After Wave 7A — parallel):
├── Task 20: Create news/classifier.py [deep]
├── Task 21: Create news/sentiment_scorer.py [deep]
└── Task 22: Create news/impact_assessor.py [deep]

Wave 7C (After Wave 7B):
├── Task 23: Wire news + sentiment CLI commands [deep]
└── Task 24: Integration tests for news pipeline [deep]
└── Task 25: Phase 7 completion — version bump to v0.07.00 [quick]

═══════════════════════════════════════════════════════════
 PHASE 8: Adaptation Engine & Full Autonomy (v0.07.XX → v0.08.00+)
═════════════════════════════════════════════════════════════

Wave 8A (Bayesian adaptation):
├── Task 26: Implement simulation/adaptation.py — Bayesian engine [ultrabrain]
└── Task 27: Implement heartbeat self-review cycle [deep]

Wave 8B (After Wave 8A — three-loop system):
├── Task 28: Define OpenClaw three-loop cron architecture [deep]
└── Task 29: Update .openclaw/ workspace files for heartbeat [deep]

Wave 8C (After Wave 8B — integration):
├── Task 30: End-to-end integration tests across all phases [deep]
└── Task 31: Phase 8 completion — version bump to v0.08.00 [quick]

═══════════════════════════════════════════════════════════
 FINAL VERIFICATION
═══════════════════════════════════════════════════════════

Wave FINAL (After ALL phases — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real QA — run all tests, verify all CLI commands (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Blocked By | Blocks |
|------|-----------|--------|
| 0 | — | 1, 2, 3, 36, 37 |
| 1 | 0 | 2, 3, 4, 5, 6 |
| 36 | 0, 1 | 4, 5, 6, 17, 18 |
| 2 | 1 | 4, 5, 6 |
| 3 | 1 | 4, 5, 6 |
| 4 | 2, 36 | 6 |
| 5 | 2, 36 | 6 |
| 6 | 4, 5 | 6b |
| 6b | 6, 33 | 7 |
| 7 | 6b | 8 |
| 37 | 0 | — |
| 8 | 7 | 9 |
| 9 | 8 | 12, 14 |
| 10 | 8 | 12, 13 |
| 11 | 8 | 26 |
| 12 | 9, 10 | 14 |
| 13 | 10 | 14 |
| 14 | 12, 13 | 15 |
| 15 | 14 | 16 |
| 16 | 15 | 17 |
| 17 | 16 | 20, 23 |
| 18 | 16 | 20, 21, 22 |
| 19 | 16 | 20, 21, 22 |
| 20 | 17, 18, 19 | 23 |
| 21 | 18 | 23 |
| 22 | 18, 19 | 23 |
| 23 | 20, 21, 22 | 24 |
| 24 | 23 | 25 |
| 25 | 24 | 26 |
| 26 | 11, 25 | 27, 28 |
| 27 | 26 | 28, 29 |
| 28 | 27 | 29 |
| 29 | 27 | 30 |
| 30 | 28, 29 | 31 |
| 31 | 30 | F1-F4 |
| 32 | 6b, 7 | 8, 9 |
| 33 | 2, 3, 5 | 6b |
| 34 | 9 | 14 |
| 35 | 16 | 20, 23 |
| 36 | 0 | 4, 5, 6, 17, 18 |
| 37 | 0 | 8 |

### Agent Dispatch Summary

- **Pre-Phase Wave 0**: 1 task — T0 → `deep`
- **Phase 5 Wave 5A**: 4 tasks — T1 → `deep`, T2 → `deep`, T3 → `quick`, T36 → `deep`
- **Phase 5 Wave 5B**: 4 tasks — T4 → `deep`, T5 → `deep`, T6 → `deep`, T33 → `deep`
- **Phase 5 Wave 5B2**: 1 task — T6b → `deep`
- **Phase 5 Wave 5C**: 3 tasks — T7 → `deep`, T32 → `deep`, T8 → `quick`
- **Phase 5 (unblocked)**: T37 → `deep` (optional, can run anytime after T0)
- **Phase 6 Wave 6A**: 3 tasks — T9 → `deep`, T10 → `deep`, T11 → `quick`
- **Phase 6 Wave 6B**: 4 tasks — T12 → `deep`, T13 → `deep`, T14 → `deep`, T34 → `deep`
- **Phase 6 Wave 6C**: 2 tasks — T15 → `deep`, T16 → `quick`
- **Phase 7 Wave 7A**: 4 tasks — T17 → `deep`, T18 → `deep`, T19 → `quick`, T35 → `deep`
- **Phase 7 Wave 7B**: 3 tasks — T20 → `deep`, T21 → `deep`, T22 → `deep`
- **Phase 7 Wave 7C**: 3 tasks — T23 → `deep`, T24 → `deep`, T25 → `quick`
- **Phase 8 Wave 8A**: 2 tasks — T26 → `ultrabrain`, T27 → `deep`
- **Phase 8 Wave 8B**: 2 tasks — T28 → `deep`, T29 → `deep`
- **Phase 8 Wave 8C**: 2 tasks — T30 → `deep`, T31 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 0. Update all docs/ files with approved plan changes

  **What to do**:
  - Per `AGENTS.md`: "`docs/` is the authoritative source for architecture, API specs, risk design, and roadmap — NEVER edit files in `docs/` without explicit human approval". User has given explicit approval to update docs to reflect the approved plan changes.
  - Update `docs/simulation.md` with:
     - StrategyProfile model spec (name, risk_multiplier, signal_weights, category_focus)
     - Multi-profile backtesting section (BacktestEngine.run_profiles)
     - Preset profiles: Conservative (0.5x), Moderate (1.0x), Aggressive (0.8x)
     - **Explicit formula**: `effective_limit = risk_multiplier * HARD_LIMITS[key]` — profiles scale within limits, never override
    - Bootstrap calibration section (traderbot bootstrap command spec)
    - Warm-up period handling for indicators on insufficient data
  - Update `docs/self-learning.md` with:
    - FEATURE_REQUESTS.md flow detail (feature_request category, PENDING_REVIEW promotion, never auto-committed)
    - Capability gap logging pattern (recurrence-based promotion)
    - Pattern staleness constraint (max_age_days=30)
    - Graceful degradation logging requirement (WARNING level on all fallback paths)
  - Update `docs/news-sentiment.md` with:
    - MarketCategory enum definition (ECONOMICS, POLITICS, WEATHER, SPORTS, CULTURE, TECHNOLOGY, SCIENCE)
    - CategoryAnalyzer Protocol spec (analyze method, CategorySignals model)
    - AnalysisRegistry pattern (register, get, analyze dispatch)
    - Domain authority scoring per news source (for impact assessor)
    - Evidence quality thresholds per category
  - Update `docs/architecture.md` with:
    - StrategyProfile in simulation layer diagram
    - AnalysisRegistry in analysis layer diagram
    - MarketCategory enum in data model section
    - Bootstrap command in CLI interface section
    - FEATURE_REQUESTS.md in self-learning data flow
  - Update `docs/openclaw-integration.md` with:
    - Feature request capability gap in heartbeat loop
    - PENDING_REVIEW status in WAL promotion flow
  - Update `docs/product-roadmap.md` with:
    - Phase 5 additions: Bootstrap (T32), StrategyProfile (T33)
    - Phase 6 additions: FEATURE_REQUESTS.md (T34)
    - Phase 7 additions: AnalysisRegistry + MarketCategory (T35)
    - Future data sources for reference (Phase 9+): SharpAPI/BetStack, FRED/BLS, NWS/OpenWeatherMap
  - Update `docs/architecture.md` security section with:
    - Keyring-based credential management (OS Keychain/Secret Service/Credential Manager)
    - `traderbot auth` CLI command spec (login, set-key, list-keys, rotate)
    - Keyring fallback to `.env` with WARNING
    - SecretStr enforcement for all credential fields
  - Update `tests/TESTING_PROMPT.md` with new sections:
    - §2.11: Phase 5 (Simulation) test patterns — backtesting, paper trading, multi-profile comparison, bootstrap
    - §2.12: Phase 6 (Self-Learning) test patterns — learnings DB, WAL, pattern promotion, feature requests
    - §2.13: Phase 7 (News/Sentiment) test patterns — source aggregation, classifier, sentiment scoring, impact assessment, category registry
    - §2.14: Phase 8 (Adaptation) test patterns — Bayesian updates, guardrails, heartbeat, cron architecture
  - Create `.env.example` documenting all required environment variables:
    - KALSHI_API_KEY, KALSHI_API_SECRET, KALSHI_DEMO_MODE
    - VOYAGE_API_KEY (optional — graceful degradation without)
    - NEWSAPI_KEY (optional — graceful degradation without)
    - CHROMA_DB_PATH (default: .chroma/)
    - Add note: "Prefer `traderbot auth` for credential management. .env is fallback only."
   - Sync `pyproject.toml` version with `VERSION` file (currently pyproject.toml says `0.00.01`, must match VERSION which is `0.04.10`)
   - Increment patch version in VERSION file and pyproject.toml after docs update
   - Tag: `v0.04.11`
   - No code changes — docs only

  **Must NOT do**:
  - No code changes in `src/` — purely documentation updates
  - No changes to risk module docs without explicit human approval (current risk docs are fine)
  - No adding new docs files — only updating existing ones
  - No future data source integration specs beyond mentioning them as Phase 9+ reference

  **⚠️ CRITICAL GUARDRAIL**: After this task completes, NO other task in this plan may modify any file in `docs/` without explicit human approval. The `docs/` directory is the authoritative source of truth per AGENTS.md. All implementation tasks (T1-T35) must implement against the docs as updated by this task — they must NOT modify docs to match their implementation.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding the full plan to correctly update 6+ interrelated doc files without introducing inconsistency
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (must complete before any implementation starts — docs are source of truth)
  - **Parallel Group**: Wave 0 (sequential, before all other waves)
  - **Blocks**: ALL tasks (1-35, F1-F4)
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `docs/simulation.md` — Current simulation spec (needs StrategyProfile, bootstrap additions)
  - `docs/self-learning.md` — Current self-learning spec (needs FEATURE_REQUESTS.md flow, capability gap logging)
  - `docs/news-sentiment.md` — Current news spec (needs MarketCategory, CategoryAnalyzer, AnalysisRegistry)
  - `docs/architecture.md` — Current architecture diagram (needs new components in layer diagrams)
  - `docs/openclaw-integration.md` — Current OpenClaw spec (needs feature request in heartbeat)
  - `docs/product-roadmap.md` — Current roadmap (needs Phase 5-8 enhancement entries)
  - `tests/TESTING_PROMPT.md` — Needs Phase 5-8 test protocol sections (§2.11-2.14)
  - `.env.example` — Needs to be created documenting all required env vars

  **API/Type References**:
  - `.sisyphus/plans/phases-5-8.md` — This plan is the source of truth for what changes to document

  **WHY Each Reference Matters**:
  - Each doc file must be updated to reflect the new components BEFORE implementation begins
  - Per AGENTS.md: "When in doubt about intended behavior, consult `docs/` first" — docs must be ahead of code
  - Executors will READ these docs as their primary reference during implementation

  **Acceptance Criteria**:

  - [ ] `docs/simulation.md` includes StrategyProfile, multi-profile backtesting, bootstrap calibration
  - [ ] `docs/self-learning.md` includes FEATURE_REQUESTS.md flow, capability gap logging, staleness constraint, degradation logging
  - [ ] `docs/news-sentiment.md` includes MarketCategory enum, CategoryAnalyzer Protocol, AnalysisRegistry, domain authority scoring
  - [ ] `docs/architecture.md` updated with new components in layer diagrams
  - [ ] `docs/openclaw-integration.md` includes feature request in heartbeat loop
  - [ ] `docs/product-roadmap.md` includes Phase 5-8 enhancements
  - [ ] No inconsistencies between docs (cross-references match)

  **QA Scenarios**:

  ```
  Scenario: All docs files updated consistently with plan changes
    Tool: Bash (grep)
    Steps:
      1. `grep -r "StrategyProfile" docs/` — Assert: found in simulation.md and architecture.md
      2. `grep -r "MarketCategory" docs/` — Assert: found in news-sentiment.md and architecture.md
      3. `grep -r "FEATURE_REQUESTS" docs/` — Assert: found in self-learning.md and openclaw-integration.md
      4. `grep -r "AnalysisRegistry" docs/` — Assert: found in news-sentiment.md and architecture.md
      5. `grep -r "bootstrap" docs/` — Assert: found in simulation.md
    Expected Result: All new concepts present in relevant docs, no missing references
    Evidence: .sisyphus/evidence/task-0-docs-grep.txt

  Scenario: No cross-reference inconsistencies between docs
    Tool: Bash (grep)
    Steps:
      1. `grep -r "CategoryAnalyzer" docs/` — verify Protocol definition and usage references match
      2. `grep -r "risk_multiplier" docs/` — verify StrategyProfile spec consistent across files
      3. `grep -r "PENDING_REVIEW" docs/` — verify feature request flow documented consistently
    Expected Result: Cross-references consistent, no contradictions
    Evidence: .sisyphus/evidence/task-0-docs-consistency.txt

  Scenario: TESTING_PROMPT.md has Phase 5-8 test protocol sections
    Tool: Bash (grep)
    Steps:
      1. `grep "2.11" tests/TESTING_PROMPT.md` — Assert: Phase 5 simulation test patterns section exists
      2. `grep "2.12" tests/TESTING_PROMPT.md` — Assert: Phase 6 self-learning test patterns section exists
      3. `grep "2.13" tests/TESTING_PROMPT.md` — Assert: Phase 7 news/sentiment test patterns section exists
      4. `grep "2.14" tests/TESTING_PROMPT.md` — Assert: Phase 8 adaptation test patterns section exists
    Expected Result: All four new testing protocol sections present in TESTING_PROMPT.md
    Evidence: .sisyphus/evidence/task-0-testing-prompt.txt

   Scenario: .env.example documents all required and optional environment variables
     Tool: Bash (grep)
     Steps:
       1. `grep "KALSHI_API_KEY" .env.example` — Assert: required key documented
       2. `grep "VOYAGE_API_KEY" .env.example` — Assert: optional key documented with graceful degradation note
       3. `grep "NEWSAPI_KEY" .env.example` — Assert: optional key documented
       4. `grep "traderbot auth" .env.example` — Assert: keyring preference note present
     Expected Result: All environment variables documented with keyring preference note
     Evidence: .sisyphus/evidence/task-0-env-example.txt

  Scenario: VERSION and pyproject.toml versions are synchronized
    Tool: Bash (grep + cat)
    Steps:
      1. `cat VERSION` → extract version string
      2. `grep '^version' pyproject.toml` → extract version
      3. Assert: both versions match exactly
    Expected Result: VERSION and pyproject.toml have identical version numbers
    Evidence: .sisyphus/evidence/task-0-version-sync.txt
  ```

  **Commit**: YES
  - Message: `docs: update all docs/ with approved plan changes for Phases 5-8`
  - Files: `docs/simulation.md`, `docs/self-learning.md`, `docs/news-sentiment.md`, `docs/architecture.md`, `docs/openclaw-integration.md`, `docs/product-roadmap.md`, `tests/TESTING_PROMPT.md`, `.env.example`, `VERSION`
  - Pre-commit: None (docs and config only, no code to test)

- [x] 1. Create simulation/ package + data_loader module

  **What to do**:
  - Create `src/traderbot/simulation/__init__.py` with module exports
  - Create `src/traderbot/simulation/data_loader.py` with `DataLoader` class
  - `DataLoader` fetches historical data from `kalshi/history.py` and caches to SQLite
  - Methods: `get_markets(start, end)`, `get_trades(ticker)`, `get_outcomes(tickers)`
  - SQLite cache tables: `cached_markets`, `cached_trades` with TTL freshness checks
  - Data quality checks: completeness, settlement consistency, liquidity thresholds
  - Write `tests/test_data_loader.py` with TDD approach (tests first)

  **Must NOT do**:
  - No external data feeds — Kalshi API only via `kalshi/history.py`
  - No in-memory-only caching — must persist to SQLite
  - No multi-leg/options data — binary YES/NO only

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Reason: Core module creation with SQLite caching and API integration patterns
  - **Skills Evaluated but Omitted**:
    - None needed for this task

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation for all other simulation modules)
  - **Parallel Group**: Wave 5A (sequential — data_loader first)
  - **Blocks**: Tasks 2, 3, 4, 5, 6
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/history.py:45-65` — `get_historical_trades` with `after`/`before`/`cursor` params for date-range queries
  - `src/traderbot/kalshi/history.py:67-80` — `get_settled_markets` with cursor pagination
  - `src/traderbot/db/decisions.py:35-54` — SQLite table creation pattern (`init_table`)
  - `src/traderbot/db/decisions.py:57-81` — SQLite insert/query pattern
  - `src/traderbot/kalshi/models.py` — `CutoffTimestamps`, `Market`, `Trade`, `MarketListResponse`, `TradeListResponse` models

  **API/Type References**:
  - `src/traderbot/kalshi/models.py` — All Pydantic models for market/trade data
  - `docs/simulation.md:86-121` — DataLoader spec: `get_markets()`, `get_trades()`, `get_outcomes()`, caching strategy, data quality checks

  **Test References**:
  - `tests/test_history.py` — History service test patterns (mocking KalshiClient)
  - `tests/test_decisions_db.py` — SQLite database test patterns (in-memory `:memory:`)

  **External References**:
  - `docs/kalshi.md:86-97` — Historical data API endpoints and pagination strategy

  **WHY Each Reference Matters**:
  - `history.py` is the API surface data_loader wraps — must use its `after`/`before`/`cursor` params
  - `db/decisions.py` shows the project's SQLite pattern: `init_table`, `insert`, `get`, `list_by_*` functions
  - `models.py` defines the Pydantic types that data_loader must consume/produce
  - Simulation docs specify caching strategy and data quality validation requirements

  **Acceptance Criteria**:

  **If TDD (tests enabled)**:
  - [ ] Test file created: `tests/test_data_loader.py`
  - [ ] `pytest tests/test_data_loader.py` → PASS (all tests green)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: DataLoader fetches and caches markets successfully
    Tool: Bash (pytest)
    Preconditions: Mock KalshiClient returning settled markets data
    Steps:
      1. Run `pytest tests/test_data_loader.py::test_get_markets_caches_results -v`
      2. Assert: test passes, markets fetched from API and stored in SQLite
      3. Run `pytest tests/test_data_loader.py::test_get_markets_uses_cache -v`
      4. Assert: second call returns data from cache without API call
    Expected Result: Both tests pass; data is cached to SQLite and reused
    Failure Indicators: Tests fail, data re-fetched from API on cache hit
    Evidence: .sisyphus/evidence/task-1-data-loader-cache.txt

  Scenario: DataLoader validates data quality and flags issues
    Tool: Bash (pytest)
    Preconditions: Mock returning markets with gaps or low liquidity
    Steps:
      1. Run `pytest tests/test_data_loader.py::test_quality_check_flags_low_liquidity -v`
      2. Run `pytest tests/test_data_loader.py::test_quality_check_flags_incomplete_trades -v`
      3. Assert: quality issues are reported in results
    Expected Result: Tests pass; quality flags present on problematic data
    Failure Indicators: Quality checks not performed or silently ignored
    Evidence: .sisyphus/evidence/task-1-data-loader-quality.txt
  ```

  **Commit**: YES (groups with Phase 5)
  - Message: `feat(simulation): add DataLoader with SQLite caching`
  - Files: `src/traderbot/simulation/__init__.py`, `src/traderbot/simulation/data_loader.py`, `tests/test_data_loader.py`
  - Pre-commit: `pytest tests/test_data_loader.py -v`

- [x] 2. Create simulation/engine.py — backtest engine

  **What to do**:
  - Create `src/traderbot/simulation/engine.py` with `BacktestEngine` class
  - Implement `Strategy` Protocol with `on_market_open`, `on_trade`, `on_settle` methods
  - Implement `Context` dataclass providing read-only portfolio, market data, sentiment, risk state
  - Implement `BacktestEngine.run()` that replays events chronologically through strategy
  - Enforce `risk/limits` checks during backtesting (same pipeline as live trading)
  - Slippage model: worst-case fill within spread (conservative)
  - Support `BacktestResult` Pydantic model with metrics: trades, PnL (cents as int), win rate, Sharpe, max drawdown
  - Write `tests/test_backtest_engine.py` with TDD approach

  **Must NOT do**:
  - No continuous price assumption — this is for binary YES/NO markets
  - No short selling support
  - No look-ahead bias — strict chronological replay, no peeking at settlement

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Reason: Core algorithmic module with event-driven architecture and risk integration
  - **Skills Evaluated but Omitted**:
    - None needed for this task

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 1 for data_loader)
  - **Parallel Group**: Wave 5A (after Task 1)
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `src/traderbot/risk/__init__.py` — `evaluate_trade()` pipeline: breaker → limits → sizing
  - `src/traderbot/risk/limits.py` — `HARD_LIMITS` and check functions
  - `src/traderbot/risk/sizing.py` — Kelly criterion position sizing
  - `src/traderbot/analysis/indicators.py` — SMA, EMA, RSI, Bollinger bands
  - `src/traderbot/analysis/odds.py` — Edge detection, implied probability

  **API/Type References**:
  - `src/traderbot/kalshi/models.py` — `Market`, `Trade`, `OrderBook`, `Order` models
  - `docs/simulation.md:56-72` — Strategy Protocol spec: `on_market_open`, `on_trade`, `on_settle`
  - `docs/simulation.md:74-83` — Context object spec: portfolio, market data, sentiment, risk state

  **Test References**:
  - `tests/test_risk_gate.py` — Pattern for testing risk integration
  - `tests/test_limits.py` — Pattern for testing hard limit enforcement
  - `tests/test_signals.py` — Pattern for testing signal generation

  **External References**:
  - `docs/simulation.md:175-181` — Backtesting limitations (survivorship bias, look-ahead, execution assumptions)

  **WHY Each Reference Matters**:
  - `risk/__init__.py` must be called in backtest engine — same constraints as live trading
  - `models.py` defines the Market/Trade types the engine processes as events
  - Simulation docs spec the Strategy Protocol and Context interface
  - Risk integration is non-negotiable — backtest must enforce same limits

  **Acceptance Criteria**:

  **If TDD**:
  - [ ] Test file created: `tests/test_backtest_engine.py`
  - [ ] `pytest tests/test_backtest_engine.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: BacktestEngine replays historical events chronologically
    Tool: Bash (pytest)
    Preconditions: Mock DataLoader with sample market/trade data, mock Strategy
    Steps:
      1. Run `pytest tests/test_backtest_engine.py::test_chronological_event_replay -v`
      2. Assert: each event timestamp ≥ previous event timestamp (monotonically non-decreasing)
      3. Run `pytest tests/test_backtest_engine.py::test_no_look_ahead_bias -v`
      4. Assert: strategy's `evaluate()` never receives `Market.settled_price` before market close_time
    Expected Result: Events replay in order, no access to future data
    Failure Indicators: Events processed out of order, or settlement data leaked early
    Evidence: .sisyphus/evidence/task-2-backtest-chronological.txt

  Scenario: Risk limits are enforced in backtest without bypass
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_backtest_engine.py::test_risk_limits_reject_oversized_position -v`
      2. Run `pytest tests/test_backtest_engine.py::test_risk_limits_reject_insufficient_edge -v`
      3. Assert: oversized trades rejected, audit trail shows rejection reason
    Expected Result: Risk module rejects trades violating limits, even in backtest
    Failure Indicators: Risk limits bypassed in backtest mode
    Evidence: .sisyphus/evidence/task-2-backtest-risk.txt

  Scenario: BacktestResult returns None for all metrics when trade_count == 0
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_backtest_engine.py::test_zero_trades_returns_none_metrics -v`
      2. Assert: win_rate is None, sharpe_ratio is None, brier_score is None, edge_capture is None
      3. Assert: trade_count is 0, total_pnl is 0
    Expected Result: All percentage/ratio metrics return None when no trades executed
    Failure Indicators: Division by zero, NaN values, or 0.0 instead of None
    Evidence: .sisyphus/evidence/task-2-backtest-zero-trades.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): add BacktestEngine with Strategy protocol and risk enforcement`
  - Files: `src/traderbot/simulation/engine.py`, `tests/test_backtest_engine.py`
  - Pre-commit: `pytest tests/test_backtest_engine.py -v`

- [x] 3. Create simulation models — BacktestResult, BacktestConfig, Strategy Protocol

  **What to do**:
  - Create `src/traderbot/simulation/models.py` with Pydantic models
  - `BacktestConfig`: start_date, end_date, strategy_name, initial_bankroll (int cents), slippage_model
  - `BacktestResult`: total_pnl (int cents), win_rate, trade_count, sharpe_ratio, max_drawdown, brier_score, edge_capture, fill_rate, trades (list), config
  - `Strategy` Protocol: `on_market_open`, `on_trade`, `on_settle` with proper type hints
  - `Context`: portfolio (read-only), market_data, sentiment, risk_state
  - `BacktestTrade`: ticker, direction, entry_price (int cents), exit_price (int cents), quantity, timestamp, pnl (int cents)
  - All models use `ConfigDict(strict=True, extra="forbid")`
  - All monetary values as `int` (cents)
  - Write `tests/test_simulation_models.py`

  **Must NOT do**:
  - No float for monetary values
  - No Pydantic models without ConfigDict(strict=True, extra="forbid")

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Skills Evaluated but Omitted**: None

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs Task 1 for pattern reference)
  - **Parallel Group**: Wave 5A
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/models.py` — Pydantic model pattern with ConfigDict, int cents, Field constraints
  - `src/traderbot/risk/circuit_breaker.py` — Enum + model pattern for state tracking
  - `docs/simulation.md:145-168` — Performance metrics spec: win rate, Sharpe, drawdown, Brier score, edge capture, fill rate

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Models enforce strict validation and int cents
    Tool: Bash (pytest)
    Preconditions: simulation.models module created
    Steps:
      1. Run `pytest tests/test_simulation_models.py -v`
      2. Assert: all models reject extra fields, float monetary values are rejected
      3. Run `pytest tests/test_simulation_models.py::test_backtest_result_rejects_float_pnl -v`
      4. Assert: ValidationError raised when pnl is float
    Expected Result: All models strictly validate, int cents enforced
    Failure Indicators: Models accept extra fields or float monetary values
    Evidence: .sisyphus/evidence/task-3-simulation-models.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): add backtest models with strict validation`
  - Files: `src/traderbot/simulation/models.py`, `tests/test_simulation_models.py`
  - Pre-commit: `pytest tests/test_simulation_models.py -v`

- [x] 4. Create simulation/paper_trader.py

  **What to do**:
  - Create `src/traderbot/simulation/paper_trader.py` with `PaperTrader` class
  - Compose with existing `kalshi/demo.py:DemoAdapter` — NOT duplicate it
  - `PaperTrader` uses `DemoAdapter` to execute against Kalshi demo API
  - Track simulated positions, fills, and P&L in SQLite (separate from live positions)
  - Log decisions to `db/decisions` with paper_trade marker
  - Implement position tracking: `get_portolio()`, `get_positions()`, `get_pnl()`
  - Slippage model: realistic fill simulation based on orderbook depth
  - Write `tests/test_paper_trader.py`

  **Must NOT do**:
  - Do NOT duplicate DemoAdapter — compose with it
  - Do NOT use real money API — only demo API
  - Do NOT merge paper positions with live positions in db/positions

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 5)
  - **Parallel Group**: Wave 5B
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3, 36

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/demo.py:10-50` — `DemoAdapter` class: factory producing demo API services, compose don't duplicate
  - `src/traderbot/kalshi/trading.py` — `TradingService` pattern for order placement
  - `src/traderbot/db/positions.py` — SQLite position tracking pattern
  - `src/traderbot/db/decisions.py` — Decision audit trail pattern

  **API/Type References**:
  - `src/traderbot/kalshi/models.py` — `Order`, `Fill`, `Position` models
  - `docs/simulation.md:123-144` — Paper trading spec: demo API execution, fill tracking, P&L

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: PaperTrader executes orders against demo API
    Tool: Bash (pytest)
    Preconditions: Mock DemoAdapter with simulated order fills
    Steps:
      1. Run `pytest tests/test_paper_trader.py::test_paper_trader_places_order -v`
      2. Assert: order placed via demo API, fill recorded in paper positions
      3. Run `pytest tests/test_paper_trader.py::test_paper_trader_tracks_pnl -v`
      4. Assert: P&L computed correctly in cents (int)
    Expected Result: Orders execute against demo API, positions and P&L tracked
    Failure Indicators: Paper positions mixed with live, or P&L as float
    Evidence: .sisyphus/evidence/task-4-paper-trader.txt

  Scenario: PaperTrader composes with DemoAdapter, not duplicating it
    Tool: Bash (grep)
    Steps:
      1. Run `grep -c "class DemoAdapter" src/traderbot/simulation/paper_trader.py`
      2. Assert: 0 (not redefined)
      3. Run `grep -c "from traderbot.kalshi.demo import" src/traderbot/simulation/paper_trader.py`
      4. Assert: 1 or more (imported and composed)
    Expected Result: PaperTrader imports DemoAdapter, doesn't redefine it
    Failure Indicators: DemoAdapter re-created inside paper_trader.py
    Evidence: .sisyphus/evidence/task-4-paper-trader-composition.txt

  Scenario: PaperTrader handles DemoAdapter failures gracefully
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_paper_trader.py::test_demo_adapter_timeout -v`
      2. Assert: PaperTrader logs error, does NOT crash, holds position
      3. Run `pytest tests/test_paper_trader.py::test_demo_adapter_5xx_error -v`
      4. Assert: PaperTrader handles HTTP 500 gracefully, retries per config
    Expected Result: PaperTrader degrades gracefully when DemoAdapter fails
    Evidence: .sisyphus/evidence/task-4-paper-trader-error.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): add PaperTrader composing with DemoAdapter`
  - Files: `src/traderbot/simulation/paper_trader.py`, `tests/test_paper_trader.py`
  - Pre-commit: `pytest tests/test_paper_trader.py -v`

- [x] 5. Create simulation/performance.py

  **What to do**:
  - Create `src/traderbot/simulation/performance.py` with performance metrics computation
  - Reuse metrics from `analysis/portfolio.py`: `win_rate`, `sharpe_ratio`, `max_drawdown`, `calmar_ratio`, `edge_realization`
  - Add prediction-market-specific metrics: `brier_score`, `fill_rate`, `edge_capture`
  - `compare_strategies()` function: side-by-side comparison of two BacktestResult objects
  - All monetary inputs/outputs as int cents
  - Write `tests/test_performance.py`

  **Must NOT do**:
  - No more than the core 5 metrics + prediction-market-specific metrics (Brier, fill rate, edge capture)
  - No strategy optimization — comparison only
  - No float for monetary values

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 4)
  - **Parallel Group**: Wave 5B
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3, 36

  **References**:

  **Pattern References**:
  - `src/traderbot/analysis/portfolio.py` — Existing `win_rate`, `sharpe_ratio`, `max_drawdown`, `calmar_ratio`, `edge_realization` functions to reuse
  - `src/traderbot/analysis/odds.py` — `implied_probability`, `detect_edge` patterns for edge capture

  **API/Type References**:
  - `src/traderbot/simulation/models.py` — `BacktestResult` model (from Task 3)
  - `docs/simulation.md:145-168` — Performance metrics spec and formulas

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Performance module computes correct metrics
    Tool: Bash (pytest)
    Preconditions: Sample BacktestResult with known values
    Steps:
      1. Run `pytest tests/test_performance.py::test_win_rate_calculation -v`
      2. Run `pytest tests/test_performance.py::test_sharpe_ratio -v`
      3. Run `pytest tests/test_performance.py::test_max_drawdown -v`
      4. Run `pytest tests/test_performance.py::test_brier_score -v`
      5. Assert: all computations mathematically correct
    Expected Result: All metrics produce correct results for known inputs
    Failure Indicators: Float monetary values, incorrect math
    Evidence: .sisyphus/evidence/task-5-performance.txt

  Scenario: compare_strategies produces side-by-side comparison
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_performance.py::test_compare_strategies -v`
      2. Assert: comparison includes all metrics for both strategies
    Expected Result: Comparison table with all metrics
    Evidence: .sisyphus/evidence/task-5-compare.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): add performance metrics and strategy comparison`
  - Files: `src/traderbot/simulation/performance.py`, `tests/test_performance.py`
  - Pre-commit: `pytest tests/test_performance.py -v`

- [x] 6. Wire backtest/paper/performance CLI commands (basic, no profile comparison)

  **What to do**:
  - Replace stub implementations in `src/traderbot/cli.py` for `backtest`, `paper`, `performance`
  - `backtest`: `--strategy`, `--from`, `--to`, `--bankroll` (default 100000 cents), `--db-path`
  - `paper`: `--strategy`, `--duration`, `--db-path`
  - `performance`: `--db-path`, `--from`, `--to`
  - Rich output formatting (tables for metrics, progress bars for backtest)
  - `--json` flag for machine-readable output on all commands
  - Write/update `tests/test_cli.py` with basic simulation command tests
  - **NOTE**: `compare` command is NOT included here — it's Task 6b, which depends on Task 33 (StrategyProfile)

  **Must NOT do**:
  - No `compare` CLI command (that's Task 6b)
  - No changes to existing CLI commands that work

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 4, 5)
  - **Parallel Group**: Wave 5B (after T4 and T5)
  - **Blocks**: Task 6b
  - **Blocked By**: Tasks 4, 5

  **References**:

  **Pattern References**:
  - `src/traderbot/cli.py:31-50` — Existing `scan` command pattern: Typer annotations, JSON output, Rich tables
  - `src/traderbot/cli.py:121-135` — `signals` command pattern for analysis integration

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: CLI backtest command produces metrics output
    Tool: Bash
    Steps:
      1. Run `traderbot backtest --strategy momentum --from 2025-01-01 --to 2025-03-01 --json`
      2. Assert: JSON output contains total_pnl, win_rate, sharpe_ratio, max_drawdown, brier_score
      3. Run `traderbot backtest --strategy momentum --from 2025-01-01 --to 2025-03-01`
      4. Assert: Rich table output visible, contains "Total P&L", "Win Rate", "Sharpe Ratio" columns
    Expected Result: Both JSON and Rich output work, all metrics present
    Failure Indicators: Command not found, stub message shown, missing metrics
    Evidence: .sisyphus/evidence/task-6a-cli-backtest.txt

  Scenario: CLI paper and performance commands show help and validate inputs
    Tool: Bash
    Steps:
      1. Run `traderbot paper --help`
      2. Assert: help text shows strategy and duration options
      3. Run `traderbot performance --help`
      4. Assert: help text shows db-path and date range options
    Expected Result: Help text works for all commands
    Evidence: .sisyphus/evidence/task-6a-cli-help.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): wire backtest, paper, performance CLI commands`
  - Files: `src/traderbot/cli.py`, `tests/test_cli.py`
  - Pre-commit: `pytest tests/test_cli.py -v`

- [x] 6b. Wire compare CLI command with StrategyProfile support

  **What to do**:
  - Add `compare` CLI command to `src/traderbot/cli.py`
  - `compare`: `--strategy-a`, `--strategy-b`, `--profile-a`, `--profile-b`, `--from`, `--to`
  - Support comparing two strategies OR two profiles on same historical data
  - Rich output formatting (side-by-side comparison table)
  - `--json` flag for machine-readable output
  - Write/update `tests/test_cli.py` for compare command

  **Must NOT do**:
  - No new Typer commands beyond `compare`
  - No changes to backtest/paper/performance commands (already done in T6)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 6, 33, 5)
  - **Parallel Group**: Wave 5B (after T33 completes)
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 6, 33

  **References**:

  **Pattern References**:
  - `src/traderbot/cli.py:31-50` — Existing `scan` command pattern: Typer annotations, Rich tables
  - `src/traderbot/simulation/profiles.py` — StrategyProfile (from Task 33)

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: CLI compare command produces side-by-side output
    Tool: Bash
    Steps:
      1. Run `traderbot compare --profile-a conservative --profile-b aggressive --from 2025-01-01 --to 2025-03-01 --json`
      2. Assert: JSON output contains results for both profiles
      3. Run `traderbot compare --strategy-a momentum --strategy-b mean_reversion --from 2025-01-01 --to 2025-03-01`
      4. Assert: Rich table shows side-by-side comparison
    Expected Result: Both profile and strategy comparison work
    Failure Indicators: Command not found, only one strategy compared
    Evidence: .sisyphus/evidence/task-6b-cli-compare.txt
  ```

  **Commit**: YES
  - Message: `feat(simulation): wire compare CLI command with profile support`
  - Files: `src/traderbot/cli.py`, `tests/test_cli.py`
  - Pre-commit: `pytest tests/test_cli.py -v`

- [x] 7. Integration tests for simulation pipeline

  **What to do**:
  - Create `tests/test_simulation_integration.py`
  - End-to-end test: DataLoader → BacktestEngine → Performance metrics
  - End-to-end test: DataLoader → PaperTrader → P&L tracking
  - Test risk module integration in backtest (limits enforced)
  - Test slippage model (worst-case fill within spread)
  - Test data quality checks flag invalid/incomplete data
  - Test compare_strategies with two different strategy results
  - Test StrategyProfile multi-profile backtesting
  - Run full test suite to verify no regressions

  **Must NOT do**:
  - No real API calls — all tests use mocks

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5C
  - **Blocks**: Task 8
  - **Blocked By**: Task 6b

  **References**:

  **Pattern References**:
  - `tests/conftest.py` — Shared pytest fixtures
  - `tests/test_risk_gate.py` — Pattern for testing risk integration end-to-end

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Full simulation pipeline produces valid results
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_simulation_integration.py -v`
      2. Assert: all integration tests pass
      3. Run `pytest --cov=traderbot/simulation --cov-report=term-missing`
      4. Assert: coverage ≥ 99%
    Expected Result: All integration tests pass, coverage ≥ 99%
    Failure Indicators: Tests fail, coverage below threshold
    Evidence: .sisyphus/evidence/task-7-integration.txt

  Scenario: No regressions in existing modules
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest --tb=short`
      2. Assert: 0 failures, all existing tests still pass
    Expected Result: Full test suite passes with 0 failures
    Evidence: .sisyphus/evidence/task-7-no-regressions.txt
  ```

  **Commit**: YES
  - Message: `test(simulation): add integration tests for full pipeline`
  - Files: `tests/test_simulation_integration.py`
  - Pre-commit: `pytest tests/test_simulation_integration.py -v`

- [x] 8. Phase 5 completion — version bump to v0.05.00

  **What to do**:
  - Sync `pyproject.toml` version with `VERSION` (verify match first)
  - Update `VERSION` file from `0.04.11` (post-T0) to `0.05.00`
  - Update `ROADMAP_PROGRESS.md` — mark Phase 5 components as ✅ Done
  - Update `pyproject.toml` version to `0.05.00`
  - Run full test suite to confirm everything passes
  - Git tag: `v0.05.00`

  **Must NOT do**:
  - No code changes beyond version/progress files
  - No starting Phase 6 work

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5C (final)
  - **Blocks**: Task 9 (Phase 6 starts)
  - **Blocked By**: Tasks 7, 32

  **References**:
  - `VERSION` — Current: `0.04.09`
  - `ROADMAP_PROGRESS.md:94-103` — Phase 5 section to update
  - `pyproject.toml:7` — `version = "0.00.01"` (note: may need sync with VERSION)

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Version bump is correct and all tests pass
    Tool: Bash
    Steps:
      1. Run `cat VERSION` — Assert: contains "0.05.00"
      2. Run `grep '^version' pyproject.toml` — Assert: matches "0.05.00"
      3. Run `pytest --tb=short -q` — Assert: 0 failures
      4. Run `ruff check src/traderbot` — Assert: 0 errors
      5. Git tag v0.05.00 exists
    Expected Result: VERSION=0.05.00, pyproject.toml version matches, all tests pass, 0 ruff errors
    Evidence: .sisyphus/evidence/task-8-version-bump.txt
  ```

  **Commit**: YES
  - Message: `chore: bump version to v0.05.00 (Phase 5 complete)`
  - Files: `VERSION`, `ROADMAP_PROGRESS.md`, `pyproject.toml`
  - Pre-commit: `pytest -q`

- [ ] 37. Create OpenClaw installer + registration script

  **What to do**:
  - Create `scripts/install_openclaw.sh` — detection + installation script
    - Detect if OpenClaw is installed: `which openclaw` or check for `.openclaw/` directory
    - If not installed: download and install OpenClaw CLI (prompt user for confirmation)
    - If installed: verify version compatibility
  - Create `scripts/register_tool.py` — TraderBot skill registration via gateway
    - Read `skills/traderbot/SKILL.md` for skill definition
    - Call OpenClaw gateway API to register the TraderBot tool:
      - `openclaw tool register --skill skills/traderbot/SKILL.md`
      - Verify registration: `openclaw tool list` shows traderbot
    - Create cron entries for three-loop architecture:
      - Decision Loop (every 5 min, market hours): `openclaw cron create` with `agentTurn` payload
      - Heartbeat Loop (every 6 hours): `openclaw cron create` with `agentTurn` payload
      - News/Sentiment (on event): `openclaw event register` with `systemEvent` payload
    - Verify each cron entry is active: `openclaw cron list`
  - Create `scripts/onboard.sh` — full onboarding script that runs install + register
    - Calls `install_openclaw.sh` first
    - Then calls `register_tool.py`
    - Verifies end-to-end: `openclaw tool test traderbot scan --limit 1`
    - Writes onboarding results to `.sisyphus/evidence/openclaw-onboarding.txt`
  - All scripts must be idempotent — safe to re-run without errors
  - Graceful degradation: if OpenClaw not available, logs warning but doesn't crash
  - Write `tests/test_openclaw_registration.py` with mocked gateway calls

  **Must NOT do**:
  - No modifying OpenClaw itself — only registration and configuration
  - No hardcoding API keys in scripts — use `traderbot auth` / keyring
  - No starting OpenClaw daemon — that's the user's responsibility
  - No changes to docs/ (docs already updated in Task 0)
  - No blocking Phase 5 completion — this is optional infrastructure, not a Phase 5 gate

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding OpenClaw gateway protocol, skill registration format, and idempotent scripting
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 7, Task 32, Task 8)
  - **Parallel Group**: Wave 5C (optional infrastructure — does NOT block Phase 5 completion)
  - **Blocks**: None (optional — can complete after Phase 5)
  - **Blocked By**: Task 0 (docs must be updated first)

  **References**:
  - `skills/traderbot/SKILL.md` — Current skill definition with cron architecture and trigger phrases
  - `.openclaw/workspace/AGENTS.md` — Agent operating rules
  - `.openclaw/workspace/SESSION-STATE.md` — WAL protocol and session state format
  - `.openclaw/workspace/HEARTBEAT.md` — Heartbeat output format
  - `docs/openclaw-integration.md` — OpenClaw integration spec (three-loop cron, WAL, workspace files)
  - `docs/architecture.md:7-63` — Three-loop system: Decision, Heartbeat, News/Sentiment

  **WHY Each Reference Matters**:
  - SKILL.md defines the exact format for tool registration (commands, triggers, env vars, cron payloads)
  - The installer must parse this file to register correctly via gateway
  - openclaw-integration.md defines the three-loop cron architecture that the registration creates
  - The gateway requires specific JSON payload formats — registration must match exactly

  **Acceptance Criteria**:

  **If TDD (tests enabled)**:
  - [ ] Test file created: `tests/test_openclaw_registration.py`
  - [ ] `pytest tests/test_openclaw_registration.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: Installer detects and registers OpenClaw tool correctly
    Tool: Bash
    Steps:
      1. Run `scripts/onboard.sh` — Assert: completes without errors
      2. Run `openclaw tool list` — Assert: traderbot appears in registered tools
      3. Run `openclaw cron list` — Assert: decision-loop, heartbeat-loop, news-sentiment entries exist
      4. Run `scripts/onboard.sh` again — Assert: idempotent, no errors on re-run
    Expected Result: OpenClaw tool registered, crons active, idempotent
    Evidence: .sisyphus/evidence/task-37-openclaw-onboard.txt

  Scenario: Registration degrades gracefully without OpenClaw
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_openclaw_registration.py::test_graceful_degradation_no_openclaw -v`
      2. Assert: script logs WARNING, doesn't crash, exits 0
    Expected Result: Graceful degradation when OpenClaw unavailable
    Evidence: .sisyphus/evidence/task-37-openclaw-degrade.txt

  Scenario: Cron payloads match SKILL.md format
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_openclaw_registration.py::test_cron_payload_format -v`
      2. Assert: decision-loop payload has sessionTarget "isolated" and kind "agentTurn"
      3. Assert: news-sentiment payload has kind "systemEvent"
    Expected Result: Cron payloads match OpenClaw spec exactly
    Evidence: .sisyphus/evidence/task-37-cron-payloads.txt
  ```

  **Commit**: YES
  - Message: `feat(infra): add OpenClaw installer and registration script with three-loop cron`
  - Files: `scripts/install_openclaw.sh`, `scripts/register_tool.py`, `scripts/onboard.sh`, `tests/test_openclaw_registration.py`
  - Pre-commit: `pytest tests/test_openclaw_registration.py -v`

---

- [x] 9. Create db/learnings.py — pattern tracking with recurrence counts

  **What to do**:
  - Create `src/traderbot/db/learnings.py` with pattern tracking CRUD
  - `DbLearning` Pydantic model: id, pattern_key, recurrence_count, priority, status, category, description, action, logged_at
  - `init_table()`, `insert()`, `get()`, `list_by_status()`, `list_by_category()`, `increment_recurrence()`, `promote()`
  - Pattern promotion: when `recurrence_count >= 3` → eligible for promotion (logged, NOT auto-edit of AGENTS.md)
  - Follow existing `db/decisions.py` pattern: SQLite with `init_table`, `insert`, `get`, `list_by_*`
  - All models use `ConfigDict(strict=True, extra="forbid")`
  - Write `tests/test_learnings_db.py`

  **Must NOT do**:
  - No auto-editing of AGENTS.md — pattern promotion is notification/logging only
  - No ChromaDB in this module (that's db/vectors.py)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 10, 11)
  - **Parallel Group**: Wave 6A
  - **Blocks**: Tasks 12, 13, 14
  - **Blocked By**: Task 8 (Phase 5 complete)

  **References**:

  **Pattern References**:
  - `src/traderbot/db/decisions.py:1-154` — Full pattern for SQLite module: `DbDecision` model, `init_table`, `insert`, `get`, `list_by_ticker`, `list_by_date_range`, `update_actual_result`
  - `docs/self-learning.md:89-111` — Learning entry format: Pattern-Key, Recurrence-Count, Priority, Status, Category

  **Test References**:
  - `tests/test_decisions_db.py` — SQLite database test patterns

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Learnings DB tracks patterns and increments recurrence
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_learnings_db.py::test_insert_and_get -v`
      2. Run `pytest tests/test_learnings_db.py::test_increment_recurrence -v`
      3. Run `pytest tests/test_learnings_db.py::test_promote_eligible_pattern -v`
      4. Assert: patterns inserted, recurrence incremented, promotion logged
    Expected Result: All CRUD operations work, recurrence tracking correct
    Evidence: .sisyphus/evidence/task-9-learnings-db.txt

  Scenario: Pattern promotion does NOT auto-edit AGENTS.md
    Tool: Bash (grep)
    Steps:
      1. Run `grep -rn "AGENTS.md" src/traderbot/db/learnings.py`
      2. Assert: no file writes to AGENTS.md in learnings.py
    Expected Result: learnings.py does not contain AGENTS.md file writes
    Evidence: .sisyphus/evidence/task-9-no-auto-edit.txt
  ```

  **Commit**: YES
  - Message: `feat(learning): add db/learnings with pattern tracking and recurrence`
  - Files: `src/traderbot/db/learnings.py`, `tests/test_learnings_db.py`
  - Pre-commit: `pytest tests/test_learnings_db.py -v`

- [x] 10. Create db/vectors.py — ChromaDB interface

  **What to do**:
  - Add `chromadb>=0.4.22,<0.5.0` to `pyproject.toml` dependencies (exact pin to avoid API breakage)
  - Add `feedparser>=6.0.0` to `pyproject.toml` dependencies (needed by Task 17 news sources — add now for integration testing)
  - Create `src/traderbot/db/vectors.py` with ChromaDB interface
  - Collections: `decision_embeddings` (voyage-4-large), `cluster_results`
  - `VectorStore` class: `init_collection`, `add_embedding`, `query_similar`, `delete_by_metadata`
  - Metadata schema: `decision_id`, `ticker`, `category`, `timestamp`, `outcome`
  - TTL support: configurable expiry (default 90 days)
  - Async support: embedding generation and querying non-blocking
  - Graceful degradation: when ChromaDB unavailable, return empty results (not error)
  - Local file-based ChromaDB: `.chroma/` directory with persistent client
  - Write `tests/test_vectors_db.py`

  **Must NOT do**:
  - No making ChromaDB the authoritative store — SQLite is authoritative
  - No blocking the hot path with ChromaDB operations
  - No Voyage API calls in this module — that's news/embeddings.py

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 11)
  - **Parallel Group**: Wave 6A
  - **Blocks**: Tasks 12, 13
  - **Blocked By**: Task 8

  **References**:

  **Pattern References**:
  - `src/traderbot/db/decisions.py` — SQLite pattern for `init_table`, `insert`, `get`
  - `docs/architecture.md:124-153` — Semantic layer: ChromaDB is search index only, SQLite authoritative
  - `docs/self-learning.md:152-171` — ChromaDB collections: `decision_embeddings` with `voyage-4-large`, `cluster_results`

  **External References**:
  - ChromaDB docs: persistent client, metadata filtering, async patterns, TTL

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: VectorStore adds and queries embeddings
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_vectors_db.py::test_add_and_query_embedding -v`
      2. Assert: embeddings stored and retrieved by similarity
      3. Run `pytest tests/test_vectors_db.py::test_metadata_filtering -v`
      4. Assert: query with ticker/category filters works
    Expected Result: Embeddings stored, queried by similarity and metadata
    Evidence: .sisyphus/evidence/task-10-vectors-db.txt

  Scenario: VectorStore degrades gracefully when unavailable
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_vectors_db.py::test_graceful_degradation -v`
      2. Assert: when ChromaDB fails, returns empty results (not exception)
    Expected Result: Graceful degradation, no crashes
    Evidence: .sisyphus/evidence/task-10-vectors-degrade.txt

  Scenario: VectorStore handles mid-query exceptions and TTL expiration
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_vectors_db.py::test_query_raises_exception -v`
      2. Assert: when ChromaDB client throws during query, returns empty results and logs WARNING
      3. Run `pytest tests/test_vectors_db.py::test_ttl_expiration -v`
      4. Assert: stale entries are excluded from results after TTL
    Expected Result: Exception and TTL edge cases handled correctly
    Evidence: .sisyphus/evidence/task-10-vectors-exceptions.txt
  ```

  **Commit**: YES
  - Message: `feat(learning): add ChromaDB vector store interface with graceful degradation`
  - Files: `src/traderbot/db/vectors.py`, `tests/test_vectors_db.py`, `pyproject.toml`
  - Pre-commit: `pytest tests/test_vectors_db.py -v`

- [x] 11. Create simulation/adaptation.py — Pydantic models for priors

  **What to do**:
  - Create `src/traderbot/simulation/adaptation.py` with Bayesian adaptation models
  - `StrategyPriors` Pydantic model: edge_threshold (Beta), signal_weights (Dirichlet), mean_reversion (Normal), momentum_decay (Exponential)
  - `AdaptationResult` model: parameter name, prior, posterior, observations, change_pct
  - `AdaptationConfig` model: bounds enforcement, min_sample (10), cooldown (4/day), reset_variance (0.01)
  - All models use `ConfigDict(strict=True, extra="forbid")`
  - Write `tests/test_adaptation_models.py`

  **Must NOT do**:
  - No Bayesian update logic yet — that's Task 26 (Phase 8)
  - No modifying risk module hard limits
  - No auto-applying adaptations — logged only

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 10)
  - **Parallel Group**: Wave 6A
  - **Blocks**: Task 26 (Phase 8)
  - **Blocked By**: Task 8

  **References**:
  - `docs/self-learning.md:28-69` — Adapted parameters table, prior distributions, update cycle
  - `docs/self-learning.md:73-81` — Guardrails: 20% max change, min 10 observations, cooldown, reset trigger

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Adaptation models validate correctly
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_adaptation_models.py -v`
      2. Assert: models accept valid data, reject extra fields, enforce int cents
    Expected Result: All model validation passes
    Evidence: .sisyphus/evidence/task-11-adaptation-models.txt
  ```

  **Commit**: YES
  - Message: `feat(adaptation): add Bayesian adaptation models and config`
  - Files: `src/traderbot/simulation/adaptation.py`, `tests/test_adaptation_models.py`
  - Pre-commit: `pytest tests/test_adaptation_models.py -v`

- [x] 12. Implement WAL protocol in trade flow

  **What to do**:
  - Create `src/traderbot/wal.py` with WAL (Write-Ahead Log) protocol
  - Before any trade execution: write intent to `SESSION-STATE.md` under `## Pending Actions`
  - WAL entries: timestamp, action (BUY/SELL), ticker, direction, quantity, price, reason, signal, risk checks, confidence, status
  - After execution: update status to COMPLETED/CANCELLED/EXPIRED
  - On crash recovery: scan SESSION-STATE.md for pending actions, reconcile with actual positions
  - Integrate WAL into existing `cli.py` trade command (before order placement)
  - Write `tests/test_wal.py`

  **Must NOT do**:
  - No modifying risk module to use WAL
  - No creating new CLI commands — integrate into existing `trade` command
  - No support for concurrent WAL writers — WAL is single-agent-only; concurrent writes MUST log ERROR and reject

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 13, 14 after 9 and 10)
  - **Parallel Group**: Wave 6B
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 9, 10

  **References**:
  - `docs/self-learning.md:193-231` — WAL Protocol spec: problem statement, solution, scanning rules
  - `docs/openclaw-integration.md:156-164` — WAL Protocol workspace integration
  - `src/traderbot/cli.py:136-200` — Existing `trade` command where WAL must integrate

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: WAL writes intent before trade execution
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_wal.py::test_wal_write_before_execution -v`
      2. Assert: SESSION-STATE.md contains pending action before trade executes
      3. Run `pytest tests/test_wal.py::test_wal_update_after_execution -v`
      4. Assert: status updated to COMPLETED after trade
    Expected Result: WAL writes before execution, updates after
    Evidence: .sisyphus/evidence/task-12-wal-protocol.txt

  Scenario: WAL crash recovery reconciles pending actions
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_wal.py::test_crash_recovery_pending_action -v`
      2. Assert: pending action detected, reconciled with positions
    Expected Result: Crash recovery works correctly
    Evidence: .sisyphus/evidence/task-12-wal-recovery.txt

  Scenario: WAL detects and rejects concurrent write access
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_wal.py::test_concurrent_write_rejected -v`
      2. Assert: second writer gets error or first writer's entry is preserved
      3. Assert: no silent data corruption from concurrent access
    Expected Result: Concurrent WAL access is rejected with clear error, not silently corrupted
    Evidence: .sisyphus/evidence/task-12-wal-concurrent.txt
  ```

  **Commit**: YES
  - Message: `feat(learning): add WAL protocol for trade execution safety`
  - Files: `src/traderbot/wal.py`, `tests/test_wal.py`, `src/traderbot/cli.py` (modified)
  - Pre-commit: `pytest tests/test_wal.py -v`

- [x] 13. Implement pattern promotion logic

  **What to do**:
  - Create `src/traderbot/learning.py` with pattern promotion engine
  - `scan_for_promotions()`: query db/learnings for entries with `recurrence_count >= 3`
  - `promote_learning()`: mark entry as `Status: promoted`, log to audit trail
  - Write promoted entries to `.openclaw/workspace/.learnings/LEARNINGS.md` (NOT auto-edit AGENTS.md)
  - Integrate with heartbeat pattern: every 6 hours, scan for eligible patterns
  - Write `tests/test_learning_promotion.py`

  **Must NOT do**:
  - No auto-editing AGENTS.md — promotion writes to LEARNINGS.md only
  - No modifying risk module

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 12, 14)
  - **Parallel Group**: Wave 6B
  - **Blocks**: Task 14
  - **Blocked By**: Task 10

  **References**:
  - `docs/self-learning.md:83-110` — Pattern promotion criteria: Recurrence-Count >= 3, across 2+ tasks, within 30 days
  - `docs/self-learning.md:115-128` — Learning entry format
  - `.openclaw/workspace/.learnings/` — Target directory for promoted entries

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Pattern promotion identifies eligible learnings
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_learning_promotion.py::test_scan_for_promotions -v`
      2. Assert: entries with recurrence_count >= 3 identified
      3. Run `pytest tests/test_learning_promotion.py::test_promote_writes_to_learnings_md -v`
      4. Assert: promoted entry written to LEARNINGS.md
    Expected Result: Eligible patterns identified and promoted correctly
    Evidence: .sisyphus/evidence/task-13-promotion.txt

  Scenario: Pattern promotion does NOT auto-edit AGENTS.md
    Tool: Bash (grep)
    Steps:
      1. Run `grep -rn "AGENTS.md" src/traderbot/learning.py`
      2. Assert: no AGENTS.md file write operations
    Expected Result: No AGENTS.md writes in learning.py
    Evidence: .sisyphus/evidence/task-13-no-agents-edit.txt
  ```

  **Commit**: YES
  - Message: `feat(learning): add pattern promotion engine with LEARNINGS.md output`
  - Files: `src/traderbot/learning.py`, `tests/test_learning_promotion.py`
  - Pre-commit: `pytest tests/test_learning_promotion.py -v`

- [x] 14. Wire learnings CLI command + heartbeat stub update

  **What to do**:
  - Replace `learnings` CLI stub with real implementation in `cli.py`
  - `traderbot learnings` — list, search, promote patterns
  - `traderbot learnings --status active` — filter by status
  - `traderbot learnings --category risk` — filter by category
  - `traderbot learnings --promote <pattern-key>` — manually trigger promotion
  - Update `heartbeat` CLI command to reference learning promotion (full implementation in Phase 8)
  - Rich output formatting (tables for learnings, status badges)
  - Write/update `tests/test_cli.py` for learnings command

  **Must NOT do**:
  - No full heartbeat implementation (Phase 8)
  - No modifying existing working CLI commands

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 12 and 13)
  - **Parallel Group**: Wave 6B
  - **Blocks**: Task 15
  - **Blocked By**: Tasks 12, 13

  **References**:
  - `src/traderbot/cli.py:389-394` — Current `learnings` stub
  - `src/traderbot/cli.py:297-300` — Current `heartbeat` stub
  - `src/traderbot/cli.py:31-50` — `scan` command pattern: Rich tables, `--json` flag

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: learnings CLI command shows and filters patterns
    Tool: Bash
    Steps:
      1. Run `traderbot learnings --help` — Assert: shows filter options
      2. Run `traderbot learnings --json` — Assert: JSON output with pattern list
      3. Run `traderbot learnings --status active --json` — Assert: JSON output contains only entries with `"status": "active"`, no `"status": "promoted"` entries
    Expected Result: CLI command works with filters and JSON output
    Evidence: .sisyphus/evidence/task-14-cli-learnings.txt
  ```

  **Commit**: YES
  - Message: `feat(learning): wire learnings CLI command with filtering and promotion`
  - Files: `src/traderbot/cli.py`, `tests/test_cli.py`
  - Pre-commit: `pytest tests/test_cli.py -v`

- [x] 15. Integration tests for self-learning pipeline

  **What to do**:
  - Create `tests/test_learning_integration.py`
  - End-to-end: insert learning → increment recurrence → scan → promote → verify LEARNINGS.md
  - End-to-end: make trade → WAL writes intent → execute → update WAL status
  - Test ChromaDB integration: add decision embedding → query similar → verify results
  - Test graceful degradation: ChromaDB unavailable → fallback to SQL search
  - Run full test suite to verify no regressions

  **Must NOT do**:
  - No real API calls in tests

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6C
  - **Blocks**: Task 16
  - **Blocked By**: Task 14

  **References**:
  - `tests/conftest.py` — Shared fixtures
  - `tests/test_risk_gate.py` — Integration test patterns

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Full self-learning pipeline works end-to-end
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_learning_integration.py -v`
      2. Assert: all integration tests pass
      3. Run `pytest --cov=traderbot --cov-report=term-missing -q`
      4. Assert: coverage ≥ 99%, 0 failures
    Expected Result: Full pipeline works, no regressions
    Evidence: .sisyphus/evidence/task-15-learning-integration.txt
  ```

  **Commit**: YES
  - Message: `test(learning): add integration tests for self-learning pipeline`
  - Files: `tests/test_learning_integration.py`
  - Pre-commit: `pytest tests/test_learning_integration.py -v`

- [x] 16. Phase 6 completion — version bump to v0.06.00

  **What to do**:
  - Update `VERSION` from `0.05.XX` to `0.06.00`
  - Update `ROADMAP_PROGRESS.md` — mark Phase 6 components as ✅ Done
  - Run full test suite, verify 0 ruff errors
  - Git tag: `v0.06.00`

  **Must NOT do**:
  - No code changes beyond version/progress files
  - No starting Phase 7 work

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Final task of Phase 6**
  - **Blocks**: Task 17 (Phase 7 starts)
  - **Blocked By**: Task 15

  **References**:
  - `VERSION`, `ROADMAP_PROGRESS.md`, `pyproject.toml`

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Version bump correct, all tests pass
    Tool: Bash
    Steps:
      1. `cat VERSION` → Assert: "0.06.00"
      2. `pytest -q` → Assert: 0 failures
      3. `ruff check src/traderbot` → Assert: 0 errors
      4. Git tag v0.06.00 exists
    Expected Result: VERSION=0.06.00, all tests pass, 0 ruff errors
    Evidence: .sisyphus/evidence/task-16-version-bump.txt
  ```

  **Commit**: YES
  - Message: `chore: bump version to v0.06.00 (Phase 6 complete)`
  - Files: `VERSION`, `ROADMAP_PROGRESS.md`, `pyproject.toml`
  - Pre-commit: `pytest -q`

- [x] 17. Create news/ package + news/sources.py

  **What to do**:
  - Create `src/traderbot/news/__init__.py` with module exports
  - Create `src/traderbot/news/sources.py` with unified news source interface
  - `NewsSource` enum: NEWSAPI, TWITTER, REDDIT
  - `NewsItem` Pydantic model: id, title, body, source, url, published_at, ticker_refs, category
  - `NewsAggregator` class: `fetch_recent(source, limit)`, `fetch_all(limit)` → aggregates from all sources
  - NewsAPI integration: HTTP via `httpx`, proper rate limiting, structured article parsing
  - Reddit RSS integration: `feedparser` or raw XML parsing
  - Twitter/X integration: stub with graceful degradation (API tier access varies)
  - Source priority: Twitter (fastest) → NewsAPI → Reddit (deepest)
  - Graceful degradation: each source can fail without crashing the pipeline
  - Add `feedparser` to `pyproject.toml` dependencies
  - Write `tests/test_news_sources.py`

  **Must NOT do**: No real API calls in tests. No WebSocket news streams. No sources beyond NewsAPI/Reddit/Twitter. Twitter stub always returns empty list with WARNING log when TWITTER_API_KEY unset — no OAuth flow, no 429 retry, no partial results.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7A (parallel with T18, T19). **Blocks**: T20, T23. **Blocked By**: T16, T36.

  **References**: `docs/news-sentiment.md:87-124` (source specs), `src/traderbot/kalshi/client.py` (HTTP pattern)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_news_sources.py` → PASS
  - [ ] NewsAggregator fetches from each source independently
  - [ ] Graceful degradation when one source is down
  - [ ] All Pydantic models use `ConfigDict(strict=True, extra="forbid")`

  **QA Scenarios**:
  ```
  Scenario: NewsAggregator fetches from multiple sources with graceful degradation
    Tool: Bash (pytest)
    Steps: Run `pytest tests/test_news_sources.py -v`
    Expected Result: All tests pass; sources degrade gracefully
    Evidence: .sisyphus/evidence/task-17-news-sources.txt

  Scenario: News sources handle malformed responses and rate limits
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_news_sources.py::test_newsapi_non_json_response -v`
      2. Assert: NewsAPI returning non-JSON body logged as WARNING, returns empty list
      3. Run `pytest tests/test_news_sources.py::test_newsapi_rate_limit_429 -v`
      4. Assert: HTTP 429 triggers retry with backoff, eventually degrades gracefully
      5. Run `pytest tests/test_news_sources.py::test_feedparser_failure -v`
      6. Assert: Reddit RSS parse failure logged, doesn't crash aggregator
    Expected Result: All malformed/degraded responses handled without crashes
    Evidence: .sisyphus/evidence/task-17-news-error.txt
  ```

  **Commit**: YES - Message: `feat(news): add unified news source aggregator`
  Files: `src/traderbot/news/__init__.py`, `src/traderbot/news/sources.py`, `tests/test_news_sources.py`, `pyproject.toml`

- [x] 18. Create news/embeddings.py — Voyage AI client

  **What to do**:
  - Create `src/traderbot/news/embeddings.py` with Voyage AI client
  - Add `voyageai` to `pyproject.toml` dependencies
  - `VoyageClient` class: lazy initialization, graceful degradation without `VOYAGE_API_KEY`
  - `embed(text, model="voyage-finance-2")` → list[float], `embed_batch()`, `rerank()`
  - Rate limiting: max 60 calls/min, queue overflow falls back to fast path
  - Timeouts: embed 500ms, rerank 300ms (non-blocking)
  - All methods return None/empty when VOYAGE_API_KEY unset
  - **Batch API support for historical backfill**: `embed_batch_submit(texts, model="voyage-finance-2")` → job_id
    - Uses Voyage Files API to upload batch request, returns job ID
    - 33% cost discount for non-urgent embeddings (historical archive backfill)
    - `embed_batch_retrieve(job_id)` → list[list[float]] | None (None if not ready yet)
    - 12-hour completion window — only use for non-time-sensitive data
    - Never use batch API on hot path (news pipeline, impact assessment)
  - Write `tests/test_news_embeddings.py`

  **Must NOT do**:
  - No Voyage calls on hot path
  - No crashes when VOYAGE_API_KEY unset
  - No sync blocking
  - No batch API for time-sensitive embeddings (heartbeat, live news)

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7A (parallel with T17, T19). **Blocks**: T20, T21, T22. **Blocked By**: T16, T36.

  **References**: `docs/decisions/voyage-ai-adoption.md` (ADR-001 full spec), `docs/architecture.md:124-165` (semantic layer)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_news_embeddings.py` → PASS
  - [ ] Graceful degradation without VOYAGE_API_KEY
  - [ ] Rate limiting enforced

  **QA Scenarios**:
  ```
  Scenario: VoyageClient embeds and degrades gracefully
    Tool: Bash (pytest)
    Steps: Run `pytest tests/test_news_embeddings.py -v`
    Expected Result: Embeddings work with key, degrade gracefully without
    Evidence: .sisyphus/evidence/task-18-embed.txt

  Scenario: Batch API submits and retrieves historical embeddings
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_news_embeddings.py::test_batch_submit -v`
      2. Assert: submit returns job_id, not embedded vectors
      3. Run `pytest tests/test_news_embeddings.py::test_batch_retrieve_not_ready -v`
      4. Assert: retrieve returns None when job not complete
      5. Run `pytest tests/test_news_embeddings.py::test_batch_retrieve_complete -v`
      6. Assert: retrieve returns embeddings when job complete
    Expected Result: Batch API works for non-urgent historical backfill
    Evidence: .sisyphus/evidence/task-18-embed-batch.txt
  ```

  **Commit**: YES - Message: `feat(news): add Voyage AI embedding client with graceful degradation`
  Files: `src/traderbot/news/embeddings.py`, `tests/test_news_embeddings.py`, `pyproject.toml`

- [x] 19. Create news Pydantic models + ChromaDB collections

  **What to do**:
  - Create `src/traderbot/news/models.py` with all news Pydantic models
  - Models: `NewsItem`, `SentimentResult`, `ImpactAssessment`, `ClassifiedNews`
  - All with `ConfigDict(strict=True, extra="forbid")`
  - Add ChromaDB `news_signals` and `market_conditions` collections to db/vectors.py
  - Write `tests/test_news_models.py`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 7A (parallel with T17, T18). **Blocks**: T20, T21, T22. **Blocked By**: T16.

  **References**: `docs/news-sentiment.md:246-253` (SentimentResult), `docs/news-sentiment.md:315-331` (ChromaDB collections)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_news_models.py` → PASS
  - [ ] All models strict validation enforced

  **Commit**: YES - Message: `feat(news): add Pydantic models and ChromaDB collections`
  Files: `src/traderbot/news/models.py`, `tests/test_news_models.py`, `src/traderbot/db/vectors.py`

- [x] 20. Create news/classifier.py

  **What to do**:
  - Create `src/traderbot/news/classifier.py` with hybrid Kalshi category classifier
  - Keyword matching (fast path) → Voyage semantic (ambiguous) → Reranker (0.5-0.7) → Agent LLM (<0.5)
  - Kalshi categories: Economics, Politics, Weather, Culture, Technology, Science
  - `classify(news_item) → ClassifiedNews` with confidence score
  - Write `tests/test_news_classifier.py`

  **Must NOT do**: No Voyage for obvious keyword matches. No non-Kalshi categories.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7B. **Blocks**: T23. **Blocked By**: T17, T18, T19.

  **References**: `docs/news-sentiment.md:134-176` (classifier spec, confidence ranges)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_news_classifier.py` → PASS
  - [ ] Classifier degrades to keyword-only without Voyage

  **Commit**: YES - Message: `feat(news): add hybrid classifier with keyword and Voyage semantic classification`

- [x] 21. Create news/sentiment_scorer.py

  **What to do**:
  - Create `src/traderbot/news/sentiment_scorer.py` with VADER + TextBlob + Voyage uplift
  - Add `vaderSentiment` and `textblob` to dependencies
  - Fast path: VADER (<1ms) for social, TextBlob (~5ms) for articles
  - Slow path: Voyage uplift when compound -0.3 to +0.3
  - `score(text, source) → SentimentResult`
  - Write `tests/test_sentiment_scorer.py`

  **Must NOT do**: No Voyage calls for high-confidence VADER. No blocking fast path.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7B (parallel with T20, T22). **Blocks**: T23. **Blocked By**: T18.

  **References**: `docs/news-sentiment.md:186-254` (scoring pipeline, Voyage uplift spec)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_sentiment_scorer.py` → PASS
  - [ ] VADER returns <10ms, Voyage uplift only for ambiguous scores

  **Commit**: YES - Message: `feat(news): add sentiment scorer with VADER, TextBlob, and Voyage uplift`
  - Files: `src/traderbot/news/sentiment_scorer.py`, `tests/test_sentiment_scorer.py`, `pyproject.toml`

- [x] 22. Create news/impact_assessor.py

  **What to do**:
  - Create `src/traderbot/news/impact_assessor.py`
  - `assess(news_item, classified_news, sentiment_result) → ImpactAssessment`
  - Weights: direct relevance (high), source authority (high), recency (medium), market sensitivity (medium), corroboration (low)
  - Impact >0.7 → high (would emit systemEvent), 0.3-0.7 moderate, <0.3 low
  - Corroboration boost: 1.3× multiplier (capped at 1.0) for multi-source events
  - Voyage semantic similarity for relevance (threshold 0.65)
  - Graceful degradation without Voyage
  - Write `tests/test_impact_assessor.py`

  **Must NOT do**: No systemEvent emission (Phase 8). No news beyond sources.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7B (parallel with T20, T21). **Blocks**: T23. **Blocked By**: T18, T19.

  **References**: `docs/news-sentiment.md:256-285` (impact criteria, weights, scoring thresholds)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_impact_assessor.py` → PASS
  - [ ] Corroboration boost capped at 1.0

  **Commit**: YES - Message: `feat(news): add impact assessor with heuristic and Voyage relevance`

- [x] 23. Wire news + sentiment CLI commands

  **What to do**:
  - Replace `news` and `sentiment` CLI stubs with real implementations
  - `traderbot news --category --limit --source --json`
  - `traderbot sentiment <ticker> --json`
  - Rich output formatting
  - Write/update `tests/test_cli.py`

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7C. **Blocks**: T24. **Blocked By**: T20, T21, T22.

  **References**: `src/traderbot/cli.py:341-354` (current stubs)

  **Acceptance Criteria**:
  - [ ] `traderbot news --help` and `traderbot sentiment --help` show options
  - [ ] Both commands work with `--json` flag

  **Commit**: YES - Message: `feat(news): wire news and sentiment CLI commands`

- [x] 24. Integration tests for news pipeline

  **What to do**:
  - Create `tests/test_news_integration.py`
  - E2E: fetch news → classify → score sentiment → assess impact → structured output
  - Test graceful degradation: each source, Voyage, ChromaDB independently
  - Run full test suite for regressions

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 7C. **Blocks**: T25. **Blocked By**: T23.

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_news_integration.py` → PASS
  - [ ] Coverage ≥ 99%, 0 regressions

  **Commit**: YES - Message: `test(news): add integration tests for news pipeline`

- [ ] 25. Phase 7 completion — version bump to v0.07.00

  **What to do**:
  - Update VERSION to `0.07.00`, ROADMAP_PROGRESS.md Phase 7 ✅, pyproject.toml version
  - Full test suite, 0 ruff errors, git tag v0.07.00

  **Recommended Agent Profile**: `quick` + `git-master`
  **Parallelization**: Final Phase 7 task. **Blocks**: T26. **Blocked By**: T24.

  **Commit**: YES - Message: `chore: bump version to v0.07.00 (Phase 7 complete)`

- [ ] 26. Implement simulation/adaptation.py — Bayesian engine

  **What to do**:
  - Expand `src/traderbot/simulation/adaptation.py` with full conjugate prior updates
  - Beta prior → Beta posterior (edge threshold), Dirichlet (signal weights), Normal (mean reversion), Gamma/Exponential (momentum decay)
  - `BayesianAdapter` class: `update(prior, observations) → AdaptationResult`
  - Guardrails: 20% max change/update, min 10 samples, cooldown 4/day, reset if variance <0.01, flag >10% drift for 3 consecutive
  - Add `scipy` to dependencies if not present
  - Write `tests/test_bayesian_adapter.py`

  **Must NOT do**: No auto-applying adaptations. No modifying risk limits. No MCMC.

  **Recommended Agent Profile**: `ultrabrain` (mathematical correctness critical)
  **Parallelization**: Wave 8A. **Blocks**: T27, T28, T29. **Blocked By**: T25, T11.

  **References**: `docs/self-learning.md:17-81` (Bayesian adaptation, guardrails, parameter table)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_bayesian_adapter.py` → PASS
  - [ ] Analytical posterior updates match conjugate formulas
  - [ ] No parameter moves more than 20% in single update
  - [ ] Minimum 10 observations required before any update
  - [ ] Max 4 updates per 24 hours (cooldown enforced)
  - [ ] Posterior variance < 0.01 triggers reset to weak prior
  - [ ] Consecutive 10%+ moves trigger human review flag

  **Commit**: YES - Message: `feat(adaptation): implement Bayesian adaptation engine with guardrails`
  - Files: `src/traderbot/simulation/adaptation.py`, `tests/test_bayesian_adapter.py`, `pyproject.toml`

- [ ] 27. Implement heartbeat self-review cycle

  **What to do**:
  - Implement full `traderbot heartbeat` CLI command (replace stub)
  - 7-step cycle: performance review → decision review → Bayesian adaptation → learning promotion → circuit breaker check → system health → update HEARTBEAT.md
  - Aggregates from db/decisions, analysis/portfolio, simulation/adaptation, risk/circuit_breaker
  - Writes structured output to HEARTBEAT.md
  - `--json` flag
  - Write `tests/test_heartbeat.py`

  **Must NOT do**: No auto-trading. No modifying risk limits.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 8A (after T26). **Blocks**: T28, T29. **Blocked By**: T26.

  **References**: `docs/self-learning.md:273-339` (heartbeat cycle, 7 steps, output format)

  **Acceptance Criteria**:
  - [ ] `traderbot heartbeat --json` produces complete output
  - [ ] HEARTBEAT.md updated with current timestamp
  - [ ] Bayesian adaptation and learning promotion executed

  **Commit**: YES - Message: `feat(adaptation): implement heartbeat self-review cycle`

- [ ] 28. Define OpenClaw three-loop cron architecture

  **What to do**:
  - Update `skills/traderbot/SKILL.md` with three-loop cron definitions
  - Decision Loop: `isolated agentTurn` every 5 min during market hours
  - Heartbeat Loop: `isolated agentTurn` every 6 hours
  - News Loop: `systemEvent` on high-impact news (impact > 0.7)
  - Define cron expressions and JSON payloads
  - Write `tests/test_cron_architecture.py`

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 8B (parallel with T29). **Blocks**: T29. **Blocked By**: T27.

  **References**: `docs/openclaw-integration.md:43-80` (three-loop cron specs)

  - Message: `feat(adaptation): define three-loop cron architecture for OpenClaw`
  - Files: `skills/traderbot/SKILL.md`, `.openclaw/workspace/SESSION-STATE.md`, `.openclaw/workspace/HEARTBEAT.md`, `tests/test_cron_architecture.py`, `pyproject.toml`

- [ ] 29. Update .openclaw/ workspace files for heartbeat

  **What to do**:
  - Update workspace templates: AGENTS.md (risk rules), USER.md (risk tolerance), HEARTBEAT.md (format), .learnings/ templates
  - Ensure consistency with WAL protocol and heartbeat output format
  - No src/ code changes
  - **No test file needed** — workspace files are Markdown templates, not Python code. Verified by T30 e2e integration tests.

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 8B (parallel with T28). **Blocks**: T30. **Blocked By**: T27.

  **References**: `docs/openclaw-integration.md:86-154` (workspace files)

  **Commit**: YES - Message: `feat(adaptation): update workspace files for heartbeat and WAL protocol`

- [ ] 30. End-to-end integration tests across all phases

  **What to do**:
  - Create `tests/test_e2e_integration.py`
  - Test full pipeline: backtest → paper trade → heartbeat → adaptation → news → sentiment
  - Test WAL: trade → WAL write → completion → crash recovery
  - Test graceful degradation: without Voyage, without ChromaDB
  - Test Bayesian guardrails
  - Full coverage check: ≥99%, 0 failures, 0 ruff errors

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 8C. **Blocks**: T31. **Blocked By**: T28, T29.

  **Commit**: YES - Message: `test: add end-to-end integration tests across all phases`

- [ ] 31. Phase 8 completion — version bump to v0.08.00

  **What to do**:
  - VERSION → `0.08.00`, ROADMAP_PROGRESS.md all phases ✅, pyproject.toml
  - Full test suite, 0 ruff errors, git tag v0.08.00

  **Recommended Agent Profile**: `quick` + `git-master`
  **Parallelization**: Final Phase 8 task. **Blocks**: F1-F4. **Blocked By**: T30.

  **Commit**: YES - Message: `chore: bump version to v0.08.00 (all phases complete)`

- [x] 32. Create `traderbot bootstrap` CLI command — initial calibration

  **What to do**:
  - Add `bootstrap` command to `src/traderbot/cli.py`
  - `traderbot bootstrap` performs first-run calibration:
    1. Validate Kalshi API connectivity (demo + production)
    2. Fetch 30 days historical data via DataLoader
    3. Warm up indicators (compute SMA/EMA/RSI on historical data to fill lookback periods)
    4. Run shadow backtest against settled markets with default strategy
    5. Compute initial Bayesian priors from historical win rates (seed Beta distribution with observed edge)
    6. Seed decisions DB with bootstrap results for baseline metrics
    7. Validate data freshness (last market data < 24 hours old)
    8. Write bootstrap results to HEARTBEAT.md with timestamp and status
  - `--dry-run` flag: runs validation without writing to DB or HEARTBEAT.md
  - `--json` flag for machine-readable output
  - Must handle empty DB gracefully (first run has no prior decisions)
  - Must handle missing historical data with clear error messages
  - Must handle insufficient historical data (< 30 days) by proceeding with partial data and logging WARNING
  - Must handle anomalous historical periods (e.g., COVID, election years) by noting the date range in bootstrap output
  - Idempotent: running bootstrap twice doesn't duplicate data
  - Write `tests/test_bootstrap.py`

  **Must NOT do**:
  - No modifying risk module or HARD_LIMITS
  - No live trading — bootstrap is read-only validation
  - No real money involved

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Phase 5 — Wave 5C (after T7, with T8). **Blocks**: Phase 6 start. **Blocked By**: Tasks 6b, 7.

  **References**:
  - `src/traderbot/cli.py` — existing CLI command pattern
  - `docs/self-learning.md:42-49` — update cycle: collect decisions, compare predicted vs actual, compute likelihood, update priors
  - `src/traderbot/analysis/indicators.py:37-42` — throws ValueError on empty prices — bootstrap must provide warm-up data
  - `src/traderbot/risk/circuit_breaker.py` — CircuitBreaker state to validate
  - `docs/simulation.md:86-121` — DataLoader spec: get_markets, get_trades, get_outcomes

  **Acceptance Criteria**:
  - [ ] `traderbot bootstrap --dry-run` validates API connectivity and data freshness
  - [ ] `traderbot bootstrap` seeds decisions DB with historical baseline
  - [ ] `traderbot bootstrap` computes initial priors from historical data
  - [ ] Idempotent: running twice doesn't duplicate data
  - [ ] `traderbot bootstrap` handles insufficient data (< 30 days) with WARNING, proceeds anyway
  - [ ] `traderbot bootstrap` notes anomalous historical periods in output
  - [ ] `pytest tests/test_bootstrap.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Bootstrap validates API and computes priors from historical data
    Tool: Bash (pytest + CLI)
    Steps:
      1. Run `traderbot bootstrap --dry-run --json`
      2. Assert: returns validation status, no DB writes
      3. Run `traderbot bootstrap --json`
      4. Assert: priors computed, decisions seeded, HEARTBEAT.md updated
      5. Run `traderbot bootstrap --json` again
      6. Assert: idempotent, no duplicate data
    Expected Result: Bootstrap validates, computes priors, seeds baseline
    Evidence: .sisyphus/evidence/task-32-bootstrap.txt

  Scenario: Bootstrap handles empty first-run gracefully
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_bootstrap.py::test_empty_first_run -v`
      2. Assert: no crashes, clear guidance message
    Expected Result: Empty DB handled gracefully with informative messages
    Evidence: .sisyphus/evidence/task-32-bootstrap-empty.txt

  Scenario: Bootstrap handles insufficient historical data with WARNING
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_bootstrap.py::test_insufficient_data_warning -v`
      2. Assert: WARNING logged when < 30 days of data available
      3. Assert: bootstrap proceeds with partial data (doesn't crash)
      4. Assert: output notes the actual date range used
    Expected Result: Bootstrap proceeds with partial data, warns about limited history
    Evidence: .sisyphus/evidence/task-32-bootstrap-partial.txt
  ```

  **Commit**: YES - Message: `feat(simulation): add bootstrap command for initial calibration`

- [ ] 33. Create StrategyProfile + multi-profile backtesting

  **What to do**:
  - Create `src/traderbot/simulation/profiles.py` with `StrategyProfile` model
  - `StrategyProfile(name, risk_multiplier, signal_weights, category_focus)`:
    - `risk_multiplier`: float 0.1-1.0, scales within HARD_LIMITS (conservative=0.5x, moderate=1.0x, aggressive=0.8x)
    - `signal_weights`: dict mapping signal types to float weights
    - `category_focus`: optional `MarketCategory` for category-aware strategies
  - `BacktestEngine.run_profiles(profiles, data, start, end)`: runs multiple profiles on same data
  - Each profile gets isolated position tracking and its own `Context`
  - `HARD_LIMITS` remain IMMUTABLE — profiles only **scale** within them (risk_multiplier * limit)
  - Extend `BacktestResult` to include `profile_name` for comparison
  - Extend `simulation/performance.py:compare_strategies()` to accept list of profiles
  - Update `traderbot compare` CLI to support `--profile-a` and `--profile-b` arguments
  - Add preset profiles: Conservative (0.5x), Moderate (1.0x), Aggressive (0.8x)
  - Write `tests/test_strategy_profiles.py`

  **Must NOT do**:
  - No modifying or overriding HARD_LIMITS — profiles scale within them only
  - No live trading with multiple profiles simultaneously (paper trading only)
- Multi-profile paper trading is sequential per demo account (shared balance and positions; backtesting can run profiles in parallel)
  - No subagent that bypasses risk checks

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Phase 5 — Wave 5B (after T2, T3). **Blocks**: T6b. **Blocked By**: Tasks 2, 3, 5.

  **References**:
  - `src/traderbot/risk/limits.py:10-19` — `HARD_LIMITS` as `MappingProxyType` (immutable)
  - `docs/simulation.md:56-69` — Strategy Protocol spec: `on_market_open`, `on_trade`, `on_settle`
  - `docs/simulation.md:74-83` — Context object: portfolio, market data, sentiment, risk state
  - `docs/architecture.md:101-123` — Toolkit vs. Agent boundary: toolkit enforces, agent decides

  **Acceptance Criteria**:
  - [ ] `StrategyProfile` model created with risk_multiplier, signal_weights, category_focus
  - [ ] `BacktestEngine.run_profiles()` runs multiple profiles on same data
  - [ ] Each profile gets isolated position tracking
  - [ ] HARD_LIMITS never overridden — risk_multiplier only scales within limits
  - [ ] `traderbot compare --profile-a conservative --profile-b aggressive` works
  - [ ] `pytest tests/test_strategy_profiles.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Multiple profiles run on same historical data with isolated tracking
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_strategy_profiles.py::test_multi_profile_backtest -v`
      2. Assert: each profile produces separate results with different P&L
      3. Assert: positions tracked independently per profile
    Expected Result: Profiles produce distinct results, no cross-contamination
    Evidence: .sisyphus/evidence/task-33-profiles.txt

  Scenario: Profile risk_multiplier scales within HARD_LIMITS, never overrides
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_strategy_profiles.py::test_risk_within_limits -v`
      2. Assert: aggressive profile (0.8x) position size ≤ HARD_LIMITS position size
      3. Assert: conservative profile (0.5x) position size is 50% of limit
      4. Assert: no profile ever exceeds HARD_LIMITS
    Expected Result: All profiles stay within HARD_LIMITS boundaries
    Evidence: .sisyphus/evidence/task-33-risk-limits.txt
  ```

  **Commit**: YES - Message: `feat(simulation): add StrategyProfile with multi-profile backtesting`

- [x] 34. Implement FEATURE_REQUESTS.md flow in learning system

  **What to do**:
  - Extend `src/traderbot/db/learnings.py` with `feature_request` category support
  - Add `feature_request` as valid `Status` and `Category` in learning entry schema
  - Feature request entry format: Pattern-Key, Description, Justification (data-backed), Impact Assessment, Priority
  - Add `list_feature_requests(status)` query method
  - Extend `src/traderbot/learning.py` promotion logic:
    - Feature requests with `Recurrence-Count >= 3` → promoted to `PENDING_REVIEW` (NOT auto-committed)
    - Promoted feature requests written to `.openclaw/workspace/.learnings/FEATURE_REQUESTS.md`
    - NEVER auto-edit risk module or any source code
  - Add `traderbot learnings --category feature_request` CLI filter
  - Update `HEARTBEAT.md` output to include feature request summaries
  - Write `tests/test_feature_requests.py`

  **Must NOT do**:
  - No auto-editing of source code — feature requests are for human review only
  - No modifying risk/limits.py or any immutable guardrails programmatically
  - No auto-applying feature requests even with high recurrence

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Phase 6 — Wave 6B (with T12, T13). **Blocks**: T14. **Blocked By**: Task 9.

  **References**:
  - `docs/self-learning.md:93` — `FEATURE_REQUESTS.md` file already specified in the directory structure
  - `docs/self-learning.md:98-110` — Learning entry format: Pattern-Key, Recurrence-Count, Priority, Status, Category
  - `docs/self-learning.md:112-124` — Pattern promotion criteria and targets
  - `src/traderbot/risk/limits.py:10-19` — `HARD_LIMITS` as `MappingProxyType` — MUST NOT be modified by any feature request

  **Acceptance Criteria**:
  - [ ] `feature_request` category works in learnings DB
  - [ ] Feature requests promoted to `PENDING_REVIEW` when recurrence >= 3
  - [ ] Promoted requests written to `FEATURE_REQUESTS.md`, not to source code
  - [ ] `traderbot learnings --category feature_request` filters correctly
  - [ ] `pytest tests/test_feature_requests.py` → PASS
  - [ ] grep confirms no code path writes to `risk/limits.py`

  **QA Scenarios**:
  ```
  Scenario: Feature requests accumulate and promote to PENDING_REVIEW at recurrence >= 3
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_feature_requests.py::test_feature_request_promotion -v`
      2. Assert: recurrence >= 3 promotes to PENDING_REVIEW status
      3. Assert: promoted request written to FEATURE_REQUESTS.md
      4. Assert: no source code files modified
    Expected Result: Feature requests promoted to PENDING_REVIEW, never auto-committed
    Evidence: .sisyphus/evidence/task-34-feature-requests.txt

  Scenario: No code path modifies immutable guardrails
    Tool: Bash (grep)
    Steps:
      1. Run `grep -rn "HARD_LIMITS" src/traderbot/learning.py src/traderbot/db/learnings.py`
      2. Assert: no modification of HARD_LIMITS, only read access
      3. Run `grep -rn "MappingProxyType" src/traderbot/learning.py src/traderbot/db/learnings.py`
      4. Assert: no re-binding of MappingProxyType
    Expected Result: Learning system never modifies immutable guardrails
    Evidence: .sisyphus/evidence/task-34-immutable-guardrails.txt
  ```

  **Commit**: YES - Message: `feat(learning): add feature request flow with PENDING_REVIEW promotion`

- [ ] 35. Create CategoryAnalyzer protocol + MarketCategory enum + AnalysisRegistry

  **What to do**:
  - Create `src/traderbot/analysis/registry.py` with `AnalysisRegistry` and `CategoryAnalyzer` protocol
  - `MarketCategory` enum defined in `src/traderbot/kalshi/models.py` (not analysis/ — avoids circular dependency with simulation/)
  - Both `simulation/` and `analysis/` import `MarketCategory` from `kalshi/models.py`
  - `MarketCategory` enum: ECONOMICS, POLITICS, WEATHER, SPORTS, CULTURE, TECHNOLOGY, SCIENCE
  - `CategoryAnalyzer` Protocol: `analyze(market, category_data) -> CategorySignals`
  - `CategorySignals` model: category, signals list, confidence, data_sources
  - `AnalysisRegistry` class: `register(category, analyzer)`, `get(category) -> CategoryAnalyzer`, `analyze(market, category) -> CategorySignals`
  - Default `GenericAnalyzer` registered for all categories — current pipeline (SMA, EMA, RSI, Bollinger, edge detection)
  - Add `market_category` field to Kalshi `Market` model parsing (from API `category` field)
  - Extend `Context` (from simulation docs) with `category: MarketCategory` field
  - Extend Bayesian adaptation to support per-category signal weights (already designed in docs)
  - Write `tests/test_analysis_registry.py`

  **Must NOT do**:
  - No implementing actual sports/weather/economics analyzers — that's Phase 9+
  - No changing existing generic analysis pipeline — it becomes the default analyzer
  - No adding external data sources beyond what Kalshi API provides

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Phase 7 — Wave 7A (with T17, T18, T19). **Blocks**: T20, T23. **Blocked By**: Task 16 (Phase 6 complete).

  **References**:
  - `src/traderbot/analysis/indicators.py` — Current generic indicator computation (SMA, EMA, RSI, Bollinger)
  - `src/traderbot/analysis/odds.py` — Current edge detection (category-agnostic)
  - `src/traderbot/analysis/signals.py` — Current signal generation (category-agnostic)
  - `docs/self-learning.md:66` — "Increased statistical signal weight for economic category markets" — category-aware Bayesian update concept
  - `docs/architecture.md:217` — `news/` depends on `kalshi/models` for market category mapping
  - `src/traderbot/kalshi/models.py` — Market model to extend with category field

  **Acceptance Criteria**:
  - [ ] `MarketCategory` enum created in `kalshi/models.py` (not analysis/) with 7 categories
  - [ ] Both `simulation/` and `analysis/` import MarketCategory from `kalshi/models.py`
  - [ ] `CategoryAnalyzer` protocol and `AnalysisRegistry` created
  - [ ] `GenericAnalyzer` registered as default for all categories
  - [ ] `Context` model extended with `category` field
  - [ ] Existing tests still pass (no regression)
  - [ ] `pytest tests/test_analysis_registry.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: AnalysisRegistry dispatches to correct analyzer per category
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_analysis_registry.py::test_registry_dispatches_generic -v`
      2. Assert: GenericAnalyzer used for all categories by default
      3. Run `pytest tests/test_analysis_registry.py::test_register_custom_analyzer -v`
      4. Assert: `registry.get("economics")` returns SportsAnalyzer, not GenericAnalyzer
    Expected Result: Registry dispatches correctly, default is generic
    Evidence: .sisyphus/evidence/task-35-registry.txt

  Scenario: Existing analysis pipeline still works as default
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_indicators.py tests/test_odds.py tests/test_signals.py -v`
      2. Assert: all existing tests pass, no regressions
    Expected Result: GenericAnalyzer = existing pipeline, no changes
    Evidence: .sisyphus/evidence/task-35-regression.txt
  ```

  **Commit**: YES - Message: `feat(analysis): add CategoryAnalyzer protocol, MarketCategory enum, and AnalysisRegistry`

- [x] 36. Create credential management — `traderbot auth` CLI + keyring integration

  **What to do**:
  - Add `keyring` to `pyproject.toml` dependencies
  - Create `src/traderbot/auth.py` with secure credential management:
    - `AuthManager` class using `keyring` library for OS-native credential storage
    - Service namespaced as `"traderbot.{service_name}"` (e.g., `"traderbot.kalshi"`, `"traderbot.voyage"`)
    - `set_credential(service, key, value)` — stores credential in OS keyring (macOS Keychain, Linux Secret Service, Windows Credential Manager)
    - `get_credential(service, key)` — retrieves from OS keyring, returns `SecretStr`
    - `delete_credential(service, key)` — removes from OS keyring
    - `list_services()` — lists all traderbot services in keyring
    - Keyring fallback: if keyring backend unavailable, log WARNING and fall back to `.env` file
    - All credentials stored as `SecretStr` in Pydantic models — never logged, never serialized to plain text
  - Create `src/traderbot/kalshi/config.py` extending `KalshiConfig`:
    - Try keyring first for `api_key` and `api_secret`
    - Fall back to `.env` only if keyring unavailable
    - Log WARNING on fallback
    - All new config models (VoyageConfig, NewsAPIConfig, etc.) use same pattern
  - Add `traderbot auth` CLI command group:
    - `traderbot auth login` — interactive credential setup (prompts for each service)
    - `traderbot auth set-key <service> <key>` — store a credential
    - `traderbot auth list-keys` — list configured services (keys only, never values)
    - `traderbot auth rotate <service>` — rotate a credential (prompt for new value, delete old)
    - `traderbot auth check` — verify all required credentials are configured
  - Create `.env.example` with all required and optional environment variables:
    - Required: `KALSHI_API_KEY`, `KALSHI_API_SECRET`, `KALSHI_DEMO_MODE`
    - Optional (graceful degradation): `VOYAGE_API_KEY`, `NEWSAPI_KEY`, `TWITTER_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
    - Configuration: `CHROMA_DB_PATH` (default: `.chroma/`), `KALSHI_RATE_LIMIT_RPS`
    - Header: "Prefer `traderbot auth` for credential management. .env is fallback only."
  - Write `tests/test_auth.py` with mocked keyring backend
  - Move `MarketCategory` enum to `kalshi/models.py` (resolves circular dependency risk between simulation/ and analysis/)

  **Must NOT do**:
  - No plaintext credential storage anywhere (no writing secrets to .env programmatically)
  - No credentials in process environment visible to other processes (use keyring, not env vars, as primary)
  - No WebAuthn/FIDO2 — keyring provides biometric unlock via OS Keychain on macOS (Touch ID)
  - No credentials in logs, error messages, or serialization — always `SecretStr`
  - No modifying existing `KalshiConfig` behavior — extend it with keyring-priority lookup

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2, Task 3 after Task 1)
  - **Parallel Group**: Wave 5A (foundation — parallel with engine/models after data_loader)
  - **Blocks**: Tasks 4, 5, 6, 17, 18 (all tasks using API credentials)
  - **Blocked By**: Task 0 (docs must be updated first)

  **References**:
  - `src/traderbot/kalshi/client.py:25-48` — Current `KalshiConfig` with `api_key`, `api_secret: SecretStr`, `BaseSettings`
  - `.gitignore:16-18` — `.env`, `.env.local`, `.env.*.local` already ignored
  - `.gitignore:34` — `credentials.json` already ignored
  - Python `keyring` library — `set_password(service, username, password)`, `get_password(service, username)`, uses OS Keychain/Secret Service/Credential Manager
  - `.env.example` — Currently missing, needs creation

  **Acceptance Criteria**:

  **If TDD (tests enabled)**:
  - [ ] Test file created: `tests/test_auth.py`
  - [ ] `pytest tests/test_auth.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: Auth manager stores and retrieves credentials via OS keyring
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_auth.py::test_set_and_get_credential -v`
      2. Assert: credential stored and retrieved correctly via keyring
      3. Run `pytest tests/test_auth.py::test_credential_is_secretstr -v`
      4. Assert: returned value is SecretStr, never plain text
    Expected Result: Credentials stored securely, retrieved as SecretStr
    Evidence: .sisyphus/evidence/task-36-auth-keyring.txt

  Scenario: Auth manager falls back gracefully when keyring unavailable
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_auth.py::test_keyring_fallback_to_env -v`
      2. Assert: WARNING logged when keyring backend unavailable
      3. Assert: credential still retrieved from .env fallback
    Expected Result: Graceful degradation with warning, no crash
    Evidence: .sisyphus/evidence/task-36-auth-fallback.txt

  Scenario: CLI auth commands work correctly
    Tool: Bash (CLI + pytest)
    Steps:
      1. Run `traderbot auth login --help` — Assert: shows service prompts
      2. Run `traderbot auth list-keys` — Assert: lists services, never values
      3. Run `traderbot auth check` — Assert: verifies all required credentials
    Expected Result: All auth CLI commands functional
    Evidence: .sisyphus/evidence/task-36-auth-cli.txt

  Scenario: No plaintext credentials in logs or serialization
    Tool: Bash (grep)
    Steps:
      1. `grep -rn "api_secret" src/traderbot/auth.py` — Assert: only SecretStr references, no plain text
      2. `grep -rn "secret" src/traderbot/auth.py` — Assert: all SecretStr, no string assignment of secrets
    Expected Result: Zero plaintext credential exposure
    Evidence: .sisyphus/evidence/task-36-auth-no-plaintext.txt
  ```

  **Commit**: YES
  - Message: `feat(auth): add keyring-based credential management with auth CLI and .env.example`
  - Files: `src/traderbot/auth.py`, `src/traderbot/kalshi/config.py`, `src/traderbot/cli.py`, `tests/test_auth.py`, `.env.example`, `pyproject.toml`
  - Pre-commit: `pytest tests/test_auth.py -v`

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check` + `pytest --cov=traderbot`. Review all new files for: `as any`/type ignore, empty catches, console.log/print in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Check all new Pydantic models have `ConfigDict(strict=True, extra="forbid")`. Check all monetary values are `int` not `float`.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Coverage [%] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real QA — CLI Verification** — `unspecified-high`
  Start from clean environment. Execute: `traderbot auth login`, `traderbot auth list-keys`, `traderbot auth check`, `traderbot bootstrap`, `traderbot backtest`, `traderbot paper`, `traderbot compare`, `traderbot performance`, `traderbot learnings`, `traderbot news`, `traderbot sentiment`, `traderbot heartbeat`. Verify each command returns expected output or sensible error. Run full test suite. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Commands [N/N working] | Tests [N pass/N fail] | Coverage [%] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each phase (5-8): read "What to do", compare to actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Verify no future expansion code (post-Phase 8). Flag unaccounted changes.
  Output: `Phases [4/4 compliant] | Forbidden [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Phase 5 tasks**: `feat(simulation): <desc>` — one concern per commit
- **Phase 6 tasks**: `feat(learning): <desc>` — one concern per commit
- **Phase 7 tasks**: `feat(news): <desc>` — one concern per commit
- **Phase 8 tasks**: `feat(adaptation): <desc>` — one concern per commit
- **Version bump commits**: `chore: bump version to v0.0N.00` at each phase milestone
- **Every commit**: `git add . && git commit -m "type(scope): msg" && git tag v0.04.XX && git push && git push --tags`

---

## Success Criteria

### Verification Commands
```bash
pytest --cov=traderbot --cov-report=term-missing  # Expected: 99%+ coverage, 0 failures
ruff check src/traderbot  # Expected: 0 errors
traderbot backtest --help  # Expected: shows backtest options
traderbot paper --help  # Expected: shows paper trading options
traderbot learnings --help  # Expected: shows learnings options
traderbot news --help  # Expected: shows news options
traderbot heartbeat --help  # Expected: shows heartbeat options
traderbot auth login --help  # Expected: shows auth login options
traderbot bootstrap --help  # Expected: shows bootstrap options
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (445+ tests)
- [ ] Coverage ≥ 99%
- [ ] Ruff errors = 0
- [ ] Version at v0.08.00