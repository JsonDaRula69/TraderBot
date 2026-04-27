# Phase 7+8: News/Sentiment Pipeline & Adaptation Autonomy

## TL;DR

Audit, extend, and wire the existing-but-unmarked news pipeline and adaptation engine into production. Phase 7 code already exists (sources, classifier, sentiment, impact, embeddings) but needs normalization, profile-awareness, CLI polish, and tests. Phase 8 adaptation engine exists (BayesianAdapter 712 lines) but is memory-only, un-persisted, and not wired into agent autonomy flows. Fix 7 critical issues (MarketCategory enum mismatch, Twitter stub, ImpactWeights validation, state persistence, CLI gaps), then wire everything together so agents can actually use news signals and adaptation state across restarts.

---

## Context

### Original Request

Implement Phase 7 (News & Sentiment Pipeline) and Phase 8 (Adaptation Engine & Full Autonomy) for TraderBot. Phases 1-6 and 9 are complete. Current version: v0.08.21.

### Interview Summary (User Decisions)

- **Phase 7**: Audit + extend + wire CLI — NOT rewrite. Existing code is substantial and functional.
- **Phase 8**: Agent autonomy + CLI wiring — NOT automated strategy adaptation. The agent decides; the toolkit computes.
- **News pipeline**: Profile-aware (per-profile filtering, storage, API keys via ProfileAuthStore).
- **Version**: Continue from v0.08.21, increment as we go. Do NOT reset to v0.07.00 or v0.08.00.

### Research Findings

**Phase 7 — Already Implemented (needs audit/extension):**

| Module | File | Lines | Status |
|---|---|---|---|
| Sources | `news/sources.py` | 259 | ✅ NewsAPI (httpx+retry/backoff), Reddit RSS (feedparser), Twitter stub (empty) |
| Classifier | `news/classifier.py` | 409 | ✅ Hybrid keyword + Voyage semantic, CategoryAnalyzer/AnalysisRegistry in docs only |
| Sentiment | `news/sentiment_scorer.py` | 129 | ✅ VADER primary, TextBlob fallback, Voyage uplift for neutral range |
| Impact | `news/impact_assessor.py` | 267 | ✅ 5-factor weighted scoring (relevance, authority, recency, sensitivity, corroboration) |
| Embeddings | `news/embeddings.py` | 235 | ✅ VoyageClient with lazy init, rate limiting, batch API |
| Models | `news/models.py` | 82 | ✅ NewsItem, ClassifiedNews, SentimentResult, ImpactAssessment |
| CLI | `cli.py` | ~330 | ✅ `news` and `sentiment` commands already wired |

**Phase 8 — Partially Implemented:**

| Module | File | Lines | Status |
|---|---|---|---|
| BayesianAdapter | `simulation/adaptation.py` | 712 | ✅ Full implementation but **memory-only** — no persistence |
| Learning system | `learning.py` + `db/learnings.py` | 341+ | ✅ Pattern promotion, feature requests |
| Heartbeat | `heartbeat.py` | 517 | ✅ 7-step cycle, CLI wired |
| Signals | `analysis/signals.py` | 171 | ✅ But **no news integration** — only indicators, odds, momentum |

**Critical: ROADMAP_PROGRESS.md incorrectly marks Phase 7 and 8 as "NOT STARTED".**

### Metis Review — 7 Critical Issues

1. **MarketCategory enum inconsistency**: `simulation/adaptation.py` uses title-case (`"Politics"`, `"Economics"`) while `news/models.py` also uses title-case (`"Politics"`, `"Economics"`). BUT `kalshi/models.py` MarketCategory and `docs/architecture.md` use lowercase (`"economics"`, `"politics"`). `profiles/models.py` imports MarketCategory from `kalshi/models.py` (lowercase). This creates a **cross-module type split**: adaptation.py and news/models.py define their own MarketCategory enums independent from kalshi/models.py, using different values.

2. **Twitter stub silently returns empty** — `_fetch_twitter()` logs warning but never raises or removes itself from source priority. First-priority source is a no-op.

3. **No `traderbot news --json` CLI command** — Actually EXISTS (line 696-850 of cli.py). This is a false finding from Metis.

