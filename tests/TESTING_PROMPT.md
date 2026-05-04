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
- `profiles/` depends on: `kalshi/models` (profile config), `db/` (data isolation paths), `risk/limits` (HARD_LIMITS ceiling checks)
- `cli.py` depends on: `kalshi/`, `analysis/`, `risk/`, `db/`, `profiles/`, `auth.py`, `wal.py`, `heartbeat.py`, `learning.py`, `updater.py`, `update_config.py` (orchestrates all modules)

**Verify additional dependency rules:**
- `profiles/` never imports from `analysis/` or `news/` (profiles configure limits, not strategy)
- `profiles/auth.py` uses `keyring` directly — verify it does NOT import `auth.py` (separate credential namespace)
- `db/vectors.py` depends on: `chromadb` (optional), `kalshi/models` — verify it never imports from `analysis/`, `risk/`, or `news/`
- `analysis/registry.py` depends on: `news/models.py` (MarketCategory enum) — verify this is the ONLY cross-module dependency in `analysis/`
- `updater.py` depends on: `update_config.py`, `httpx` (version check) — verify it never imports from `risk/`, `kalshi/`, or `db/`
- `learning.py` depends on: `db/learnings.py` — verify it does not import from `risk/` or `kalshi/`

**CLI entry point**: `cli.py` → Typer app with 16+ main commands, `auth` sub-app (5 commands), `update` sub-app (3 commands), and `profile` sub-app (12 commands). Each command lazily imports its dependencies. `scan`/`analyze` use `kalshi/` (async calls wrapped in `asyncio.run()`). `trade` uses `risk/` gate. `positions`/`audit` use `db/` layer. `halt` uses `risk/circuit_breaker`. `signals` uses `analysis/signals`. `news`/`sentiment` use `news/`. `backtest`/`paper`/`compare`/`performance` use `simulation/`. `learnings` uses `learning.py`. `profile` commands use `profiles/`. `auth` commands use `auth.py`. `update` commands use `updater.py`.

**Dependency rule**: `analysis/` never imports from `risk/`, `db/`, or `news/`. `db/` never imports from `analysis/` or `risk/`. `cli.py` is the only module that imports across all domain boundaries.

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
| Enum strict deserialization (IntEnum + StrEnum) | JSON stores enum values as raw int/str, but strict Pydantic mode rejects implicit coercion. Both `IntEnum(int_val)` and `StrEnum(str_val)` must be explicitly constructed before `model_validate`. | For every `_parse_*` or `_row_to_model` helper that converts API/DB data to Pydantic models, verify enum fields are wrapped: `OrderSide(raw_str)`, `BreakerLevel(raw_int)`. Grep for `model_validate` call sites and trace enum-typed fields. |
| SecretStr violation — plain str for credentials | A credential field (API key, secret, token) is declared as `str` instead of `SecretStr`, making it exposed via `model_dump()`, `repr()`, and log output. | Grep all Pydantic models for fields containing `key`, `secret`, `token`, or `password` in their names; verify each uses `SecretStr`. Check that `.get_secret_value()` is only called in assignment context, never in logging or printing. |
| Credential bypass — raw env access | Code reads credentials via `os.getenv` or `os.environ.get` instead of the keyring-based `ProfileAuthStore`, bypassing credential isolation and rotation. | Grep for `os.environ.get` and `os.getenv` in all source files; every match referencing a key, secret, token, or credential must go through `ProfileAuthStore` instead. |
| Unsafe model_dump() on SecretStr models | `model_dump()` is called on a Pydantic model containing `SecretStr` fields without `mode="json"`, exposing raw secret values in the returned dict. | Grep for `.model_dump()` calls; trace each call to verify the model has no `SecretStr` fields, or the call uses `mode="json"` with proper serialization. |
| Secret printed to console (P0) | A secret (profile token, API key, session token) is printed to stdout/console via `print()`, `typer.echo()`, or `logger` with the value interpolated. This is a P0 confidentiality violation. | Grep for `print` and `typer.echo` and `logger.*info/debug` in CLI and entrypoint files; verify no line outputs a variable holding a secret value. |
| Insecure file permissions on sensitive data | A file containing credentials, tokens, session state, or audit data is created with default (world-readable) permissions instead of `0o600`/`0o700`. | Grep for `open`, `write_text`, `Path.touch`, and `sqlite3.connect` in `risk/`, `db/`, and `profiles/` modules; verify each sensitive file creation uses restrictive permissions. |
| Demo/production credential cross-contamination | Demo mode uses production credentials, or production endpoint is reachable with demo credentials, allowing real-money trades in a test context. | Verify `DemoAdapter` and `WebSocketConfig.active_url` enforce endpoint isolation: `demo_mode=True` must route only to demo URLs, and production credentials must not leak into demo config objects. |
| Audit trail mutability — WAL opened r+ | Audit trail files are opened in `r+` mode, allowing modification of past entries. No hash chain or HMAC protects entry integrity. | Grep for `open` modes in `risk/audit.py`; verify WAL files use `'a'` (append) mode only. Verify each entry includes a content hash or HMAC of the prior entry. |

**Custom check generation template:**
```
Bug Class: [abstract name — NO line numbers, NO function names, NO file paths]
Abstract Pattern: [general description that could apply to any codebase with this structure]
How to Detect: [concrete methodology to find ALL instances in current codebase]
Phase: [which phase this check belongs in]
Expected Severity: [P0/P1/P2 if found]
```

**Phase 0 Gate Addition:** Before proceeding to Phase 1, ALL bugs found since the last review cycle (both during-review AND manual/outside) must have their bug class extracted, generalized, and custom checks inserted into the appropriate phase sections.

### 0.7 Documentation vs. Code Validation

**Purpose:** Docs are the source of truth (per AGENTS.md: "When in doubt about intended behavior, consult `docs/` first"). If docs say one thing and code does another, either the doc is wrong (needs updating) or the code is wrong (bug). This section ensures docs match reality BEFORE code review begins.

**Critical principle:** The reviewer MUST NOT assume docs are accurate. Every specification in docs must be validated against the actual codebase. Never infer or hallucinate — read the code, compare line-by-line, and flag discrepancies.

**Process:**

1. **Read every doc file** in `docs/` and compare each specification against the corresponding source code
2. **Read `ROADMAP_PROGRESS.md`** and verify every claim against actual test runs and file existence
3. **Flag every discrepancy** with severity classification
4. **For each discrepancy**, determine: is the doc wrong, or is the code wrong?
5. **Never edit `docs/`** without explicit human approval (per AGENTS.md source-of-truth rule)

**Doc files to validate and what to check:**

| Doc File | What to Validate | How to Verify |
|----------|-----------------|---------------|
| `docs/architecture.md` | Module dependency rules | Grep imports in each module; verify no forbidden dependencies (e.g., `risk/` importing from `analysis/`) |
| `docs/architecture.md` | Data flow descriptions | Trace each described flow against actual `cli.py` command implementations |
| `docs/architecture.md` | Component map (module names, file names) | Verify each module and file listed actually exists |
| `docs/architecture.md` | Toolkit vs. Agent boundary table | Verify no toolkit function makes strategy decisions (returns buy/sell/hold) |
| `docs/risk.md` | `HARD_LIMITS` values (5%, 2%, 10%, 1000, 20, 3%) | Read `risk/limits.py` and compare actual values against docs |
| `docs/risk.md` | Circuit breaker thresholds (1% Slow, 2% Halt, 10% FULL_STOP) | Read `risk/circuit_breaker.py` and compare thresholds |
| `docs/risk.md` | Decision model schema (`price: float` or `price: int`) | Read `db/decisions.py` and `kalshi/models.py` — verify monetary fields are `int` cents, NOT `float` |
| `docs/risk.md` | Kelly fraction range [0.1, 0.5] | Read `risk/sizing.py` and verify clamping bounds |
| `docs/risk.md` | Audit trail fields match actual Decision model | Compare doc's Decision fields against `db/decisions.py` model |
| `docs/kalshi.md` | API endpoints and response shapes | Read `kalshi/client.py` and `kalshi/models.py` and verify each documented endpoint |
| `docs/openclaw-integration.md` | SKILL.md command names match `cli.py` commands | Read `skills/traderbot/SKILL.md` and compare command list against `typer` app commands |
| `docs/simulation.md` | Module and function names for Phase 5 (BUILT) | Verify `simulation/` directory exists with engine.py, models.py, adaptation.py, adapter_state.py, paper_trader.py, performance.py, profiles.py, data_loader.py |
| `docs/news-sentiment.md` | Module and function names for Phase 7 (BUILT) | Verify `news/` directory exists with sources.py, classifier.py, sentiment_scorer.py, impact_assessor.py, embeddings.py, models.py, cache_paths.py |
| `docs/self-learning.md` | Module and function names for Phase 6 (BUILT) | Verify `db/learnings.py` exists with LearningsDB, and `learning.py` exists with pattern promotion |
| `docs/decisions/` | ADR records match current architecture | Verify each ADR's decision is still reflected in current code |

**ROADMAP_PROGRESS.md validation checklist:**

| Claim in ROADMAP | How to Verify |
|-----------------|---------------|
| Phase status (✅ COMPLETE, 🔲 NOT STARTED) | Verify each component file exists and has real implementation (not just stubs) |
| Test count ("X tests passing") | Run `pytest tests/ --co -q` and compare actual count |
| Coverage percentage | Run `pytest --cov=traderbot --cov-report=term-missing tests/` and compare |
| "strict=True, extra=forbid" on all models | Grep for `ConfigDict` in all model files; verify each has `strict=True, extra="forbid"` |
| Version number in header matches `VERSION` file | Read `VERSION` file and compare |
| Success criteria checkboxes | For each checked item, verify the feature actually works (run relevant tests) |
| Bug class taxonomy entries | Spot-check 2-3 entries against actual code (e.g., verify HARD_LIMITS is still frozen) |
| Class/function names in Notes column | Parse actual source with `ast` to get real class/function names; compare against roadmap notes |
| CLI command count | Parse `cli.py` for `@app.command()` decorated functions; verify count matches roadmap claim |

**Naming consistency check (NEW):**

Docs and ROADMAP_PROGRESS.md may reference class/function names that differ from actual code. Divergence happens silently as code evolves. For each component in the roadmap, verify the names listed in the "Notes" column match the actual source:

```bash
# Example: verify class names in a module
python3 -c "
import ast
with open('src/traderbot/kalshi/demo.py') as f:
    tree = ast.parse(f.read())
names = sorted({n.name for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and not n.name.startswith('_')})
print(names)
"
```

Flag any name in ROADMAP that doesn't match source as P3 (stale docs).

**Known discrepancies (re-verify each cycle):**

| Discrepancy | Doc Says | Code Reality | Severity | Action |
|-------------|---------|-------------|----------|--------|
| `docs/risk.md` Decision model | ~~`price: float`~~ → fixed to `price: int` | `price: int` (cents) | ~~P1~~ ✅ Fixed | Updated in v0.04.06 |
| `docs/risk.md` project name | ~~"BetBot"~~ → fixed to "TraderBot" | "TraderBot" | ~~P3~~ ✅ Fixed | Updated in v0.04.06 |
| `docs/risk.md` Human Override | ~~Duplicate section~~ → removed | Single section | ~~P3~~ ✅ Fixed | Updated in v0.04.06 |
| `docs/architecture.md` `kalshi/trading` | Listed in component map | `kalshi/trading.py` now implemented | ~~P2~~ ✅ Fixed | Implemented in v0.04.06 |
| `docs/architecture.md` sentiment placement | ~~`sentim.` in analysis column~~ → moved to news | `news/sentiment_scorer.py` (Phase 7) | ~~P2~~ ✅ Fixed | Updated in v0.04.06 |
| `docs/kalshi.md` import example | ~~`from betbot.kalshi`~~ → fixed to `from traderbot.kalshi` | `from traderbot.kalshi` | ~~P3~~ ✅ Fixed | Updated in v0.04.06 |
| `VERSION` file staleness | May lag behind git tags | Actual version is in git tags | P2 | Verify `VERSION` matches latest tag |

**Phase 0 Gate Addition:** Before proceeding to Phase 1, ALL documentation discrepancies must be documented and classified. P0/P1 discrepancies (wrong financial types, missing modules, incorrect thresholds) must be flagged for human review. P2/P3 discrepancies (stale names, duplicate sections) should be noted but don't block review.

---

## PHASE 0.9: KALSHI API SPEC COMPLIANCE

Verify that every interaction with the Kalshi API conforms to the documented spec in `docs/kalshi.md` and the live API behavior. Each check must reference the source file, line number, and the doc section that defines expected behavior.

### 0.9.1 Authentication Compliance

- Verify `KalshiClient.login()` (`src/traderbot/kalshi/client.py` L132–155) sends `POST /login` with `api_key` and `api_secret` in the JSON body — matches `docs/kalshi.md` §Authentication
- Verify login response parsing extracts the `token` field correctly (L153) and stores it as `_session_token`
- Verify subsequent requests include `Authorization: Bearer <token>` header (L172) — matches `docs/kalshi.md` §Authentication ("RSA-PSS signed JWT headers" documented; current implementation uses session-token Bearer auth)
- Verify `AuthenticationError` is raised on 401/403 responses (L149–150, L188–191)
- Verify `WebSocketConfig` (`src/traderbot/kalshi/websocket.py` L20–37) sends auth message with `type: "auth"`, `api_key`, and `api_secret` (L65–69) on connect — matches `docs/kalshi.md` §WebSocket Streams
- Verify `MarketStream._authenticate()` (`src/traderbot/kalshi/websocket.py` L59–75) validates `type: "auth_approved"` response (L73) and rejects non-approved responses
- Verify `AuthManager` (`src/traderbot/auth.py` L52–214) resolves Kalshi credentials from keyring first, then `.env` fallback (L100–133)
- Verify `KeyringKalshiConfig` (`src/traderbot/kalshi/config.py` L31–68) resolves `api_key` and `api_secret` via keyring-priority lookup before env vars

