# Provider_Expansion — Multi-Provider Architecture

## TL;DR

> **Quick Summary**: Redesign TraderBot from a Kalshi-only toolkit into a platform-agnostic provider kernel. Abstract `DataProvider`/`ExecutionProvider`/`PortfolioProvider` protocols let any exchange plug in. First backends: OddsPipe (unified data across Kalshi + Polymarket) and native Polymarket CLOB (execution).
>
> **Deliverables**:
> - `src/traderbot/providers/` — Provider protocols, cross-provider models, registry
> - `src/traderbot/providers/oddspipe/` — OddsPipe DataProvider (verified live)
> - `src/traderbot/providers/polymarket/` — Polymarket DataProvider (Gamma) + ExecutionProvider (CLOB)
> - Kalshi protocol facade wrapping existing adapters
> - Multi-provider CLI (`--provider` flag on scan, analyze, trade)
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: Wave 1 (Protocols) → Wave 2 (OddsPipe) → Wave 3 (Polymarket Gamma) → Wave 4 (Polymarket CLOB) → Wave 5 (Kalshi facade) → Wave 6 (CLI)

---

## Context

### Original Request
Integrate new market providers (Polymarket, FanDuel, DraftKings) into TraderBot's toolkit. After feasibility analysis: FanDuel/DraftKings have no public API; Polymarket has a rich API; OddsPipe (free) already normalizes Kalshi + Polymarket data with cross-platform spread detection.

### Interview Summary
**Key Discussions**:
- TraderBot must be **platform-agnostic** — core function is aggregating data + normalizing execution access
- **Revenue priority**: fastest path to multi-provider visibility and execution
- **Approach**: Abstract Provider Protocol + OddsPipe as first data backend + native Polymarket execution via py-clob-client-v2
- FanDuel and DraftKings deferred to future phase (needs paid aggregator)

**Research Findings**:
- **Polymarket**: 3 APIs (Gamma/discovery public, CLOB/trading HMAC+EIP-712, Data/analytics public). Official Python SDK (`py-clob-client-v2`) for order placement. Verified live: Gamma API responds, CLOB orderbook works.
- **OddsPipe**: Free API, 88K+ markets across Kalshi+Polymarket. Already has cross-platform spread detection (2,500+ matched pairs). 1-min OHLCV history. 100 req/min free tier. Verified live: all endpoints functional.
- **Existing code**: `MarketDataProvider` protocol in `kalshi/provider.py` is Kalshi-specific. `ProdDataProvider` uses `MarketService` + caching. `TradingService` and `PortfolioService` are Kalshi-specific.

---

## Work Objectives

### Core Objective
Design and implement a generic provider abstraction layer that makes TraderBot platform-agnostic, with working backends for OddsPipe (unified data) and Polymarket (native execution).

### Concrete Deliverables
- `src/traderbot/providers/__init__.py` — Public API exports
- `src/traderbot/providers/models.py` — Cross-provider data models (UnifiedMarket, UnifiedOrderBook, etc.)
- `src/traderbot/providers/protocols.py` — DataProvider, ExecutionProvider, PortfolioProvider protocols
- `src/traderbot/providers/registry.py` — ProviderRegistry singleton
- `src/traderbot/providers/oddspipe/client.py` — OddsPipe HTTP client
- `src/traderbot/providers/oddspipe/provider.py` — OddsPipe DataProvider implementation
- `src/traderbot/providers/oddspipe/models.py` — OddsPipe-specific response models
- `src/traderbot/providers/polymarket/gamma.py` — Polymarket Gamma API DataProvider
- `src/traderbot/providers/polymarket/clob.py` — Polymarket CLOB ExecutionProvider
- `src/traderbot/providers/polymarket/models.py` — Polymarket-specific response models
- Kalshi protocol facade in `src/traderbot/kalshi/` or new bridge module
- CLI updates for `--provider` flag
- Tests for each provider adapter

### Definition of Done
- [ ] `pytest tests/providers/` passes with mocked provider data
- [ ] `traderbot scan --provider oddspipe` returns live markets from OddsPipe
- [ ] `traderbot scan --provider polymarket` returns live markets from Polymarket Gamma
- [ ] Cross-provider spread data available via OddsPipe backend
- [ ] Existing `traderbot scan` (no flag) continues working as before (defaults to Kalshi)

### Must Have
- [ ] Working generic Provider Protocols that any exchange can implement
- [ ] OddsPipe DataProvider returning normalized market data
- [ ] Polymarket DataProvider via Gamma API
- [ ] Provider Registry for runtime provider selection
- [ ] All existing Kalshi functionality continues working unchanged

### Must NOT Have (Guardrails)
- [ ] No breaking changes to existing CLI interfaces (backward-compatible)
- [ ] No hardcoded provider-specific logic in the analysis/risk/simulation modules
- [ ] FanDuel, DraftKings not included (deferred)
- [ ] No changes to HARD_LIMITS or risk module (stays provider-agnostic)
- [ ] No direct manipulation of OddsPipe API from outside its adapter

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, async support)
- **Automated tests**: YES (Tests-after)
- **Framework**: pytest with pytest-asyncio
- **Mock strategy**: pytest fixtures for mocked provider responses; integration tests against live public APIs where safe

### QA Policy
Every task MUST include agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Provider protocol unit tests**: pytest against mock implementations
- **OddsPipe integration**: Bash (curl/httpx) against live OddsPipe API
- **Polymarket Gamma integration**: Bash (httpx) against live Gamma API
- **CLI integration**: Bash (subprocess) running `traderbot scan --provider X`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — start immediately):
├── T1: Cross-provider data models [quick]
├── T2: Provider protocol definitions [quick]
├── T3: ProviderRegistry + provider manager [quick]
└── T4: Test infrastructure + mock providers [unspecified-medium]

Wave 2 (OddsPipe Backend — MAX PARALLEL after Wave 1):
├── T5: OddsPipe HTTP client + auth [quick]
├── T6: OddsPipe market search/list/get [unspecified-medium]
├── T7: OddsPipe cross-platform spreads + history [unspecified-medium]
└── T8: OddsPipe DataProvider integration tests [unspecified-medium]

Wave 3 (Polymarket Gamma — parallel with Wave 2, after Wave 1):
├── T9: Polymarket Gamma HTTP client [quick]
├── T10: Polymarket Gamma DataProvider [unspecified-medium]
└── T11: Gamma integration tests [unspecified-medium]

Wave 4 (Polymarket CLOB — after Wave 3):
├── T12: Polymarket CLOB auth + py-clob-client-v2 setup [unspecified-high]
├── T13: Polymarket ExecutionProvider (order placement) [deep]
├── T14: Polymarket PortfolioProvider (balance, positions) [unspecified-medium]
└── T15: CLOB integration tests [unspecified-medium]

Wave 5 (Kalshi Retrofit — after Wave 1, parallel with Waves 2-4):
├── T16: Kalshi DataProvider facade [quick]
├── T17: Kalshi ExecutionProvider facade [quick]
└── T18: Kalshi PortfolioProvider facade [quick]

Wave 6 (CLI + Integration — after Waves 2-5):
├── T19: CLI `--provider` flag support [unspecified-medium]
├── T20: Provider-aware scan command [unspecified-medium]
├── T21: Provider-aware analyze command [unspecified-medium]
└── T22: Cross-provider spread CLI command [unspecified-medium]

