# COMPREHENSIVE AUTOMATED CODE REVIEW AND TESTING PROTOCOL

> **Purpose:** This document is a prompt for LLM agents performing systematic code review and testing of the TraderBot project. It provides exhaustive checklists for every phase, grounded in how Python 3.12+, Pydantic v2, pytest, and async I/O actually work. Every module and execution path must be reviewed.

> **Critical principle:** The checklists in this document define the MINIMUM scope of review — they are a starting point, not an exhaustive list of everything that could be wrong. The reviewer MUST go beyond the specific items listed here and perform thorough, original analysis on every function, module, and execution path. Do not limit your review to checking items off a list; actively seek bugs, logic errors, and structural problems that are NOT anticipated by the checklists. The goal is to discover ALL issues, not just confirm that listed checks pass.

## Subagent Usage Guidelines

This review protocol is designed to be executed by a lead agent orchestrating subagents (explore, librarian, oracle, etc.) for maximum parallelism and coverage. Follow these guidelines to use subagents effectively:

### When to Use Subagents vs. Direct Tools

| Task Type | Best Approach | Why |
|-----------|--------------|-----|
| Searching for a **known pattern** (e.g., `grep 'float'` for monetary precision bugs) | **Direct tools** (grep, read, ast_grep) | You already know exactly what to search for; subagent overhead is wasted |
| Discovering **unknown patterns** (e.g., "find all functions that both read position and call trading") | **Explore subagent** | You know the shape of the bug but not the exact pattern; subagent can search broadly |
| Checking **external library behavior** (e.g., how Kalshi API handles rate limiting) | **Librarian subagent** | Requires documentation lookup, not local code search |
| **Architecture decisions** or debugging **hard problems** after 2+ failed attempts | **Oracle subagent** | Expensive but high-quality reasoning for complex tradeoffs |

### Subagent Prompt Structure (MANDATORY)

Every subagent delegation MUST include these 6 sections. Vague prompts produce poor results:

```
1. CONTEXT: What task I'm working on, which files/modules are involved, and what approach I'm taking
2. GOAL: The specific outcome I need — what decision or action the results will unblock
3. DOWNSTREAM: How I will use the results — what I'll build/decide based on what's found
4. REQUEST: Concrete search instructions — what to find, what format to return, and what to SKIP
5. CONSTRAINTS: File paths, severity levels, patterns to exclude, known false positives to ignore
6. ANTI-PATTERNS: What NOT to do (e.g., "Don't just list files — show the specific line with context")
```

### Parallelism Rules

- **Fire 3-5 explore agents in parallel** for discovery tasks (Phase 0 architecture, Phase 1 static analysis)
- **Fire 2-3 librarian agents** when external documentation is needed (Kalshi API, Pydantic behavior, Kelly criterion math)
- **Never block** waiting for a single subagent — continue with non-overlapping work
- **Cross-reference** subagent results before trusting them — always verify a sample of findings directly
- **Prefer direct tools for targeted checks** — if you can write the grep pattern yourself, do it. Reserve subagents for genuine discovery.

### Subagent Anti-Patterns

1. **Don't ask one subagent to "analyze everything."** Break broad tasks into narrow, pattern-specific searches. One subagent per bug class, per module group, per pattern.
2. **NEVER repeat work assigned to a subagent.** Once you delegate a search to a subagent, you MUST NOT run the same search yourself. If an explore agent was tasked with finding all `float` usage for monetary values, running `grep 'float'` yourself is FORBIDDEN — you already delegated that work. Wait for the subagent's results, then use them. The only exception is verifying a small sample (3-5 items) to confirm accuracy.
3. **Don't trust subagent results blindly.** Verify a sample of findings (3-5 items) directly before relying on the full result set. This is sample verification, not a full re-search.
4. **Don't delegate trivial checks.** If you can run `grep -n 'float' src/traderbot/risk/` in 2 seconds, do it yourself. Don't spawn a subagent for that.
5. **Don't forget to cancel** idle background subagents after collecting results.

