# Agent-Profile Binding & Multi-Agent Deployment

## TL;DR

> **Quick Summary**: Implement profile-based multi-agent deployment for TraderBot with token-based handshake to OpenClaw agents, per-profile data isolation/risk params/market categories/auth stores, an installer script for Linux+macOS, and full documentation rebuild.
> 
> **Deliverables**:
> - Profile management module (models, registry, encrypted keyring storage)
> - Token handshake system (generation, resolution, auto-injection)
> - Per-profile risk enforcement (AgentRiskLimits with HARD_LIMITS ceiling)
> - Per-profile market category filtering
> - Per-profile auth store (keyring namespace hierarchy)
> - Data isolation plumbing (separate DBs/dirs per profile)
> - CLI commands for profile CRUD, assignment, discovery
> - Installer script (OS detect → deps → persistence → config flow)
> - systemd (Linux) + launchd (macOS) service templates
> - TDD test suite covering security invariants
> - Full documentation rebuild
> 
> **Estimated Effort**: XL
> **Parallel Execution**: YES - 6 waves
> **Critical Path**: T1 (profile models) → T5 (profile-aware risk gate) → T11 (installer config flow) → T16 (doc rebuild) → F1-F4

---

## Context

### Original Request
Deploy TraderBot on Ubuntu with multiple OpenClaw agents running simultaneously (paper + live). Profiles determine paper/live mode, risk parameters, enabled market categories, and API credentials. Agents are assigned to profiles via immutable token-based handshake. An installer script ties everything together.

### Interview Summary
**Key Discussions**:
- Profiles are TraderBot-owned presets; agents are OpenClaw entities. TraderBot doesn't own agents.
- Token-based handshake: 12-char opaque token per agent, embedded in TOOLS.md, resolved on each CLI request
- One agent per profile (no concurrency complexity)
- Per-profile: risk params (capped by HARD_LIMITS), market categories (enable/disable), auth stores (different API keys per profile)
- Encrypted keyring storage for all profile data and assignments — agent cannot read/modify
- Installer: lightweight shell script, downloads from GitHub (supports PAT + public), 3-phase (detect → persist → configure)
- OS support: Linux + macOS (Windows later), boot persistence via systemd/launchd
- TDD for all security-critical code

**Research Findings**:
- Existing `StrategyProfile` (simulation only) has risk_multiplier pattern to follow
- `HARD_LIMITS` uses `MappingProxyType` + `Final` — same pattern for AgentRiskLimits
- `evaluate_trade()` in `risk/__init__.py` is the central risk gate — needs profile awareness
- Data isolation gaps: SQLite, ChromaDB, config dir, .env loading, keyring namespace all hardcoded
- OpenClaw workspace: `.openclaw/workspace/` with IDENTITY.md, TOOLS.md, etc.
- `AuthManager` uses `traderbot.{service}` namespace — needs per-profile variant

### Metis Review
**Identified Gaps** (addressed):
- Concurrency model → Decided: one agent per profile, no shared profiles
- Keyring encryption mechanism → OS keyring (encrypted by OS), namespace `traderbot.profiles`
- Token entropy → `secrets.token_urlsafe(9)[:12]` (~72 bits)
- Profile deletion data retention → Prompt, default keep
- Keyring fallback on headless → gnome-keyring install or Fernet-encrypted file
- Installer idempotency → Skip configured steps, offer update
- Cross-profile visibility → Explicitly excluded
- Profile hierarchy → Flat only for v1.0

---

## Work Objectives

### Core Objective
Enable multiple OpenClaw agents to run TraderBot simultaneously on the same host with different trading profiles, where each profile provides isolated data, immutable risk enforcement, per-profile API credentials, and market category filtering — all secured against LLM runtime abuse and config tampering.

### Concrete Deliverables
- `src/traderbot/profiles/models.py` — TradingProfile Pydantic model
- `src/traderbot/profiles/registry.py` — ProfileRegistry with encrypted keyring storage
- `src/traderbot/profiles/discovery.py` — OpenClaw agent auto-discovery
- `src/traderbot/profiles/tokens.py` — Token generation, resolution, injection
- `src/traderbot/profiles/auth.py` — Per-profile auth store with keyring namespace
- `src/traderbot/risk/agent_limits.py` — AgentRiskLimits with HARD_LIMITS ceiling
- Updated `src/traderbot/risk/__init__.py` — Profile-aware evaluate_trade()
- Updated `src/traderbot/cli.py` — Profile CLI commands
- `install/traderbot-installer.sh` — Installer script
- `install/services/traderbot-agent@.service` — Systemd template
- `install/services/com.traderbot.agent.plist` — Launchd template
- Test suite in `tests/profiles/` and `tests/risk/`
- Rebuilt `docs/` directory

### Definition of Done
- [x] `traderbot profile create/list/show/delete/assign/revoke` all work
- [x] Agent with token resolves to correct profile, isolated data dirs
- [x] Profile with risk_multiplier 0.5 → trades sized at 50% of HARD_LIMITS
- [x] Profile with categories [Economics, Politics] → Sports trade rejected
- [x] Profile with own Kalshi API key → uses that instead of global
- [x] Agent cannot change profile, token, or risk params at runtime (verified by tests)
- [x] Installer runs on fresh Ubuntu + macOS, sets up persistence, injects tokens
- [x] All docs rebuilt and accurate

### Must Have
- Immutable profile-agent binding (token handshake, encrypted storage)
- Per-profile data isolation (separate SQLite, ChromaDB, audit dirs)
- Per-profile risk params capped by HARD_LIMITS ceiling
- Per-profile market category filtering enforced in risk gate
- Per-profile auth store with keyring namespace hierarchy
- Agent auto-discovery from OpenClaw IDENTITY.md
- Token auto-injection into agent TOOLS.md
- TDD test suite proving security invariants
- Installer script with OS detection + persistence + config flow
- Documentation rebuild

### Must NOT Have (Guardrails)
- NO Docker/containerization
- NO Windows support
- NO profile nesting or hierarchy (flat only)
- NO cross-profile visibility or data sharing
- NO multiple agents per profile (one-to-one)
- NO profile export/import (v1.0)
- NO CLI `--profile` flag for agents (token-only, no bypass)
- AI slop: no excessive comments on security code, no generic `data`/`result` variable names
- NEVER store profile data in plaintext accessible to agent processes
- NEVER allow profile risk params to exceed HARD_LIMITS ceiling
- NEVER allow token resolution to succeed for revoked/invalid tokens

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: YES (pytest with async support)
- **Automated tests**: TDD — RED → GREEN → REFACTOR for every task
- **Framework**: pytest

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Security tests**: pytest proves invariants (token immutability, risk ceiling enforcement, category rejection)
- **CLI tests**: Bash (typer CLI) — run commands, parse JSON output, assert fields
- **Installer tests**: Bash (shellcheck + dry-run) — validate script syntax, dependency detection logic
- **Integration tests**: Bash — create profile, assign agent, run trade, verify isolation

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — types, models, interfaces):
├── T1: TradingProfile model + validation [deep]
├── T2: Profile registry (keyring CRUD) [deep]
├── T3: Token module (generation, resolution) [deep]
├── T4: AgentRiskLimits model [quick]
├── T5: Per-profile auth store [unspecified-high]
└── T6: OpenClaw agent discovery [quick]

Wave 2 (Core integration — risk gate, CLI, data isolation):
├── T7: Profile-aware evaluate_trade() (depends: T1, T4) [deep]
├── T8: Profile CLI commands (depends: T1, T2, T3) [unspecified-high]
├── T9: Data isolation plumbing (depends: T1) [unspecified-high]
├── T10: Token auto-injection into TOOLS.md (depends: T3, T6) [unspecified-high]
└── T11: Profile-aware config loading (depends: T1, T5, T9) [deep]

Wave 3 (Persistence + installer):
├── T12: Systemd service template (depends: T8, T11) [quick]
├── T13: Launchd plist template (depends: T8, T11) [quick]
├── T14: Installer: OS detection + dependency install [unspecified-high]
├── T15: Installer: Persistence setup (depends: T12, T13) [quick]
└── T16: Installer: Config flow + token injection (depends: T10, T14, T15) [unspecified-high]