Wave FINAL (Verification):
├── F1: Plan compliance audit
├── F2: Code quality + type check + lint
├── F3: End-to-end integration QA
└── F4: Scope fidelity check
```

### Dependency Matrix
- T1-T4: - (foundation, no deps)
- T5-T8: T1, T2, T3, T4 (needs protocols + models)
- T9-T11: T1, T2, T3, T4 (needs protocols + models)
- T12-T15: T9, T10, T11 (needs Gamma client working)
- T16-T18: T1, T2, T3 (needs protocols)
- T19-T22: T5-T8, T9-T11, T12-T15, T16-T18 (needs all providers working)

### Agent Dispatch Summary
- Wave 1: 4 agents max parallel
- Wave 2: 4 agents max parallel
- Wave 3: 3 agents max parallel
- Wave 4: 4 agents max parallel
- Wave 5: 3 agents parallel
- Wave 6: 4 max parallel
- Final: 4 parallel review agents

---

## TODOs

- [ ] 1. **Cross-provider data models**

  **What to do**:
  - Create `src/traderbot/providers/models.py` with unified data types that any exchange can map into:
    - `UnifiedMarket` — provider, provider_id, question, yes_price (float 0-1), no_price (float 0-1), volume_usd, close_time, status, category
    - `UnifiedOrderBookLevel` — price (float), size (float)
    - `UnifiedOrderBook` — bids: list[OrderBookLevel], asks: list[OrderBookLevel], provider, provider_id, timestamp
    - `UnifiedOrder` — provider, provider_order_id, side (yes/no), price, size, status, created_at
    - `UnifiedPosition` — provider, provider_market_id, side, quantity, avg_price
    - `UnifiedBalance` — provider, available, total, currency
    - `UnifiedFill` — provider, order_id, market_id, side, price, size, timestamp
    - `CrossSpread` — provider_a, provider_b, market_id_a, market_id_b, yes_diff, direction
    - `PriceSnapshot` — yes_price, no_price, volume_usd, timestamp
    - `Candlestick` — timestamp, open, high, low, close, volume
  - All models use Pydantic v2 with `ConfigDict(strict=True, extra="forbid")` (project convention)
  - All monetary values as float 0-1 (cross-provider normalization — Polymarket uses dollars, Kalshi uses cents, OddsPipe uses 0-1 floats)
  - Include `ProviderStr` enum: `kalshi`, `polymarket`, `oddspipe`

  **Must NOT do**:
  - No provider-specific fields in unified models (use `extra` dict if needed)
  - No float for monetary amounts in cents — keep everything in the provider's native unit and normalize only at the presentation layer

  **Recommended Agent Profile**:
  - Category: `quick` — data modeling, clear spec
  - Skills: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T4)
  - **Blocks**: T5-T22 (everything depends on models)
  - **Blocked By**: None

  **References**:
  - `src/traderbot/kalshi/models.py` — Existing Pydantic models (Market, OrderBook, etc.) — follow the same patterns
  - `docs/architecture.md` — Architecture principles for understanding what models need to support
  - OddsPipe API response (verified live) — market: `{id, title, status, source: {platform, platform_market_id, latest_price: {yes_price, no_price, volume_usd}}}`
  - Polymarket Gamma API response (verified live) — market: `{conditionId, outcomePrices: ["0.0135", "0.9865"], clobTokenIds: [yes, no]}`

  **Acceptance Criteria**:
  - [ ] All unified models defined in `providers/models.py`
  - [ ] `from traderbot.providers.models import UnifiedMarket` works
  - [ ] `pydantic` validates strict types

  **QA Scenarios**:
  ```
  Scenario: UnifiedMarket creates successfully
    Tool: Bash (python -c)
    Preconditions: None
    Steps:
      1. Run: python3 -c "from traderbot.providers.models import UnifiedMarket; m = UnifiedMarket(provider='kalshi', provider_id='KXBTCD', question='test', yes_price=0.55, no_price=0.45, volume_usd=1000.0, close_time='2026-06-26T12:00:00Z', status='open'); print(m.model_dump_json())"
    Expected Result: Valid JSON output with all fields
    Evidence: .sisyphus/evidence/task-1-model-create.json

  Scenario: UnifiedMarket rejects invalid data
    Tool: Bash (python -c)
    Preconditions: None
    Steps:
      1. Run: python3 -c "from traderbot.providers.models import UnifiedMarket; m = UnifiedMarket(provider='kalshi', provider_id='KXBTCD', question='test', yes_price=1.5, no_price=0.45, volume_usd=1000.0, close_time='bad-date', status='open')" 2>&1
    Expected Result: pydantic validation error (yes_price > 1.0)
    Evidence: .sisyphus/evidence/task-1-model-validation-error.txt
  ```

  **Evidence to Capture**:
  - [ ] Successful model creation
  - [ ] Validation error on bad data

  **Commit**: YES (group with T2, T3)
  - Message: `feat(providers): add cross-provider data models and protocol definitions`
  - Files: `src/traderbot/providers/models.py`
  - Pre-commit: `python3 -c "from traderbot.providers.models import UnifiedMarket"`

- [ ] 2. **Provider protocol definitions**

  **What to do**:
  - Create `src/traderbot/providers/protocols.py` with abstract protocols:
    - `DataProvider(Protocol)`:
      - `async def search_markets(query: str, *, limit: int = 50, **filters) -> list[UnifiedMarket]`
      - `async def get_market(provider_id: str) -> UnifiedMarket`
      - `async def get_orderbook(provider_id: str) -> UnifiedOrderBook`
      - `async def get_price_history(provider_id: str, *, limit: int = 100) -> list[PriceSnapshot]`
      - `async def get_candlesticks(provider_id: str, *, interval: str = "1h", limit: int = 100) -> list[Candlestick]`
    - `ExecutionProvider(Protocol)`:
      - `async def place_order(order: UnifiedOrder) -> UnifiedOrder`
      - `async def cancel_order(provider_order_id: str) -> bool`
      - `async def get_orders(*, market_id: str | None = None) -> list[UnifiedOrder]`
    - `PortfolioProvider(Protocol)`:
      - `async def get_balance() -> UnifiedBalance`
      - `async def get_positions() -> list[UnifiedPosition]`
      - `async def get_fills(*, limit: int = 100) -> list[UnifiedFill]`
    - `CombinedProvider(DataProvider, ExecutionProvider, PortfolioProvider, Protocol)` — for providers that offer all three
  - Use `@runtime_checkable` for runtime isinstance checks
  - All methods accept `**kwargs` for provider-specific parameters
  - Docstrings on every method

  **Must NOT do**:
  - No implementation in protocol definitions (abstract only)
  - No Kalshi-specific method names (e.g., `get_market` not `get_market_by_ticker`)
  - No assumptions about auth mechanism

  **Recommended Agent Profile**:
  - Category: `quick` — protocol design, well-scoped
  - Skills: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3, T4)
  - **Blocks**: T5-T22
  - **Blocked By**: T1 (needs models)

  **References**:
  - `src/traderbot/kalshi/provider.py:MarketDataProvider` — Existing protocol (lines 70-77, 90-96) — follow the same `@runtime_checkable` pattern
  - PEP 544 — Protocol typing in Python
  - `src/traderbot/kalshi/trading.py:TradingService` — Existing execution interface to abstract from

  **Acceptance Criteria**:
  - [ ] All three protocols defined and exported from `providers/__init__.py`
  - [ ] `isinstance(some_impl, DataProvider)` works at runtime
  - [ ] `mypy --strict` passes on protocol definitions
  - [ ] Protocol methods have full type annotations

  **QA Scenarios**:
  ```
  Scenario: Protocols import and runtime_checkable works
    Tool: Bash (python -c)
    Preconditions: T1 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.protocols import DataProvider, ExecutionProvider, PortfolioProvider; print('OK')"
    Expected Result: "OK"
    Evidence: .sisyphus/evidence/task-2-protocols-import.txt

  Scenario: Mock provider satisfies protocols
    Tool: Bash (python -c)
    Preconditions: T1, T2 complete
    Steps:
      1. Run: python3 -c "
from traderbot.providers.protocols import DataProvider
from typing import runtime_checkable, Protocol

class MockProvider:
    async def search_markets(self, query, *, limit=50, **filters): return []
    async def get_market(self, provider_id): pass
    async def get_orderbook(self, provider_id): pass
    async def get_price_history(self, provider_id, *, limit=100): return []
    async def get_candlesticks(self, provider_id, *, interval='1h', limit=100): return []