4. **No `traderbot heartbeat --json` CLI command** — Actually EXISTS (line 546-645 of cli.py with --json flag). False finding.

5. **No adaptation state persistence** — BayesianAdapter is memory-only. `_update_timestamps` and `_drift_counts` are in-memory dicts. Restart loses all state.

6. **ImpactWeights are float constants with no validation** that they sum to 1.0 — weights in `impact_assessor.py` are 0.30+0.25+0.20+0.15+0.10=1.0 but this is not enforced by validators.

7. **Version conflict**: Phase 7 says v0.07.00, Phase 8 says v0.08.00, but we're already at v0.08.21. Resolution: continue from v0.08.21+.

---

## Work Objectives

### Core Objective

Make the existing news/sentiment pipeline and adaptation engine **production-ready** by: normalizing cross-module types, adding persistence, making them profile-aware, wiring news signals into `analysis/signals.py`, and updating ROADMAP_PROGRESS.md to reflect reality.

### Concrete Deliverables

1. **Unified MarketCategory enum** — single source of truth, all modules reference it
2. **ImpactWeights validation** — Pydantic model enforcing sum=1.0
3. **Twitter source demoted** — moved below NEWSAPI in priority, explicit stub marker
4. **Adaptation state persistence** — JSON-backed BayesianAdapter state survives restarts
5. **Profile-aware news pipeline** — per-profile API key resolution, category filtering, data isolation
6. **News signal in analysis/signals.py** — sentiment as a 4th signal source
7. **Updated ROADMAP_PROGRESS.md** — Phase 7 marked as partially complete with correct status
8. **`news/__init__.py` expanded** — expose full public API
9. **Tests for all new/changed code**

### Definition of Done

- All 7 critical issues resolved
- `traderbot news --category Economics --json` works with profile-aware API key resolution
- `traderbot heartbeat --json` persists adaptation state across simulated restart
- `traderbot sentiment BTC` returns news-weighted signal
- `analysis/signals.py` includes a `sentiment` SignalSource in `generate_signal()`
- All Pydantic models maintain `ConfigDict(strict=True, extra="forbid")`
- `ruff check` passes, all tests green
- ROADMAP_PROGRESS.md reflects actual implementation status

### Must Have

- Unified MarketCategory (lowercase per kalshi/models.py, the single source of truth)
- Adaptation state persistence (JSON file, atomic writes)
- Profile-aware news API key resolution
- ImpactWeights Pydantic model with sum=1.0 validator
- News signal source in analysis/signals.py
- Twitter source deprioritized in _SOURCE_PRIORITY

### Must Not Have

- Automated strategy changes (agent decides, toolkit computes)
- Any modifications to `risk/` hard limits
- Twitter API implementation (remains stub, just demoted+documented)
- ChromaDB vector store implementation (Phase 7+8 scope is audit+wire, not new infra)
- Version reset (continue from v0.08.21)
- Rewrite of existing functional code

---

## Verification Strategy

### Test Decision

- Unit tests for all new/changed functions
- Integration test for adaptation persistence (write→restart→read)
- CLI smoke tests for `news --json`, `sentiment --json` with mock sources
- Profile-aware test: news command with profile token → uses profile API key

### QA Policy

- `ruff check src/traderbot/` must pass
- `pytest tests/ -x` must pass
- `pytest tests/ --cov=traderbot.news --cov=traderbot.simulation --cov=traderbot.analysis -x` coverage check
- Manual CLI verification of all modified commands

---

## Execution Strategy

### Dependency Matrix

```
TODO-1 (MarketCategory enum) ──┬──> TODO-3 (Twitter demotion)
                                ├──> TODO-4 (ImpactWeights)
                                ├──> TODO-5 (Profile-aware news)
                                └──> TODO-7 (News signals)
                                       
TODO-2 (Adaptation persistence) ──> TODO-6 (Heartbeat persistence wiring)
                                       
TODO-8 (ROADMAP update) depends on all others
TODO-9 (__init__.py) depends on TODO-1
TODO-10 (Tests) runs in parallel with all
```

### Parallel Waves

**Wave 1** (foundation, parallel):
- TODO-1: Unify MarketCategory enum
- TODO-2: Adaptation state persistence

