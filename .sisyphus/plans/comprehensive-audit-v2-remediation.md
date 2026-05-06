# Comprehensive Audit V2 — Remediation Plan

## TL;DR

> **Quick Summary**: Fix all V1 API remnants, security issues (NewsAPI key leakage, fd leaks), destructive profile injection, broken installer, stale workspace files, and code correctness issues across the TraderBot toolkit. 7 work streams, ~30 tasks across 5 waves.
> 
> **Deliverables**:
> - Kalshi V2 API fully compliant (no V1 remnants)
> - NewsAPI secure (X-Api-Key header, 401 handling, daily budget)
> - Profile injection: fenced-merge strategy (never destroys agent data)
> - Installer: end-to-end working (env var expansion, all profile categories, correct OpenClaw config)
> - Workspace files: accurate, relevant, no stale/phantom commands
> - WAL/heartbeat: absolute paths, fd leak fixed, sharpe/drawdown computed
> - Tests for all fixes
> 
> **Estimated Effort**: Large (7 work streams, ~30 commits)
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: Wave 1 (V2 migration) → Wave 2 (security) → Wave 3 (injection refactor) → Wave 4 (workspace/installer) → Wave 5 (verification)

---

## Context

### Original Request
Full codebase audit for implementation correctness and API compliance. Verify all Kalshi V1 references removed, validate assumptions from memory, ensure .openclaw workspace files give the agent comprehensive instructions without irrelevant info, audit heartbeat/cron for correct Gateway-triggered operation, fix installer to fully configure all pieces, and switch profile injection from overwrite to merge.

### Interview Summary
**Key Discussions**:
- V1 API remnants confirmed still present in trading.py, portfolio.py, _normalize.py, models.py
- .openclaw/ in project root = TEMPLATES; ~/.openclaw/ = deployed agent workspaces
- AGENTS.md and SOUL.md must reach agent workspaces but must NOT destroy agent personalizations → fenced-merge strategy
- `traderbot cron setup` EXISTS in cli.py (wraps `openclaw cron add`), contradicts some memory entries
- NewsAPI apiKey passed as query param in 3 locations (security issue)
- heartbeat self-initiated in service templates (should be Gateway-triggered)

### Metis Review
**Identified Gaps** (addressed):
- Test coverage gaps for new V2 parsing (must add tests)
- _parse_order has zero direct unit tests — must add
- No CI exists — out of scope for this plan
- WebSocket reconnection missing — out of scope (feature addition, not audit fix)
- Concurrency safety for profile injection not addressed — added guardrails

---

## Work Objectives

### Core Objective
Remediate all audit findings: V1→V2 migration, security fixes, profile injection refactor, workspace file corrections, installer fixes, and heartbeat/cron corrections.

### Concrete Deliverables
- src/traderbot/kalshi/ fully V2-compliant (no V1 fields or endpoints)
- src/traderbot/news/sources.py using X-Api-Key header with 401 handling and daily budget
- src/traderbot/profiles/injection.py with 4-strategy merge (fenced-merge, copy-if-missing, never-overwrite)
- .openclaw/workspace/ files accurate and relevant
- install/traderbot-installer.sh working end-to-end
- src/traderbot/wal.py fd leak fixed
- src/traderbot/heartbeat.py absolute paths and computed sharpe/drawdown
- Tests for all changes

### Definition of Done
- [ ] `uv run pytest tests/ -x --tb=short` passes all tests
- [ ] `ruff check src/` passes with 0 errors
- [ ] No V1 API references remain (`grep -rn "yes_price\|/portfolio/orders[^/]\|action.*buy\|action.*sell" src/traderbot/kalshi/` returns 0 in API-facing code)
- [ ] No apiKey-as-query-param in sources.py (`grep -n "apiKey.*self._newsapi_key" src/traderbot/news/sources.py` returns 0)
- [ ] Profile injection: `python -c "from traderbot.profiles.injection import propagate_workspace_files; help(propagate_workspace_files)"` shows merge strategies
- [ ] All workspace files pass accuracy verification (no phantom commands)

### Must Have
- V2 API compliance (no V1 remnants in API-facing code)
- NewsAPI X-Api-Key header (no query param leakage)
- Token security: tokens NEVER displayed in plain text, NEVER in workspace files, NEVER in logs, NEVER in CLI output
- Token storage: .env file must be chmod 600; PEM key file must be chmod 600; OpenClaw SecretRefs integration
- Fenced-merge injection for AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md
- INIT_IF_MISSING for USER.md, MEMORY.md, SESSION-STATE.md, HEARTBEAT_DATA.md, .learnings/ (deploy template on first setup, never overwrite existing)
- ASK_THEN_MERGE for BOOTSTRAP.md, BOOT.md, HEARTBEAT.md (prompt user, then FENCED_MERGE if yes; fallback to INIT_IF_MISSING in non-interactive/TTY contexts)
- Absolute paths for WAL and heartbeat, absolute env_file in ALL BaseSettings subclasses
- fd leak fix in wal.py update_status
- SESSION-STATE.md, HEARTBEAT_DATA.md, .learnings/ documented as TraderBot-specific extensions (not standard OpenClaw files)
- NewsAPI env var naming: standardize on NEWSAPI_API_KEY with NEWSAPI_KEY fallback
- env_file in all BaseSettings subclasses changed to absolute path (~/.traderbot/.env)

### Must NOT Have (Guardrails)
- NEVER modify risk/ hard limits without explicit human approval
- NEVER add `from __future__ import annotations` to cli.py or any Typer module
- NEVER use `kalshi_python_async` SDK (requires Python 3.13, project is 3.12)
- NEVER overwrite agent personalization data (USER.md, MEMORY.md, etc.) — use INIT_IF_MISSING: deploy template if absent, skip if present
- NEVER use copy-if-missing for files that OpenClaw auto-creates (USER.md etc.) — check existence first, init only if missing
- NEVER store API credentials in query parameters (NewsAPI apiKey → X-Api-Key header)
- NEVER leave unexpanded env vars in installer config templates
- NEVER display tokens in plain text (CLI output, logs, exception messages, workspace files)
- NEVER store tokens in workspace template files (they become part of the prompt context and are visible to the agent)
- NEVER log API key values, auth header values, or request bodies containing credentials
- NEVER use float for monetary cents values
- NEVER add WebSocket reconnection (feature addition, not audit fix)
- NEVER add CI pipeline (out of scope)
- NEVER assume [voyage] extra exists — voyageai is a hard dependency, not optional
- NEVER store API credentials in query parameters (NewsAPI apiKey → X-Api-Key header)
- NEVER leave unexpanded env vars in installer config templates

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest with 70 test files)
- **Automated tests**: YES (tests-after) — add tests for each fix
- **Framework**: pytest with async support

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend**: Bash (pytest, ruff, grep) — run tests, check lint, verify no V1 remnants
- **File verification**: Bash (grep, diff) — verify injection strategies, header changes
- **Installer**: Bash (shellcheck, test runs) — verify env var expansion, path resolution

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (V2 Migration — foundation, blocks Wave 4 workspace edits):
├── Task 1: Migrate OrderRequest/TradingOrder to V2 field names [deep]
├── Task 2: Migrate portfolio.py and _normalize.py to V2 response fields [deep]
├── Task 3: Fix V2 endpoint paths (/portfolio/events/orders, cancel path) [quick]
└── Task 4: Remove V1 WebSocket channels, verify CRYPTO category [quick]

Wave 2 (Security + Infrastructure — independent of Wave 1):
├── Task 5: NewsAPI: X-Api-Key header, 401 permanent error, daily budget [unspecified-high]
├── Task 6: Fix wal.py fd leak and add absolute path resolution [deep]
├── Task 7: Fix heartbeat.py absolute paths, compute sharpe/drawdown [quick]
└── Task 8: Add _parse_order unit tests and V2 field edge cases [unspecified-high]

Wave 3 (Profile Injection Refactor — core feature):
├── Task 9: Create injection strategies module with 4 merge strategies [deep]
├── Task 10: Implement inject_profile_into_identity() with fenced markers [unspecified-high]
├── Task 11: Implement inject_agents_block() and inject_soul_block() [unspecified-high]
├── Task 12: Refactor propagate_workspace_files() to use strategy dispatcher [deep]
└── Task 13: Add comprehensive injection tests (merge, fresh, never-overwrite) [unspecified-high]

Wave 4 (Workspace Files + Installer — depends on Wave 3):
├── Task 14: Rewrite TOOLS.md with accurate CLI reference and profile docs [writing]
├── Task 15: Fix AGENTS.md: remove phantom commands, correct thresholds [writing]
├── Task 16: Fix BOOTSTRAP.md: correct cron command, trim training manifesto [writing]
├── Task 17: Fix SOUL.md, HEARTBEAT.md, BOOT.md, IDENTITY.md updates [writing]
├── Task 18: Reinitialize SESSION-STATE.md, create missing .learnings files [quick]
├── Task 19: Fix installer: env var expansion, all categories, correct cron/heartbeat [deep]
└── Task 20: Fix service templates: remove self-initiated heartbeat polling [unspecified-high]

Wave 5 (Verification — after ALL implementation):
├── Task 21: Full test suite pass + ruff check [quick]
├── Task 22: V1 grep verification (no V1 remnants remain) [quick]
├── Task 23: NewsAPI header verification [quick]
├── Task 24: Injection strategy verification [quick]
└── Task 25: Installer dry-run verification [unspecified-high]

Wave FINAL (after ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: Task 1-4 → Task 14-17 (templates) → Task 19 (installer) → Task 25 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Waves 1, 2)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|---|---|---|
| 1 | — | 14 (uses V2 models) |
| 2 | — | 8 (testing V2 parsing) |
| 3 | — | 14, 19 |
| 4 | — | — |
| 5 | — | — |
| 6 | — | — |
| 7 | — | — |
| 8 | 1, 2 | — |
| 9 | — | 10, 11, 12 |
| 10 | 9 | 12 |
| 11 | 9 | 12 |
| 12 | 9, 10, 11 | 13, 14-17, 19 |
| 13 | 12 | — |
| 14 | 1, 3 | — |
| 15 | 12 | — |
| 16 | 12 | — |
| 17 | 12 | — |
| 18 | — | — |
| 19 | 12 | 20 |
| 20 | 19 | — |
| 21 | ALL | — |
| 22 | 1-4 | — |
| 23 | 5 | — |
| 24 | 12 | — |
| 25 | 19, 20 | — |

### Agent Dispatch Summary