print(isinstance(MockProvider(), DataProvider))
"
    Expected Result: "True"
    Evidence: .sisyphus/evidence/task-2-mock-satisfies.txt
  ```

  **Evidence to Capture**:
  - [ ] Protocol import success
  - [ ] Runtime isinstance check passes

  **Commit**: YES (group with T1, T3)
  - Message: `feat(providers): add cross-provider data models and protocol definitions`
  - Files: `src/traderbot/providers/protocols.py`
  - Pre-commit: `python3 -c "from traderbot.providers.protocols import DataProvider"`

- [ ] 3. **ProviderRegistry + provider manager**

  **What to do**:
  - Create `src/traderbot/providers/registry.py`:
    - `ProviderRegistry` class:
      - `register(name: str, data: DataProvider | None, execution: ExecutionProvider | None, portfolio: PortfolioProvider | None)`
      - `get_data(name: str) -> DataProvider` — raises `KeyError` if not found
      - `get_execution(name: str) -> ExecutionProvider`
      - `get_portfolio(name: str) -> PortfolioProvider`
      - `list_providers() -> list[str]`
      - `get_default_provider() -> str` — returns "kalshi" initially (backward compat)
    - Module-level singleton: `_registry = ProviderRegistry()` with `get_provider_registry()` accessor
    - Auto-register Kalshi providers on first import (lazy, only if imports succeed)
    - Configuration-driven registration via `providers/config.py`:
      - `ProviderConfig` pydantic model with `ODDSPIPE_API_KEY`, `POLYMARKET_RPC_URL`, etc.
      - `init_providers(config: ProviderConfig)` — registers all configured providers

  **Must NOT do**:
  - No global mutable state beyond the registry singleton
  - No automatic provider discovery (explicit registration only)
  - No blocking I/O in registry methods

  **Recommended Agent Profile**:
  - Category: `quick` — straightforward implementation
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T1, T2)
  - **Parallel Group**: Wave 1 (with T1, T2, T4)
  - **Blocks**: T5-T22
  - **Blocked By**: T1, T2 (needs models + protocols)

  **References**:
  - `src/traderbot/profiles/registry.py` — Existing registry pattern for profiles
  - `src/traderbot/profiles/runtime.py` — Runtime profile resolution pattern

  **Acceptance Criteria**:
  - [ ] `registry.py` exists with ProviderRegistry class
  - [ ] `get_provider_registry()` returns singleton
  - [ ] Mock providers can be registered and retrieved
  - [ ] Missing provider raises clear `KeyError` with available options

  **QA Scenarios**:
  ```
  Scenario: Register and retrieve a provider
    Tool: Bash (python -c)
    Preconditions: T1, T2 complete
    Steps:
      1. Run a Python script that creates a mock DataProvider, registers it, retrieves it, and calls list_providers
    Expected Result: Provider retrieved, list shows registered name
    Evidence: .sisyphus/evidence/task-3-registry-basic.txt

  Scenario: Missing provider raises helpful error
    Tool: Bash (python -c)
    Preconditions: T1, T2 complete
    Steps:
      1. Try to get a provider that doesn't exist
    Expected Result: KeyError listing available providers
    Evidence: .sisyphus/evidence/task-3-registry-missing.txt
  ```

  **Evidence to Capture**:
  - [ ] Registry operations
  - [ ] Error handling

  **Commit**: YES (group with T1, T2)
  - Message: `feat(providers): add cross-provider data models and protocol definitions`
  - Files: `src/traderbot/providers/registry.py`
  - Pre-commit: `python3 -c "from traderbot.providers.registry import get_provider_registry"`

- [ ] 4. **Test infrastructure + mock providers**

  **What to do**:
  - Create `tests/providers/` directory structure:
    - `tests/providers/__init__.py`
    - `tests/providers/conftest.py` — shared fixtures
    - `tests/providers/test_models.py` — model validation tests
    - `tests/providers/test_protocols.py` — protocol structural tests
    - `tests/providers/test_registry.py` — registry tests
    - `tests/providers/mock_data.py` — reusable mock data for all providers
  - Create `MockDataProvider` in test fixtures:
    - Implements `DataProvider` with pre-configured dicts
    - Returns `UnifiedMarket`, `UnifiedOrderBook`, etc.
  - Create `MockExecutionProvider` in test fixtures
  - Mock data should include realistic examples:
    - A Kalshi market (crypto category)
    - A Polymarket market (politics category)
    - An OddsPipe cross-spread pair
    - Various edge cases (zero volume, resolved markets, empty orderbooks)

  **Must NOT do**:
  - No live API calls in unit tests (use fixtures)
  - No test data that mirrors real API keys

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T1, T2, T3)
  - **Parallel Group**: Wave 1
  - **Blocks**: T5-T22 (tests validate provider implementations)
  - **Blocked By**: T1, T2 (needs models + protocols)

  **References**:
  - `tests/risk/test_evaluate_trade_profile.py` — Existing test patterns
  - `tests/kalshi/` — Existing kalshi test patterns (if they exist)
  - `src/traderbot/kalshi/provider.py:MockDataProvider` — Existing mock pattern (lines 102-136)

  **Acceptance Criteria**:
  - [ ] `pytest tests/providers/` runs and all tests pass
  - [ ] Mock providers implement all protocol methods
  - [ ] Test coverage for model validation, protocol checking, registry operations

  **QA Scenarios**:
  ```
  Scenario: All provider unit tests pass
    Tool: Bash (pytest)
    Preconditions: T1-T3 complete
    Steps:
      1. Run: cd /path/to/traderbot && python -m pytest tests/providers/ -v --tb=short
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-4-pytest-pass.txt

  Scenario: Mock providers return expected data shapes
    Tool: Bash (python -c with pytest)
    Preconditions: T1-T3 complete
    Steps:
      1. Run test that asserts mock provider returns UnifiedMarket with expected fields
    Expected Result: Assertions pass
    Evidence: .sisyphus/evidence/task-4-mock-shapes.txt
  ```

  **Evidence to Capture**:
  - [ ] Full pytest output
  - [ ] Mock data validation

  **Commit**: YES
  - Message: `test(providers): add test infrastructure and mock providers`
  - Files: `tests/providers/`
  - Pre-commit: `python -m pytest tests/providers/ -x`

- [ ] 5. **OddsPipe HTTP client + auth**

  **What to do**:
  - Create `src/traderbot/providers/oddspipe/client.py`:
    - `OddsPipeConfig` pydantic model: `api_key: str`, `base_url: str = "https://oddspipe.com/v1"`
    - `OddsPipeHTTPClient` class:
      - `__init__(self, config: OddsPipeConfig)` — stores API key
      - `_request(method, path, **params) -> dict` — httpx-based, adds `X-API-Key` header
      - Rate limiting: token bucket at 100 req/min (matching free tier)
      - Error handling: 401 → `ConfigurationError`, 429 → rate limit backoff, 5xx → retry (1 attempt)
    - `create_oddspipe_client() -> OddsPipeHTTPClient` — resolves API key from env var `ODDSPIPE_API_KEY` or provider config
  - Create `src/traderbot/providers/oddspipe/models.py`:
    - OddsPipe-specific response models (mapping their exact JSON shape):
      - `OddsPipeMarketResponse`, `OddsPipeSource`, `OddsPipePrice`, `OddsPipeSpreadItem`, `OddsPipeCandlestick`
    - Transform methods: `.to_unified_market() -> UnifiedMarket`, `.to_unified_orderbook() -> UnifiedOrderBook`, etc.

  **Must NOT do**:
  - No hardcoded API keys
  - No synchronous HTTP calls (use httpx.AsyncClient)
  - No mixing of OddsPipe models with Polymarket logic

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T6, T7, T8)
  - **Blocks**: T6, T7, T8
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - OddsPipe OpenAPI spec (verified at `https://oddspipe.com/openapi.json`) — endpoint definitions
  - `src/traderbot/kalshi/client.py` — Existing HTTP client pattern (KalshiClient, auth headers, error handling)
  - Verified live response shapes from research: market `{id, title, status, source: {platform, platform_market_id, latest_price: {yes_price, no_price, volume_usd}}}`
  - Spreads response (verified live): `{match_id, score, status, polymarket: {market_id, yes_price, ...}, kalshi: {...}, spread: {yes_diff, direction, note}}`

  **Acceptance Criteria**:
  - [ ] `OddsPipeHTTPClient` created with config, auth, rate limiting
  - [ ] `create_oddspipe_client()` creates a configured client from env
  - [ ] Models correctly map OddsPipe JSON → Unified models
  - [ ] `tests/providers/oddspipe/` with mocked HTTP tests

  **QA Scenarios**:
  ```
  Scenario: OddsPipe client transforms data correctly
    Tool: Bash (python -c)
    Preconditions: T1-T4 complete
    Steps:
      1. Unit test: create client with mock transport, assert transform methods work
    Expected Result: OddsPipe JSON → UnifiedMarket correctly mapped
    Evidence: .sisyphus/evidence/task-5-client-basic.txt

  Scenario: OddsPipe client handles auth error
    Tool: Bash (python -c)
    Preconditions: T1-T4 complete
    Steps:
      1. Unit test: mock 401 response, assert ConfigurationError raised
    Expected Result: Clear error message about missing API key
    Evidence: .sisyphus/evidence/task-5-auth-error.txt
  ```

  **Evidence to Capture**:
  - [ ] Data transformation test
  - [ ] Auth error handling test

  **Commit**: YES (group with T6)
  - Message: `feat(oddspipe): add OddsPipe HTTP client and market data provider`
  - Files: `src/traderbot/providers/oddspipe/`
  - Pre-commit: `python -m pytest tests/providers/oddspipe/ -x`

- [ ] 6. **OddsPipe market search/list/get**

  **What to do**:
  - Create `src/traderbot/providers/oddspipe/provider.py`:
    - `OddsPipeProvider` class implementing `DataProvider`:
      - `async def search_markets(self, query: str, *, limit=50, platform=None, **filters)` → calls `GET /v1/markets/search?q=...`
      - `async def get_market(self, provider_id: str)` → calls `GET /v1/markets/{id}`
      - `async def get_orderbook(self, provider_id: str)` → currently unavailable via OddsPipe (raises `NotImplementedError` — will use direct provider API)
  - Map all responses to `UnifiedMarket` via models
  - Implement pagination (limit/offset) for list endpoints
  - Support `platform` filter (kalshi, polymarket, or both)

  **Must NOT do**:
  - No caching layer (existing ProdDataProvider cache is Kalshi-specific; caching comes later)
  - No fallback to direct API if OddsPipe fails (caller handles)

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T7, T8)
  - **Blocks**: T19-T22
  - **Blocked By**: T5

  **References**:
  - Live-verified: `GET /v1/markets?limit=3` and `GET /v1/markets/search?q=bitcoin` — both work
  - `src/traderbot/kalshi/provider.py:ProdDataProvider` — existing data provider pattern
  - `src/traderbot/kalshi/markets.py:MarketService` — existing market service pattern

  **Acceptance Criteria**:
  - [ ] `OddsPipeProvider` implements all `DataProvider` methods
  - [ ] Search returns `list[UnifiedMarket]` from real OddsPipe data
  - [ ] Get market returns single `UnifiedMarket`
  - [ ] Integration test: `traderbot scan --provider oddspipe --limit 3` works
  - [ ] Integration test: `traderbot scan --provider oddspipe --search bitcoin --limit 3` works

  **QA Scenarios**:
  ```
  Scenario: OddsPipe search returns real markets
    Tool: Bash (python -c with httpx, asyncio)
    Preconditions: ODDSPIPE_API_KEY env var set, T5 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.oddspipe.provider import OddsPipeProvider; import asyncio; p = OddsPipeProvider(); markets = asyncio.run(p.search_markets('bitcoin', limit=3)); print(f'Found {len(markets)} markets'); [print(f'  {m.question[:60]} [{m.provider}] YES={m.yes_price} NO={m.no_price}') for m in markets]"
    Expected Result: 3 markets returned, each with question, provider, prices
    Evidence: .sisyphus/evidence/task-6-search-live.txt

  Scenario: OddsPipe get_market returns single market
    Tool: Bash (python -c with httpx, asyncio)
    Preconditions: ODDSPIPE_API_KEY set, T5 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.oddspipe.provider import OddsPipeProvider; import asyncio; p = OddsPipeProvider(); m = asyncio.run(p.get_market('3089676')); print(m.model_dump_json(indent=2))"
    Expected Result: Single UnifiedMarket with all fields populated
    Evidence: .sisyphus/evidence/task-6-get-market.txt
  ```

  **Evidence to Capture**:
  - [ ] Live search results
  - [ ] Live market detail

  **Commit**: YES (group with T5)
  - Message: `feat(oddspipe): add OddsPipe HTTP client and market data provider`

