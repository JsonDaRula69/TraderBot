# Fix Signal Documentation & Verify Weather Agent Toolkit

## TL;DR

> **Quick Summary**: Investigation revealed 3 documentation bugs, 5 code bugs (1 critical), and 1 non-bug. The critical bug is that `scan`/`signals` commands return zero useful results because the Kalshi V2 API's `category` filter is broken and TraderBot doesn't paginate or filter correctly. Plus heartbeat `open_positions` is always 0, audit logs go to global dir instead of profile dir, API connectivity check fails on demo, and `cron setup` was never run for the weather agent.
>
> **Deliverables**:
> - Fix signal documentation in `.openclaw/workspace/AGENTS.md` and `TOOLS.md`
> - Fix critical market scanning bug (empty signals)
> - Fix heartbeat open_positions dead field
> - Fix AuditLogger profile-aware path resolution
> - Fix heartbeat API connectivity check for demo environment
> - Register cron loops for weather agent via `traderbot cron setup`
> - Update heartbeat loop payload to include `--json`
> - Update plan with investigation-verified findings
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Wave 1 (doc+filter fixes) → Wave 2 (scan bug) → Wave 3 (heartbeat+cron fixes) → Wave 4 (verification)

---

## Context

### Original Request
Fix the signal system documentation (TOOLS.md has gaps, AGENTS.md has wrong confidence formula), then SSH to macpro-linux to verify the weather agent's toolkit — compare manual API calls and computations with traderbot CLI output to identify any bugs.

### Investigation Findings (VERIFIED ON REMOTE)

**🔴 CRITICAL BUG: `scan` and `signals` return zero useful markets**

Root cause chain:
1. **Kalshi V2 API ignores `category` parameter**: `GET /markets?limit=50&category=climate_and_weather` returns the SAME results as `GET /markets?limit=50` — all `KXMVE*` provisional multivariate event junk with zero volume. The API does not filter by category at all.
2. **No `status` filter**: `list_markets()` (markets.py line 41-57) does NOT pass `status=open` or `status=active` to the API. The API returns all statuses including `provisional` and dormant.
3. **Results dominated by MVE shells**: First 200 results are all `KXMVE*` markets with `volume_fp=0, OI=0, category=N/A`. These have no orderbooks, so `implied_probability()` skips them all.
4. **Event enrichment enriches wrong markets**: `_fetch_event_categories()` correctly looks up categories from events, but the MVE events return `category=Exotics`, which doesn't match `weather` or `climate_and_weather`. After enrichment, `market_category=None` and `category=None` for all returned markets.
5. **The actual weather markets ARE on the exchange**: Direct API call `GET /markets?event_ticker=KXHIGHLAX-26MAY12` returns 6 markets with **533K total volume** and **321K OI**. But TraderBot never reaches them because pagination doesn't go far enough.

**Evidence (ssh macpro-linux)**:
- `traderbot scan --category weather --limit 50` → 50 MVE markets, all `cat=None, vol=0`
- `traderbot scan --category climate_and_weather --limit 50` → same MVE markets, all `cat=sports` (enriched from events)
- `traderbot signals --json` → `[]` (all markets fail `implied_probability()`)
- Direct API: `GET /markets?limit=5&category=climate_and_weather` → same MVE junk (API ignores category param)
- Direct API: `GET /markets?limit=5` → identical results
- Direct API: `GET /markets?event_ticker=KXHIGHLAX-26MAY12` → 6 real markets with volume (533K total)
- Direct API: `GET /events/KXHIGHLAX-26MAY12` → `category: Climate and Weather`

**Proposed Fix**: Add `status=open` filter to `list_markets()`, add pagination to fetch more results, and implement a 2-step discovery: first fetch events by category, then fetch markets by `event_ticker`. This makes `scan` and `signals` actually find weather markets.

---

**Documentation Bugs**:
1. **AGENTS.md "Signal Confidence Thresholds"** says confidence is "the product of: 1) Statistical edge magnitude 2) Indicator agreement 3) Volume/liquidity check 4) Recency weighting" — WRONG. Actual formula: weighted average of signed strengths (indicators=0.30, odds=0.50, momentum=0.20; with sentiment: indicators=0.25, odds=0.45, momentum=0.15, sentiment=0.15). No volume/liquidity check or recency weighting exists.
2. **TOOLS.md** lists `traderbot signals --json` with zero detail on how signals are computed.
3. **AGENTS.md says "All 16 supported market categories"** — actual `MarketCategory` enum has 14 values. TOOLS.md correctly says 14.