- **Wave 1**: 4 tasks — T1 `deep`, T2 `deep`, T3 `quick`, T4 `quick`
- **Wave 2**: 4 tasks — T5 `unspecified-high`, T6 `deep`, T7 `quick`, T8 `unspecified-high`
- **Wave 3**: 5 tasks — T9 `deep`, T10 `unspecified-high`, T11 `unspecified-high`, T12 `deep`, T13 `unspecified-high`
- **Wave 4**: 7 tasks — T14-T17 `writing`, T18 `quick`, T19 `deep`, T20 `unspecified-high`
- **Wave 5**: 5 tasks — T21-T24 `quick`, T25 `unspecified-high`
- **FINAL**: 4 tasks — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [x] 1. Migrate OrderRequest/TradingOrder to V2 field names

  **What to do**:
  - In `src/traderbot/kalshi/models.py`:
    - Convert `OrderRequest.action` from `Literal["buy", "sell"]` to `OrderSide` enum with values `bid`/`ask`
    - Convert `OrderRequest.count: int` to `count: Decimal` (or `str` for fixed-point)
    - Convert `OrderRequest.price_cents: int` to `price: Decimal` (or `str` for fixed-point dollars)
    - Rename `CancelResponse.order_id` to match actual V2 cancel response fields
    - Add `OrderSide` enum if not present (bid/ask, not buy/sell)
  - In `src/traderbot/kalshi/trading.py`:
    - Update `place_order()` to post to `/portfolio/events/orders` (not `/portfolio/orders`)
    - Update request body construction to use `side: bid/ask`, `count_fp: str`, `price_dollars: str`, `client_order_id: str`
    - Auto-generate `client_order_id` as UUID4 when not provided
    - Update `_parse_order()` to read V2 fields: `price_dollars`/`price_fp` not `yes_price`, `count_fp` not `count`
    - Handle V2 side field (`bid`/`ask`) instead of action (`buy`/`sell`)
  - In `src/traderbot/kalshi/models.py` `OrderRequest.to_v2_body()`:
    - Fix key names: `count` → `count_fp`, `price` → `price_dollars`
    - Ensure values are strings (fixed-point format)
  - Add/update tests for new model structure

  **Must NOT do**:
  - Do NOT use `float` for monetary values — use `Decimal` or `str` fixed-point
  - Do NOT modify anything in `risk/`
  - Do NOT add `from __future__ import annotations` to cli.py

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 14, 22
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/models.py:220-270` — OrderRequest, TradingOrder, OrderSide current definitions
  - `src/traderbot/kalshi/trading.py:1-120` — TradingService with V1/V2 mix
  - `src/traderbot/kalshi/_normalize.py:1-100` — Trade/Settlement parsers using V1 fields

  **API/Type References**:
  - `src/traderbot/kalshi/config.py` — API base URLs (correct, verified)
  - `src/traderbot/kalshi/signing.py` — RSA-PSS auth (correct, verified)

  **Test References**:
  - `tests/kalshi/test_trading.py` — existing trading tests
  - `tests/kalshi/test_models.py` — existing model tests

  **WHY Each Reference Matters**:
  - models.py:220-270 is the core model definitions that must change (action→side, count→count_fp, price_cents→price)
  - trading.py:1-120 contains the endpoint URL and request body construction
  - _normalize.py:1-100 parses API responses using V1 field names that must update

  **Acceptance Criteria**:

  **If TDD**: N/A (tests-after for this audit fix)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V2 order endpoint and field names
    Tool: Bash (pytest + grep)
    Preconditions: All V2 migration code merged
    Steps:
      1. grep -rn "portfolio/orders[^/]" src/traderbot/kalshi/trading.py | grep -v "# V1\|deprecated\|comment" | wc -l
      2. Expected: 0 (no V1 /portfolio/orders endpoint, only /portfolio/events/orders)
      3. grep -rn "action.*buy\|action.*sell" src/traderbot/kalshi/models.py | grep -v "V1\|deprecated\|comment\|OrderSide" | wc -l
      4. Expected: 0 (no buy/sell action, only bid/ask side)
      5. grep -rn "yes_price" src/traderbot/kalshi/ | grep -v "V1\|deprecated\|comment\|# " | wc -l
      6. Expected: 0 (no V1 yes_price field in API-facing code)
      7. uv run pytest tests/kalshi/ -x --tb=short -k "order or trading"
      8. Expected: all pass
    Expected Result: 0 V1 remnants, all order/trading tests pass
    Failure Indicators: grep finds V1 patterns, tests fail
    Evidence: .sisyphus/evidence/task-1-v2-order-fields.txt

  Scenario: OrderRequest produces correct V2 body
    Tool: Bash (pytest)
    Preconditions: New OrderRequest model
    Steps:
      1. uv run pytest tests/kalshi/test_models.py -x --tb=short -k "order"
      2. Verify to_v2_body() outputs {"side": "bid"/"ask", "count_fp": "10", "price_dollars": "0.5500", "client_order_id": "..."}
    Expected Result: All order model tests pass, correct V2 field names in output
    Failure Indicators: V1 field names in output, test failures
    Evidence: .sisyphus/evidence/task-1-v2-body-structure.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `fix(kalshi): migrate OrderRequest to V2 field names (side/count_fp/price_dollars)`
  - Files: `src/traderbot/kalshi/models.py`, `src/traderbot/kalshi/trading.py`, `src/traderbot/kalshi/_normalize.py`, tests
  - Pre-commit: `uv run pytest tests/kalshi/ -x --tb=short`

- [x] 2. Migrate portfolio.py and _normalize.py to V2 response fields

  **What to do**:
  - In `src/traderbot/kalshi/portfolio.py`:
    - Update `Settlement` model: `yes_price` → `price_dollars`/`price_fp`, `count` → `count_fp`
    - Update `_parse_settlement()` or equivalent to read V2 fixed-point string fields
    - Update any `MarketPosition` or similar models using V1 integer cent fields
  - In `src/traderbot/kalshi/_normalize.py`:
    - Update `Trade` model: `yes_price` → V2 field, `count` → `count_fp`
    - Update `_normalize_trade()` to parse V2 response format
    - Update `_normalize_settlement()` if present
  - Add V2 field parsing tests

  **Must NOT do**:
  - Do NOT use `float` for monetary values
  - Do NOT modify anything in `risk/`

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 8
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/portfolio.py:80-130` — Settlement parsing with V1 fields
  - `src/traderbot/kalshi/_normalize.py:20-80` — Trade/Settlement normalizers

  **Test References**:
  - `tests/kalshi/test_portfolio.py` — portfolio tests
  - `tests/kalshi/test_normalize.py` — normalize tests if they exist

  **WHY Each Reference Matters**:
  - portfolio.py still reads `yes_price` and `count` — must switch to `price_dollars`/`count_fp`
  - _normalize.py transforms API responses — must handle V2 fixed-point format

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V2 response parsing for settlements
    Tool: Bash (pytest + grep)
    Preconditions: V2 field migration complete
    Steps:
      1. grep -rn "yes_price" src/traderbot/kalshi/portfolio.py src/traderbot/kalshi/_normalize.py | grep -v "V1\|deprecated\|comment" | wc -l
      2. Expected: 0
      3. grep -rn "count[^_]" src/traderbot/kalshi/portfolio.py src/traderbot/kalshi/_normalize.py | grep -v "count_fp\|count=\|#\|comment\|V1" | wc -l
      4. Expected: 0 (count should be count_fp in V2)
      5. uv run pytest tests/kalshi/ -x --tb=short -k "portfolio or settlement or normalize"
    Expected Result: No V1 field names, all portfolio/normalize tests pass
    Failure Indicators: grep finds yes_price or bare count, tests fail
    Evidence: .sisyphus/evidence/task-2-v2-portfolio-fields.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `fix(kalshi): migrate portfolio and normalize to V2 response fields`
  - Files: `src/traderbot/kalshi/portfolio.py`, `src/traderbot/kalshi/_normalize.py`, tests