- [ ] 7. **OddsPipe cross-platform spreads + history**

  **What to do**:
  - Add to `OddsPipeProvider`:
    - `async def get_spreads(self, *, min_spread: float = 0.0, limit: int = 20)` → calls `GET /v1/spreads` (provider-specific method, not in base DataProvider)
    - `async def get_price_history(self, provider_id: str, *, limit: int = 100)` → calls `GET /v1/markets/{id}/history`
    - `async def get_candlesticks(self, provider_id: str, *, interval: str = "1h", limit: int = 100)` → calls `GET /v1/markets/{id}/candlesticks`
  - Map history snapshots → `list[PriceSnapshot]`
  - Map candlesticks → `list[Candlestick]`
  - Map spreads → `list[CrossSpread]`

  **Must NOT do**:
  - Don't pollute the `DataProvider` protocol with OddsPipe-specific methods (keep `get_spreads` as OddsPipe-only)
  - No aggregation of multiple providers' history into one call

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T6, T8)
  - **Blocks**: T22
  - **Blocked By**: T5

  **References**:
  - Verified live: `GET /v1/spreads?limit=2` returns `{match_id, score, status, polymarket: {...}, kalshi: {...}, spread: {yes_diff, direction, note}}`
  - Verified live: `GET /v1/markets/3089676/history` returns `{market_id, count, snapshots: [{id, yes_price, no_price, volume_usd, snapshot_at}]}`
  - Verified live: `GET /v1/markets/3089676/candlesticks?interval=1d` returns `{market_id, source, interval, candles: [{timestamp, open, high, low, close, volume}]}`

  **Acceptance Criteria**:
  - [ ] Spreads return `list[CrossSpread]` with cross-platform price differences
  - [ ] History returns `list[PriceSnapshot]` with yes_prices and timestamps
  - [ ] Candlesticks return `list[Candlestick]` with OHLCV
  - [ ] Integration test validates data from all three endpoints

  **QA Scenarios**:
  ```
  Scenario: OddsPipe spreads returns cross-platform pairs
    Tool: Bash (httpx, asyncio)
    Preconditions: ODDSPIPE_API_KEY set, T5 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.oddspipe.provider import OddsPipeProvider; import asyncio; p = OddsPipeProvider(); spreads = asyncio.run(p.get_spreads(min_spread=0.05, limit=5)); [print(f'{s.polymarket.title[:40]} vs {s.kalshi.title[:40]} | diff={s.spread.yes_diff:.2%}') for s in spreads]"
    Expected Result: 5 spreads returned with cross-platform price differences
    Evidence: .sisyphus/evidence/task-7-spreads.txt

  Scenario: OddsPipe candlesticks return OHLCV data
    Tool: Bash (httpx, asyncio)
    Preconditions: ODDSPIPE_API_KEY set, T5 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.oddspipe.provider import OddsPipeProvider; import asyncio; p = OddsPipeProvider(); hist = asyncio.run(p.get_price_history('3089676', limit=5)); print(f'Got {len(hist)} snapshots'); [print(f'  YES={s.yes_price} NO={s.no_price} VOL={s.volume_usd}') for s in hist[:3]]"
    Expected Result: Price snapshots with non-zero data
    Evidence: .sisyphus/evidence/task-7-history.txt
  ```

  **Evidence to Capture**:
  - [ ] Cross-platform spreads
  - [ ] Price history

  **Commit**: YES (group with T8)
  - Message: `feat(oddspipe): add cross-platform spreads and price history`

- [ ] 8. **OddsPipe DataProvider integration tests**

  **What to do**:
  - Create `tests/providers/oddspipe/`:
    - `tests/providers/oddspipe/__init__.py`
    - `tests/providers/oddspipe/conftest.py` — ODDSPIPE_API_KEY fixture (skip if not set)
    - `tests/providers/oddspipe/test_client.py` — unit tests with mocked httpx transport
    - `tests/providers/oddspipe/test_provider.py` — integration tests against live API
    - `tests/providers/oddspipe/test_models.py` — model transformation tests
  - Mock fixtures that simulate OddsPipe API responses:
    - markets list response (3 markets, mixed platforms)
    - search response (bitcoin results)
    - spreads response (2 cross-platform pairs)
    - history response (10 price snapshots)
    - candlesticks response (5 daily candles)
  - Integration tests should skip if `ODDSPIPE_API_KEY` is not set
  - Test rate limiting, error handling, edge cases

  **Must NOT do**:
  - No hardcoded market IDs that will break (use mock fixtures for unit tests)
  - No live API calls in CI without ODDSPIPE_API_KEY

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T6, T7)
  - **Blocks**: T19-T22
  - **Blocked By**: T5, T6, T7

  **References**:
  - `tests/risk/test_evaluate_trade_profile.py` — Existing test patterns
  - `src/traderbot/kalshi/provider.py:MockDataProvider` — Existing mock pattern

  **Acceptance Criteria**:
  - [ ] `pytest tests/providers/oddspipe/` passes with mock data
  - [ ] Integration tests run against live API when key is set
  - [ ] Edge case tests: empty response, 401, 429, 5xx, malformed JSON
  - [ ] All tests independent (no shared state)

  **QA Scenarios**:
  ```
  Scenario: All OddsPipe unit tests pass with mocks
    Tool: Bash (pytest)
    Preconditions: T5, T6, T7 complete
    Steps:
      1. Run: python -m pytest tests/providers/oddspipe/test_client.py tests/providers/oddspipe/test_models.py -v --tb=short
    Expected Result: All unit tests pass
    Evidence: .sisyphus/evidence/task-8-unit-tests.txt

  Scenario: Integration tests run against live API
    Tool: Bash (pytest with env var)
    Preconditions: ODDSPIPE_API_KEY set, T5-T7 complete
    Steps:
      1. Run: ODDSPIPE_API_KEY=xxx python -m pytest tests/providers/oddspipe/test_provider.py -v --tb=short
    Expected Result: Integration tests pass (or skip if key not set)
    Evidence: .sisyphus/evidence/task-8-integration-tests.txt
  ```

  **Evidence to Capture**:
  - [ ] Unit test output
  - [ ] Integration test output

  **Commit**: YES (group with T7)
  - Message: `test(oddspipe): add OddsPipe integration and unit tests`

- [ ] 9. **Polymarket Gamma HTTP client**

  **What to do**:
  - Create `src/traderbot/providers/polymarket/client.py`:
    - `PolymarketConfig` pydantic model: `gamma_base_url: str = "https://gamma-api.polymarket.com"`, `clob_base_url: str = "https://clob.polymarket.com"`, `chain_id: int = 137`, `private_key: str | None = None`
    - `GammaClient` class:
      - `__init__(self, config: PolymarketConfig | None = None)` — no auth needed for Gamma
      - `async def get_markets(self, *, limit=50, offset=0, active=True, closed=False, **params) -> list[dict]` — `GET /markets`
      - `async def get_events(self, *, limit=50, offset=0, **params) -> list[dict]` — `GET /events`
      - `async def search_markets(self, query: str, *, limit=50) -> list[dict]` — `GET /markets?slug=<query>` or search by tag
      - `async def get_market_by_condition_id(self, condition_id: str) -> dict` — `GET /markets?condition_ids=...`
      - `async def get_tags(self) -> list[dict]` — `GET /tags`
    - Rate limiting: conservative 5 req/s to avoid throttling
    - Error handling: 4xx → `ConfigurationError`, 5xx → retry (1 attempt)
    - Pagination: handle limit/offset pattern across all endpoints

  **Must NOT do**:
  - No auth headers for Gamma (it's a public API)
  - No caching at this layer (done by provider if needed)

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T10, T11)
  - **Blocks**: T10, T11
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - Polymarket llms.txt (docs.polymarket.com/llms.txt) — complete doc index
  - Verified live: `GET https://gamma-api.polymarket.com/markets?limit=3&order=volume24hr&ascending=false` returns markets with `{conditionId, question, outcomePrices, clobTokenIds, volume, active, closed}`
  - Gamma OpenAPI spec from `/api-spec/gamma-openaml` in docs
  - `src/traderbot/kalshi/client.py` — Existing HTTP client pattern

  **Acceptance Criteria**:
  - [ ] `GammaClient` created with config and Gamma base URL
  - [ ] `get_markets()` returns parsed lists from live API
  - [ ] `get_market_by_condition_id()` returns single market
  - [ ] Proper error handling for network failures

  **QA Scenarios**:
  ```
  Scenario: Gamma client fetches live markets
    Tool: Bash (httpx, asyncio)
    Preconditions: None (Gamma is public API)
    Steps:
      1. Run: python3 -c "from traderbot.providers.polymarket.client import GammaClient; import asyncio; c = GammaClient(); markets = asyncio.run(c.get_markets(limit=3)); print(f'Found {len(markets)} markets'); [print(f'  {m[\"question\"][:50]} | cond={m[\"conditionId\"][:20]}...') for m in markets]"
    Expected Result: 3 markets returned from live Gamma API
    Evidence: .sisyphus/evidence/task-9-gamma-live.txt

  Scenario: Gamma client handles missing markets gracefully
    Tool: Bash (httpx, asyncio)
    Preconditions: None
    Steps:
      1. Run: python3 -c "from traderbot.providers.polymarket.client import GammaClient; import asyncio; c = GammaClient(); m = asyncio.run(c.get_market_by_condition_id('0xnonexistent000000000000000000000000000000000000000000000000000')); print(f'Result: {m}')"
    Expected Result: Empty list or appropriate error message
    Evidence: .sisyphus/evidence/task-9-gamma-missing.txt
  ```

  **Evidence to Capture**:
  - [ ] Live market fetch
  - [ ] Error handling

  **Commit**: YES (group with T10)
  - Message: `feat(polymarket): add Gamma API data provider`
  - Files: `src/traderbot/providers/polymarket/`
  - Pre-commit: `python -m pytest tests/providers/polymarket/test_gamma.py -x`

