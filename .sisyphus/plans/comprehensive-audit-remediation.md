# Comprehensive Audit Remediation Plan

## TL;DR

> **Quick Summary**: Fix 5 CRITICAL Kalshi API issues (auth, URLs, WebSocket, order fields, endpoint paths), remediate 12 HIGH and 10 MEDIUM codebase findings, close 7 OpenClaw integration gaps, and clean up 10+ minor issues. All automated work runs in isolated sessions — the main session is never blocked.
> 
> **Deliverables**:
> - Fixed Kalshi client with RSA-PSS auth and correct API endpoints
> - Working WebSocket with HTTP-header auth and correct subscribe format
> - Corrected order creation with `action`/`count`/`yes_price` fields
> - Missing API surface: portfolio, events, historical endpoints
> - OpenClaw integration aligned with official docs (cron delivery, SKILL.md gating, workspace files)
> - Internal code quality fixes (Brier score, Sharpe ratio, effective_limit, rate limiter, dead code)
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: Task 0.1 → 0.2 → 0.3 → 0.4 → Wave 1 → Wave 2 → Integration → Final

---

## Context

### Original Request
Do a comprehensive read through of: (1) TraderBot entire codebase, (2) Kalshi API docs, (3) NewsAPI docs, (4) OpenClaw API docs. Ensure correct and full implementation of all program logic and API usage. Identify areas for improvement and plan for implementation.

### Interview Summary
**Key Decisions**:
- **OpenClaw heartbeat architecture**: User explicitly chose to keep ALL automated work (heartbeat, cron, decision loops) in isolated sessions. The main session must ALWAYS remain available for user input. "The User is King, Their Voice SHALL ALWAYS be heard." — This overrides the OpenClaw-recommended main-session heartbeat pattern.
- **Auth migration**: RSA-PSS signed headers replace session-token auth. Breaking change → v0.10.00.
- **Test strategy**: TDD for critical auth changes; tests-after for others. pytest with async support already exists.

**Research Findings**:
- `kalshi-starter-code-python/clients.py` in repo confirms all 5 CRITICAL findings and demonstrates correct auth, URLs, and WebSocket protocol
- OpenClaw docs at https://docs.openclaw.ai/ reveal 7 integration gaps not in original audit
- NewsAPI rate-limit headers not captured for proactive throttling

### Metis Review
**Identified Gaps** (addressed):
- OpenClaw audit coverage was dangerously thin → added OC1-OC7 findings
- NewsAPI coverage light → added N5 (rate-limit headers)
- Plan format was a findings doc, not executable → converted to Prometheus format with QA scenarios
- QA scenarios missing for most tasks → added for every task
- No Final Verification Wave → added F1-F4

---

## Work Objectives

### Core Objective
Make TraderBot fully functional against the real Kalshi API, align all external API integrations with their official docs, and fix internal code quality issues identified during the comprehensive audit.

### Concrete Deliverables
- `src/traderbot/kalshi/signing.py` — new RSA-PSS auth module
- Fixed `client.py`, `config.py`, `websocket.py`, `trading.py`, `models.py`, `markets.py`, `history.py`
- New `src/traderbot/kalshi/portfolio.py`, `src/traderbot/kalshi/events.py`
- Updated `cron_loops.py`, `cli.py` (cron setup, OpenClaw config paths)
- Updated `skills/traderbot/SKILL.md` (env var names after auth migration)
- Fixed `engine.py`, `paper_trader.py`, `simulation/profiles.py`, `analysis/portfolio.py`
- Deleted `simulation/models.py`, `EXAMPLE_TESTING_PROMPT.md`

### Definition of Done
- [ ] `pytest` passes with 0 failures
- [ ] `ruff check` passes with 0 errors
- [ ] `mypy` or `pyright` type-check passes (if configured)
- [ ] All CRITICAL/HIGH findings verified fixed via agent QA scenarios

### Must Have
- RSA-PSS auth working against real Kalshi API (demo mode for testing)
- Correct base URLs (`api.elections.kalshi.com` for prod, `demo-api.kalshi.co` for demo)
- WebSocket auth via HTTP headers, not JSON message
- Order creation with `action`/`count`/`yes_price` fields
- All automated work in isolated sessions — main session NEVER blocked
- Breaking auth change tagged as v0.10.00

### Must NOT Have (Guardrails)
- **NEVER** adopt `kalshi_python_async` SDK (requires Python ≥3.13, pinned <3.13)
- **NEVER** modify `HARD_LIMITS` in risk module without explicit human approval
- **NEVER** run automated loops in the main session (user interaction always wins)
- **NEVER** auto-edit files in `docs/` without explicit human approval
- **NEVER** commit `.env` or credentials
- No AI slop: no obvious comments, boilerplate docstrings, over-abstraction, generic names
- No scope creep beyond identified findings — no new features, no "while we're here" refactors

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest with async support)
- **Automated tests**: Tests-after (TDD for critical auth changes Task 0.2)
- **Framework**: pytest

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash — `pytest`, `python -c`, import verification
- **API endpoints**: Use Bash (curl against demo API or mock)
- **CLI commands**: Use Bash — run `traderbot` CLI with args
- **Config/docs**: Use Bash/Grep — verify file contents, patterns

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Sequential — blocks everything, auth foundation):
├── Task 0.1: Fix Base URLs [quick]
├── Task 0.2: RSA-PSS Auth + Credential Migration [deep]
├── Task 0.3: Fix WebSocket Auth + Protocol [deep]
└── Task 0.4: Fix Order Creation Fields [deep]

Wave 1 (Parallel after Wave 0 — endpoint + model corrections):
├── Task 1.1: Fix Trades Endpoint Path [quick]
├── Task 1.2: Fix Market Model Fields [deep]
├── Task 1.3: Fix Historical Endpoints [deep]
├── Task 1.4: Add DELETE Method to KalshiClient [quick]
└── Task 1.5: Fix _normalize_trade Timestamp Fallback [quick]

Wave 2 (Parallel after Wave 1 — missing endpoints + OpenClaw + NewsAPI):
├── Task 2.1: Add Portfolio Endpoints [deep]
├── Task 2.2: Add Events Endpoints [deep]
├── Task 2.3: Add list_markets Query Parameters [quick]
├── Task 2.4: Add NewsAPI /everything Endpoint [deep]
├── Task 2.5: NewsAPI Error Checking + Auth Header [quick]
├── Task 2.6: NewsAPI Rate-Limit Header Capture [quick]
├── Task 2.7: Fix OpenClaw Cron Delivery + Session Logic [deep]
├── Task 2.8: Fix SKILL.md Gating After Auth Migration [quick]
└── Task 2.9: Fix injection.py Wrong Finding Reference [quick]