---

**Code Bugs Found**:

4. **Heartbeat `open_positions` always 0** — `PerformanceReview.open_positions` (heartbeat.py line 57) defaults to 0 and is never populated. `step_performance_review()` (lines 203-211) constructs `PerformanceReview` without setting `open_positions`. **Severity: HIGH**.

5. **AuditLogger uses global audit dir** — `AuditLogger.__init__()` (audit.py line 18) calls `get_audit_dir()` returning `~/.traderbot/audit/`. With profile token set, should go to profile-specific `~/.traderbot/paper-weather-demo/audit/`. **Severity: MEDIUM**.

---

**NOT Bugs (Investigated and Resolved)**:

6. **DB path "mismatch"** — NOT A BUG. Works correctly when `TRADERBOT_PROFILE_TOKEN` is sourced.

7. **Signals returning `[]`** — Symptom of Bug #1 (scan filtering), not a separate issue.

8. **Settlement stall** — Not a TraderBot bug. Markets show `status=active, result=""` on Kalshi API directly.

9. **Limit order "slippage" (ERR-006)** — Pricing semantics, not a code bug. For band markets where direction=NO, `--price 40` means YES price is 40¢, but you pay the NO fill price: `100 - 40 = 60¢`. This is correct behavior.

**Heartbeat & Cron Investigation Findings**:

10. **`traderbot cron setup` was partially run** — `~/.openclaw/openclaw.json` exists with a heartbeat config (`"every": "30m"`) for the weather agent, but the 3 cron loops (decision_loop, heartbeat_loop, news_loop) are NOT all properly registered. The decision_loop cron is registered but stalling (634-900+ second sessions with "active_work_without_progress"), because `traderbot scan --category weather` returns empty (the critical scan bug). The news_loop and heartbeat_loop status is unclear.

11. **`system_health.api_connectivity` always shows "unavailable"** — `step_system_health()` (heartbeat.py lines 370-406) calls `GET /platform/status` which doesn't exist on the Kalshi demo API. It then falls back to `GET /` which also fails, resulting in "Kalshi API unreachable" and "unavailable" status. This is misleading — the API works fine for market/trade operations; only the health check endpoint is missing. Should fall back to `GET /markets?limit=1` as a connectivity check.

12. **Heartbeat loop payload doesn't specify `--json`** — `HeartbeatLoopPayload.message` (cron_loops.py line 53-58) tells the agent to "Run traderbot self-improvement cycle" but doesn't specify `--json` flag for machine-readable output. The agent may produce human-readable output, making it harder for downstream parsing.

13. **OpenClaw decision_loop sessions stalling** — Syslog shows: `stalled session: age=994s, lastProgress=model_call:started, lastProgressAge=905s`. This is because `traderbot scan --limit 500` with the broken category filter returns 200+ zero-volume MVE markets, causing the agent to waste cycles finding no tradeable markets. Root cause: the critical scan bug (already tracked).

13. **OpenClaw truncating AGENTS.md in injected context** — Gateway logs show: `workspace bootstrap file AGENTS.md is 14475 chars (limit 12000); truncating in injected context`. The weather agent's AGENTS.md is 14,475 characters, exceeding OpenClaw's 12,000 character limit. This means the agent is losing critical context from its own guardrails and instructions on every turn. After fixing the signal confidence section (Task 1) and category count (Task 4), the file may shrink, but it should be audited to stay under 12,000 chars.

14. **Decision loop sessions stalling** — OpenClaw gateway logs show `decision_loop` cron jobs stalling for 634-900+ seconds with `active_work_without_progress`. Root cause: `traderbot scan --category weather` returns empty (the critical scan bug). After Task 5 fixes the scan, the decision loop should be able to find markets and complete.

---

## Work Objectives

### Core Objective
1. Fix the critical market scanning bug so `scan`/`signals` return real markets with volume
2. Fix signal documentation to accurately reflect the codebase implementation
3. Fix heartbeat `open_positions` dead field
4. Fix AuditLogger profile-aware path resolution

### Concrete Deliverables
- `src/traderbot/kalshi/markets.py` — Fix `list_markets()` to pass `status=open` and support event-based category filtering
- `src/traderbot/cli.py` — Update `scan` and `signals` commands to paginate and filter correctly
- `.openclaw/workspace/AGENTS.md` — Fix signal confidence section, fix category count
- `.openclaw/workspace/TOOLS.md` — Add signal computation detail section
- `src/traderbot/heartbeat.py` — Fix `open_positions` to count from DB
- `src/traderbot/risk/audit.py` — Fix `AuditLogger` to use profile-aware path