Wave 4 (Documentation):
└── T17: Full documentation rebuild (depends: ALL above) [writing]

Wave FINAL (Verification — 4 parallel reviews):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: T1 → T7 → T11 → T16 → T17 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 6 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|---|---|---|---|
| T1 | — | T7, T8, T9, T11 | 1 |
| T2 | — | T8 | 1 |
| T3 | — | T8, T10 | 1 |
| T4 | — | T7 | 1 |
| T5 | — | T11 | 1 |
| T6 | — | T10 | 1 |
| T7 | T1, T4 | T11 | 2 |
| T8 | T1, T2, T3 | T12, T13 | 2 |
| T9 | T1 | T11 | 2 |
| T10 | T3, T6 | T16 | 2 |
| T11 | T1, T5, T9 | T12, T13 | 2 |
| T12 | T8, T11 | T15 | 3 |
| T13 | T8, T11 | T15 | 3 |
| T14 | — | T16 | 3 |
| T15 | T12, T13 | T16 | 3 |
| T16 | T10, T14, T15 | T17 | 3 |
| T17 | ALL | F1-F4 | 4 |
| F1-F4 | T17 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 6 tasks — T1→`deep`, T2→`deep`, T3→`deep`, T4→`quick`, T5→`unspecified-high`, T6→`quick`
- **Wave 2**: 5 tasks — T7→`deep`, T8→`unspecified-high`, T9→`unspecified-high`, T10→`unspecified-high`, T11→`deep`
- **Wave 3**: 5 tasks — T12→`quick`, T13→`quick`, T14→`unspecified-high`, T15→`quick`, T16→`unspecified-high`
- **Wave 4**: 1 task — T17→`writing`
- **FINAL**: 4 tasks — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [x] 1. TradingProfile Model + Validation

  **What to do**:
  - Create `src/traderbot/profiles/__init__.py` with package exports
  - Create `src/traderbot/profiles/models.py` with `TradingProfile` Pydantic model:
    - Fields: `name`, `mode` (Literal["paper", "live"]), `description`, `enabled_categories` (list[MarketCategory], default empty=all), `risk_multiplier`, `max_position_per_market_pct`, `max_daily_loss_pct`, `max_drawdown_pct`, `max_open_positions`, `min_liquidity_threshold`, `min_edge_pct`
    - Computed properties: `base_dir`, `demo_mode`, `keyring_prefix`, `env_file`
    - Method: `is_category_enabled(category) -> bool`
    - Validator: all risk params MUST be <= corresponding HARD_LIMITS value (raise ValueError if exceeding)
  - Write TDD tests FIRST in `tests/profiles/test_models.py`:
    - Profile creation with valid params
    - Profile with mode="paper" → demo_mode=True, base_dir=".traderbot-paper"
    - Profile with mode="live" → demo_mode=False, base_dir=".traderbot-live"
    - Risk param exceeding HARD_LIMITS → validation error
    - Risk param within HARD_LIMITS → succeeds
    - Empty enabled_categories → all categories permitted
    - Specific enabled_categories → only those permitted
    - Category not in list → is_category_enabled returns False

  **Must NOT do**:
  - Do NOT implement registry/storage logic (that's T2)
  - Do NOT implement token logic (that's T3)
  - Do NOT modify existing `simulation/profiles.py` (different concern)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core model with security-critical validators, needs careful implementation
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: No UI in this task

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T4, T5, T6)
  - **Blocks**: T7, T8, T9, T11
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `src/traderbot/simulation/profiles.py:StrategyProfile` — Pattern for profile model with risk_multiplier (simulation-only, this is the runtime variant)
  - `src/traderbot/risk/limits.py:HARD_LIMITS` — The ceiling values that TradingProfile risk params must not exceed (MappingProxyType pattern to follow)
  - `src/traderbot/kalshi/models.py:MarketCategory` — The StrEnum for market categories to reuse in enabled_categories field

  **API/Type References** (contracts to implement against):
  - `src/traderbot/risk/limits.py:HARD_LIMITS` dict keys — Must match field names for validator (max_position_per_market_pct, max_daily_loss_pct, etc.)

  **Test References** (testing patterns to follow):
  - `tests/test_*.py` — Existing pytest patterns in the project

  **WHY Each Reference Matters**:
  - `simulation/profiles.py`: Shows the existing profile pattern but for simulation only. TradingProfile is the runtime production variant, must not duplicate but must be compatible.
  - `risk/limits.py`: The HARD_LIMITS dict is the ceiling. The TradingProfile validator MUST use these exact keys to enforce `min(profile_param, HARD_LIMITS[key])`.
  - `kalshi/models.py:MarketCategory`: Reuse this exact enum — don't create a new one.

  **Acceptance Criteria**:

  **If TDD (tests enabled):**
  - [ ] Test file created: tests/profiles/test_models.py
  - [ ] pytest tests/profiles/test_models.py → PASS (8+ tests, 0 failures)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Create valid paper profile
    Tool: Bash (pytest)
    Preconditions: TraderBot package installed
    Steps:
      1. pytest tests/profiles/test_models.py::test_create_paper_profile -v
      2. Assert: test passes, profile.demo_mode == True
    Expected Result: Profile with mode="paper" has demo_mode=True, base_dir=".traderbot-paper"
    Failure Indicators: ValueError on creation, demo_mode=False
    Evidence: .sisyphus/evidence/task-1-valid-paper-profile.txt

  Scenario: Risk param exceeds HARD_LIMITS ceiling
    Tool: Bash (pytest)
    Preconditions: TraderBot package installed
    Steps:
      1. pytest tests/profiles/test_models.py::test_risk_exceeds_hard_limits -v
      2. Assert: validation error raised with message about HARD_LIMITS
    Expected Result: Pydantic ValidationError with field-specific message
    Failure Indicators: Profile created with exceeding params (security violation!)
    Evidence: .sisyphus/evidence/task-1-risk-ceiling-violation.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add TradingProfile model with risk params, categories, auth overrides`
  - Files: `src/traderbot/profiles/__init__.py, src/traderbot/profiles/models.py, tests/profiles/test_models.py`
  - Pre-commit: `pytest tests/profiles/test_models.py`

- [x] 2. Profile Registry (Encrypted Keyring Storage)

  **What to do**:
  - Create `src/traderbot/profiles/registry.py` with `ProfileRegistry` class:
    - Keyring service namespace: `traderbot.profiles` (separate from agent-accessible `traderbot.{service}`)
    - Store/retrieve TradingProfile objects as JSON in keyring entries
    - `create_profile(profile: TradingProfile)` — serialize to JSON, store in keyring
    - `get_profile(name: str) -> TradingProfile | None` — retrieve and deserialize
    - `list_profiles() -> list[str]` — list all profile names
    - `delete_profile(name: str) -> bool` — remove profile, prompt for data purge
    - `update_profile(name: str, **kwargs)` — update specific fields
    - Fallback: If keyring unavailable, use Fernet-encrypted file at `~/.traderbot/profiles.enc`
  - Write TDD tests FIRST in `tests/profiles/test_registry.py`:
    - Create profile → retrieve → matches original
    - List profiles after creating two → returns both names
    - Delete profile → get_profile returns None
    - Update profile field → persisted change
    - Keyring unavailable → fallback to encrypted file
    - Corrupted keyring entry → graceful error, not crash

  **Must NOT do**:
  - Do NOT implement token logic (that's T3)
  - Do NOT store credentials in plaintext
  - Do NOT modify existing `AuthManager` class (T5 extends it)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Encrypted storage layer with security-critical fallback logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3, T4, T5, T6)
  - **Blocks**: T8
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/auth.py:AuthManager` — Keyring CRUD pattern to follow (get_password/set_password/delete_password with service prefix). Key difference: ProfileRegistry uses `traderbot.profiles` namespace, not `traderbot.{service}`.
  - `src/traderbot/auth.py:KeyringUnavailableError` — Reuse this error pattern for keyring fallback

  **API/Type References**:
  - `src/traderbot/profiles/models.py:TradingProfile` — The model this registry stores/retrieves (T1 concurrent, use interface: serialize/deserialize TradingProfile to/from JSON)

  **WHY Each Reference Matters**:
  - `auth.py:AuthManager`: Shows the established keyring pattern in this codebase. ProfileRegistry must follow same conventions (service prefix, fallback, error handling) but use a SEPARATE namespace the agent cannot discover.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_registry.py
  - [ ] pytest tests/profiles/test_registry.py → PASS (6+ tests, 0 failures)

  **QA Scenarios:**

  ```
  Scenario: Create and retrieve profile
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_registry.py::test_create_and_get_profile -v
    Expected Result: Retrieved profile matches created profile exactly
    Failure Indicators: Retrieved profile differs, None returned, serialization error
    Evidence: .sisyphus/evidence/task-2-create-retrieve.txt

  Scenario: Keyring fallback to encrypted file
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_registry.py::test_keyring_fallback -v
    Expected Result: Profile stored in Fernet-encrypted file when keyring unavailable
    Failure Indicators: Profile lost when keyring unavailable, plaintext storage
    Evidence: .sisyphus/evidence/task-2-keyring-fallback.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add ProfileRegistry with encrypted keyring storage`
  - Files: `src/traderbot/profiles/registry.py, tests/profiles/test_registry.py`
  - Pre-commit: `pytest tests/profiles/test_registry.py`

- [x] 3. Token Module (Generation, Resolution, Revocation)

  **What to do**:
  - Create `src/traderbot/profiles/tokens.py`:
    - `generate_token() -> str` — `secrets.token_urlsafe(9)[:12]` (~72 bits entropy)
    - `store_token_mapping(token: str, agent_name: str, profile_name: str)` — store in keyring under `traderbot.profiles.tokens` namespace
    - `resolve_token(token: str) -> tuple[str, TradingProfile]` — given token, return (agent_name, profile). Must NOT work for revoked/invalid tokens.
    - `revoke_token(agent_name: str) -> bool` — remove token mapping
    - `list_tokens() -> list[dict]` — list all token-agent-profile mappings (token values masked)
    - `token_is_valid(token: str) -> bool` — check without resolving
  - Write TDD tests FIRST in `tests/profiles/test_tokens.py`:
    - generate_token returns 12-char string
    - generate_token is cryptographically unique across calls
    - store + resolve returns correct agent + profile
    - resolve with invalid token → raises error, does not succeed
    - revoke token → subsequent resolve fails
    - list_tokens → tokens are masked (first 4 + **** + last 2)

  **Must NOT do**:
  - Do NOT make tokens guessable or predictable
  - Do NOT store tokens in plaintext files
  - Do NOT allow resolve to succeed after revocation

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Security-critical token system, needs careful implementation of revocation and validation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T4, T5, T6)
  - **Blocks**: T8, T10
  - **Blocked By**: None (uses ProfileRegistry interface, assumes T2's storage pattern)

  **References**:

  **Pattern References**:
  - `src/traderbot/auth.py:AuthManager` — Keyring storage pattern for tokens. Use same `set_password`/`get_password` API but `traderbot.profiles.tokens` namespace.

  **API/Type References**:
  - `src/traderbot/profiles/models.py:TradingProfile` — What resolve_token returns (T1 concurrent)
  - `src/traderbot/auth.py:CredentialResult` — Pattern for returning structured auth results

  **WHY Each Reference Matters**:
  - `auth.py`: Token storage must use a keyring namespace the agent cannot discover. The `traderbot.profiles.tokens` namespace is separate from `traderbot.{service}` that agents see.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_tokens.py
  - [ ] pytest tests/profiles/test_tokens.py → PASS (6+ tests, 0 failures)

  **QA Scenarios:**

  ```
  Scenario: Token generation and resolution
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_tokens.py::test_generate_resolve_token -v
    Expected Result: 12-char token resolves to correct agent and profile
    Failure Indicators: Token wrong length, resolution fails or returns wrong data
    Evidence: .sisyphus/evidence/task-3-token-gen-resolve.txt

  Scenario: Revoked token fails resolution
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_tokens.py::test_revoke_token -v
    Expected Result: After revocation, resolve_token raises error (does not silently succeed)
    Failure Indicators: Revoked token still resolves (CRITICAL SECURITY FAILURE)
    Evidence: .sisyphus/evidence/task-3-token-revoke.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add token generation, resolution, and revocation`
  - Files: `src/traderbot/profiles/tokens.py, tests/profiles/test_tokens.py`
  - Pre-commit: `pytest tests/profiles/test_tokens.py`

- [x] 4. AgentRiskLimits Model

  **What to do**:
  - Create `src/traderbot/risk/agent_limits.py`:
    - `AgentRiskLimits` class: takes agent_name + risk param overrides, freezes via `MappingProxyType`
    - Constructor: for each key in HARD_LIMITS, `min(override, HARD_LIMITS[key])` — ceiling always wins
    - `limits` property returns frozen `MappingProxyType` — no runtime mutation
    - Fallback: any key not overridden uses HARD_LIMITS default
    - `__repr__` shows agent name + effective limits
  - Write TDD tests FIRST in `tests/risk/test_agent_limits.py`:
    - Agent with all defaults → matches HARD_LIMITS exactly
    - Agent with stricter daily loss → effective limit is stricter
    - Agent with daily loss exceeding HARD_LIMITS → HARD_LIMITS ceiling wins (min())
    - Attempt to mutate limits property → TypeError (MappingProxyType frozen)
    - Partial overrides → unspecified keys fall back to HARD_LIMITS

  **Must NOT do**:
  - Do NOT allow limits to exceed HARD_LIMITS
  - Do NOT make limits mutable after construction

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small, focused module following established MappingProxyType pattern from limits.py
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T5, T6)
  - **Blocks**: T7
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/risk/limits.py:HARD_LIMITS` — The MappingProxyType + Final pattern to follow exactly. This is the ceiling this class enforces.

  **WHY Each Reference Matters**:
  - `limits.py`: AgentRiskLimits MUST use the same immutability pattern. The `min()` enforcement is the core security guarantee.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/risk/test_agent_limits.py
  - [ ] pytest tests/risk/test_agent_limits.py → PASS (5+ tests, 0 failures)

  **QA Scenarios:**

  ```
  Scenario: Risk param exceeds HARD_LIMITS ceiling
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/risk/test_agent_limits.py::test_ceiling_enforcement -v
    Expected Result: AgentRiskLimits.limits["max_daily_loss_pct"] == HARD_LIMITS value, not the override
    Failure Indicators: Override exceeding HARD_LIMITS accepted (CRITICAL SECURITY FAILURE)
    Evidence: .sisyphus/evidence/task-4-ceiling-enforcement.txt

  Scenario: Limits immutable after construction
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/risk/test_agent_limits.py::test_limits_frozen -v
    Expected Result: TypeError when attempting limits["key"] = value
    Failure Indicators: Mutation succeeds (CRITICAL SECURITY FAILURE)
    Evidence: .sisyphus/evidence/task-4-limits-frozen.txt
  ```

  **Commit**: YES
  - Message: `feat(risk): add AgentRiskLimits with HARD_LIMITS ceiling enforcement`
  - Files: `src/traderbot/risk/agent_limits.py, tests/risk/test_agent_limits.py`
  - Pre-commit: `pytest tests/risk/test_agent_limits.py`

- [x] 5. Per-Profile Auth Store

  **What to do**:
  - Create `src/traderbot/profiles/auth.py` with `ProfileAuthStore` class:
    - Resolution chain: profile-specific keyring → global keyring → environment variable
    - Profile keyring namespace: `traderbot.profiles.<profile_name>.<service>.<key>`
    - Global keyring: `traderbot.<service>.<key>` (existing AuthManager)
    - `set_credential(profile_name, service, key, value)` — store in profile namespace
    - `get_credential(profile_name, service, key) -> CredentialResult | None` — full resolution chain
    - `delete_credential(profile_name, service, key) -> bool`
    - `list_profile_credentials(profile_name) -> list[ServiceInfo]`
    - `copy_global_to_profile(profile_name, service)` — convenience: clone global creds to profile
  - Write TDD tests FIRST in `tests/profiles/test_auth.py`:
    - No profile-specific cred → falls back to global keyring
    - Profile-specific cred → overrides global
    - Neither profile nor global → falls back to env var
    - Delete profile cred → global still works
    - Copy global to profile → profile now has its own copy

  **Must NOT do**:
  - Do NOT modify existing `AuthManager` class behavior
  - Do NOT expose credential values in list operations

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Auth resolution chain with 3-level fallback, needs careful testing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T4, T6)
  - **Blocks**: T11
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/auth.py:AuthManager` — The global auth pattern to extend. ProfileAuthStore composes AuthManager, doesn't inherit it.
  - `src/traderbot/kalshi/config.py:KeyringKalshiConfig` — The config that currently resolves Kalshi creds. Needs updating in T11 to use ProfileAuthStore.

  **WHY Each Reference Matters**:
  - `auth.py:AuthManager`: ProfileAuthStore MUST compose this class for global-fallback behavior. The `get_credential` method already handles keyring→env resolution. ProfileAuthStore adds the profile-specific namespace on top.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_auth.py
  - [ ] pytest tests/profiles/test_auth.py → PASS (5+ tests, 0 failures)

  **QA Scenarios:**

  ```
  Scenario: Profile credential overrides global
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_auth.py::test_profile_overrides_global -v
    Expected Result: get_credential returns profile-specific value, not global
    Failure Indicators: Global value returned despite profile override
    Evidence: .sisyphus/evidence/task-5-profile-override.txt

  Scenario: Fallback chain exhausted
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_auth.py::test_fallback_to_env -v
    Expected Result: When profile+global keyring both empty, env var used
    Failure Indicators: None returned when env var exists, or crash
    Evidence: .sisyphus/evidence/task-5-fallback-chain.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add per-profile auth store with keyring namespace`
  - Files: `src/traderbot/profiles/auth.py, tests/profiles/test_auth.py`
  - Pre-commit: `pytest tests/profiles/test_auth.py`