- [ ] 10. **Polymarket Gamma DataProvider**

  **What to do**:
  - Create `src/traderbot/providers/polymarket/gamma.py`:
    - `PolymarketGammaProvider` class implementing `DataProvider`:
      - `async def search_markets(self, query: str, *, limit=50, **filters)` → queries Gamma events/markets by slug/search params
      - `async def get_market(self, provider_id: str)` → `GET /markets?condition_ids={provider_id}`
      - `async def get_orderbook(self, provider_id: str)` → `GET https://clob.polymarket.com/book?token_id={get_yes_token(provider_id)}` (crosses into CLOB, but only for reads)
      - `async def get_price_history(self, provider_id, *, limit=100)` → not available via Gamma (raises `NotImplementedError`)
    - Transform `outcomePrices` → yes_price (float), no_price (float)
    - Map `conditionId` → provider_id
    - Map `clobTokenIds` → stored for orderbook access (YES token)
    - Parse `endDate` → close_time
    - Handle `active`/`closed` → status mapping

  **Must NOT do**:
  - No caching layer
  - No Polymarket CLOB auth (this is for public data only)
  - No order placement in the DataProvider

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T9, T11)
  - **Blocks**: T12-T15, T19-T22
  - **Blocked By**: T9

  **References**:
  - `src/traderbot/kalshi/provider.py:MarketDataProvider` — Existing protocol pattern
  - Verified live Gamma market: `{conditionId, question, outcomePrices: ['0.0135', '0.9865'], clobTokenIds: ['139156...', '132906...'], volume, volume24hr, active, closed, endDate, liquidity}`
  - Verified live Gamma events: `{id, ticker, slug, title, active, closed, markets: [{conditionId, ...}]}`

  **Acceptance Criteria**:
  - [ ] `PolymarketGammaProvider` implements all `DataProvider` methods
  - [ ] `get_market()` returns `UnifiedMarket` with correct 0-1 prices
  - [ ] `search_markets()` returns relevant results
  - [ ] Status mapping: `active=true && closed=false` → "open", `active=true && closed=true` → "closed", `active=false` → "settled"

  **QA Scenarios**:
  ```
  Scenario: Gamma provider returns unified market
    Tool: Bash (httpx, asyncio)
    Preconditions: T9 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.polymarket.gamma import PolymarketGammaProvider; import asyncio; p = PolymarketGammaProvider(); m = asyncio.run(p.get_market('0x1fad72fae204143ff1c3035e99e7c0f65ea8d5cd9bd1070987bd1a3316f772be')); print(f'Question: {m.question}'); print(f'YES={m.yes_price} NO={m.no_price}'); print(f'Status: {m.status}')"
    Expected Result: UnifiedMarket with prices summing to ~1.0
    Evidence: .sisyphus/evidence/task-10-gamma-market.txt

  Scenario: Gamma provider search returns results
    Tool: Bash (httpx, asyncio)
    Preconditions: T9 complete
    Steps:
      1. Run: python3 -c "from traderbot.providers.polymarket.gamma import PolymarketGammaProvider; import asyncio; p = PolymarketGammaProvider(); ms = asyncio.run(p.search_markets('bitcoin', limit=3)); print(f'Found {len(ms)} markets'); [print(f'  {m.question[:50]}') for m in ms]"
    Expected Result: Markets with "bitcoin" in question
    Evidence: .sisyphus/evidence/task-10-gamma-search.txt
  ```

  **Evidence to Capture**:
  - [ ] Unified market mapping
  - [ ] Search functionality

  **Commit**: YES (group with T9)
  - Message: `feat(polymarket): add Gamma API data provider`

- [ ] 11. **Gamma integration tests**

  **What to do**:
  - Create `tests/providers/polymarket/test_gamma.py`:
    - Unit tests with mocked httpx transport
    - Integration tests against live Gamma API (no auth needed, always available)
    - Test market list, event list, single market, search
    - Test edge cases: empty results, pagination, inactive/archived markets
    - Test model transformations (Gamma JSON → UnifiedMarket)
  - Mock fixtures with realistic Gamma responses

  **Must NOT do**:
  - No tests that depend on specific market IDs existing forever (use condition_id query for known markets)

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T9, T10)
  - **Blocks**: T19-T22
  - **Blocked By**: T9, T10

  **References**:
  - pytest-asyncio patterns in existing tests

  **Acceptance Criteria**:
  - [ ] `pytest tests/providers/polymarket/test_gamma.py -v` passes
  - [ ] Unit tests cover all GammaClient methods
  - [ ] Integration tests verify real API responses
  - [ ] Model transform tests validate UnifiedMarket fields

  **QA Scenarios**:
  ```
  Scenario: All Gamma tests pass
    Tool: Bash (pytest)
    Preconditions: T9, T10 complete
    Steps:
      1. Run: python -m pytest tests/providers/polymarket/test_gamma.py -v --tb=short
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-11-gamma-tests.txt
  ```

  **Evidence to Capture**:
  - [ ] Full test output

  **Commit**: YES
  - Message: `test(polymarket): add Gamma API integration tests`
  - Files: `tests/providers/polymarket/`
  - Pre-commit: `python -m pytest tests/providers/polymarket/ -x`

- [ ] 12. **Polymarket CLOB auth + py-clob-client-v2 setup**

  **What to do**:
  - Add `py-clob-client-v2` to project dependencies (`pyproject.toml`)
  - Create `src/traderbot/providers/polymarket/clob.py`:
    - `PolymarketClobClient` wrapper:
      - `async def authenticate(self, private_key: str, creds: ApiCreds | None = None)` — L1 + L2 auth flow
      - `async def get_yes_token_id(self, condition_id: str) -> str` — resolves which clobTokenId is YES
      - `async def get_orderbook(self, token_id: str) -> UnifiedOrderBook` — `client.get_order_book(token_id)`
      - `async def get_midpoint(self, token_id: str) -> float` — `client.get_midpoint(token_id)`
      - `async def get_last_trade_price(self, token_id: str) -> float` — `client.get_last_trade_price(token_id)`
    - Credential resolution:
      - Load `POLYMARKET_PRIVATE_KEY` from `.env` or profile config
      - Auto-derive API credentials if not stored
      - Cache credentials for session lifetime
    - Error handling: auth failures → `ConfigurationError`, trading errors → provider-specific exceptions

  **Must NOT do**:
  - No hardcoded private keys
  - No synchronous wallet operations in async context

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — auth setup is tricky (Ethereum wallet signing)
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequential with T13, T14, T15)
  - **Parallel Group**: Wave 4 (starts after Wave 3)
  - **Blocks**: T13, T14, T15
  - **Blocked By**: T9, T10, T11

  **References**:
  - `py-clob-client-v2` README — auth flow: L1 (wallet sign) → L2 (HMAC API creds)
  - Polymarket authentication docs: `https://docs.polymarket.com/api-reference/authentication`
  - `src/traderbot/kalshi/signing.py` — existing signing pattern
  - `src/traderbot/kalshi/client.py:KalshiConfig` — config pattern to follow

  **Acceptance Criteria**:
  - [ ] `py-clob-client-v2` installed and importable
  - [ ] `PolymarketClobClient` authenticates with private key (unit test with mock)
  - [ ] Orderbook fetch works against CLOB (public endpoint, no auth needed)
  - [ ] Credential resolution from env var works

  **QA Scenarios**:
  ```
  Scenario: CLOB public orderbook fetch works
    Tool: Bash (httpx)
    Preconditions: None (CLOB public endpoint)
    Steps:
      1. Run: python3 -c "from traderbot.providers.polymarket.clob import PolymarketClobClient; import asyncio; c = PolymarketClobClient(); ob = asyncio.run(c.get_orderbook('98022490269692409998126496127597032490334070080325855126491859374983463996227')); print(f'Bids: {len(ob.bids)}, Asks: {len(ob.asks)}'); [print(f'  BID: price={b.price} size={b.size}') for b in ob.bids[:3]]"
    Expected Result: Orderbook with bids and asks
    Evidence: .sisyphus/evidence/task-12-clob-orderbook.txt

  Scenario: CLOB client handles auth credentials
    Tool: Bash (python -c with httpx mock)
    Preconditions: T9, T10 complete
    Steps:
      1. Mock API credentials response
      2. Assert client initializes correctly
    Expected Result: Client ready with L2 credentials
    Evidence: .sisyphus/evidence/task-12-clob-auth.txt
  ```

  **Evidence to Capture**:
  - [ ] Orderbook fetch
  - [ ] Auth flow

  **Commit**: YES (group with T13)
  - Message: `feat(polymarket): add CLOB client and execution provider`
  - Files: `src/traderbot/providers/polymarket/clob.py`, `pyproject.toml`
  - Pre-commit: `python -c "from py_clob_client_v2 import ClobClient; print('OK')"`

