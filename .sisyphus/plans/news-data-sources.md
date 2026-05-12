# News Data Source Expansion — 8 New Sources

## TL;DR

> **Quick Summary**: Add 8 new data sources (Open-Meteo, CoinGecko, TheSportsDB, CoinCap, OpenWeatherMap, Ballotpedia, FRED, Google Trends) to the TraderBot news pipeline, following the existing NewsAggregator pattern with a new `DataPoint` model for structured data (forecasts, prices, scores).
> 
> **Deliverables**:
> - `DataPoint` Pydantic model for structured data (forecasts, prices, economic indicators)
> - 8 new `NewsSource` enum members with category coverage mappings
> - `DataSourcesConfig` replacing per-key `__init__` params to avoid parameter bloat
> - Source-specific fetch methods in `NewsAggregator` for all 8 new sources
> - `resolve_*_key` functions for API-key-requiring sources (OpenWeatherMap, FRED)
> - `SOURCE_CATEGORY_COVERAGE` dict mapping each source to its supported categories
> - CLI `--source` flag support for all new sources in `traderbot news`
> - `@pytest.mark.live` integration tests for each source with real API calls
> - Updated TOOLS.md and AGENTS.md documenting all sources
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: T1 (DataPoint model) → T2 (DataSourcesConfig) → T3-T7 (no-key sources) → T8-T10 (key-required sources) → T11 (CLI) → T12-T13 (tests) → F1-F4

---

## Context

### Original Request
Add 8 new data sources to the TraderBot news pipeline. User explicitly requested: Open-Meteo, CoinGecko, TheSportsDB, CoinCap, OpenWeatherMap, Ballotpedia, FRED, and Google Trends. User stated: "It doesn't hurt for us to offer backup/alternative sources for our agent to compare multiple perspectives." User insisted: "Be very careful in not making assumptions and implement API requirements exactly. Refer to docs if uncertain."

### Interview Summary
**Key Discussions**:
- Weather agent returned empty results from NewsAPI — structured weather data (forecasts) is what's actually needed
- User wants backup/alternative sources for cross-perspective comparison
- User included Ballotpedia, CoinCap, OpenWeatherMap despite being lower priority
- Tests should use real API tokens against real APIs (@pytest.mark.live)

**Research Findings**:
- 4 sources need NO API key: Open-Meteo, CoinGecko (basic), TheSportsDB (key "3"), CoinCap
- 2 sources need API keys: OpenWeatherMap (free), FRED (free, register)
- 2 sources are non-API: Ballotpedia (RSS only), Google Trends (scraping via pytrends)
- Existing `NewsItem` model doesn't fit structured data — need new `DataPoint` model
- Current `NewsAggregator.__init__` takes individual key params — adding 8 more is unwieldy

### Metis Review
**Identified Gaps** (addressed):
- Structured data (forecasts/prices) ≠ news articles → Added `DataPoint` model
- `resolve_*_key` returning None means "skip" but no-key sources need "None = normal" → Added `requires_api_key` flag per source
- No source→category mapping exists → Added `SOURCE_CATEGORY_COVERAGE` dict
- `__init__` parameter bloat → Added `DataSourcesConfig` dataclass
- Google Trends fragility → Added graceful degradation + health check
- `pycoingecko`/`fredapi`/`pytrends` as deps → Using plain httpx for all sources (minimize deps)
- Parallel versus sequential fetch → New `fetch_all` uses `asyncio.gather` for parallel

---

## Work Objectives

### Core Objective
Add 8 new data sources to the news pipeline with proper structured data support, enabling agents to compare multiple perspectives across categories.

### Concrete Deliverables
- `src/traderbot/news/models.py`: New `DataPoint` model + 8 new `NewsSource` enum members
- `src/traderbot/news/sources.py`: 8 new fetch methods + `DataSourcesConfig` + `SOURCE_CATEGORY_COVERAGE`
- `src/traderbot/profiles/config.py`: 2 new `resolve_*_key` functions (OpenWeatherMap, FRED)
- `src/traderbot/cli.py`: CLI `--source` support for all new sources
- `tests/news/test_live_sources.py`: `@pytest.mark.live` integration tests
- `tests/news/test_sources.py`: Unit tests with mocks
- `.openclaw/workspace/TOOLS.md`: Updated source documentation
- `.openclaw/workspace/AGENTS.md`: Updated source references

### Definition of Done
- [ ] All 8 sources return data when called with real API keys (live tests)
- [ ] All 8 sources degrade gracefully when keys are missing or APIs fail (mock tests)
- [ ] `traderbot news --source openmeteoey --category weather` returns weather forecasts
- [ ] `traderbot news --source coingecko --category crypto` returns crypto prices
- [ ] All existing tests still pass (zero regressions)

### Must Have
- Every source follows httpx.AsyncClient pattern with retry/backoff
- Structured data sources produce `DataPoint` objects, not forced `NewsItem`
- No-key sources work without any configuration (Open-Meteo, CoinGecko basic, TheSportsDB, CoinCap)
- Each source has explicit `SOURCE_CATEGORY_COVERAGE` — won't be called for unsupported categories
- All monetary values in cents as `int` (never float) per AGENTS.md
- `pyproject.toml` updated with new optional dependencies group `[news-extras]`
- `DataSourcesConfig` with sensible defaults so callers don't need 10 params

### Must NOT Have (Guardrails)
- Do NOT add `pycoingecko`, `fredapi`, or `pytrends` as required dependencies — use plain httpx
- Do NOT add WebSocket connections (future work, explicitly out of scope)
- Do NOT add `SerpAPI` paid integration for Google Trends
- Do NOT modify the risk module or analysis module
- Do NOT add `from __future__ import annotations` in any Typer module
- Do NOT use `float` for monetary values — always `int` cents
- Do NOT make real API calls in non-live unit tests
- Do NOT force structured data (forecasts, prices) into `NewsItem` — use `DataPoint`
- Do NOT assume OpenWeatherMap free tier has unlimited calls — enforce 1K/day budget
- Do NOT assume pytrends is reliable — treat it as best-effort with aggressive timeout

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after
- **Framework**: pytest with async support
- **Live tests**: `@pytest.mark.live` with real API keys (skip gracefully if no keys)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API sources**: Use Bash (curl) — Send requests, assert status + response fields
- **CLI commands**: Use Bash — Run traderbot commands, assert output
- **Python modules**: Use Bash (pytest) — Run tests, verify pass/fail

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — models, config, architecture):
├── Task 1: DataPoint model + NewsSource enum expansion [quick]
├── Task 2: DataSourcesConfig + SOURCE_CATEGORY_COVERAGE [quick]
├── Task 3: resolve_*_key functions for OpenWeatherMap/FRED [quick]

Wave 2 (No-key sources — MAX PARALLEL, all independent):
├── Task 4: Open-Meteo weather source (depends: 1, 2) [deep]
├── Task 5: CoinGecko crypto source (depends: 1, 2) [deep]
├── Task 6: TheSportsDB sports source (depends: 1, 2) [deep]
├── Task 7: CoinCap crypto source (depends: 1, 2) [unspecified-high]
├── Task 8: Ballotpedia elections RSS source (depends: 1, 2) [unspecified-high]