Wave 3 (Independent — internal code quality, parallel with any wave):
├── Task 3.1: Implement Real Brier Score [deep]
├── Task 3.2: Wire PaperTrader Through evaluate_trade() [deep]
├── Task 3.3: Fix effective_limit Floor Thresholds [quick]
├── Task 3.4: Delete simulation/models.py Dead Code [quick]
├── Task 3.5: Unify NewsSource Enum [quick]
├── Task 3.6: Replace Semaphore Rate Limiter with Token Bucket [deep]
├── Task 3.7: Fix Sharpe Ratio N→N-1 [quick]
├── Task 3.8: Fix Orderbook Key Names + Remove Fallback [quick]
├── Task 3.9: Centralize Path.home() / ".traderbot" into paths.py [quick]
└── Task 3.10: Fix OpenClaw Config Path in cli.py [quick]

Wave 4 (Batch at end — cleanup):
├── Task 4.1: Require --channel/--to with --announce in cron [quick]
├── Task 4.2: Update ROADMAP_PROGRESS.md version [quick]
├── Task 4.3: Fix docs/news-sentiment.md rate limit — REQUIRES HUMAN APPROVAL [quick]
├── Task 4.4: Delete EXAMPLE_TESTING_PROMPT.md [quick]
├── Task 4.5: Remove # Made with Bob from injection.py:173 [quick]
├── Task 4.6: Fix cron hour range 9-15 → 9-16 [quick]
├── Task 4.7: Remove dead return from _process_signals [quick]
├── Task 4.8: Document Twitter source stub as not implemented [quick]
├── Task 4.9: Document signals CLI command as stub [quick]
└── Task 4.10: Resolve simulation/strategies/ directory mismatch — REQUIRES HUMAN APPROVAL [quick]

Wave 5 (Documentation — requires human approval per AGENTS.md):
├── Task 5.1: Update docs/kalshi.md — REQUIRES HUMAN APPROVAL [writing]
└── Task 5.2: Update docs/simulation.md — REQUIRES HUMAN APPROVAL [writing]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan Compliance Audit [oracle]
├── Task F2: Code Quality Review [unspecified-high]
├── Task F3: Real Manual QA [unspecified-high]
└── Task F4: Scope Fidelity Check [deep]
→ Present results → Get explicit user okay