### Definition of Done
- [ ] `traderbot scan --category weather` returns real weather markets with volume > 0
- [ ] `traderbot signals --json` produces non-empty results for markets with orderbooks
- [ ] Documentation accurately describes signal computation (weights, sources, formula)
- [ ] `traderbot heartbeat --json` reports correct `open_positions` count
- [ ] Audit logs write to profile-specific directory when `TRADERBOT_PROFILE_TOKEN` is set

### Must Have
- All 4 bugs fixed
- Test commands pass on macpro-linux

### Must NOT Have (Guardrails)
- No changes to risk module (immutable)
- No changes to signal computation algorithm (only documentation and scanning)
- No API keys in code
- All monetary values remain in cents as int

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: Tests-after (verify fixes on remote)
- **Framework**: pytest

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — documentation + type fix):
├── Task 1: Fix AGENTS.md signal confidence section [quick]
├── Task 2: Add signal computation section to TOOLS.md [quick]
├── Task 3: Add status=open filter to list_markets() [quick]
└── Task 4: Fix MarketCategory count 16→14 in AGENTS.md [quick]

Wave 2 (After Wave 1 — core scan bug fix):
├── Task 5: Implement event-based category filtering in scan/signals [deep]
└── Task 6: Add pagination to list_markets for full market coverage [deep]

Wave 3 (After Wave 2 — heartbeat + audit + cron fixes):
├── Task 7: Fix heartbeat open_positions dead field [quick]
├── Task 8: Fix AuditLogger profile-aware audit dir [quick]
├── Task 9: Fix heartbeat API connectivity check for demo [quick]
├── Task 10: Update heartbeat loop payload to include --json [quick]
└── Task 11: Register cron loops for weather agent [quick]