- [x] 3. Fix V2 endpoint paths (order creation, cancel)

  **What to do**:
  - In `src/traderbot/kalshi/trading.py`:
    - Change `place_order()` endpoint from `/portfolio/orders` to `/portfolio/events/orders`
    - Verify `cancel_order()` endpoint path against V2 API (may be `/portfolio/events/orders/{order_id}` or different)
    - Update URL construction in both methods
  - Verify `WebSocket` subscribe endpoint is correct (wss:// URLs already verified)
  - Add endpoint path constants in config.py if not already present

  **Must NOT do**:
  - Do NOT change WebSocket URLs (already correct)
  - Do NOT change auth headers (already correct)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 19
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/trading.py:29` — `POST /portfolio/orders` (deprecated V1 path)
  - `src/traderbot/kalshi/trading.py:37` — `DELETE /portfolio/orders/{order_id}` (likely V1 path)
  - `src/traderbot/kalshi/config.py` — base URL definitions

  **Test References**:
  - `tests/kalshi/test_trading.py` — integration tests that may hit endpoint paths

  **WHY Each Reference Matters**:
  - trading.py:29 and :37 are the wrong V1 endpoint paths
  - config.py has the correct base URL that endpoints are appended to

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V2 order creation endpoint
    Tool: Bash (grep)
    Preconditions: Endpoint migration complete
    Steps:
      1. grep -rn "portfolio/orders" src/traderbot/kalshi/trading.py | grep -v "events/orders"
      2. Expected: 0 matches (no bare /portfolio/orders)
      3. grep -n "events/orders" src/traderbot/kalshi/trading.py
      4. Expected: place_order and cancel_order both use /events/orders path
    Expected Result: All order endpoints use /portfolio/events/orders
    Failure Indicators: grep finds /portfolio/orders without /events/
    Evidence: .sisyphus/evidence/task-3-v2-endpoints.txt
  ```

  **Commit**: YES (group with Wave 1)

- [x] 4. Remove V1 WebSocket channels, verify CRYPTO category

  **What to do**:
  - In `src/traderbot/kalshi/websocket.py`:
    - Remove V1 channel names from VALID_CHANNELS (keep only V2: ticker, orderbook_delta, market_lifecycle_v2, fill, user_orders, market_positions)
    - Remove `orderbook` (V1) — replaced by `orderbook_delta` in V2
    - Remove `market_lifecycle` (V1) — replaced by `market_lifecycle_v2` in V2
    - Keep `ticker` if it's V2-valid (verify)
    - Add authenticated channels documentation: fill, user_orders, market_positions require auth headers
  - In `src/traderbot/kalshi/models.py`:
    - **VERIFIED**: Queried live Kalshi API `tags_by_categories` — CRYPTO IS a valid category (14 total: Climate and Weather, Commodities, Companies, Crypto, Economics, Elections, Entertainment, Financials, Health, Mentions, Politics, Science and Technology, Social, Sports)
    - **OUTCOME**: Expanded `MarketCategory` from 7 to 16 values (added CRYPTO, COMMODITIES, COMPANIES, ELECTIONS, ENTERTAINMENT, FINANCIALS, HEALTH, MENTIONS, SOCIAL). Added API variant mappings: "climate and weather"→WEATHER, "science and technology"→TECHNOLOGY. Removed `_normalize_category` blacklist so unknown categories pass through instead of being nullified. (See extra task: "Expand MarketCategory to all 14 live API categories")
  - Update tests for channel validation

  **Must NOT do**:
  - Do NOT add WebSocket reconnection (out of scope)
  - Do NOT change WebSocket auth (already correct in V2)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/websocket.py:15` — VALID_CHANNELS with possible V1 channels
  - `src/traderbot/kalshi/models.py:222` — MarketCategory enum with CRYPTO
  - `src/traderbot/kalshi/_normalize.py:28` — _CATEGORY_MAP with crypto entry

  **Test References**:
  - `tests/kalshi/test_websocket.py` — websocket tests if they exist

  **WHY Each Reference Matters**:
  - websocket.py:15 lists channels including possible V1 ones
  - models.py:222 CRYPTO category may not exist on live API
  - _normalize.py:28 maps category strings to enum values

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V2-only WebSocket channels
    Tool: Bash (grep + pytest)
    Preconditions: V1 channels removed
    Steps:
      1. grep -n "orderbook[^_]" src/traderbot/kalshi/websocket.py | wc -l
      2. Expected: 0 (bare "orderbook" V1 channel removed, only "orderbook_delta" remains)
      3. grep -n "market_lifecycle[^_]" src/traderbot/kalshi/websocket.py | wc -l
      4. Expected: 0 (V1 "market_lifecycle" removed, only "market_lifecycle_v2" remains)
      5. uv run pytest tests/kalshi/ -x --tb=short -k "websocket or channel"
    Expected Result: No V1 channels remain, all websocket tests pass
    Evidence: .sisyphus/evidence/task-4-v2-websocket-channels.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `fix(kalshi): remove V1 WebSocket channels, remove CRYPTO category`

- [x] 5. NewsAPI: X-Api-Key header, 401 handling, daily budget

  **What to do**:
  - In `src/traderbot/news/sources.py`:
    - Lines 97, 187, 322: Change `params={"apiKey": self._newsapi_key, ...}` to `headers={"X-Api-Key": self._newsapi_key}` with params minus the apiKey key
    - Add 401 handling: if response status == 401, raise a permanent auth error (no retry) — `NewsAPIAuthError` or similar, distinguishing it from transient errors
    - The existing `_handle_error` or equivalent should short-circuit on 401 immediately
    - Add client-side daily budget enforcement: track request count in `_session`, abort after 100 requests/day (reset at midnight UTC), since NewsAPI free tier doesn't return rate limit headers
    - Add `NewsAPIBudgetExceeded` exception for daily budget
  - Update any tests that pass apiKey as query param

  **Must NOT do**:
  - Do NOT change NewsAPI endpoint paths
  - Do NOT add premium tier handling (out of scope)
  - Do NOT modify `classifier.py` or `sentiment_scorer.py` (separate concerns)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 6, 7, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 23
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:90-100` — apiKey as query param in _fetch_top_headlines
  - `src/traderbot/news/sources.py:180-195` — apiKey as query param in _fetch_everything
  - `src/traderbot/news/sources.py:315-330` — apiKey as query param in _fetch_news_by_category
  - `src/traderbot/news/sources.py:218-224` — error handling that treats 401 same as other errors
  - `src/traderbot/news/sources.py:340-355` — same error handling issue in _fetch_news_by_category

  **Test References**:
  - `tests/news/test_sources.py` — existing news tests

  **WHY Each Reference Matters**:
  - Lines 97, 187, 322 are the 3 security vulnerabilities (apiKey in URL/logs)
  - Lines 218-224, 340-355 treat 401 as retryable — they must fail permanently

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: NewsAPI X-Api-Key header usage
    Tool: Bash (grep)
    Preconditions: Header migration complete
    Steps:
      1. grep -n "apiKey.*self._newsapi_key" src/traderbot/news/sources.py | wc -l
      2. Expected: 0 (no apiKey in query params)
      3. grep -n "X-Api-Key" src/traderbot/news/sources.py | wc -l
      4. Expected: 3+ (each _fetch method uses X-Api-Key header)
    Expected Result: 0 apiKey query params, 3+ X-Api-Key header usages
    Evidence: .sisyphus/evidence/task-5-newsapi-header.txt

  Scenario: 401 permanent auth error
    Tool: Bash (pytest)
    Preconditions: Auth error handling added
    Steps:
      1. uv run pytest tests/news/ -x --tb=short -k "401 or auth"
      2. Verify test exists that confirms 401 raises permanent error (no retry)
    Expected Result: Test confirms 401 raises NewsAPIAuthError without retry
    Evidence: .sisyphus/evidence/task-5-newsapi-401-handling.txt

  Scenario: Daily budget enforcement
    Tool: Bash (pytest)
    Preconditions: Daily budget tracking added
    Steps:
      1. uv run pytest tests/news/ -x --tb=short -k "budget"
      2. Verify test confirms budget exceeded after 100 requests
    Expected Result: Budget tracking works, NewsAPIBudgetExceeded raised after 100 req/day
    Evidence: .sisyphus/evidence/task-5-newsapi-daily-budget.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `fix(security): NewsAPI X-Api-Key header, 401 handling, daily budget`
  - Files: `src/traderbot/news/sources.py`, tests

- [x] 6. Fix wal.py fd leak and add absolute path resolution

  **What to do**:
  - In `src/traderbot/wal.py`:
    - Fix `update_status()` fd leak: inner except closes fd and re-raises; outer except tries to flock on already-closed fd → ValueError that masks original exception. Fix by removing double-close or using context managers properly.
    - Change all relative paths (`Path(".openclaw/workspace/...")`) to absolute paths using project root resolution. Use `Path(__file__).parent.parent / ".openclaw/workspace/..."` or pass base_dir parameter.
  - Add/update tests for WAL operations

  **Must NOT do**:
  - Do NOT change WAL entry format
  - Do NOT add new WAL operations

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 7, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/wal.py` — WAL implementation with relative paths and fd leak
  - Project memory: "WAL default path is relative (.openclaw/workspace/SESSION-STATE.md) — breaks if CWD != project root"
  - Project memory: "wal.py update_status has fd leak: inner except closes fd and re-raises; outer except tries to flock closed fd"

  **WHY Each Reference Matters**:
  - fd leak can mask exceptions and leak file descriptors under contention
  - Relative paths break WAL when process runs from non-project-root CWD

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: WAL fd leak fixed
    Tool: Bash (pytest)
    Preconditions: WAL fix merged
    Steps:
      1. uv run pytest tests/ -x --tb=short -k "wal"
      2. Verify no double-close or ValueError from fcntl on closed fd
    Expected Result: All WAL tests pass, fd operations clean
    Evidence: .sisyphus/evidence/task-6-wal-fd-leak.txt

  Scenario: WAL uses absolute paths
    Tool: Bash (grep)
    Preconditions: Path fix merged
    Steps:
      1. grep -n 'Path("\\.' src/traderbot/wal.py | wc -l
      2. Expected: 0 (no relative paths)
      3. grep -n "PROJECT_ROOT\|base_dir\|__file__" src/traderbot/wal.py | wc -l
      4. Expected: 1+ (uses absolute path resolution)
    Expected Result: No relative Path() usage in wal.py
    Evidence: .sisyphus/evidence/task-6-wal-paths.txt
  ```

  **Commit**: YES (group with Wave 2)

- [x] 7. Fix heartbeat.py absolute paths and compute sharpe/drawdown

  **What to do**:
  - In `src/traderbot/heartbeat.py`:
    - Change relative `Path(".openclaw/workspace/...")` to absolute path resolution (same pattern as wal.py fix)
  - In `src/traderbot/heartbeat.py` or relevant step module:
    - Fix `step_performance_review`: compute `sharpe_ratio` (currently returns None) and `max_drawdown_pct` (currently 0.0 default)
    - Use standard formulas: Sharpe = (mean_return - risk_free_rate) / std_return, Max Drawdown = max peak-to-trough decline
  - Add tests for heartbeat path resolution and performance calculations

  **Must NOT do**:
  - Do NOT add new heartbeat steps
  - Do NOT change heartbeat frequency logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 6, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/heartbeat.py` — heartbeat with relative paths and missing metrics
  - Project memory: "step_performance_review doesn't compute sharpe_ratio (None) or max_drawdown_pct (0.0)"
  - `src/traderbot/wal.py` — reference for absolute path pattern (same fix applied in Task 6)

  **WHY Each Reference Matters**:
  - Same relative path issue as wal.py — must be consistent
  - sharpe_ratio=None and max_drawdown_pct=0.0 are placeholder values that need real computation

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Heartbeat uses absolute paths
    Tool: Bash (grep)
    Preconditions: Path fix merged
    Steps:
      1. grep -n 'Path("\\.' src/traderbot/heartbeat.py | wc -l
      2. Expected: 0 (no relative paths)
    Expected Result: No relative Path() usage
    Evidence: .sisyphus/evidence/task-7-heartbeat-paths.txt

  Scenario: Sharpe ratio and max drawdown computed
    Tool: Bash (pytest)
    Preconditions: Performance review fix merged
    Steps:
      1. uv run pytest tests/ -x --tb=short -k "sharpe or drawdown"
      2. Verify sharpe_ratio returns float (not None), max_drawdown_pct returns float (not 0.0 for non-trivial case)
    Expected Result: Metrics computed correctly for non-trivial portfolios
    Evidence: .sisyphus/evidence/task-7-performance-metrics.txt
  ```

  **Commit**: YES (group with Wave 2)

- [x] 8. Add _parse_order unit tests and V2 field edge cases

  **What to do**:
  - Create comprehensive unit tests for `_parse_order()` in `src/traderbot/kalshi/trading.py`:
    - Test V2 response fields: `price_dollars`/`price_fp`, `count_fp`, `side` (bid/ask)
    - Test missing fields: `created_time` (should handle gracefully)
    - Test unknown `order_type`/`side` fallback behavior
    - Test type coercion: string-to-int for count, string-to-float for price
  - Add tests for V2 model serialization:
    - Test `OrderRequest.to_v2_body()` outputs correct key names (`side`, `count_fp`, `price_dollars`)
    - Test `client_order_id` auto-generation when not provided
    - Test that `action` field is not used in V2 output
  - Add edge case tests for `_normalize.py`:
    - Fixed-point string parsing: "0.5500" → correct numeric value
    - Missing/empty fields

  **Must NOT do**:
  - Do NOT add integration tests against live API
  - Do NOT modify existing passing tests

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 1, 2)
  - **Parallel Group**: Wave 2 (but blocked by Wave 1)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/trading.py:60-90` — _parse_order function
  - `src/traderbot/kalshi/models.py:240-270` — OrderRequest.to_v2_body
  - `src/traderbot/kalshi/_normalize.py:20-80` — Trade/Settlement normalizers

  **Test References**:
  - `tests/kalshi/test_trading.py` — existing trading tests to extend
  - `tests/kalshi/test_models.py` — existing model tests to extend

  **WHY Each Reference Matters**:
  - _parse_order has zero direct unit tests (only indirect via integration)
  - to_v2_body must output correct V2 key names after migration

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: _parse_order V2 field handling
    Tool: Bash (pytest)
    Preconditions: Tests written
    Steps:
      1. uv run pytest tests/kalshi/ -x --tb=short -k "parse_order"
      2. Verify: handles V2 fields (price_dollars, count_fp, side), missing created_time, unknown order_type
    Expected Result: All _parse_order tests pass
    Evidence: .sisyphus/evidence/task-8-parse-order-tests.txt

  Scenario: V2 model serialization tests
    Tool: Bash (pytest)
    Preconditions: Tests written
    Steps:
      1. uv run pytest tests/kalshi/ -x --tb=short -k "v2_body"
      2. Verify: to_v2_body() outputs side, count_fp, price_dollars, client_order_id keys only
    Expected Result: V2 body serialization uses correct key names
    Evidence: .sisyphus/evidence/task-8-v2-body-tests.txt
  ```

  **Commit**: YES (group with Wave 2)