- [x] 6. OpenClaw Agent Auto-Discovery

  **What to do**:
  - Create `src/traderbot/profiles/discovery.py`:
    - `discover_agents(workspace_root: Path | None = None) -> list[AgentInfo]`
    - `AgentInfo` model: agent_name, workspace_path, assigned_profile (if any), identity_summary
    - Scan `~/.openclaw/workspace/` (or custom root) for IDENTITY.md files
    - Parse agent name from IDENTITY.md (first `**Name**: <value>` pattern)
    - Check if agent has existing token assignment in ProfileRegistry
    - Handle: missing workspace dir, malformed IDENTITY.md, multiple workspaces
  - Write TDD tests FIRST in `tests/profiles/test_discovery.py`:
    - Discover single agent from IDENTITY.md
    - Discover multiple agents from workspace
    - Missing workspace dir → returns empty list, no error
    - Malformed IDENTITY.md → skip with warning
    - Agent with existing assignment → shows profile name

  **Must NOT do**:
  - Do NOT write to any OpenClaw files (that's T10)
  - Do NOT depend on specific IDENTITY.md format beyond the Name field

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File parsing with simple regex, well-defined scope
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T4, T5)
  - **Blocks**: T10
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/IDENTITY.md` — Format: `**Name**: TraderBot` on a line. Parse this pattern.
  - `.openclaw/workspace/TOOLS.md` — Where token gets injected (T10 writes here)

  **WHY Each Reference Matters**:
  - `IDENTITY.md`: The source of agent names. Current format is `- **Name**: TraderBot`. Discovery must parse this reliably.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_discovery.py
  - [ ] pytest tests/profiles/test_discovery.py → PASS (5+ tests, 0 failures)

  **QA Scenarios:**

  ```
  Scenario: Discover agents from workspace
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_discovery.py::test_discover_agents -v
    Expected Result: Returns list of AgentInfo with correct names
    Failure Indicators: Empty list when agents exist, crash on parse
    Evidence: .sisyphus/evidence/task-6-discover-agents.txt

  Scenario: Missing workspace directory
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_discovery.py::test_missing_workspace -v
    Expected Result: Returns empty list, no exception raised
    Failure Indicators: FileNotFoundError crash
    Evidence: .sisyphus/evidence/task-6-missing-workspace.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add OpenClaw agent auto-discovery from IDENTITY.md`
  - Files: `src/traderbot/profiles/discovery.py, tests/profiles/test_discovery.py`
  - Pre-commit: `pytest tests/profiles/test_discovery.py`

- [x] 7. Profile-Aware evaluate_trade()

  **What to do**:
  - Update `src/traderbot/risk/__init__.py:evaluate_trade()`:
    - Add `agent_limits: AgentRiskLimits | None = None` parameter
    - Add `profile: TradingProfile | None = None` parameter
    - Before existing checks: if profile has enabled_categories, check trade market category → reject if not enabled
    - Replace all `HARD_LIMITS[key]` references with `agent_limits.limits[key] if agent_limits else HARD_LIMITS[key]`
    - This means: profile limits (via AgentRiskLimits) enforce stricter limits, HARD_LIMITS remains default ceiling
  - Write TDD tests FIRST in `tests/risk/test_evaluate_trade_profile.py`:
    - Trade with profile limits stricter than HARD_LIMITS → uses stricter limit
    - Trade in disabled market category → returns 0 with rejection reason
    - Trade without profile → uses HARD_LIMITS (backward compatible)
    - Trade with profile but no AgentRiskLimits → uses TradingProfile risk params as AgentRiskLimits
    - Category filter + risk limiter both apply → category check happens before risk math

  **Must NOT do**:
  - Do NOT break existing evaluate_trade() calls (backward compatible — defaults preserve current behavior)
  - Do NOT remove HARD_LIMITS — it remains the ultimate ceiling
  - Do NOT change function signature for existing callers

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core risk gate modification — must preserve existing behavior while adding new constraints
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: T11
  - **Blocked By**: T1, T4

  **References**:

  **Pattern References**:
  - `src/traderbot/risk/__init__.py:evaluate_trade()` — The function being modified. Lines 21-54. Critical: preserve the circuit breaker → limits → sizing flow.
  - `src/traderbot/risk/limits.py:run_all_checks()` — Called by evaluate_trade. Must understand what it checks to know where AgentRiskLimits plugs in.

  **API/Type References**:
  - `src/traderbot/risk/agent_limits.py:AgentRiskLimits` (T4) — The limits object to accept
  - `src/traderbot/profiles/models.py:TradingProfile` (T1) — For category check

  **WHY Each Reference Matters**:
  - `risk/__init__.py`: This is the ONE place all trades pass through. Adding agent_limits here means it's enforced everywhere — no bypass route.
  - `limits.py:run_all_checks`: Must accept agent_limits parameter too, or evaluate_trade must do the min() check before calling run_all_checks.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/risk/test_evaluate_trade_profile.py
  - [ ] pytest tests/risk/test_evaluate_trade_profile.py → PASS (5+ tests)
  - [ ] pytest tests/ — ALL existing tests still pass (regression check)

  **QA Scenarios:**

  ```
  Scenario: Category filter rejects disallowed market
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/risk/test_evaluate_trade_profile.py::test_category_rejection -v
    Expected Result: evaluate_trade returns 0 with rejection mentioning category not enabled
    Failure Indicators: Trade executes despite category not in enabled_categories
    Evidence: .sisyphus/evidence/task-7-category-rejection.txt

  Scenario: Backward compatibility — no profile argument
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/ -v (full suite)
    Expected Result: All existing tests pass without modification
    Failure Indicators: Any existing test breaks
    Evidence: .sisyphus/evidence/task-7-backward-compat.txt
  ```

  **Commit**: YES
  - Message: `feat(risk): update evaluate_trade() for profile-aware risk gate and category filter`
  - Files: `src/traderbot/risk/__init__.py, src/traderbot/risk/limits.py, tests/risk/test_evaluate_trade_profile.py`
  - Pre-commit: `pytest tests/`

- [x] 8. Profile CLI Commands

  **What to do**:
  - Add `profile` command group to `src/traderbot/cli.py` using Typer subcommands:
    - `traderbot profile create <name> --mode paper|live [--risk-multiplier N] [--max-daily-loss N] [--max-open-positions N] [--categories Economics,Politics,...] [--description TEXT]` — create TradingProfile, store via ProfileRegistry
    - `traderbot profile list [--json]` — list all profile names
    - `traderbot profile show <name> [--json]` — display profile details
    - `traderbot profile delete <name> [--purge-data]` — remove profile (and optionally data dirs)
    - `traderbot profile update <name> [--categories ...] [--risk-multiplier ...]` — update specific fields
    - `traderbot profile assign <agent-name> <profile-name>` — create token, auto-inject, display token
    - `traderbot profile revoke <agent-name>` — revoke token, remove from TOOLS.md
    - `traderbot profile assignments [--json]` — list all agent-profile-token mappings
    - `traderbot profile discover-agents [--json]` — scan OpenClaw workspaces
    - `traderbot profile set-auth <profile-name> <service> <key>` — store credential for profile
    - `traderbot profile auth <profile-name> [--json]` — show configured credentials for profile
  - Token resolution: on EVERY CLI invocation, check for `TRADERBOT_PROFILE_TOKEN` env var → if present, resolve → load profile → use for all operations
  - Write TDD tests FIRST in `tests/profiles/test_cli.py`:
    - `profile create` → persists, shows confirmation
    - `profile list` → shows created profiles
    - `profile show` → correct details
    - `profile delete` → profile removed
    - `profile assign` → token generated, agent workspace updated
    - `profile assign` with missing agent → error, not crash
    - Token in env → CLI resolves to correct profile

  **Must NOT do**:
  - Do NOT add `--profile` flag that agents can use to bypass token
  - Do NOT show unmasked tokens in `profile assignments` output

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Many CLI subcommands with proper JSON output, error handling, and token integration
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: T12, T13
  - **Blocked By**: T1, T2, T3

  **References**:

  **Pattern References**:
  - `src/traderbot/cli.py` — Existing Typer CLI structure. Follow the same pattern: `app = typer.Typer()`, subcommand groups, `--json` flag support, Rich console output.
  - `src/traderbot/cli.py:440` — `Path.home() / ".traderbot"` — this hardcoded path needs to become profile-aware

  **API/Type References**:
  - `src/traderbot/profiles/registry.py:ProfileRegistry` (T2) — CLI calls this for CRUD
  - `src/traderbot/profiles/tokens.py` (T3) — CLI calls this for assign/revoke
  - `src/traderbot/profiles/discovery.py` (T6) — CLI calls this for discover-agents
  - `src/traderbot/profiles/auth.py:ProfileAuthStore` (T5) — CLI calls this for set-auth/auth

  **WHY Each Reference Matters**:
  - `cli.py`: Existing CLI has ~900 lines. Profile commands should be a NEW subcommand group, not inline. Follow `traderbot scan` pattern for `--json` output.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_cli.py
  - [ ] pytest tests/profiles/test_cli.py → PASS (7+ tests)
  - [ ] `traderbot profile --help` shows all subcommands

  **QA Scenarios:**

  ```
  Scenario: Create profile via CLI
    Tool: Bash (CLI)
    Steps:
      1. traderbot profile create test-paper --mode paper --categories Economics,Politics --json
      2. Parse JSON output, assert name=="test-paper", mode=="paper"
      3. traderbot profile show test-paper --json
      4. Assert enabled_categories contains Economics, Politics
    Expected Result: Profile created and retrievable with correct fields
    Failure Indicators: JSON parse error, missing fields, wrong category list
    Evidence: .sisyphus/evidence/task-8-cli-create.txt

  Scenario: Token resolution on CLI invocation
    Tool: Bash (CLI)
    Steps:
      1. Create profile and assign agent to get token
      2. TRADERBOT_PROFILE_TOKEN=<token> traderbot scan --json
      3. Assert: uses paper API URL (not production) in output metadata
    Expected Result: CLI resolves token and uses profile-specific config
    Failure Indicators: Uses global config, production API on paper profile
    Evidence: .sisyphus/evidence/task-8-token-resolution.txt
  ```

  **Commit**: YES
  - Message: `feat(cli): add profile management CLI commands`
  - Files: `src/traderbot/cli.py, tests/profiles/test_cli.py`
  - Pre-commit: `pytest tests/profiles/test_cli.py`

- [x] 9. Per-Profile Data Isolation Plumbing

  **What to do**:
  - Make all data paths profile-configurable instead of hardcoded:
    - `src/traderbot/db/__init__.py` line 16: `Path.home() / ".traderbot" / "traderbot.db"` → accept `base_dir` parameter, default to `Path.home() / ".traderbot"`
    - `src/traderbot/db/vectors.py` line 22: `Path.home() / ".traderbot" / "chromadb"` → accept `base_dir` parameter
    - `src/traderbot/risk/circuit_breaker.py` line 37: already accepts `state_file` param — pass profile-specific path
    - `src/traderbot/risk/audit.py` line 14: already accepts `log_dir` param — pass profile-specific path
  - Add helper function `get_profile_base_dir(profile: TradingProfile | None) -> Path`:
    - If profile provided: `Path.home() / profile.base_dir` (e.g., `~/.traderbot-paper/`)
    - If None: `Path.home() / ".traderbot"` (backward compatible)
  - CLI initialization: when token resolved → profile loaded → pass base_dir to all components
  - Write TDD tests FIRST in `tests/profiles/test_data_isolation.py`:
    - Profile "paper" → DB path = `~/.traderbot-paper/traderbot.db`
    - Profile "live" → DB path = `~/.traderbot-live/traderbot.db`
    - No profile → DB path = `~/.traderbot/traderbot.db` (existing)
    - Profile dirs created automatically on first use

  **Must NOT do**:
  - Do NOT delete or migrate existing `~/.traderbot/` data
  - Do NOT change default behavior when no profile is active

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple files need coordinated changes, must maintain backward compatibility
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T7, T8, T10)
  - **Parallel Group**: Wave 2
  - **Blocks**: T11
  - **Blocked By**: T1

  **References**:

  **Pattern References**:
  - `src/traderbot/db/__init__.py:16` — Hardcoded `Path.home() / ".traderbot" / "traderbot.db"` that needs base_dir param
  - `src/traderbot/db/vectors.py:22` — Hardcoded `Path.home() / ".traderbot" / "chromadb"` that needs base_dir param
  - `src/traderbot/cli.py:440` — Hardcoded `Path.home() / ".traderbot"` that needs profile-aware variant

  **WHY Each Reference Matters**:
  - These are the EXACT lines that hardcode `~/.traderbot/`. Each must accept an optional base_dir that comes from the profile. Default must remain `~/.traderbot/` for backward compatibility.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_data_isolation.py
  - [ ] pytest tests/profiles/test_data_isolation.py → PASS (4+ tests)
  - [ ] Existing tests pass (no regression in default behavior)

  **QA Scenarios:**

  ```
  Scenario: Paper profile uses isolated DB
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_data_isolation.py::test_paper_db_path -v
    Expected Result: DB path is ~/.traderbot-paper/traderbot.db
    Failure Indicators: DB path still ~/.traderbot/traderbot.db
    Evidence: .sisyphus/evidence/task-9-isolated-db.txt

  Scenario: No profile uses default path
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_data_isolation.py::test_default_db_path -v
    Expected Result: DB path is ~/.traderbot/traderbot.db (unchanged)
    Failure Indicators: Default path changed
    Evidence: .sisyphus/evidence/task-9-default-path.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add per-profile data isolation plumbing (DB, ChromaDB, audit dirs)`
  - Files: `src/traderbot/db/__init__.py, src/traderbot/db/vectors.py, src/traderbot/profiles/paths.py, tests/profiles/test_data_isolation.py`
  - Pre-commit: `pytest tests/profiles/test_data_isolation.py`

- [x] 10. Token Auto-Injection into OpenClaw Agent TOOLS.md

  **What to do**:
  - Add injection logic to `src/traderbot/profiles/discovery.py` (or new `src/traderbot/profiles/injection.py`):
    - `inject_token(workspace_path: Path, token: str) -> bool` — write `TRADERBOT_PROFILE_TOKEN=<token>` into TOOLS.md
    - Parse existing TOOLS.md, find or create `## Environment` section
    - Add `TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4` line under Environment section
    - If token already exists (from previous assignment), replace it
    - `remove_token(workspace_path: Path) -> bool` — remove token line from TOOLS.md
    - Backup TOOLS.md before modification (`.tools.md.bak`)
  - Write TDD tests FIRST in `tests/profiles/test_injection.py`:
    - Inject token into TOOLS.md with Environment section → token added
    - Inject token into TOOLS.md without Environment section → section created + token added
    - Re-inject (replace existing token) → old token replaced, not duplicated
    - Remove token → line removed, section preserved
    - Missing TOOLS.md → returns False, no crash

  **Must NOT do**:
  - Do NOT modify any other workspace files (AGENTS.md, SOUL.md, etc.)
  - Do NOT corrupt TOOLS.md if injection fails mid-write

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: File manipulation with backup/rollback, needs careful edge case handling
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T7, T8, T9)
  - **Parallel Group**: Wave 2
  - **Blocks**: T16
  - **Blocked By**: T3, T6

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/TOOLS.md` — Target file. Current format has `## Environment` section with env var table. Add token line there.

  **WHY Each Reference Matters**:
  - `TOOLS.md`: The file the OpenClaw Gateway injects into agent sessions. Token MUST end up in this file's Environment section so the agent passes it as env var.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_injection.py
  - [ ] pytest tests/profiles/test_injection.py → PASS (5+ tests)

  **QA Scenarios:**

  ```
  Scenario: Inject token into TOOLS.md
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_injection.py::test_inject_token -v
    Expected Result: TOOLS.md contains TRADERBOT_PROFILE_TOKEN=<token> line
    Failure Indicators: Line missing, duplicate lines, file corrupted
    Evidence: .sisyphus/evidence/task-10-inject-token.txt

  Scenario: Replace existing token
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_injection.py::test_replace_token -v
    Expected Result: Only one TRADERBOT_PROFILE_TOKEN line with new value
    Failure Indicators: Two token lines, old value persists
    Evidence: .sisyphus/evidence/task-10-replace-token.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add token auto-injection into OpenClaw agent TOOLS.md`
  - Files: `src/traderbot/profiles/injection.py, tests/profiles/test_injection.py`
  - Pre-commit: `pytest tests/profiles/test_injection.py`