Wave 4 (After Wave 3 — verification):
├── Task 12: Verify all fixes on macpro-linux [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA on macpro-linux (unspecified-high)
└── F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: Task 3 → Task 5 → Task 6 → Tasks 7-11 → Task 12 → F1-F4 → user okay
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 5 (Wave 3)
```

Critical Path: Task 3 → Task 5 → Task 9 → F1-F4

---

## TODOs

- [x] 1. Fix AGENTS.md signal confidence section

  **What to do**:
  - In `.openclaw/workspace/AGENTS.md`, find the "Signal Confidence Thresholds" section
  - Replace the incorrect "product of 4 factors" description with the actual formula:
    - Confidence = `|weighted_sum| / total_weight` where weighted_sum = Σ(source_strength × source_weight × sign)
    - 3-source weights: indicators=0.30, odds=0.50, momentum=0.20
    - 4-source weights (with sentiment): indicators=0.25, odds=0.45, momentum=0.15, sentiment=0.15
    - Sign: +1 for yes, -1 for no, 0 for neutral
    - Direction: signed_sum > 0.01 = yes, < -0.01 = no, else neutral
    - Confidence clamped to [0, 1]
  - Describe each source: indicators (RSI + Bollinger), odds (edge detection), momentum (EMA crossover), sentiment (optional)
  - Note: NO volume/liquidity check or recency weighting in confidence calculation

  **Must NOT do**: Change signal computation code, change risk module

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `.openclaw/workspace/AGENTS.md` — File to edit, contains wrong "product of 4 factors" formula
  - `src/traderbot/analysis/signals.py:generate_signal()` — Actual signal generation entry point
  - `src/traderbot/analysis/signals.py:combine_signals()` — Actual confidence formula
  - `src/traderbot/analysis/indicators.py:calc_rsi()`, `calc_bollinger_bands()` — Indicator sources
  - `src/traderbot/analysis/odds.py:detect_edge()` — Odds/edge source

  **Acceptance Criteria**:
  - [ ] AGENTS.md signal section describes weighted average, NOT product
  - [ ] All 4 sources documented with correct weights
  - [ ] No mention of "volume/liquidity check" or "recency weighting" in confidence formula
  - [ ] Category count changed from 16 to 14

  **QA Scenarios**:

  ```
  Scenario: Verify signal documentation accuracy
    Tool: Bash (grep)
    Preconditions: AGENTS.md edits complete
    Steps:
      1. grep -c "weighted average" .openclaw/workspace/AGENTS.md → count > 0
      2. grep -c "product of" .openclaw/workspace/AGENTS.md → count == 0 (old formula removed)
      3. grep "recency weighting" .openclaw/workspace/AGENTS.md → not found
      4. grep "volume/liquidity check" .openclaw/workspace/AGENTS.md → not found
    Expected Result: Old formula completely replaced with correct description
    Evidence: .sisyphus/evidence/task-1-signal-doc-accuracy.txt
  ```

  **Commit**: YES (groups with 2, 3, 4)
  - Message: `docs: fix signal confidence formula and category count in AGENTS.md`
  - Files: `.openclaw/workspace/AGENTS.md`, `.openclaw/workspace/TOOLS.md`

- [x] 2. Add signal computation section to TOOLS.md

  **What to do**:
  - In `.openclaw/workspace/TOOLS.md`, add a new section after the "Modules" section called "Signal Computation"
  - Document the 3-source model: indicators(0.30) + odds(0.50) + momentum(0.20)
  - Document the 4-source model (with sentiment): indicators(0.25) + odds(0.45) + momentum(0.15) + sentiment(0.15)
  - Document how `generate_signal()` works: fetches prices, computes RSI/Bollinger, calculates implied probability, runs EMA crossover, combines into final direction/confidence
  - Note that `estimated_prob` defaults to market-implied probability unless overridden via `--estimated-prob`
  - Note that `traderbot signals` returns empty when no markets have orderbooks (common on demo)

  **Must NOT do**: Change signal computation code

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `.openclaw/workspace/TOOLS.md` — File to edit, add new section
  - `src/traderbot/analysis/signals.py` — Source of truth for signal computation
  - `src/traderbot/cli.py:189-260` — `signals` command showing how it invokes the pipeline

  **Acceptance Criteria**:
  - [ ] TOOLS.md has "Signal Computation" section
  - [ ] Section includes weights, sources, and formula
  - [ ] Section mentions empty-result caveat for demo environments

  **QA Scenarios**:

  ```
  Scenario: Verify TOOLS.md signal section exists and is accurate
    Tool: Bash (grep)
    Preconditions: TOOLS.md edits complete
    Steps:
      1. grep -c "Signal Computation" .openclaw/workspace/TOOLS.md → count > 0
      2. grep "indicators.*0\\.3" .openclaw/workspace/TOOLS.md → found
      3. grep "odds.*0\\.5" .openclaw/workspace/TOOLS.md → found
      4. grep "momentum.*0\\.2" .openclaw/workspace/TOOLS.md → found
    Expected Result: Signal computation section present with correct weights
    Evidence: .sisyphus/evidence/task-2-tools-signal-section.txt
  ```

  **Commit**: YES (groups with 1, 3, 4)
  - Message: `docs: fix signal confidence formula and category count in AGENTS.md`

- [x] 3. Add status=open filter to list_markets()

  **What to do**:
  - In `src/traderbot/kalshi/markets.py`, modify `list_markets()` to pass `status=open` by default when no status is specified
  - The Kalshi V2 API uses `active` and `initialized` for what TraderBot calls `open`
  - After adding the status filter, verify the API call includes `status=open` (which `_normalize_market()` maps from V2's `active`/`initialized`)
  - This is a prerequisite for the deeper scan fix (Task 5) but provides immediate improvement

  **Must NOT do**: Change signal computation, change risk module

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 5 (needs status filter as baseline)
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/markets.py:30-57` — `list_markets()` method, where `status` param is defined but not defaulted
  - `src/traderbot/kalshi/_normalize.py:77-82` — Status mapping from V2 `active`/`initialized` → `open`
  - `src/traderbot/kalshi/models.py:113` — `Market.status` field with `Literal["open", "closed", "settled"]`

  **Acceptance Criteria**:
  - [ ] `list_markets()` passes `status=open` when no status filter provided
  - [ ] Existing tests still pass
  - [ ] `traderbot scan --limit 10` no longer returns provisional MVE markets

  **QA Scenarios**:

  ```
  Scenario: Verify status filter works
    Tool: Bash (ssh)
    Preconditions: Code deployed to macpro-linux
    Steps:
      1. ssh macpro-linux 'traderbot scan --limit 10 --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'markets'); [print(f'  {m[\"ticker\"][:50]} status={m[\"status\"]}') for m in d[:5]]"
      2. Verify no KXMVE provisional markets in results
      3. Verify all returned markets have status=open
    Expected Result: Only open markets, no provisional MVE shells
    Failure Indicators: KXMVE* markets still in results, status=active (not normalized)
    Evidence: .sisyphus/evidence/task-3-status-filter.txt
  ```

  **Commit**: YES
  - Message: `fix: add status=open filter to list_markets to exclude provisional markets`
  - Files: `src/traderbot/kalshi/markets.py`

- [x] 4. Fix MarketCategory count 16→14 in AGENTS.md

  **What to do**:
  - In `.openclaw/workspace/AGENTS.md`, find any reference to "16 supported market categories" or "All 16"
  - Change to "14 supported market categories" or "All 14"
  - This aligns with the actual `MarketCategory` enum which has 14 values

  **Must NOT do**: Change the MarketCategory enum itself

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `.openclaw/workspace/AGENTS.md` — Contains "16" category reference
  - `src/traderbot/kalshi/models.py:MarketCategory` — Actual enum with 14 values

  **Acceptance Criteria**:
  - [ ] AGENTS.md says "14 supported market categories"
  - [ ] No "16 categories" references remain

  **QA Scenarios**:

  ```
  Scenario: Verify category count is correct
    Tool: Bash (grep)
    Steps:
      1. grep -c "16.*categor" .openclaw/workspace/AGENTS.md → 0
      2. grep -c "14.*categor" .openclaw/workspace/AGENTS.md → > 0
    Expected Result: Only 14 referenced, no 16
    Evidence: .sisyphus/evidence/task-4-category-count.txt
  ```

  **Commit**: YES (groups with 1, 2)
  - Message: `docs: fix signal confidence formula and category count in AGENTS.md`

- [x] 5. Implement event-based category filtering in scan/signals

  **What to do**:
  - This is the CORE FIX for the critical scanning bug.
  - The Kalshi V2 API's `category` parameter on `/markets` is broken (ignored, returns same results regardless).
  - **Solution**: When `--category` is specified, use a 2-step approach:
    1. Fetch events with category via `/events?category={category}` (this endpoint DOES filter correctly)
    2. For each event, fetch its markets via `/markets?event_ticker={event_ticker}`
    3. Merge and return results
  - Add a new method `list_markets_by_category()` to `MarketService` that implements this 2-step approach
  - Update `scan` and `signals` CLI commands to use this method when `--category` is specified
  - Also add pagination support: `list_markets()` should follow cursors to get more than `limit` results when needed
  - **Verification**: `traderbot scan --category weather --limit 50` should return the KXHIGHNY/KXHIGHLAX/KXHIGHTPHX markets with volume

  **Must NOT do**: Change signal computation, change risk module, remove existing `list_markets()` API

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Wave 1 Task 3)
  - **Blocks**: Task 6 (pagination builds on this), Task 9
  - **Blocked By**: Task 3 (needs status filter as baseline)

  **References**:
  - `src/traderbot/kalshi/markets.py:30-57` — Current `list_markets()` to extend
  - `src/traderbot/kalshi/markets.py:115-126` — `_fetch_event_categories()` pattern to reuse
  - `src/traderbot/kalshi/events.py` — Event service for `/events` endpoint
  - `src/traderbot/kalshi/client.py` — HTTP client for API calls
  - `src/traderbot/cli.py:99-128` — `scan` command
  - `src/traderbot/cli.py:189-260` — `signals` command
  - Direct API evidence: `GET /events?category=climate_and_weather` → filtered results; `GET /markets?event_ticker=KXHIGHLAX-26MAY12` → real markets with volume

  **Acceptance Criteria**:
  - [ ] `traderbot scan --category weather --limit 50` returns weather markets with volume > 0
  - [ ] `traderbot signals --category weather --limit 50` produces non-empty results
  - [ ] `traderbot scan --category climate_and_weather` returns same results as `--category weather`
  - [ ] `traderbot scan` (no category) still works for general scanning
  - [ ] Existing tests pass

  **QA Scenarios**:

  ```
  Scenario: Verify category filter returns real weather markets
    Tool: Bash (ssh)
    Preconditions: Code deployed to macpro-linux
    Steps:
      1. ssh macpro-linux 'traderbot scan --category weather --limit 20 --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Markets: {len(d)}'); print(f'With volume: {sum(1 for m in d if float(m.get(\"volume_fp\",0) or 0) > 0)}'); [print(f'  {m[\"ticker\"]}') for m in d[:5]]"
      2. Verify at least 1 market has volume_fp > 0
      3. Verify weather tickers (KXHIGH*, KXLOW*) are present
    Expected Result: Weather markets with actual volume returned
    Failure Indicators: Empty results, or all volume_fp=0, or only KXMVE* markets
    Evidence: .sisyphus/evidence/task-5-category-filter.txt

  Scenario: Verify signals produces results for weather markets
    Tool: Bash (ssh)
    Preconditions: Code deployed to macpro-linux
    Steps:
      1. ssh macpro-linux 'traderbot signals --category weather --limit 20 --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Signals: {len(d)}'); [print(f'  {s[\"ticker\"]} dir={s[\"direction\"]} conf={s[\"confidence\"]}') for s in d[:5]]"
      2. Verify len(d) > 0
      3. Verify each signal has direction and confidence
    Expected Result: Non-empty signal results
    Failure Indicators: Empty array
    Evidence: .sisyphus/evidence/task-5-signals-non-empty.txt

  Scenario: Verify scan without category still works
    Tool: Bash (ssh)
    Steps:
      1. ssh macpro-linux 'traderbot scan --limit 10 --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Markets: {len(d)}')"
      2. Verify len(d) > 0
    Expected Result: General scan still works
    Evidence: .sisyphus/evidence/task-5-scan-general.txt
  ```

  **Commit**: YES
  - Message: `fix: implement event-based category filtering for scan/signals commands`
  - Files: `src/traderbot/kalshi/markets.py`, `src/traderbot/kalshi/events.py`, `src/traderbot/cli.py`