- [x] 9. Create injection strategies module with 4 merge strategies

  **What to do**:
  - Create `src/traderbot/profiles/injection_strategies.py`:
    - Define `InjectionStrategy` enum: `FENCED_MERGE`, `INIT_IF_MISSING`, `ASK_THEN_MERGE`, `OVERWRITE`
  - FENCED_MERGE: Always inject TraderBot content inside markers, preserving agent additions outside markers
  - INIT_IF_MISSING: Deploy template if file doesn't exist (fresh agent setup), skip if it exists (preserve agent data)
  - ASK_THEN_MERGE: Prompt user during bootstrap/profile-assign. If user says yes, FENCED_MERGE. If no, skip.
  - OVERWRITE: Only for explicitly-marked files (none currently)
    - Define `FENCED_BLOCK_MARKERS` dict mapping file names to their marker pairs:
      - AGENTS.md → `<!-- TRADERBOT_RULES_START -->` / `<!-- TRADERBOT_RULES_END -->`
      - SOUL.md → `<!-- TRADERBOT_SOUL_START -->` / `<!-- TRADERBOT_SOUL_END -->`
      - TOOLS.md → `<!-- TRADERBOT_TOOLS_START -->` / `<!-- TRADERBOT_TOOLS_END -->` + existing `inject_token()` for env vars
      - IDENTITY.md → `<!-- TRADERBOT_PROFILE_START -->` / `<!-- TRADERBOT_PROFILE_END -->`
    - Implement `fenced_merge(template_content: str, target_path: Path, markers: tuple[str, str]) -> str`:
      - If target doesn't exist: write template (first deploy)
      - If target exists with markers: replace content between markers with template's marked block
      - If target exists without markers: append marker block from template at end
    - Implement `ask_then_merge(template_content: str, target_path: Path, markers: tuple[str, str], file_label: str) -> bool`:
      - Prompt user: "Apply TraderBot template for {file_label}? (y/n)"
      - If yes: call `fenced_merge()` with the template and markers
      - If no: skip, return False
    - Implement `init_if_missing(template_content: str, target_path: Path) -> bool`:
      - If target doesn't exist: write template → True (fresh agent deployment)
      - If target exists: skip → False (preserve agent data, never overwrite)
    - Define `FILE_STRATEGIES` dict mapping filename → strategy:
      - AGENTS.md → FENCED_MERGE with RULES markers
      - SOUL.md → FENCED_MERGE with SOUL markers
      - TOOLS.md → FENCED_MERGE with TOOLS markers
      - IDENTITY.md → FENCED_MERGE with PROFILE markers
      - BOOTSTRAP.md → ASK_THEN_MERGE (prompt user, then FENCED_MERGE if yes)
      - BOOT.md → ASK_THEN_MERGE (prompt user, then FENCED_MERGE if yes)
      - HEARTBEAT.md → ASK_THEN_MERGE (prompt user, then FENCED_MERGE if yes)
      - USER.md → INIT_IF_MISSING (deploy template if absent, skip if present)
      - MEMORY.md → INIT_IF_MISSING (deploy template if absent, skip if present)
      - SESSION-STATE.md → INIT_IF_MISSING (deploy template if absent, skip if present)
      - HEARTBEAT_DATA.md → INIT_IF_MISSING (deploy template if absent, skip if present)
      - .learnings/ → INIT_IF_MISSING (deploy template dirs/files if absent, skip if present)
  - Add comprehensive tests for each strategy:
    - FENCED_MERGE: new file, existing file with markers, existing file without markers, markers with content to replace
      - ASK_THEN_MERGE: user declines, user accepts
      - INIT_IF_MISSING: file absent (deploy template), file present (skip, preserve data)

  **Must NOT do**:
  - Do NOT modify `propagate_workspace_files()` yet (that's Task 12)
  - Do NOT touch risk/ or any other module

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation for Tasks 10-13)
  - **Parallel Group**: Wave 3, first
  - **Blocks**: Tasks 10, 11, 12
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/injection.py` — current propagate_workspace_files() with shutil.copy2 overwrite
  - `.openclaw/workspace/` — template files to be merged
  - Project memory: "inject_profile_into_identity() does NOT exist"
  - Project memory: "inject_token() in profiles/injection.py" — existing fenced injection for TOOLS.md env vars

  **API/Type References**:
  - `src/traderbot/profiles/models.py` — TradingProfile model
  - `src/traderbot/profiles/tokens.py` — profile token resolution

  **Test References**:
  - `tests/profiles/test_injection.py` — existing test file (if exists)

  **WHY Each Reference Matters**:
  - injection.py is the file we're refactoring — need to understand current flow before changing
  - .openclaw/workspace/ contains the template content that will be injected
  - inject_token() already does a form of fenced merge — study its pattern

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Injection strategies module loads and has all strategies
    Tool: Bash (python)
    Preconditions: Module created
    Steps:
      1. python -c "from traderbot.profiles.injection_strategies import InjectionStrategy, FILE_STRATEGIES, fenced_merge, copy_if_missing, never_overwrite; print(list(InjectionStrategy)); print(list(FILE_STRATEGIES.keys()))"
      2. Verify: FENCED_MERGE, INIT_IF_MISSING, ASK_THEN_MERGE, OVERWRITE
      3. Verify: FILE_STRATEGIES has entries for all 11+ workspace files
    Expected Result: All strategies and file mappings enumerated
    Evidence: .sisyphus/evidence/task-9-strategy-enum.txt

  Scenario: Fenced merge strategies tested
    Tool: Bash (pytest)
    Preconditions: Tests written
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "injection_strategies"
      2. Verify: FENCED_MERGE replaces marked content, appends to unmarked files, creates new files
      3. Verify: ASK_THEN_MERGE prompts user, merges if accepted, skips if declined
      4. Verify: INIT_IF_MISSING deploys template for missing files, skips existing
    Expected Result: All strategy tests pass
    Evidence: .sisyphus/evidence/task-9-strategy-tests.txt
  ```

  **Commit**: YES (Wave 3 foundation)
  - Message: `feat(profiles): create injection strategies module with 4 merge strategies`
  - Files: `src/traderbot/profiles/injection_strategies.py`, `tests/profiles/test_injection_strategies.py`