Execute a systematic, multi-phase review and testing cycle. Do not stop at static analysis. Each phase must be completed before moving to the next. Found bugs must be fixed, then ALL tests re-run from the beginning.

---

## PHASE 0: CODEBASE ARCHITECTURE MODEL

Perform this phase FIRST. Its findings feed into and expand the scope of all subsequent phases.

**Phase 0 is not just about checking the items listed below.** It is about building a complete mental model of the codebase — understanding every module's role, every type's lifecycle, every function's callers and callees, every import chain. If you identify a dependency, import cycle, or architecture issue that is NOT listed in the sections below, document it and classify it. The sections below define MINIMUM coverage.

**Phase 0 Gate:** Before proceeding to Phase 1, all Phase 0 findings must be documented and classified. Any P0 finding from Phase 0 (e.g., import cycle that prevents type checking) must be fixed before continuing, because it blocks all subsequent testing.

### 0.1 Module Dependency Map

Map the complete import tree: which module imports which, in what order.

Trace the entry point initialization sequence step by step from `cli.py` to each module.

Document which modules are loaded before others and why that order matters.

Identify which modules use async I/O and which use sync computation.

**Verify the documented dependency rules from docs/architecture.md:**

- `kalshi/` depends on: nothing (pure I/O)
- `analysis/` depends on: `kalshi/models` (Pydantic types only)
- `risk/` depends on: `kalshi/models`, `db/positions` (to check current exposure)
- `simulation/` depends on: `kalshi/history`, `analysis/`, `risk/`
- `news/` depends on: `kalshi/models` (for market category mapping)
- `db/` depends on: `kalshi/models`

**CRITICAL ARCHITECTURE RULE**: `risk/` never depends on `analysis/` or `news/`. Risk guards must be enforceable without understanding strategy signals. A signal can suggest "buy everything" — the risk module checks exposure regardless of signal quality.

**Verify**: Check imports in every `risk/` module file. If any `risk/` file imports from `analysis/` or `news/`, that is a P0 architecture violation.

**Verify**: Does `risk/` depend on `db/` for position data? Is the dependency only for read access (checking exposure), not for strategy signals?

### 0.2 Type and Variable Namespace Map

List ALL Pydantic model definitions across every module.

Identify any model name collisions across modules (e.g., two modules defining a `Trade` model).

Identify any base type that is extended inconsistently (e.g., `BaseModel` vs `BaseModel` from different sources).

Check that all Pydantic models use `ConfigDict(strict=True, extra="forbid")` per AGENTS.md.

For each shared type: document which module defines it, which modules consume it, and whether any module redefines it.

### 0.3 Function and Import Namespace Map

List ALL public function definitions across every module.

Identify any function name collisions across modules.

Identify any async/sync inconsistency in function signatures where the caller expects one but the callee provides the other.

Check: does any function in `kalshi/` shadow a built-in or standard library function?

Verify import boundaries: every import in every module should come from the documented dependency graph.

### 0.4 Async/Sync Boundary Audit

Map which functions are `async` and which are sync.

Identify any `await` in sync functions or missing `await` in async callers.

Trace the call chain from `cli.py` through each module to verify async gates are handled correctly.

Check: does `analysis/` (sync computation) ever call `kalshi/` (async I/O) directly without proper awaiting?

### 0.5 Architecture Diagram

Produce a dependency diagram: `cli.py` → modules → sub-modules.

Mark each edge with what is consumed (types, functions, data).

Highlight circular dependencies or fragile ordering assumptions.

Verify: `simulation/` depends on `risk/` — is this only for reading limits, not for strategy logic?

Verify: `db/` depends only on `kalshi/models` — is there any hidden dependency on `analysis/` or `news/`?

### 0.6 Bug Class Taxonomy and Custom Check Generation