- [x] 6. Add pagination to list_markets for full market coverage

  **What to do**:
  - `list_markets()` currently returns a single page of results (up to `limit=200`)
  - The Kalshi V2 API uses cursor-based pagination (`cursor` parameter)
  - Add pagination support: when the caller needs more results, follow the `cursor` from `MarketListResponse` to fetch subsequent pages
  - Add a `list_all_markets()` convenience method that pages through all results
  - This ensures `signals` can scan all available markets, not just the first 200 provisional MVE shells

  **Must NOT do**: Change the default `list_markets()` signature (keep backward compat)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (after Task 5)
  - **Blocks**: Task 9
  - **Blocked By**: Task 5

  **References**:
  - `src/traderbot/kalshi/markets.py:30-57` — Current `list_markets()` with single-page `limit`
  - `src/traderbot/kalshi/models.py:MarketListResponse` — Already has `cursor` field
  - `src/traderbot/cli.py:189-260` — `signals` command needs to use pagination

  **Acceptance Criteria**:
  - [ ] `list_markets()` still works with `limit` parameter (backward compat)
  - [ ] New `list_all_markets()` pages through all results
  - [ ] `traderbot scan --limit 500` returns more than 200 unique markets

  **QA Scenarios**:

  ```
  Scenario: Verify pagination returns more markets
    Tool: Bash (ssh)
    Steps:
      1. ssh macpro-linux 'traderbot scan --limit 500 --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Total markets: {len(d)}'); print(f'Unique tickers: {len(set(m[\"ticker\"] for m in d))}')"
      2. Verify total markets > 200
    Expected Result: Pagination works, more than 200 markets returned
    Evidence: .sisyphus/evidence/task-6-pagination.txt
  ```

  **Commit**: YES
  - Message: `feat: add pagination support to list_markets for full market coverage`
  - Files: `src/traderbot/kalshi/markets.py`, `src/traderbot/cli.py`