- [x] 10. Implement inject_profile_into_identity() with fenced markers

  **What to do**:
  - In `src/traderbot/profiles/injection_strategies.py` (or injection.py if that's where it belongs):
    - Implement `inject_profile_into_identity(profile: TradingProfile, target_path: Path) -> bool`:
      - Uses FENCED_MERGE strategy with `<!-- TRADERBOT_PROFILE_START/END -->` markers
      - Builds profile block from TradingProfile fields: name, category, risk_multiplier, max_position_pct, enabled_categories
      - Merges into existing IDENTITY.md or creates new with template
  - This is the function that `discovery.py` needs to find agents in identity files
  - Add tests: new identity, existing identity with markers, existing identity without markers

  **Must NOT do**:
  - Do NOT modify `propagate_workspace_files()` yet (Task 12)
  - Do NOT change discovery.py

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 12
  - **Blocked By**: Task 9

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/injection_strategies.py` — just created in Task 9
  - `src/traderbot/profiles/injection.py` — existing inject_token() pattern for fenced merge
  - `src/traderbot/profiles/models.py` — TradingProfile model fields
  - `src/traderbot/profiles/discovery.py` — parses IDENTITY.md to find agents

  **WHY Each Reference Matters**:
  - inject_token() is the existing pattern to follow for fenced block injection
  - TradingProfile fields determine what goes into the identity block
  - discovery.py reads the output format — must be compatible

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: inject_profile_into_identity creates new identity
    Tool: Bash (pytest)
    Preconditions: Function implemented
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "identity_inject"
      2. Verify: new file created with profile markers and content
    Expected Result: Identity file created with fenced profile block
    Evidence: .sisyphus/evidence/task-10-identity-inject.txt

  Scenario: inject_profile_into_identity merges into existing
    Tool: Bash (pytest)
    Preconditions: Function implemented
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "identity_merge"
      2. Verify: existing content preserved, profile block updated within markers
    Expected Result: Existing content preserved, only profile block replaced
    Evidence: .sisyphus/evidence/task-10-identity-merge.txt
  ```

  **Commit**: YES (group with Task 11)

- [x] 11. Implement inject_agents_block() and inject_soul_block()

  **What to do**:
  - In `src/traderbot/profiles/injection_strategies.py`:
    - Implement `inject_agents_block(template: str, target_path: Path) -> bool`:
      - Uses FENCED_MERGE strategy with `<!-- TRADERBOT_RULES_START/END -->` markers
      - Template content from .openclaw/workspace/AGENTS.md goes between markers
      - Preserves any agent additions outside markers
    - Implement `inject_soul_block(template: str, target_path: Path) -> bool`:
      - Uses FENCED_MERGE strategy with `<!-- TRADERBOT_SOUL_START/END -->` markers
      - Template content from .openclaw/workspace/SOUL.md goes between markers
      - Preserves any agent personality additions outside markers
  - Add fenced-block template markers to `.openclaw/workspace/AGENTS.md` and `.openclaw/workspace/SOUL.md` (wrap their content in the markers)
  - Add tests: new file, existing with markers, existing without markers

  **Must NOT do**:
  - Do NOT modify propagate_workspace_files() yet (Task 12)
  - Do NOT add content to AGENTS.md/SOUL.md — just add the marker comments around existing content

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 12
  - **Blocked By**: Task 9

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/injection_strategies.py` — just created in Task 9
  - `.openclaw/workspace/AGENTS.md` — template to be wrapped in markers
  - `.openclaw/workspace/SOUL.md` — template to be wrapped in markers
  - Task 9's `fenced_merge()` function — reuse this

  **WHY Each Reference Matters**:
  - AGENTS.md and SOUL.md contain TraderBot rules/personality that must reach agent workspaces
  - But agent may have added notes/personality beyond the template — cannot destroy those

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: AGENTS.md fenced merge preserves agent additions
    Tool: Bash (pytest)
    Preconditions: inject_agents_block implemented
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "agents_block"
      2. Verify: new workspace gets full template, existing workspace preserves agent additions outside markers
    Expected Result: Template content within markers, agent additions preserved outside
    Evidence: .sisyphus/evidence/task-11-agents-block.txt

  Scenario: SOUL.md fenced merge preserves agent personality
    Tool: Bash (pytest)
    Preconditions: inject_soul_block implemented
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "soul_block"
      2. Verify: new workspace gets full template, existing workspace preserves personality outside markers
    Expected Result: Template content within markers, agent personality preserved outside
    Evidence: .sisyphus/evidence/task-11-soul-block.txt
  ```

  **Commit**: YES (group with Task 10)
  - Message: `feat(profiles): add fenced-merge injectors for AGENTS.md, SOUL.md, IDENTITY.md`
  - Files: `src/traderbot/profiles/injection_strategies.py`, `.openclaw/workspace/AGENTS.md`, `.openclaw/workspace/SOUL.md`, tests

- [x] 12. Refactor propagate_workspace_files() to use strategy dispatcher

  **What to do**:
  - In `src/traderbot/profiles/injection.py`:
    - Rewrite `propagate_workspace_files()` to use the strategy dispatcher from `injection_strategies.py`
    - For each workspace file, look up its strategy from `FILE_STRATEGIES`
    - FENCED_MERGE files: call the appropriate injector (`inject_agents_block`, `inject_soul_block`, `inject_token`, `inject_profile_into_identity`)
    - INIT_IF_MISSING files: deploy template if absent, skip if present
    - ASK_THEN_MERGE files: prompt user, merge if accepted (deploy template for fresh agents)
    - OVERWRITE: only for files explicitly marked (none currently)
    - Remove the old `shutil.copy2` loop that overwrites everything unconditionally
    - Remove the separate `inject_token()` call that "repairs" TOOLS.md after overwrite (now handled by FENCED_MERGE)
    - Ensure the function still correctly resolves `profile.base_dir` / workspace paths
  - Update `profile_assign` call chain if needed
  - Update tests to test the new strategy-based flow end-to-end

  **Must NOT do**:
  - Do NOT change the profile_assign function signature
  - Do NOT change discovery.py
  - Do NOT modify risk/

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 9, 10, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 13, 14-20
  - **Blocked By**: Tasks 9, 10, 11

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/injection.py` — current propagate_workspace_files() with shutil.copy2
  - `src/traderbot/profiles/injection_strategies.py` — new strategies from Task 9
  - `.openclaw/workspace/` — template files

  **Test References**:
  - `tests/profiles/test_injection.py` — existing injection tests to update

  **WHY Each Reference Matters**:
  - injection.py is the core file being refactored
  - The strategy dispatcher must correctly route every file to its strategy

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: propagate_workspace_files uses merge strategies
    Tool: Bash (pytest)
    Preconditions: Refactored injection.py
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "propagate"
      2. Verify: new deployment creates all files, re-linking preserves existing USER.md/MEMORY.md/etc.
    Expected Result: New deploy creates all files; re-link preserves agent data
    Evidence: .sisyphus/evidence/task-12-strategy-dispatcher.txt

  Scenario: Re-linking preserves agent data
    Tool: Bash (pytest)
    Preconditions: Refactored injection.py
    Steps:
      1. Create mock workspace with USER.md containing "My custom notes"
      2. Call propagate_workspace_files with a profile
      3. Read USER.md — should still contain "My custom notes"
      4. Read AGENTS.md — should have TRADERBOT_RULES block updated
    Expected Result: USER.md preserved exactly, AGENTS.md rules updated but agent additions preserved
    Evidence: .sisyphus/evidence/task-12-relink-preserve.txt
  ```

  **Commit**: YES (Wave 3 core)
  - Message: `refactor(profiles): switch injection from overwrite to merge strategy dispatcher`
  - Files: `src/traderbot/profiles/injection.py`, tests

- [x] 13. Add comprehensive injection tests

  **What to do**:
  - Add end-to-end tests for the complete injection flow:
    - Test fresh deployment (no existing workspace): all templates deployed
    - Test re-linking (existing workspace): agent data preserved, template blocks updated
    - Test FENCED_MERGE: verify marker detection, content replacement, marker insertion
    - Test ASK_THEN_MERGE: verify prompt, merge on accept, skip on decline
    - Test INIT_IF_MISSING: verify deploy on absent, skip on present
    - Test edge cases: empty files, files with only markers, corrupted markers
  - Verify cross-file interactions don't clobber each other

  **Must NOT do**:
  - Do NOT add integration tests against live OpenClaw

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 12)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/injection_strategies.py` — strategies to test
  - `src/traderbot/profiles/injection.py` — refactored dispatcher to test

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: End-to-end fresh deployment
    Tool: Bash (pytest)
    Preconditions: All injection code merged
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "fresh_deploy"
      2. Verify: all 11+ workspace files handled correctly for fresh deploy
      3. Verify: FENCED_MERGE files have marker blocks
      4. Verify: ASK_THEN_MERGE files prompt user and inject if accepted
      5. Verify: INIT_IF_MISSING files: absent → template deployed, present → skipped
    Expected Result: FENCED_MERGE files updated, ASK_THEN_MERGE prompts handled, INIT_IF_MISSING deploys absent/skips present
    Evidence: .sisyphus/evidence/task-13-fresh-deploy.txt

  Scenario: End-to-end re-link preserves agent data
    Tool: Bash (pytest)
    Preconditions: All injection code merged
    Steps:
      1. uv run pytest tests/profiles/ -x --tb=short -k "relink"
      2. Verify: USER.md, MEMORY.md, SESSION-STATE.md, HEARTBEAT_DATA.md content unchanged (INIT_IF_MISSING skipped since they exist)
      3. Verify: AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md fenced blocks updated
      4. Verify: .learnings/ content unchanged
    Expected Result: Agent personalization preserved, template blocks updated
    Evidence: .sisyphus/evidence/task-13-relink-preserve.txt
  ```

  **Commit**: YES (group with Task 12)

- [x] 14. Rewrite TOOLS.md with accurate CLI reference and profile docs

  **What to do**:
  - Rewrite `.openclaw/workspace/TOOLS.md`:
    - **SECURITY**: Remove `.env` file references and credential variable names (agent should not know where credentials live)
    - **SECURITY**: Remove internal paths (`skills/traderbot/SKILL.md`, `src/traderbot/simulation/strategies/`)
    - **SECURITY**: Remove `pip install -e .` reference (agent shouldn't install software)
    - Remove all phantom CLI commands that don't exist (`traderbot evaluate_trade`, `traderbot halt --clear`)
    - Add correct CLI command syntax for all actual commands (verify against cli.py)
    - Add `traderbot cancel` command (currently MISSING entirely)
    - Add `traderbot cron setup` command (currently MISSING entirely)
    - Add `traderbot --version` command (currently MISSING)
    - Add missing `profile` subcommands: `revoke`, `assignments`, `update`, `auth`
    - Add TRADERBOT_PROFILE_TOKEN environment variable documentation (runtime behavior, how it resolves, what it affects)
    - Add profile runtime usage instructions (how profiles actually work at runtime, that limits are capped by HARD_LIMITS)
    - Add complete risk limit reference table (all HARD_LIMITS values in one place)
    - Fix wrong syntax: `compare` requires `--profiles`, `paper` requires `--duration`
    - Add module documentation: what `kalshi/`, `analysis/`, `risk/`, `simulation/`, `news/` do
    - Add end-to-end workflow: scan → analyze → trade → monitor
    - Add paper trading mode explanation (how paper differs from live, how to check current mode)
    - Add market categories list and filtering behavior
    - Wrap TraderBot-provided content in `<!-- TRADERBOT_TOOLS_START/END -->` markers
    - Add fenced block for env var section (already has inject_token() markers)
  - Remove philosophical/rationale content — agent needs "how to use" not "why we built it"

  **Must NOT do**:
  - Do NOT remove safety guidelines or risk limits documentation
  - Do NOT add V1 API references
  - Do NOT add WebSocket reconnection docs (doesn't exist)

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 15-18, if Wave 1 complete)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 3 (V2 migrations in workspace docs)

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/TOOLS.md` — current (inaccurate) workspace file
  - `src/traderbot/cli.py` — actual CLI commands (source of truth)
  - `src/traderbot/profiles/injection.py` — inject_token() for env vars

  **WHY Each Reference Matters**:
  - TOOLS.md is the primary instruction file for agents — must be accurate
  - cli.py is the source of truth for what commands actually exist

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: TOOLS.md contains no phantom commands
    Tool: Bash (grep)
    Preconditions: TOOLS.md rewritten
    Steps:
      1. grep -n "evaluate_trade\|halt --clear\|cancel" .openclaw/workspace/TOOLS.md
      2. Expected: 0 matches for phantom commands
      3. grep -n "TRADERBOT_PROFILE_TOKEN" .openclaw/workspace/TOOLS.md
      4. Expected: 1+ (documented)
      5. grep -n "TRADERBOT_TOOLS_START" .openclaw/workspace/TOOLS.md
      6. Expected: 1+ (fenced markers present)
    Expected Result: No phantom commands, profile env var documented, fenced markers present
    Evidence: .sisyphus/evidence/task-14-tools-md.txt
  ```

  **Commit**: YES (group with Tasks 15-17)
  - Message: `fix(workspace): rewrite TOOLS.md with accurate CLI reference and profile docs`

- [x] 15. Fix AGENTS.md: remove phantom commands, correct thresholds

  **What to do**:
  - In `.openclaw/workspace/AGENTS.md`:
    - **HIGH**: Remove `traderbot evaluate_trade()` — this is an internal function, NOT a CLI command. Replace with `traderbot trade`
    - **MEDIUM**: Remove "Compute Kelly-based position sizing" — this is toolkit responsibility, not agent. Rewrite as "The toolkit computes position sizing based on Kelly criterion and your confidence"
    - Remove `traderbot halt --clear` — flag doesn't exist
    - Clarify circuit breaker thresholds are hard-coded immutable constants (not "human-configured")
    - Add complete list of all HARD_LIMITS values
    - Add market categories list and how filtering works
    - Wrap TraderBot rules content in `<!-- TRADERBOT_RULES_START/END -->` markers
    - Keep actionable info only (how to use, what the limits are, what the categories are)

  **Must NOT do**:
  - Do NOT remove risk limit values (agents need to know them)
  - Do NOT add philosophical content

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 14, 16-18)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 12 (injection refactor must exist for markers)

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/AGENTS.md` — current workspace file with phantom commands
  - `src/traderbot/cli.py` — actual CLI commands (source of truth)
  - `src/traderbot/risk/__init__.py` — actual hard limits (source of truth)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: AGENTS.md has no phantom commands and correct thresholds
    Tool: Bash (grep)
    Preconditions: AGENTS.md fixed
    Steps:
      1. grep -n "evaluate_trade\|halt --clear\|human-configured" .openclaw/workspace/AGENTS.md
      2. Expected: 0 matches
      3. grep -n "TRADERBOT_RULES_START" .openclaw/workspace/AGENTS.md
      4. Expected: 1 marker present
    Expected Result: No phantom commands, fenced markers present, thresholds described as immutable
    Evidence: .sisyphus/evidence/task-15-agents-md.txt
  ```

  **Commit**: YES (group with Tasks 14, 16, 17)