**Purpose:** Phase 0 doesn't just model what IS — it must model what GOES WRONG. Every bug found (whether during review cycles OR manually between them) represents a **bug class** that may have additional instances. Phase 0 must extract the general pattern from each past bug and generate custom checks for the current cycle.

**Critical: Catalog PATTERNS, not instances.** Bug class entries must NEVER reference specific line numbers, function names, file paths, or version numbers. These details are transient — the pattern is permanent. A good bug class description applies equally to ANY codebase with the same architectural structure, not just this one at a specific point in time.

**CRITICAL: Include bugs found outside review cycles.** Many bugs are found by manual testing, user reports, or ad-hoc investigation between formal review cycles. These bugs are EQUALLY valuable for pattern extraction. Before each review cycle:

1. Review `git log --oneline` since the last review cycle for commits containing `fix`, `Fix`, or `bug`
2. Review CHANGELOG.md entries since the last review cycle
3. Ask the user: "Were any bugs found manually since the last review cycle?"
4. For EACH bug found, extract the bug class

**Bug class extraction process:**
For EACH bug found since the last review cycle:

1. **Generalize the bug**: Strip ALL instance-specific details. What is the abstract pattern?
2. **Identify the class**: What structural condition enables this pattern? Where else could it occur?
3. **Generate a check**: Write a concrete, executable check that finds ALL instances of this class in the CURRENT codebase
4. **Add to the appropriate phase**: Insert the check with a `[BUG-CLASS]` tag

**Bug class catalog (accrues across review cycles — never remove entries):**

| Bug Class | Abstract Pattern | Custom Check |
|-----------|-----------------|--------------|
| Float for monetary cents | A module uses `float` for currency values that should be `int` (cents). Rounding errors in financial calculations. | Verify all money-related fields in Pydantic models use `int` for cents, not `float`. Check `risk/` HARD_LIMITS values. |
| Risk limit bypass via config | Risk limits are read from a config file or environment variable instead of being compiled into the module. Agent can modify limits without code change. | Verify `risk/` module has NO `os.environ`, `pathlib.Path().read_text()`, `json.load()`, or similar config-reading code. All limits must be hardcoded constants. |
| Strategy logic in toolkit | The toolkit computes a signal strength or generates a trading recommendation, crossing the toolkit/agent boundary. The toolkit should only compute, never recommend. | Verify no function in `risk/`, `kalshi/`, or `db/` returns a buy/sell/hold signal. Verify `analysis/` returns numerical scores only, not direction recommendations. |
| Async in wrong context | An `async` function is called without `await` in an async context, or a sync function calls an async function without proper event loop handling. | Trace all async call sites. Verify every `async def` is awaited at its call site. |
| Import cycle | Module A imports from module B which imports from module A, causing import failure or type checking failure. | Run `python -c "import traderbot"` as a smoke test. Run `mypy --no-error-summary src/traderbot/` and check for import-cycle errors. |
| Pydantic strict mode violation | A Pydantic model accepts fields not defined in the model type, or coerces types that should be rejected (e.g., string "123" to int 123). | Verify all models have `ConfigDict(strict=True, extra="forbid")`. Test with `model.model_validate` using wrong types. |
| Audit trail gap | A trade decision is made without a corresponding audit log entry. The decision/rejection is not recorded. | Trace every trade execution and rejection path. Verify each path calls the audit logger before returning. |
| Circuit breaker not persistent | Circuit breaker state is held in memory only, lost on restart. A halted system can restart and resume trading without human intervention. | Verify circuit breaker state is written to `SESSION-STATE.md` or equivalent persistent store. Verify on startup the state is read and respected. |

**Custom check generation template:**
```
Bug Class: [abstract name — NO line numbers, NO function names, NO file paths]
Abstract Pattern: [general description that could apply to any codebase with this structure]
How to Detect: [concrete methodology to find ALL instances in current codebase]
Phase: [which phase this check belongs in]
Expected Severity: [P0/P1/P2 if found]
```