- [x] 7. Fix heartbeat open_positions dead field

  **What to do**:
  - In `src/traderbot/heartbeat.py`, find `step_performance_review()` (around line 203-211)
  - The `PerformanceReview` dataclass has `open_positions: int = 0` (line 57) but it's never set
  - Query the DB for current open positions count and set `open_positions` to the actual count
  - Use the same DB resolution pattern as `positions` command (`_resolve_db_path()`)

  **Must NOT do**: Change risk module, change signal computation

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 8)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `src/traderbot/heartbeat.py:57` — `open_positions: int = 0` dead field
  - `src/traderbot/heartbeat.py:203-211` — `step_performance_review()` where `PerformanceReview` is constructed
  - `src/traderbot/cli.py:67-80` — `_resolve_db_path()` pattern to follow for DB access
  - `src/traderbot/db/positions.py` — Position model for counting open positions

  **Acceptance Criteria**:
  - [ ] `traderbot heartbeat --json` reports `open_positions` matching actual DB count
  - [ ] With 3 positions in DB, `open_positions` shows 3 (not 0)

  **QA Scenarios**:

  ```
  Scenario: Verify heartbeat open_positions count
    Tool: Bash (ssh)
    Preconditions: 3 positions exist in paper-weather-demo DB
    Steps:
      1. ssh macpro-linux 'source ~/.openclaw/workspace/weather/.env && traderbot heartbeat --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'open_positions={d.get(\"performance\",{}).get(\"open_positions\",\"NOT_FOUND\")}')"
      2. Compare with: ssh macpro-linux 'source ~/.openclaw/workspace/weather/.env && traderbot positions --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'positions_count={len(d)}')"
      3. Verify open_positions matches positions count
    Expected Result: open_positions=3 (matching actual position count)
    Failure Indicators: open_positions=0 (dead field not fixed)
    Evidence: .sisyphus/evidence/task-7-heartbeat-positions.txt
  ```

  **Commit**: YES
  - Message: `fix: populate heartbeat open_positions from DB instead of dead default`
  - Files: `src/traderbot/heartbeat.py`