Wave 3 (Key-required sources — API keys needed, independent):
├── Task 9: OpenWeatherMap weather source (depends: 1, 2, 3) [deep]
├── Task 10: FRED economics source (depends: 1, 2, 3) [deep]
├── Task 11: Google Trends mentions source (depends: 1, 2) [deep]

Wave 4 (Integration + CLI + Documentation):
├── Task 12: CLI integration + fetch_all refactor (depends: 4-11) [unspecified-high]
├── Task 13: Workspace docs update — TOOLS.md + AGENTS.md (depends: 12) [writing]

Wave 5 (Tests — after all sources implemented):
├── Task 14: Live integration tests (depends: 4-11) [deep]
├── Task 15: Unit tests with mocks (depends: 4-11) [unspecified-high]

Wave FINAL (Reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: T1 → T2 → T4-T8 → T12 → T14-T15 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 5 (Wave 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | - | 2-15 | 1 |
| 2 | 1 | 4-15 | 1 |
| 3 | - | 9, 10 | 1 |
| 4 | 1, 2 | 12, 14, 15 | 2 |
| 5 | 1, 2 | 12, 14, 15 | 2 |
| 6 | 1, 2 | 12, 14, 15 | 2 |
| 7 | 1, 2 | 12, 14, 15 | 2 |
| 8 | 1, 2 | 12, 14, 15 | 2 |
| 9 | 1, 2, 3 | 12, 14, 15 | 3 |
| 10 | 1, 2, 3 | 12, 14, 15 | 3 |
| 11 | 1, 2 | 12, 14, 15 | 3 |
| 12 | 4-11 | 13 | 4 |
| 13 | 12 | - | 4 |
| 14 | 4-11 | F1-F4 | 5 |
| 15 | 4-11 | F1-F4 | 5 |
| F1-F4 | 14, 15 | - | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 3 tasks — T1 `quick`, T2 `quick`, T3 `quick`
- **Wave 2**: 5 tasks — T4 `deep`, T5 `deep`, T6 `deep`, T7 `unspecified-high`, T8 `unspecified-high`
- **Wave 3**: 3 tasks — T9 `deep`, T10 `deep`, T11 `deep`
- **Wave 4**: 2 tasks — T12 `unspecified-high`, T13 `writing`
- **Wave 5**: 2 tasks — T14 `deep`, T15 `unspecified-high`
- **FINAL**: 4 tasks — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [x] 1. DataPoint Model + NewsSource Enum Expansion

  **What to do**:
  - Add `DataPoint` Pydantic model to `src/traderbot/news/models.py` with fields: `id`, `source` (NewsSource), `category` (NewsCategory), `title` (str), `data` (dict — structured payload like temp/price/score), `timestamp` (datetime), `ticker_refs` (list[str]), `metadata` (dict — source-specific extras)
  - `DataPoint` uses `ConfigDict(strict=True, extra="forbid")`
  - Add 8 new `NewsSource` enum members: `OPEN_METEO`, `COINGECKO`, `THESPORTSDB`, `COINCAP`, `OPENWEATHERMAP`, `BALLOTPEDIA`, `FRED`, `GOOGLE_TRENDS`
  - Update `__all__` exports in `models.py` and `__init__.py`
  - All monetary values in `data` dict as `int` cents — never float

  **Must NOT do**:
  - Do NOT modify existing `NewsSource` members (newsapi, twitter, reddit)
  - Do NOT add `from __future__ import annotations` in any Typer module
  - Do NOT use `float` for any monetary value

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 2-15
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/news/models.py:NewsSource` — Existing StrEnum pattern to extend with 8 new members
  - `src/traderbot/news/models.py:NewsItem` — Existing Pydantic model pattern to follow for DataPoint (ConfigDict, Field validators)

  **API/Type References**:
  - `src/traderbot/kalshi/models.py:MarketCategory` — `NewsCategory = MarketCategory` alias; all 14 category values

  **WHY Each Reference Matters**:
  - `NewsSource` shows exactly how to add enum members (StrEnum, lowercase snake_case values)
  - `NewsItem` shows the Pydantic model convention (which fields are required vs optional, ConfigDict pattern)
  - `MarketCategory` confirms 14 categories that new sources must map to

  **Acceptance Criteria**:
  - [ ] `DataPoint` model defined with all 6 fields
  - [ ] 8 new `NewsSource` members added
  - [ ] `from traderbot.news.models import DataPoint, NewsSource` works
  - [ ] All `DataPoint` monetary values use `int` cents

  **QA Scenarios**:

  ```
  Scenario: DataPoint model creation
    Tool: Bash
    Preconditions: Python 3.12+ with traderbot installed
    Steps:
      1. Run `python -c "from traderbot.news.models import DataPoint, NewsSource; dp = DataPoint(id='test', source=NewsSource.OPEN_METEO, category='weather', title='NYC Forecast', data={'temp_c': 22}, timestamp='2026-05-12T12:00:00Z', ticker_refs=[], metadata={}); print(dp.model_dump_json())"`
      2. Assert output contains `"source":"open_meteo"` and `"temp_c":22`
    Expected Result: DataPoint serializes correctly with new NewsSource enum
    Failure Indicators: ImportError, ValidationError, or missing fields
    Evidence: .sisyphus/evidence/task-1-datapoint-model.txt

  Scenario: All 8 new NewsSource members exist
    Tool: Bash
    Preconditions: Python 3.12+ with traderbot installed
    Steps:
      1. Run `python -c "from traderbot.news.models import NewsSource; members = ['OPEN_METEO','COINGECKO','THESPORTSDB','COINCAP','OPENWEATHERMAP','BALLOTPEDIA','FRED','GOOGLE_TRENDS']; print(all(hasattr(NewsSource, m) for m in members))"`
      2. Assert output is `True`
    Expected Result: All 8 new enum members accessible
    Failure Indicators: `False` or `AttributeError`
    Evidence: .sisyphus/evidence/task-1-news-source-enum.txt
  ```

  **Commit**: YES
  - Message: `feat(news): add DataPoint model and extend NewsSource enum`
  - Files: `src/traderbot/news/models.py`, `src/traderbot/news/__init__.py`
  - Pre-commit: `python -c "from traderbot.news.models import DataPoint, NewsSource"`

- [x] 2. DataSourcesConfig + SOURCE_CATEGORY_COVERAGE

  **What to do**:
  - Add `DataSourcesConfig` dataclass to `src/traderbot/news/sources.py` replacing the growing number of `__init__` params. Fields: `newsapi_key`, `openweather_key`, `fred_key`, `reddit_subreddits`, `daily_budget` — with `None` defaults
  - Add `SOURCE_CATEGORY_COVERAGE` dict mapping each `NewsSource` to its supported `NewsCategory` list. This prevents calling a source for unsupported categories (e.g., don't call Open-Meteo for crypto):
    - `OPEN_METEO`: [WEATHER]
    - `COINGECKO`: [CRYPTO, MENTIONS]
    - `THESPORTSDB`: [SPORTS]
    - `COINCAP`: [CRYPTO]
    - `OPENWEATHERMAP`: [WEATHER]
    - `BALLOTPEDIA`: [ELECTIONS, POLITICS]
    - `FRED`: [ECONOMICS, FINANCIALS]
    - `GOOGLE_TRENDS`: [MENTIONS, SOCIAL]
  - Add `SOURCE_REQUIRES_KEY` frozenset: sources that need API keys (OPENWEATHERMAP, FRED). Sources NOT in this set work without keys.
  - Update `NewsAggregator.__init__` to accept `DataSourcesConfig` while maintaining backward compatibility (individual params still work, wrapped into config)
  - Add `requires_api_key` property to determine if a source needs a key that's missing

  **Must NOT do**:
  - Do NOT break existing `NewsAggregator(newsapi_key=...)` call sites
  - Do NOT remove existing category mapping dicts (NEWSAPI_CATEGORY_QUERIES, REDDIT_CATEGORY_SUBREDDITS)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 1 (depends on Task 1 completing first)
  - **Blocks**: Tasks 4-11
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator.__init__` (lines 79-100) — Current param pattern to refactor into DataSourcesConfig
  - `src/traderbot/news/sources.py:NEWSAPI_CATEGORY_QUERIES` (lines 21-36) — Category mapping dict pattern to follow for SOURCE_CATEGORY_COVERAGE

  **API/Type References**:
  - `src/traderbot/news/models.py:NewsSource` — Enum members used as keys in SOURCE_CATEGORY_COVERAGE
  - `src/traderbot/news/models.py:NewsCategory` — 14 Category enum values for coverage mapping

  **WHY Each Reference Matters**:
  - `__init__` shows the exact params that need wrapping into DataSourcesConfig
  - `NEWSAPI_CATEGORY_QUERIES` shows the dict[Enum, value] pattern for category mappings
  - `NewsSource`/`NewsCategory` confirm the exact enum values to use as dict keys

  **Acceptance Criteria**:
  - [ ] `DataSourcesConfig` defined with all key fields
  - [ ] `SOURCE_CATEGORY_COVERAGE` has entries for all 8 new sources + existing 3
  - [ ] `SOURCE_REQUIRES_KEY` contains OPENWEATHERMAP and FRED
  - [ ] `NewsAggregator.__init__` accepts both `config: DataSourcesConfig` and legacy individual params
  - [ ] Existing call sites (tests, CLI) still work without changes

  **QA Scenarios**:

  ```
  Scenario: DataSourcesConfig backward compatibility
    Tool: Bash
    Preconditions: Python 3.12+ with traderbot installed
    Steps:
      1. Run `python -c "from traderbot.news.sources import NewsAggregator, DataSourcesConfig; a = NewsAggregator(newsapi_key='test'); print('legacy ok'); b = NewsAggregator(config=DataSourcesConfig(newsapi_key='test')); print('config ok')"`
      2. Assert both "legacy ok" and "config ok" printed
    Expected Result: Both constructor patterns work
    Failure Indicators: TypeError or AttributeError
    Evidence: .sisyphus/evidence/task-2-datasources-config.txt

  Scenario: SOURCE_CATEGORY_COVERAGE covers all new sources
    Tool: Bash
    Preconditions: Python 3.12+ with traderbot installed
    Steps:
      1. Run `python -c "from traderbot.news.sources import SOURCE_CATEGORY_COVERAGE; from traderbot.news.models import NewsSource; new_sources = [NewsSource.OPEN_METEO, NewsSource.COINGECKO, NewsSource.THESPORTSDB, NewsSource.COINCAP, NewsSource.OPENWEATHERMAP, NewsSource.BALLOTPEDIA, NewsSource.FRED, NewsSource.GOOGLE_TRENDS]; print(all(s in SOURCE_CATEGORY_COVERAGE for s in new_sources))"`
      2. Assert True
    Expected Result: All 8 new sources have category coverage entries
    Failure Indicators: False or KeyError
    Evidence: .sisyphus/evidence/task-2-source-coverage.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `feat(news): add DataSourcesConfig and SOURCE_CATEGORY_COVERAGE`
  - Files: `src/traderbot/news/sources.py`

- [x] 3. resolve_*_key Functions for OpenWeatherMap and FRED

  **What to do**:
  - Add `resolve_openweather_key()` to `src/traderbot/profiles/config.py` following the existing 5-step fallback chain: profile keyring → global keyring → global `.env` → environment variable → None
  - Add `resolve_fred_key()` to `src/traderbot/profiles/config.py` following same pattern
  - Both use `AuthManager._env_file_get` for `.env` file lookups (handles both `export KEY=VAL` and `KEY=VAL` formats)
  - Update `profile_auth` CLI command to show both new key sources with correct source indicators
  - Environment variable names: `OPENWEATHER_API_KEY`, `FRED_API_KEY`

  **Must NOT do**:
  - Do NOT add resolve functions for no-key sources (Open-Meteo, CoinGecko, TheSportsDB, CoinCap)
  - Do NOT modify the existing `resolve_newsapi_key` function
  - Do NOT store API keys in workspace `.env` — they go in global `~/.traderbot/.env` only

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/traderbot/profiles/config.py:resolve_newsapi_key` (lines ~90-120) — Exact 5-step fallback chain to replicate for both new functions
  - `src/traderbot/profiles/config.py:AuthManager._env_file_get` — `.env` file reader that handles `export` prefix

  **API/Type References**:
  - `src/traderbot/profiles/config.py:ProfileAuthStore` — Keyring storage per-profile (keyring namespace: `traderbot.profiles.<name>.<service>`)

  **WHY Each Reference Matters**:
  - `resolve_newsapi_key` is the exact template — same structure, same fallback steps, same logging
  - `_env_file_get` handles the `export KEY=VAL` format correctly
  - `ProfileAuthStore` shows how to store/retrieve keys per-profile

  **Acceptance Criteria**:
  - [ ] `resolve_openweather_key()` follows 5-step fallback chain
  - [ ] `resolve_fred_key()` follows 5-step fallback chain
  - [ ] Both return `None` when no key found (not raising)
  - [ ] `profile_auth` command shows both new services

  **QA Scenarios**:

  ```
  Scenario: resolve_*_key returns None when no keys configured
    Tool: Bash
    Preconditions: No OPENWEATHER_API_KEY or FRED_API_KEY in env or .env
    Steps:
      1. Run `python -c "from traderbot.profiles.config import resolve_openweather_key, resolve_fred_key; print(resolve_openweather_key(), resolve_fred_key())"`
      2. Assert output is `None None`
    Expected Result: Both return None gracefully
    Failure Indicators: Exception raised or non-None value
    Evidence: .sisyphus/evidence/task-3-resolve-keys.txt

  Scenario: resolve_*_key finds key from environment variable
    Tool: Bash
    Preconditions: OPENWEATHER_API_KEY or FRED_API_KEY set in env
    Steps:
      1. Run `OPENWEATHER_API_KEY=test123 python -c "from traderbot.profiles.config import resolve_openweather_key; print(resolve_openweather_key())"`
      2. Assert output is `test123`
    Expected Result: Key resolved from environment variable
    Failure Indicators: None returned or exception
    Evidence: .sisyphus/evidence/task-3-resolve-env.txt
  ```

  **Commit**: YES
  - Message: `feat(profiles): add resolve_openweather_key and resolve_fred_key`
  - Files: `src/traderbot/profiles/config.py`

- [x] 4. Open-Meteo Weather Source

  **What to do**:
  - Add `_fetch_open_meteo(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `httpx.AsyncClient` to call `https://api.open-meteo.com/v1/forecast`
  - For WEATHER category: resolve city → lat/lon via geocoding API `https://geocoding-api.open-meteo.com/v1/search?name={city}`, then fetch forecast
  - Cities to fetch: map Kalshi weather market tickers (KXHIGHNY, KXHIGHPHIL, KXHIGHTPHX, KXHIGHTMIN, KXHIGHTSEA, etc.) to city lat/lon pairs. Start with a predefined `KALSHI_WEATHER_CITIES` dict mapping ticker prefixes to {name, lat, lon}
  - Request params: `latitude`, `longitude`, `current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m`, `daily=temperature_2m_max,temperature_2m_min,precipitation_sum`, `temperature_unit=fahrenheit`, `timezone=America/New_York`
  - Parse response into `DataPoint` objects: `title` = "NYC Forecast: High 72°F, Low 58°F", `data` = {temp_high_f, temp_low_f, humidity_pct, precipitation_mm, weather_code}, `timestamp` from response
  - WMO weather codes: map numeric codes to descriptions (0=Clear, 1-3=Partly cloudy, 45-48=Fog, 51-55=Drizzle, 61-65=Rain, 71-75=Snow, 80-82=Showers, 95-99=Thunderstorm)
  - Error handling: follow existing pattern — log + return empty list on failure
  - No rate limit enforcement needed (10K/day is generous)
  - No API key required

  **Must NOT do**:
  - Do NOT add `openmeteo-requests` as a dependency — use plain httpx
  - Do NOT make real API calls in unit tests (mock httpx responses)
  - Do NOT use Celsius internally (Kalshi markets resolve on Fahrenheit)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5-8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_newsapi` (lines 149-248) — Fetch method pattern: httpx call, retry loop, parse response, build items, return list. Follow this exact structure.
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_reddit` — RSS fetch pattern with feedparser (simpler, no retry). Use as simpler reference if applicable.

  **API/Type References**:
  - `src/traderbot/news/models.py:DataPoint` — Created in Task 1; the output model for structured weather data
  - `src/traderbot/news/sources.py:SOURCE_CATEGORY_COVERAGE` — Created in Task 2; confirms OPEN_METEO covers [WEATHER]

  **External References**:
  - Open-Meteo Forecast API: `https://open-meteo.com/en/docs` — Exact endpoint, params, response schema
  - Open-Meteo Geocoding API: `https://open-meteo.com/en/docs/geocoding-api` — City name → lat/lon
  - WMO Weather Codes: `https://open-meteo.com/en/docs/docs#weathervariables` — Numeric code → description mapping

  **WHY Each Reference Matters**:
  - `_fetch_newsapi` is the canonical fetch method pattern — all new sources must follow it
  - `DataPoint` defines the output format — weather data goes in `data` dict, not `NewsItem.body`
  - Open-Meteo docs provide exact field names (`temperature_2m`, `weather_code`) and units

  **Acceptance Criteria**:
  - [ ] `_fetch_open_meteo` method implemented
  - [ ] Returns `list[DataPoint]` with weather data
  - [ ] Works without API key
  - [ ] Maps Kalshi ticker prefixes to city lat/lon
  - [ ] WMO weather codes mapped to human-readable descriptions

  **QA Scenarios**:

  ```
  Scenario: Open-Meteo returns weather data for NYC
    Tool: Bash
    Preconditions: Internet access, no API key needed
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://api.open-meteo.com/v1/forecast', params={'latitude':40.71,'longitude':-74.01,'current':'temperature_2m,weather_code','temperature_unit':'fahrenheit','timezone':'America/New_York'}); print(r.status_code, r.json().get('current',{}).get('temperature_2m')); asyncio.run(t())"`
      2. Assert status 200 and temperature value present
    Expected Result: 200 and numeric temperature in Fahrenheit
    Failure Indicators: Non-200 status, missing temperature_2m field
    Evidence: .sisyphus/evidence/task-4-open-meteo-live.txt

  Scenario: Geocoding resolves "New York" to lat/lon
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://geocoding-api.open-meteo.com/v1/search', params={'name':'New York','count':1}); d=r.json(); print(d['results'][0]['latitude'], d['results'][0]['longitude']); asyncio.run(t())"`
      2. Assert lat ~40.7, lon ~-74.0
    Expected Result: Coordinates for New York City
    Failure Indicators: No results key or empty results
    Evidence: .sisyphus/evidence/task-4-geocoding.txt
  ```

  **Commit**: YES (groups with Task 5-8)
  - Message: `feat(news): add Open-Meteo weather source`
  - Files: `src/traderbot/news/sources.py`

- [x] 5. CoinGecko Crypto Source

  **What to do**:
  - Add `_fetch_coingecko(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `httpx.AsyncClient` to call `https://api.coingecko.com/api/v3`
  - For CRYPTO category: fetch `/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1&sparkline=false`
  - For MENTIONS category: fetch `/search/trending` to get trending coins
  - Also fetch `/simple/price?ids=bitcoin,ethereum&vs_currencies=usd` for quick price check
  - Parse response into `DataPoint` objects: `title` = "BTC: $67,234 (+2.3% 24h)", `data` = {price_cents, market_cap_cents, volume_24h_cents, change_24h_pct}, `timestamp` from `last_updated`
  - All price values converted to `int` cents: `int(float(price) * 100)`
  - Error handling: follow existing pattern — 429 retry with backoff, log + return empty
  - No API key required for basic tier (30 req/min demo limit)
  - Respect `x-ratelimit-remaining` header if present

  **Must NOT do**:
  - Do NOT add `pycoingecko` as a required dependency — use plain httpx
  - Do NOT use `float` for price_cents — always `int(round(float(price_usd) * 100))`
  - Do NOT make real API calls in unit tests

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 6-8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_newsapi` — Fetch method pattern to follow

  **API/Type References**:
  - `src/traderbot/news/models.py:DataPoint` — Output model for structured price data

  **External References**:
  - CoinGecko API: `https://www.coingecko.com/en/api/documentation` — Endpoints, params, response schema
  - CoinGecko `/coins/markets` response fields: `id`, `symbol`, `name`, `current_price`, `market_cap`, `total_volume`, `price_change_percentage_24h`, `last_updated`

  **WHY Each Reference Matters**:
  - CoinGecko docs provide exact field names and types for parsing
  - `_fetch_newsapi` shows retry/backoff pattern for rate-limited APIs

  **Acceptance Criteria**:
  - [ ] `_fetch_coingecko` method implemented
  - [ ] Returns `list[DataPoint]` with crypto price data
  - [ ] All prices in `int` cents
  - [ ] Works without API key
  - [ ] Handles 429 rate limiting gracefully

  **QA Scenarios**:

  ```
  Scenario: CoinGecko returns market data for top coins
    Tool: Bash
    Preconditions: Internet access, no API key needed
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://api.coingecko.com/api/v3/coins/markets', params={'vs_currency':'usd','order':'market_cap_desc','per_page':5,'page':1,'sparkline':'false'}); d=r.json(); print(r.status_code, len(d), d[0]['symbol'], int(round(float(d[0]['current_price'])*100))); asyncio.run(t())"`
      2. Assert 200, 5 items, symbol and price_cents present
    Expected Result: List of 5 coins with symbols and prices in cents
    Failure Indicators: Non-200, empty list, missing current_price
    Evidence: .sisyphus/evidence/task-5-coingecko-live.txt

  Scenario: CoinGecko trending endpoint
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://api.coingecko.com/api/v3/search/trending'); d=r.json(); print(r.status_code, len(d.get('coins',[]))); asyncio.run(t())"`
      2. Assert 200 and coins array present
    Expected Result: Trending coins list
    Failure Indicators: Non-200 or missing coins field
    Evidence: .sisyphus/evidence/task-5-coingecko-trending.txt
  ```

  **Commit**: YES (groups with Tasks 4, 6-8)
  - Message: `feat(news): add CoinGecko crypto source`
  - Files: `src/traderbot/news/sources.py`

- [x] 6. TheSportsDB Sports Source

  **What to do**:
  - Add `_fetch_thesportsdb(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `httpx.AsyncClient` to call `https://www.thesportsdb.com/api/v1/json/3/`
  - Free API key is `3` (confirmed from official docs)
  - For SPORTS category: fetch today's events via `eventsday.php?d={YYYY-MM-DD}&s={sport}` for major sports (Soccer, Basketball, Baseball, American Football, Ice Hockey)
  - Parse response into `DataPoint` objects: `title` = "Lakers vs Celtics — 7:30pm ET", `data` = {home_team, away_team, date_event, str_league, home_score, away_score, str_thumb}, `timestamp` from `dateEvent`
  - Response fields: `idEvent`, `strEvent`, `strHomeTeam`, `strAwayTeam`, `intHomeScore`, `intAwayScore`, `dateEvent`, `strLeague`, `strThumb`
  - Rate limit: 30 req/min — add client-side budget enforcement
  - No API key configuration needed (hardcoded free key `3`)

  **Must NOT do**:
  - Do NOT add Python SDK dependency — use plain httpx
  - Do NOT use premium V2 endpoints (free tier only)
  - Do NOT call search endpoints (heavily restricted on free tier)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4-5, 7-8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_newsapi` — Fetch method pattern

  **External References**:
  - TheSportsDB API: `https://www.thesportsdb.com/documentation` — Endpoints, free key, rate limits
  - `eventsday.php` endpoint: params `d` (YYYY-MM-DD), optional `s` (sport name), `l` (league ID)

  **WHY Each Reference Matters**:
  - TheSportsDB docs confirm free key is `3` (not `123` which is the old key)
  - `eventsday.php` is the primary free-tier endpoint for daily schedules

  **Acceptance Criteria**:
  - [ ] `_fetch_thesportsdb` method implemented
  - [ ] Returns `list[DataPoint]` with sports event data
  - [ ] Works with hardcoded free key `3`
  - [ ] Client-side 30 req/min rate limit enforced

  **QA Scenarios**:

  ```
  Scenario: TheSportsDB returns today's events
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `python -c "import asyncio, httpx, datetime; d=datetime.date.today().isoformat(); async def t(): r = await httpx.AsyncClient().get(f'https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={d}'); j=r.json(); evts=j.get('events') or []; print(r.status_code, len(evts)); asyncio.run(t())"`
      2. Assert 200 status (events count varies by day)
    Expected Result: HTTP 200, events array (may be empty on some days)
    Failure Indicators: Non-200 status
    Evidence: .sisyphus/evidence/task-6-thesportsdb-live.txt

  Scenario: TheSportsDB handles null events gracefully
    Tool: Bash
    Preconditions: Internet access, date with no events
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2099-12-31'); j=r.json(); print(j.get('events')); asyncio.run(t())"`
      2. Assert None or empty list handled without error
    Expected Result: Graceful handling of null/empty events
    Failure Indicators: TypeError or crash on None
    Evidence: .sisyphus/evidence/task-6-thesportsdb-empty.txt
  ```

  **Commit**: YES (groups with Tasks 4-5, 7-8)
  - Message: `feat(news): add TheSportsDB sports source`
  - Files: `src/traderbot/news/sources.py`

- [x] 7. CoinCap Crypto Source

  **What to do**:
  - Add `_fetch_coincap(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `httpx.AsyncClient` to call `https://api.coincap.io/v2/`
  - For CRYPTO category: fetch `/assets?limit={limit}` for top assets
  - Also fetch `/assets/{id}/history?interval=d1` for 24h price history if individual asset requested
  - Parse response into `DataPoint` objects: `title` = "BTC: $67,234 (rank #1)", `data` = {price_cents, market_cap_cents, volume_24h_cents, change_24h_pct, rank}, `timestamp` from response
  - All price values in `int` cents: `int(round(float(price_usd) * 100))`
  - Response fields for `/assets`: `id`, `rank`, `symbol`, `name`, `priceUsd`, `marketCapUsd`, `volumeUsd24Hr`, `changePercent24Hr`, `vwap24Hr`
  - Optional API key via `Authorization: Bearer {key}` header — but free tier works without
  - "Fair use" rate limit — add budget of 200 req/min as safety margin

  **Must NOT do**:
  - Do NOT add WebSocket connections (future work)
  - Do NOT use `float` for monetary values — always `int` cents

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4-6, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **External References**:
  - CoinCap API v2: `https://coincap.io/api` — Endpoints, response schema, auth pattern

  **Acceptance Criteria**:
  - [ ] `_fetch_coincap` method implemented
  - [ ] Returns `list[DataPoint]` with crypto data
  - [ ] Works without API key
  - [ ] All prices in `int` cents

  **QA Scenarios**:

  ```
  Scenario: CoinCap returns top crypto assets
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `python -c "import asyncio, httpx; async def t(): r = await httpx.AsyncClient().get('https://api.coincap.io/v2/assets', params={'limit':5}); d=r.json(); print(r.status_code, len(d.get('data',[])), d['data'][0]['symbol']); asyncio.run(t())"`
      2. Assert 200, 5 items, BTC symbol present
    Expected Result: Top 5 crypto assets with symbol and price
    Failure Indicators: Non-200, empty data array
    Evidence: .sisyphus/evidence/task-7-coincap-live.txt
  ```

  **Commit**: YES (groups with Tasks 4-6, 8)
  - Message: `feat(news): add CoinCap crypto source`
  - Files: `src/traderbot/news/sources.py`

- [x] 8. Ballotpedia Elections RSS Source

  **What to do**:
  - Add `_fetch_ballotpedia(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `feedparser` (already a dependency for Reddit RSS) to parse Ballotpedia RSS feeds
  - RSS feed URLs: `https://ballotpedia.org/wiki/RSS_Feeds` — use main elections feed and state-specific feeds
  - Primary feeds: `https://ballotpedia.org/feed/`, `https://ballotpedia.org/wiki/RSS_Feed_-_Elections`
  - Parse feed entries into `DataPoint` objects: `title` = entry.title, `data` = {summary, link, tags}, `timestamp` from entry.published_parsed
  - Use existing `feedparser` pattern from `_fetch_reddit` — same parsing, same error handling
  - No API key required, no rate limits documented (follow polite crawling: cache results for 5 min)

  **Must NOT do**:
  - Do NOT add new HTTP client dependencies — feedparser already available
  - Do NOT scrape Ballotpedia HTML — RSS feeds only
  - Do NOT assume a public API exists

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4-7)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_reddit` — RSS fetch pattern with feedparser, entry parsing, md5 hashing for IDs. Follow this exact structure.

  **External References**:
  - Ballotpedia RSS: `https://ballotpedia.org/wiki/RSS_Feeds` — List of available RSS feeds

  **WHY Each Reference Matters**:
  - `_fetch_reddit` is the canonical RSS parsing pattern — Ballotpedia uses same feedparser approach

  **Acceptance Criteria**:
  - [ ] `_fetch_ballotpedia` method implemented
  - [ ] Returns `list[DataPoint]` with election data
  - [ ] Uses feedparser (existing dependency)
  - [ ] No API key required

  **QA Scenarios**:

  ```
  Scenario: Ballotpedia RSS feed is reachable
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `python -c "import feedparser; f = feedparser.parse('https://ballotpedia.org/feed/'); print(len(f.entries), f.entries[0].title if f.entries else 'empty')"`
      2. Assert non-negative entry count
    Expected Result: RSS entries returned (count varies)
    Failure Indicators: FeedParseError or empty feed
    Evidence: .sisyphus/evidence/task-8-ballotpedia-live.txt
  ```

  **Commit**: YES (groups with Tasks 4-7)
  - Message: `feat(news): add Ballotpedia elections RSS source`
  - Files: `src/traderbot/news/sources.py`

- [x] 9. OpenWeatherMap Weather Source

  **What to do**:
  - Add `_fetch_openweathermap(self, category_filter, limit)` method to `NewsAggregator`
  - Requires API key — resolved via `resolve_openweather_key()` (from Task 3)
  - Uses `httpx.AsyncClient` to call `https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=imperial`
  - For WEATHER category: fetch current weather for same `KALSHI_WEATHER_CITIES` dict used by Open-Meteo
  - Current weather response fields: `main.temp`, `main.temp_min`, `main.temp_max`, `main.humidity`, `wind.speed`, `weather[0].description`, `weather[0].id`
  - Also fetch 5-day forecast: `https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={key}&units=imperial`
  - Parse response into `DataPoint` objects: `title` = "NYC: 72°F, Partly Cloudy, Wind 8mph", `data` = {temp_f, temp_min_f, temp_max_f, humidity_pct, wind_mph, weather_code, description}
  - Enforce daily budget: 1,000 calls/day on free tier. Add `OWM_DAILY_BUDGET` = 900 (leave buffer)
  - Key missing → log warning + return empty (don't attempt API call)

  **Must NOT do**:
  - Do NOT call OpenWeatherMap without API key
  - Do NOT exceed 1,000 calls/day free tier limit
  - Do NOT add `pyowm` as dependency — use plain httpx

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 10-11)
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_newsapi` — Fetch with API key, budget enforcement, retry pattern
  - `src/traderbot/news/sources.py:NewsAggregator._check_daily_budget` — Budget tracking pattern

  **API/Type References**:
  - `src/traderbot/profiles/config.py:resolve_openweather_key` — Created in Task 3; key resolution chain

  **External References**:
  - OpenWeatherMap API: `https://openweathermap.org/api` — Endpoints, pricing, free tier limits
  - Current weather: `https://openweathermap.org/current` — Exact response schema
  - 5-day forecast: `https://openweathermap.org/forecast5` — Exact response schema

  **Acceptance Criteria**:
  - [ ] `_fetch_openweathermap` method implemented
  - [ ] Skips fetch if no API key (logs warning)
  - [ ] Enforces 900 calls/day budget
  - [ ] Returns `list[DataPoint]` with weather data in Fahrenheit
  - [ ] All temp values as `int` (Fahrenheit, no decimals)

  **QA Scenarios**:

  ```
  Scenario: OpenWeatherMap with valid API key
    Tool: Bash
    Preconditions: OPENWEATHER_API_KEY in env or .env
    Steps:
      1. Run `traderbot news --source openweathermap --category weather --limit 1 --json`
      2. Assert JSON output contains temperature data
    Expected Result: DataPoint with weather data
    Failure Indicators: Empty array or "API key not set" error
    Evidence: .sisyphus/evidence/task-9-owm-live.txt

  Scenario: OpenWeatherMap without API key
    Tool: Bash
    Preconditions: No OPENWEATHER_API_KEY configured
    Steps:
      1. Run `traderbot news --source openweathermap --category weather --json 2>&1`
      2. Assert output contains "skipping" or "not set" warning
    Expected Result: Graceful skip with warning logged
    Failure Indicators: HTTP 401 error or crash
    Evidence: .sisyphus/evidence/task-9-owm-no-key.txt
  ```

  **Commit**: YES
  - Message: `feat(news): add OpenWeatherMap weather source`
  - Files: `src/traderbot/news/sources.py`

- [x] 10. FRED Economics Source

  **What to do**:
  - Add `_fetch_fred(self, category_filter, limit)` method to `NewsAggregator`
  - Requires API key — resolved via `resolve_fred_key()` (from Task 3)
  - Uses `httpx.AsyncClient` to call `https://api.stlouisfed.org/fred`
  - For ECONOMICS category: fetch latest observations for key series: CPIAUCSL (CPI), UNRATE (Unemployment), FEDFUNDS (Fed Funds Rate), GDP
  - For FINANCIALS category: fetch DFF (Daily Fed Funds), T10Y2Y (10Y-2Y Treasury Spread)
  - Endpoint: `/series/observations?series_id={id}&api_key={key}&file_type=json&sort_order=desc&limit=1`
  - Response fields: `observations[].date`, `observations[].value`
  - Parse into `DataPoint` objects: `title` = "CPI: 314.5 (Apr 2026)", `data` = {series_id, value, date, units}, `timestamp` from observation date
  - Rate limit: 120 req/min with key. Add client-side rate tracking.
  - Key missing → log warning + return empty

  **Must NOT do**:
  - Do NOT call FRED without API key
  - Do NOT add `fredapi` as dependency — use plain httpx
  - Do NOT use `float` for monetary values where applicable

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_newsapi` — Fetch with API key pattern

  **API/Type References**:
  - `src/traderbot/profiles/config.py:resolve_fred_key` — Created in Task 3

  **External References**:
  - FRED API: `https://fred.stlouisfed.org/docs/api/fred/` — Endpoints, params, response schema
  - Series IDs: `https://fred.stlouisfed.org/docs/api/fred/series_observations.html` — observations endpoint
  - Key series: CPIAUCSL (CPI), UNRATE, FEDFUNDS, GDP, DFF, T10Y2Y

  **Acceptance Criteria**:
  - [ ] `_fetch_fred` method implemented
  - [ ] Skips fetch if no API key
  - [ ] Returns `list[DataPoint]` with economic indicator data
  - [ ] Fetches latest observations for 4+ series

  **QA Scenarios**:

  ```
  Scenario: FRED returns latest CPI observation
    Tool: Bash
    Preconditions: FRED_API_KEY in env or .env
    Steps:
      1. Run `python -c "import asyncio, httpx, os; key=os.environ.get('FRED_API_KEY',''); async def t(): r = await httpx.AsyncClient().get('https://api.stlouisfed.org/fred/series/observations', params={'series_id':'CPIAUCSL','api_key':key,'file_type':'json','sort_order':'desc','limit':1}); d=r.json(); print(r.status_code, d.get('observations',[{}])[0].get('date')); asyncio.run(t())"` 2>/dev/null
      2. Assert 200 and date value present
    Expected Result: Latest CPI date and value
    Failure Indicators: Non-200 or missing observations
    Evidence: .sisyphus/evidence/task-10-fred-live.txt
  ```

  **Commit**: YES
  - Message: `feat(news): add FRED economics source`
  - Files: `src/traderbot/news/sources.py`

- [x] 11. Google Trends Mentions Source

  **What to do**:
  - Add `_fetch_google_trends(self, category_filter, limit)` method to `NewsAggregator`
  - Uses `pytrends` Python package (unofficial, scraping-based) as optional dependency
  - For MENTIONS category: call `pytrends.TrendingRequests().top_charts(date, geo='US')` or `pytrends.daily_search_requests()` for daily trending searches
  - For SOCIAL category: call `InterestOverTime` for specific queries
  - Wrap in try/except with aggressive 10s timeout — Google aggressively blocks scraping
  - If `pytrends` import fails → log info + return empty (not an error)
  - If Google blocks → log warning + return empty (expected behavior)
  - Parse into `DataPoint` objects: `title` = "Trending: {topic}", `data` = {topic, traffic, related_queries}, `timestamp` from pytrends response
  - This is explicitly best-effort — agents should use NewsAPI/Reddit as primary sources for MENTIONS
  - Add `pytrends` to `[news-extras]` optional dependency group in `pyproject.toml`, NOT as required dep

  **Must NOT do**:
  - Do NOT add `pytrends` as a required dependency — it's optional and fragile
  - Do NOT treat Google Trends as a reliable source — it's best-effort only
  - Do NOT add SerpAPI paid integration
  - Do NOT retry on scraping failures (Google blocks are permanent until cooldown)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9-10)
  - **Parallel Group**: Wave 3
  - **Blocks**: Tasks 12, 14, 15
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `src/traderbot/news/sources.py:NewsAggregator._fetch_twitter` — Stub pattern for optional sources; Google Trends follows this graceful-degradation approach

  **External References**:
  - pytrends: `https://github.com/GeneralMills/pytrends` — Unofficial Google Trends scraper
  - Note: NOT on Context7 — it's a GitHub-only package with no official docs

  **Acceptance Criteria**:
  - [ ] `_fetch_google_trends` method implemented
  - [ ] Returns empty if `pytrends` not installed (no crash)
  - [ ] Returns empty if Google blocks (no crash)
  - [ ] 10s timeout enforced on all requests
  - [ ] `pytrends` in `[news-extras]` optional dep group

  **QA Scenarios**:

  ```
  Scenario: Google Trends graceful skip when pytrends not installed
    Tool: Bash
    Preconditions: pytrends NOT installed
    Steps:
      1. Run `python -c "from traderbot.news.sources import NewsAggregator; a = NewsAggregator(); import asyncio; r = asyncio.run(a._fetch_google_trends(limit=5)); print(len(r))"`
      2. Assert 0
    Expected Result: Empty list, no crash
    Failure Indicators: ImportError or exception
    Evidence: .sisyphus/evidence/task-11-trends-no-pytrends.txt

  Scenario: Google Trends returns data when pytrends installed
    Tool: Bash
    Preconditions: pytrends installed (`pip install pytrends`)
    Steps:
      1. Run `python -c "from traderbot.news.sources import NewsAggregator; a = NewsAggregator(); import asyncio; r = asyncio.run(a._fetch_google_trends(limit=5)); print(len(r), type(r))"`
      2. Assert list returned (may be empty if Google blocks — that's OK)
    Expected Result: List (0 or more items, no crash)
    Failure Indicators: Unhandled exception or timeout >10s
    Evidence: .sisyphus/evidence/task-11-trends-with-pytrends.txt
  ```

  **Commit**: YES
  - Message: `feat(news): add Google Trends mentions source (best-effort)`
  - Files: `src/traderbot/news/sources.py`, `pyproject.toml`

- [x] 12. CLI Integration + fetch_all Refactor

  **What to do**:
  - Update `traderbot news` CLI command (in `src/traderbot/cli.py`) to support all 11 sources (3 existing + 8 new)
  - Extend `--source` flag to accept: `newsapi`, `reddit`, `open-meteo`, `coingecko`, `thesportsdb`, `coincap`, `openweathermap`, `ballotpedia`, `fred`, `google-trends` (twitter remains stub)
  - Refactor `fetch_all` to use `asyncio.gather` for parallel fetching across sources instead of sequential loop
  - Route sources based on `SOURCE_CATEGORY_COVERAGE` — only call sources that cover the requested category
  - Add `--source all` flag that fetches from ALL sources covering the category
  - Return both `NewsItem` and `DataPoint` objects — CLI outputs both, differentiated by output format
  - JSON output: DataPoint objects have `"type": "data_point"` field, NewsItem objects have `"type": "news_item"`
  - Human-readable output: DataPoints shown as structured summary, NewsItems shown as headlines

  **Must NOT do**:
  - Do NOT break existing `traderbot news` behavior (backward compatible)
  - Do NOT add `from __future__ import annotations` in cli.py

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after all sources implemented)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 4-11

  **References**:

  **Pattern References**:
  - `src/traderbot/cli.py:news` command — Current CLI command to extend

  **API/Type References**:
  - `src/traderbot/news/sources.py:SOURCE_CATEGORY_COVERAGE` — Source routing logic
  - `src/traderbot/news/models.py:DataPoint` — New output type for CLI rendering

  **Acceptance Criteria**:
  - [ ] `--source` flag accepts all 11 source names
  - [ ] `fetch_all` uses `asyncio.gather` for parallel fetches
  - [ ] Sources routed by `SOURCE_CATEGORY_COVERAGE`
  - [ ] Both `NewsItem` and `DataPoint` rendered in CLI output
  - [ ] JSON output includes `"type"` field for differentiation

  **QA Scenarios**:

  ```
  Scenario: weather category fetches multiple sources
    Tool: Bash
    Preconditions: Internet access, no API keys needed for Open-Meteo
    Steps:
      1. Run `traderbot news --category weather --limit 5 --json`
      2. Assert output contains both Open-Meteo DataPoint objects and (possibly) NewsAPI items
    Expected Result: Mixed output with type differentiation
    Failure Indicators: Only one source or missing type field
    Evidence: .sisyphus/evidence/task-12-cli-multi-source.txt

  Scenario: explicit source selection
    Tool: Bash
    Preconditions: Internet access
    Steps:
      1. Run `traderbot news --source open-meteo --category weather --limit 3 --json`
      2. Assert output contains only open_meteo DataPoint objects
    Expected Result: Only Open-Meteo data returned
    Failure Indicators: Other sources in output
    Evidence: .sisyphus/evidence/task-12-cli-source-select.txt
  ```

  **Commit**: YES
  - Message: `feat(news): integrate all new sources into CLI with parallel fetch`
  - Files: `src/traderbot/cli.py`, `src/traderbot/news/sources.py`

- [x] 13. Workspace Docs Update — TOOLS.md + AGENTS.md

  **What to do**:
  - Update `.openclaw/workspace/TOOLS.md`: Add table of all 11 sources with source name, CLI flag value, categories covered, API key requirement, and free tier limits
  - Update `.openclaw/workspace/AGENTS.md`: Add section on multi-source data fetching — agents should compare perspectives across sources. Note that structured data sources (Open-Meteo, CoinGecko, FRED) provide numeric data, not news articles. Note that Google Trends is best-effort and may return empty.
  - Add instructions for setting up API keys: `traderbot profile auth` shows all key sources, keys for OpenWeatherMap and FRED can be added via `traderbot profile update` or via `~/.traderbot/.env`
  - Update the fenced `TRADERBOT_TOOLS` block in TOOLS.md and `TRADERBOT_RULES` block in AGENTS.md

  **Must NOT do**:
  - Do NOT modify content outside fenced marker blocks
  - Do NOT add API key plaintext values to workspace docs
  - Do NOT delete existing workspace content outside injection points

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after Task 12)
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:

  **Pattern References**:
  - `.openclaw/workspace/TOOLS.md:TRADERBOT_TOOLS_START/END` — Fenced merge injection point for tools docs
  - `.openclaw/workspace/AGENTS.md:TRADERBOT_RULES_START/END` — Fenced merge injection point for agent rules

  **Acceptance Criteria**:
  - [ ] TOOLS.md lists all 11 sources with correct CLI flag values
  - [ ] AGENTS.md explains multi-source strategy
  - [ ] API key setup instructions included
  - [ ] Content only modified within fenced blocks

  **QA Scenarios**:

  ```
  Scenario: TOOLS.md contains all source names
    Tool: Bash
    Steps:
      1. Run `grep -c 'open-meteo\|coingecko\|thesportsdb\|coincap\|openweathermap\|ballotpedia\|fred\|google-trends' .openclaw/workspace/TOOLS.md`
      2. Assert count >= 8
    Expected Result: All 8 new sources mentioned in TOOLS.md
    Failure Indicators: Count < 8
    Evidence: .sisyphus/evidence/task-13-tools-md.txt
  ```

  **Commit**: YES
  - Message: `docs(workspace): update TOOLS.md and AGENTS.md with new data sources`
  - Files: `.openclaw/workspace/TOOLS.md`, `.openclaw/workspace/AGENTS.md`

- [x] 14. Live Integration Tests

  **What to do**:
  - Add `tests/news/test_live_sources.py` with `@pytest.mark.live` tests for each of the 8 new sources
  - Each test makes real API calls and asserts response structure
  - Tests for no-key sources (5): Open-Meteo, CoinGecko, TheSportsDB, CoinCap, Ballotpedia — skip if network unavailable
  - Tests for key-required sources (2): OpenWeatherMap, FRED — skip if env vars not set
  - Test for Google Trends — skip if `pytrends` not installed or Google blocks
  - Each test verifies: correct return type (DataPoint), non-empty data dict, valid timestamp, correct source enum
  - Add `conftest.py` fixtures for live API client setup
  - Module-level `pytestmark = pytest.mark.live`

  **Must NOT do**:
  - Do NOT make real API calls in non-live unit tests
  - Do NOT require API keys for live tests — skip gracefully if missing
  - Do NOT commit API keys in test files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 15)
  - **Parallel Group**: Wave 5
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 4-11

  **References**:

  **Pattern References**:
  - `tests/test_kalshi_live.py` — Existing live test pattern with `pytestmark = pytest.mark.live`, skip decorators, real API calls

  **Acceptance Criteria**:
  - [ ] 8+ live test functions (one per source)
  - [ ] Each skips gracefully when prerequisites missing
  - [ ] `pytest tests/news/ -m live -v` runs without error (tests skip when keys unavailable)
  - [ ] `pytest tests/news/test_live_sources.py -m live --co` lists all tests

  **QA Scenarios**:

  ```
  Scenario: Live test discovery
    Tool: Bash
    Steps:
      1. Run `pytest tests/news/test_live_sources.py -m live --co -q`
      2. Assert 8+ tests listed
    Expected Result: All live tests discoverable
    Failure Indicators: 0 tests or collection error
    Evidence: .sisyphus/evidence/task-14-live-discovery.txt
  ```

  **Commit**: YES
  - Message: `test(news): add live integration tests for all 8 new sources`
  - Files: `tests/news/test_live_sources.py`, `tests/news/conftest.py`