### 0.9.2 REST Endpoint Compliance

- Verify `MarketService.list_markets()` (`src/traderbot/kalshi/markets.py` L29–48) sends `GET /markets` with `limit`, `cursor`, `category`, `state` params — matches `docs/kalshi.md` §Market Data table
- Verify `MarketService.get_market()` (`src/traderbot/kalshi/markets.py` L50–55) sends `GET /markets/{ticker}` — matches `docs/kalshi.md` §Market Data table
- Verify `MarketService.get_orderbook()` (`src/traderbot/kalshi/markets.py` L57–69) sends `GET /markets/{ticker}/orderbook` with `depth` param — matches `docs/kalshi.md` §Market Data table
- Verify `MarketService.get_recent_trades()` (`src/traderbot/kalshi/markets.py` L71–85) sends `GET /markets/{ticker}/trades` with `limit` and `cursor` params — matches `docs/kalshi.md` §Market Data table
- Verify `TradingService.place_order()` (`src/traderbot/kalshi/trading.py` L26–39) sends `POST /portfolio/orders` with `ticker`, `side`, `order_type`, `quantity`, `price` — matches `docs/kalshi.md` §Trading table
- Verify `TradingService.cancel_order()` (`src/traderbot/kalshi/trading.py` L41–49) sends `DELETE /portfolio/orders/{order_id}` — matches `docs/kalshi.md` §Trading table
- Verify `TradingService.get_order()` (`src/traderbot/kalshi/trading.py` L51–57) sends `GET /portfolio/orders/{order_id}` — matches `docs/kalshi.md` §Trading table
- Verify `TradingService.list_orders()` (`src/traderbot/kalshi/trading.py` L59–69) sends `GET /portfolio/orders` with optional `ticker` filter — matches `docs/kalshi.md` §Trading table
- Verify `HistoryService.get_cutoffs()` (`src/traderbot/kalshi/history.py` L27–43) fetches market data and extracts `market_settled_ts`, `trade_cutoff_ts`, `order_cutoff_ts` — matches `docs/kalshi.md` §Historical Data ("cutoff endpoint")
- Verify `HistoryService.get_historical_trades()` (`src/traderbot/kalshi/history.py` L45–65) sends `GET /markets/{ticker}/trades` with `min_ts`, `max_ts`, `limit`, `cursor` — matches `docs/kalshi.md` §Historical Endpoints table
- Verify `HistoryService.get_settled_markets()` (`src/traderbot/kalshi/history.py` L67–80) sends `GET /markets` with `state=settled` and `cursor` — matches `docs/kalshi.md` §Historical Endpoints table

### 0.9.3 WebSocket Protocol Compliance

- Verify `MarketStream` (`src/traderbot/kalshi/websocket.py` L39–172) connects to `wss://` URL (L52) — matches `docs/kalshi.md` §WebSocket Streams
- Verify `WebSocketConfig.base_url` default is `wss://api.kalshi.co/trade-api/ws/v2` (L27) — matches `docs/kalshi.md` §WebSocket Streams URL
- Verify `WebSocketConfig.demo_url` default is `wss://demo-api.kalshi.co/trade-api/ws/v2` (L28)
- Verify `WebSocketConfig.active_url` property (L33–36) returns `demo_url` when `demo_mode=True` and `base_url` otherwise
- Verify `MarketStream.connect()` (L50–57) establishes connection then calls `_authenticate()` before any subscriptions
- Verify `MarketStream.subscribe()` (L77–89) sends `type: "subscribe"` message with `channels` list containing `ticker` and `side: "all"` (L83–86)
- Verify `MarketStream.unsubscribe()` (L91–103) sends `type: "unsubscribe"` message with matching channel format
- Verify `MarketStream.listen()` (L105–120) yields parsed JSON messages and auto-reconnects on `ConnectionClosed` with exponential backoff (L127–149)
- Verify `_try_reconnect()` (L127–149) uses exponential backoff starting at `reconnect_delay` and caps at `max_reconnect_attempts`
- Verify `_resubscribe()` (L122–125) re-issues subscriptions for all tracked tickers after reconnection

### 0.9.4 Rate Limit Compliance

- Verify `KalshiClient._request()` (`src/traderbot/kalshi/client.py` L157–215) raises `RateLimitError` on HTTP 429 (L185–186) — matches `docs/kalshi.md` §Rate limit ("~10 requests/second")
- Verify rate-limiting semaphore (`src/traderbot/kalshi/client.py` L129) uses `rate_limit_rps` config value (default 5.0 rps)
- Verify exponential backoff with jitter on retry: `retry_base_delay * (2^attempt) + random(0, 0.5)` (L208–209)
- Verify `max_retries` config defaults to 3 (L45) and is respected in retry loop (L175)
- Verify `RateLimitError` and `AuthenticationError` are NOT retried — raised immediately (L202–203)
- Verify server errors (5xx) trigger retry within the backoff loop (L193–198)

### 0.9.5 Error Handling Compliance

- Verify `KalshiClient.login()` raises `AuthenticationError` on 401/403 (`src/traderbot/kalshi/client.py` L149–150)
- Verify `KalshiClient._request()` raises `AuthenticationError` on 401/403 during subsequent requests (L188–191)
- Verify `KalshiClient._request()` raises `RateLimitError` on 429 (L185–186)
- Verify `KalshiClient._request()` raises `httpx.HTTPStatusError` on server errors (5xx) after exhausting retries (L193–198)
- Verify `KalshiClient._request()` raises `httpx.HTTPError` on network-level failures (L204–205)
- Verify all service methods (`MarketService`, `TradingService`, `HistoryService`) call `response.raise_for_status()` after API calls
- Verify `MarketStream._authenticate()` raises `RuntimeError` on auth failure (`src/traderbot/kalshi/websocket.py` L73–75)
- Verify `MarketStream.listen()` catches `ConnectionClosed` and attempts reconnection (L116–120)
- Verify `_normalize_market()` handles missing optional fields gracefully (`src/traderbot/kalshi/_normalize.py` L19–35: `raw.get()` for optional fields)

### 0.9.6 Demo vs. Production Isolation

- Verify `KalshiConfig` (`src/traderbot/kalshi/client.py` L28–50) has separate `base_url` (production: `https://api.kalshi.co/trade-api/v2`, L41) and `demo_url` (demo: `https://demo-api.kalshi.co/trade-api/v2`, L42)
- Verify `KalshiConfig.active_url` property (L49–50) returns `demo_url` when `demo_mode=True` and `base_url` otherwise — matches `docs/kalshi.md` §API Overview table
- Verify `KALSHI_DEMO_MODE` env var controls demo mode toggle (L43: `demo_mode: bool = False`)
- Verify `WebSocketConfig` (`src/traderbot/kalshi/websocket.py` L20–37) has separate `base_url` and `demo_url` with `active_url` property (L33–36)
- Verify `KeyringKalshiConfig` (`src/traderbot/kalshi/config.py` L31–68) has same `base_url`/`demo_url` separation (L44–45) and `active_url` property (L51–53)
- Verify `KalshiClient.__init__()` (`src/traderbot/kalshi/client.py` L95–130) uses `config.active_url` for the HTTP client base (L130) — no hardcoded URLs bypass demo mode
- Verify profile-aware config (`src/traderbot/kalshi/client.py` L112–121) propagates `profile.demo_mode` to `KalshiConfig` and does not mix credentials between profiles
- Verify no credential cross-contamination: `AuthManager` (`src/traderbot/auth.py`) uses namespace-prefixed service names `traderbot.<service>` (L82–85) and profile namespaces `traderbot.profiles.<profile_name>.<service>` per `AGENTS.md` §Credential Isolation

### 0.9.7 Historical Data Compliance

- Verify `HistoryService.get_cutoffs()` (`src/traderbot/kalshi/history.py` L27–43) fetches cutoff timestamps before historical queries — matches `docs/kalshi.md` §Historical Data ("Before querying historical data, call the cutoff endpoint")
- Verify cutoff timestamp parsing handles `None` values (L34–37)
- Verify `HistoryService.get_historical_trades()` (`src/traderbot/kalshi/history.py` L45–65) sends `min_ts`/`max_ts` as Unix timestamps (integer seconds, L55–56) — matches `docs/kalshi.md` §Historical Endpoints
- Verify `HistoryService.get_historical_trades()` respects `limit` parameter (default 100, L50) — `docs/kalshi.md` states max 1000 per page
- Verify `HistoryService.get_settled_markets()` (`src/traderbot/kalshi/history.py` L67–80) filters by `state=settled` (L72)
- Verify `CutoffTimestamps` model (`src/traderbot/kalshi/models.py` L101–106) uses `ConfigDict(strict=True, extra="forbid")` and all three timestamp fields are `datetime | None`

### 0.9.8 Pagination Compliance

- Verify `MarketListResponse` model (`src/traderbot/kalshi/models.py` L109–113) includes `cursor: str | None` field for cursor-based pagination
- Verify `TradeListResponse` model (`src/traderbot/kalshi/models.py` L116–120) includes `cursor: str | None` field for cursor-based pagination
- Verify `MarketService.list_markets()` (`src/traderbot/kalshi/markets.py` L29–48) accepts `cursor` param and passes it to `GET /markets`
- Verify `MarketService.get_recent_trades()` (`src/traderbot/kalshi/markets.py` L71–85) accepts `cursor` param and passes it to `GET /markets/{ticker}/trades`
- Verify `HistoryService.get_historical_trades()` (`src/traderbot/kalshi/history.py` L45–65) accepts `cursor` param and passes it to the API
- Verify `HistoryService.get_settled_markets()` (`src/traderbot/kalshi/history.py` L67–80) accepts `cursor` param and passes it to `GET /markets`
- Verify all paginated endpoints return the cursor from the API response in their response models (`cursor=data.get("cursor")` in L48, L84, L65, L80)
- Verify callers can iterate through all pages by passing the returned cursor to subsequent requests until `cursor is None`

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
src/traderbot/risk/circuit_breaker.py
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

Verify `risk/circuit_breaker.py` logs when circuit breaker activates.

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

Test `risk/circuit_breaker.py`:

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

### 2.8 CLI Command Tests

Test all CLI commands via `typer.testing.CliRunner`:

**scan command:**
- `traderbot scan` returns list of open markets (mock MarketService)
- `traderbot scan --json` returns JSON array of markets
- `traderbot scan --category FED` filters by category
- `traderbot scan --limit 5` limits results
- API failure: graceful error message, no crash

**analyze command:**
- `traderbot analyze KXBTCD-26MAR31-T55000` returns market details + indicators
- `traderbot analyze TICKER --json` returns JSON with market + orderbook + implied_prob
- API failure: graceful error message
- Implied probability displayed even when API succeeds (computed from orderbook)

**trade command:**
- `traderbot trade TICKER --direction yes --quantity 1 --price 50` through risk gate
- Rejected trade: reason displayed (risk check failed)
- Executed trade: sized amount shown
- `--json` output includes outcome and reason

**positions command:**
- `traderbot positions --db path` lists positions from SQLite
- `traderbot positions --json` outputs JSON array
- No positions: "No open positions" message
- DB failure: graceful error

**audit command:**
- `traderbot audit --ticker TICKER` filters by ticker
- `traderbot audit --start 2026-01-01 --end 2026-04-01` filters by date
- `traderbot audit --outcome executed` filters by outcome
- `traderbot audit --json` outputs JSON array
- No decisions: "No decisions found" message

**halt command:**
- `traderbot halt` shows current circuit breaker state
- `traderbot halt --force` sets FULL_STOP level
- `traderbot halt --force --json` outputs JSON with level/multiplier/reason
- `traderbot halt --json` shows state as JSON

**heartbeat command:**
- `traderbot heartbeat` prints status message

**signals command:**
- `traderbot signals` displays signal generation placeholder
- `traderbot signals --json` outputs JSON placeholder

### 2.9 DB Layer Tests

Test `db/__init__.py`, `db/positions.py`, `db/decisions.py`:

**Connection management:**
- `get_connection()` creates SQLite in-memory or file DB
- Schema initialization creates tables on first connection
- Context manager ensures connection is closed after use
- Concurrent access: `OperationalError` on write conflicts handled gracefully

**Positions (CRUD):**
- `upsert()` creates new position
- `upsert()` updates existing position (quantity, avg_price change)
- `list_all()` returns all positions
- `get_by_ticker()` returns specific position or None
- `delete()` removes a position
- All monetary values stored/retrieved as int cents
- Invalid ticker raises appropriate error

**Decisions (CRUD):**
- `insert()` creates new decision entry
- `list_by_ticker()` returns decisions filtered by ticker
- `list_by_date_range()` returns decisions in date window
- `list_by_outcome()` returns decisions filtered by outcome ("executed"|"rejected"|"held")
- All fields present in retrieved records
- Timestamps stored in ISO format, parsed correctly on retrieval