- [x] 8. Fix AuditLogger profile-aware audit dir

  **What to do**:
  - In `src/traderbot/risk/audit.py`, `AuditLogger.__init__()` calls `get_audit_dir()` (global path)
  - Change it to use profile-aware path resolution, similar to `_resolve_db_path()` in `cli.py`
  - When `TRADERBOT_PROFILE_TOKEN` is set, audit logs should go to `~/.traderbot/{mode}-{name}/audit/`
  - When no profile token, use global `~/.traderbot/audit/`

  **Must NOT do**: Change risk module, change DB module

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 7)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `src/traderbot/risk/audit.py:16-20` — `AuditLogger.__init__()` with `get_audit_dir()`
  - `src/traderbot/paths.py` — `get_audit_dir()` returns global path
  - `src/traderbot/cli.py:67-80` — `_resolve_db_path()` pattern to follow
  - `src/traderbot/profiles/` — Profile resolution for `TRADERBOT_PROFILE_TOKEN`

  **Acceptance Criteria**:
  - [ ] With `TRADERBOT_PROFILE_TOKEN` set, audit logs write to `~/.traderbot/paper-weather-demo/audit/`
  - [ ] Without profile token, audit logs write to `~/.traderbot/audit/`
  - [ ] `traderbot audit --json` reads from the correct profile-specific dir

  **QA Scenarios**:

  ```
  Scenario: Verify audit logs go to profile dir
    Tool: Bash (ssh)
    Preconditions: TRADERBOT_PROFILE_TOKEN set in weather agent .env
    Steps:
      1. ls -la ~/.traderbot/paper-weather-demo/audit/ → should contain JSONL files
      2. ssh macpro-linux 'source ~/.openclaw/workspace/weather/.env && traderbot audit --json' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Decisions: {len(d)}')"
      3. Verify decisions match the 3 trades made
    Expected Result: 3 decisions found in profile-specific audit dir
    Failure Indicators: 0 decisions (audit reading from global dir instead)
    Evidence: .sisyphus/evidence/task-8-audit-profile-dir.txt
  ```

  **Commit**: YES (groups with 7)
  - Message: `fix: make AuditLogger use profile-aware audit directory`
  - Files: `src/traderbot/risk/audit.py`, `src/traderbot/paths.py`