- [x] 15. Unit Tests with Mocks

  **What to do**:
  - Update `tests/news/test_sources.py` (or create if not exists) with unit tests for all 8 new sources using mocked httpx responses
  - Each test: mock the source's API response JSON, call fetch method, assert correct `DataPoint` construction
  - Test edge cases: null/empty responses, malformed JSON, rate limit headers, timeout, connection error
  - Test `SOURCE_CATEGORY_COVERAGE` routing: calling with wrong category returns empty from that source
  - Test `DataSourcesConfig` backward compatibility
  - Test `resolve_openweather_key` and `resolve_fred_key` with mocked env/keyring
  - No real API calls — all mocked via `httpx.MockTransport` or `respx`

  **Must NOT do**:
  - Do NOT make real API calls in unit tests
  - Do NOT use `MagicMock` for httpx when `respx` or `MockTransport` is available

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 14)
  - **Parallel Group**: Wave 5
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 4-11

  **References**:

  **Pattern References**:
  - `tests/news/` — Existing test patterns for the news module

  **Acceptance Criteria**:
  - [ ] 8+ unit test functions (one per source)
  - [ ] Each uses mocked responses, no real API calls
  - [ ] Edge cases tested (empty, error, rate limit)
  - [ ] `pytest tests/news/ -v` passes all tests

  **QA Scenarios**:

  ```
  Scenario: All unit tests pass
    Tool: Bash
    Steps:
      1. Run `pytest tests/news/ -v --tb=short`
      2. Assert all pass, 0 failures
    Expected Result: All tests green
    Failure Indicators: Any failure
    Evidence: .sisyphus/evidence/task-15-unit-tests.txt
  ```

  **Commit**: YES
  - Message: `test(news): add unit tests with mocks for all 8 new sources`
  - Files: `tests/news/test_sources.py`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present results to user for explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check` + `pytest`. Review all changed files for: `as any`, `# type: ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop. Verify all monetary values are `int` cents.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-source integration (fetch_all with multiple sources). Test edge cases: missing keys, rate limits, empty results. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(news): add DataPoint model and DataSourcesConfig` - models.py, sources.py, config.py
- **Wave 2**: `feat(news): add Open-Meteo, CoinGecko, TheSportsDB, CoinCap, Ballotpedia sources` - sources.py
- **Wave 3**: `feat(news): add OpenWeatherMap, FRED, Google Trends sources` - sources.py, config.py
- **Wave 4**: `feat(news): integrate all new sources into CLI and docs` - cli.py, TOOLS.md, AGENTS.md
- **Wave 5**: `test(news): add live and mock tests for all new sources` - tests/news/

---

## Success Criteria

### Verification Commands
```bash
pytest tests/news/ -v                    # All unit tests pass
pytest tests/news/ -m live -v            # Live tests pass (with API keys)
traderbot news --source open-meteo --category weather --limit 5 --json  # Returns DataPoint objects
traderbot news --source coingecko --category crypto --limit 5 --json   # Returns DataPoint objects
ruff check src/traderbot/news/           # Zero lint errors
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (unit + live)
- [ ] All 8 sources return data with real API keys
- [ ] All 8 sources degrade gracefully when unavailable