**Phase 0 Gate Addition:** Before proceeding to Phase 1, ALL bugs found since the last review cycle (both during-review AND manual/outside) must have their bug class extracted, generalized, and custom checks inserted into the appropriate phase sections.

---

## PHASE 1: STATIC CODE ANALYSIS

All findings from this phase must be classified by severity:
- **P0 (Fatal):** Module won't import, crashes immediately, risk limits bypassed, data loss risk
- **P1 (Critical):** Core feature broken, wrong behavior, silent data corruption, strategy logic in toolkit
- **P2 (Major):** Error path mishandled, missing validation, incorrect fallback, type coercion
- **P3 (Minor):** Style, formatting, documentation gaps, non-idiomatic patterns

### 1.1 Linter and Formatter Validation

Run `ruff check` on ALL Python files:
- `src/traderbot/**/*.py`
- `tests/**/*.py`

Run `ruff format --check` on ALL Python files.

Document EVERY warning and error. Do not filter. Classify each finding as P0/P1/P2/P3.

### 1.2 Type Checker Validation

Run `mypy` (or `pyright`) on the codebase with strict settings.

Check for `# type: ignore` comments — these are forbidden by AGENTS.md (no `as any`, no `# type: ignore`).

Check for `Any` type usage that bypasses type checking.

Check for `float` used where `int` should be used (monetary precision).

Verify all Pydantic models declare `ConfigDict(strict=True, extra="forbid")`.

Verify `pyproject.toml` configures mypy/ruff with appropriate settings.

### 1.3 Risk Module Import Audit

**CRITICAL — P0 architecture violation detection:**

Check every file in `src/traderbot/risk/` for imports:

```python
# Files to check:
src/traderbot/risk/__init__.py
src/traderbot/risk/limits.py
src/traderbot/risk/sizing.py
src/traderbot/risk/breaker.py
src/traderbot/risk/audit.py
```

For each file:
1. Does it import from `analysis/`? (P0 violation)
2. Does it import from `news/`? (P0 violation)
3. Does it read any config file (`.json`, `.yaml`, `.env`)? (P0 — limits must be compiled in)
4. Does it import from `kalshi/models`? (Allowed — type definitions)
5. Does it import from `db/positions`? (Allowed — position read-only)

### 1.4 Monetary Precision Audit

**Float for cents is a P1 bug.** Financial calculations must use integer cents.

Search for ALL `float` usage in the codebase that relates to money:

```bash
grep -rn 'float' src/traderbot/risk/ src/traderbot/db/ src/traderbot/kalshi/
```

For each hit:
1. Is this a monetary value (price, quantity, position, P&L, limit)?
2. If yes, should it be `int` (cents) or `Decimal` instead?
3. Check `HARD_LIMITS` in `risk/limits.py` — are these stored as float or int?

Verify `risk/` module uses `Decimal` or integer cents for all monetary calculations, never float.

### 1.5 Pydantic Model Strict Mode Audit

Verify ALL Pydantic models have `ConfigDict(strict=True, extra="forbid")`:

```bash
grep -rn 'class.*BaseModel' src/traderbot/
```

For each model found, verify:
1. Has `model_config = ConfigDict(strict=True, extra="forbid")` or equivalent
2. No `Field(default=...)` with implicit None that bypasses strict mode
3. No `@field_validator` that silently coerces types

Test with invalid inputs:
```python
model.model_validate({"field": "not_an_int"})  # Should raise
model.model_validate({"extra_field": 123})     # Should raise (extra=forbid)
```

### 1.6 Audit Trail Completeness Audit

Every trading function must have a corresponding audit log call.

Search for trade execution and rejection paths:

```bash
grep -rn 'def.*trade\|def.*execute\|def.*order\|def.*reject' src/traderbot/
```

For each trading-related function:
1. Does it call the audit logger?
2. Is the audit entry written BEFORE the function returns?
3. Does the audit entry include: timestamp, ticker, direction, quantity, price, signal_strength, risk_checks, outcome, rejection_reason?