Critical Path: 0.1 → 0.2 → 0.3 → 0.4 → 1.1-1.5 → 2.1-2.9 → F1-F4 → user okay
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 10 (Wave 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|---|---|---|---|
| 0.1 | — | 0.2, 0.3 | 0 |
| 0.2 | 0.1 | 0.3, 2.8 | 0 |
| 0.3 | 0.2 | Wave 1 | 0 |
| 0.4 | — | Wave 1 | 0 |
| 1.1-1.5 | Wave 0 | Wave 2 | 1 |
| 2.1-2.9 | Wave 1 | Wave 4, 5 | 2 |
| 3.1-3.10 | — | — | 3 (parallel with any) |
| 4.1-4.10 | Wave 2, 3 | Wave 5 | 4 |
| 5.1-5.2 | Wave 4 | F1-F4 | 5 |
| F1-F4 | All | — | FINAL |

### Agent Dispatch Summary

- **Wave 0**: 4 tasks — T0.1 → `quick`, T0.2 → `deep`, T0.3 → `deep`, T0.4 → `deep`
- **Wave 1**: 5 tasks — T1.1 → `quick`, T1.2 → `deep`, T1.3 → `deep`, T1.4 → `quick`, T1.5 → `quick`
- **Wave 2**: 9 tasks — T2.1-2.2 → `deep`, T2.3-2.6 → `quick`, T2.7 → `deep`, T2.8-2.9 → `quick`
- **Wave 3**: 10 tasks — T3.1,3.2,3.6 → `deep`, rest → `quick`
- **Wave 4**: 10 tasks — all `quick`
- **Wave 5**: 2 tasks — `writing`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 0.1. Fix Base URLs (C2 + C3 partial)

  **What to do**:
  - Change `api.kalshi.co` → `api.elections.kalshi.com` in `client.py:41`, `config.py:44`
  - Change WebSocket URL `wss://api.kalshi.co` → `wss://api.elections.kalshi.com` in `websocket.py:27`
  - Keep `demo-api.kalshi.co` URLs unchanged (confirmed correct by starter code)
  - Reference: `kalshi-starter-code-python/clients.py:42` (demo), `clients.py:45` (prod)

  **Must NOT do**:
  - Do NOT change demo URLs
  - Do NOT modify any auth logic (that's Task 0.2)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (blocks 0.2)
  - **Parallel Group**: Wave 0 (sequential first)
  - **Blocks**: Task 0.2, Task 0.3
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/client.py:41` — Current wrong `base_url`
  - `src/traderbot/kalshi/config.py:44-45` — Config defaults
  - `src/traderbot/kalshi/websocket.py:27-28` — WebSocket URL
  - `kalshi-starter-code-python/clients.py:42,45` — Reference: correct URLs

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(); assert 'elections.kalshi.com' in c.base_url"` passes
  - [ ] `python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(demo_mode=True); assert 'demo-api.kalshi.co' in c.base_url"` passes

  **QA Scenarios**:

  ```
  Scenario: Production URL is correct
    Tool: Bash
    Preconditions: Package installed/editable
    Steps:
      1. python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(); print(c.base_url)"
      2. Assert output contains "api.elections.kalshi.com"
    Expected Result: Output contains "api.elections.kalshi.com"
    Failure Indicators: Output contains "api.kalshi.co"
    Evidence: .sisyphus/evidence/task-0.1-prod-url.txt

  Scenario: Demo URL preserved
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(demo_mode=True); print(c.base_url)"
      2. Assert output contains "demo-api.kalshi.co"
    Expected Result: Output contains "demo-api.kalshi.co"
    Evidence: .sisyphus/evidence/task-0.1-demo-url.txt
  ```

  **Commit**: YES
  - Message: `fix(kalshi): correct base URLs to api.elections.kalshi.com`
  - Files: `client.py, config.py, websocket.py`

- [x] 0.2. RSA-PSS Auth + Credential Migration (C1 — BREAKING v0.10.00)

  **What to do**:
  - Create `src/traderbot/kalshi/signing.py` with:
    - `sign_request(private_key_pem: str, timestamp_ms: int, method: str, path: str) -> str` using `cryptography` PSS/SHA256/MGF1
    - `auth_headers(api_key: str, private_key_pem: str, method: str, path: str) -> dict[str, str]` returning 3 headers
    - Reference: `kalshi-starter-code-python/clients.py:50-83`
  - Modify `KalshiConfig` and `KeyringKalshiConfig`: Remove `api_secret`, add `private_key_pem: SecretStr | None`, `private_key_path: Path | None`, `resolve_private_key() -> str`
  - Modify `KalshiClient`: Remove `login()` and `_session_token`, `_request()` calls `signing.auth_headers()` per-request, keep 401/403 → `AuthenticationError`
  - Modify `demo.py:22-26`: Change `KalshiConfig(api_key="demo", api_secret="demo")` to handle demo auth separately
  - Modify `cli.py:1670`: Change `service_keys["kalshi"]` from `["api_key", "api_secret"]` to `["api_key", "private_key_pem"]`
  - Modify `auth.py:15-16,207-210`: Change required services and env mapping from `api_secret` to `private_key_pem`
  - Modify `profiles/config.py`, `profiles/auth.py`: Update credential resolution for private_key_pem
  - Version: v0.10.00 (breaking config change)

  **Must NOT do**:
  - Do NOT adopt `kalshi_python_async` SDK
  - Do NOT modify demo URL
  - Do NOT change WebSocket auth (that's Task 0.3)
  - Do NOT commit real private keys

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (blocks 0.3, 2.8)
  - **Parallel Group**: Wave 0 (sequential after 0.1)
  - **Blocks**: Task 0.3, Task 2.8
  - **Blocked By**: Task 0.1

  **References**:
  - `kalshi-starter-code-python/clients.py:50-67` — auth_headers reference: KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP
  - `kalshi-starter-code-python/clients.py:69-83` — sign_request reference: PSS/SHA256/MGF1, salt_length=digest_length
  - `src/traderbot/kalshi/client.py:92-180` — Current login()+session-token auth to replace
  - `src/traderbot/kalshi/config.py:39-49` — Current api_secret field to replace
  - `src/traderbot/kalshi/auth.py:15-16,207-210` — Required services and env mapping
  - `src/traderbot/cli.py:1670` — auth_login service_keys
  - `src/traderbot/demo.py:22-26` — Demo config constructor
  - `src/traderbot/profiles/config.py` — resolve_kalshi_credentials()
  - `src/traderbot/profiles/auth.py` — Keyring namespace

  **Acceptance Criteria**:
  - [ ] `from traderbot.kalshi.signing import sign_request, auth_headers` imports succeed
  - [ ] `sign_request()` produces base64-encoded signature matching starter code vector
  - [ ] `auth_headers()` returns dict with exactly 3 keys: KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP
  - [ ] `KalshiClient` has no `login()` method
  - [ ] `KalshiConfig` has no `api_secret` field, has `private_key_pem` and `private_key_path`
  - [ ] `resolve_private_key()` chain: keyring → env → file → raise ConfigurationError
  - [ ] All existing tests pass (after updating fixtures)

  **QA Scenarios**:

  ```
  Scenario: sign_request produces valid base64 PSS signature
    Tool: Bash
    Preconditions: cryptography package installed
    Steps:
      1. Generate test RSA key pair: python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; key = rsa.generate_private_key(65537, 2048); print(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())"
      2. Call sign_request with known inputs and verify output is valid base64
    Expected Result: Base64 string, no exceptions
    Failure Indicators: Exception, empty output
    Evidence: .sisyphus/evidence/task-0.2-sign-request.txt

  Scenario: auth_headers returns 3 required headers
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.signing import auth_headers; h = auth_headers('test-key', TEST_PEM, 'GET', '/trade-api/v2/markets'); print(sorted(h.keys()))"
      2. Assert: ['KALSHI-ACCESS-KEY', 'KALSHI-ACCESS-SIGNATURE', 'KALSHI-ACCESS-TIMESTAMP']
    Expected Result: Exactly 3 headers with correct names
    Evidence: .sisyphus/evidence/task-0.2-auth-headers.txt

  Scenario: No login() method on KalshiClient
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.client import KalshiClient; assert not hasattr(KalshiClient, 'login'), 'login() still exists'"
    Expected Result: No AttributeError, assertion passes
    Evidence: .sisyphus/evidence/task-0.2-no-login.txt

  Scenario: Demo mode works without private_key_pem
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(demo_mode=True); print(c.base_url)"
    Expected Result: Demo URL printed, no ConfigurationError
    Failure Indicators: ConfigurationError raised
    Evidence: .sisyphus/evidence/task-0.2-demo-no-pem.txt
  ```

  **Commit**: YES
  - Message: `feat(kalshi): RSA-PSS auth replaces session-token auth [BREAKING v0.10.00]`
  - Files: `signing.py (new), client.py, config.py, auth.py, cli.py, demo.py, profiles/config.py, profiles/auth.py`

- [x] 0.3. Fix WebSocket Auth + Protocol (C3)

  **What to do**:
  - Rewrite `src/traderbot/kalshi/websocket.py`:
    - URLs: `wss://api.elections.kalshi.com/trade-api/ws/v2` (prod), `wss://demo-api.kalshi.co/trade-api/ws/v2` (demo)
    - Auth: HTTP headers during WebSocket handshake via `additional_headers` param, NOT JSON auth message
      - `headers = auth_headers(api_key, private_key_pem, "GET", "/trade-api/ws/v2")`
      - `websockets.connect(url, additional_headers=headers)`
    - Subscribe: `{"id": N, "cmd": "subscribe", "params": {"channels": ["ticker"], "market_ticker": "XXX"}}`
    - Unsubscribe: `{"id": N, "cmd": "unsubscribe", "params": {"channels": [...], "market_ticker": "XXX"}}`
    - Remove: `auth_approved` expectation, JSON auth message, `api_key`/`api_secret` in WebSocketConfig
    - Add: private_key_pem, ping/pong handler, subscription confirmation parsing
  - Reference: `kalshi-starter-code-python/clients.py:188-210`

  **Must NOT do**:
  - Do NOT add login() or session token to WebSocket
  - Do NOT change REST API URLs (done in 0.1)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on 0.2)
  - **Parallel Group**: Wave 0
  - **Blocks**: Wave 1
  - **Blocked By**: Task 0.1, Task 0.2

  **References**:
  - `kalshi-starter-code-python/clients.py:188-193` — WebSocket with `additional_headers=auth_headers`
  - `kalshi-starter-code-python/clients.py:203-210` — Subscribe format: `{"id": N, "cmd": "subscribe", "params": {...}}`
  - `src/traderbot/kalshi/websocket.py` (entire file) — Current wrong implementation
  - `src/traderbot/kalshi/signing.py` — Task 0.2 output: `auth_headers()` function

  **Acceptance Criteria**:
  - [ ] WebsocketConfig has no `api_key`/`api_secret` fields, uses `private_key_pem`
  - [ ] `_authenticate()` method removed or empty (auth is in HTTP headers now)
  - [ ] Subscribe message uses `"cmd": "subscribe"` with `"params"` dict
  - [ ] No `auth_approved` expectation in code

  **QA Scenarios**:

  ```
  Scenario: WebSocket config has no api_secret field
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.websocket import WebSocketConfig; assert not hasattr(WebSocketConfig, '__dataclass_fields__') or 'api_secret' not in WebSocketConfig.__dataclass_fields__, 'api_secret still in config'"
    Expected Result: No api_secret field
    Evidence: .sisyphus/evidence/task-0.3-no-api-secret.txt

  Scenario: Subscribe message has correct format
    Tool: Bash
    Steps:
      1. grep -n '"cmd".*subscribe' src/traderbot/kalshi/websocket.py
      2. Assert line contains "cmd" and "params" keys
    Expected Result: At least one match with correct format
    Failure Indicators: No match, or old "type": "subscribe" format
    Evidence: .sisyphus/evidence/task-0.3-subscribe-format.txt

  Scenario: No auth_approved expectation in code
    Tool: Bash
    Steps:
      1. grep -rn "auth_approved" src/traderbot/kalshi/websocket.py
      2. Assert no matches
    Expected Result: grep returns exit code 1 (no matches)
    Evidence: .sisyphus/evidence/task-0.3-no-auth-approved.txt
  ```

  **Commit**: YES
  - Message: `fix(kalshi): WebSocket auth via HTTP headers + correct subscribe format`
  - Files: `websocket.py`

- [x] 0.4. Fix Order Creation Fields (C4)

  **What to do**:
  - Modify `src/traderbot/kalshi/trading.py:28-34`: Body = `{ticker, action, side, count, yes_price}`
  - Modify `src/traderbot/kalshi/models.py:197-213` — `OrderRequest` model:
    - Add `action: Literal["buy", "sell"]` (required)
    - Keep `side: OrderSide` (yes/no)
    - `quantity: int` → `count: int` in API body
    - `price: int` → `yes_price: int` in API body (must be 1-99)
    - Add optional: `client_order_id: str | None`, `no_price: int | None`
  - `place_order()` body construction: send `{ticker, action, side, count, yes_price}`

  **Must NOT do**:
  - Do NOT remove `OrderType` enum (used internally)
  - Do NOT change cancel_order logic (separate concern)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 0 sequential)
  - **Parallel Group**: Wave 0
  - **Blocks**: Wave 1 (trading is used by integration tests)
  - **Blocked By**: None (can start immediately, parallel with 0.1-0.3 for code structure)

  **References**:
  - `src/traderbot/kalshi/trading.py:28-34` — Current wrong body construction
  - `src/traderbot/kalshi/models.py:197-213` — Current OrderRequest model
  - `kalshi-starter-code-python/clients.py` — Reference: correct order body format

  **Acceptance Criteria**:
  - [ ] `OrderRequest` model has `action: Literal["buy", "sell"]` field
  - [ ] `OrderRequest` model has `count: int` field (not `quantity`)
  - [ ] `place_order()` sends `yes_price` in body (not `price`)
  - [ ] `OrderRequest` model has optional `client_order_id` and `no_price`

  **QA Scenarios**:

  ```
  Scenario: OrderRequest requires action field
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.models import OrderRequest; try: OrderRequest(ticker='X', side='yes', count=1, yes_price=50); raise AssertionError('Should fail without action'); except Exception: pass"
    Expected Result: Validation error for missing action
    Failure Indicators: No exception raised
    Evidence: .sisyphus/evidence/task-0.4-action-required.txt

  Scenario: place_order body has correct field names
    Tool: Bash
    Steps:
      1. grep -A5 "place_order" src/traderbot/kalshi/trading.py
      2. Assert body contains "action", "count", "yes_price" keys
    Expected Result: Body construction uses correct field names
    Evidence: .sisyphus/evidence/task-0.4-order-body.txt
  ```

  **Commit**: YES
  - Message: `fix(kalshi): order creation uses action/count/yes_price fields`
  - Files: `trading.py, models.py`

- [x] 1.1. Fix Trades Endpoint Path (C5)

  **What to do**:
  - Change `GET /markets/{ticker}/trades` → `GET /markets/trades?ticker={ticker}` in `markets.py:81` and `history.py` (get_historical_trades, get_recent_trades)

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (parallel), Blocks: none, Blocked By: Wave 0

  **References**: `src/traderbot/kalshi/markets.py:81`, `src/traderbot/kalshi/history.py`

  **QA Scenarios**:
  ```
  Scenario: Trades endpoint uses query param
    Tool: Bash
    Steps:
      1. grep -n "markets/trades" src/traderbot/kalshi/markets.py
      2. Assert line contains "ticker=" as query param, not path segment
    Expected Result: Path is "/markets/trades" with "ticker" as query param
    Evidence: .sisyphus/evidence/task-1.1-trades-path.txt
  ```

- [x] 1.2. Fix Market Model Fields (H5)

  **What to do**:
  - `Market.state` → `Market.status` in `models.py:28`; add `@field_validator("status", mode="before")` accepting `state` as alias
  - Add `resting`/`canceled`/`executed` to `OrderStatus` enum with normalizer
  - Update `data_loader.py:134` from `market.state == "settled"` to `market.status == "settled"` (field_validator alias only works at parse time)
  - Update `history.py:72` from `{"state": "settled"}` to `{"status": "settled"}` as API query param

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 1 (parallel), Blocks: none, Blocked By: Wave 0

  **References**: `src/traderbot/kalshi/models.py:28`, `src/traderbot/kalshi/_normalize.py`, `src/traderbot/simulation/data_loader.py:134`, `src/traderbot/kalshi/history.py:72`

  **QA Scenarios**:
  ```
  Scenario: Market model accepts 'state' as alias for 'status'
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.models import Market; m = Market.model_validate({'state': 'open'}); print(m.status)"
      2. Assert: output is "open"
    Expected Result: "open" (alias works at parse time)
    Evidence: .sisyphus/evidence/task-1.2-status-alias.txt

  Scenario: No .state attribute access in data_loader
    Tool: Bash
    Steps:
      1. grep -n "\.state" src/traderbot/simulation/data_loader.py
      2. Assert: no matches for market.state
    Expected Result: grep returns exit code 1
    Evidence: .sisyphus/evidence/task-1.2-no-state-access.txt
  ```

- [x] 1.3. Fix Historical Endpoints (M9 + H2 partial)

  **What to do**:
  - In `history.py`: `get_cutoffs()` → `GET /historical/cutoffs`; `get_historical_trades()` → `GET /historical/trades?ticker=...`
  - Add `get_historical_markets()`, `get_historical_orders()`

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 1 (parallel), Blocks: none, Blocked By: Wave 0

  **References**: `src/traderbot/kalshi/history.py`

  **QA Scenarios**:
  ```
  Scenario: Historical endpoints use /historical/ prefix
    Tool: Bash
    Steps:
      1. grep -n "historical" src/traderbot/kalshi/history.py
      2. Assert: at least 3 endpoint paths with /historical/ prefix
    Expected Result: Multiple /historical/ endpoint paths
    Evidence: .sisyphus/evidence/task-1.3-historical-endpoints.txt
  ```

- [x] 1.4. Add DELETE Method to KalshiClient (M2 + A1)

  **What to do**:
  - Add `async def delete(self, path, **params)` to `client.py`
  - Update `cancel_order` in `trading.py:43` to use `self.delete()` instead of `self._request("DELETE", ...)`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (parallel), Blocks: none, Blocked By: Wave 0

  **References**: `src/traderbot/kalshi/client.py`, `src/traderbot/kalshi/trading.py:43`

  **QA Scenarios**:
  ```
  Scenario: delete() method exists on KalshiClient
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.client import KalshiClient; assert hasattr(KalshiClient, 'delete'), 'delete() missing'"
    Expected Result: No assertion error
    Evidence: .sisyphus/evidence/task-1.4-delete-method.txt

  Scenario: cancel_order uses self.delete()
    Tool: Bash
    Steps:
      1. grep -n "cancel_order" src/traderbot/kalshi/trading.py
      2. Assert: method body contains "self.delete" not "self._request"
    Expected Result: cancel_order calls self.delete()
    Evidence: .sisyphus/evidence/task-1.4-cancel-delete.txt
  ```

- [x] 1.5. Fix _normalize_trade Timestamp Fallback (M4 + A3)

  **What to do**:
  - Replace `raw.get("timestamp") or raw.get("created_time", 0)` in `_normalize.py:43` with explicit None check: `raw.get("timestamp") if raw.get("timestamp") is not None else raw.get("created_time", 0)`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (parallel), Blocks: none, Blocked By: Wave 0

  **References**: `src/traderbot/kalshi/_normalize.py:43`

  **QA Scenarios**:
  ```
  Scenario: Zero timestamp no longer falsy-falls through
    Tool: Bash
    Steps:
      1. python -c "raw = {'timestamp': 0, 'created_time': 123}; val = raw.get('timestamp') if raw.get('timestamp') is not None else raw.get('created_time', 0); assert val == 0, f'Expected 0, got {val}'"
    Expected Result: 0 (preserved, not replaced by 123)
    Evidence: .sisyphus/evidence/task-1.5-timestamp-zero.txt
  ```

- [x] 2.1. Add Portfolio Endpoints (H1)

  **What to do**:
  - Create `src/traderbot/kalshi/portfolio.py` with endpoints: `GET /portfolio/balance`, `GET /portfolio/positions`, `GET /portfolio/fills`, `GET /portfolio/settlements`
  - Create Pydantic models: `PortfolioBalance`, `Position`, `Fill`, `Settlement` with `ConfigDict(strict=True, extra="forbid")`

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: Wave 1

  **References**: `src/traderbot/kalshi/markets.py` — Pattern: endpoint methods on client, Pydantic response models

  **QA Scenarios**:
  ```
  Scenario: Portfolio module imports correctly
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.portfolio import PortfolioBalance, Position, Fill, Settlement; print('OK')"
    Expected Result: "OK"
    Evidence: .sisyphus/evidence/task-2.1-portfolio-imports.txt
  ```

- [x] 2.2. Add Events Endpoints (H3)

  **What to do**:
  - Create `src/traderbot/kalshi/events.py` with `GET /events`, `GET /events/{event_ticker}`
  - Create `Event` Pydantic model with `ConfigDict(strict=True, extra="forbid")`

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: Wave 1

  **References**: `src/traderbot/kalshi/markets.py` — Pattern reference

  **QA Scenarios**:
  ```
  Scenario: Events module imports correctly
    Tool: Bash
    Steps:
      1. python -c "from traderbot.kalshi.events import Event; print('OK')"
    Expected Result: "OK"
    Evidence: .sisyphus/evidence/task-2.2-events-imports.txt
  ```

- [x] 2.3. Add list_markets Query Parameters (H4)

  **What to do**:
  - Add params to `markets.py`: `event_ticker`, `series_ticker`, `min_close_ts`, `max_close_ts`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: Wave 1

  **References**: `src/traderbot/kalshi/markets.py`

  **QA Scenarios**:
  ```
  Scenario: list_markets accepts event_ticker param
    Tool: Bash
    Steps:
      1. grep -n "event_ticker" src/traderbot/kalshi/markets.py
      2. Assert: at least one match
    Expected Result: event_ticker parameter exists
    Evidence: .sisyphus/evidence/task-2.3-market-params.txt
  ```

- [ ] 2.4. Add NewsAPI /everything Endpoint (H6)

  **What to do**:
  - Add `_fetch_everything()` to `sources.py` using `GET /v2/everything` with `q`, `from`, `to`, `sortBy` params
  - Add pagination support (`page` param) for both `/top-headlines` and `/everything`
  - Wire into `fetch_recent()` based on query type

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: none

  **References**: `src/traderbot/news/sources.py:100-182` — Current _fetch_newsapi implementation

  **QA Scenarios**:
  ```
  Scenario: _fetch_everything method exists
    Tool: Bash
    Steps:
      1. python -c "from traderbot.news.sources import NewsAggregator; assert hasattr(NewsAggregator, '_fetch_everything'), 'missing _fetch_everything'"
    Expected Result: No assertion error
    Evidence: .sisyphus/evidence/task-2.4-everything-method.txt
  ```

- [x] 2.5. NewsAPI Error Checking + Auth Header (H7 + M6)

  **What to do**:
  - Check `status: "error"` in 200 responses before accessing `articles`
  - Change auth from query param `apiKey` to `X-Api-Key` header (while keeping query param as fallback for compatibility)
  - Add `X-Api-Key` header to `httpx.AsyncClient` default headers

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: none

  **References**: `src/traderbot/news/sources.py:106-147` — Current auth and error handling

  **QA Scenarios**:
  ```
  Scenario: Error status checked in NewsAPI response
    Tool: Bash
    Steps:
      1. grep -n '"status".*"error"' src/traderbot/news/sources.py
      2. Assert: at least one match checking for error status
    Expected Result: Error status check exists
    Evidence: .sisyphus/evidence/task-2.5-error-check.txt

  Scenario: X-Api-Key header used
    Tool: Bash
    Steps:
      1. grep -n "X-Api-Key" src/traderbot/news/sources.py
      2. Assert: at least one match
    Expected Result: X-Api-Key header sent
    Evidence: .sisyphus/evidence/task-2.5-auth-header.txt
  ```

- [x] 2.6. NewsAPI Rate-Limit Header Capture (N5)

  **What to do**:
  - Capture `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` from NewsAPI responses
  - Store on `NewsAggregator` for proactive throttling
  - Log warning when remaining < 10% of limit

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: none

  **References**: `src/traderbot/news/sources.py:117-119` — Current response handling where headers could be captured

  **QA Scenarios**:
  ```
  Scenario: Rate limit headers captured from response
    Tool: Bash
    Steps:
      1. grep -n "X-RateLimit" src/traderbot/news/sources.py
      2. Assert: at least one match
    Expected Result: Rate limit header parsing exists
    Evidence: .sisyphus/evidence/task-2.6-rate-limit.txt
  ```

- [x] 2.7. Fix OpenClaw Cron Delivery + Session Logic (OC1 + OC2 + OC5 + OC6)

  **What to do**:
  - Fix `cli.py` cron setup to require `--channel` + `--to` with `--announce` and validate channel format per OpenClaw docs (e.g. `telegram`, `whatsapp`, `slack` with proper `--to` format like E.164 for WhatsApp, chat ID for Telegram)
  - Fix `cron_loops.py:17` hour range `9-15` → `9-16` (captures full market hours 9:30-4:00 ET)
  - Fix `NewsLoopPayload` delivery: add `--wake now` for immediate delivery of systemEvent alerts, add optional `--channel`/`--to` for direct delivery
  - Ensure all cron jobs in `cli.py:2488-2530` are constructed as `--session isolated` with `--announce --channel <ch> --to <id>` for proper delivery per OpenClaw cron docs
  - **Guardrail**: The main session is NEVER used for automated work. User input always wins. Verify no cron/heartbeat schedules target `--session main` for autonomous work.

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: none

  **References**:
  - `src/traderbot/cron_loops.py` — Cron loop definitions
  - `src/traderbot/cli.py:2448-2530` — Cron setup command
  - OpenClaw docs: `https://docs.openclaw.ai/automation/cron-jobs.md` — Delivery format: `--announce --channel telegram --to "+15555550123"`

  **QA Scenarios**:
  ```
  Scenario: Cron setup requires --channel with --announce
    Tool: Bash
    Steps:
      1. grep -A10 "announce" src/traderbot/cli.py | head -20
      2. Assert: --announce is accompanied by --channel and --to in cron setup code
    Expected Result: All announce instances have channel+to
    Evidence: .sisyphus/evidence/task-2.7-cron-delivery.txt

  Scenario: No cron targets --session main for autonomous work
    Tool: Bash
    Steps:
      1. grep -n "session.*main" src/traderbot/cron_loops.py
      2. Assert: Any "main" session target is ONLY for systemEvent (user alerts), not autonomous work
    Expected Result: main session only used for user-facing systemEvent, never for agentTurn
    Evidence: .sisyphus/evidence/task-2.7-session-isolation.txt

  Scenario: Cron hour range is 9-16
    Tool: Bash
    Steps:
      1. grep -n "9-15" src/traderbot/cron_loops.py
      2. Assert: no matches (changed to 9-16)
      3. grep -n "9-16" src/traderbot/cron_loops.py
      4. Assert: at least one match
    Expected Result: 9-15 gone, 9-16 present
    Evidence: .sisyphus/evidence/task-2.7-cron-hours.txt
  ```

- [x] 2.8. Fix SKILL.md Gating After Auth Migration (OC6)

  **What to do**:
  - Update `skills/traderbot/SKILL.md:7` env list from `["KALSHI_API_KEY", "KALSHI_PRIVATE_KEY"]` to `["KALSHI_API_KEY", "KALSHI_PRIVATE_KEY_PEM"]`
  - Ensure `KALSHI_API_KEY` remains `primaryEnv`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: Task 0.2

  **References**: `skills/traderbot/SKILL.md:1-10` — Frontmatter with gating

  **QA Scenarios**:
  ```
  Scenario: SKILL.md requires KALSHI_PRIVATE_KEY_PEM
    Tool: Bash
    Steps:
      1. grep "KALSHI_PRIVATE_KEY_PEM" skills/traderbot/SKILL.md
      2. Assert: at least one match
    Expected Result: KALSHI_PRIVATE_KEY_PEM in env list
    Evidence: .sisyphus/evidence/task-2.8-skill-gating.txt
  ```

- [x] 2.9. Fix injection.py Wrong Finding Reference (OC7)

  **What to do**:
  - Remove `# Made with Bob` from `src/traderbot/profiles/injection.py:173` (plan 4.5 references wrong file `agent_limits.py:92`)

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 2 (parallel), Blocks: none, Blocked By: none

  **References**: `src/traderbot/profiles/injection.py:173`

  **QA Scenarios**:
  ```
  Scenario: No "Made with Bob" comment in injection.py
    Tool: Bash
    Steps:
      1. grep -n "Made with Bob" src/traderbot/profiles/injection.py
      2. Assert: exit code 1 (no matches)
    Expected Result: Comment removed
    Evidence: .sisyphus/evidence/task-2.9-no-bob.txt
  ```

- [x] 3.1. Implement Real Brier Score (H9)

  **What to do**:
  - Replace `engine.py:384` hardcoded `brier_score = 0.25 if closed_trades else None` with proper Brier score computation: `mean((predicted - actual)^2)` where predicted is the price/100 and actual is 1 or 0
  - Compute `edge_capture` (fraction of theoretical edge realized) and `fill_rate` (fraction of signals that became trades)

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 3 (parallel with ANY wave), Blocks: none, Blocked By: none

  **References**: `src/traderbot/simulation/engine.py:384`

  **QA Scenarios**:
  ```
  Scenario: Brier score is computed, not hardcoded
    Tool: Bash
    Steps:
      1. grep -n "brier_score" src/traderbot/simulation/engine.py
      2. Assert: no line contains "= 0.25" as hardcoded assignment
    Expected Result: Brier score dynamically computed
    Evidence: .sisyphus/evidence/task-3.1-brier-score.txt
  ```

- [x] 3.2. Wire PaperTrader Through evaluate_trade() (H10)

  **What to do**:
  - Add `evaluate_trade()` call in `paper_trader.py:162-200` `submit_order()` before placing paper trade
  - PaperTrader should respect risk limits (just like live), but with paper-mode profile limits

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/simulation/paper_trader.py:162-200`, `src/traderbot/risk/` — evaluate_trade pattern

  **QA Scenarios**:
  ```
  Scenario: submit_order calls evaluate_trade
    Tool: Bash
    Steps:
      1. grep -n "evaluate_trade" src/traderbot/simulation/paper_trader.py
      2. Assert: at least one match in submit_order method
    Expected Result: evaluate_trade called before paper trade execution
    Evidence: .sisyphus/evidence/task-3.2-paper-risk.txt
  ```

- [ ] 3.3. Fix effective_limit Floor Thresholds (H11)

  **What to do**:
  - Fix `simulation/profiles.py:41-45`: `effective_limit()` returns `risk_multiplier * HARD_LIMITS[key]` for ALL keys
  - For floor-type limits (min_liquidity, min_edge): use `max()` so multiplier doesn't make floor LESS restrictive
  - For ceiling-type limits: use `min()` (as `AgentRiskLimits` correctly does)

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/simulation/profiles.py:41-45`, `src/traderbot/risk/limits.py` — AgentRiskLimits as correct reference

  **QA Scenarios**:
  ```
  Scenario: Floor-type limits use max() not multiplication
    Tool: Bash
    Steps:
      1. grep -n "effective_limit" src/traderbot/simulation/profiles.py
      2. Assert: floor-type limits use max() or separate handling
    Expected Result: Floor limits can't become less restrictive with multiplier < 1
    Evidence: .sisyphus/evidence/task-3.3-floor-fix.txt
  ```

- [x] 3.4. Delete simulation/models.py Dead Code (H12)

  **What to do**:
  - Delete `src/traderbot/simulation/models.py` — duplicates `BacktestResult` fields and imports from `kalshi.models`, creating circular import risk
  - Remove any imports of `simulation.models` from other files

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/simulation/models.py`

  **QA Scenarios**:
  ```
  Scenario: simulation/models.py does not exist
    Tool: Bash
    Steps:
      1. test ! -f src/traderbot/simulation/models.py && echo "DELETED"
    Expected Result: "DELETED"
    Evidence: .sisyphus/evidence/task-3.4-dead-code.txt

  Scenario: No imports of simulation.models
    Tool: Bash
    Steps:
      1. grep -rn "from traderbot.simulation.models" src/
      2. Assert: exit code 1 (no matches)
    Expected Result: No imports remain
    Evidence: .sisyphus/evidence/task-3.4-no-imports.txt
  ```

- [ ] 3.5. Unify NewsSource Enum (H8)

  **What to do**:
  - `sources.py:19-24`: `NewsSource` has lowercase values (`newsapi`, `twitter`, `reddit`)
  - `models.py:17-23`: `NewsSource` has titlecase values (`NewsAPI`, `Twitter`, `Reddit`)
  - Unify to ONE enum (keep in `sources.py` as source of truth), update `models.py` to import from `sources.py`
  - Remove `source_map` translation in `cli.py`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/news/sources.py:19-24`, `src/traderbot/news/models.py:17-23`

  **QA Scenarios**:
  ```
  Scenario: Only one NewsSource enum definition
    Tool: Bash
    Steps:
      1. grep -rn "class NewsSource" src/traderbot/news/
      2. Assert: exactly 1 match
    Expected Result: Single NewsSource definition
    Evidence: .sisyphus/evidence/task-3.5-unified-enum.txt
  ```

- [x] 3.6. Replace Semaphore Rate Limiter with Token Bucket (M1 + A2)

  **What to do**:
  - Replace `asyncio.Semaphore(int(rate_limit_rps))` in `client.py:129` with token bucket rate limiter
  - Semaphore is a concurrency limiter (5 concurrent requests ≠ 5 requests/second)
  - Implement simple token bucket: `max_tokens`, `refill_rate`, `last_refill` timestamp

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/kalshi/client.py:129`

  **QA Scenarios**:
  ```
  Scenario: No Semaphore in rate limiter
    Tool: Bash
    Steps:
      1. grep -n "Semaphore" src/traderbot/kalshi/client.py
      2. Assert: no matches (or only for unrelated concurrency, not rate limiting)
    Expected Result: Semaphore removed from rate limiting
    Evidence: .sisyphus/evidence/task-3.6-token-bucket.txt
  ```

- [x] 3.7. Fix Sharpe Ratio N→N-1 (M3)

  **What to do**:
  - Fix `analysis/portfolio.py:75`: Change `variance = sum(...) / len(excess)` to `/ (len(excess) - 1)` for sample standard deviation
  - Same fix in `engine._compute_result` if present

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/analysis/portfolio.py:75`

  **QA Scenarios**:
  ```
  Scenario: Sharpe uses N-1 divisor
    Tool: Bash
    Steps:
      1. grep -n "len(excess)" src/traderbot/analysis/portfolio.py
      2. Assert: division uses (len(excess) - 1) or equivalent
    Expected Result: Bessel's correction applied
    Evidence: .sisyphus/evidence/task-3.7-sharpe-fix.txt
  ```

- [x] 3.8. Fix Orderbook Key Names + Remove Fallback (M5)

  **What to do**:
  - Fix `markets.py:62-67`: Orderbook key names to match Kalshi API (`bids`/`asks` with sub-fields)
  - Remove fallback that silently accepts wrong key names

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/kalshi/markets.py:62-67`

  **QA Scenarios**:
  ```
  Scenario: Orderbook parsing uses correct keys
    Tool: Bash
    Steps:
      1. grep -n "orderbook\|bids\|asks" src/traderbot/kalshi/markets.py
      2. Assert: matches use 'bids'/'asks' key names matching Kalshi API spec
    Expected Result: Correct key names used
    Evidence: .sisyphus/evidence/task-3.8-orderbook-keys.txt
  ```

- [x] 3.9. Centralize Path.home() / ".traderbot" into paths.py (M10)

  **What to do**:
  - Create `src/traderbot/paths.py` with `TRADERBOT_HOME = Path.home() / ".traderbot"` and related path constants
  - Replace all scattered `Path.home() / ".traderbot"` references with imports from paths.py

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: Search codebase for `Path.home() / ".traderbot"` pattern

  **QA Scenarios**:
  ```
  Scenario: paths.py exists and TRADERBOT_HOME defined
    Tool: Bash
    Steps:
      1. python -c "from traderbot.paths import TRADERBOT_HOME; print(TRADERBOT_HOME)"
    Expected Result: Path object printed (e.g. /home/user/.traderbot)
    Evidence: .sisyphus/evidence/task-3.9-paths.txt
  ```

- [x] 3.10. Fix OpenClaw Config Path in cli.py (M7)

  **What to do**:
  - `cli.py:2413`: `_write_heartbeat_config()` uses `Path.home() / ".openclaw" / "config.json"` — WRONG
  - Correct path is `Path.home() / ".openclaw" / "openclaw.json"` (matches `profiles/discovery.py:8`)

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3, Blocks: none, Blocked By: none

  **References**: `src/traderbot/cli.py:2413`, `src/traderbot/profiles/discovery.py:8`

  **QA Scenarios**:
  ```
  Scenario: cli.py uses openclaw.json not config.json
    Tool: Bash
    Steps:
      1. grep -n "config.json" src/traderbot/cli.py
      2. Assert: no matches
      3. grep -n "openclaw.json" src/traderbot/cli.py
      4. Assert: at least one match where config.json was
    Expected Result: config.json replaced with openclaw.json
    Evidence: .sisyphus/evidence/task-3.10-config-path.txt
  ```

- [ ] 4.1. Require --channel/--to with --announce in cron

  **What to do**: In `cli.py:2516-2526`, validate that `--announce` is always accompanied by `--channel` and `--to`. Raise error if missing.

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.2. Update ROADMAP_PROGRESS.md version

  **What to do**: Update version reference from v0.08.32 → current v0.09.21 (and v0.10.00 after Task 0.2)

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.3. Fix docs/news-sentiment.md rate limit (1000 → 100/day free) — **REQUIRES HUMAN APPROVAL**

  **What to do**: Correct rate limit documentation in `docs/news-sentiment.md:96`

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.4. Delete EXAMPLE_TESTING_PROMPT.md

  **What to do**: Delete unrelated project file from repo root

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.5. Remove # Made with Bob from injection.py:173

  **What to do**: Remove comment from line 173 (previously misattributed to agent_limits.py:92)

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.6. Fix cron hour range 9-15 → 9-16 in cli.py

  **What to do**: Change market hours cron expression in `cli.py` to include 4 PM ET hour

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.7. Remove dead return from _process_signals

  **What to do**: Fix `engine.py:338` unreachable/dead return

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.8. Document Twitter source stub as not implemented

  **What to do**: Add explicit docstring/comment in `sources.py` that Twitter API integration is a stub

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.9. Document signals CLI command as stub

  **What to do**: Add explicit docstring in `cli.py` that `signals` command is not yet implemented

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 4.10. Resolve simulation/strategies/ directory mismatch — **REQUIRES HUMAN APPROVAL**

  **What to do**: TOOLS.md references `src/traderbot/simulation/strategies/` but directory doesn't exist. Either create with strategy modules or update TOOLS.md.

  **Recommended Agent Profile**: `quick` | **Parallelization**: Wave 4

- [ ] 5.1. Update docs/kalshi.md — **REQUIRES HUMAN APPROVAL**

  **What to do**: Update with corrected URLs, auth mechanism, endpoint field names, historical cutoff, and events

  **Recommended Agent Profile**: `writing` | **Parallelization**: Wave 5

- [ ] 5.2. Update docs/simulation.md — **REQUIRES HUMAN APPROVAL**

  **What to do**: Update with real Brier score implementation details

  **Recommended Agent Profile**: `writing` | **Parallelization**: Wave 5

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check`, `pytest`, type checker. Review all changed files for: `as any`/`# type: ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration. Test edge cases: no credentials, invalid ticker, demo mode. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **0.1**: `fix(kalshi): correct base URLs to api.elections.kalshi.com` — client.py, config.py, websocket.py
- **0.2**: `feat(kalshi): RSA-PSS auth replaces session-token auth [BREAKING v0.10.00]` — signing.py (new), client.py, config.py, auth.py, cli.py, profiles/*
- **0.3**: `fix(kalshi): WebSocket auth via HTTP headers + correct subscribe format` — websocket.py
- **0.4**: `fix(kalshi): order creation uses action/count/yes_price fields` — trading.py, models.py
- **1.1-1.5**: `fix(kalshi): correct trades endpoint, model fields, historical endpoints, DELETE method, normalize fallback`
- **2.1-2.2**: `feat(kalshi): add portfolio and events endpoints` — portfolio.py (new), events.py (new)
- **2.4-2.6**: `fix(news): add /everything endpoint, error checking, auth header, rate-limit headers`
- **2.7**: `fix(openclaw): correct cron delivery logic and session isolation guarantee`
- **2.8**: `fix(skills): update SKILL.md gating after auth migration`
- **3.x**: Individual commits per fix
- **4.x**: Batch cleanup commit
- **5.x**: Individual commits per doc (after human approval)

---

## Success Criteria

### Verification Commands
```bash
pytest                                    # Expected: 0 failures
ruff check src/                           # Expected: 0 errors
python -c "from traderbot.kalshi.signing import sign_request, auth_headers"  # Expected: imports succeed
python -c "from traderbot.kalshi.client import KalshiClient; c = KalshiClient(); assert not hasattr(c, 'login')"  # Expected: True
python -c "from traderbot.kalshi.config import KalshiConfig; c = KalshiConfig(); assert 'elections.kalshi.com' in c.base_url"  # Expected: True
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Version bumped to v0.10.00