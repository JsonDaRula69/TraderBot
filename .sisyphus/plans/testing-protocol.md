# Comprehensive E2E Testing Protocol Update

## TL;DR

> **Quick Summary**: Rewrite and expand `tests/TESTING_PROMPT.md` from a phases-0-through-5 static analysis document into a comprehensive end-to-end testing protocol covering installation flow, all 8 phases, Kalshi API spec compliance, OpenClaw gateway integration, Telegram E2E, security deep audit, and real-world context testing. The protocol must be designed to be run repeatedly as development continues.
>
> **Deliverables**:
> - Updated `tests/TESTING_PROMPT.md` with comprehensive E2E testing protocol
> - New sections for installation/config flow, Kalshi API spec compliance, OpenClaw integration, security audit, Telegram E2E, agent decision-making analysis
> - Updated phase references (Phases 5-8 now built, not "pending")
> - Bug class taxonomy additions for security findings (SecretStr, file permissions, demo/prod isolation)
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 3 → Task 8 → Task 12 → Task 15

---

## Context

### Original Request
User wants to update `tests/TESTING_PROMPT.md` to implement a full end-to-end test of the entire TraderBot package. Must test every module and function, starting from installation flow through safe storage of secrets and agent tool calls. Must verify integrations are used to specification (Kalshi API, OpenClaw, security). Must reference `docs/` as source of truth and settle divergences. Must test real-world context. This is documentation update only.

### Interview Summary
**Key Discussions**:
- Real Kalshi demo API calls vs mocks: User chose **real demo API**
- OpenClaw integration depth: User chose **full gateway integration**
- Telegram testing: User chose **full Telegram E2E test**
- SecretStr findings: User chose **P1 bug — must fix**
- Docs divergence: User chose **update TESTING_PROMPT to match code**

**Research Findings**:
- Kalshi API: Full spec at docs.kalshi.com/openapi.yaml, RSA-PSS JWT auth, distinct demo/prod endpoints, ~10 req/sec rate limits
- Security: Plain `str` for credential fields (P1), SQLite without permission constraints, os.getenv without keyring fallback in some paths, no audit log tamper-evidence, hardcoded TEST_API_KEY
- OpenClaw: Workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, HEARTBEAT.md/HEARTBEAT_DATA.md distinction), `isolated agentTurn` vs `systemEvent` cron architectures, skill system YAML frontmatter, Telegram channel via gateway
- Metis gap analysis: Identified 5 critical clarification points about scope boundaries, test environments, Phase 8 status, fix-vs-document decisions, and version discipline

### Metis Review
**Identified Gaps** (addressed):
- Scope creep risk: Clearly delimited as documentation-only update (no test code, no bug fixes)
- Test environment: Real credentials required for Kalshi demo; OpenClaw gateway required for E2E
- Phase 8 status: `simulation/adaptation.py`, `heartbeat.py`, `cron_loops.py` exist — update references
- Fix vs. document: P1 bugs (SecretStr) documented as findings in the protocol, not fixed in this plan
- Version discipline: Commit update with standard version bump per AGENTS.md conventions

---

## Work Objectives

### Core Objective
Rewrite `tests/TESTING_PROMPT.md` as a comprehensive, repeatable E2E testing protocol that covers every module, every function, every integration point, and every security concern — from installation through production readiness.

### Concrete Deliverables
- Updated `tests/TESTING_PROMPT.md` with all new and revised sections

### Definition of Done
- [ ] Every module in `src/traderbot/` has testing coverage specified in TESTING_PROMPT.md
- [ ] All integration points (Kalshi API, OpenClaw, Telegram) have verification checklists
- [ ] Security audit section covers SecretStr, file permissions, keyring, demo/prod isolation, audit tamper-evidence
- [ ] Phase references updated: Phases 5-7 marked as built, Phase 8 partial
- [ ] Bug class taxonomy updated with new security findings
- [ ] Installation/config flow section added with concrete validation steps
- [ ] All acceptance criteria are agent-executable (no "manually verify" or "visually check")

### Must Have
- Installation flow testing (dependencies, API key config, OpenClaw setup)
- Kalshi API spec compliance verification (every endpoint, auth, websocket, rate limits)
- OpenClaw workspace file validation (AGENTS.md, SOUL.md, IDENTITY.md, HEARTBEAT.md, HEARTBEAT_DATA.md)
- OpenClaw gateway integration testing (cron, heartbeat, skill execution, session management)
- Telegram E2E testing (gateway → Telegram → agent → skill call → response)
- Security deep audit (SecretStr, keyring, file permissions, demo/prod isolation, audit trail integrity)
- Agent decision-making analysis (toolkit outputs never contain buy/sell/hold signals)
- Docs vs. code validation updated for all phases
- All phase references updated to match current codebase reality

### Must NOT Have (Guardrails)
- DO NOT modify files in `docs/` without explicit human approval per AGENTS.md
- DO NOT write actual test code — this is documentation update only
- DO NOT attempt penetration testing or exploit vulnerabilities
- DO NOT send real Telegram messages without explicit human gate
- DO NOT make real trades on production Kalshi API
- DO NOT scope-creep into fixing P1 bugs (SecretStr, etc.) — document them as findings
- DO NOT leave "not yet built" markers for modules that actually exist
- DO NOT write vague acceptance criteria ("verify it works" → specify exact command, expected output, pass condition)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, ruff, mypy per pyproject.toml)
- **Automated tests**: Tests-after (this plan updates the testing PROTOCOL document, not test files)
- **Framework**: pytest (existing)

### QA Policy
Every task includes agent-executed QA scenarios that verify the TESTING_PROMPT.md update is correct, complete, and internally consistent.

- **File consistency**: Use `grep` and `read` to verify every module referenced actually exists
- **Phase accuracy**: Use `ls` and `glob` to confirm built modules match phase claims
- **Doc-code alignment**: Cross-reference TESTING_PROMPT.md against `docs/` and source code

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — research and verify current state):
├── Task 1: Audit current TESTING_PROMPT.md against codebase [deep]
├── Task 2: Audit all docs/ files against source code [deep]
└── Task 3: Audit security posture and identify all bug classes [deep]

Wave 2 (New sections — write in parallel):
├── Task 4: Write Phase 0.8 — Installation & Configuration Flow Tests [unspecified-high]
├── Task 5: Write Phase 0.9 — Kalshi API Spec Compliance Tests [unspecified-high]
├── Task 6: Write Phase 3.5 — OpenClaw Gateway Integration Tests [unspecified-high]
├── Task 7: Write Phase 5.5 — Security & Encryption Deep Audit [deep]
└── Task 8: Write Phase 4.5 — Agent Decision-Making Analysis [unspecified-high]