Verify `risk/breaker.py` logs when circuit breaker activates.

Verify `risk/limits.py` logs each limit check result.

### 1.7 Import Graph Validation

Run a Python import to verify no import cycles:

```bash
python -c "import traderbot; print('Import OK')"
```

Run mypy to verify no import-cycle type errors:

```bash
mypy src/traderbot/ 2>&1 | grep -i 'import'
```

Document any import failures or cycles.

### 1.8 Circuit Breaker Persistence Audit

Verify circuit breaker state is persisted to disk:

1. Check `SESSION-STATE.md` or equivalent is written when FULL_STOP triggers
2. Check startup code reads and respects circuit breaker state
3. Verify no code path can clear the FULL_STOP flag without human intervention

### 1.9 Async/Sync Boundary Verification

Trace every async function:

```bash
grep -rn 'async def\|await ' src/traderbot/
```

For each `async def`:
1. All call sites must use `await`
2. No `async def` is called from a sync function without explicit event loop handling
3. Verify `cli.py` uses `asyncio.run()` or similar to invoke async modules

---

## PHASE 2: UNIT TESTS

**Beyond the listed tests:** The test cases in sections 2.1–2.x cover specific scenarios, but the reviewer MUST also think about what is NOT listed. For each module, consider: "What happens with empty input? What happens with maximum-length input? What happens when a prerequisite fails silently?" Design ADDITIONAL test cases beyond those listed.

All tests in Phase 2 use mocks for external I/O. No real Kalshi API calls.

### 2.1 Pydantic Model Validation Tests

Test each Pydantic model for:

**Valid data roundtrip:**
```python
model.model_validate(valid_data)  # Should pass
model.model_dump()  # Should serialize back correctly
```

**Invalid type rejection:**
```python
with pytest.raises(ValidationError):
    model.model_validate(invalid_type_data)
```

**Extra field rejection (strict mode):**
```python
with pytest.raises(ValidationError):
    model.model_validate({"extra_field": 123})
```

**Edge cases for each model:**

For `KalshiClient` response models:
- Missing required fields
- Fields with wrong types (string where int expected)
- Fields with out-of-range values (negative for quantities, etc.)

For market data models (`Market`, `OrderBook`, `Trade`):
- Zero liquidity
- Negative prices (invalid for prediction markets)
- Extremely large values (overflow potential)

For trade request models:
- Quantity of 0
- Quantity exceeding position limits
- Negative edge values

For position models:
- Negative current value
- Unrealized loss exceeding daily loss limit

### 2.2 KalshiClient Tests

Test `KalshiClient` with mocked responses:

**Authentication:**
- Valid key/secret produces correct signature
- Invalid/missing credentials raises appropriate error
- Token refresh logic works correctly

**Retry logic:**
- Successful request on first try
- Successful request after one retry (transient failure)
- Failure after max retries raises exception
- Rate limit (429) triggers proper backoff

**Demo mode:**
- Client initializes in demo mode without API keys
- Demo mode returns structured mock data
- Demo mode does NOT make real API calls

**Response normalization:**
- Raw Kalshi API response → Pydantic model
- Verify no data loss in normalization
- Verify nested objects are properly parsed

**Market data operations:**
- `get_markets()` returns list of `Market` objects
- `get_market()` returns single `Market` with orderbook
- `get_orderbook()` returns properly structured orderbook
- `get_trades()` returns list of `Trade` objects
- Pagination: verify cursor-based pagination works, verify all pages retrieved

### 2.3 WebSocket Tests

Test `KalshiWebSocket` with mocked WebSocket:

**Connection:**
- Connects to correct WebSocket URL
- Sends authentication on connect
- Handles connection failure gracefully

**Subscribe/Unsubscribe:**
- Subscribing to a market registers correct subscription
- Unsubscribing removes subscription
- Duplicate subscription handling is idempotent