### 2.10 Analysis Engine Tests

Test all `analysis/` modules:

**indicators.py:**
- `sma(data, window)` returns correct simple moving average
- `ema(data, span)` returns correct exponential moving average
- `rsi(data, periods)` returns correct relative strength index
- `bollinger_bands(data, window, num_std)` returns upper, middle, lower bands
- `volume_weighted_price(prices, volumes)` returns VWAP
- Edge cases: empty data, data shorter than window, single-element data
- All functions are sync (no async)

**odds.py:**
- `implied_probability(orderbook)` computes yes/no probabilities from bids
- `detect_edge(estimated_prob, orderbook)` identifies edge direction and size
- `compute_kelly_inputs(estimated_prob, orderbook)` returns Kelly-relevant metrics
- `expected_value(prob, price_cents)` computes EV correctly
- Edge cases: empty orderbook, zero spread, equal yes/no bids
- All monetary values as int cents

**portfolio.py:**
- `win_rate(predictions, outcomes)` computes correct win rate
- `brier_score(predictions, outcomes)` computes correct Brier score
- `sharpe_ratio(returns, risk_free_rate)` computes correct Sharpe
- `max_drawdown(values)` computes correct max drawdown
- `calmar_ratio(returns, max_dd)` computes correct Calmar
- `calibration_curve(predictions, outcomes, n_bins)` bins predictions
- `edge_realization(edges, outcomes)` computes realized edge
- Edge cases: empty inputs, single prediction, constant predictions

**signals.py:**
- `combine_signals(sources)` computes weighted direction + confidence
- `combine_signals([])` returns ("neutral", 0.0)
- `default_weights()` returns expected weight dict
- `generate_signal(ticker, prices, trades, orderbook, estimated_prob)` builds CombinedSignal
- CombinedSignal model validates: confidence in [0,1], edge_cents as int
- Toolkit computes direction+confidence, NEVER returns "buy"|"sell"|"hold"

**Analysis dependency rule:**
- Verify `analysis/` never imports from `risk/`, `db/`, or `news/`
- All functions in `analysis/` are sync (no async)
- All monetary values use int cents

**registry.py:**
- `AnalysisRegistry.register(category, analyzer)` adds per-category analyzer
- `AnalysisRegistry.get(category)` returns `None` for unregistered categories
- `AnalysisRegistry.analyze(category, data)` dispatches to appropriate `CategoryAnalyzer`
- `GenericAnalyzer` provides keyword-based fallback for unregistered categories
- `CategorySignals` model validates: `category: MarketCategory`, `signals: list[SignalSource]`, `confidence: float` (0–1)
- Verify `MarketCategory` enum values match `news/models.py` `NewsCategory` alias values

### 2.11 AuthManager Tests

Test `auth.py` (`AuthManager`):

**Keyring operations:**
- `AuthManager.set_credential(service, key, value)` stores credential via keyring with `traderbot.` prefix
- `AuthManager.get_credential(service, key)` retrieves credential from keyring
- `AuthManager.delete_credential(service, key)` removes credential from keyring
- `AuthManager.list_services()` returns service names (never credential values)
- `keyring_available` returns `False` when backend name contains "Fail" or "Null"

**Credential check:**
- `check_credentials()` returns `{service: {key: bool}}` for all services in `_ALL_SERVICES`
- `_REQUIRED_SERVICES = {"kalshi": ["api_key", "api_secret"]}`
- `_OPTIONAL_SERVICES` contains `voyage`, `newsapi`, `twitter`, `reddit`

**Env fallback:**
- `get_credential()` returns `CredentialResult(source="env")` when keyring is unavailable and env var is set
- `_service_key_to_env("kalshi", "api_key")` returns `"KALSHI_API_KEY"`
- `_service_key_to_env("kalshi", "api_secret")` returns `"KALSHI_API_SECRET"`
- `_service_key_to_env("kalshi", "demo_mode")` returns `"KALSHI_DEMO_MODE"`

**Keyring namespace isolation:**
- `_full_service("kalshi")` returns `"traderbot.kalshi"`
- Profile-aware: inside a profile, resolves to `"traderbot.profiles.<name>.<service>"`

**CLI commands:**
- `traderbot auth check` displays credential status for all 5 services
- `traderbot auth login` prompts for credentials interactively when keyring available
- `traderbot auth set-key <service> <key>` stores credential via keyring
- `traderbot auth list-keys` shows service names only (never values)
- `traderbot auth rotate <service>` deletes old keys and prompts for new ones

### 2.12 WAL Protocol Tests

Test `wal.py` (Write-Ahead Log):

**WalEntry model:**
- `WalEntry` validates required fields: `intent_id`, `timestamp`, `action` (BUY/SELL), `ticker`, `direction` (yes/no), `quantity` (int ≥ 1), `price_cents` (int ≥ 1), `reason`, `signal`, `risk_checks`, `confidence` (float 0.0–1.0), `status` (PENDING/COMPLETED/CANCELLED/EXPIRED)
- Uses `ConfigDict(strict=True, extra="forbid")`
- Rejects extra fields, rejects wrong types

**Write intent:**
- `write_intent()` creates WAL entry with status `PENDING`
- Writes to `SESSION-STATE.md` (default path)
- Creates parent directories if they don't exist

**Update status:**
- `update_status()` transitions status: PENDING → COMPLETED, PENDING → CANCELLED, PENDING → EXPIRED
- Status is persisted to file immediately

**Concurrent write protection:**
- `write_intent()` uses file lock (`fcntl.LOCK_EX | fcntl.LOCK_NB`)
- Concurrent write attempt raises `ConcurrentWriteError`
- `update_status()` also uses exclusive file lock

**Crash recovery:**
- `scan_pending()` returns only PENDING entries
- `reconcile()` compares pending intents against actual positions and updates status

**Markdown format:**
- Each WAL entry renders as `### WAL-XXXXX` heading
- Entries include: Action, Reason, Signal, Risk, Confidence, Status

### 2.13 Heartbeat Step Unit Tests

Test `heartbeat.py` individual steps:

**step_performance_review:**
- Aggregates trade outcomes from decisions DB
- Computes: `trade_count`, `win_rate`, `total_pnl_cents`, `avg_confidence`, `sharpe_ratio` (or None if <2 trades), `max_drawdown_pct`, `open_positions`
- `deviation_flag` set to `True` when actual win rate deviates >15% from average confidence

**step_decision_review:**
- Reviews prediction accuracy for closed markets
- Computes: `closed_count`, `correct_predictions`, `prediction_accuracy`, `open_count`, `pending_review` count

**step_bayesian_adaptation:**
- Applies Beta-Binomial update on win/loss observations
- Cooldown: max 4 updates per 24 hours
- Guardrail: no update with fewer than 10 observations
- Guardrail: parameter change ≤ 20% in single update
- Variance reset: if posterior variance < 0.01, reset to weak prior
- Human review flag: if any parameter moves >10% for 3 consecutive updates, flag for review

**step_learning_promotion:**
- Scans for patterns with `Recurrence-Count >= 3` across 2+ tasks within 30-day window
- Promotes to `PENDING_REVIEW` status (NEVER auto-commits to AGENTS.md)
- Returns `candidates_found` and `promoted` counts

**step_circuit_breaker_check:**
- Reads `CircuitBreaker` state: NORMAL/SLOW/HALT/FULL_STOP
- Returns `level`, `can_trade` (bool), `daily_loss_pct`, `drawdown_pct`, `position_size_multiplier`, `reason`

**step_system_health:**
- DB integrity check (SQLite connection)
- API connectivity test (Kalshi API ping or mock)
- Data freshness check (last trade timestamp within threshold)
- Returns `api_connectivity`, `db_integrity`, `data_freshness`, `alerts`

**_write_heartbeat_md:**
- Writes to `.openclaw/workspace/HEARTBEAT_DATA.md`
- Creates parent directories if they don't exist
- Header: `# TraderBot Heartbeat Data`
- All monetary values in cents (int), displayed as USD in markdown

**HeartbeatResult model:**
- Uses `ConfigDict(strict=True, extra="forbid")`
- All sub-models also use `ConfigDict(strict=True, extra="forbid")`
- `--dry-run` flag produces same output structure but skips state mutations

### 2.14 Profiles Module Tests

Test `profiles/` module internals:

**models.py (TradingProfile):**
- `TradingProfile` validates: `name` (str), `mode` (paper/live), `risk_multiplier` (float 0.01–1.0), `max_position_per_market_pct` (float), `min_edge_pct` (float), `min_liquidity_threshold` (int), `enabled_categories` (list[str])
- `risk_multiplier * HARD_LIMITS[key]` never exceeds `HARD_LIMITS[key]` for any key
- `enabled_categories` validates against known `MarketCategory` values

**tokens.py:**
- `generate_token()` produces cryptographically random token
- `assign_token(token, profile_name)` stores token-to-profile mapping
- `resolve_token(token)` returns profile name or `None`
- `revoke_token(token)` removes mapping
- `list_assignments()` returns all token→profile mappings
- `get_profile_token(profile_name)` returns assigned token or `None`

**registry.py (ProfileRegistry):**
- CRUD operations: create, retrieve, list, update, delete profiles
- Duplicate profile name raises error
- Non-existent profile returns `None` or raises appropriate error
- Update preserves unmodified fields

**runtime.py:**
- `get_current_profile()` with valid `TRADERBOT_PROFILE_TOKEN` env var resolves to profile
- `get_current_profile()` with invalid token returns `None` (falls back to global)
- `get_current_profile()` with no token returns `None` (uses global config)
- `load_profile_config()` loads config with profile-specific overrides
- `load_profile_config()` without profile loads global config

**auth.py (ProfileAuthStore):**
- `set_credential(profile_name, service, key, value)` stores under `traderbot.profiles.<name>.<service>` namespace
- `get_credential(profile_name, service, key)` retrieves from profile-specific namespace
- `delete_credential(profile_name, service, key)` removes from profile namespace
- `has_service(profile_name, service)` checks if profile has any credentials for service
- `list_services(profile_name)` returns service names (never values)
- Credentials isolated per profile: Profile A cannot read Profile B's credentials
- `created_at` timestamp recorded for each credential

**injection.py:**
- `inject_token(tools_path, token)` inserts `TRADERBOT_PROFILE_TOKEN` into TOOLS.md
- `remove_token_from_tools(tools_path)` removes injected token
- `get_token_from_tools(tools_path)` extracts token value or returns `None`

**isolation.py:**
- `resolve_state_path(profile)` returns profile-specific paths for DB, ChromaDB, audit
- `ensure_profile_dirs(profile)` creates directory structure for profile data
- Profile data paths use `profile.base_dir`, never global `~/.traderbot/`

**config.py:**
- `resolve_kalshi_credentials(profile)` returns profile-specific credentials if profile active, else global
- `resolve_newsapi_key(profile)` same pattern for NewsAPI

**discovery.py:**
- `discover_agents()` scans OpenClaw workspaces for agent directories
- `get_agent_identity(workspace_dir)` returns agent name and type

**CLI commands:**
- `traderbot profile create/list/show/delete/update` — CRUD operations
- `traderbot profile assign/revoke` — token management
- `traderbot profile discover-agents` — scan for agents
- `traderbot profile set-auth/auth` — credential management

### 2.15 Self-Update Tests

Test `updater.py` and `update_config.py`:

**updater.py:**
- `get_current_version()` reads from `VERSION` file
- `fetch_latest_version()` queries remote for latest version string
- `compare_versions(current, latest)` returns whether update is available
- `cache_read() / cache_write()` manage version cache file
- `check_for_updates()` combines fetch + compare
- `apply_update()` downloads and installs update
- All operations handle network failures gracefully

**update_config.py (UpdateConfig):**
- `UpdateConfig` validates: `check_interval_hours` (int > 0), `cache_path` (str), `repo_url` (str)
- Default values are sensible
- Config load/save roundtrips correctly
- Invalid config values raise validation errors

### 2.16 Vector Store Tests

Test `db/vectors.py` (ChromaDB):

**Initialization:**
- `VectorStore` initializes with persistent ChromaDB client when `chromadb` available
- Falls back to in-memory or raises graceful error when `chromadb` unavailable
- Default collections: `news_embeddings`, `market_embeddings`

**CRUD operations:**
- `add_document(collection, doc_id, embedding, metadata)` inserts document
- `search(collection, query_embedding, top_k)` returns nearest neighbors
- `delete_document(collection, doc_id)` removes document
- Search on empty collection returns empty results

**Embedding dimension:**
- All collections enforce consistent embedding dimension
- Mismatched dimensions raise appropriate error

**ChromaDB optional:**
- When `chromadb` is not installed, vector operations degrade gracefully
- Warning logged when ChromaDB unavailable
- Non-vector features still work without ChromaDB

### 2.17 Install Template Tests

Test installer template files:

**Systemd template (`install/services/traderbot-agent@.service.template`):**
- Template file exists and is readable
- Contains `[Unit]`, `[Service]`, `[Install]` sections
- Uses `-%i` instance variable for multi-agent deployment
- Contains `TRADERBOT_PROFILE_TOKEN` environment variable placeholder
- Has proper `Restart=on-failure` policy
- Contains documentation comments
- Filename follows `traderbot-agent@.service` convention
- Has `SyslogIdentifier` for logging