- [ ] 13. **Polymarket ExecutionProvider (order placement)**

  **What to do**:
  - Add to `src/traderbot/providers/polymarket/clob.py`:
    - `PolymarketExecutionProvider` implementing `ExecutionProvider`:
      - `async def place_order(self, order: UnifiedOrder) -> UnifiedOrder`:
        - Resolve token_id from condition_id
        - Convert UnifiedOrder → OrderArgs (token_id, price, side, size)
        - Determine OrderType: GTC for limit, FOK for market
        - Submit via `client.create_and_post_order()` or `client.create_and_post_market_order()`
        - Map response → UnifiedOrder
      - `async def cancel_order(self, provider_order_id: str) -> bool`:
        - `client.cancel_order(provider_order_id)`
      - `async def get_orders(self, *, market_id: str | None = None) -> list[UnifiedOrder]`:
        - `client.get_orders(market_id)` or all orders
    - Side mapping: `UnifiedOrder.side` ("yes"/"no") → `Side.BUY`/`Side.SELL` (for YES token)
      - Buying YES token at price X → `Side.BUY` at price X
      - Buying NO token (selling YES) → `Side.SELL` for YES token at price (1.0 - X)
    - Map order statuses: "RESTING" → "live", "FILLED" → "filled", "CANCELLED" → "cancelled"
    - Tick size validation: clamp price to `orderPriceMinTickSize` (from Gamma market data)

  **Must NOT do**:
  - No test orders sent to production API (use testnet chain_id=80002)
  - No order placement without prior risk check (risk module stays in control)
  - No direct `Ethereum private key` exposure in logs

  **Recommended Agent Profile**:
  - Category: `deep` — complex domain (Ethereum signing, order types, side mapping)
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after T12)
  - **Blocks**: T15, T21
  - **Blocked By**: T12

  **References**:
  - py-clob-client-v2 `OrderArgs`, `Side`, `OrderType`, `PartialCreateOrderOptions` — SDK order types
  - `src/traderbot/kalshi/trading.py:TradingService` — Existing order placement pattern
  - Polymarket orders doc: `https://docs.polymarket.com/trading/orders`
  - Verified live Gamma market: `orderPriceMinTickSize: 0.001`, `orderMinSize: 5`

  **Acceptance Criteria**:
  - [ ] `PolymarketExecutionProvider` implements `ExecutionProvider`
  - [ ] `place_order()` constructs correct SDK call (unit test, not live)
  - [ ] `cancel_order()` calls correct SDK method
  - [ ] `get_orders()` returns list of UnifiedOrder
  - [ ] Side mapping is mathematically correct (buy NO = sell YES at 1-X)
  - [ ] Tick size validation prevents invalid prices

  **QA Scenarios**:
  ```
  Scenario: Execution provider constructs valid order (unit test)
    Tool: Bash (python -c with mock)
    Preconditions: T12 complete
    Steps:
      1. Mock py-clob-client to capture call args
      2. Submit buy order for token_id, price=0.55, size=100
      3. Verify SDK called with correct OrderArgs
    Expected Result: SDK receives token_id, price=0.55, side=Side.BUY, size=100
    Evidence: .sisyphus/evidence/task-13-order-construct.txt

  Scenario: Side mapping works correctly
    Tool: Bash (python -c)
    Preconditions: T12 complete
    Steps:
      1. Test buy YES at 0.55 → Side.BUY, price=0.55
      2. Test buy NO at 0.45 → Side.SELL, price=0.55 (1.0 - 0.45)
    Expected Result: Correct side and price for NO orders
    Evidence: .sisyphus/evidence/task-13-side-mapping.txt
  ```

  **Evidence to Capture**:
  - [ ] Order construction
  - [ ] Side mapping correctness

  **Commit**: YES (group with T12)
  - Message: `feat(polymarket): add CLOB client and execution provider`

- [ ] 14. **Polymarket PortfolioProvider**

  **What to do**:
  - Add to `src/traderbot/providers/polymarket/clob.py`:
    - `PolymarketPortfolioProvider` implementing `PortfolioProvider`:
      - `async def get_balance(self) -> UnifiedBalance`:
        - Requires auth (L2). Calls `client.get_balances()` or Data API for USDC balance
        - Map to `UnifiedBalance(provider='polymarket', available=..., total=..., currency='USDC')`
      - `async def get_positions(self) -> list[UnifiedPosition]`:
        - `GET https://data-api.polymarket.com/positions?user={address}`
        - Or via `client.get_positions()` if available in SDK
        - Map each position to `UnifiedPosition`
      - `async def get_fills(self, *, limit=100) -> list[UnifiedFill]`:
        - `GET https://data-api.polymarket.com/trades?user={address}&limit={limit}`
        - Or via CLOB API
    - Use `httpx` for Data API calls (public, no auth needed)
    - Address resolution: derive from private key via SDK

  **Must NOT do**:
  - No caching (but 3600s balance TTL from Kalshi pattern may be replicated later)
  - No position modification in portfolio provider (read-only)

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after T13)
  - **Blocks**: T15, T21
  - **Blocked By**: T13 (needs authenticated client)

  **References**:
  - `src/traderbot/kalshi/portfolio.py:PortfolioService` — Existing portfolio pattern (balance cache, positions, fills)
  - Polymarket Data API: `https://data-api.polymarket.com` — positions, trades endpoints
  - `src/traderbot/profiles/auth.py` — Existing credential resolution pattern

  **Acceptance Criteria**:
  - [ ] `PolymarketPortfolioProvider` implements `PortfolioProvider`
  - [ ] `get_balance()` returns `UnifiedBalance` (unit test with mock)
  - [ ] `get_positions()` returns `list[UnifiedPosition]`
  - [ ] `get_fills()` returns `list[UnifiedFill]`

  **QA Scenarios**:
  ```
  Scenario: Portfolio provider returns valid balance structure
    Tool: Bash (python -c with mock)
    Preconditions: T12, T13 complete
    Steps:
      1. Mock Data API response for balance
      2. Call get_balance()
      3. Assert UnifiedBalance has provider='polymarket', currency='USDC'
    Expected Result: UnifiedBalance with correct fields
    Evidence: .sisyphus/evidence/task-14-balance.txt

  Scenario: Portfolio provider handles empty positions
    Tool: Bash (python -c with mock)
    Preconditions: T12, T13 complete
    Steps:
      1. Mock empty positions response
      2. Call get_positions()
    Expected Result: Empty list, no error
    Evidence: .sisyphus/evidence/task-14-empty-positions.txt
  ```

  **Evidence to Capture**:
  - [ ] Balance structure
  - [ ] Empty state handling

  **Commit**: YES (group with T15)
  - Message: `feat(polymarket): add portfolio provider and tests`
  - Files: updates to `src/traderbot/providers/polymarket/clob.py`