**Reconnect:**
- On disconnect, automatic reconnect attempt
- Reconnect uses exponential backoff
- After max retries, raises exception or switches to polling

**Message parsing:**
- Market update messages parse correctly
- Trade messages parse correctly
- Unknown message types are logged and skipped (not fatal)

**Message handling:**
- Callback is invoked with parsed message
- Callback exception does not crash WebSocket loop

### 2.4 Risk Limit Tests

Test each limit in `risk/limits.py`:

**Per-market position limit (max 5%):**
- Position value at exactly 5% of portfolio: PASS
- Position value at 5.01% of portfolio: FAIL (reject)
- New order that would push position over 5%: FAIL

**Daily loss limit (max 2%):**
- Daily loss at exactly 2%: PASS (halt trading)
- Daily loss at 2.01%: FAIL (same action)
- Loss calculation: realized + unrealized

**Maximum drawdown (max 10%):**
- Drawdown at exactly 10%: PASS (halt trading)
- Drawdown at 10.01%: FULL_STOP (all trading halted)

**Liquidity threshold (min 1000 open interest):**
- Open interest at 1000: PASS
- Open interest at 999: FAIL (market excluded)

**Minimum edge (min 3%):**
- Edge at exactly 3%: PASS
- Edge at 2.99%: FAIL

**HARD_LIMITS immutability:**
- Verify `HARD_LIMITS` dict keys cannot be changed at runtime
- Verify `HARD_LIMITS` values cannot be modified after import
- Verify no code in `risk/` reads limits from config files

### 2.5 Kelly Criterion Tests

Test Kelly sizing in `risk/sizing.py`:

**Mathematical correctness:**
```
f* = (bp - q) / b
where b = odds, p = probability, q = 1 - p
```

Verify calculation against known values:
- If b=2, p=0.6, q=0.4: f* = (2*0.6 - 0.4) / 2 = 0.4
- If b=1, p=0.55, q=0.45: f* = (1*0.55 - 0.45) / 1 = 0.1

**Fraction clamping:**
- Full Kelly result clamped to [0.1, 0.5] Kelly fraction range
- Half-Kelly (0.5 * f*) is within range
- Zero edge produces zero or negative f* (clamped to 0, no position)

**Zero/negative inputs:**
- Zero probability: f* should be 0 or negative (clamped to 0)
- Probability <= 0.5 with odds=1: f* should be 0 or negative (clamped to 0)
- Negative odds: invalid input raises error

**Confidence scaling:**
```
sized_position = kelly_fraction * confidence * bankroll
```
- With 50% Kelly and 0.8 confidence, result is 0.4 * bankroll
- Result capped at per-market limit regardless of confidence

### 2.6 Circuit Breaker Tests

Test `risk/breaker.py`:

**Level 1 (Slow — 1% daily loss):**
- Daily loss crosses 1% threshold: position sizes reduced 50%
- Position size after reduction still passes per-market limit

**Level 2 (Halt — 2% daily loss):**
- Daily loss crosses 2% threshold: no new trades, existing positions held
- Recovery: automatic at next market open (next day)

**Level 3 (Full Stop — 10% drawdown):**
- Drawdown crosses 10%: ALL trading halted
- State persists to `SESSION-STATE.md`
- Manual recovery required (human clears flag)

**Persistence:**
- State written to disk on trigger
- State read from disk on startup
- FULL_STOP cannot be cleared by code (requires human)

**Recovery behavior:**
- Level 1/2 recovery tested: system resumes after market open
- Level 3 recovery: system does NOT auto-resume

### 2.7 Audit Trail Tests

Test `risk/audit.py` and `db/decisions.py`:

**Logging:**
- Every decision (executed or rejected) logged
- Log entry contains all required fields
- Timestamp is accurate

**Filtering:**
- Can filter by date range
- Can filter by ticker
- Can filter by outcome (executed/rejected/held)