**Launchd template (`install/services/com.traderbot.agent.plist.template`):**
- Template file exists and is readable
- Valid XML with `<plist>` root and `<dict>` body
- Contains `Label` key with `AGENT_ID` placeholder
- Contains `ProgramArguments` array pointing to TraderBot venv
- Contains `EnvironmentVariables` dict with `TRADERBOT_PROFILE_TOKEN` placeholder
- `WorkingDirectory` set to install directory
- `UserName` key for service user
- `RunAtLoad` and `KeepAlive` configured
- `StandardOutPath` and `StandardErrorPath` for logging
- All placeholders documented in comments

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

## PHASE 3.5: OPENCLAW GATEWAY INTEGRATION

### 3.5.1 Workspace File Validation

Verify that every workspace file required by the OpenClaw Gateway exists and contains the expected structure.

**AGENTS.md** (`.openclaw/workspace/AGENTS.md`):
- Contains `## Session Startup` section referencing runtime-provided context files (`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, `USER.md`, `HEARTBEAT.md`, `SESSION-STATE.md`, `HEARTBEAT_DATA.md`)
- Contains `## Trading Rules` → `### Hard Limits` with exact values: 10% max per market, circuit breaker 1%/2%/10%
- Contains `## Self-Learning Protocol` with recurrence threshold (`Recurrence-Count >= 3`) and promotion flow
- Contains `## Heartbeats` section stating `traderbot heartbeat --json` writes to `HEARTBEAT_DATA.md`

**SOUL.md** (`.openclaw/workspace/SOUL.md`):
- Contains `## Core Identity` naming the agent as **TraderBot**
- Contains `## Principles` with: "Data-driven only", "Risk discipline is non-negotiable", "Earn trust through transparency"
- Contains `## Boundaries` with immutable constraints (no risk modification, no trading outside guard rails, no audit skip)

**IDENTITY.md** (`.openclaw/workspace/IDENTITY.md`):
- Contains fields: `Name` = TraderBot, `Role` = Autonomous Kalshi prediction market agent, `Emoji` = 📊
- Contains `Vibe` field matching SOUL.md persona

**HEARTBEAT.md** (`.openclaw/workspace/HEARTBEAT.md`):
- Contains YAML-style `tasks:` list with at minimum: `circuit-breaker-check`, `performance-review`, `learning-promotion`
- Each task has `name`, `interval`, and `prompt` fields
- `performance-review` prompt references `traderbot heartbeat --json`
- Contains `## General Instructions` with circuit breaker halt rule
- Contains `## Data Output` section clarifying that HEARTBEAT_DATA.md is written by `traderbot heartbeat`, NOT this file

**HEARTBEAT_DATA.md** (`.openclaw/workspace/HEARTBEAT_DATA.md`):
- Header line: `# TraderBot Heartbeat Data`
- Blockquote distinguishing it from HEARTBEAT.md: "This is NOT HEARTBEAT.md"
- Contains `## Last Heartbeat:` timestamp section
- Contains sections: `### Performance`, `### Adaptation`, `### Learnings`, `### Circuit Breaker`, `### System Health`, `### Alerts`
- Written by `traderbot heartbeat` CLI command (`src/traderbot/heartbeat.py` → `_write_heartbeat_md()`), NOT by the agent manually

**SESSION-STATE.md** (`.openclaw/workspace/SESSION-STATE.md`):
- Contains `## Active Context` section with `Last Updated`, `Decision Loop`, `Circuit Breaker` fields
- Contains `## Tracked Markets`, `## Open Positions`, `## Pending Actions` tables
- Contains `## WAL Entries` section with column headers: Timestamp, Ticker, Direction, Quantity, Price, Reason
- Default `DEFAULT_SESSION_STATE_PATH` in `src/traderbot/wal.py` points to `.openclaw/workspace/SESSION-STATE.md`

**.learnings/** (`.openclaw/workspace/.learnings/`):
- Directory must exist and contain at minimum: `LEARNINGS.md`, `ERRORS.md`, `FEATURE_REQUESTS.md`
- Referenced by AGENTS.md `## Memory` section and HEARTBEAT.md `learning-promotion` task

**TOOLS.md** (`.openclaw/workspace/TOOLS.md`):
- Contains `## TraderBot CLI` table with commands: `scan`, `analyze`, `trade`, `positions`, `heartbeat`, `halt`, `news`, `sentiment`
- Contains `## Environment` with `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`, `KALSHI_DEMO`
- Contains `## Gotchas` noting price is in cents and `--json` flag requirement

**USER.md** (`.openclaw/workspace/USER.md`):
- Contains `## Trading Preferences` with risk tolerance and signal weighting entries
- Contains `## Context` section (filled by user over time)

### 3.5.2 SKILL.md Format Validation

Verify that `skills/traderbot/SKILL.md` conforms to the OpenClaw skill definition format and matches the actual CLI.

**YAML frontmatter** (`skills/traderbot/SKILL.md` lines 1–10):
- `name` field = `traderbot`
- `description` field contains "Autonomous prediction market investment toolkit for Kalshi"
- `metadata.openclaw.requires.env` lists `["KALSHI_API_KEY", "KALSHI_PRIVATE_KEY"]`
- `metadata.openclaw.requires.bins` lists `["python3"]`
- `metadata.openclaw.primaryEnv` = `KALSHI_API_KEY`

**Command table** (`skills/traderbot/SKILL.md` lines 16–42):
- Every command in the table must match a `@app.command()` function in `src/traderbot/cli.py`
- Required commands to verify: `scan`, `analyze`, `trade`, `positions`, `audit`, `signals`, `heartbeat`, `halt`, `news`, `sentiment`, `backtest`, `paper`, `compare`, `performance`, `learnings`, `profile create/list/show/delete/assign/revoke/assignments/discover-agents/set-auth/auth`
- Each command must document its `--json` flag where applicable
- `trade` command must document `--direction yes/no --quantity N --price CENTS` args

**Trigger phrases** (`skills/traderbot/SKILL.md` lines 46–59):
- Mapping from natural language to CLI command must cover all primary workflows
- "What markets look interesting?" → `traderbot scan`
- "Check KX* markets" → `traderbot analyze <ticker>`
- "Buy Yes on..." → `traderbot trade`
- "System status" / "Health check" → `traderbot heartbeat`
- "Stop trading" → `traderbot halt`

**Workspace Files section** (`skills/traderbot/SKILL.md` lines 162–177):
- Lists all 9 workspace files: AGENTS.md, SOUL.md, IDENTITY.md, TOOLS.md, USER.md, HEARTBEAT.md, SESSION-STATE.md, HEARTBEAT_DATA.md, .learnings/
- Explicitly documents the HEARTBEAT.md vs HEARTBEAT_DATA.md distinction

**Cron Architecture section** (`skills/traderbot/SKILL.md` lines 92–148):
- Documents two cron modes: `isolated agentTurn` and `systemEvent`
- References `src/traderbot/cron_loops.py` as programmatic source

### 3.5.3 Cron Architecture Validation

Verify that the three cron loop definitions in `src/traderbot/cron_loops.py` match the SKILL.md documentation and produce valid JSON payloads.

**Decision Loop** (`src/traderbot/cron_loops.py` → `DecisionLoopConfig`):
- `name` = `decision_loop`
- `cron_expression` = `*/5 9-15 * * 1-5`
- `loop_type` = `decision`
- `session_target` = `isolated`
- `payload_type` = `agentTurn`
- `DecisionLoopPayload.message` starts with `"AUTONOMOUS: Run traderbot decision loop"`

**Heartbeat Loop** (`src/traderbot/cron_loops.py` → `HeartbeatLoopConfig`):
- `name` = `heartbeat_loop`
- `cron_expression` = `0 */6 * * *`
- `loop_type` = `heartbeat`
- `session_target` = `isolated`
- `payload_type` = `agentTurn`
- `HeartbeatLoopPayload.message` starts with `"HEARTBEAT: Run traderbot self-improvement cycle"`

**News/Sentiment Loop** (`src/traderbot/cron_loops.py` → `NewsLoopConfig`):
- `name` = `news_loop`
- `cron_expression` = `None` (event-driven, not scheduled)
- `loop_type` = `news`
- `session_target` = `main`
- `payload_type` = `systemEvent`
- `NewsLoopPayload` requires `topic` (str) and `impact_score` (float, 0.0–1.0)
- `impact_score` must be ≥ `NEWS_IMPACT_THRESHOLD` (0.7) when surfaced
- Auto-generated `message` includes the topic: `"ALERT: High-impact event detected ({topic})"`

**LOOP_DEFINITIONS** (`src/traderbot/cron_loops.py` line 120):
- Contains exactly 3 entries: `DecisionLoopConfig()`, `HeartbeatLoopConfig()`, `NewsLoopConfig()`

**Payload serialization**:
- Each `*Payload` model uses `ConfigDict(strict=True, extra="forbid")` (no extra fields)
- `build_payload("decision")` returns `DecisionLoopPayload` instance
- `build_payload("heartbeat")` returns `HeartbeatLoopPayload` instance
- `build_payload("news", topic=..., impact_score=...)` returns `NewsLoopPayload` instance
- `build_payload("unknown")` raises `ValueError`

### 3.5.4 WAL Protocol Verification

Verify that the Write-Ahead Log protocol in `src/traderbot/wal.py` functions correctly for crash-safe trade execution.

**WAL entry fields** (`src/traderbot/wal.py` → `WalEntry`):
- Required fields: `intent_id`, `timestamp`, `action` (BUY/SELL), `ticker`, `direction` (yes/no), `quantity` (int ≥ 1), `price_cents` (int ≥ 1), `reason` (str), `signal` (str), `risk_checks` (str), `confidence` (float 0.0–1.0), `status` (PENDING/COMPLETED/CANCELLED/EXPIRED)
- Uses `ConfigDict(strict=True, extra="forbid")`

**Write-ahead before execution**:
- `write_intent()` is called BEFORE `evaluate_trade()` in `src/traderbot/cli.py` → `trade` command (lines 268–279)
- Initial status = `WalStatus.PENDING`
- After evaluation: status updated to `WalStatus.COMPLETED` (sized > 0) or `WalStatus.CANCELLED` (sized == 0)
- No trade execution path exists without first writing a WAL intent

**Concurrent write protection**:
- `write_intent()` uses `fcntl.LOCK_EX | fcntl.LOCK_NB` for exclusive file lock
- If lock fails → raises `ConcurrentWriteError`
- `update_status()` also uses exclusive lock for status transitions

**WAL file path** (`DEFAULT_SESSION_STATE_PATH`):
- Points to `.openclaw/workspace/SESSION-STATE.md`
- File is created with parent directories if it doesn't exist

**Status transitions**:
- PENDING → COMPLETED (trade executed)
- PENDING → CANCELLED (trade rejected)
- PENDING → EXPIRED (stale intent)
- `scan_pending()` returns only PENDING entries for crash recovery
- `reconcile()` compares pending intents against actual positions and updates status

**Markdown format**:
- Each WAL entry renders as `### WAL-XXXXX` heading followed by bullet lines
- Entry format: `- Action: {BUY|SELL} {YES|NO} {quantity} {ticker} @ {price}¢`
- Entry format includes: `- Reason:`, `- Signal:`, `- Risk:`, `- Confidence:`, `- Status:`

### 3.5.5 Skill Execution Flow

Verify the complete flow from user message through OpenClaw Gateway to TraderBot response.

**Discovery flow**:
- OpenClaw Gateway reads `skills/traderbot/SKILL.md` for command definitions and trigger phrases
- Gateway injects workspace files into agent session context (AGENTS.md, SOUL.md, IDENTITY.md, TOOLS.md, USER.md, HEARTBEAT.md, SESSION-STATE.md, HEARTBEAT_DATA.md)

**Command invocation**:
- User message → Gateway matches trigger phrase → Gateway invokes `traderbot <command> --json`
- All commands support `--json` flag for machine-readable output (single JSON object or array)
- JSON response shape: `{"command": "<cmd>", "timestamp": "<ISO>", "data": {...}}`

**Decision Loop flow** (isolated agentTurn):
1. Gateway starts isolated session
2. Agent reads `SESSION-STATE.md` for tracked markets and pending actions
3. Agent calls `traderbot scan --json` or `traderbot analyze <ticker> --json`
4. If signal found → `traderbot trade <ticker> --direction <yes|no> --quantity N --price CENTS --json`
5. Trade command writes WAL intent (PENDING) → evaluates risk → updates WAL status (COMPLETED/CANCELLED)
6. All decisions logged to audit trail in SQLite

**Heartbeat Loop flow** (isolated agentTurn):
1. Gateway starts isolated session with heartbeat context
2. Agent follows `HEARTBEAT.md` checklist tasks
3. Agent runs `traderbot heartbeat --json` → executes 7-step cycle
4. Output written to `HEARTBEAT_DATA.md` (NOT `HEARTBEAT.md`)
5. If circuit breaker is HALT/FULL_STOP → no new trades
6. If nothing needs attention → agent replies `HEARTBEAT_OK`

**News Loop flow** (systemEvent):
1. News source triggers with `impact_score >= 0.7`
2. Gateway surfaces alert to main session (not isolated)
3. Agent calls `traderbot sentiment <topic> --json`
4. Agent decides whether to adjust tracked markets or circuit breaker

### 3.5.6 Session Management

Verify session scoping and idle reset behavior for multi-channel OpenClaw deployments.

**Per-channel-peer scoping**:
- When `TRADERBOT_PROFILE_TOKEN` is set, CLI resolves it to a `TradingProfile` via `src/traderbot/profiles/tokens.py`
- Profile determines: `enabled_categories`, `max_position_per_market_pct`, `risk_multiplier`
- Profile-aware `AgentRiskLimits` enforces `min(profile_limit, HARD_LIMITS)` — profiles cannot exceed hard limits
- Data isolation: DB, ChromaDB, and audit paths use `profile.base_dir` (via `src/traderbot/profiles/isolation.py`)
- Credentials isolated per profile: keyring namespace `traderbot.profiles.<profile_name>.<service>`

**Session ID scoping**:
- Each cron loop runs in an `isolated` or `main` session context
- Decision and Heartbeat loops use `sessionTarget = "isolated"` (separate from main chat)
- News loop uses `sessionTarget = "main"` (surfaces alerts to human)

**Idle reset behavior**:
- `SESSION-STATE.md` tracks `Last Updated` timestamp for active context
- Pending WAL entries with `status = PENDING` remain across sessions for crash recovery
- `scan_pending()` recovers interrupted trades on session restart
- `HEARTBEAT_DATA.md` timestamp (`## Last Heartbeat:`) indicates staleness — heartbeat loop should check this

**Profile token injection**:
- `TRADERBOT_PROFILE_TOKEN` is injected into `TOOLS.md` by `src/traderbot/profiles/injection.py`
- Agent reads `TOOLS.md` at session start to determine profile context
- `get_current_profile()` in `src/traderbot/profiles/tokens.py` reads env var and resolves it

### 3.5.7 Heartbeat Execution Verification

Verify that the `traderbot heartbeat --json` command produces valid JSON output and writes `HEARTBEAT_DATA.md`.

**CLI entry point** (`src/traderbot/cli.py` → `heartbeat` command):
- Accepts `--json` flag for machine-readable output
- Accepts `--dry-run` flag for report-only mode (no state changes)
- Accepts `--db` flag for overriding database path
- Calls `run_heartbeat_cycle(conn, heartbeat_path=DEFAULT_HEARTBEAT_PATH, dry_run=dry_run)`

**7-step review cycle** (`src/traderbot/heartbeat.py` → `run_heartbeat_cycle`):
1. **Performance review** (`step_performance_review`): aggregates trade outcomes, computes win rate, P&L, avg confidence, deviation flags
2. **Decision review** (`step_decision_review`): reviews prediction accuracy for closed markets, identifies pending reviews
3. **Bayesian adaptation** (`step_bayesian_adaptation`): Beta-Binomial update on win/loss observations, applies 4-update/day cooldown
4. **Learning promotion** (`step_learning_promotion`): scans for `Recurrence-Count >= 3`, promotes to PENDING_REVIEW (never auto-commits to AGENTS.md)
5. **Circuit breaker check** (`step_circuit_breaker_check`): reads CircuitBreaker state → NORMAL/SLOW/HALT/FULL_STOP
6. **System health** (`step_system_health`): DB integrity check, API availability, data freshness
7. **Write HEARTBEAT_DATA.md** (`_write_heartbeat_md`): renders result to markdown at `.openclaw/workspace/HEARTBEAT_DATA.md`

**JSON output structure** (`HeartbeatResult.model_dump(mode="json")`):
- `timestamp`: ISO format datetime
- `performance`: `{trade_count, win_rate, total_pnl_cents, avg_confidence, deviation_flag, ...}`
- `decisions`: `{closed_count, correct_predictions, prediction_accuracy, open_count, pending_review}`
- `adaptation`: `{updated, direction, magnitude, confidence, method, human_review, variance_reset, skipped_reason}`
- `learning_promotion`: `{candidates_found, promoted, promoted_count}`
- `circuit_breaker`: `{level, can_trade, daily_loss_pct, drawdown_pct, position_size_multiplier, reason}`
- `system_health`: `{api_connectivity, db_integrity, data_freshness, alerts}`
- `steps_completed`: list of 7 step names in order

**HEARTBEAT_DATA.md writer** (`_write_heartbeat_md` in `src/traderbot/heartbeat.py`):
- Writes to `DEFAULT_HEARTBEAT_PATH` = `.openclaw/workspace/HEARTBEAT_DATA.md`
- Creates parent directories if they don't exist (`path.parent.mkdir(parents=True, exist_ok=True)`)
- Header: `# TraderBot Heartbeat Data` with blockquote distinguishing from HEARTBEAT.md
- Timestamp line: `## Last Heartbeat: {ISO timestamp}`
- Sections match `steps_completed` order: Performance, Adaptation, Learnings, Circuit Breaker, System Health, Alerts
- All monetary values in cents (int), displayed as USD in markdown
- Written by `traderbot heartbeat` CLI, NOT by the agent manually

**HeartbeatResult model** (`src/traderbot/heartbeat.py`):
- Uses `ConfigDict(strict=True, extra="forbid")`
- All sub-models also use `ConfigDict(strict=True, extra="forbid")`
- Fields have defaults for clean construction when no data is available

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

## PHASE 4.5: AGENT DECISION-MAKING ANALYSIS

Verify the toolkit NEVER decides strategy — it computes, enforces, and executes, but the agent decides. The toolkit is a dumb pipe with smart guards.

### 4.5.1 Toolkit/Agent Boundary

No function in `risk/`, `kalshi/`, `db/`, or `analysis/` returns a buy/sell/hold recommendation.

- `grep -rn "buy\|sell\|hold" src/traderbot/risk/ src/traderbot/kalshi/ src/traderbot/db/ src/traderbot/analysis/` — verify no function return type or docstring contains "buy", "sell", or "hold" as a trading order
- `grep -rn "Literal\[.*buy\|Literal\[.*sell\|Literal\[.*hold" src/traderbot/risk/ src/traderbot/kalshi/ src/traderbot/db/ src/traderbot/analysis/` — verify no Literal type restricts to buy/sell/hold action types
- Verify `evaluate_trade()` in `src/traderbot/risk/__init__.py` returns `int` (sized position in cents, or 0 for rejected) — never returns a decision verb
- Verify `run_all_checks()` in `src/traderbot/risk/limits.py` returns `list[RiskCheckResult]` — each result has `passed: bool` and `rejection_reason: str | None`, never a buy/sell directive
- Verify `sized_position_for_trade()` in `src/traderbot/risk/sizing.py` returns `int` (position size in cents) — no trade action
- Verify `AuditLogger.log_decision()` in `src/traderbot/risk/audit.py` accepts a `Decision` model — it records, never decides
- Verify `src/traderbot/kalshi/` modules only: fetch market data, submit orders, manage positions — no strategy logic
- Verify `src/traderbot/db/` modules only: persist/retrieve state — no strategy logic
- Verify the dependency rule from line 83 of this file: `analysis/` never imports from `risk/`, `db/`, or `news/`

### 4.5.2 Signal Output Verification

`CombinedSignal` describes market conviction, not trading orders. The four signal sources are indicators, odds, momentum, and sentiment.

- Verify `CombinedSignal` model in `src/traderbot/analysis/signals.py` has fields: `ticker: str`, `direction: Literal["yes", "no", "neutral"]`, `confidence: float` (0–1), `sources: list[SignalSource]`, `estimated_prob: float`, `edge_cents: int`
- Verify `direction` is `Literal["yes", "no", "neutral"]` — never `"buy"`, `"sell"`, or `"hold"`
- Verify `SignalSource` model has: `name: str`, `weight: float` (0–1), `direction: Literal["yes", "no", "neutral"]`, `strength: float` (0–1)
- Verify `generate_signal()` returns `CombinedSignal` with populated `sources` list containing entries for each source computed
- Verify `combine_signals()` returns `tuple[Literal["yes", "no", "neutral"], float]` — direction and confidence, never an order
- Verify `default_weights()` returns `{"indicators": 0.3, "odds": 0.5, "momentum": 0.2}` — three base sources, weights sum to 1.0
- Verify sentiment is supported as a 4th source: `default_weights()` has an `include_sentiment` parameter that, when `True`, redistributes weights to include `"sentiment": 0.15` (reducing others proportionally)
- Verify when sentiment source is included, the 4 sources in `generate_signal()` output are: `indicators`, `odds`, `momentum`, `sentiment`
- Verify `edge_cents` is typed as `int` — no floating-point monetary values leak from signal computation

### 4.5.3 Risk Module Immutability

`HARD_LIMITS` are frozen, non-overridable constants. Circuit breaker cannot be cleared by code.

- Verify `HARD_LIMITS` in `src/traderbot/risk/limits.py` is defined as `HARD_LIMITS: Final[dict[str, float | int]] = MappingProxyType({...})` — Python frozen dict via `MappingProxyType`
- Verify `HARD_LIMITS` contains exactly 6 keys: `max_position_per_market_pct`, `max_daily_loss_pct`, `max_drawdown_pct`, `min_liquidity_threshold`, `max_open_positions`, `min_edge_pct`
- Verify `MappingProxyType` prevents mutation: `HARD_LIMITS["max_position_per_market_pct"] = 0.10` raises `TypeError`
- Verify no code path in `risk/` reads limits from config files, environment variables, or external sources — `grep -rn "os.environ\|config\|yaml\|json.load\|toml" src/traderbot/risk/` must return zero matches
- Verify `AgentRiskLimits` in `src/traderbot/risk/agent_limits.py` always takes `min(profile_limit, HARD_LIMITS)` for maximum thresholds — a permissive profile can never exceed hard limits
- Verify `AgentRiskLimits.max_position_per_market_pct` returns `min(self._profile.max_position_per_market_pct, float(HARD_LIMITS["max_position_per_market_pct"]))`
- Verify `AgentRiskLimits.min_edge_pct` returns `max(self._profile.min_edge_pct, float(HARD_LIMITS["min_edge_pct"]))` — more restrictive floor wins
- Verify `AgentRiskLimits.min_liquidity_threshold` returns `max(self._profile.min_liquidity_threshold, int(HARD_LIMITS["min_liquidity_threshold"]))` — higher minimum liquidity threshold wins
- Verify all `AgentRiskLimits` properties are read-only (no setters)
- Verify `CircuitBreaker.clear_full_stop()` in `src/traderbot/risk/circuit_breaker.py` raises `RuntimeError("Not in FULL_STOP state")` if called when not in `FULL_STOP` — code cannot programmatically clear a `FULL_STOP` state that was never reached
- Verify `clear_full_stop()` only resets to `NORMAL` from `FULL_STOP` — it does not transition `SLOW` or `HALT` levels, and `FULL_STOP` requires manual human reset via `traderbot halt --force` followed by clear
- Verify `CircuitBreakerState` model uses `ConfigDict(strict=True, extra="forbid")`
- Verify circuit breaker state is persisted to disk (`~/.traderbot/circuit_breaker_state.json`) on every `check()` call

### 4.5.4 Decision Flow

The CLI `trade` command orchestrates: analysis → signal → risk gate → Kelly sizing → audit log. The agent decides strategy; the toolkit enforces constraints.

- Verify `cli.py` `trade` command flow: creates `TradeRequest` → calls `evaluate_trade()` → receives `int` sized position (0 = rejected) → logs to WAL → records result
- Verify `TradeRequest` model contains: `ticker`, `direction`, `quantity`, `price_cents`, `estimated_prob`, `confidence`, `edge_estimate`, `market_price_cents`, `market_open_interest` — no "strategy" or "action" field
- Verify `evaluate_trade()` in `risk/__init__.py` executes in order: (1) profile category filter → (2) circuit breaker check → (3) `run_all_checks()` → (4) `sized_position_for_trade()` → (5) apply breaker multiplier → (6) apply profile risk multiplier
- Verify if `evaluate_trade()` returns 0, no trade execution happens — the `cli.py` trade handler logs `"outcome": "rejected"` and the reason
- Verify if `evaluate_trade()` returns non-zero, the sized amount still goes through `int()` conversion — always integer cents
- Verify `from traderbot.risk import evaluate_trade` is the ONLY public entry point for risk evaluation from `cli.py`
- Verify `trade` command writes a WAL intent BEFORE calling `evaluate_trade()` — order matters: write intent → evaluate → update status
- Verify audit log is written for BOTH accepted and rejected trades — no path that skips audit
- Verify no function in `cli.py` constructs a "buy" or "sell" string — the `direction` field is `"yes"` or `"no"` (binary outcome), not a strategy recommendation

### 4.5.5 SKILL.md Trigger Verification

Every trigger phrase in `skills/traderbot/SKILL.md` maps to a CLI command. No trigger causes autonomous execution beyond risk-gated placement.

- Verify each trigger phrase in `skills/traderbot/SKILL.md` Trigger Phrases table corresponds to exactly one CLI command defined in `src/traderbot/cli.py`
- Verify "Buy Yes on..." / "Place a trade" maps to `traderbot trade` — which runs through `evaluate_trade()` risk gate
- Verify "What markets look interesting?" maps to `traderbot scan` — which is read-only, no trade execution
- Verify "System status" / "Health check" maps to `traderbot heartbeat` — which is read-only, no trade execution
- Verify "Check signals" maps to `traderbot signals` — which displays signal data, never places trades
- Verify "What's the latest news?" maps to `traderbot news` — which fetches and classifies news, no trade execution
- Verify "Check sentiment" maps to `traderbot sentiment` — which computes sentiment scores, no trade execution
- Verify no SKILL.md trigger phrase causes automatic order placement without going through the `trade` command and its risk gate
- Verify Decision Loop cron payload says "AUTONOMOUS: Run traderbot decision loop... Execute analysis, risk-check, and trades within guard rails" — the phrase "within guard rails" refers to the risk module enforcement
- Verify News Loop uses `systemEvent` mode (surfaces to main session for human intervention) — NOT `agentTurn` for autonomous trading
- Verify `TRADERBOT_PROFILE_TOKEN` environment variable is documented in SKILL.md as optional and controls profile-specific risk limits — not a strategy override

### 4.5.6 Heartbeat Output

Heartbeat outputs only metrics and adaptation data — never trading recommendations.

- Verify `HeartbeatResult` model in `src/traderbot/heartbeat.py` contains: `timestamp`, `performance` (PerformanceReview), `decisions` (DecisionReview), `adaptation` (AdaptationReview), `learning_promotion` (LearningPromotionReview), `circuit_breaker` (CircuitBreakerReview), `system_health` (SystemHealthReview), `steps_completed`
- Verify `PerformanceReview` fields: `trade_count`, `win_rate`, `total_pnl_cents`, `avg_confidence`, `sharpe_ratio`, `max_drawdown_pct`, `open_positions`, `deviation_flag` — all metrics, no actions
- Verify `AdaptationReview` has `direction` field typed as `str` (values like "increase", "decrease", "maintain") — this is a parameter direction for Bayesian adaptation, NOT a trading direction
- Verify `AdaptationReview.direction` is never `"yes"` or `"no"` — it describes edge threshold adjustment, not market position
- Verify heartbeat writes to `HEARTBEAT_DATA.md` (data output file), NOT `HEARTBEAT.md` (agent instructions file) — `_write_heartbeat_md()` writes to `heartbeat_path` parameter, defaulting to `.openclaw/workspace/HEARTBEAT_DATA.md`
- Verify no field in `HeartbeatResult` contains buy/sell/hold recommendations
- Verify `CircuitBreakerReview` fields: `level`, `can_trade`, `daily_loss_pct`, `drawdown_pct`, `position_size_multiplier`, `reason` — status report, no action directive
- Verify `SystemHealthReview` fields: `api_connectivity`, `db_integrity`, `data_freshness`, `alerts` — health status, no trade signals
- Verify heartbeat `--dry-run` flag produces the same output structure but skips all state mutations (no writes to DB, no Bayes updates, no learning promotions)

### 4.5.7 News/Sentiment Output

News classification and sentiment scoring produce category labels and numeric scores — never buy/sell signals.

- Verify `ClassifiedNews` model in `src/traderbot/news/models.py` has fields: `news_item: NewsItem`, `category: NewsCategory`, `sentiment: SentimentResult | None`, `impact: ImpactAssessment | None` — category classification, not trading recommendations
- Verify `NewsCategory` enum values: `politics`, `economics`, `science`, `sports`, `crypto`, `culture`, `tech`, `weather` (lowercase per Python enum convention) — none are "buy", "sell", or "hold". Verify these alias to corresponding `MarketCategory` values in `analysis/registry.py`.
- Verify `SentimentResult` model has: `news_id: str`, `score: float` (ge=-1.0, le=1.0), `confidence: float` (ge=0.0, le=1.0), `model: str`, `timestamp: datetime` — sentiment score and confidence, never a trade direction
- Verify `ImpactAssessment` model has `direction: Literal["bullish", "bearish", "neutral"]` — market outlook, not an order type
- Verify `ImpactAssessment.direction` uses "bullish"/"bearish"/"neutral" — distinct from "yes"/"no" in signal vocabulary, and never "buy"/"sell"/"hold"
- Verify `NewsClassifier.classify()` returns `ClassifiedNews` — a category assignment, never an investment recommendation
- Verify `SentimentScorer.score()` returns `SentimentResult` — a numeric score + confidence, never a trading action
- Verify `ClassificationResult` (internal) has `flagged_for_llm: bool` — this flags uncertainty for future LLM review, NOT for automatic trading
- Verify `traderbot news` CLI command outputs: title, source, category, published_at, sentiment_score, sentiment_confidence, sentiment_model, url, ticker_refs — all descriptive/metric, no "recommendation" field
- Verify `traderbot sentiment` CLI command outputs: ticker, items_analyzed, sentiment (score + direction + confidence), and impacts — direction is "bullish"/"bearish"/"neutral" (market outlook), NOT "buy"/"sell"
- Verify no code path in `news/classifier.py` or `news/sentiment_scorer.py` produces a `SignalSource` or `CombinedSignal` — news/sentiment feeds data INTO the signal system, it IS a signal source, but the classifier and scorer themselves don't create trading signals

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

**Coverage gap remediation protocol:**

When coverage report shows missing lines (e.g., `risk/audit.py   60      6    90%   36,41,43,54,67-68`):

1. **Classify the gap**: Is it an error path, an edge case, or dead code?
   - **Error path** (e.g., `except SomeError:` catch blocks) → Add test that triggers the error
   - **Edge case** (e.g., None returns, zero-length input) → Add test with edge-case input
   - **Dead code** (unreachable branch) → Remove the dead code; don't add tests for unreachable paths

2. **Prioritize by module criticality**:
   - `risk/` gaps (money at stake) → P1, must fix before any release
   - `kalshi/trading.py` (order placement) → P1, wrong order = real money loss
   - `analysis/` gaps → P2, wrong signal = bad decisions but no direct money handling
   - `cli.py` gaps → P3, UX only (no financial impact from missing CLI test)

3. **Write targeted tests**: One test per uncovered branch. Do NOT write catch-all tests that cover multiple branches incidentally — each test should target a specific uncovered line.

4. **Verify**: Re-run `pytest --cov=traderbot --cov-report=term-missing tests/` and confirm the specific lines are now covered.

### 5.5 Security & Encryption Deep Audit

This phase verifies that no secrets are exposed in plaintext and that the highest security practices are implemented. Every finding from the T3 security audit must be verified as a formal checklist item.

#### 5.5.1 SecretStr Enforcement

All credential fields must use `SecretStr` instead of plain `str`. Any credential stored as plain `str` is a leak vector — `model_dump()`, `repr()`, and log output will expose the value.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | `KalshiConfig.api_key` is `SecretStr` | `grep -n "api_key:" src/traderbot/kalshi/config.py` | Field declaration uses `SecretStr`, not `str` | P1 |
| 2 | `WebSocketConfig.api_key` is `SecretStr` | `grep -n "api_key:" src/traderbot/kalshi/websocket.py` | Field declaration uses `SecretStr`, not `str` | P1 |
| 3 | `KalshiClient._session_token` is `SecretStr` | `grep -n "_session_token" src/traderbot/kalshi/client.py` | Private attribute typed as `SecretStr` | P1 |
| 4 | `NewsAggregator._newsapi_key` is `SecretStr` | `grep -n "_newsapi_key" src/traderbot/news/aggregator.py` | Private attribute typed as `SecretStr` | P1 |
| 5 | `NewsAggregator._twitter_api_key` is `SecretStr` | `grep -n "_twitter_api_key" src/traderbot/news/aggregator.py` | Private attribute typed as `SecretStr` | P1 |
| 6 | `VoyageClient` does not store API key as plain attribute | `grep -n "api_key\|VOYAGE_API_KEY" src/traderbot/news/embeddings.py` | Key is not stored as a plain instance attribute; accessed via keyring or `SecretStr` | P1 |

#### 5.5.2 Keyring Usage — Credential Access Path

All credentials must be retrieved through `auth.py` keyring abstractions. No direct `os.getenv` or `os.environ.get` for secrets — these bypass keyring isolation and make credential rotation impossible.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | No `os.getenv` / `os.environ.get` for credential-like env vars outside `auth.py` | `grep -rn 'os\.environ\.get\|os\.getenv' src/traderbot/ --include='*.py' \| grep -v auth.py \| grep -i 'key\|secret\|token\|cred\|api'` | Zero matches outside `auth.py` | P1 |
| 2 | `VOYAGE_API_KEY` read from keyring (not env) | `grep -n "VOYAGE_API_KEY" src/traderbot/news/embeddings.py` | No `os.environ.get("VOYAGE_API_KEY")`; credential fetched via `ProfileAuthStore` | P1 |
| 3 | `NEWSAPI_KEY` read from keyring (not env) | `grep -n "NEWSAPI_KEY" src/traderbot/cli.py` | No `os.environ.get("NEWSAPI_KEY")`; credential fetched via `ProfileAuthStore` | P1 |
| 4 | `TWITTER_API_KEY` read from keyring (not env) | `grep -n "TWITTER_API_KEY" src/traderbot/cli.py` | No `os.environ.get("TWITTER_API_KEY")`; credential fetched via `ProfileAuthStore` | P1 |
| 5 | `ProfileAuthStore` is the sole credential accessor | `grep -rn "get_credentials\|set_credentials" src/traderbot/ --include='*.py' \| grep -v auth.py \| grep -v test` | All credential reads go through `ProfileAuthStore` | P1 |

#### 5.5.3 `model_dump()` Safety

When a model containing `SecretStr` fields is serialized with `model_dump()`, the default mode exposes raw secret values. Only `model_dump(mode="json")` with `SecretStr` serialization guards is safe.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | `DemoAdapter` does not call `model_dump()` on `KalshiConfig` without serialization guard | `grep -n "model_dump" src/traderbot/kalshi/demo.py` | Uses `model_dump(mode="json")` or manual field copy, NOT bare `model_dump()` on a config that contains `SecretStr` fields | P1 |
| 2 | No bare `model_dump()` on objects with `SecretStr` fields anywhere | `grep -rn "\.model_dump()" src/traderbot/ --include='*.py' \| grep -v 'mode="json"' \| grep -v test` | Every `model_dump()` call on a model with secret fields uses `mode="json"` or excludes secret fields | P1 |

#### 5.5.4 Logging Safety — No Secrets in Console Output

Logging or printing secrets to console, logs, or stdout is a P0 violation. Secrets must never appear in any output stream.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | **P0**: `cli.py` does not print profile token to console | `grep -n "profile.*token\|token.*profile\|print.*token" src/traderbot/cli.py` around line 1829 context | No `print()` or `typer.echo()` that outputs the profile token value | **P0** |
| 2 | No `logger` calls that include secret values | `grep -rn 'logger\.\(info\|debug\|warning\|error\).*api_key\|logger\.\(info\|debug\|warning\|error\).*secret\|logger\.\(info\|debug\|warning\|error\).*token' src/traderbot/ --include='*.py'` | Zero matches where a secret value (not its name) is interpolated into a log message | P0 |
| 3 | All `SecretStr` fields use `.get_secret_value()` only in assignment context | `grep -rn "get_secret_value" src/traderbot/ --include='*.py'` | Every call to `.get_secret_value()` is followed by assignment to a local variable, never passed to `print()`, `logger`, or `json.dump()` | P1 |

#### 5.5.5 File Permissions — Sensitive Files Not World-Readable

All files containing credentials, tokens, session state, or audit data must be created with restrictive permissions (0600 or equivalent). Default `open()` creates world-readable files.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | Audit log files created with restricted permissions | `grep -n "open\|write_text\|Path.*touch" src/traderbot/risk/audit.py` | Uses `os.open()` with `0o600` mode or equivalent; NOT default `open()` | P1 |
| 2 | Session state file created with restricted permissions | `grep -n "write_text\|open.*w\|Path.*touch" src/traderbot/risk/circuit_breaker.py` | Uses restrictive file creation mode | P1 |
| 3 | DB files created with restricted permissions | `grep -n "sqlite\|connect" src/traderbot/db/` | SQLite connection uses `mode=0600` or equivalent | P2 |
| 4 | Profile directory created with restrictive permissions | `grep -n "mkdir\|makedirs" src/traderbot/profiles/` | Uses `0o700` mode for profile directories | P2 |

#### 5.5.6 Demo/Production Isolation

Demo and production configurations must be strictly separated. A demo credential must never reach a production endpoint, and a production credential must never be used in demo mode.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | `DemoAdapter` rebuilds config without leaking `SecretStr` value | Read `src/traderbot/kalshi/demo.py` lines 14–18 | `_rebuild_config` explicitly excludes secret fields from the dump, or uses `model_dump(mode="json")` with SecretStr serialization | P1 |
| 2 | `DemoAdapter` validates that demo credentials are used for demo endpoints | `grep -n "demo_mode\|demo_url\|prod" src/traderbot/kalshi/demo.py` | When `demo_mode=True`, the adapter refuses to connect to production URLs | P1 |
| 3 | No credential cross-contamination between demo and production | `grep -rn "demo.*prod\|prod.*demo" src/traderbot/ --include='*.py'` | No code path that loads production credentials into a demo context or vice versa | P1 |
| 4 | `model_dump()` on `KalshiConfig` in demo context does not leak production secrets | `grep -n "model_dump" src/traderbot/kalshi/demo.py` | When `model_dump()` is called with a production config, `SecretStr` fields are redacted | P1 |

#### 5.5.7 Secrets in Git History

No API keys, tokens, or credentials may be tracked in git. The `.gitignore` must prevent accidental commits.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | No tracked files contain literal secret strings | `git ls-files \| xargs grep -l 'api_key\s*=\s*["\x27][a-zA-Z0-9]\{16,\}["\x27]' 2>/dev/null \|\| echo "PASS: No hardcoded secrets"` | Command exits cleanly with "PASS" output | P0 |
| 2 | `.gitignore` covers `.env`, `*.key`, `*.pem`, `credentials.json` | `grep -E '\.env|\.key|\.pem|credentials' .gitignore` | All four patterns are ignored | P1 |
| 3 | Git history does not contain secrets in diff content | `git log -p --all -S 'api_key' -- '*.py' \| head -50` | No diffs showing literal secret values committed | P1 |

#### 5.5.8 Audit Trail Integrity

Audit logs must be tamper-evident. The current WAL implementation allows `r+` (read-write) mode, enabling mutation of past entries.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | WAL file opened in append-only mode, not `r+` | `grep -n "open.*r+\|open.*'r+'" src/traderbot/risk/audit.py` | No `r+` mode; WAL files opened with `'a'` (append) or `'r'` (read-only) | P1 |
| 2 | Audit log entries include content hash for tamper detection | `grep -n "hash\|sha\|hmac\|digest" src/traderbot/risk/audit.py` | Each audit entry includes a hash/HMAC of the prior entry (chain) or its own content | P1 |
| 3 | Audit log files are append-only at the filesystem level | `grep -n "open.*a\b" src/traderbot/risk/audit.py` | Audit file opened in append mode (`'a'`) | P2 |
| 4 | No code path rewrites or overwrites past audit entries | `grep -rn "seek\|truncate\|write.*offset" src/traderbot/risk/audit.py` | Zero matches; no seek/truncate/write operations on audit files | P1 |

#### 5.5.9 Jailbreak Resistance — Agent Safety Boundaries

The agent must not be lured into bypassing safety constraints through prompt injection, SOUL.md manipulation, or risk limit override.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | `HARD_LIMITS` are hardcoded constants, not read from config | `grep -n "HARD_LIMITS" src/traderbot/risk/limits.py` | `HARD_LIMITS` values are literal `int` constants; no `os.getenv`, `json.load`, or file reads | P0 |
| 2 | No code path allows runtime modification of `HARD_LIMITS` | `grep -rn "HARD_LIMITS\." src/traderbot/risk/ --include='*.py' \| grep -v "import\|from\|HardLimits\|class Hard"` | Zero assignment statements modifying `HARD_LIMITS` attributes | P0 |
| 3 | SOUL.md contains red lines that prevent self-modification | `grep -i "red.line\|never.override\|immutable\|cannot.modify" SOUL.md \| head -5` | Red-line section exists with explicit immutability rules | P1 |
| 4 | `evaluate_trade()` enforces `min(profile_limit, HARD_LIMITS)` ceiling | `grep -n "profile.*HARD_LIMITS\|min.*HARD" src/traderbot/risk/` | Position sizing uses `min(profile.risk_multiplier, HARD_LIMITS.ceiling)` | P0 |

#### 5.5.10 Dependency Security

Third-party dependencies must not introduce known vulnerabilities.

| # | Check | Grep / Read Command | Pass Criteria | Severity |
|---|-------|---------------------|---------------|----------|
| 1 | No known CVEs in direct dependencies | `pip audit 2>/dev/null \|\| pip-audit 2>/dev/null \|\| echo "SKIPPED: pip-audit not installed"` | Zero known vulnerabilities in direct dependencies | P1 |
| 2 | `pyproject.toml` pins dependency versions | `grep -c "^dependencies" pyproject.toml \| grep -A20 "^dependencies" pyproject.toml \| grep ">=" | head -10` | Dependencies are pinned to specific versions or minimum versions with upper bounds | P2 |
| 3 | No `--no-verify` or `--allow-unverified` in install commands | `grep -rn "no-verify\|allow-unverified\|--trusted" pyproject.toml Makefile scripts/` | Zero matches | P1 |

### 5.6 Fix and Re-run

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
- ALL phases (0-5.5) pass with zero P0, P1, P2 findings (including Phase 5.5 Security & Encryption Deep Audit)
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

---

## §2.18: Phase 5 — Simulation Test Patterns

### Backtesting Tests

- Verify `BacktestEngine.run()` replays events chronologically (monotonically non-decreasing timestamps)
- Verify no look-ahead bias: strategy never receives `Market.settled_price` before market `close_time`
- Verify risk limits are enforced during backtesting: oversize positions rejected, audit trail shows rejection reason
- Verify `BacktestResult` returns `None` for `win_rate`, `sharpe_ratio`, `brier_score`, `edge_capture` when `trade_count == 0` (no division by zero)
- Verify slippage model uses worst-case fill within spread
- Verify `DataLoader` caches results in SQLite and reuses cache on second call
- Verify `DataLoader` quality checks flag low-liquidity markets and incomplete trade data

### Paper Trading Tests

- Verify `PaperTrader` composes with `DemoAdapter` (imports it, does not redefine it)
- Verify `PaperTrader` places orders against demo API, tracks fills and P&L in cents (int)
- Verify `PaperTrader` handles `DemoAdapter` failures gracefully (logs error, holds position, does NOT crash)
- Verify paper positions are stored separately from live positions in `db/positions`

### StrategyProfile Tests

- Verify `StrategyProfile` model validates `risk_multiplier` in range (0, 1.0]
- Verify `StrategyProfile` rejects zero or negative `signal_weights`
- Verify `StrategyProfile` validates at least one non-zero weight in `signal_weights`
- Verify preset profiles (Conservative 0.5x, Moderate 1.0x, Aggressive 0.8x) produce expected `effective_limit` values
- Verify `effective_limit = risk_multiplier * HARD_LIMITS[key]` never exceeds `HARD_LIMITS[key]`
- Verify `BacktestEngine.run_profiles()` produces separate results for each profile
- Verify `compare` CLI shows side-by-side metrics for multiple profiles

### Bootstrap Tests

- Verify `traderbot bootstrap` produces calibration report with per-horizon fit parameters
- Verify warm-up period handling: SMA/EMA/RSI use `min(period, len(prices))` for shorter lookback on insufficient data
- Verify insufficient data (< 30 days): proceeds with partial data and logs WARNING with date range used
- Verify bootstrap never crashes on empty or sparse data (returns warning, partial results)

---

### Simulation Integration Tests

Test `tests/test_simulation_integration.py` end-to-end scenarios:

**End-to-end pipeline:**
- `BacktestEngine.run()` replays events chronologically with monotonically non-decreasing timestamps
- No look-ahead bias: strategy never receives `Market.settled_price` before market `close_time`
- Risk limits enforced during backtesting: oversize positions rejected, audit trail shows rejection reason
- `BacktestResult` returns `None` for `win_rate`, `sharpe_ratio`, `brier_score`, `edge_capture` when `trade_count == 0` (no division by zero)
- Slippage model uses worst-case fill within spread
- `DataLoader` caches results in SQLite and reuses cache on second call
- `DataLoader` quality checks flag low-liquidity markets and incomplete trade data

**Paper trading integration:**
- `PaperTrader` composes with `DemoAdapter` (imports it, does not redefine it)
- `PaperTrader` places orders against demo API, tracks fills and P&L in cents (int)
- `PaperTrader` handles `DemoAdapter` failures gracefully (logs error, holds position, does NOT crash)
- Paper positions stored separately from live positions in `db/positions`

**CLI integration:**
- `traderbot backtest` command runs backtest with `--ticker`, `--start`, `--end` flags and produces `BacktestResult`
- `traderbot paper` command runs paper trading with `--ticker`, `--strategy` flags
- `traderbot compare` command shows side-by-side metrics for multiple profiles
- `traderbot performance` command shows aggregated performance metrics

**Risk enforcement in simulation:**
- Backtest engine rejects trades that exceed per-market position limit
- Paper trader respects circuit breaker state (no new trades when HALT or FULL_STOP)
- Risk checks logged to audit trail during simulation

---

## §2.19: Phase 6 — Self-Learning Test Patterns

### Learnings DB Tests

- Verify `db/learnings.py` tracks pattern entries with `Pattern-Key`, `Recurrence-Count`, `Priority`, `Status`, `Category`
- Verify pattern staleness: entries with `max_age_days > 30` from last recurrence are NOT eligible for promotion
- Verify `max_age_days=30` constraint cannot be overridden at runtime
- Verify pattern promotion requires `Recurrence-Count >= 3` across 2+ tasks within 30-day window

### WAL Protocol Tests

- Verify trade decisions are written to `SESSION-STATE.md` BEFORE execution
- Verify WAL entries contain: action, reason, signal, risk params, confidence, status
- Verify concurrent write attempts log ERROR and reject (single-agent constraint)
- Verify crash recovery: on restart, `SESSION-STATE.md` pending actions are reconciled with actual positions

### Feature Request Tests

- Verify `FEATURE_REQUESTS.md` entries use `feature_request` category
- Verify feature request entries have `Recurrence-Count` that increments per occurrence
- Verify promotion to `PENDING_REVIEW` status when recurrence criteria met
- Verify `PENDING_REVIEW` entries are NOT auto-implemented — they require human approval
- Verify feature requests follow same staleness constraint (`max_age_days=30`)

### Degradation Logging Tests

- Verify all fallback paths log WARNING when degrading:
  - Voyage API unavailable: log WARNING with `"voyage_status": "unavailable"` and component name
  - ChromaDB unavailable: log WARNING with which semantic features are disabled
  - NewsAPI unavailable: log WARNING and continue with available sources
  - Twitter API key unset: log WARNING and return empty results (stub)
- Verify degradation warnings are visible in heartbeat review logs

---

## §2.20: Phase 7 — News/Sentiment Test Patterns

### Source Aggregation Tests

- Verify `news/sources.py` aggregates from NewsAPI, Twitter, Reddit with unified interface
- Verify each source degrades gracefully when API key is unset (WARNING logged)
- Verify Twitter stub returns empty list with WARNING when `TWITTER_API_KEY` is unset (no OAuth flow attempted)
- Verify source priority: Twitter (fastest) → NewsAPI → Reddit (deepest)

### Classifier Tests

- Verify `MarketCategory` enum covers: ECONOMICS, POLITICS, WEATHER, SPORTS, CULTURE, TECHNOLOGY, SCIENCE
- Verify `CategoryAnalyzer` Protocol requires `analyze` method returning `CategorySignals`
- Verify `AnalysisRegistry.register()` adds per-category analyzers
- Verify `AnalysisRegistry.get()` returns `None` for unregistered categories
- Verify `AnalysisRegistry.analyze()` dispatches to appropriate `CategoryAnalyzer` based on classification
- Verify fallback to keyword matching when no analyzer registered for a category

### Sentiment Scoring Tests

- Verify VADER scores complete in <10ms per text
- Verify TextBlob used for longer-form content (articles)
- Verify Voyage uplift only invoked for VADER compound in [-0.3, +0.3] range
- Verify `SentimentResult` model has: `compound`, `category`, `confidence`, `relevant_tickers`
- Verify slow path (Voyage) is non-blocking — fast path returns immediately, Voyage updates asynchronously

### Impact Assessment Tests

- Verify domain authority scoring multiplies impact by source authority per category
- Verify evidence quality thresholds per category:
  - ECONOMICS: min evidence quality 0.7, min authority 0.5
  - POLITICS: min evidence quality 0.6, min authority 0.5
  - WEATHER: min evidence quality 0.5, min authority 0.3
  - SPORTS: min evidence quality 0.55, min authority 0.3
  - TECHNOLOGY: min evidence quality 0.7, min authority 0.4
  - SCIENCE: min evidence quality 0.7, min authority 0.5
- Verify items below threshold have proportionally reduced impact scores (still logged)
- Verify corroboration boost: 1.3× multiplier when multiple independent sources report same event (capped at 1.0)

---

## §2.21: Phase 8 — Adaptation Test Patterns

### Bayesian Update Tests

- Verify `simulation/adaptation.py` produces mathematically correct posterior distributions
- Verify conjugate prior updates for Beta, Dirichlet, Normal distributions
- Verify parameter bounds: no parameter moves more than 20% in a single update
- Verify minimum sample: no update with fewer than 10 observations
- Verify cooldown: no more than 4 updates per 24 hours
- Verify reset trigger: posterior distribution variance < 0.01 resets to weak prior
- Verify human review flag: any parameter moving >10% for 3 consecutive updates triggers alert

### Guardrails Tests

- Verify adaptation guardrails prevent pathological behavior:
  - Wild parameter swings from small sample sizes (bounded by 20% rule)
  - Over-fitting to recent data (minimum 10 observations, cooldown)
  - False convergence (variance reset trigger)
- Verify all monetary values in adaptation are `int` cents
- Verify all Pydantic models use `ConfigDict(strict=True, extra="forbid")`

### Heartbeat Tests

- Verify `traderbot heartbeat` runs the self-review cycle (triggered every 6 hours via cron, 7 steps within):
  1. Performance review (win rate, Sharpe, drawdown)
  2. Decision review (predicted vs. actual outcomes)
  3. Bayesian adaptation (parameter updates)
  4. Learning promotion (recurrence check with staleness constraint)
  5. Capability gap detection (scan FEATURE_REQUESTS.md)
  6. Circuit breaker check
  7. Write HEARTBEAT_DATA.md
- Verify heartbeat logs all parameter changes with reasoning
- Verify heartbeat promotes learnings to `PENDING_REVIEW` (not auto-committed to AGENTS.md)

### Cron Architecture Tests

- Verify three-loop cron definitions: Decision Loop (5 min), Heartbeat Loop (6 hr), News Loop (event-driven)
- Verify `isolated agentTurn` for Decision and Heartbeat loops (no human attention needed)
- Verify `systemEvent` for News Loop (surfaces actionable events to main session)
- Verify WAL entry recovery on cron restart

---

## PHASE 0.8: INSTALLATION & CONFIGURATION FLOW

Test the full installation flow from zero to operational. Every check must reference a specific file, command, or value — no vague "verify it works" items.

### 0.8.1 Dependency Installation

- Verify `pyproject.toml` specifies `requires-python = ">=3.12"` — run `python3 -c "import tomllib; f=open('pyproject.toml','rb'); d=tomllib.load(f); assert d['project']['requires-python']=='>=3.12'"`
- Verify all runtime dependencies listed in `pyproject.toml` `[project.dependencies]` are present: `httpx>=0.27`, `websockets>=13.0`, `pydantic>=2.7`, `pydantic-settings>=2.3`, `typer>=0.12`, `rich>=13.0`, `keyring>=25.0`, `feedparser>=6.0`, `vaderSentiment>=3.3`, `textblob>=0.18`, `chromadb>=0.4.22,<0.5.0`, `voyageai>=0.2,<1.0`
- Verify dev dependencies are present: `pytest>=8.2`, `pytest-asyncio>=0.23`, `pytest-cov>=5.0`, `ruff>=0.5`, `respx>=0.22`
- Verify `uv pip install -e .` completes with exit code 0 from repo root
- Verify `pip install -e .` completes with exit code 0 as fallback when `uv` is unavailable
- Verify after install, `traderbot --help` exits 0 and prints command listing
- Verify `traderbot` entry point is defined in `pyproject.toml` `[project.scripts]` as `traderbot = "traderbot.cli:main"`
- Verify `install/traderbot-installer.sh` checks for `uv` first (`command -v uv`) and falls back to `pip install -e .`

### 0.8.2 Python Version Check Enforcement

- Verify `cli.py` `bootstrap` command checks `sys.version_info >= (3, 12)` and exits with code 1 if version is insufficient
- Run `traderbot bootstrap --dry-run` with Python 3.12+ — verify `"python_version_ok": true` in JSON output
- Verify `pyproject.toml` `target-version = "py312"` is set in `[tool.ruff]`
- Verify `install/traderbot-installer.sh` `install_dependencies_macos` checks for `python3` and exits 1 with message if not found
- Verify error output contains "3.12" when running with Python < 3.12: `traderbot bootstrap --dry-run` produces `"python_version_ok": false` and exit code 1

### 0.8.3 API Key Configuration via Keyring

- Verify `src/traderbot/auth.py` defines `_REQUIRED_SERVICES = {"kalshi": ["api_key", "api_secret"]}` and `_OPTIONAL_SERVICES` containing `voyage`, `newsapi`, `twitter`, `reddit`
- Verify `AuthManager.keyring_available` returns `False` when keyring backend name contains "Fail" or "Null"
- Verify `AuthManager.check_credentials()` returns `{service: {key: bool}}` for all services in `_ALL_SERVICES`
- Verify `traderbot auth check` displays credential status for all 5 services (kalshi, voyage, newsapi, twitter, reddit)
- Verify `traderbot auth login` prompts for each key in `_ALL_SERVICES` when keyring is available
- Verify `traderbot auth set-key <service> <key>` stores a credential via keyring with prefix `traderbot.`
- Verify `traderbot auth list-keys` displays service names (never values) for configured credentials
- Verify `traderbot auth rotate kalshi` deletes old keys and prompts for new ones
- Verify keyring namespace isolation: `AuthManager._full_service("kalshi")` returns `"traderbot.kalshi"`
- Verify profile-aware keyring namespace: `AuthManager` used inside profiles resolves to `traderbot.profiles.<name>.<service>`
- Verify `.env` fallback: `AuthManager.get_credential()` returns `CredentialResult(source="env")` when keyring is unavailable and `KALSHI_API_KEY` environment variable is set
- Verify env mapping: `AuthManager._service_key_to_env("kalshi", "api_key")` returns `"KALSHI_API_KEY"`, `"kalshi", "api_secret"` → `"KALSHI_API_SECRET"`, `"kalshi", "demo_mode"` → `"KALSHI_DEMO_MODE"`

### 0.8.4 Demo Mode Configuration

- Verify `src/traderbot/kalshi/config.py` `KeyringKalshiConfig` has `demo_mode: bool = False` field
- Verify `KALSHI_DEMO=true` environment variable sets `KeyringKalshiConfig.demo_mode = True`
- Verify `KeyringKalshiConfig.active_url` returns `"https://demo-api.kalshi.co/trade-api/v2"` when `demo_mode=True`
- Verify `KeyringKalshiConfig.active_url` returns `"https://api.kalshi.co/trade-api/v2"` when `demo_mode=False`
- Verify `KeyringKalshiConfig` has `base_url = "https://api.kalshi.co/trade-api/v2"` and `demo_url = "https://demo-api.kalshi.co/trade-api/v2"` defaults
- Verify `KeyringKalshiConfig` uses `SettingsConfigDict(strict=True, extra="forbid", env_prefix="KALSHI_", env_file=".env")`
- Verify `skills/traderbot/SKILL.md` environment table lists `KALSHI_DEMO` (or `KALSHI_DEMO_MODE`) as an environment variable
- Verify `paper` command uses `DemoAdapter` when demo mode is active: `from traderbot.kalshi.demo import DemoAdapter`

### 0.8.5 OpenClaw Workspace Setup

- Verify `.openclaw/workspace/` directory exists with all 8 required files: `AGENTS.md`, `SESSION-STATE.md`, `HEARTBEAT.md`, `HEARTBEAT_DATA.md`, `TOOLS.md`, `IDENTITY.md`, `SOUL.md`, `USER.md`
- Verify `.openclaw/workspace/AGENTS.md` contains trading constraints and self-learning protocol (references from `docs/architecture.md`)
- Verify `.openclaw/workspace/SESSION-STATE.md` contains WAL protocol sections (active positions, pending actions)
- Verify `.openclaw/workspace/HEARTBEAT.md` contains `tasks:` blocks for heartbeat checklist (NOT data output — distinct from `HEARTBEAT_DATA.md`)
- Verify `.openclaw/workspace/TOOLS.md` references `traderbot` CLI commands and contains `TRADERBOT_PROFILE_TOKEN` placeholder for token injection
- Verify `.learnings/` directory exists under `.openclaw/workspace/` with at minimum `LEARNINGS.md`, `ERRORS.md`, `FEATURE_REQUESTS.md`
- Verify workspace files are non-empty: each file in `.openclaw/workspace/` has size > 0 bytes
- Verify `install/traderbot-installer.sh` checks for `~/.openclaw` directory and `openclaw` binary via `check_openclaw()` — exits 1 if not found

### 0.8.6 Skill Registration

- Verify `skills/traderbot/SKILL.md` YAML frontmatter contains `name: traderbot`, `description`, and `metadata.openclaw` with `requires.env` listing `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY`
- Verify `skills/traderbot/SKILL.md` command table lists all CLI commands that exist in `src/traderbot/cli.py` — cross-check every command in SKILL.md against a `@app.command()` or `@<sub>_app.command()` decorator in cli.py
- Verify SKILL.md table includes these commands with matching argument signatures: `scan`, `analyze`, `trade`, `positions`, `audit`, `signals`, `heartbeat`, `halt`, `news`, `sentiment`, `backtest`, `paper`, `compare`, `performance`, `learnings`, `bootstrap`, `profile create`, `profile list`, `profile show`, `profile delete`, `profile update`, `profile assign`, `profile revoke`, `profile assignments`, `profile discover-agents`, `profile set-auth`, `profile auth`, `auth login`, `auth set-key`, `auth list-keys`, `auth rotate`, `auth check`, `update check`, `update apply`, `update configure`, `auth login`, `auth set-key`, `auth list-keys`, `auth rotate`, `auth check`
- Verify SKILL.md trigger phrases table maps agent language to correct CLI commands
- Verify SKILL.md environment table lists all required and optional env vars: `KALSHI_API_KEY` (required), `KALSHI_PRIVATE_KEY` (required), `KALSHI_DEMO` (optional), `TRADERBOT_PROFILE_TOKEN` (optional)
- Verify SKILL.md cron architecture section describes 3 loops matching `src/traderbot/cron_loops.py`: Decision Loop (`*/5 9-15 * * 1-5`), Heartbeat Loop (`0 */6 * * *`), News Loop (event-driven, `None` cron)
- Verify SKILL.md risk guard rails section lists limits matching `src/traderbot/risk/limits.py`: 10% max position per market, daily loss thresholds, no short selling, full audit trail

### 0.8.7 Cron Configuration

- Verify `src/traderbot/cron_loops.py` exports `LOOP_DEFINITIONS: list[CronLoopConfig]` containing exactly 3 entries
- Verify Decision Loop config: `name="decision_loop"`, `cron_expression="*/5 9-15 * * 1-5"`, `loop_type="decision"`, `session_target="isolated"`, `payload_type="agentTurn"`
- Verify Heartbeat Loop config: `name="heartbeat_loop"`, `cron_expression="0 */6 * * *"`, `loop_type="heartbeat"`, `session_target="isolated"`, `payload_type="agentTurn"`
- Verify News Loop config: `name="news_loop"`, `cron_expression=None`, `loop_type="news"`, `session_target="main"`, `payload_type="systemEvent"`
- Verify `DecisionLoopPayload` model has `session_target="isolated"`, `kind="agentTurn"`, and a `message` field containing "AUTONOMOUS"
- Verify `HeartbeatLoopPayload` model has `session_target="isolated"`, `kind="agentTurn"`, and a `message` field containing "HEARTBEAT"
- Verify `NewsLoopPayload` model has `session_target="main"`, `kind="systemEvent"`, `topic: str`, `impact_score: float` with `Field(ge=0.0, le=1.0)`
- Verify `NewsLoopPayload.model_post_init` auto-generates `message` if empty, containing "ALERT" and referencing `self.topic`
- Verify `build_payload("decision")` returns `DecisionLoopPayload`, `build_payload("heartbeat")` returns `HeartbeatLoopPayload`, `build_payload("news", topic="BTC", impact_score=0.9)` returns `NewsLoopPayload`
- Verify `build_payload("invalid")` raises `ValueError`
- Verify `NEWS_IMPACT_THRESHOLD = 0.7` in `cron_loops.py` matches the threshold documented in SKILL.md
- Verify all cron Pydantic models use `ConfigDict(strict=True, extra="forbid")`

### 0.8.8 Configuration Validation Smoke Test

- Verify `traderbot --help` exits 0 and lists all subcommands: `scan`, `analyze`, `trade`, `positions`, `audit`, `signals`, `heartbeat`, `halt`, `news`, `sentiment`, `backtest`, `paper`, `compare`, `performance`, `learnings`, `bootstrap`, `auth`, `profile`, `update`
- Verify `traderbot scan --help` exits 0 and describes market listing with `--limit`, `--category`, `--json` options
- Verify `traderbot analyze --help` exits 0 and describes market analysis with `TICKER` argument and `--json` option
- Verify `traderbot trade --help` exits 0 and describes trade placement with `TICKER`, `--direction`, `--quantity`, `--price`, `--json` options
- Verify `traderbot bootstrap --dry-run --json` exits 0 and returns JSON with keys: `python_version`, `python_version_ok`, `config_dir`, `keyring_available`, `credentials_ok`, `db_path`
- Verify `traderbot auth check` exits 0 and shows credential status table (or `.env` fallback message)
- Verify `traderbot profile list` exits 0 even with no profiles created
- Verify `VERSION` file reads `0.08.21` (matches current release)
- Verify `pyproject.toml` version field — note: may lag behind `VERSION` file but must be a valid semver
- Verify `traderbot heartbeat --dry-run --json` exits 0 and returns JSON with keys: `timestamp`, `steps_completed`, `performance`, `decisions`, `adaptation`, `learning_promotion`, `circuit_breaker`, `system_health`

### 0.8.9 Environment Isolation

- Verify `KALSHI_DEMO=true` causes `KeyringKalshiConfig.demo_mode` to be `True` and `active_url` to point to `demo-api.kalshi.co`
- Verify `KALSHI_DEMO` unset or `KALSHI_DEMO=false` causes `demo_mode=False` and `active_url` to point to `api.kalshi.co`
- Verify `TRADERBOT_PROFILE_TOKEN` unset results in global HARD_LIMITS being used by risk module
- Verify `TRADERBOT_PROFILE_TOKEN` set to a valid token resolves via `get_current_profile()` and applies profile-specific risk limits
- Verify profile-specific `AgentRiskLimits.max_position_per_market_pct` is capped by `HARD_LIMITS.max_position_per_market_pct` — a permissive profile cannot exceed hard limits
- Verify `AuthManager` with `TRADERBOT_PROFILE_TOKEN` resolves credentials from `traderbot.profiles.<name>.<service>` namespace, not global `traderbot.<service>`
- Verify `KALSHI_API_KEY` and `KALSHI_API_SECRET` env vars are used as `.env` fallback when keyring is unavailable
- Verify profile data isolation: `profile.base_dir` is used for DB, ChromaDB, and audit paths (not global `~/.traderbot/`)
- Verify no credential values appear in `traderbot auth list-keys` output — only key names are shown
- Verify `traderbot bootstrap --dry-run` does NOT write to keyring, database, or filesystem — only validates and reports