- [x] 16. Fix BOOTSTRAP.md: correct cron command, trim training manifesto

  **What to do**:
  - In `.openclaw/workspace/BOOTSTRAP.md`:
    - Replace `openclaw cron add` with correct `traderbot cron setup` (which wraps `openclaw cron add`)
    - Remove or relocate the 72-hour training manifesto — it's philosophical bloat, not actionable
    - Keep only actionable first-run steps
  - Ensure bootstrap references are consistent with actual cli.py commands

  **Must NOT do**:
  - Do NOT remove safety-critical bootstrap steps
  - Do NOT add new bootstrap steps beyond what's verified

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 14, 15, 17, 18)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/BOOTSTRAP.md` — current workspace file
  - `src/traderbot/cli.py` — actual cron setup command

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: BOOTSTRAP.md has correct cron command, no manifesto
    Tool: Bash (grep)
    Preconditions: BOOTSTRAP.md fixed
    Steps:
      1. grep -n "openclaw cron add" .openclaw/workspace/BOOTSTRAP.md | wc -l
      2. Expected: 0 (should reference traderbot cron setup)
      3. wc -l .openclaw/workspace/BOOTSTRAP.md
      4. Expected: significantly shorter than 72-hour manifesto version
    Expected Result: Correct cron command, concise actionable steps
    Evidence: .sisyphus/evidence/task-16-bootstrap-md.txt
  ```

  **Commit**: YES (group with Tasks 14, 15, 17)

- [x] 17. Fix SOUL.md, HEARTBEAT.md, BOOT.md, IDENTITY.md updates

  **What to do**:
  - In `.openclaw/workspace/SOUL.md`:
    - **HIGH**: Remove `traderbot evaluate_trade()` reference — replace with `traderbot trade`
    - Wrap content in `<!-- TRADERBOT_SOUL_START/END -->` markers
    - Remove philosophical bloat, keep personality definition actionable
  - In `.openclaw/workspace/HEARTBEAT.md`:
    - Add `--json` flag documentation for `traderbot heartbeat`
    - Add explicit instruction to redirect output to HEARTBEAT_DATA.md
    - Make it COPY-IF-MISSING (not overwrite on every re-link)
  - In `.openclaw/workspace/BOOT.md`:
    - Verify startup checklist steps are accurate against actual codebase
    - Make it COPY-IF-MISSING
    - **MEDIUM**: Remove reference to `~/.openclaw/openclaw.json` (agent shouldn't know internal config paths)
  - In `.openclaw/workspace/IDENTITY.md`:
    - Add `<!-- TRADERBOT_PROFILE_START/END -->` markers around profile template content
    - Ensure discovery.py can still parse the profile section
  - In `.openclaw/workspace/BOOTSTRAP.md`:
    - **MEDIUM**: Remove reference to `~/.openclaw/openclaw.json` (internal config path)
    - **LOW**: Remove `/path/to/TraderBot_BOB` installer path reference

  **Must NOT do**:
  - Do NOT add new workspace files beyond the standard set
  - Do NOT break discovery.py's ability to parse IDENTITY.md

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 14-16, 18)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/SOUL.md`, `HEARTBEAT.md`, `BOOT.md`, `IDENTITY.md` — templates
  - `src/traderbot/profiles/discovery.py` — parses IDENTITY.md

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All workspace templates have correct markers
    Tool: Bash (grep)
    Preconditions: All templates updated
    Steps:
      1. grep -l "TRADERBOT_SOUL_START" .openclaw/workspace/SOUL.md
      2. grep -l "TRADERBOT_PROFILE_START" .openclaw/workspace/IDENTITY.md
      3. grep -c "\-\-json" .openclaw/workspace/HEARTBEAT.md
      4. Expected: SOUL.md has markers, IDENTITY.md has markers, HEARTBEAT.md mentions --json
    Expected Result: All templates have appropriate fenced markers and accurate content
    Evidence: .sisyphus/evidence/task-17-workspace-templates.txt
  ```

  **Commit**: YES (group with Tasks 14-16)

- [x] 18. Reinitialize SESSION-STATE.md, create missing .learnings files

  **What to do**:
  - In `.openclaw/workspace/SESSION-STATE.md`:
    - Reinitialize with clean WAL header format (remove orphaned Status lines outside headers — currently has `Status: CANCELLED`, `Status: COMPLETED` with no context)
    - This is a TraderBot-specific file (not standard OpenClaw) — document it as such
  - Create `.openclaw/workspace/.learnings/` directory if missing
  - In `.openclaw/workspace/.learnings/LEARNINGS.md`:
    - Remove test data entry `PROMO-001` (contains "Test evidence", "Test pattern for heartbeat", Recurrence-Count: 4). New agents would see this as real promoted learnings — misleading.
    - Replace with empty template with header only
  - Create `.openclaw/workspace/.learnings/ERRORS.md` template (empty with header)
  - Create `.openclaw/workspace/.learnings/FEATURE_REQUESTS.md` template (empty with header)
  - All .learnings/ content is INIT_IF_MISSING in deployment (deploy template if absent, skip if present)
  - Document SESSION-STATE.md and HEARTBEAT_DATA.md as TraderBot-specific extensions (OpenClaw does not have these as standard workspace files)

  **Must NOT do**:
  - Do NOT add content to ERRORS.md or FEATURE_REQUESTS.md — they're agent-created
  - Do NOT overwrite any of these files during re-linking

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 14-17)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/SESSION-STATE.md` — current template (may have corrupted format)
  - `src/traderbot/wal.py` — WAL parser that must be compatible

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: .learnings directory and templates exist
    Tool: Bash (ls)
    Preconditions: Files created
    Steps:
      1. ls -la .openclaw/workspace/.learnings/
      2. Expected: ERRORS.md and FEATURE_REQUESTS.md present
      3. head -5 .openclaw/workspace/.learnings/ERRORS.md
      4. Expected: Has header, otherwise empty template
    Expected Result: .learnings/ directory with empty template files
    Evidence: .sisyphus/evidence/task-18-learnings-templates.txt
  ```

  **Commit**: YES (group with Tasks 14-17)

- [x] 19. Fix installer: env vars, credentials, paths, services, and deployment

  **What to do**:
  - In `install/traderbot-installer.sh`:
    - **Fix env var naming mismatches**: Align `.env` key names with `AuthManager` expectations:
      - Rename `KALSHI_PRIVATE_KEY_PATH` to match what `AuthManager` checks (either update AuthManager to recognize `_PATH` variant, or write the key content as `KALSHI_PRIVATE_KEY_PEM`)
      - Rename `NEWSAPI_KEY` to `NEWSAPI_API_KEY` (or update AuthManager to recognize both)
    - **Fix credential path for services**: Installer writes to `~/.traderbot/.env` but services run from `~/traderbot`. Solutions:
      - Add `EnvironmentFile=%h/.traderbot/.env` to systemd template
      - Add `EnvironmentVariables` dict to launchd plist reading from `~/.traderbot/.env`
      - OR: Copy/symlink `~/.traderbot/.env` to `~/traderbot/.env` during install
    - **Fix systemd `%i` bug**: `install-service.sh` must replace `%i` in `User=`, `WorkingDirectory=`, and `ReadWritePaths=` with actual username (`$USER` or `$(whoami)`)
    - **Fix unexpanded `$HOME` and `$PROJECT_ROOT`**: Use `envsubst` or shell variable substitution to expand at install time
    - **Fix hardcoded "economics" workspace**: Detect user's profile category and create appropriate workspace directory
    - **Fix merge behavior**: Use `jq` recursive merge consistently; drop the python3 fallback that silently drops keys
    - **Fix heartbeat configuration**: Set `every: "30m"` and `target: "last"` consistently (not 6h)
    - **Fix post-install verification**: Source `~/.traderbot/.env` before checking credentials; export `TRADERBOT_PROFILE_TOKEN` to shell
    - **Add API credential verification**: After each credential entry, ping the API (e.g., `traderbot auth check --service kalshi`) and retry on failure
    - **Complete workspace file deployment**: Copy ALL template files (not just 5), using injection strategies from Task 9
    - **Fix OpenClaw agent config**: Dynamically generate config with actual agent name, not hardcoded `traderbot-economics`
    - **Set `KALSHI_DEMO_MODE=true`**: When paper profile is selected, write this to `.env`
    - **Install `[voyage]` extra**: Add `uv pip install -e ".[voyage]"` if Voyage key was provided
    - **Add `openclaw agents add` automation**: Create agent via `openclaw agents add` if it doesn't exist, rather than just warning
  - In `install/services/traderbot-agent@.service`:
    - Replace `User=%i` and `WorkingDirectory=/home/%i/traderbot` with actual username
    - Add `EnvironmentFile=%h/.traderbot/.env` for credential loading
  - In `install/services/com.traderbot.agent.plist`:
    - Add `EnvironmentVariables` dict reading from `~/.traderbot/.env`
  - In `src/traderbot/auth.py`:
    - Fix `_service_key_to_env` mapping: add `KALSHI_PRIVATE_KEY_PATH` as recognized variant, add `NEWSAPI_KEY` as recognized variant for `newsapi/api_key`
  - In `src/traderbot/cli.py`:
    - Verify `traderbot cron setup` command exists and wraps `openclaw cron add` correctly
    - Ensure cron schedule strings match market hours (9-16 ET, Mon-Fri)

  **Must NOT do**:
  - Do NOT modify risk/ or core trading logic
  - Do NOT add new installer features beyond fixing the gaps identified above

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 12 for injection strategy)
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 20
  - **Blocked By**: Task 3 (V2 endpoints), Task 12 (injection), Task 18 (workspace templates)

  **References**:

  **Pattern References**:
  - `install/traderbot-installer.sh` — main installer script with all credential flows
  - `install/services/install-service.sh` — systemd installer with %i bug
  - `install/services/install-launchd.sh` — launchd installer (more correct)
  - `install/services/traderbot-agent@.service` — systemd template with %i bug
  - `install/services/com.traderbot.agent.plist` — launchd template
  - `install/openclaw-agent-config.json` — config with unexpanded vars and hardcoded economics
  - `src/traderbot/cli.py` — cron setup command, profile commands
  - `src/traderbot/auth.py` — `_service_key_to_env` mapping with naming mismatches
  - `src/traderbot/cron_loops.py` — cron loop models

  **WHY Each Reference Matters**:
  - installer.sh is the gateway for setup — broken installer means nothing works
  - install-service.sh has the %i bug that makes systemd fail
  - auth.py has the env var naming mismatches that break `auth check`
  - openclaw-agent-config.json has hardcoded economics and unexpanded $HOME/$PROJECT_ROOT

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Installer passes shellcheck and env vars are expanded
    Tool: Bash (shellcheck + grep)
    Preconditions: Installer fixes merged
    Steps:
      1. shellcheck install/traderbot-installer.sh
      2. Expected: 0 errors
      3. grep -rn '\$HOME\|\$PROJECT_ROOT' install/openclaw-agent-config.json | wc -l
      4. Expected: 0 (all expanded at install time)
    Expected Result: Installer script passes shellcheck, config has no unexpanded vars
    Evidence: .sisyphus/evidence/task-19-installer.txt

  Scenario: Credential env vars match AuthManager expectations
    Tool: Bash (grep + pytest)
    Preconditions: Auth fixes merged
    Steps:
      1. grep -n "KALSHI_PRIVATE_KEY_PATH\|NEWSAPI_KEY\b" src/traderbot/auth.py | wc -l
      2. Expected: 2+ (both variants recognized)
      3. uv run pytest tests/ -x --tb=short -k "auth"
    Expected Result: Auth manager recognizes both naming variants
    Evidence: .sisyphus/evidence/task-19-auth-naming.txt

  Scenario: Service templates use correct username and env file
    Tool: Bash (grep)
    Preconditions: Service template fixes merged
    Steps:
      1. grep -n "User=%i\|WorkingDirectory=/home/%i" install/services/traderbot-agent@.service | wc -l
      2. Expected: 0 (no %i template variables left)
      3. grep -n "EnvironmentFile" install/services/traderbot-agent@.service | wc -l
      4. Expected: 1+ (env file loaded)
    Expected Result: Service file uses actual username, loads .env
    Evidence: .sisyphus/evidence/task-19-service-templates.txt

  Scenario: Cron setup command exists and wraps openclaw cron add
    Tool: Bash (pytest + grep)
    Preconditions: CLI verified
    Steps:
      1. grep -n "cron.setup\|cron_setup" src/traderbot/cli.py
      2. Expected: command exists
      3. uv run pytest tests/ -x --tb=short -k "cron"
    Expected Result: Cron setup command found and tested
    Evidence: .sisyphus/evidence/task-19-cron-setup.txt
  ```

  **Commit**: YES (group with Task 20)

- [x] 20. Fix service templates: remove self-initiated heartbeat polling

  **What to do**:
  - In `install/services/`:
    - Remove any `while true; sleep 300; traderbot heartbeat` polling loops from service templates
    - Heartbeat should be Gateway-initiated, not self-polling
    - Replace with documentation comment that OpenClaw Gateway initiates heartbeat turns
    - Ensure service files only start the main process, not heartbeat loops
  - Verify the Gateway config (`openclaw-agent-config.json`) has correct heartbeat settings:
    - `heartbeat.every: "30m"`
    - `heartbeat.target: "last"`

  **Must NOT do**:
  - Do NOT add self-initiated heartbeat as a fallback
  - Do NOT modify the Gateway itself

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 19)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 19

  **References**:

  **Pattern References**:
  - `install/services/` — systemd/launchd templates with self-initiated heartbeat
  - `install/openclaw-agent-config.json` — Gateway config

  **WHY Each Reference Matters**:
  - Self-initiated heartbeat polling conflicts with Gateway-initiated architecture
  - Service templates define how the agent runs in production

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No self-initiated heartbeat in service templates
    Tool: Bash (grep)
    Preconditions: Service templates fixed
    Steps:
      1. grep -rn "while.*sleep.*heartbeat\|heartbeat.*loop" install/services/
      2. Expected: 0 matches (no self-initiated heartbeat loops)
      3. grep -n "every.*30\|target.*last" install/openclaw-agent-config.json
      4. Expected: heartbeat.every: "30m" and heartbeat.target: "last" present
    Expected Result: No polling loops, correct Gateway heartbeat config
    Evidence: .sisyphus/evidence/task-20-service-templates.txt
  ```

  **Commit**: YES (group with Task 19)