Wave 3 (Update existing sections):
├── Task 9: Update Phase 0 — Architecture Model for current modules [quick]
├── Task 10: Update Phases 2.11-2.14 — Simulation, Self-Learning, News, Adaptation [unspecified-high]
├── Task 11: Update Bug Class Taxonomy with security findings [quick]
└── Task 12: Write Phase 6.5 — Telegram E2E Integration Tests [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review — verify no test code was written [unspecified-high]
├── Task F3: Real QA — run grep/read commands to verify all references exist [unspecified-high]
└── Task F4: Scope fidelity check — verify Only TESTING_PROMPT.md was modified [deep]
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | - | 4, 5, 6, 7, 8, 9, 10, 11 |
| 2 | - | 4, 5, 6, 7, 8, 9, 10, 11 |
| 3 | - | 7, 11 |
| 4 | 1, 2 | 12 |
| 5 | 1, 2 | - |
| 6 | 1, 2 | 12 |
| 7 | 3 | - |
| 8 | 1, 2 | 12 |
| 9 | 1 | - |
| 10 | 1 | - |
| 11 | 3 | - |
| 12 | 4, 6, 8 | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: 3 — T1→`deep`, T2→`deep`, T3→`deep`
- **Wave 2**: 5 — T4→`unspecified-high`, T5→`unspecified-high`, T6→`unspecified-high`, T7→`deep`, T8→`unspecified-high`
- **Wave 3**: 4 — T9→`quick`, T10→`unspecified-high`, T11→`quick`, T12→`unspecified-high`
- **FINAL**: 4 — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. Audit Current TESTING_PROMPT.md Against Codebase

  **What to do**:
  - Read every line of `tests/TESTING_PROMPT.md` (1156 lines)
  - For every module, function, and file referenced, verify it actually exists in `src/traderbot/`
  - Identify all "not yet built" / "pending" markers and cross-reference against actual files in `src/traderbot/`
  - Specifically verify: simulation/ (Phase 5), news/ (Phase 7), simulation/adaptation.py + heartbeat.py + cron_loops.py (Phase 8)
  - Document every stale reference, outdated phase marker, and missing module coverage
  - Categorize each finding: stale phase reference, missing test section, outdated bug class, incorrect function name

  **Must NOT do**:
  - Do not modify TESTING_PROMPT.md yet — this is an audit only
  - Do not modify any `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Tasks 4, 5, 6, 7, 8, 9, 10, 11
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:1-1156` — Full document to audit
  - `ROADMAP_PROGRESS.md:1-199` — Current phase status claims

  **API/Type References**:
  - `src/traderbot/` directory listing — actual modules to cross-reference
  - `VERSION` file — current version (0.08.01) to verify against TESTING_PROMPT version references

  **WHY Each Reference Matters**:
  - TESTING_PROMPT.md contains phase claims that may be outdated (e.g., "Phase 5 not yet built" when simulation/ exists)
  - ROADMAP_PROGRESS.md tracks phase status but may itself be stale — verify both against actual code

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All module references in TESTING_PROMPT.md point to files that exist
    Tool: Bash (grep + ls)
    Preconditions: TESTING_PROMPT.md read in full
    Steps:
      1. Extract every file path referenced in TESTING_PROMPT.md (e.g., `risk/limits.py`, `simulation/engine.py`)
      2. For each path, prepend `src/traderbot/` and check existence with `ls`
      3. Count paths that exist vs. paths that don't
    Expected Result: 100% of referenced modules exist; any that don't are flagged as P2 findings
    Failure Indicators: Referenced file returns "No such file or directory"
    Evidence: .sisyphus/evidence/task-1-module-ref-audit.txt

  Scenario: All "not yet built" markers are accurate
    Tool: Bash (grep)
    Preconditions: TESTING_PROMPT.md read in full
    Steps:
      1. grep -n "not yet built\|NOT STARTED\|pending\|Phase.*not" tests/TESTING_PROMPT.md
      2. For each hit, verify the corresponding module does NOT exist in src/traderbot/
      3. Flag any "not yet built" markers where the module actually exists
    Expected Result: All "not yet built" markers match reality; any mismatches are P1 findings
    Failure Indicators: "not yet built" marker exists but `ls src/traderbot/news/classifier.py` succeeds
    Evidence: .sisyphus/evidence/task-1-stale-phase-markers.txt
  ```

  **Commit**: NO (audit only)

- [ ] 2. Audit All docs/ Files Against Source Code

  **What to do**:
  - Read every file in `docs/`: architecture.md, kalshi.md, openclaw-integration.md, risk.md, simulation.md, news-sentiment.md, self-learning.md, product-roadmap.md, research.md, decisions/
  - For each documented claim (module names, function signatures, CLI commands, thresholds, data schemas), verify against actual source code
  - Specifically verify:
    - `docs/kalshi.md`: Every endpoint documented matches `kalshi/client.py`, `kalshi/markets.py`, `kalshi/trading.py`, `kalshi/history.py`
    - `docs/risk.md`: HARD_LIMITS values match `risk/limits.py`, circuit breaker thresholds match `risk/circuit_breaker.py`
    - `docs/architecture.md`: Module dependency rules match actual imports
    - `docs/openclaw-integration.md`: SKILL.md commands match `cli.py`, cron payloads match `cron_loops.py`
    - `docs/simulation.md`: Module names match `simulation/` directory contents
    - `docs/news-sentiment.md`: Module names match `news/` directory contents
    - `docs/self-learning.md`: Module names match `db/learnings.py`, `learning.py`, `wal.py`
  - Document every discrepancy with: doc file, line, doc claim, code reality, severity, recommended action (fix doc or fix code)
  - Per AGENTS.md: NEVER edit docs/ without explicit human approval — just document discrepancies

  **Must NOT do**:
  - Do not modify any `docs/` files
  - Do not assume docs are inaccurate — verify every claim against code

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 4, 5, 6, 7, 8, 9, 10, 11
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `docs/architecture.md` — Module dependency rules, component map
  - `docs/kalshi.md` — API endpoint documentation
  - `docs/risk.md` — Risk limits, circuit breaker thresholds, audit schema
  - `docs/openclaw-integration.md` — SKILL.md commands, cron architectures
  - `docs/simulation.md` — Backtest engine modules
  - `docs/news-sentiment.md` — News pipeline modules
  - `docs/self-learning.md` — Bayesian adaptation, learnings DB
  - `docs/product-roadmap.md` — Phase implementation timeline

  **API/Type References**:
  - `src/traderbot/risk/limits.py` — Actual HARD_LIMITS values
  - `src/traderbot/risk/circuit_breaker.py` — Actual breaker thresholds
  - `src/traderbot/cli.py` — Actual CLI commands
  - `src/traderbot/cron_loops.py` — Actual cron definitions
  - `skills/traderbot/SKILL.md` — Actual skill definition

  **WHY Each Reference Matters**:
  - The testing protocol references docs/ as source of truth — if docs are wrong, the protocol will verify against incorrect expectations
  - Risk doc discrepancies (wrong thresholds, wrong types) could be P1 security issues
  - Kalshi doc discrepancies could mean we're not using the API correctly

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Risk limits in docs/risk.md match actual code
    Tool: Bash (grep + python)
    Preconditions: docs/risk.md and risk/limits.py both read
    Steps:
      1. Extract HARD_LIMITS values from docs/risk.md
      2. Run `python3 -c "from traderbot.risk.limits import HARD_LIMITS; print(dict(HARD_LIMITS))"` to get actual values
      3. Compare every key-value pair
    Expected Result: 100% match between documented and actual values
    Failure Indicators: Any value differs — flag as P1 if financial threshold differs, P3 if naming differs
    Evidence: .sisyphus/evidence/task-2-risk-limits-comparison.txt

  Scenario: CLI commands in SKILL.md match cli.py
    Tool: Bash (grep)
    Preconditions: SKILL.md and cli.py both read
    Steps:
      1. Extract command names from SKILL.md table
      2. grep for `@app.command()` or `def ` in cli.py
      3. Compare lists
    Expected Result: Every SKILL.md command corresponds to a cli.py command
    Failure Indicators: SKILL.md references command not in cli.py
    Evidence: .sisyphus/evidence/task-2-skill-cli-comparison.txt
  ```

  **Commit**: NO (audit only)

- [ ] 3. Audit Security Posture and Identify All Bug Classes

  **What to do**:
  - Comprehensive security audit of `src/traderbot/` and `tests/`
  - Specifically check:
    1. **SecretStr**: Grep all Pydantic models (`class.*BaseModel`) for credential-related fields (`api_key`, `token`, `secret`, `password`, `private_key`, `credentials`) that use `str` instead of `SecretStr`
    2. **Secret exposure**: Grep for `print(`, `logger.`, `rich.print` within proximity of secret variable names
    3. **Environment variables**: Grep for `os.getenv`, `os.environ` — verify each has keyring fallback or is a non-secret config value
    4. **File permissions**: Grep for `open(` in db/ and log-related code — verify sensitive files use `0o600` permissions
    5. **Demo vs production isolation**: Verify `KALSHI_DEMO` env var properly switches endpoints; verify no demo credentials can reach production
    6. **Audit trail integrity**: Verify JSONL logs are append-only; verify no code path deletes or overwrites entries
    7. **Git-tracked secrets**: Run `git ls-files .env` and verify no credential files are tracked
    8. **Hardcoded test values**: Grep for `TEST_`, `FAKE_`, `MOCK_` patterns in src/ (not tests/) — these are acceptable in tests/ but P1 in src/
    9. **model_dump() on credential models**: Verify no code calls `model_dump()` on models containing credentials without `exclude={"field_name"}`
  - For each finding, extract a bug class per the existing taxonomy format (no line numbers, no function names, abstract pattern + custom check)
  - All findings feed into Task 7 (security section) and Task 11 (bug class taxonomy)

  **Must NOT do**:
  - Do not attempt to exploit any vulnerability found
  - Do not fix any bugs — document only
  - Do not modify any files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Tasks 7, 11
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:137-180` — Existing bug class taxonomy (format to follow)
  - `ROADMAP_PROGRESS.md:173-186` — Bug class taxonomy in roadmap

  **API/Type References**:
  - `src/traderbot/auth.py` — Keyring-based auth management
  - `src/traderbot/kalshi/config.py` — Config and environment handling
  - `src/traderbot/kalshi/client.py` — API client with credential handling
  - `src/traderbot/db/__init__.py` — SQLite connection with potential permission issues
  - `src/traderbot/risk/audit.py` — Audit trail format and integrity

  **WHY Each Reference Matters**:
  - `auth.py` uses keyring — verify it's the ONLY path for credential access, no raw os.getenv fallback
  - `client.py` handles API keys — verify they're never logged or serialized
  - `db/__init__.py` creates SQLite files — verify permissions
  - `audit.py` writes JSONL — verify append-only and no deletion paths

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No credential Pydantic model uses plain str instead of SecretStr
    Tool: Bash (grep + python)
    Preconditions: All Pydantic models in src/traderbot/ identified
    Steps:
      1. grep -rn 'class.*BaseModel' src/traderbot/ to find all models
      2. For each model, grep for fields named api_key, token, secret, password, private_key, credentials
      3. For each such field, verify it uses SecretStr type annotation, not str
      4. Count and list violations
    Expected Result: Zero credential fields using plain str; any violations are P1 findings
    Failure Indicators: api_key: str found in any model
    Evidence: .sisyphus/evidence/task-3-secretstr-audit.txt

  Scenario: No secrets appear in print/logger output paths
    Tool: Bash (grep)
    Preconditions: All source and test files scanned
    Steps:
      1. grep -rn 'print\(|logger\.\(info\|debug\|warning\|error\)' src/traderbot/ with context lines
      2. For each match, check surrounding context (3 lines) for secret variable names
      3. Count and list exposures
    Expected Result: Zero print/logger calls that include secret data; any found are P0
    Failure Indicators: logger.info(f"API key: {api_key}") found
    Evidence: .sisyphus/evidence/task-3-secret-exposure.txt

  Scenario: Demo mode properly isolates from production endpoints
    Tool: Bash (grep + python)
    Preconditions: Demo/production URL constants identified
    Steps:
      1. grep -rn 'demo-api\|api.kalshi' src/traderbot/ to find all URL references
      2. Verify demo URL and production URL are in different code paths
      3. Verify no code path can use demo credentials against production URL
    Expected Result: Demo and production endpoints are mutually exclusive based on KALSHI_DEMO flag
    Failure Indicators: Production URL reachable when KALSHI_DEMO=true
    Evidence: .sisyphus/evidence/task-3-demo-isolation.txt
  ```

  **Commit**: NO (audit only)

  **Commit**: NO (audit only)

- [ ] 4. Write Phase 0.8 — Installation & Configuration Flow Tests

  **What to do**:
  - Add a new section `## PHASE 0.8: INSTALLATION & CONFIGURATION FLOW` to TESTING_PROMPT.md
  - This section tests the full installation flow from zero to operational:
    1. **Dependency installation**: Verify `pip install traderbot` (or `uv pip install -e .`) succeeds, all dependencies resolve
    2. **Python version check**: Verify Python 3.12+ is required and enforced
    3. **API key configuration**: Verify `traderbot auth` command sets up keyring, that `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY` are stored securely via keyring (not in plaintext env files)
    4. **Demo mode configuration**: Verify `KALSHI_DEMO=true` switches to demo endpoint, verify demo mode works without production credentials
    5. **OpenClaw workspace setup**: Verify `.openclaw/workspace/` contains required files (AGENTS.md, SOUL.md, IDENTITY.md, TOOLS.md, USER.md, HEARTBEAT.md, HEARTBEAT_DATA.md, SESSION-STATE.md, .learnings/)
    6. **Skill registration**: Verify `skills/traderbot/SKILL.md` has correct YAML frontmatter, command list matches `cli.py`, env requirements match reality
    7. **Cron configuration**: Verify `src/traderbot/cron_loops.py` defines three loops (Decision, Heartbeat, News) with correct schedules and JSON payloads matching OpenClaw spec
    8. **Configuration validation smoke test**: Verify `traderbot scan --help` returns help text, `traderbot --version` returns correct version from VERSION file
  - Each check must have concrete executable commands and expected outputs
  - Include a subsection on "Environment Isolation" — verify install tests don't mutate dev environment

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Wave 1 completes)
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7, 8)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:1-50` — Existing section structure and subagent usage guidelines format
  - `tests/TESTING_PROMPT.md:631-681` — CLI test section format to follow

  **API/Type References**:
  - `src/traderbot/cli.py` — CLI commands to verify against
  - `src/traderbot/auth.py` — Auth management and keyring integration
  - `src/traderbot/kalshi/config.py` — Kalshi configuration and demo mode
  - `src/traderbot/cron_loops.py` — Cron loop definitions
  - `skills/traderbot/SKILL.md` — Skill definition with YAML frontmatter
  - `.openclaw/workspace/` — All workspace files (AGENTS.md, SOUL.md, etc.)
  - `pyproject.toml` — Dependency list and Python version requirement
  - `VERSION` file — Current version string

  **WHY Each Reference Matters**:
  - Existing TESTING_PROMPT format must be followed for consistency
  - CLI test section provides the pattern for command-level verification
  - auth.py and config.py are the key files for configuration flow testing
  - SKILL.md and workspace files define the OpenClaw integration contract

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: New section follows TESTING_PROMPT.md format conventions
    Tool: Bash (grep)
    Preconditions: TESTING_PROMPT.md updated with Phase 0.8
    Steps:
      1. Verify section header format matches existing (## PHASE 0.8: ...)
      2. Verify each subsection has numbered checklist items
      3. Verify each item has concrete verification command
    Expected Result: Section format matches Phase 1-5 conventions exactly
    Failure Indicators: Section header missing "PHASE" prefix, no grep-able verification commands
    Evidence: .sisyphus/evidence/task-4-format-check.txt

  Scenario: Every referenced file and command exists in the codebase
    Tool: Bash (ls + python)
    Preconditions: Phase 0.8 section written
    Steps:
      1. Extract every file path referenced in Phase 0.8
      2. Run `ls` for each path to verify existence
      3. Extract every CLI command referenced (e.g., `traderbot scan --help`)
      4. Verify each command appears in cli.py function definitions
    Expected Result: 100% of referenced files exist; 100% of commands have matching CLI definitions
    Failure Indicators: Referenced file does not exist, or command not found in cli.py
    Evidence: .sisyphus/evidence/task-4-reference-validation.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 0.8 installation and configuration flow tests`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 5. Write Phase 0.9 — Kalshi API Spec Compliance Tests

  **What to do**:
  - Add a new section `## PHASE 0.9: KALSHI API SPEC COMPLIANCE` to TESTING_PROMPT.md
  - This section verifies our Kalshi integration matches the official API specification:
    1. **Authentication**: RSA-PSS JWT signing, `X-Kalshi-Timestamp` (UTC nanoseconds), `X-Kalshi-Signature` (base64), `Authorization: Bearer <JWT>`. Verify our `auth.py` and `kalshi/client.py` implement all headers correctly
    2. **All REST endpoints**: For each endpoint in `docs/kalshi.md`, verify `kalshi/client.py`, `kalshi/markets.py`, `kalshi/trading.py`, `kalshi/history.py` implement the correct HTTP method, path, query params, request body, and response shape. Cross-reference with OpenAPI spec at `docs.kalshi.com/openapi.yaml`
    3. **WebSocket protocol**: Verify `kalshi/websocket.py` uses correct URL (`wss://api.kalshi.com/v2`), auth headers during handshake, subscription message format (`{"channels": ["market-ticker", ...]}`), and keep-alive ping/pong every 30s
    4. **Rate limits**: Verify our client implements backoff on 429 with max 3 retries
    5. **Error handling**: Verify all API response errors are caught and properly wrapped in our error types
    6. **Demo vs production**: Verify `KALSHI_DEMO=true` switches endpoint to `demo-api.kalshi.co`, and that demo credentials never reach production endpoints
    7. **Historical data**: Verify `kalshi/history.py` fetches cutoffs before querying historical data, uses correct pagination
    8. **Pagination**: Verify all paginated endpoints handle cursor-based pagination correctly
  - Each check must reference specific line numbers in our code and specific sections in the Kalshi docs

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Wave 1 completes)
  - **Parallel Group**: Wave 2 (with Tasks 4, 6, 7, 8)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:462-492` — KalshiClient test section format
  - `tests/TESTING_PROMPT.md:493-520` — WebSocket test section format

  **API/Type References**:
  - `docs/kalshi.md` — Our Kalshi API documentation (source of truth)
  - `src/traderbot/kalshi/client.py` — API client implementation
  - `src/traderbot/kalshi/markets.py` — Market data methods
  - `src/traderbot/kalshi/trading.py` — Order placement methods
  - `src/traderbot/kalshi/history.py` — Historical data methods
  - `src/traderbot/kalshi/websocket.py` — WebSocket implementation
  - `src/traderbot/kalshi/demo.py` — Demo adapter
  - `src/traderbot/kalshi/config.py` — Configuration
  - `src/traderbot/auth.py` — Authentication

  **External References**:
  - Kalshi API docs: `https://docs.kalshi.com` — Official API specification
  - Kalshi OpenAPI spec: `https://docs.kalshi.com/openapi.yaml` — Machine-readable endpoint definitions
  - Kalshi SDK: `kalshi_python_async` — Official SDK for comparison

  **WHY Each Reference Matters**:
  - Our docs/kalshi.md documents our understanding of the API — we must verify our code matches both our docs AND the official spec
  - Each kalshi/ module must be verified against the corresponding API endpoints
  - The OpenAPI spec is the canonical reference for endpoint shapes

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Every Kalshi endpoint in docs/kalshi.md has a corresponding verification checklist item
    Tool: Bash (grep)
    Preconditions: Phase 0.9 section written
    Steps:
      1. Extract all endpoint references from docs/kalshi.md (e.g., GET /markets, POST /order)
      2. Extract all endpoint checklist items from Phase 0.9
      3. Compare lists — every documented endpoint must have a checklist item
    Expected Result: 100% coverage of documented endpoints
    Failure Indicators: Endpoint in docs/kalshi.md has no corresponding checklist item
    Evidence: .sisyphus/evidence/task-5-endpoint-coverage.txt

  Scenario: Authentication implementation matches API spec
    Tool: Bash (grep + read)
    Preconditions: auth.py and kalshi/client.py read
    Steps:
      1. Verify auth.py implements RSA-PSS signing
      2. Verify client.py sets X-Kalshi-Timestamp in nanoseconds
      3. Verify client.py sets X-Kalshi-Signature as base64
      4. Verify client.py sets Authorization as Bearer JWT
    Expected Result: All three auth headers implemented correctly per Kalshi spec
    Failure Indicators: Missing header, wrong format, or wrong timestamp precision
    Evidence: .sisyphus/evidence/task-5-auth-spec-compliance.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 0.9 Kalshi API spec compliance tests`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 6. Write Phase 3.5 — OpenClaw Gateway Integration Tests

  **What to do**:
  - Add a new section `## PHASE 3.5: OPENCLAW GATEWAY INTEGRATION` to TESTING_PROMPT.md
  - This section verifies our OpenClaw integration matches the framework specification:
    1. **Workspace file validation**: Verify each workspace file follows OpenClaw expected format:
       - `AGENTS.md`: Has session startup, memory, trading rules, red lines sections
       - `SOUL.md`: Has core identity, principles, boundaries sections
       - `IDENTITY.md`: Has name, role, emoji, vibe fields
       - `HEARTBEAT.md`: Has tasks with name, interval, prompt blocks; has general instructions
       - `HEARTBEAT_DATA.md`: Written by `traderbot heartbeat`, not by agent (key distinction)
       - `SESSION-STATE.md`: Has WAL protocol content
       - `.learnings/LEARNINGS.md`, `ERRORS.md`, `FEATURE_REQUESTS.md`: Follow self-improving agent pattern
    2. **SKILL.md format validation**: Verify YAML frontmatter has required fields (name, description, metadata.openclaw.requires.env, metadata.openclaw.requires.bins, metadata.openclaw.primaryEnv). Verify command table matches cli.py. Verify trigger phrases map to commands. Verify cron architecture section matches cron_loops.py
    3. **Cron architecture validation**: Verify three cron loops defined with correct JSON payloads:
       - Decision Loop: `*/5 9-15 * * 1-5`, `sessionTarget: "isolated"`, `kind: "agentTurn"`
       - Heartbeat Loop: `0 */6 * * *`, `sessionTarget: "isolated"`, `kind: "agentTurn"`
       - News Loop: event-driven, `sessionTarget: "main"`, `kind: "systemEvent"`, `impact_threshold: 0.7`
    4. **WAL protocol verification**: Verify SESSION-STATE.md is written BEFORE execution (write-ahead log), contains action/reason/signal/risk/params/confidence/status, and is reconciled on restart
    5. **Skill execution flow**: Verify TraderBot skill can be invoked via OpenClaw gateway: user sends message → gateway routes to agent → agent calls `traderbot scan` → output returned to user
    6. **Session management**: Verify per-channel-peer session scoping works, idle resets clear state correctly
    7. **Heartbeat execution**: Verify `traderbot heartbeat --json` produces valid JSON output, writes to HEARTBEAT_DATA.md, and follows the 7-step review cycle

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Wave 1 completes)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 7, 8)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:753-805` — Integration test section format
  - `.openclaw/workspace/AGENTS.md` — Current workspace file to validate
  - `.openclaw/workspace/SOUL.md` — Current soul file to validate
  - `.openclaw/workspace/IDENTITY.md` — Current identity file to validate
  - `.openclaw/workspace/HEARTBEAT.md` — Current heartbeat checklist
  - `.openclaw/workspace/HEARTBEAT_DATA.md` — Data output file

  **API/Type References**:
  - `skills/traderbot/SKILL.md` — OpenClaw skill definition
  - `src/traderbot/cron_loops.py` — Cron loop definitions
  - `src/traderbot/cli.py` — CLI command definitions (must match SKILL.md triggers)
  - `src/traderbot/heartbeat.py` — Heartbeat implementation
  - `src/traderbot/wal.py` — WAL protocol implementation

  **External References**:
  - OpenClaw docs: `https://docs.openclaw.ai/concepts/agent` — Agent workspace file formats
  - OpenClaw docs: `https://docs.openclaw.ai/gateway/configuration` — Gateway config reference
  - OpenClaw docs: `https://docs.openclaw.ai/tools/skills` — Skill system documentation
  - OpenClaw docs: `https://docs.openclaw.ai/automation/cron-jobs` — Cron job format

  **WHY Each Reference Matters**:
  - Workspace files define the agent's operating rules and must match OpenClaw's expected format
  - SKILL.md is the contract between TraderBot and OpenClaw — must be valid
  - Cron loops define autonomous behavior — must match OpenClaw cron spec
  - External docs provide the canonical format specifications

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Every workspace file section mentioned in OpenClaw docs exists in our workspace
    Tool: Bash (grep)
    Preconditions: All .openclaw/workspace/ files read
    Steps:
      1. For each OpenClaw-mandated section (AGENTS.md sections, SOUL.md sections, IDENTITY.md fields, HEARTBEAT.md tasks), grep for its presence
      2. Compare HEARTBEAT.md task structure against OpenClaw task format (name, interval, prompt)
    Expected Result: Every mandated section found; HEARTBEAT.md has valid task format
    Failure Indicators: Missing section or malformed task format
    Evidence: .sisyphus/evidence/task-6-workspace-validation.txt

  Scenario: SKILL.md commands match cli.py one-to-one
    Tool: Bash (grep)
    Preconditions: SKILL.md and cli.py both read
    Steps:
      1. Extract command names from SKILL.md command table
      2. Extract @app.command() decorated functions from cli.py
      3. Compare sets — every SKILL.md command must exist in cli.py
    Expected Result: 100% command match between SKILL.md and cli.py
    Failure Indicators: Command listed in SKILL.md but not found in cli.py
    Evidence: .sisyphus/evidence/task-6-skill-command-match.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 3.5 OpenClaw gateway integration tests`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 7. Write Phase 5.5 — Security & Encryption Deep Audit Section

  **What to do**:
  - Add a new section `## PHASE 5.5: SECURITY & ENCRYPTION DEEP AUDIT` to TESTING_PROMPT.md
  - This section is one of the most critical — it verifies that no secrets are exposed in plaintext and that the highest level of security is implemented:
    1. **SecretStr enforcement**: Every Pydantic model field that holds credentials (api_key, token, secret, password, private_key) MUST use `SecretStr` not `str`. Grep all models and verify.
    2. **Keyring usage**: All credential storage MUST go through `keyring`. Verify `auth.py` is the sole credential accessor and that no code path reads `KALSHI_PRIVATE_KEY` from environment without going through keyring.
    3. **model_dump() safety**: Verify no code calls `model_dump()` on models containing SecretStr fields without `exclude` for secret fields. Verify `model_dump()` output never contains plaintext secrets.
    4. **Logging safety**: Grep ALL logger and print calls. Verify no secret data is ever included in log output. Verify SecretStr fields are never serialized to logs.
    5. **File permissions**: Verify SQLite database files are created with `0o600` permissions. Verify PEM key files are read with restricted permissions.
    6. **Demo/production isolation**: Verify `KALSHI_DEMO=true` is the SOLE mechanism for switching endpoints. Verify no code path can send real credentials to demo endpoint or demo credentials to production.
    7. **Secrets in git**: Run `git ls-files` to verify no `.env`, `credentials.json`, `*.pem`, or `*.key` files are tracked. Verify `.gitignore` includes these patterns.
    8. **Audit trail security**: Verify JSONL audit logs are append-only. Verify no code path deletes or modifies audit entries. Verify audit logs contain no secret data.
    9. **Jailbreak resistance**: Verify SOUL.md and AGENTS.md red lines are enforced. Circuit breaker cannot be disabled. Risk limits cannot be overridden. No code path allows `halt --force` without human approval.
    10. **Dependency security**: Review `pyproject.toml` dependencies for known vulnerabilities. Verify no pinned versions with known CVEs.
  - Convert all findings from Task 3 into formal bug class taxonomy entries and testing checklists

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not modify source code — document security findings only
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Wave 1 completes)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 8)
  - **Blocks**: Task 11
  - **Blocked By**: Task 3

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:296-310` — Risk import audit section format
  - `tests/TESTING_PROMPT.md:319-333` — Monetary precision audit format
  - `tests/TESTING_PROMPT.md:137-180` — Bug class taxonomy format

  **API/Type References**:
  - Task 3 output — All security findings from the audit
  - `src/traderbot/auth.py` — Credential handling
  - `src/traderbot/kalshi/config.py` — Configuration and environment variables
  - `src/traderbot/kalshi/client.py` — API client
  - `src/traderbot/risk/circuit_breaker.py` — Circuit breaker immutability
  - `src/traderbot/risk/limits.py` — Risk limits immutability
  - `src/traderbot/risk/audit.py` — Audit trail
  - `src/traderbot/db/__init__.py` — Database connection and file creation
  - `.gitignore` — Patterns for secret file exclusion
  - `.openclaw/workspace/SOUL.md` — Agent boundaries and red lines
  - `.openclaw/workspace/AGENTS.md` — Trading rules and immutable constraints

  **WHY Each Reference Matters**:
  - auth.py and config.py are the primary credential access points — must be locked down
  - Circuit breaker and risk limits must be provably immutable — no override paths
  - SOUL.md and AGENTS.md define behavioral constraints — must be unbreachable
  - Task 3 output provides the raw findings that must be formalized

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Security section covers all 10 checklist areas
    Tool: Bash (grep)
    Preconditions: Phase 5.5 section written
    Steps:
      1. grep for each of the 10 checklist area titles in the new section
      2. Count matches
    Expected Result: All 10 areas present as subsection headers or checklist items
    Failure Indicators: Missing area (e.g., no "Jailbreak resistance" subsection)
    Evidence: .sisyphus/evidence/task-7-coverage-check.txt

  Scenario: Every security finding from Task 3 has a corresponding checklist item
    Tool: Manual review
    Preconditions: Task 3 output and Phase 5.5 section both available
    Steps:
      1. List all findings from Task 3 audit
      2. For each finding, locate a corresponding verification step in Phase 5.5
    Expected Result: Every Task 3 finding has a Phase 5.5 checklist item
    Failure Indicators: Finding from Task 3 not addressed in Phase 5.5
    Evidence: .sisyphus/evidence/task-7-finding-coverage.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 5.5 security and encryption deep audit`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 8. Write Phase 4.5 — Agent Decision-Making Analysis Tests

  **What to do**:
  - Add a new section `## PHASE 4.5: AGENT DECCISION-MAKING ANALYSIS` to TESTING_PROMPT.md
  - This section verifies the toolkit/agent boundary — the toolkit NEVER decides strategy, only computes and enforces:
    1. **Toolkit/agent boundary**: Verify no function in `risk/`, `kalshi/`, `db/`, or `analysis/` returns a buy/sell/hold recommendation. Every return value must be a numerical score, a pass/fail decision, or structured data — never a trading direction.
    2. **Signal output verification**: Verify `analysis/signals.py` outputs are direction+confidence tuples (e.g., "bullish", 0.7) NOT trading orders. Verify `combine_signals()` returns a CombinedSignal with `edge_cents` as int and `confidence` in [0,1].
    3. **Risk module immutability**: Verify `HARD_LIMITS` is frozen (MappingProxyType or equivalent). Verify no code path in `risk/` reads from config files or environment variables. Verify circuit breaker state cannot be cleared by code (only human).
    4. **Decision flow verification**: Trace a complete decision from `cli.py trade` through: analysis → signal → risk gate → Kelly sizing → audit log. Verify the agent (LLM) receives the signal output and makes the call, NOT the toolkit.
    5. **OpenClaw SKILL.md trigger verification**: Verify every trigger phrase in SKILL.md maps to a CLI command that produces output only (no autonomous execution beyond risk-gated trade placement). Verify the Decision Loop's autonomous trading is explicitly bounded by risk guards.
    6. **Heartbeat output verification**: Verify `traderbot heartbeat --json` output contains only metrics and adaptation data, never trading recommendations.
    7. **News/sentiment output verification**: Verify news pipeline outputs are classification scores and sentiment values, never buy/sell signals.

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Wave 1 completes)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 7)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:79-86` — Existing toolkit/agent boundary rule
  - `tests/TESTING_PROMPT.md:523-551` — Risk limit test format

  **API/Type References**:
  - `src/traderbot/analysis/signals.py` — Signal combining and generation
  - `src/traderbot/risk/__init__.py` — Risk gate (evaluate_trade)
  - `src/traderbot/risk/limits.py` — HARD_LIMITS immutability
  - `src/traderbot/risk/circuit_breaker.py` — Circuit breaker state management
  - `src/traderbot/risk/sizing.py` — Kelly criterion sizing
  - `src/traderbot/risk/audit.py` — Audit trail
  - `src/traderbot/cli.py` — CLI decision flow
  - `src/traderbot/heartbeat.py` — Heartbeat output format
  - `src/traderbot/news/classifier.py` — News classification output
  - `src/traderbot/news/sentiment_scorer.py` — Sentiment scoring output

  **WHY Each Reference Matters**:
  - CRITICAL ARCHITECTURE RULE: risk/ must never import from analysis/ or news/
  - signals.py is the boundary — must verify it outputs direction+confidence, not orders
  - heartbeat.py and news/sentiment must also respect the compute-only boundary

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No function in risk/, kalshi/, db/, analysis/ returns buy/sell/hold
    Tool: Bash (grep)
    Preconditions: All relevant source files scanned
    Steps:
      1. grep -rn 'return.*buy\|return.*sell\|return.*hold\|return.*recommend\|return.*should' src/traderbot/risk/ src/traderbot/kalshi/ src/traderbot/db/ src/traderbot/analysis/
      2. For each match, verify context — is this a trading signal or a data value?
      3. Count violations
    Expected Result: Zero functions return buy/sell/hold/recommend/should trading signals
    Failure Indicators: Function returns "buy" or "sell" as a recommendation
    Evidence: .sisyphus/evidence/task-8-boundary-check.txt

  Scenario: analyze_signals output is direction+confidence, not a trading order
    Tool: Bash (grep + python)
    Preconditions: signals.py read and analyzed
    Steps:
      1. Verify CombinedSignal model has field types: direction (str enum), confidence (float [0,1]), edge_cents (int)
      2. Verify generate_signal() return type annotation
      3. Verify no output field contains "buy", "sell", or "hold" as a recommendation
    Expected Result: CombinedSignal has direction, confidence, edge_cents — no order fields
    Failure Indicators: CombinedSignal contains side, order_type, or quantity fields
    Evidence: .sisyphus/evidence/task-8-signal-format.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 4.5 agent decision-making analysis tests`
  - Files: `tests/TESTING_PROMPT.md`

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add Phase 4.5 agent decision-making analysis tests`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 9. Update Phase 0 — Architecture Model for Current Modules

  **What to do**:
  - Update the Phase 0 section of TESTING_PROMPT.md to reflect current codebase reality:
    1. **Module Dependency Map (0.1)**: Update to include `news/`, `simulation/` (adaptation, paper_trader, profiles, data_loader, performance), `learning.py`, `wal.py`, `heartbeat.py`, `cron_loops.py`, `auth.py`, `kalshi/config.py`, `kalshi/trading.py`
    2. **Type and Variable Namespace Map (0.2)**: Add all new Pydantic models from news, simulation, learning, and auth modules
    3. **Function and Import Namespace Map (0.3)**: Add all new public functions from the new modules
    4. **Async/Sync Boundary Audit (0.4)**: Include `news/` async pipeline, `simulation/` sync computation, `kalshi/trading.py` async operations
    5. **Architecture Diagram (0.5)**: Update to show all 8 phases and their dependencies
    6. **Bug Class Taxonomy (0.6)**: Add entries from Task 3 security findings (SecretStr, file permissions, demo isolation, audit trail tampering, hardcoded test values)
    7. **Documentation vs Code Validation (0.7)**: Update the validation checklist table to include all new docs and modules. Use findings from Task 2 to populate the discrepancy table. Remove stale "not yet built" references
  - Critical: verify that all "Verify" statements reference files that actually exist

  **Must NOT do**:
  - Do not modify `docs/` files — only update TESTING_PROMPT.md
  - Do not add "not yet built" markers for modules that actually exist

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs Task 1 results)
  - **Parallel Group**: Wave 3 (with Tasks 10, 11, 12)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:53-261` — Existing Phase 0 content to update

  **API/Type References**:
  - `ROADMAP_PROGRESS.md` — Current phase status (Phase 5-7 complete, Phase 8 partial)
  - `src/traderbot/` directory listing — All actual modules
  - Task 1 output — Stale reference findings
  - Task 2 output — Docs vs. code discrepancies

  **WHY Each Reference Matters**:
  - Phase 0 is the foundation for all subsequent testing — outdated module maps cause cascading failures
  - Task 1 and Task 2 outputs tell us exactly what needs updating

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Phase 0 module map includes all existing modules
    Tool: Bash (ls + grep)
    Preconditions: Updated TESTING_PROMPT.md
    Steps:
      1. ls src/traderbot/ to get actual module list
      2. grep for each module name in the updated Phase 0.1 section
      3. Compare lists
    Expected Result: Every directory in src/traderbot/ is referenced in Phase 0.1
    Failure Indicators: Module exists in src/ but not referenced in TESTING_PROMPT
    Evidence: .sisyphus/evidence/task-9-phase0-coverage.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): update Phase 0 architecture model for current modules`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 10. Update Phases 2.11-2.14 — Simulation, Self-Learning, News, Adaptation

  **What to do**:
  - Update existing test pattern sections (§2.11-§2.14) in TESTING_PROMPT.md to reflect that these phases ARE NOW BUILT:
    1. **§2.11 Simulation Tests**: Verify all test patterns reference actual module names (`engine.py`, `data_loader.py`, `models.py`, `paper_trader.py`, `performance.py`, `profiles.py`). Verify StrategyProfile model exists. Verify backtest CLI commands exist. Remove any "not yet built" language.
    2. **§2.12 Self-Learning Tests**: Verify all patterns reference `db/learnings.py`, `learning.py`, `wal.py`. Verify pattern promotion, WAL protocol, feature request, and degradation logging tests match actual implementation.
    3. **§2.13 News/Sentiment Tests**: Verify all patterns reference `news/sources.py`, `news/classifier.py`, `news/sentiment_scorer.py`, `news/impact_assessor.py`, `news/models.py`, `news/embeddings.py`. Verify source aggregation, classifier, sentiment scoring, and impact assessment tests match actual implementation.
    4. **§2.14 Adaptation Tests**: Verify patterns reference `simulation/adaptation.py`, `heartbeat.py`, `cron_loops.py`. Verify Bayesian update tests, guardrails tests, heartbeat tests, and cron architecture tests match actual implementation.
  - For each section, verify every function name and module reference actually exists in the codebase

  **Must NOT do**:
  - Do not modify `docs/` files
  - Do not add new test sections — only update existing §2.11-§2.14

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs Task 1 results)
  - **Parallel Group**: Wave 3 (with Tasks 9, 11, 12)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:1003-1050` — §2.11 Simulation test patterns
  - `tests/TESTING_PROMPT.md:1041-1063` — §2.12 Self-Learning test patterns
  - `tests/TESTING_PROMPT.md:1065-1092` — §2.13 News/Sentiment test patterns
  - `tests/TESTING_PROMPT.md:1094-1156` — §2.14 Adaptation test patterns

  **API/Type References**:
  - `src/traderbot/simulation/` — All simulation modules (engine, data_loader, models, paper_trader, performance, profiles, adaptation)
  - `src/traderbot/news/` — All news modules (sources, classifier, sentiment_scorer, impact_assessor, models, embeddings)
  - `src/traderbot/db/learnings.py` — Learnings database
  - `src/traderbot/learning.py` — Pattern promotion
  - `src/traderbot/wal.py` — WAL protocol
  - `src/traderbot/heartbeat.py` — Heartbeat implementation
  - `src/traderbot/cron_loops.py` — Cron definitions

  **WHY Each Reference Matters**:
  - These sections currently say phases are "not yet built" or contain placeholder test patterns
  - All these modules now exist and have real implementations
  - Test patterns must match actual function signatures and behavior

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Every function name in §2.11-2.14 exists in the codebase
    Tool: Bash (grep + python)
    Preconditions: Updated TESTING_PROMPT.md
    Steps:
      1. Extract all function/class names from §2.11-2.14 (e.g., BacktestEngine.run, DataLoader)
      2. Use python3 -c "import ast; ..." to get actual names from each module
      3. Compare lists
    Expected Result: 100% of referenced names exist in source code
    Failure Indicators: Referenced function not found in module
    Evidence: .sisyphus/evidence/task-10-name-verification.txt

  Scenario: No "not yet built" or "Phase N not started" markers remain
    Tool: Bash (grep)
    Preconditions: Updated TESTING_PROMPT.md
    Steps:
      1. grep -n "not yet built\|NOT STARTED\|pending.*Phase" tests/TESTING_PROMPT.md
      2. For each match, verify the corresponding module actually does NOT exist
    Expected Result: Zero stale "not yet built" markers for built modules
    Failure Indicators: "not yet built" marker for simulation/ or news/ which exist
    Evidence: .sisyphus/evidence/task-10-stale-markers.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): update Phases 2.11-2.14 for built simulation, learning, news, adaptation`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 11. Update Bug Class Taxonomy with Security Findings

  **What to do**:
  - Add new bug class entries to the taxonomy table in TESTING_PROMPT.md (§0.6) based on Task 3 security findings:
    1. **Credential field as plain str**: Pydantic model fields for credentials (api_key, token, secret, password, private_key) use `str` instead of `SecretStr`. Allows secrets in model_dump() output, log serialization, and repr. → Custom check: grep all BaseModel classes for credential-typed fields, verify SecretStr
    2. **SQLite file world-readable**: Database files created without explicit permission constraints (no `0o600` mode). → Custom check: verify all `open()` calls in db/ specify mode=0o600 or equivalent
    3. **Environment variable without keyring fallback**: `os.getenv`/`os.environ` reads for sensitive values without keyring fallback path. → Custom check: grep for os.getenv/os.environ, verify keyring is used for credential access
    4. **Audit log tampering**: No mechanism to detect or prevent audit log modification or deletion. → Custom check: verify audit logs use append-only mode, verify no code path deletes entries
    5. **Demo/production endpoint crossover**: Code paths that could send demo credentials to production endpoints or vice versa. → Custom check: verify endpoint selection is gated by KALSHI_DEMO env var with no bypass
    6. **Hardcoded test values in production code**: TEST_, MOCK_, FAKE_ patterns in src/ (not tests/). → Custom check: grep for these patterns in src/traderbot/ and verify they're only in test/demo contexts
  - Follow the existing taxonomy format: Bug Class | Abstract Pattern | Custom Check (no line numbers, no function names)

  **Must NOT do**:
  - Do not include line numbers or file paths in bug class entries (they must be abstract)
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs Task 3 results)
  - **Parallel Group**: Wave 3 (with Tasks 9, 10, 12)
  - **Blocks**: None
  - **Blocked By**: Task 3

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:137-180` — Existing bug class taxonomy (format to follow exactly)

  **API/Type References**:
  - Task 3 output — All security findings to formalize

  **WHY Each Reference Matters**:
  - The existing taxonomy format must be followed exactly for consistency
  - Bug classes must be abstract (no line numbers) so they remain valid as code evolves
  - Task 3 findings are the raw input for these taxonomy entries

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: New bug class entries follow existing taxonomy format
    Tool: Bash (grep)
    Preconditions: Updated TESTING_PROMPT.md
    Steps:
      1. Extract all new bug class entries added after the existing 9 entries
      2. Verify each entry has: Bug Class name, Abstract Pattern, Custom Check
      3. Verify no entry contains a file path or line number
    Expected Result: All entries follow | Bug Class | Abstract Pattern | Custom Check | format with no specific references
    Failure Indicators: Entry contains src/traderbot/ or line numbers
    Evidence: .sisyphus/evidence/task-11-taxonomy-format.txt

  Scenario: Every Task 3 security finding has a corresponding bug class entry
    Tool: Manual review
    Preconditions: Task 3 output available
    Steps:
      1. List all security findings from Task 3
      2. For each finding, locate the corresponding bug class entry in the updated taxonomy
    Expected Result: Every Task 3 finding has a taxonomy entry
    Failure Indicators: Finding from Task 3 not represented in taxonomy
    Evidence: .sisyphus/evidence/task-11-finding-coverage.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `docs(tests): add security bug classes to taxonomy`
  - Files: `tests/TESTING_PROMPT.md`