- [x] 11. Profile-Aware Config Loading

  **What to do**:
  - Create profile-aware config initialization flow:
    - When `TRADERBOT_PROFILE_TOKEN` env var is set at CLI startup:
      1. `resolve_token(token)` → get agent_name + TradingProfile
      2. Create `AgentRiskLimits` from profile risk params
      3. Create `KeyringKalshiConfig` subclass or factory that uses `ProfileAuthStore` for credential resolution
      4. Resolve base_dir from profile → pass to all DB/component initialization
      5. Freeze the resolved config — no re-reading during the session
    - When no token: use existing global config (backward compatible)
  - Update `src/traderbot/kalshi/config.py`:
    - Add `ProfileKalshiConfig` that accepts `profile_name` and uses `ProfileAuthStore` resolution chain
    - `resolve_api_key()` → checks profile keyring first, then global, then env
  - Create a `ProfileContext` object that bundles all resolved profile state:
    - profile: TradingProfile
    - agent_limits: AgentRiskLimits
    - config: ProfileKalshiConfig
    - base_dir: Path
    - agent_name: str
  - Write TDD tests FIRST in `tests/profiles/test_config_loading.py`:
    - Token set → ProfileContext created with correct profile
    - No token → uses global config (backward compatible)
    - Profile with Kalshi API key override → uses profile key, not global
    - Profile demo_mode=True → config resolves to demo URL
    - Profile demo_mode=False → config resolves to production URL

  **Must NOT do**:
  - Do NOT allow config re-resolution after initial load (frozen for session lifetime)
  - Do NOT break existing config loading when no profile is active

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integration point that ties all profile components together, needs careful design
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: T12, T13
  - **Blocked By**: T1, T5, T9

  **References**:

  **Pattern References**:
  - `src/traderbot/kalshi/config.py:KeyringKalshiConfig` — The config class to extend with profile awareness
  - `src/traderbot/cli.py` — Where profile context gets initialized at startup

  **API/Type References**:
  - `src/traderbot/profiles/tokens.py:resolve_token()` (T3) — To get profile from token
  - `src/traderbot/risk/agent_limits.py:AgentRiskLimits` (T4) — To create from profile risk params
  - `src/traderbot/profiles/auth.py:ProfileAuthStore` (T5) — For credential resolution chain
  - `src/traderbot/profiles/paths.py` (T9) — For base_dir resolution

  **WHY Each Reference Matters**:
  - `config.py:KeyringKalshiConfig`: This is the config that every API call uses. ProfileKalshiConfig must compose/extend it to add profile-specific auth resolution while preserving the existing `active_url` and `resolve_api_key` interface.

  **Acceptance Criteria**:

  - [ ] Test file created: tests/profiles/test_config_loading.py
  - [ ] pytest tests/profiles/test_config_loading.py → PASS (5+ tests)
  - [ ] Existing integration tests pass

  **QA Scenarios:**

  ```
  Scenario: Profile context with token
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_config_loading.py::test_profile_context_from_token -v
    Expected Result: ProfileContext has correct profile, limits, config, base_dir
    Failure Indicators: Missing fields, wrong profile, config still global
    Evidence: .sisyphus/evidence/task-11-profile-context.txt

  Scenario: No token uses global config
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/profiles/test_config_loading.py::test_no_token_global_config -v
    Expected Result: Uses KeyringKalshiConfig with default settings
    Failure Indicators: ProfileContext created without token, crash
    Evidence: .sisyphus/evidence/task-11-global-fallback.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add profile-aware config loading with auth resolution chain`
  - Files: `src/traderbot/profiles/context.py, src/traderbot/kalshi/config.py, tests/profiles/test_config_loading.py`
  - Pre-commit: `pytest tests/profiles/test_config_loading.py`