**Wave 2** (depends on Wave 1):
- TODO-3: Twitter source demotion (after TODO-1)
- TODO-4: ImpactWeights validation model (after TODO-1)
- TODO-5: Profile-aware news pipeline (after TODO-1)
- TODO-6: Heartbeat adaptation persistence wiring (after TODO-2)

**Wave 3** (depends on Wave 2):
- TODO-7: News signal in analysis/signals.py (after TODO-5)
- TODO-9: Expand news/__init__.py (after TODO-1)

**Wave 4** (finalize):
- TODO-8: Update ROADMAP_PROGRESS.md
- TODO-10: Comprehensive tests

### Agent Dispatch

- **build agent**: TODO-1 through TODO-9 (code changes)
- **build agent**: TODO-10 (tests, can parallel with code)
- Manual review after each wave

---

## TODOs

---

### TODO-1: Unify MarketCategory Enum

**1. TASK**

Create a single canonical `MarketCategory` StrEnum with lowercase values matching `kalshi/models.py`. Remove duplicate enum definitions from `simulation/adaptation.py` and `news/models.py`. Make both modules import from `kalshi/models.py`.

**2. EXPECTED OUTCOME**

- `kalshi/models.py` is the single source of truth for `MarketCategory`
- `simulation/adaptation.py` imports `MarketCategory` from `kalshi/models.py` instead of defining its own
- `news/models.py` `NewsCategory` either imports and aliases `MarketCategory` or uses it directly
- All `NewsCategory` usages across the codebase updated to use canonical enum
- CLI `news --category` validation works with lowercase values
- Zero test regressions

**3. REQUIRED TOOLS**

- Read, Edit, Bash, LSP (goto_definition, find_references)

**4. MUST DO**