- [x] 21. Full test suite pass + ruff check

  **What to do**:
  - Run `uv run pytest tests/ -x --tb=short` and ensure all tests pass
  - Run `ruff check src/` and fix any errors
  - Run `ruff format src/ tests/` and ensure formatting is clean
  - Verify VERSION file is correct and ready for tagging

  **Must NOT do**:
  - Do NOT add new tests (that was done in previous tasks)
  - Do NOT skip failing tests

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 22-25)
  - **Parallel Group**: Wave 5
  - **Blocks**: None
  - **Blocked By**: ALL implementation tasks (1-20)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass
    Tool: Bash (pytest)
    Preconditions: All implementation complete
    Steps:
      1. uv run pytest tests/ -x --tb=short
      2. Expected: All tests pass, 0 failures
    Expected Result: Clean test run
    Evidence: .sisyphus/evidence/task-21-test-suite.txt
  ```

  **Commit**: YES (Wave 5 verification)
  - Message: `test: verification passes for audit v2 remediation`

- [x] 22. V1 grep verification (no V1 remnants remain)

  **What to do**:
  - Run comprehensive grep for V1 remnants:
    - `grep -rn "yes_price" src/traderbot/kalshi/ | grep -v "V1\|deprecated\|comment"` → 0
    - `grep -rn "count[^_fp]" src/traderbot/kalshi/ | grep -v "count_fp\|comment\|# "` → 0 in API code
    - `grep -rn "/portfolio/orders[^/]" src/traderbot/kalshi/trading.py | grep -v "events`\ → 0
    - `grep -rn "action.*buy\|action.*sell" src/traderbot/kalshi/models.py | grep -v "OrderSide\|comment"` → 0
    - Verify MarketCategory.CRYPTO removal (if confirmed invalid)
    - Verify V1 WebSocket channels removed

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 21, 23-25)
  - **Parallel Group**: Wave 5
  - **Blocks**: None
  - **Blocked By**: Tasks 1-4

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No V1 API remnants
    Tool: Bash (grep)
    Preconditions: V2 migration complete
    Steps:
      1. grep -rn "yes_price" src/traderbot/kalshi/ | grep -v "V1\|deprecated\|comment\|# " | wc -l
      2. Expected: 0
      3. grep -rn "'/portfolio/orders'" src/traderbot/kalshi/ | grep -v "events" | wc -l
      4. Expected: 0
      5. grep -rn "orderbook[^_]" src/traderbot/kalshi/websocket.py | wc -l
      6. Expected: 0
    Expected Result: Zero V1 remnants in API-facing code
    Evidence: .sisyphus/evidence/task-22-v1-verification.txt
  ```

  **Commit**: NO (verification only)

- [x] 23. NewsAPI header verification

  **What to do**:
  - Verify `grep -n "apiKey.*self._newsapi_key" src/traderbot/news/sources.py` returns 0
  - Verify `grep -n "X-Api-Key" src/traderbot/news/sources.py` returns 3+ matches
  - Verify 401 handling raises permanent error
  - Verify daily budget enforcement works

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 21, 22, 24, 25)
  - **Parallel Group**: Wave 5
  - **Blocks**: None
  - **Blocked By**: Task 5

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: NewsAPI uses X-Api-Key header
    Tool: Bash (grep)
    Preconditions: Header migration complete
    Steps:
      1. grep -n "apiKey.*self._newsapi_key" src/traderbot/news/sources.py | wc -l
      2. Expected: 0
      3. grep -n "X-Api-Key" src/traderbot/news/sources.py | wc -l
      4. Expected: 3+
      5. grep -n "401\|NewsAPIAuthError" src/traderbot/news/sources.py | wc -l
      6. Expected: 2+ (permanent auth error handling)
    Expected Result: Security headers in place, 401 handled permanently
    Evidence: .sisyphus/evidence/task-23-newsapi-verification.txt
  ```

  **Commit**: NO (verification only)

- [x] 24. Injection strategy verification

  **What to do**:
  - Verify `python -c "from traderbot.profiles.injection_strategies import InjectionStrategy, FILE_STRATEGIES; print(list(InjectionStrategy)); print(list(FILE_STRATEGIES.keys()))"`
  - Verify all 4 strategies exist: FENCED_MERGE, INIT_IF_MISSING, ASK_THEN_MERGE, OVERWRITE
  - Verify file mapping covers all workspace files
  - Test end-to-end: fresh deploy creates all files, re-link preserves agent data

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 21-23, 25)
  - **Parallel Group**: Wave 5
  - **Blocks**: None
  - **Blocked By**: Task 12

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Injection strategies work end-to-end
    Tool: Bash (python + pytest)
    Preconditions: All injection code deployed
    Steps:
      1. python -c "from traderbot.profiles.injection_strategies import InjectionStrategy, FILE_STRATEGIES; print(list(InjectionStrategy)); print(list(FILE_STRATEGIES.keys()))"
      2. Verify 4 strategies enumerated, 11+ file mappings present
      3. uv run pytest tests/profiles/ -x --tb=short -k "injection"
    Expected Result: All strategies and mappings enumerated, tests pass
    Evidence: .sisyphus/evidence/task-24-injection-verification.txt
  ```

  **Commit**: NO (verification only)

- [x] 25. Installer dry-run verification

  **What to do**:
  - Run shellcheck on installer script
  - Verify env var expansion in generated config (no `$HOME` literals)
  - Verify cron setup command works (`traderbot cron setup --help` at minimum)
  - Verify heartbeat settings in generated config (every: 30m, target: last)
  - Verify no self-initiated heartbeat loops in service templates

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs install fixes done)
  - **Parallel Group**: Wave 5
  - **Blocks**: None
  - **Blocked By**: Tasks 19, 20

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Installer config clean
    Tool: Bash (shellcheck + grep)
    Preconditions: Installer fixes merged
    Steps:
      1. shellcheck install/traderbot-installer.sh
      2. Expected: 0 errors
      3. grep -rn '\$HOME\|\$PROJECT_ROOT' install/openclaw-agent-config.json | wc -l
      4. Expected: 0 (all expanded)
      5. grep -n "every.*30\|target.*last" install/openclaw-agent-config.json | wc -l
      6. Expected: 2+ (heartbeat config present)
    Expected Result: Installer passes shellcheck, config clean
    Evidence: .sisyphus/evidence/task-25-installer-verification.txt
  ```

  **Commit**: NO (verification only)