- [x] 12. Systemd Service Template

  **What to do**:
  - Create `install/services/traderbot-agent@.service` — systemd template unit:
    - Template parameter: `%i` = agent name (e.g., `traderbot-agent@molty.service`)
    - `ExecStart=/usr/bin/env traderscan agent-loop --agent %i` (or equivalent)
    - `Restart=on-failure`, `RestartSec=30`
    - `WantedBy=default.target` (user service, not system)
    - `Environment=TRADERBOT_PROFILE_TOKEN=` (resolved from profile assignment)
    - Service runs as the user, NOT root
    - Boot persistence: `loginctl enable-linger <username>` ensures services start at boot
  - Create `install/services/install-service.sh` — helper script:
    - Takes agent name as argument
    - Resolves profile assignment token
    - Writes instance-specific `.service` file with token env var
    - `systemctl --user enable traderbot-agent@<agent>.service`
  - Write tests in `tests/install/test_systemd.py`:
    - Template file is valid systemd unit syntax
    - install-service.sh passes shellcheck
    - Generated instance file has correct token env var

  **Must NOT do**:
  - Do NOT create system-level services (requires root)
  - Do NOT hardcode tokens in the template file (use instance override)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard systemd template, well-established pattern
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T13, T14)
  - **Parallel Group**: Wave 3
  - **Blocks**: T15
  - **Blocked By**: T8, T11

  **References**:

  **External References**:
  - systemd documentation: `man systemd.unit`, `man systemd.service`
  - `loginctl enable-linger` — enables user services at boot without login

  **WHY Each Reference Matters**:
  - User services + loginctl is the correct pattern for "run at boot without user login" without root.

  **Acceptance Criteria**:

  - [ ] Template file exists: install/services/traderbot-agent@.service
  - [ ] shellcheck install/services/install-service.sh → PASS
  - [ ] Template contains `WantedBy=default.target` and `Restart=on-failure`

  **QA Scenarios:**

  ```
  Scenario: Template is valid systemd unit
    Tool: Bash
    Steps:
      1. systemd-analyze verify install/services/traderbot-agent@.service 2>&1 || true
      2. grep -c "ExecStart" install/services/traderbot-agent@.service
    Expected Result: Template has valid unit structure with ExecStart
    Failure Indicators: Missing required systemd directives
    Evidence: .sisyphus/evidence/task-12-systemd-template.txt
  ```

  **Commit**: YES
  - Message: `feat(install): add systemd service template for per-agent persistence`
  - Files: `install/services/traderbot-agent@.service, install/services/install-service.sh`
  - Pre-commit: `shellcheck install/services/install-service.sh`