- Verify `kalshi/models.py` MarketCategory enum values and structure
- Change `simulation/adaptation.py` to import MarketCategory from `kalshi/models.py`
- Remove the duplicate MarketCategory class from `simulation/adaptation.py`
- Change `news/models.py` NewsCategory to alias or re-export MarketCategory from kalshi
- Update all references across the codebase (cli.py, heartbeat.py, classifier.py, impact_assessor.py, etc.)
- Ensure StrEnum behavior preserved (values are lowercase strings)
- CLI category flag in `news` command must accept lowercase: `--category economics`
- Update `news/models.py` NewsCategory docstring to reference MarketCategory
- `NewsSource` enum in `news/models.py` stays (it's source-specific, not market-specific)
- Verify classifier keyword maps use the new enum members

**5. MUST NOT DO**

- Change `kalshi/models.py` MarketCategory values to title-case (kalshi is the source of truth with lowercase)
- Change any existing test assertions without verifying the enum values actually changed
- Remove `NewsCategory` if it's used externally — alias it instead
- Modify risk/ module

**6. CONTEXT**

- `kalshi/models.py` MarketCategory uses lowercase values: "economics", "politics", etc.
- `simulation/adaptation.py` lines 30-40: duplicate MarketCategory with title-case "Politics", "Economics"
- `news/models.py` lines 20-30: NewsCategory with title-case "Politics", "Economics"
- `profiles/models.py` line 9: imports MarketCategory from `kalshi/models.py` (correct)
- `docs/architecture.md` lines 143-151: shows MarketCategory with lowercase values
- CLI `news` command line 710-720: validates `NewsCategory(category)` — must work with lowercase after change
- `news/classifier.py` lines 43-109: keyword maps reference `NewsCategory.ECONOMICS` etc. — will still work via enum member name
- `news/impact_assessor.py` lines 54-63: `CATEGORY_SENSITIVITY` dict uses `NewsCategory` keys

**Commit message**: `refactor: unify MarketCategory enum — single source of truth in kalshi/models.py`

**Pre-commit test**: `pytest tests/ -x -k "category or Category or market_category"`

**QA scenario**: Run `traderbot news --category economics --json` and verify lowercase category value accepted. Run `traderbot news --category Economics --json` and verify it also works (StrEnum case-insensitive lookup or clear error).

---

### TODO-2: Adaptation State Persistence

**1. TASK**

Add JSON file-based persistence for `BayesianAdapter` state so it survives restarts. Implement atomic writes (write-to-temp + rename), lazy load on first access, and state versioning.

**2. EXPECTED OUTCOME**

- `BayesianAdapter` state (`_update_timestamps`, `_drift_counts`, current distribution params) persists to JSON
- New file `simulation/adapter_state.py` with `AdapterStateStore` class
- `AdapterStateStore.save(adapter, path)` serializes state
- `AdapterStateStore.load(path)` returns state dict or empty defaults
- Atomic writes via tempfile + os.rename
- JSON schema version field for forward compatibility
- `BayesianAdapter.__init__` accepts optional `state_path` parameter
- On init with state_path, loads existing state; on each update, persists
- Heartbeat step restores adapter from persisted state

**3. REQUIRED TOOLS**

- Read, Edit, Write, Bash

**4. MUST DO**

- Create `src/traderbot/simulation/adapter_state.py` with `AdapterStateStore`
- `AdapterStateStore` uses Pydantic model for state schema with `ConfigDict(strict=True, extra="forbid")`
- State model contains: `version: int`, `update_timestamps: list[str]`, `drift_counts: dict[str, int]`, `distributions: dict[str, Any]`
- Atomic write: write to `.tmp` file, then `os.rename()`
- `BayesianAdapter.__init__` accepts `state_path: Path | None = None`
- If `state_path` provided and file exists, load state on init
- After each successful `update_*` call, persist state to `state_path`
- Default state path: `.traderbot/adaptation_state.json`
- Profile-aware: when profile active, path becomes `profile.base_dir/adaptation_state.json`
- Handle corrupt/missing state file gracefully (log warning, start fresh)
- Include `_schema_version = 1` constant for migration support

**5. MUST NOT DO**

- Use pickle (security risk)
- Write state on every `_record_update()` call inside guard check methods
- Modify `risk/` module
- Change the mathematical behavior of any adaptation method
- Make state persistence required (must work without state_path for backward compat)

**6. CONTEXT**

- `simulation/adaptation.py` lines 393-463: `BayesianAdapter.__init__` and state tracking
- `_update_timestamps`: `list[datetime]` — needs ISO format serialization
- `_drift_counts`: `dict[str, int]` — directly serializable
- Distribution params are passed as method args, not stored on adapter — we need to persist the adapter's internal tracking state, not the full distributions (those are observation-driven)
- `heartbeat.py` line 225: creates `BayesianAdapter()` with no args — needs to pass state_path
- `profiles/isolation.py`: pattern for profile-aware paths

**Commit message**: `feat: add BayesianAdapter state persistence with atomic JSON writes`

**Pre-commit test**: `pytest tests/ -x -k "adaptation or adapter"`

**QA scenario**: 
1. `adapter = BayesianAdapter(state_path=Path("test_state.json"))`
2. Call `update_beta()` with observations
3. Create new `BayesianAdapter(state_path=Path("test_state.json"))`
4. Verify cooldown status preserved (second update should fail within cooldown)

---

### TODO-3: Demote Twitter Source and Document Stub

**1. TASK**

Move Twitter from first position in `_SOURCE_PRIORITY` to last. Add runtime warning when Twitter is the only configured source. Add `@deprecated`-style docstring marker to `_fetch_twitter()`.

**2. EXPECTED OUTCOME**

- `_SOURCE_PRIORITY` order: `NEWSAPI, REDDIT, TWITTER` (Twitter last)
- `_fetch_twitter()` has docstring clearly marking it as unimplemented stub
- CLI `news` command doesn't silently accept `--source twitter` as primary
- When all real sources fail and only Twitter remains, clear error message

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Change `_SOURCE_PRIORITY` in `news/sources.py` line 46: `[NewsSource.TWITTER, NewsSource.NEWSAPI, NewsSource.REDDIT]` → `[NewsSource.NEWSAPI, NewsSource.REDDIT, NewsSource.TWITTER]`
- Add docstring to `_fetch_twitter()`: `"STUB — not implemented. Returns empty list. Twitter/X API integration pending."`
- Add `logger.warning("Twitter source is a stub and returns no data")` when `fetch_recent(NewsSource.TWITTER)` is called
- In `fetch_all()`, after aggregating from all sources, if only Twitter returned items (unlikely since it's empty), log a specific warning
- Update `docs/news-sentiment.md` Source Priority section to reflect new order

**5. MUST NOT DO**

- Remove Twitter source entirely (still needed architecturally)
- Implement Twitter API integration
- Change the `NewsSource` enum

**6. CONTEXT**

- `news/sources.py` lines 46-49: `_SOURCE_PRIORITY` class variable
- `news/sources.py` lines 184-191: `_fetch_twitter()` stub
- `docs/news-sentiment.md` lines 126-133: Source Priority section
- CLI `news --source twitter` currently returns empty silently

**Commit message**: `fix: demote Twitter to last source priority, document as stub`

**Pre-commit test**: `pytest tests/ -x -k "source or Source"`

**QA scenario**: `traderbot news --source twitter --json` returns `[]` with a stderr warning about stub.

---

### TODO-4: ImpactWeights Validation Model

**1. TASK**

Extract the 5 impact weight constants from `impact_assessor.py` into a Pydantic model `ImpactWeights` with a `model_validator` enforcing they sum to 1.0 (within float tolerance). Use this model in `ImpactAssessor`.

**2. EXPECTED OUTCOME**

- New `ImpactWeights` Pydantic model in `news/impact_assessor.py`
- `ConfigDict(strict=True, extra="forbid")`
- Fields: `direct_relevance`, `source_authority`, `recency`, `market_sensitivity`, `corroboration` — all `Annotated[float, Field(gt=0, lt=1)]`
- `@model_validator(mode="after")` checks `abs(sum - 1.0) < 1e-6`
- Default instance matches current constants (0.30, 0.25, 0.20, 0.15, 0.10)
- `ImpactAssessor` accepts optional `weights: ImpactWeights` parameter
- All weight accesses go through the model instance

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Create `ImpactWeights` model with 5 fields and sum validator
- Default factory produces current weight values
- `ImpactAssessor.__init__` accepts `weights: ImpactWeights = Field(default_factory=ImpactWeights)`
- Replace all `WEIGHT_*` constant references in `assess()` with `self.weights.*`
- Keep the module-level constants as `DEFAULT_IMPACT_WEIGHTS` instance for backward compat
- Add test: `ImpactWeights(direct_relevance=0.5, ...)` where sum != 1.0 raises `ValidationError`

**5. MUST NOT DO**

- Change the default weight values
- Remove the module-level constants (keep as defaults reference)
- Use `float` equality check (use tolerance of `1e-6`)

**6. CONTEXT**

- `news/impact_assessor.py` lines 27-31: 5 weight constants
- `news/impact_assessor.py` lines 111-117: weighted sum computation in `assess()`
- Pydantic v2 `model_validator(mode="after")` pattern

**Commit message**: `feat: add ImpactWeights Pydantic model with sum=1.0 validation`

**Pre-commit test**: `pytest tests/ -x -k "impact or Impact or weight"`

**QA scenario**: Instantiate `ImpactWeights(direct_relevance=0.3, source_authority=0.25, recency=0.2, market_sensitivity=0.15, corroboration=0.1)` → success. Instantiate with sum=0.99 → ValidationError.

---

### TODO-5: Profile-Aware News Pipeline

**1. TASK**

Wire the news pipeline to use `ProfileAuthStore` for API key resolution and `TradingProfile.enabled_categories` for category filtering. Add profile-aware data isolation for cached news.

**2. EXPECTED OUTCOME**

- `NewsAggregator` resolves API keys via `ProfileAuthStore` when profile is active
- `NewsClassifier` filters against `profile.enabled_categories` when profile is set
- CLI `news` and `sentiment` commands detect active profile via `get_current_profile()`
- Category filtering rejects news not in profile's `enabled_categories`
- Profile-aware news cache path: `profile.base_dir/news_cache/`

**3. REQUIRED TOOLS**

- Read, Edit, Bash

**4. MUST DO**

- Import `get_current_profile` from `profiles/runtime.py` in CLI news/sentiment commands
- When profile is active, resolve NEWSAPI_KEY via `ProfileAuthStore` chain: `profile → global → env`
- Use `profiles/config.py` `resolve_credential()` pattern for API key resolution
- When profile has `enabled_categories`, filter classified items against it AFTER classification
- Add `category_filter: list[NewsCategory] | None = None` parameter to `NewsClassifier.classify()`
- When category_filter is set, items not matching are still classified but marked as `filtered_out`
- CLI `news --category` respects profile: if `--category X` not in profile.enabled_categories, error
- Default subreddits from profile config if available (future extension point)
- Update `news/__init__.py` to re-export any new public API

**5. MUST NOT DO**

- Modify `profiles/models.py` or `profiles/isolation.py` (they're done)
- Change the news pipeline behavior when no profile is active (backward compat)
- Add ChromaDB integration (out of scope)
- Modify risk/ module

**6. CONTEXT**

- `profiles/runtime.py`: `get_current_profile()` reads `TRADERBOT_PROFILE_TOKEN` env var
- `profiles/config.py`: credential resolution chain pattern
- `profiles/auth.py`: `ProfileAuthStore` with keyring namespaces
- `profiles/isolation.py`: `get_profile_*_path()` pattern for per-profile paths
- `cli.py` lines 686-850: `news` command — currently reads `NEWSAPI_KEY` from `os.environ`
- `cli.py` lines 853-1014: `sentiment` command — same pattern
- `news/classifier.py` line 297: `classify()` method — add optional filtering

**Commit message**: `feat: profile-aware news pipeline — API key resolution and category filtering`

**Pre-commit test**: `pytest tests/ -x -k "news or sentiment or profile"`

**QA scenario**: 
1. Create profile with `enabled_categories: [Economics]`
2. `TRADERBOT_PROFILE_TOKEN=<token> traderbot news --category sports --json` → error (category not in profile)
3. `traderbot news --category economics --json` → works

---

### TODO-6: Heartbeat Adaptation Persistence Wiring

**1. TASK**

Wire the `BayesianAdapter` persistence into the heartbeat cycle so `step_bayesian_adaptation()` creates an adapter with state_path and state survives across heartbeat runs.

**2. EXPECTED OUTCOME**

- `step_bayesian_adaptation()` creates `BayesianAdapter(state_path=state_path)` 
- State path is profile-aware: `.traderbot/adaptation_state.json` or `profile.base_dir/adaptation_state.json`
- CLI `heartbeat` command passes correct state path
- Heartbeat result includes persistence status

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Update `heartbeat.py` `step_bayesian_adaptation()` to accept `state_path: Path | None = None`
- When `state_path` provided, pass to `BayesianAdapter(state_path=state_path)`
- Default state path: `Path(".traderbot/adaptation_state.json")`
- Profile-aware path resolution using `get_current_profile()` if available
- Update `run_heartbeat_cycle()` to accept and pass through `state_path`
- Update CLI `heartbeat` command to compute and pass `state_path`
- Add `state_persisted: bool` field to `AdaptationReview` model
- Log WARNING if state path not writable

**5. MUST NOT DO**

- Change the mathematical behavior of adaptation
- Make state persistence mandatory (graceful degradation without state_path)
- Modify `risk/` module

**6. CONTEXT**

- `heartbeat.py` lines 198-253: `step_bayesian_adaptation()` creates adapter at line 225
- `heartbeat.py` lines 359-423: `run_heartbeat_cycle()` calls step_bayesian_adaptation at line 382
- `cli.py` lines 543-645: heartbeat command
- `profiles/isolation.py`: path resolution pattern

**Commit message**: `feat: wire adaptation state persistence into heartbeat cycle`

**Pre-commit test**: `pytest tests/ -x -k "heartbeat or adaptation"`

**QA scenario**: Run `traderbot heartbeat` twice. Second run should reflect state from first run (cooldown counter, update count).

---

### TODO-7: News Signal in analysis/signals.py

**1. TASK**

Add a `sentiment` signal source to `generate_signal()` in `analysis/signals.py`. This allows news sentiment to influence the combined signal alongside indicators, odds, and momentum.

**2. EXPECTED OUTCOME**

- `generate_signal()` accepts optional `news_sentiment: float | None = None` parameter
- When provided, creates a `SignalSource(name="sentiment", weight=0.15, ...)` 
- Default weights adjusted: `indicators: 0.30, odds: 0.50, momentum: 0.20` → `indicators: 0.25, odds: 0.45, momentum: 0.15, sentiment: 0.15`
- When `news_sentiment` is None, uses original 3-source weights
- Direction maps: positive sentiment → "yes", negative → "no", near-zero → "neutral"
- Strength = `abs(news_sentiment)` clamped to [0, 1]

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Add `news_sentiment: float | None = None` parameter to `generate_signal()`
- Add `sentiment` weight to `default_weights()` return dict (when sentiment available)
- Create separate `default_weights_no_sentiment()` for backward compat, or make `default_weights()` accept a flag
- Map sentiment score direction: `> 0.1 → "yes"`, `< -0.1 → "no"`, else `"neutral"`
- Strength: `min(abs(news_sentiment), 1.0)`
- Update docstring for `generate_signal()`
- Ensure backward compatibility: callers that don't pass `news_sentiment` get exactly the same results as before

**5. MUST NOT DO**

- Make `news_sentiment` required (breaks backward compat)
- Change the mathematical output for existing callers
- Call news API from within `generate_signal()` (news is external data, passed in)
- Modify risk/ module

**6. CONTEXT**

- `analysis/signals.py` lines 67-170: `generate_signal()` function
- `analysis/signals.py` lines 62-64: `default_weights()` — currently 3 sources
- `analysis/signals.py` lines 36-58: `combine_signals()` — unchanged, just gets 4 sources instead of 3
- Docs architecture: Decision Loop step 3 says "Cross-reference with sentiment signals"

**Commit message**: `feat: add news sentiment as 4th signal source in analysis/signals.py`

**Pre-commit test**: `pytest tests/ -x -k "signal"`

**QA scenario**: `generate_signal(ticker, prices, trades, orderbook, prob, news_sentiment=0.5)` returns a `CombinedSignal` with 4 sources including `sentiment`. `generate_signal(ticker, prices, trades, orderbook, prob)` (no sentiment) returns 3 sources, same as before.

---

### TODO-8: Update ROADMAP_PROGRESS.md

**1. TASK**

Update ROADMAP_PROGRESS.md to accurately reflect the implementation status of Phase 7 and Phase 8 components, fixing the incorrect "NOT STARTED" labels.

**2. EXPECTED OUTCOME**

- Phase 7 table shows existing components as "✅ Done (needs audit)" 
- Phase 8 table shows existing components with correct status
- "Last updated" version changed to v0.08.21
- Metrics snapshot updated
- Bug Class Taxonomy updated with new bug class: duplicate enum definitions

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Update Phase 7 table: sources, classifier, sentiment_scorer, impact_assessor all "✅ Done (needs audit+extension)"
- Add Phase 7 new components: embeddings.py, models.py, CLI news/sentiment commands
- Update Phase 8 table: BayesianAdapter "✅ Done (needs persistence)", heartbeat "✅ Done", learning "✅ Done"
- Add Phase 8 remaining work: persistence, profile-aware wire, news-signal integration
- Update "Last updated" to v0.08.21
- Update metrics snapshot: version, test count, CLI command count
- Add bug class: "Duplicate MarketCategory enum" — separate modules defining the same enum with different values
- Add bug class: "Float weights without sum validation"

**5. MUST NOT DO**

- Mark things as complete that aren't actually done
- Remove any existing content
- Change versioning scheme

**6. CONTEXT**

- `ROADMAP_PROGRESS.md` lines 148-169: Phase 7 and 8 sections marked "NOT STARTED"
- Phase 9 (line 202+) correctly marked "COMPLETE"
- Current version: v0.08.21

**Commit message**: `docs: update ROADMAP_PROGRESS.md to reflect actual Phase 7/8 implementation status`

**Pre-commit test**: `ruff check ROADMAP_PROGRESS.md` (or just verify file exists and is valid markdown)

**QA scenario**: Read through updated Phase 7/8 sections — all statuses match actual codebase state.

---

### TODO-9: Expand news/__init__.py Public API

**1. TASK**

Expand `news/__init__.py` to expose the full public API of the news module: all model classes, the aggregator, classifier, scorer, assessor, and VoyageClient.

**2. EXPECTED OUTCOME**

- `from traderbot.news import NewsAggregator, NewsClassifier, SentimentScorer, ImpactAssessor, VoyageClient, ...`
- All model classes re-exported: `NewsItem, NewsSource, NewsCategory, ClassifiedNews, SentimentResult, ImpactAssessment`
- `__all__` list is comprehensive
- Backward compat: existing `from traderbot.news import NewsAggregator, NewsItem, NewsSource` still works

**3. REQUIRED TOOLS**

- Read, Edit

**4. MUST DO**

- Add all public classes to `__init__.py` imports
- Update `__all__` list
- Ensure no circular imports (use lazy imports if needed)
- Re-export `NewsCategory` as alias for `MarketCategory` from kalshi/models.py (after TODO-1)

**5. MUST NOT DO**

- Import private/internal helpers
- Create circular dependencies
- Break existing import paths

**6. CONTEXT**

- `news/__init__.py` currently: 5 lines, exports `NewsAggregator, NewsItem, NewsSource` only
- `news/models.py`: `NewsSource, NewsCategory, NewsItem, SentimentResult, ImpactAssessment, ClassifiedNews`
- `news/classifier.py`: `NewsClassifier, ClassificationResult`
- `news/sentiment_scorer.py`: `SentimentScorer`
- `news/impact_assessor.py`: `ImpactAssessor, ImpactWeights` (after TODO-4)
- `news/embeddings.py`: `VoyageClient`

**Commit message**: `refactor: expand news/__init__.py to expose full public API`

**Pre-commit test**: `python -c "from traderbot.news import NewsAggregator, NewsClassifier, SentimentScorer, ImpactAssessor, NewsItem, NewsCategory"`

**QA scenario**: Import all classes from `traderbot.news` in a Python shell — no errors.

---

### TODO-10: Comprehensive Tests

**1. TASK**

Write tests covering all new code and changed behavior from TODOs 1-9. Tests for enum normalization, adaptation persistence, ImpactWeights validation, profile-aware news, and signal integration.

**2. EXPECTED OUTCOME**

- `tests/test_market_category_unified.py`: enum import paths, value consistency, StrEnum behavior
- `tests/test_adapter_state.py`: save/load cycle, corrupt file recovery, atomic writes
- `tests/test_impact_weights.py`: valid/invalid weights, sum validation, default values
- `tests/test_profile_news.py`: API key resolution, category filtering, isolation
- `tests/test_news_signals.py`: sentiment signal source in generate_signal, backward compat
- `tests/test_news_cli.py`: CLI smoke tests for news/sentiment commands with mocks
- All tests pass with `pytest tests/ -x`

**3. REQUIRED TOOLS**

- Read, Edit, Write, Bash

**4. MUST DO**

- Test MarketCategory enum: `MarketCategory.ECONOMICS.value == "economics"`, import from both modules gives same class
- Test ImpactWeights: valid defaults, sum validation, individual field constraints
- Test adapter state: save→load roundtrip, corrupt JSON recovery, missing file → fresh start
- Test profile news: mock `get_current_profile()`, verify API key chain, category rejection
- Test signals: `generate_signal()` with and without `news_sentiment`, verify 3 vs 4 sources
- Test CLI smoke: `traderbot news --source reddit --json` with mocked NewsAggregator
- Test Twitter demotion: `_SOURCE_PRIORITY` order, stub warning
- All Pydantic tests use `ConfigDict(strict=True, extra="forbid")` where applicable

**5. MUST NOT DO**

- Test internal/private methods (test public API)
- Make tests dependent on external APIs (mock everything)
- Skip edge cases for adaptation persistence (corrupt files, permission errors)

**6. CONTEXT**

- Test directory: `tests/`
- Existing test patterns: `tests/test_simulation_integration.py`, `tests/test_learning_integration.py`
- Mock patterns: `unittest.mock.AsyncMock` for httpx, `monkeypatch` for env vars
- Profile test patterns: `tests/profiles/`

**Commit message**: `test: comprehensive tests for Phase 7+8 audit, persistence, and wiring`

**Pre-commit test**: `pytest tests/ -x --tb=short`

**QA scenario**: Full test suite green. `pytest tests/ --cov=traderbot.news --cov=traderbot.simulation --cov=traderbot.analysis` shows no coverage regressions.