- [ ] 12. Write Phase 6.5 — Telegram E2E Integration Tests

  **What to do**:
  - Add a new section `## PHASE 6.5: TELEGRAM E2E INTEGRATION` to TESTING_PROMPT.md
  - This section verifies end-to-end communication through the OpenClaw gateway to Telegram:
    1. **Gateway-to-Telegram bridge**: Verify OpenClaw gateway can route messages to a Telegram bot. Test: send message to Telegram bot → verify OpenClaw receives it → agent processes → response routes back through gateway to Telegram
    2. **Telegram message format**: Verify TraderBot CLI output is compatible with Telegram message formatting — JSON output valid for parsing, Rich output suitable for character limits, no excessive message length
    3. **Skill invocation via Telegram**: Verify `traderbot scan`, `traderbot analyze`, `traderbot positions` produce output that renders correctly in Telegram
    4. **Heartbeat alerts via Telegram**: Verify heartbeat can surface alerts through the gateway to Telegram channel when circuit breaker activates or high-impact news detected
    5. **News alert via Telegram**: Verify News Loop systemEvent (impact > 0.7) surfaces actionable alert to main Telegram session
    6. **Error handling in Telegram context**: Verify error responses from TraderBot are gracefully formatted for Telegram (no stack traces, no overly long messages)
    7. **Isolation verification**: Verify isolated agentTurn sessions (Decision Loop, Heartbeat Loop) do NOT send messages to Telegram unless explicitly configured to do so
  - Include a prerequisite section: "This phase requires a running OpenClaw gateway with a Telegram bot token configured. Tests should not execute real Telegram messages without explicit human confirmation."

  **Must NOT do**:
  - Do not write actual test code — write the TESTING_PROMPT.md checklist section only
  - Do not send real Telegram messages without explicit human gate
  - Do not modify `docs/` files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Final verification
  - **Blocked By**: Tasks 4, 6, 8

  **References**:
  **Pattern References**:
  - `tests/TESTING_PROMPT.md:753-805` — Integration test section format

  **API/Type References**:
  - `skills/traderbot/SKILL.md` — Command definitions and JSON output format
  - `src/traderbot/cli.py` — CLI commands and output formatting
  - `src/traderbot/cron_loops.py` — Decision Loop, Heartbeat Loop, News Loop definitions
  - `.openclaw/workspace/AGENTS.md` — Telegram alert references
  - `.openclaw/workspace/HEARTBEAT.md` — Heartbeat task definitions

  **External References**:
  - OpenClaw docs: `https://docs.openclaw.ai/channels/telegram` — Telegram channel setup
  - OpenClaw docs: `https://docs.openclaw.ai/automation/cron-jobs` — Cron job payload formats

  **WHY Each Reference Matters**:
  - SKILL.md defines the output format that must render in Telegram
  - cli.py controls output formatting — must be Telegram-compatible
  - cron_loops.py defines which loops send messages to Telegram vs. isolated sessions
  - AGENTS.md and HEARTBEAT.md define the Telegram alert conditions

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Every CLI command's --json output is valid JSON parseable by Telegram gateway
    Tool: Bash (python)
    Preconditions: cli.py read and analyzed
    Steps:
      1. List all CLI commands that support --json flag
      2. For each, verify the JSON output format from SKILL.md matches cli.py's actual output
      3. Verify JSON output fits within Telegram message character limits (4096 chars)
    Expected Result: All --json outputs are valid JSON under 4096 characters
    Failure Indicators: JSON output exceeds character limit or is invalid JSON
    Evidence: .sisyphus/evidence/task-12-telegram-format.txt

  Scenario: Cron loop payloads match OpenClaw systemEvent/agentTurn format
    Tool: Bash (grep + python)
    Preconditions: cron_loops.py and SKILL.md both read
    Steps:
      1. Extract JSON payloads from cron_loops.py (Decision, Heartbeat, News loops)
      2. Verify each payload has: sessionTarget, payload.kind, payload.message
      3. Verify News Loop uses sessionTarget: "main" and kind: "systemEvent"
      4. Verify Decision/Heartbeat loops use sessionTarget: "isolated" and kind: "agentTurn"
    Expected Result: All three payloads conform to OpenClaw cron spec
    Failure Indicators: Missing required field or wrong sessionTarget/kind value
    Evidence: .sisyphus/evidence/task-12-cron-format.txt
  ```

  **Commit**: YES (final commit)
  - Message: `docs(tests): comprehensive E2E testing protocol update`
  - Files: `tests/TESTING_PROMPT.md`
  - Pre-commit: `grep -c 'PHASE' tests/TESTING_PROMPT.md` (verify all phases present)

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the updated TESTING_PROMPT.md end-to-end. Verify every "Must Have" is addressed. Verify no "Must NOT Have" violations. Verify all phase references match actual modules. Verify bug class taxonomy has security entries. Output: `Must Have [N/N] | Must NOT Have [N/N] | Phase references [N/N correct] | VERDICT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Verify ONLY TESTING_PROMPT.md was modified. Run `git diff --stat` to confirm. Verify no actual test code was written. Verify no files in `docs/` were modified. Verify no source files were modified. Output: `Files Modified [1] | Test Code [NONE] | Docs Modified [NONE] | VERDICT`