- [ ] 15. **Polymarket CLOB integration tests**

  **What to do**:
  - Create `tests/providers/polymarket/test_clob.py`:
    - Unit tests with mocked `py-clob-client-v2` responses
    - Integration tests against live CLOB (public endpoints only: orderbook, midpoint, last trade price)
    - Auth integration test (skip if POLYMARKET_PRIVATE_KEY not set)
    - Test order construction, side mapping, tick validation
    - Test error scenarios: network failure, invalid token_id, auth failure
  - Mock fixtures for CLOB API responses
  - Integration test for orderbook fetch (public, no auth)
  - Integration test for Gamma → CLOB linkage (condition_id → token_id → orderbook)

  **Must NOT do**:
  - No auth integration tests that would submit real orders
  - No hardcoded token_ids (fetch via Gamma first)

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after T13, T14)
  - **Blocks**: T19-T22
  - **Blocked By**: T12, T13, T14

  **References**:
  - `tests/risk/test_evaluate_trade_profile.py` — Existing test patterns for mock-based testing
  - pytest-asyncio for async test support

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/providers/polymarket/test_clob.py -v` passes
  - [ ] Public CLOB integration tests pass (no auth needed)
  - [ ] Auth tests skip gracefully when no private key configured
  - [ ] Side mapping tests cover buy-yes, buy-no, sell-yes, sell-no

  **QA Scenarios**:
  ```
  Scenario: All CLOB tests pass (unit + public integration)
    Tool: Bash (pytest)
    Preconditions: T12-T14 complete
    Steps:
      1. Run: python -m pytest tests/providers/polymarket/test_clob.py -v --tb=short
    Expected Result: All unit tests pass, public integration tests pass
    Evidence: .sisyphus/evidence/task-15-clob-tests.txt
  ```

  **Evidence to Capture**:
  - [ ] Full test output

  **Commit**: YES (group with T14)
  - Message: `test(polymarket): add CLOB integration and unit tests`
  - Files: `tests/providers/polymarket/test_clob.py`
  - Pre-commit: `python -m pytest tests/providers/polymarket/test_clob.py -x`

- [ ] 16. **Kalshi DataProvider facade**

  **What to do**:
  - Create `src/traderbot/providers/kalshi.py`:
    - `KalshiDataProvider` implementing `DataProvider`:
      - Wraps existing `ProdDataProvider` + `MarketService`
      - `async def search_markets(self, query: str, *, limit=50, **filters)` → uses `MarketService.list_markets()` with search-like params
      - `async def get_market(self, provider_id: str)` → `ProdDataProvider.get_market(ticker)` where ticker = provider_id
      - `async def get_orderbook(self, provider_id: str)` → `ProdDataProvider.get_orderbook(ticker)`
      - `async def get_price_history(self, provider_id: str, *, limit=100)` → not available via existing API (raises `NotImplementedError`)
      - `async def get_candlesticks(self, provider_id: str, *, interval="1h", limit=100)` → not available (raises `NotImplementedError`)
    - Map `MarketSnapshot` → `UnifiedMarket`:
      - `ticker` → `provider_id`
      - `status` → "open" etc. (same values)
      - `open_interest_cents / 100` → `volume_usd` (approximate)
      - No price in MarketSnapshot — need to fetch orderbook for implied prob
    - Use existing `KalshiClient` + `TradingService` internally
    - Configure via existing `KalshiConfig`

  **Must NOT do**:
  - No changes to existing `ProdDataProvider` or `MarketService`
  - No duplicate caching (let the underlying provider handle it)

  **Recommended Agent Profile**:
  - Category: `quick` — simple wrapper around existing code
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T17, T18)
  - **Blocks**: T19-T22
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - `src/traderbot/kalshi/provider.py:ProdDataProvider` — wraps existing `get_market()`, `get_orderbook()`
  - `src/traderbot/kalshi/markets.py:MarketService` — existing market listing
  - `src/traderbot/kalshi/models.py:Market` — existing market model

  **Acceptance Criteria**:
  - [ ] `KalshiDataProvider` implements `DataProvider`
  - [ ] `get_market()` returns `UnifiedMarket` (wraps existing)
  - [ ] `search_markets()` returns `list[UnifiedMarket]`
  - [ ] Registration with ProviderRegistry works
  - [ ] `traderbot scan` (default, no flag) continues working

  **QA Scenarios**:
  ```
  Scenario: Kalshi data provider wraps existing functionality
    Tool: Bash (python -c with pytest)
    Preconditions: T1-T4 complete
    Steps:
      1. Unit test: create KalshiDataProvider with mock ProdDataProvider
      2. Call get_market with known ticker
    Expected Result: UnifiedMarket returned with provider='kalshi'
    Evidence: .sisyphus/evidence/task-16-kalshi-facade.txt
  ```

  **Evidence to Capture**:
  - [ ] Facade works with mock

  **Commit**: YES (group with T17, T18)
  - Message: `refactor(kalshi): add provider protocol facades`
  - Files: `src/traderbot/providers/kalshi.py`
  - Pre-commit: `python -c "from traderbot.providers.kalshi import KalshiDataProvider; print('OK')"`

- [ ] 17. **Kalshi ExecutionProvider facade**

  **What to do**:
  - Add to `src/traderbot/providers/kalshi.py`:
    - `KalshiExecutionProvider` implementing `ExecutionProvider`:
      - Wraps existing `TradingService`
      - `async def place_order(self, order: UnifiedOrder) -> UnifiedOrder`:
        - Map `UnifiedOrder.side` ("yes"/"no") → `OrderSideV2.bid`/`OrderSideV2.ask`
        - Map price (float 0-1) → cents (int): `int(price * 100)`
        - Map size to integer count
        - Create `OrderRequest` → submit via `TradingService.place_order()`
        - Map response `OrderResult` → `UnifiedOrder`
      - `async def cancel_order(self, provider_order_id: str) -> bool` → `TradingService.cancel_order()`
      - `async def get_orders(self, *, market_id=None) -> list[UnifiedOrder]` → `TradingService.list_orders(ticker=market_id)`

  **Must NOT do**:
  - No changes to existing `TradingService`
  - No risk check duplication (risk module handles this)

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T16, T18)
  - **Blocks**: T19-T22
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - `src/traderbot/kalshi/trading.py:TradingService` — Existing order placement

  **Acceptance Criteria**:
  - [ ] `KalshiExecutionProvider` implements `ExecutionProvider`
  - [ ] `place_order()` correctly maps UnifiedOrder → OrderRequest
  - [ ] `cancel_order()` wraps TradingService
  - [ ] Price mapping: 0.55 → 55 cents

  **QA Scenarios**:
  ```
  Scenario: Price and side mapping is correct
    Tool: Bash (python -c)
    Preconditions: T1-T4 complete
    Steps:
      1. Unit test: submit buy-yes at 0.55 → verify OrderRequest has side='bid', price='55'
      2. Unit test: submit buy-no at 0.45 → verify side='bid' for NO at 0.45
    Expected Result: Correct V2 API mapping
    Evidence: .sisyphus/evidence/task-17-kalshi-map.txt
  ```

  **Evidence to Capture**:
  - [ ] Price mapping validation

  **Commit**: YES (group with T16, T18)
  - Message: `refactor(kalshi): add provider protocol facades`

- [ ] 18. **Kalshi PortfolioProvider facade**

  **What to do**:
  - Add to `src/traderbot/providers/kalshi.py`:
    - `KalshiPortfolioProvider` implementing `PortfolioProvider`:
      - Wraps existing `PortfolioService`
      - `async def get_balance(self) -> UnifiedBalance`:
        - `PortfolioService.get_cached_balance()` → extract `available`, `total` (cents) → convert to unified
        - `currency` = "USD"
      - `async def get_positions(self) -> list[UnifiedPosition]`:
        - `PortfolioService.get_positions()` → map each `Position` → `UnifiedPosition`
      - `async def get_fills(self, *, limit=100) -> list[UnifiedFill]`:
        - `PortfolioService.get_fills(limit=limit)` → map each `Fill` → `UnifiedFill`
    - Register with `ProviderRegistry` as `kalshi` during init

  **Must NOT do**:
  - No changes to existing `PortfolioService`

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with T16, T17)
  - **Blocks**: T19-T22
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - `src/traderbot/kalshi/portfolio.py:PortfolioService` — Existing portfolio

  **Acceptance Criteria**:
  - [ ] `KalshiPortfolioProvider` implements `PortfolioProvider`
  - [ ] `get_balance()` returns `UnifiedBalance`
  - [ ] `get_positions()` returns `list[UnifiedPosition]`
  - [ ] All Kalshi facades auto-register with ProviderRegistry

  **QA Scenarios**:
  ```
  Scenario: Kalshi portfolio facade returns unified balance
    Tool: Bash (python -c with mock)
    Preconditions: T1-T4 complete
    Steps:
      1. Unit test: create with mock PortfolioService
      2. Call get_balance()
    Expected Result: UnifiedBalance with provider='kalshi'
    Evidence: .sisyphus/evidence/task-18-kalshi-portfolio.txt
  ```

  **Evidence to Capture**:
  - [ ] Portfolio facade test

  **Commit**: YES (group with T16, T17)
  - Message: `refactor(kalshi): add provider protocol facades`

- [ ] 19. **CLI `--provider` flag support**

  **What to do**:
  - Add `--provider` option to CLI commands:
    - `scan`: `--provider {kalshi|polymarket|oddspipe}`, default `kalshi`
    - `analyze`: `--provider` flag
    - `trade`: `--provider` flag
  - In `src/traderbot/cli.py`:
    - Add `ProviderOption` as a shared click option or typer argument
    - Default: `"kalshi"` (backward compatible)
    - `resolve_provider(name: str) -> tuple[DataProvider, ExecutionProvider | None]` — uses `ProviderRegistry`
  - Auto-register providers at CLI startup:
    - `init_providers()` called on CLI entry
    - Registers: kalshi (always), oddspipe (if key configured), polymarket (always for data, auth-key for execution)
  - Update help text to show available providers

  **Must NOT do**:
  - No changes to existing default behavior (no `--provider` = Kalshi, same as today)
  - No breaking changes to command output format

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on all providers)
  - **Parallel Group**: Wave 6 (after Waves 2-5)
  - **Blocks**: T20, T21, T22
  - **Blocked By**: T5-T8, T9-T11, T12-T15, T16-T18

  **References**:
  - `src/traderbot/cli.py` — Existing CLI structure (typer-based)
  - `src/traderbot/providers/registry.py` — ProviderRegistry

  **Acceptance Criteria**:
  - [ ] `traderbot scan --help` shows `--provider` option
  - [ ] `traderbot scan` (no flag) works identically to before
  - [ ] `traderbot scan --provider oddspipe` returns OddsPipe data
  - [ ] `traderbot scan --provider polymarket` returns Polymarket data
  - [ ] Invalid provider shows error with available options

  **QA Scenarios**:
  ```
  Scenario: Default CLI still works (backward compatible)
    Tool: Bash (traderbot command)
    Preconditions: All provider tasks complete
    Steps:
      1. Run: traderbot scan --limit 3
    Expected Result: Markets from Kalshi (same format as before)
    Evidence: .sisyphus/evidence/task-19-default-cli.txt

  Scenario: Provider flag works for OddsPipe
    Tool: Bash (traderbot command)
    Preconditions: All provider tasks complete, ODDSPIPE_API_KEY set
    Steps:
      1. Run: traderbot scan --provider oddspipe --limit 3
    Expected Result: Markets from OddsPipe (mixed Kalshi+Polymarket)
    Evidence: .sisyphus/evidence/task-19-oddspipe-cli.txt
  ```

  **Evidence to Capture**:
  - [ ] Default CLI output
  - [ ] OddsPipe provider output

  **Commit**: YES (group with T20, T21, T22)
  - Message: `feat(cli): add multi-provider CLI commands`
  - Files: `src/traderbot/cli.py`
  - Pre-commit: `traderbot scan --help`

- [ ] 20. **Provider-aware scan command**

  **What to do**:
  - Refactor `traderbot scan` to use the provider system:
    - No flag: uses Kalshi DataProvider (existing behavior)
    - `--provider kalshi`: explicit Kalshi scan
    - `--provider oddspipe`: scan via OddsPipe (returns mixed Kalshi+Polymarket)
    - `--provider polymarket`: scan via Polymarket Gamma
    - `--search`: passes to `DataProvider.search_markets()`
    - `--category`: filters by category (provider-specific)
    - `--status`: filters by status
  - Output format:
    - Same table format as current scan
    - Add `Provider` column when showing multi-provider data
    - Handle provider-specific fields gracefully

  **Must NOT do**:
  - No changes to default output format unless explicitly requested
  - No breaking changes to machine-readable output (JSON mode)

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6
  - **Blocks**: None
  - **Blocked By**: T19

  **References**:
  - `src/traderbot/cli.py:scan()` — Existing scan command

  **Acceptance Criteria**:
  - [ ] `traderbot scan --search "bitcoin"` returns relevant markets from default provider
  - [ ] `traderbot scan --provider oddspipe --search "trump"` returns cross-platform results
  - [ ] Output is readable with provider column

  **QA Scenarios**:
  ```
  Scenario: Scan with search works across providers
    Tool: Bash (traderbot)
    Preconditions: T19 complete
    Steps:
      1. Run: traderbot scan --provider oddspipe --search "bitcoin" --limit 5
    Expected Result: Bitcoin-related markets from both Kalshi and Polymarket
    Evidence: .sisyphus/evidence/task-20-scan-search.txt
  ```

  **Evidence to Capture**:
  - [ ] Search output

  **Commit**: YES (group with T19)

- [ ] 21. **Provider-aware analyze command**

  **What to do**:
  - Update `traderbot analyze` to support multi-provider:
    - `--provider` flag to specify source
    - Market lookup uses `DataProvider.get_market()` + `get_orderbook()`
    - Display orderbook data regardless of provider
    - Handle providers that lack orderbook data (graceful fallback)
  - Add `--spreads` flag (only with `--provider oddspipe`):
    - Shows cross-platform price divergences
    - `--min-spread 0.05` to filter by minimum spread
    - `--limit 20` for maximum results
    - Output: comparison table with side-by-side prices

  **Must NOT do**:
  - No spread feature for non-OddsPipe providers

  **Recommended Agent Profile**:
  - Category: `unspecified-medium`
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6
  - **Blocks**: None
  - **Blocked By**: T19

  **References**:
  - `src/traderbot/cli.py:analyze()` — Existing analyze command
  - `src/traderbot/analysis/odds.py:implied_probability()` — Existing analysis

  **Acceptance Criteria**:
  - [ ] `traderbot analyze <market_id> --provider oddspipe` shows market details
  - [ ] `traderbot analyze <condition_id> --provider polymarket` shows Gamma data
  - [ ] `traderbot analyze --provider oddspipe --spreads --min-spread 0.05` shows cross-platform spreads
  - [ ] Analyze without `--provider` works as before (Kalshi)

  **QA Scenarios**:
  ```
  Scenario: Analyze with cross-platform spreads
    Tool: Bash (traderbot)
    Preconditions: T19, T20 complete
    Steps:
      1. Run: traderbot analyze --provider oddspipe --spreads --min-spread 0.10 --limit 5
    Expected Result: Table of cross-platform price differences > 10%
    Evidence: .sisyphus/evidence/task-21-spreads.txt
  ```

  **Evidence to Capture**:
  - [ ] Spreads output

  **Commit**: YES (group with T19, T20, T22)

- [ ] 22. **Cross-provider spread CLI command**

  **What to do**:
  - Add `traderbot spreads` subcommand:
    - Shows cross-platform price divergences (uses OddsPipe)
    - Flags: `--min-spread`, `--limit`, `--platform` (filter by one side), `--search`
    - Output: comparison table with columns [Platform A | Price A | Platform B | Price B | Difference]
    - Color-coded: green when `abs(diff) < 0.02`, yellow when `0.02-0.10`, red when > 0.10
    - Auto-refresh via `--watch` flag (polls every 30s)
    - JSON output via `--json` flag
  - Backend: calls `OddsPipeProvider.get_spreads()`
  - Error handling: graceful if OddsPipe is down

  **Must NOT do**:
  - No changes to existing analyze or scan commands
  - No hardcoded spread thresholds

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — CLI table formatting with color
  - Skills: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6
  - **Blocks**: None
  - **Blocked By**: T19 (needs `--provider` infrastructure)

  **References**:
  - `src/traderbot/cli.py` — CLI patterns (typer subcommands)
  - OddsPipe spread response (verified live): `{yes_diff, direction: 'kalshi_higher'|'polymarket_higher', note}`

  **Acceptance Criteria**:
  - [ ] `traderbot spreads` shows cross-platform price differences
  - [ ] `traderbot spreads --min-spread 0.10` filters by minimum
  - [ ] `traderbot spreads --json` outputs machine-readable JSON
  - [ ] `traderbot spreads --watch` refreshes every 30s
  - [ ] Error message if OddsPipe not configured

  **QA Scenarios**:
  ```
  Scenario: Spreads command shows live cross-platform divergences
    Tool: Bash (traderbot)
    Preconditions: OddsPipe configured
    Steps:
      1. Run: traderbot spreads --limit 5
    Expected Result: Table showing 5 pairs with cross-platform prices
    Evidence: .sisyphus/evidence/task-22-spreads-cmd.txt

  Scenario: Spreads command JSON output
    Tool: Bash (traderbot)
    Preconditions: OddsPipe configured
    Steps:
      1. Run: traderbot spreads --limit 2 --json
    Expected Result: Valid JSON output
    Evidence: .sisyphus/evidence/task-22-spreads-json.txt
  ```

  **Evidence to Capture**:
  - [ ] Spreads table
  - [ ] JSON output

  **Commit**: YES (group with T19, T20, T21)
  - Message: `feat(cli): add multi-provider CLI commands`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command, check output). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `mypy src/traderbot/providers/` + `ruff check` + `ruff format --check` + `pytest tests/providers/`. Review for: `Any` type leaks, bare `except:`, commented-out code, unused imports, AI slop.
  Output: `Types [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | VERDICT`

- [ ] F3. **End-to-End Integration QA** — `unspecified-high`
  Start from clean state. Test: `traderbot scan --provider oddspipe` returns real markets. `traderbot scan --provider polymarket` returns real markets. `traderbot scan` (no flag) defaults to Kalshi. All evidence captured.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Verify everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- T1-T3: `feat(providers): add cross-provider data models and protocol definitions`
- T4: `test(providers): add test infrastructure and mock providers`
- T5-T6: `feat(oddspipe): add OddsPipe HTTP client and market search`
- T7-T8: `feat(oddspipe): add cross-platform spreads and history`
- T9-T10: `feat(polymarket): add Gamma API data provider`
- T11: `test(polymarket): add Gamma integration tests`
- T12-T13: `feat(polymarket): add CLOB execution provider`
- T14-T15: `feat(polymarket): add portfolio provider and tests`
- T16-T18: `refactor(kalshi): add provider protocol facades`
- T19-T22: `feat(cli): add multi-provider CLI commands`

## Success Criteria

### Verification Commands
```bash
# Default Kalshi still works
traderbot scan --limit 3

# OddsPipe unified data
traderbot scan --provider oddspipe --limit 3

# Polymarket direct data
traderbot scan --provider polymarket --limit 3

# Cross-platform spreads
traderbot scan --provider oddspipe --spreads --min-spread 0.05

# All tests pass
pytest tests/providers/ -v
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All existing Kalshi commands continue working
- [ ] `traderbot scan --provider oddspipe` returns real data from both platforms
- [ ] `traderbot scan --provider polymarket` returns real data from Gamma API
- [ ] Cross-platform spreads available to agent