- [x] 13. Launchd Plist Template

  **What to do**:
  - Create `install/services/com.traderbot.agent.plist` — launchd template:
    - Template: agent name and token are placeholder strings (filled by install script)
    - `RunAtLoad=true`, `KeepAlive=true`
    - `Label=com.traderbot.<agent>`
    - `ProgramArguments` pointing to traderbot binary with agent args
    - `EnvironmentVariables` with TRADERBOT_PROFILE_TOKEN
    - `StandardOutPath` / `StandardErrorPath` for logging
  - Create `install/services/install-launchd.sh` — helper script:
    - Takes agent name as argument
    - Resolves profile token
    - Fills template with agent name + token
    - Copies to `~/Library/LaunchAgents/`
    - `launchctl load ~/Library/LaunchAgents/com.traderbot.<agent>.plist`
  - Write tests in `tests/install/test_launchd.py`:
    - Template file is valid plist XML
    - Script passes shellcheck
    - Generated plist has correct token

  **Must NOT do**:
  - Do NOT install to `/Library/LaunchDaemons/` (requires root)
  - Do NOT hardcode tokens in template

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard launchd plist template, well-established pattern
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T12, T14)
  - **Parallel Group**: Wave 3
  - **Blocks**: T15
  - **Blocked By**: T8, T11

  **References**:

  **External References**:
  - Apple developer docs: launchd plist format
  - `~/Library/LaunchAgents/` — user-level launch agents, no root needed

  **Acceptance Criteria**:

  - [ ] Template file exists: install/services/com.traderbot.agent.plist
  - [ ] Template is valid XML (xmllint --noout)
  - [ ] shellcheck install/services/install-launchd.sh → PASS

  **QA Scenarios:**

  ```
  Scenario: Template is valid plist XML
    Tool: Bash
    Steps:
      1. xmllint --noout install/services/com.traderbot.agent.plist
    Expected Result: No XML validation errors
    Failure Indicators: Malformed XML
    Evidence: .sisyphus/evidence/task-13-plist-valid.txt
  ```

  **Commit**: YES
  - Message: `feat(install): add launchd plist template for per-agent persistence`
  - Files: `install/services/com.traderbot.agent.plist, install/services/install-launchd.sh`
  - Pre-commit: `shellcheck install/services/install-launchd.sh`