- [x] 26. Fix token security: eliminate all plain text token leaks in CLI, logs, workspace files, and service templates

  **What to do**:
  - **CRITICAL FIXES** (token values currently exposed):
    - `src/traderbot/cli.py:2226-2234`: `profile assignments` prints **full tokens** in rich table → mask all but last 4 chars
    - `src/traderbot/cli.py:2410-2421`: `profile auth --json` leaks **full credential keys** → mask in JSON output too
    - `src/traderbot/profiles/runtime.py:42`: `logger.warning("Invalid or revoked token: %s", token)` logs full token → mask
    - `src/traderbot/profiles/tokens.py:158,165`: `logger.info("Revoked token: %s", token)` logs full token → mask
    - `src/traderbot/profiles/tokens.py:187`: `logger.warning("Failed to parse token data for %s: %s", token, e)` logs full token → mask
    - `src/traderbot/profiles/injection.py:68`: TOOLS.md receives **actual token value** → change to inject env var NAME only, not value. Agent should read token from `TRADERBOT_PROFILE_TOKEN` env var at runtime, not from workspace file.
  - **HIGH FIXES**:
    - `src/traderbot/cli.py:2135`: `profile assign` reveals first 4 chars → show only `****abcd` (last 4, not first)
    - `src/traderbot/cli.py:2430`: `profile auth` reveals first 8 chars of key → reduce to 4
    - `install/services/traderbot-agent@.service:24`: Replace `Environment=TRADERBOT_PROFILE_TOKEN=<PROFILE_TOKEN>` with `EnvironmentFile=%h/.traderbot/.env` (load from restricted file, not inline)
    - `install/services/com.traderbot.agent.plist:19-20`: Replace inline token with file-based env loading
  - **MEDIUM FIXES**:
    - `src/traderbot/profiles/tokens.py:121,134,155`: Keyring service names contain the token (`traderbot.tokens.{token}`). Change to use token hash or ID instead of raw token in service name.
    - `src/traderbot/cli.py:560-567`: Bootstrap `.env` fallback write does NOT enforce `chmod 600` → add explicit permission
    - Set `.env` file permissions to 600 everywhere it's created
    - Set PEM key file permissions to 600
  - **WORKSPACE FILE SECURITY**:
    - `.openclaw/workspace/TOOLS.md` (line 11): Remove references to `.env` file and credential variable names. The agent should not know where credentials are stored.
    - Remove internal paths: `skills/traderbot/SKILL.md`, `src/traderbot/simulation/strategies/`, `~/.openclaw/openclaw.json`
    - Remove `pip install -e .` reference (agent shouldn't install software)
  - Add tests for token masking in CLI output and logs

  **Must NOT do**:
  - Do NOT remove diagnostic capability entirely — masked tokens are fine
  - Do NOT store actual token values in workspace files
  - Do NOT let the agent know where tokens are stored on disk

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with other Wave 2/5 tasks)
  - **Parallel Group**: Wave 2 (security)
  - **Blocks**: F1-F4
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/cli.py` — CLI commands that may display tokens
  - `src/traderbot/profiles/injection.py` — inject_token() that must inject NAME not VALUE
  - OpenClaw security docs: "Never put secrets in workspace files — they become part of the prompt context"
  - OpenClaw secrets docs: SecretRefs system for credential management

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No plain text tokens in CLI output
    Tool: Bash (grep)
    Preconditions: Token masking implemented
    Steps:
      1. grep -rn "print.*token\|click.echo.*token\|typer.echo.*token" src/traderbot/cli.py | grep -v "mask\|truncat\|last.*4\|••••\|\*\*\*\*" | wc -l
      2. Expected: 0 (no commands print full tokens)
      3. grep -rn "logger.*key\|logger.*token\|logger.*secret" src/traderbot/ | grep -v "mask\|redact\|truncat" | wc -l
      4. Expected: 0 (no logger calls with raw key/token values)
    Expected Result: No plain text token output anywhere
    Evidence: .sisyphus/evidence/task-26-token-security.txt

  Scenario: inject_token writes env var NAME not VALUE
    Tool: Bash (grep)
    Preconditions: Injection code audited
    Steps:
      1. grep -n "inject_token" src/traderbot/profiles/injection.py
      2. Review: verify it writes NAME reference (e.g., "export TRADERBOT_PROFILE_TOKEN=...") not actual value
    Expected Result: inject_token writes env var names, not values
    Evidence: .sisyphus/evidence/task-26-inject-token-audit.txt

  Scenario: .env file has correct permissions
    Tool: Bash
    Preconditions: Permission fix merged
    Steps:
      1. Check installer sets chmod 600 on ~/.traderbot/.env and ~/.traderbot/kalshi_key.pem
      2. grep -n "chmod 600\|0600" install/traderbot-installer.sh | wc -l
      3. Expected: 2+ (.env and .pem)
    Expected Result: Sensitive files created with restricted permissions
    Evidence: .sisyphus/evidence/task-26-file-permissions.txt
  ```

  **Commit**: YES
  - Message: `fix(security): mask tokens in CLI output, logs, and exception messages`
  - Files: `src/traderbot/cli.py`, `src/traderbot/profiles/injection.py`, `install/traderbot-installer.sh`, tests

- [x] 27. Fix env_file to absolute path in all BaseSettings subclasses

  **What to do**:
  - In `src/traderbot/kalshi/config.py`:
    - Change `env_file=".env"` to `env_file=str(Path.home() / ".traderbot" / ".env")` or equivalent absolute path
  - In `src/traderbot/kalshi/client.py` (if it has its own BaseSettings):
    - Same fix to absolute path
  - In `src/traderbot/kalshi/websocket.py` (if it has its own BaseSettings):
    - Same fix to absolute path
  - Standardize on `~/.traderbot/.env` as the canonical credential location
  - Ensure all code that reads credentials uses this canonical path or falls back to CWD `.env`
  - Add `EnvironmentFile=%h/.traderbot/.env` to systemd template
  - Add `EnvironmentVariables` dict to launchd plist reading from `~/.traderbot/.env`

  **Must NOT do**:
  - Do NOT hardcode user-specific paths — use `Path.home()`
  - Do NOT break existing tests that may rely on CWD `.env`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (independent of other tasks)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 19 (installer env_file config)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/config.py` — env_file=".env" (relative)
  - `src/traderbot/kalshi/client.py` — possible BaseSettings with relative env_file
  - Metis finding: "Three BaseSettings classes use env_file='.env' (relative). The plan only fixes the installer, but the classes themselves remain broken for CLI/manual usage."

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: env_file is absolute in all BaseSettings
    Tool: Bash (grep)
    Preconditions: Path fix merged
    Steps:
      1. grep -rn 'env_file="\.env"' src/traderbot/ | wc -l
      2. Expected: 0 (no relative .env paths)
      3. grep -rn 'env_file=' src/traderbot/kalshi/ | grep -v "traderbot" | wc -l
      4. Expected: 0 (all use absolute ~/.traderbot/.env)
    Expected Result: All BaseSettings use absolute env_file path
    Evidence: .sisyphus/evidence/task-27-env-file-absolute.txt
  ```

  **Commit**: YES
  - Message: `fix(config): change env_file to absolute path in all BaseSettings subclasses`

- [x] 28. Standardize NewsAPI env var naming and add OpenClaw SecretRefs support

  **What to do**:
  - In `src/traderbot/auth.py`:
    - Update `_service_key_to_env` to recognize `NEWSAPI_KEY` as a fallback alias for `NEWSAPI_API_KEY`
    - Update `_service_key_to_env` to recognize `KALSHI_PRIVATE_KEY_PATH` as a fallback alias for `KALSHI_PRIVATE_KEY_PEM`
  - In `src/traderbot/profiles/config.py` (or wherever `NEWSAPI_KEY` is read directly):
    - Change `os.environ.get("NEWSAPI_KEY")` to use `AuthManager` for credential resolution (follows auth.py naming convention)
    - Or add `NEWSAPI_KEY` as a recognized fallback
  - In `install/openclaw-agent-config.json`:
    - Add OpenClaw SecretRefs for API tokens: KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH, NEWSAPI_API_KEY, VOYAGE_API_KEY
    - Use `{ "source": "env", "provider": "default", "id": "KALSHI_API_KEY" }` format
    - This integrates with OpenClaw's secrets management instead of plaintext config
  - Document that TraderBot tokens should be provided via env vars, NOT stored in openclaw.json plaintext

  **Must NOT do**:
  - Do NOT break existing NEWSAPI_KEY env var users — add fallback alias
  - Do NOT store actual key values in openclaw.json — use SecretRefs only
  - Do NOT remove `.env` file support — SecretRefs complement it, not replace it

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (independent)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 19 (installer)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/auth.py:_service_key_to_env` — env var naming mapping
  - `src/traderbot/profiles/config.py:108` — reads NEWSAPI_KEY directly (not via AuthManager)
  - `install/openclaw-agent-config.json` — config that needs SecretRefs
  - OpenClaw secrets docs: SecretRef format `{ source: "env", provider: "default", id: "ENV_VAR_NAME" }`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: AuthManager recognizes both NEWSAPI_KEY and NEWSAPI_API_KEY
    Tool: Bash (grep + pytest)
    Preconditions: Naming fix merged
    Steps:
      1. grep -n "NEWSAPI_KEY\b" src/traderbot/auth.py | wc -l
      2. Expected: 1+ (fallback alias exists)
      3. uv run pytest tests/ -x --tb=short -k "auth"
    Expected Result: Auth manager recognizes both env var names
    Evidence: .sisyphus/evidence/task-28-auth-naming.txt

  Scenario: OpenClaw config uses SecretRefs not plaintext
    Tool: Bash (grep)
    Preconditions: SecretRefs added
    Steps:
      1. grep -c "source.*env\|provider.*default" install/openclaw-agent-config.json
      2. Expected: 4+ (one for each API service: Kalshi key, Kalshi key path, NewsAPI, Voyage)
      3. grep -c "apiKey.*sk_\|apiKey.*[a-f0-9]\{32\}" install/openclaw-agent-config.json
      4. Expected: 0 (no actual key values in config)
    Expected Result: SecretRefs present, no plaintext keys
    Evidence: .sisyphus/evidence/task-28-secretrefs.txt
  ```

  **Commit**: YES
  - Message: `fix(auth): standardize env var naming, add OpenClaw SecretRefs support`

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read plan end-to-end. Verify every Must Have present, every Must NOT Have absent. Check evidence files. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check src/` + `uv run pytest tests/ -x --tb=short`. Review all changed files for: `as any`/`# type: ignore`, empty catches, console.log in prod, commented-out code, unused imports, AI slop patterns.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Run every QA scenario from every task. Test cross-task integration. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify no scope creep. Check Must NOT Have compliance. Detect unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `fix(kalshi): migrate to V2 API field names and endpoints` (after Tasks 1-4)
- **Wave 2**: `fix(security): NewsAPI header, WAL fd leak, heartbeat paths` (after Tasks 5-8)
- **Wave 3**: `refactor(profiles): switch injection from overwrite to fenced-merge strategy` (after Tasks 9-13)
- **Wave 4a**: `fix(workspace): correct agent instruction files` (after Tasks 14-18)
- **Wave 4b**: `fix(installer): env var expansion, all categories, correct services` (after Tasks 19-20)
- **Wave 5**: `test: verification passes for V2 migration and injection refactor` (after Tasks 21-25)
- Each commit tagged per project versioning convention

---

## Success Criteria

### Verification Commands
```bash
cd /Users/djtchill/Desktop/TraderBot
grep -rn "yes_price\|/portfolio/orders[^/]\|action.*buy\|action.*sell" src/traderbot/kalshi/trading.py src/traderbot/kalshi/portfolio.py src/traderbot/kalshi/_normalize.py src/traderbot/kalshi/models.py | grep -v "V1\|v1\|deprecated\|#.*V1\|orderbook_delta" | wc -l  # Expected: 0
grep -n "apiKey.*self._newsapi_key" src/traderbot/news/sources.py | wc -l  # Expected: 0
uv run pytest tests/ -x --tb=short  # Expected: all pass
ruff check src/  # Expected: 0 errors
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] No V1 API references in API-facing code
- [ ] No apiKey as query parameter
- [ ] No plain text tokens in CLI output (grep for full token prints)
- [ ] No plain text tokens in logger calls (grep for logger.*token)
- [ ] No actual token VALUE in workspace TOOLS.md (only env var name)
- [ ] No internal paths or .env references in workspace files
- [ ] Service templates use EnvironmentFile not inline Environment=
- [ ] .env and PEM files have chmod 600
- [ ] Installer credentials path matches KalshiConfig env_file path (or explicit EnvironmentFile in services)
- [ ] Installer env var names match AuthManager expectations
- [ ] Profile injection uses fenced-merge for AGENTS/SOUL/TOOLS/IDENTITY
- [ ] Profile injection uses INIT_IF_MISSING for USER/MEMORY/SESSION-STATE/HEARTBEAT_DATA/.learnings (deploy template if absent, skip if present)
- [ ] Bootstrap-prompt injection for BOOTSTRAP/BOOT/HEARTBEAT (ask user, then fenced-merge)
- [ ] Installer expands env vars correctly
- [ ] Workspace files contain no phantom CLI commands