- [ ] F3. **Real QA** — `unspecified-high`
  Run grep commands to verify every module referenced in TESTING_PROMPT.md actually exists in the codebase. Run glob to confirm file existence. Cross-reference version claims against VERSION file. Verify acceptance criteria are all agent-executable (no "manually verify"). Output: `Module refs [N/N valid] | Version [MATCH] | Executable criteria [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Compare testing-protocol plan against actual TESTING_PROMPT.md changes. Verify everything in the plan was implemented. Verify nothing beyond scope was added. Flag any unaccounted additions. Output: `Plan items [N/N implemented] | Scope creep [NONE/N items] | VERDICT`

---

## Commit Strategy

- **1**: `docs(tests): rewrite TESTING_PROMPT.md as comprehensive E2E protocol` — tests/TESTING_PROMPT.md

## Success Criteria

### Verification Commands
```bash
# Verify TESTING_PROMPT.md exists and is substantial
wc -l tests/TESTING_PROMPT.md  # Expected: >2000 lines

# Verify no source code was modified
git diff --stat src/  # Expected: no changes

# Verify no docs/ were modified
git diff --stat docs/  # Expected: no changes

# Verify only TESTING_PROMPT.md was modified
git diff --name-only  # Expected: tests/TESTING_PROMPT.md only
```

### Final Checklist
- [ ] All "Must Have" sections present in TESTING_PROMPT.md
- [ ] All "Must NOT Have" violations absent
- [ ] No files in docs/ were modified
- [ ] No actual test code was written
- [ ] All phase references updated (5-8 built status)
- [ ] Bug class taxonomy includes security findings
- [ ] All acceptance criteria are agent-executable
- [ ] TESTING_PROMPT.md references match actual codebase modules