- [x] 14. Installer: OS Detection + Dependency Installation

  **What to do**:
  - Create `install/traderbot-installer.sh` — lightweight shell script:
    - Phase 1: OS detection:
      - Detect Linux distro (Ubuntu/Debian, other), macOS version
      - Detect OpenClaw: check for `~/.openclaw/` directory + `openclaw` binary in PATH
      - If OpenClaw NOT found: print install instructions, EXIT with code 1
    - Phase 2: Dependency installation:
      - Linux: `sudo apt install build-essential python3-dev python3-venv gnome-keyring` (if headless)
      - macOS: check for Xcode CLI tools (`xcode-select -p`), install if missing; check for python3
    - Phase 3: TraderBot download and install:
      - Try public GitHub URL first: `curl -L https://github.com/{org}/TraderBot/archive/refs/heads/main.zip`
      - If 404/403: prompt for GitHub PAT, try: `curl -H "Authorization: token $PAT" https://api.github.com/repos/{org}/TraderBot/zipball/main`
      - Unzip, `pip install -e .` or `uv pip install -e .`
    - Idempotent: if TraderBot already installed, offer update instead of reinstall
  - Write tests in `tests/install/test_installer_detect.sh` (shellcheck + unit):
    - shellcheck passes on entire installer script
    - OS detection logic testable (mock uname output)
    - OpenClaw detection exits with code 1 when not found

  **Must NOT do**:
  - Do NOT run as root (use sudo only for apt install)
  - Do NOT install system-level services
  - Do NOT silently overwrite existing TraderBot installs

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multi-OS installer with detection logic, private repo auth, error recovery
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T12, T13, T15)
  - **Parallel Group**: Wave 3
  - **Blocks**: T16
  - **Blocked By**: None

  **References**:

  **External References**:
  - GitHub API: `https://api.github.com/repos/{org}/{repo}/zipball/main` — private repo download with PAT
  - `shellcheck` — bash script linter

  **WHY Each Reference Matters**:
  - GitHub zipball API supports private repos with PAT auth headers. This is the correct download mechanism.

  **Acceptance Criteria**:

  - [ ] Installer file exists: install/traderbot-installer.sh
  - [ ] shellcheck install/traderbot-installer.sh → PASS
  - [ ] Script exits with code 1 when OpenClaw not found

  **QA Scenarios:**

  ```
  Scenario: OpenClaw not found → script exits
    Tool: Bash
    Steps:
      1. PATH=/usr/bin:/bin HOME=/tmp bash install/traderbot-installer.sh 2>&1
      2. echo $? 
    Expected Result: Exit code 1, message about installing OpenClaw
    Failure Indicators: Exit code 0, script continues without OpenClaw
    Evidence: .sisyphus/evidence/task-14-openclaw-check.txt

  Scenario: Script passes shellcheck
    Tool: Bash
    Steps:
      1. shellcheck install/traderbot-installer.sh
    Expected Result: No warnings or errors
    Failure Indicators: Shellcheck failures
    Evidence: .sisyphus/evidence/task-14-shellcheck.txt
  ```

  **Commit**: YES
  - Message: `feat(install): add OS detection and dependency installation`
  - Files: `install/traderbot-installer.sh`
  - Pre-commit: `shellcheck install/traderbot-installer.sh`

- [x] 15. Installer: Persistence Setup

  **What to do**:
  - Add persistence setup to `install/traderbot-installer.sh`:
    - Linux: call `install-service.sh` for each assigned agent, enable linger
    - macOS: call `install-launchd.sh` for each assigned agent
    - Verify service is running after setup
    - Add `--uninstall` flag: stop + disable services, remove plist/unit files, preserve data
    - Add `--update` flag: stop services, pull latest from GitHub, restart services
  - Write tests in `tests/install/test_persistence.sh`:
    - --uninstall stops and disables services
    - --update pulls latest and restarts
    - Idempotent setup (run twice → no error)

  **Must NOT do**:
  - Do NOT delete data dirs on uninstall unless explicitly requested
  - Do NOT run as root

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Script additions to existing installer, follows established patterns
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T14)
  - **Parallel Group**: Wave 3
  - **Blocks**: T16
  - **Blocked By**: T12, T13

  **References**:

  **Pattern References**:
  - `install/services/install-service.sh` (T12) — Linux service installer to call
  - `install/services/install-launchd.sh` (T13) — macOS service installer to call

  **Acceptance Criteria**:

  - [ ] shellcheck install/traderbot-installer.sh → PASS (including new --uninstall/--update flags)
  - [ ] `--uninstall` flag disables and stops services

  **QA Scenarios:**

  ```
  Scenario: Uninstall disables services
    Tool: Bash
    Steps:
      1. bash install/traderbot-installer.sh --uninstall
      2. systemctl --user is-enabled traderbot-agent@molty.service 2>&1 || echo "disabled"
    Expected Result: Service is disabled after uninstall
    Failure Indicators: Service still enabled
    Evidence: .sisyphus/evidence/task-15-uninstall.txt
  ```

  **Commit**: YES
  - Message: `feat(install): add persistence setup (systemd + launchd)`
  - Files: `install/traderbot-installer.sh, tests/install/test_persistence.sh`
  - Pre-commit: `shellcheck install/traderbot-installer.sh`