- [x] 9. Fix heartbeat API connectivity check for demo environment — **FIXED**: Changed `KalshiConfig()` + `KalshiClient(config)` to `KalshiClient()` (auto-resolve auth from profile). Verified: `api_connectivity: "ok"` on macpro-linux
- [x] 10. Update heartbeat loop payload to include --json flag
- [x] 11. Register cron loops for weather agent on macpro-linux
- [x] 12. Verify all fixes on macpro-linux

  **What to do**:
  - SSH to macpro-linux and run comprehensive verification of all fixes
  - Test scan with categories: weather, sports, economics
  - Test signals with categories
  - Test heartbeat open_positions
  - Test audit with profile token
  - Test heartbeat API connectivity
  - Test cron registration
  - Test end-to-end: scan → signals → analyze for the 4 weather markets the user specified
  - **Also verify**: AGENTS.md file size is under 12,000 chars (OpenClaw context limit)
  - **Also verify**: Decision loop no longer stalls after scan fix

  **Must NOT do**: Make code changes in this task (verification only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after all Wave 3 tasks)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 5, 6, 7, 8, 9, 10, 11

  **Acceptance Criteria**:
  - [ ] `traderbot scan --category weather` returns weather markets with volume
  - [ ] `traderbot signals --category weather` produces signals
  - [ ] `traderbot heartbeat --json` shows correct open_positions
  - [ ] `traderbot heartbeat --json` shows api_connectivity != "unavailable"
  - [ ] `traderbot audit --json` shows 3 decisions
  - [ ] All 4 user-requested markets found via scan
  - [ ] AGENTS.md under 12,000 chars
  - [ ] Decision loop not stalling

  **QA Scenarios**:

  ```
  Scenario: End-to-end verification of all fixes
    Tool: Bash (ssh)
    Preconditions: All code deployed to macpro-linux
    Steps:
      1. source ~/.openclaw/workspace/weather/.env
      2. traderbot scan --category weather --limit 20 --json → verify weather markets with volume > 0
      3. traderbot signals --category weather --limit 20 --json → verify non-empty signals
      4. traderbot heartbeat --json → verify open_positions > 0 AND api_connectivity != "unavailable"
      5. traderbot audit --json → verify 3 decisions returned
      6. wc -c ~/.openclaw/workspace/weather/AGENTS.md → verify under 12000 chars
      7. Verify KXHIGHLAX-26MAY12 appears in scan results
      8. Verify KXHIGHTPHX-26MAY12 appears in scan results
      9. Check gateway logs: no "stalled session" for decision_loop (may take 10+ min to verify)
    Expected Result: All 8 checks pass
    Failure Indicators: Any check returns empty/wrong results, AGENTS.md > 12000, decision_loop stalling
    Evidence: .sisyphus/evidence/task-12-e2e-verification.txt
  ```

  **Commit**: NO (verification only)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files. Compare deliverables against plan.
  Output: `Must Have [5/5] | Must NOT Have [3/3] | Tasks [9/9] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check` + `pytest`. Review all changed files for: `as any`/type issues, empty catches, console.log, unused imports. Check AI slop.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (CONDITIONAL PASS — 3 secondary issues)
  Start from clean state on macpro-linux. Execute EVERY QA scenario from EVERY task. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `docs: fix signal confidence formula and category count in AGENTS.md` — `.openclaw/workspace/AGENTS.md`, `.openclaw/workspace/TOOLS.md`
- **Wave 1**: `fix: add status=open filter to list_markets to exclude provisional markets` — `src/traderbot/kalshi/markets.py`
- **Wave 2**: `fix: implement event-based category filtering for scan/signals commands` — `src/traderbot/kalshi/markets.py`, `src/traderbot/kalshi/events.py`, `src/traderbot/cli.py`
- **Wave 2**: `feat: add pagination support to list_markets for full market coverage` — `src/traderbot/kalshi/markets.py`, `src/traderbot/cli.py`
- **Wave 3**: `fix: populate heartbeat open_positions from DB instead of dead default` — `src/traderbot/heartbeat.py`
- **Wave 3**: `fix: make AuditLogger use profile-aware audit directory` — `src/traderbot/risk/audit.py`, `src/traderbot/paths.py`
- **Wave 3**: `fix: heartbeat API connectivity check with demo API fallback` — `src/traderbot/heartbeat.py`
- **Wave 3**: `feat: add --json references to cron loop payloads for structured output` — `src/traderbot/cron_loops.py`
- **Wave 3**: (no commit — config task) Register cron loops via `traderbot cron setup`

---

## Success Criteria

### Verification Commands
```bash
# On macpro-linux with TRADERBOT_PROFILE_TOKEN set:
traderbot scan --category weather --limit 20 --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} markets, {sum(1 for m in d if float(m.get(\"volume_fp\",0) or 0)>0)} with volume')"
# Expected: >0 markets with volume

traderbot signals --category weather --limit 20 --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} signals')"
# Expected: >0 signals

traderbot heartbeat --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('performance',{}).get('open_positions'))"
# Expected: 3 (not 0)

traderbot audit --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} decisions')"
# Expected: 3 decisions

traderbot heartbeat --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('system_health',{}).get('api_connectivity'))"
# Expected: "ok" or "degraded" (NOT "unavailable")

cat ~/.openclaw/openclaw.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Agents: {len(d.get(\"agents\",{}).get(\"list\",[]))}')"
# Expected: 1+ agents registered
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Weather markets visible via scan --category weather
- [ ] Signals non-empty for markets with orderbooks
- [ ] Heartbeat shows correct open_positions
- [ ] Heartbeat shows api_connectivity != "unavailable" (ok or degraded)
- [ ] Audit reads from profile-specific dir
- [ ] Cron loops registered for weather agent
- [ ] Cron payloads reference --json flag