**Append-only:**
- Existing log file is not overwritten
- New entries appended to existing file

**JSONL format:**
- Each line is valid JSON
- No malformed lines in log file

---

## PHASE 3: INTEGRATION TESTS

### 3.1 Full Trade Evaluation Flow Tests

Test the complete flow: `TradeRequest` → `risk/limits` → `risk/sizing` → `risk/breaker` → `audit log`.

**Approved trade path:**
- TradeRequest with valid signal → risk checks pass → Kelly sizing → approved → audit log "executed"

**Rejected trade path (limit failure):**
- TradeRequest that exceeds per-market limit → rejected → audit log "rejected" with reason

**Rejected trade path (circuit breaker):**
- TradeRequest when circuit breaker active → rejected → audit log "rejected" with breaker reason

**Rejected trade path (no edge):**
- TradeRequest with edge < 3% → rejected → audit log "rejected" with edge reason

### 3.2 Client → Market Data → Risk Gate Pipeline

Test the complete pipeline:

```
cli.py trade command
  → KalshiClient.get_market() [mocked]
  → analysis/indicators computes signal [mocked data]
  → risk/limits checks pass/fail
  → risk/sizing computes position
  → audit log entry
```

Verify each stage receives correct input from the previous stage.

Verify failure at any stage produces appropriate error and audit entry.

### 3.3 Risk Module Non-Bypassable Tests

**Verify risk module cannot be bypassed:**

- Direct `KalshiClient` trade call without going through `risk/limits`: should fail or be rejected
- Modifying `HARD_LIMITS` at runtime: should be impossible (frozen or read-only)
- Calling `risk/sizing` directly without `risk/limits` check: should fail in tests

### 3.4 Audit Trail Completeness Tests

Verify no decision path exists that does NOT produce an audit entry:

- Approved trade → audit entry
- Rejected trade (any reason) → audit entry
- Circuit breaker trigger → audit entry
- Heartbeat loop review → audit entry (if it results in parameter changes)

---

## PHASE 4: PROPERTY-BASED AND INVARIANT TESTS

### 4.1 Pydantic Model Fuzzing

Use `hypothesis` to fuzz Pydantic models:

```python
@given(st.integers(min_value=0, max_value=10**12))
def test_market_open_interest_fuzz(oi):
    # Market with random open interest should not crash
    market = Market(model={"open_interest": oi})
    assert market.open_interest >= 0
```

For each model, test:
- Boundary values (0, 1, max int, negative where invalid)
- Random valid integers
- Random invalid types (strings, floats where int expected)

Verify no fuzz input causes crash or silent data corruption.

### 4.2 Kelly Criterion Invariants

**Invariants:**
- `f* + q * f* <= 1` (Kelly fraction cannot exceed bankroll)
- Result is in `[0, 1]` (fraction of bankroll)
- Zero edge produces zero or negative result (clamped to 0)

```python
def test_kelly_invariants(b, p):
    f = kelly_fraction(b, p)
    q = 1 - p
    assert f + q * f <= 1.0 + 1e-9  # allow floating point tolerance
    assert 0 <= f <= 1.0
```

### 4.3 Circuit Breaker Invariants

**Invariants:**
- Circuit breaker level never decreases without clearance
- Level 3 (FULL_STOP) requires manual reset, cannot auto-clear
- State file exists and is readable after trigger

### 4.4 Risk Limit Invariants

**Invariants:**
- `HARD_LIMITS` dict keys never change
- `HARD_LIMITS` values are within documented ranges
- No code can read risk limits from config files

### 4.5 Decimal Precision Invariants

- No float arithmetic for money — all cents as int
- `Decimal` used for intermediate calculations if needed
- No `round()` that could lose precision on monetary values

---

## PHASE 5: EXECUTION AND VALIDATION

### 5.1 Full Test Suite

Run the full test suite:

```bash
pytest tests/ -v --tb=short
```

Verify all tests pass.