- [x] 16. Installer: Config Flow + Token Injection

  **What to do**:
  - Add interactive config flow to `install/traderbot-installer.sh`:
    - Phase: Profile creation:
      - Prompt: "Create a trading profile? (y/n)"
      - Prompt for: name, mode (paper/live), categories, risk params
      - Call `traderbot profile create ...` with user inputs
    - Phase: API key setup:
      - Prompt for each required credential per profile
      - Call `traderbot profile set-auth <profile> <service> <key>`
    - Phase: Agent assignment:
      - Run `traderbot profile discover-agents` to list available agents
      - Prompt: "Assign which agent to which profile?"
      - Call `traderbot profile assign <agent> <profile>` — this generates token AND auto-injects into TOOLS.md
      - Warn: "Agent workspace files will be updated. Existing token will be replaced."
    - Phase: Verification:
      - For each assigned agent: `TRADERBOT_PROFILE_TOKEN=<token> traderbot heartbeat --json`
      - If heartbeat fails: print error, offer to reconfigure
  - Write tests in `tests/install/test_config_flow.sh`:
    - Config flow creates profile, sets auth, assigns agent
    - Agent discovery shows available agents
    - Heartbeat verification succeeds

  **Must NOT do**:
  - Do NOT skip verification step
  - Do NOT silently overwrite agent workspace without warning

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Interactive CLI flow with multiple phases, validation, and integration with all previous modules
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (last task in wave)
  - **Blocks**: T17
  - **Blocked By**: T10, T14, T15

  **References**:

  **API/Type References**:
  - `src/traderbot/profiles/tokens.py` (T3) — Token generation called by profile assign
  - `src/traderbot/profiles/injection.py` (T10) — Token injection into TOOLS.md
  - `src/traderbot/profiles/discovery.py` (T6) — Agent discovery

  **Acceptance Criteria**:

  - [ ] shellcheck install/traderbot-installer.sh → PASS
  - [ ] Config flow creates profile, sets auth, assigns agent, verifies heartbeat

  **QA Scenarios:**

  ```
  Scenario: Full config flow
    Tool: Bash (interactive)
    Steps:
      1. bash install/traderbot-installer.sh (with mock inputs via here-doc)
      2. Verify profile exists: traderbot profile list
      3. Verify assignment: traderbot profile assignments
      4. Verify token in TOOLS.md: grep TRADERBOT_PROFILE_TOKEN .openclaw/workspace/TOOLS.md
    Expected Result: Profile created, agent assigned, token injected
    Failure Indicators: Missing profile, no assignment, token not in TOOLS.md
    Evidence: .sisyphus/evidence/task-16-config-flow.txt
  ```

  **Commit**: YES
  - Message: `feat(install): add config flow with profile-agent mapping and token injection`
  - Files: `install/traderbot-installer.sh, tests/install/test_config_flow.sh`
  - Pre-commit: `shellcheck install/traderbot-installer.sh`

- [x] 17. Full Documentation Rebuild

  **What to do**:
  - After ALL implementation tasks complete, conduct line-by-line code audit:
    - Read every Python module in `src/traderbot/profiles/`
    - Read every modified file in `src/traderbot/risk/`, `src/traderbot/cli.py`, `src/traderbot/db/`, `src/traderbot/kalshi/config.py`
    - Read installer scripts in `install/`
    - Compare against existing docs in `docs/`
  - Rebuild documentation from ground up:
    - `docs/profiles.md` — Profile system architecture, TradingProfile model, registry, token handshake
    - `docs/risk.md` — Update with AgentRiskLimits, profile-aware evaluate_trade(), category filtering
    - `docs/deployment.md` — Installer guide, Ubuntu + macOS setup, persistence, config flow
    - `docs/security.md` — Threat model, token handshake security, keyring encryption, enforcement layers
    - `docs/api.md` — Update CLI command reference with profile commands
    - Update `README.md` with multi-agent deployment section
    - Update `AGENTS.md` with profile-aware trading rules
    - Update `skills/traderbot/SKILL.md` with new profile commands and TRADERBOT_PROFILE_TOKEN env var
    - Update `ROADMAP_PROGRESS.md` with completion status

  **Must NOT do**:
  - Do NOT start this until ALL implementation tasks are complete
  - Do NOT document features that aren't implemented
  - Do NOT leave outdated documentation unupdated

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation-heavy task requiring code audit and clear technical writing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after ALL implementation)
  - **Blocks**: F1-F4
  - **Blocked By**: ALL previous tasks

  **References**:

  **Pattern References**:
  - `docs/` — Current documentation structure to follow/update
  - `ROADMAP_PROGRESS.md` — Progress tracking file to update
  - `AGENTS.md` — Project conventions to follow for doc style
  - `skills/traderbot/SKILL.md` — OpenClaw skill definition to update

  **Acceptance Criteria**:

  - [ ] All new/modified modules have corresponding doc sections
  - [ ] CLI reference includes all profile subcommands
  - [ ] Security docs cover threat model + enforcement layers
  - [ ] Deployment docs cover Ubuntu + macOS install flow
  - [ ] No orphaned references to old hardcoded paths

  **QA Scenarios:**

  ```
  Scenario: Documentation covers all profile features
    Tool: Bash (grep)
    Steps:
      1. grep -c "profile" docs/profiles.md
      2. grep -c "TRADERBOT_PROFILE_TOKEN" docs/deployment.md
      3. grep -c "AgentRiskLimits" docs/risk.md
    Expected Result: All key terms documented
    Failure Indicators: Zero hits for key terms
    Evidence: .sisyphus/evidence/task-17-doc-coverage.txt
  ```

  **Commit**: YES
  - Message: `docs: rebuild all documentation from code audit`
  - Files: `docs/profiles.md, docs/risk.md, docs/deployment.md, docs/security.md, docs/api.md, README.md, AGENTS.md, skills/traderbot/SKILL.md, ROADMAP_PROGRESS.md`
  - Pre-commit: none (documentation only)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  - VERDICT: APPROVE (naming fixes applied)
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  - Shellcheck PASS | Tests 103 PASS | Clean YES | VERDICT: APPROVE
  Run linter + pytest. Review all changed files for: type safety, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  - Doc coverage complete (revoke IS documented at api.md:163) | VERDICT: APPROVE
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (profile + risk gate + data isolation together). Test edge cases: empty categories, revoked token, missing keyring.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  - Tasks compliant: 17/17 | Contamination: CLEAN | VERDICT: APPROVE
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **T1**: `feat(profiles): add TradingProfile model with risk params, categories, auth overrides`
- **T2**: `feat(profiles): add ProfileRegistry with encrypted keyring storage`
- **T3**: `feat(profiles): add token generation, resolution, and revocation`
- **T4**: `feat(risk): add AgentRiskLimits with HARD_LIMITS ceiling enforcement`
- **T5**: `feat(profiles): add per-profile auth store with keyring namespace`
- **T6**: `feat(profiles): add OpenClaw agent auto-discovery from IDENTITY.md`
- **T7**: `feat(risk): update evaluate_trade() for profile-aware risk gate and category filter`
- **T8**: `feat(cli): add profile management CLI commands`
- **T9**: `feat(profiles): add per-profile data isolation plumbing (DB, ChromaDB, audit dirs)`
- **T10**: `feat(profiles): add token auto-injection into OpenClaw agent TOOLS.md`
- **T11**: `feat(profiles): add profile-aware config loading with auth resolution chain`
- **T12**: `feat(install): add systemd service template for per-agent persistence`
- **T13**: `feat(install): add launchd plist template for per-agent persistence`
- **T14**: `feat(install): add OS detection and dependency installation`
- **T15**: `feat(install): add persistence setup (systemd + launchd)`
- **T16**: `feat(install): add config flow with profile-agent mapping and token injection`
- **T17**: `docs: rebuild all documentation from code audit`

---

## Success Criteria

### Verification Commands
```bash
pytest tests/profiles/ -v                          # All profile tests pass
pytest tests/risk/test_agent_limits.py -v           # Risk ceiling enforcement passes
traderbot profile list                              # Lists configured profiles
traderbot profile show aggressive-paper --json      # Returns profile details
traderbot profile assignments                       # Shows agent-token-profile mapping
TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4 traderbot scan --json  # Resolves token to profile
shellcheck install/traderbot-installer.sh           # Installer passes lint
systemctl --user status traderbot-molty.service     # Service active (Linux)
launchctl list | grep traderbot                     # Agent loaded (macOS)
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] Agent cannot change profile at runtime (proven by tests)
- [x] Agent cannot exceed HARD_LIMITS via profile params (proven by tests)
- [x] Profile category filter rejects disallowed markets (proven by tests)
- [x] Per-profile auth overrides work (proven by tests)
- [x] Installer runs successfully on fresh Ubuntu + macOS
- [x] Documentation matches code