### 5.2 Linter Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

Verify zero errors.

### 5.3 Type Checker Validation

```bash
mypy src/traderbot/
```

Verify zero type errors.

### 5.4 Coverage Verification

```bash
pytest --cov=traderbot --cov-report=term-missing tests/
```

Review coverage report. Identify any modules with coverage below 80% and add tests.

### 5.5 Fix and Re-run

Fix any failures and re-run from Phase 1.

---

## ITERATIVE FIX AND TEST CYCLE

**Discovery vs. verification:** Each phase has two purposes: (1) verify the SPECIFIC items listed in that phase's checklists pass, and (2) DISCOVER new issues NOT listed in any checklist. The checklists define MINIMUM coverage, not maximum.

**Bug class extraction (MANDATORY for every bug found):** Before fixing any bug, extract its abstract pattern per §0.6. Every fix must be accompanied by a generalized bug class entry.

Process findings in severity order: P0 first, then P1, then P2, then P3.

Within each severity level, fix bugs one at a time, **except when a single root cause affects multiple files** — in that case, fix all affected files in one commit.

For each bug:
1. **Fix Implementation**: Document root cause, implement minimal fix
2. **Full Regression Testing**: After ANY code change, re-run ALL phases from the beginning
3. **Version Control and Documentation**: Commit with descriptive message, tag with next version

### Continue Until
- ALL phases (0-5) pass with zero P0, P1, P2 findings
- `pytest tests/` passes
- `ruff check src/ tests/` reports zero errors
- `mypy src/traderbot/` reports zero errors
- Coverage meets minimum threshold

---

## REPORTING REQUIREMENTS

After each phase, provide:

- **Findings:** Complete list of all issues discovered
- **Severity:** P0/P1/P2/P3 classification for each finding
- **Impact:** What breaks and for whom
- **Evidence:** Logs, output, or reproduction steps
- **Root Cause:** Why this happens
- **Fix Applied:** What was changed and why
- **Verification:** How the fix was validated and which phases were re-run

### Phase Pass Criteria
- **Phase 0 PASS:** Architecture model is complete, no import cycles, no P0 architecture violations
- **Phase 1 PASS:** Zero P0 findings, zero P1 findings, ruff/mypy clean
- **Phase 2 PASS:** All unit tests pass, no P0/P1 findings
- **Phase 3 PASS:** No P0/P1 integration issues, risk module non-bypassable
- **Phase 4 PASS:** All invariants hold, fuzzing finds no crashes
- **Phase 5 PASS:** Full test suite passes, coverage adequate

---

## FINAL CHECKLIST

Before completion, verify:

- [ ] All Python files pass `ruff check` with zero errors
- [ ] All Python files pass `ruff format --check`
- [ ] All modules pass `mypy` type checking with zero errors
- [ ] No `float` used for monetary values (cents should be `int`)
- [ ] No `# type: ignore` comments anywhere
- [ ] No `as any` type bypasses anywhere
- [ ] All Pydantic models have `ConfigDict(strict=True, extra="forbid")`
- [ ] `risk/` module has NO config-reading code
- [ ] `risk/` module does NOT import from `analysis/` or `news/`
- [ ] `risk/` HARD_LIMITS are frozen/hardcoded constants
- [ ] Every trading function has a corresponding audit log call
- [ ] Circuit breaker state persists to disk
- [ ] FULL_STOP requires manual human reset
- [ ] All async functions are properly awaited
- [ ] All external I/O (Kalshi API, WebSocket) is mocked in tests
- [ ] No real API keys or credentials in test code
- [ ] Kelly criterion math is mathematically correct
- [ ] Kelly fraction clamped to [0.1, 0.5] range
- [ ] No strategy logic in toolkit (toolkit computes, agent decides)
- [ ] Import graph is cycle-free
- [ ] All modules have at least 80% test coverage
- [ ] Bug class taxonomy is up to date
- [ ] All commits tagged with version numbers
