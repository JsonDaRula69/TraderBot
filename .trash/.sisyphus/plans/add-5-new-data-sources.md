# Add 5 New Data Sources — Weather.gov, Federal Register, SEC EDGAR, Alpha Vantage, PubMed

## TL;DR

> **Quick Summary**: Add 5 new data sources to achieve ≥2 dedicated sources per market category. All 5 APIs verified with live direct API calls (curl/httpx). Three are free with no key required (weather.gov, Federal Register, SEC EDGAR). Alpha Vantage requires a free API key. PubMed is free with rate limits. CoinCap and Ballotpedia were removed (defunct APIs) — no replacements needed since CoinGecko and the new sources cover their categories.
>
> **Deliverables**:
> - 5 new `NewsSource` enum members: `WEATHER_GOV`, `FEDERAL_REGISTER`, `SEC_EDGAR`, `ALPHA_VANTAGE`, `PUBMED`
> - 5 new `resolve_*_key` functions for Alpha Vantage (only new key-required source)
> - `SOURCE_CATEGORY_COVERAGE` updates for all 5 new sources
> - 5 new `_fetch_*` methods in `NewsAggregator`
> - `DataSourcesConfig` updates for Alpha Vantage key
> - CLI `--source` additions for all 5 new sources
> - Installer prompt for Alpha Vantage API key
> - `auth_login` update for Alpha Vantage
> - Unit tests (20+ mock tests) + live integration tests (5 live tests)
> - TOOLS.md + AGENTS.md updates with new source documentation
> - Source ranking/filtering algorithm to avoid token overload
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: T1 (enum+model) → T2 (config+coverage) → T3-T7 (5 fetch methods parallel) → T8 (CLI+routing) → T9 (ranking/filtering) → T10-T11 (tests) → T12 (docs) → F1-F4

---

## Context

### Original Request
User requested: identify replacement sources for CoinCap and Ballotpedia (both defunct), then research more sources so we have at least 2 per category. Overlapping sources between categories is allowed. User emphasized: "ensure you test sources before integrating to avoid wasted effort."

### Research Findings (All Verified with Live API Calls)

| Source | API Endpoint | Free? | Key? | Categories | Live Test Result |
|---|---|---|---|---|---|
| **weather.gov** | `/points/{lat},{lon}` → `/gridpoints/{office}/{gridX},{gridY}/forecast` + `/stations/{stationId}/observations/latest` | ✅ Free | ❌ None (User-Agent req) | WEATHER | ✅ 14 forecast periods, humidity, wind, precip% |
| **Federal Register** | `/api/v1/documents.json?per_page=N&order=newest` | ✅ Free | ❌ None | ELECTIONS, POLITICS | ✅ Returns gov docs (total field is quirky=0, but results present) |
| **SEC EDGAR** | `/api/xbrl/companyfacts/CIK{cik}.json` | ✅ Free | ❌ None (User-Agent+email req) | COMPANIES, FINANCIALS | ✅ Full financial data (assets, revenue, liabilities) |
| **Alpha Vantage** | `/query?function=TOP_GAINERS_LOSERS&apikey={key}` | ⚠️ Free tier (25/day) | ✅ Key required | COMPANIES, FINANCIALS, COMMODITIES | ✅ Market movers, demo key works but rate-limited |
| **PubMed** | `esearch.fcgi?db=pubmed&term={query}` → `efetch.fcgi?retmode=json` | ✅ Free | ❌ None (3 req/s) | HEALTH, SCIENCE_AND_TECHNOLOGY | ✅ 67K results for "influenza", article details with abstracts |

### Category Coverage After Adding 5 Sources

| Category | Before | After | Sources |
|---|---|---|---|
| WEATHER | 3 (Open-Meteo, OpenWeatherMap, NewsAPI/Reddit) | **4** | + **weather.gov** |
| ECONOMICS | 3 (FRED, NewsAPI, Reddit) | 3 | Already ≥2 |
| POLITICS | 2 (NewsAPI, Reddit) | **3** | + **Federal Register** |
| SPORTS | 3 (TheSportsDB, NewsAPI, Reddit) | 3 | Already ≥2 |
| SCIENCE_AND_TECHNOLOGY | 2 (NewsAPI, Reddit) | **3** | + **PubMed** |
| CRYPTO | 3 (CoinGecko, NewsAPI, Reddit) | 3 | Already ≥2 |
| COMMODITIES | 2 (NewsAPI, Reddit) | **3** | + **Alpha Vantage** |
| COMPANIES | 2 (NewsAPI, Reddit) | **4** | + **SEC EDGAR**, **Alpha Vantage** |
| ELECTIONS | 2 (NewsAPI, Reddit) | **3** | + **Federal Register** |
| ENTERTAINMENT | 2 (NewsAPI, Reddit) | 2 | Lowest priority, no good free API found |
| FINANCIALS | 3 (FRED, NewsAPI, Reddit) | **5** | + **SEC EDGAR**, **Alpha Vantage** |
| HEALTH | 2 (NewsAPI, Reddit) | **3** | + **PubMed** |
| SOCIAL | 3 (Google Trends, NewsAPI, Reddit) | 3 | Already ≥2 |
| MENTIONS | 4 (CoinGecko, Google Trends, NewsAPI, Reddit) | 4 | Already ≥2 |

**Result**: After adding 5 sources, all 14 categories have ≥2 dedicated sources except ENTERTAINMENT (2). ENTERTAINMENT remains at NewsAPI + Reddit, which is acceptable since no suitable free entertainment API exists (TMDB requires key, IMDB has no public API).

---

## Design Decisions

### D1: DataPoint vs NewsItem
- weather.gov forecasts → `DataPoint` (structured weather data: temp, humidity, wind, precip%)
- Federal Register → `NewsItem` (government documents are news articles)
- SEC EDGAR → `DataPoint` (financial data: revenue, assets, liabilities in cents)
- Alpha Vantage → `DataPoint` (market movers: gainers/losers, price changes in cents)
- PubMed → `NewsItem` (research articles are news)

### D2: Weather.gov Gridpoint Resolution
- Use `/points/{lat},{lon}` to get gridpoint, then `/gridpoints/{office}/{gridX},{gridY}/forecast` for 14-period forecast
- Use `/stations/{stationId}/observations/latest` for current conditions with humidity
- Kalshi weather markets reference specific cities — maintain a `WEATHER_CITY_COORDS` dict mapping city names to lat/lon pairs
- User-Agent header required: "TraderBot/1.0 (https://github.com/djtech/traderbot)"

### D3: Federal Register API Quirks
- `total` field in response may report 0 even when results are present — ignore `total`, check `results` array length
- Use `publication_date` for `published_at` field
- Category mapping: ELECTIONS (election-related docs), POLITICS (all other docs)

### D4: SEC EDGAR CIK Mapping
- Need a `TICKER_TO_CIK` dict for common companies (AAPL→0000320193, etc.)
- Start with top 50 companies by market cap
- Fallback: use SEC's `company_tickers.json` endpoint for dynamic lookup (cache result)
- User-Agent header required: "TraderBot/1.0 (contact@traderbot.dev)"

### D5: Alpha Vantage Rate Limits
- Free tier: 25 requests/day, 5 requests/minute
- Demo key heavily rate-limited — store real key via resolve_alpha_vantage_key()
- `SOURCE_REQUIRES_KEY` must include ALPHA_VANTAGE
- DataSourcesConfig needs `alpha_vantage_api_key` field
- Installer needs Alpha Vantage key prompt

### D6: PubMed Rate Limits
- 3 requests/second without API key
- Use `esearch.fcgi` to get PMIDs, then `efetch.fcgi?retmode=json` for details
- Add `asyncio.sleep(0.35)` between requests to stay under rate limit
- No API key needed — no resolve function required

### D7: Source Ranking and Filtering
- Add `SOURCE_PRIORITY` dict to rank sources by data quality within each category
- When `fetch_recent` is called with `max_items` limit, prioritize higher-ranked sources
- Add `SOURCE_DAILY_BUDGET` to cap requests per source per day (prevents token overload)
- Sources that require API keys have lower priority if key is missing (graceful degradation)
- Deduplication: hash on `id` field to prevent same story from multiple sources

---

## TODOs

### Wave 1: Foundation (T1-T2) — Sequential dependency

- [ ] **T1: Add 5 NewsSource enum members + DataPoint field updates**
  Files: `src/traderbot/news/models.py`
  - Add `WEATHER_GOV = "weather_gov"`, `FEDERAL_REGISTER = "federal_register"`, `SEC_EDGAR = "sec_edgar"`, `ALPHA_VANTAGE = "alpha_vantage"`, `PUBMED = "pubmed"` to `NewsSource` enum
  - Add `DataPoint.data` field documentation entries for weather (temp_c, humidity_pct, wind_speed_kmh, precip_pct), financial (revenue_cents, assets_cents, liabilities_cents), and market data (price_cents, change_pct, volume)
  - Update `__all__` if needed
  - **Acceptance**: All 5 new enum members exist, DataPoint model unchanged (field already supports dict payload)

- [ ] **T2: DataSourcesConfig + SOURCE_CATEGORY_COVERAGE + SOURCE_PRIORITY updates**
  Files: `src/traderbot/news/sources.py`, `src/traderbot/profiles/config.py`
  - Add 5 new entries to `SOURCE_CATEGORY_COVERAGE`:
    - `WEATHER_GOV → [WEATHER]`
    - `FEDERAL_REGISTER → [ELECTIONS, POLITICS]`
    - `SEC_EDGAR → [COMPANIES, FINANCIALS]`
    - `ALPHA_VANTAGE → [COMPANIES, FINANCIALS, COMMODITIES]`
    - `PUBMED → [HEALTH, SCIENCE_AND_TECHNOLOGY]`
  - Add `SOURCE_PRIORITY` dict ranking sources (1=highest) per category for deduplication
  - Add `SOURCE_DAILY_BUDGET` dict capping requests per source per day
  - Add `alpha_vantage_api_key: str | None = None` to `DataSourcesConfig`
  - Update `SOURCE_REQUIRES_KEY` to include `ALPHA_VANTAGE`
  - Add `resolve_alpha_vantage_key()` in `config.py` (5-step fallback: profile keyring → global keyring → .env → env var → None)
  - Add `_check_env_permissions()` call in `resolve_alpha_vantage_key()`
  - Update `__init__` to pass `alpha_vantage_api_key` through config
  - **Acceptance**: All 5 sources in coverage map, Alpha Vantage in `SOURCE_REQUIRES_KEY`, `resolve_alpha_vantage_key()` works with 5-step chain

### Wave 2: Fetch Methods (T3-T7) — All 5 can run in parallel

- [ ] **T3: _fetch_weather_gov() method**
  Files: `src/traderbot/news/sources.py`
  - Add `WEATHER_CITY_COORDS` dict mapping Kalshi weather cities to lat/lon pairs (use top 20 US cities from weather markets)
  - Add `_fetch_weather_gov()` async method:
    - Use `/points/{lat},{lon}` to get gridpoint for each city
    - Then `/gridpoints/{office}/{gridX},{gridY}/forecast` for 14-period forecast
    - Then `/stations/{stationId}/observations/latest` for current conditions
    - Return `list[DataPoint]` with `data` containing: temp_c, temp_max_c, temp_min_c, humidity_pct, wind_speed_kmh, precip_pct, short_forecast, detailed_forecast
    - User-Agent: "TraderBot/1.0 (https://github.com/djtech/traderbot)"
    - Cache gridpoint lookups (they're stable per lat/lon)
    - Graceful degradation: skip cities whose gridpoint lookup fails
  - Register in `fetch_recent()` dispatcher under `NewsSource.WEATHER_GOV`
  - **Acceptance**: Method returns DataPoints for weather forecasts, handles errors gracefully, caches gridpoints

- [ ] **T4: _fetch_federal_register() method**
  Files: `src/traderbot/news/sources.py`
  - Add `_fetch_federal_register()` async method:
    - GET `https://www.federalregister.gov/api/v1/documents.json?per_page={limit}&order=newest`
    - Map to `list[NewsItem]` with: id, title=abstract, body=full_text, url, published_at=publication_date
    - Handle quirky `total=0` (ignore it, check `results` array length)
    - Category mapping: ELECTIONS for election-related docs (type=Presidential Document, Election), POLITICS for everything else
    - No API key or User-Agent required
  - Register in `fetch_recent()` dispatcher under `NewsSource.FEDERAL_REGISTER`
  - **Acceptance**: Method returns NewsItems for government documents, handles `total=0` quirk, maps to correct categories

- [ ] **T5: _fetch_sec_edgar() method**
  Files: `src/traderbot/news/sources.py`
  - Add `TICKER_TO_CIK` dict for top 50 companies (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, etc.)
  - Add `_fetch_sec_edgar()` async method:
    - GET `https://www.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
    - User-Agent required: "TraderBot/1.0 (contact@traderbot.dev)"
    - Extract key financial data: revenue, assets, liabilities, net income (all in cents)
    - Return `list[DataPoint]` with `data` containing: revenue_cents, total_assets_cents, total_liabilities_cents, net_income_cents, fiscal_year
    - Cache CIK lookups
  - Register in `fetch_recent()` dispatcher under `NewsSource.SEC_EDGAR`
  - **Acceptance**: Method returns DataPoints for SEC filings, handles User-Agent requirement, caches CIK lookups

- [ ] **T6: _fetch_alpha_vantage() method**
  Files: `src/traderbot/news/sources.py`
  - Add `_fetch_alpha_vantage()` async method:
    - GET `https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={key}`
    - Key resolved via `resolve_alpha_vantage_key()` — if None, skip with warning
    - Return `list[DataPoint]` with `data` containing: ticker, price_cents, change_pct, volume
    - Rate limit: 25/day free tier, add `SOURCE_DAILY_BUDGET` cap
    - Handle error responses: "Information" key (demo key rate limit), 429, 401
    - Also fetch `SYMBOL_SEARCH` and `NEWS_SENTIMENT` endpoints for enriched data
  - Register in `fetch_recent()` dispatcher under `NewsSource.ALPHA_VANTAGE`
  - **Acceptance**: Method returns DataPoints for market movers, handles rate limits gracefully, degrades when no key available

- [ ] **T7: _fetch_pubmed() method**
  Files: `src/traderbot/news/sources.py`
  - Add `_fetch_pubmed()` async method:
    - Use `esearch.fcgi?db=pubmed&term={query}&retmax={limit}` to get PMIDs
    - Then `efetch.fcgi?db=pubmed&id={pmids}&retmode=json` for article details
    - Return `list[NewsItem]` with: id=PMID, title, body=abstract, url=`https://pubmed.ncbi.nlm.nih.gov/{PMID}/`
    - Category mapping: HEALTH for medical terms, SCIENCE_AND_TECHNOLOGY for science terms
    - Rate limit: `asyncio.sleep(0.35)` between requests (3 req/s)
    - No API key required
  - Register in `fetch_recent()` dispatcher under `NewsSource.PUBMED`
  - **Acceptance**: Method returns NewsItems for PubMed articles, respects rate limits, maps to correct categories

### Wave 3: Integration + Ranking (T8-T9) — Depends on T3-T7

- [ ] **T8: CLI integration + fetch_all routing**
  Files: `src/traderbot/cli.py`
  - Add 5 new source names to `--source` help text: `weather_gov`, `federal_register`, `sec_edgar`, `alpha_vantage`, `pubmed`
  - Update `fetch_all` to include 5 new sources in parallel dispatch
  - Ensure Alpha Vantage skips gracefully when no API key configured
  - Ensure SEC EDGAR handles User-Agent requirement
  - **Acceptance**: `traderbot news --source weather_gov` returns DataPoints, all 5 sources work via CLI

- [ ] **T9: Source ranking and filtering algorithm**
  Files: `src/traderbot/news/sources.py`
  - Add `SOURCE_PRIORITY` dict mapping `(source, category)` pairs to priority ranks (1=highest, 10=lowest)
  - Priority heuristics:
    - Dedicated sources rank higher than general sources (e.g., FED > NEWSAPI for ECONOMICS)
    - Free sources rank higher than key-required when both are available
    - DataPoint-providing sources rank higher than NewsItem for structured categories (WEATHER, COMPANIES, FINANCIALS)
  - Add `SOURCE_DAILY_BUDGET` dict capping requests per source per day:
    - weather.gov: 100 (gridpoints cached, only observations refresh)
    - Federal Register: 100
    - SEC EDGAR: 50 (heavy payloads)
    - Alpha Vantage: 25 (free tier limit)
    - PubMed: 200
  - Modify `fetch_recent()` to use priority ordering and budget limits
  - Add deduplication: merge results by `id` hash, keep highest-priority source's version
  - **Acceptance**: When `max_items=10` is specified and 3 sources return 10 items each, only the top 10 by priority are returned, with no duplicates

### Wave 4: Tests + Docs (T10-T12) — All 3 can run in parallel

- [ ] **T10: Unit tests (mock)**
  Files: `tests/news/test_sources.py`
  - Add test class for each source: `TestWeatherGov`, `TestFederalRegister`, `TestSecEdgar`, `TestAlphaVantage`, `TestPubMed`
  - Each class: success test (mock 200 response), error test (mock 404/500), rate limit test (mock 429 for AV)
  - Test priority-based deduplication
  - Test budget capping
  - Test Alpha Vantage graceful degradation when no key
  - Test SEC EDGAR User-Agent header
  - Test weather.gov gridpoint caching
  - Test PubMed rate limiting (sleep between requests)
  - **Acceptance**: All 20+ new tests pass, `pytest tests/news/` clean

- [ ] **T11: Live integration tests**
  Files: `tests/news/test_live_sources.py`
  - Add 5 `@pytest.mark.live` async test functions:
    - `test_live_weather_gov`: real API call, verify DataPoints with temp_c and humidity_pct
    - `test_live_federal_register`: real API call, verify NewsItems from gov docs
    - `test_live_sec_edgar`: real API call for AAPL CIK, verify DataPoints with financial data
    - `test_live_alpha_vantage`: real API call with Test-Keys.txt key, verify DataPoints
    - `test_live_pubmed`: real API call, verify NewsItems with abstracts
  - Each test: assert response is list, assert correct item type, assert category matches
  - **Acceptance**: All 5 live tests pass against real APIs (with real keys from Test-Keys.txt)

- [ ] **T12: Workspace docs + installer + auth updates**
  Files: `.openclaw/workspace/TOOLS.md`, `.openclaw/workspace/AGENTS.md`, `install/traderbot-installer.sh`, `src/traderbot/profiles/config.py`, `src/traderbot/cli.py`
  - TOOLS.md: Add 5 new sources to the source table with API, key requirements, and categories
  - AGENTS.md: Update data source strategy section with new sources and ranking guidance
  - Installer: Add Alpha Vantage API key prompt in `setup_api_credentials()` section
  - `auth_login` CLI: Add `alpha_vantage` to services list
  - `resolve_alpha_vantage_key()`: Already added in T2, verify it's called from `auth_login` and installer writes the key
  - **Acceptance**: `traderbot installer` prompts for Alpha Vantage key, `traderbot auth_login alpha_vantage` stores/retrieves key, TOOLS.md has all 5 new sources documented

### Final Verification Wave

- [ ] **F1: Plan Compliance Audit (oracle)**
  Must Have:
  - [ ] All 5 new NewsSource enum members exist in models.py
  - [ ] All 5 `_fetch_*` methods exist in sources.py
  - [ ] `SOURCE_CATEGORY_COVERAGE` includes all 5 new sources with correct categories
  - [ ] `SOURCE_PRIORITY` ranking dict exists
  - [ ] `SOURCE_DAILY_BUDGET` capping dict exists
  - [ ] `resolve_alpha_vantage_key()` with 5-step fallback chain in config.py
  - [ ] `alpha_vantage_api_key` in `DataSourcesConfig`
  - [ ] `ALPHA_VANTAGE` in `SOURCE_REQUIRES_KEY`
  - [ ] CLI `--source` accepts all 5 new names
  - [ ] Installer prompts for Alpha Vantage API key
  - Must NOT Have:
  - [ ] No CoinCap or Ballotpedia references (they were removed)
  - [ ] No real API calls in unit tests (only in live tests)
  - [ ] No `extra="forbid"` bypass on DataPoint models
  - [ ] No monetary values as float (must be int cents)

- [ ] **F2: Code Quality Review**
  - [ ] `ruff check src/traderbot/news/` passes with zero errors
  - [ ] `ruff format src/traderbot/news/` — no formatting changes
  - [ ] All new functions have one-line docstrings
  - [ ] No `# type: ignore` or `as any` in new code
  - [ ] `_check_env_permissions()` called in `resolve_alpha_vantage_key()`
  - [ ] User-Agent headers set correctly (weather.gov, SEC EDGAR)

- [ ] **F3: Functional Verification**
  - [ ] `traderbot news --source weather_gov` returns DataPoints
  - [ ] `traderbot news --source federal_register` returns NewsItems
  - [ ] `traderbot news --source sec_edgar` returns DataPoints
  - [ ] `traderbot news --source alpha_vantage` returns DataPoints (or warning if no key)
  - [ ] `traderbot news --source pubmed` returns NewsItems
  - [ ] Priority deduplication works: `traderbot news --category weather` returns results prioritized by source ranking
  - [ ] Budget capping works: sources respect daily request limits
  - [ ] All 14 categories have ≥2 dedicated sources (ENTERTAINMENT accepts 2)

- [ ] **F4: Scope Fidelity Check**
  - [ ] Only files in scope were modified: models.py, sources.py, config.py, cli.py, tests/news/, install/traderbot-installer.sh, .openclaw/workspace/TOOLS.md, .openclaw/workspace/AGENTS.md
  - [ ] No changes to risk/, analysis/, db/, simulation/, kalshi/ modules
  - [ ] No changes to existing _fetch methods (Open-Meteo, CoinGecko, etc.)
  - [ ] VERSION bumped correctly

---

## API Reference (Direct curl commands for testing)

### weather.gov
```bash
# Get gridpoint for NYC (40.7128, -74.0060)
curl -s -H "User-Agent: TraderBot/1.0" "https://api.weather.gov/points/40.7128,-74.0060" | python3 -m json.tool | head -20

# Get forecast using gridpoint
curl -s -H "User-Agent: TraderBot/1.0" "https://api.weather.gov/gridpoints/OKX/33,35/forecast" | python3 -m json.tool | head -30

# Get current observations
curl -s -H "User-Agent: TraderBot/1.0" "https://api.weather.gov/stations/KLGA/observations/latest" | python3 -m json.tool | head -20
```

### Federal Register
```bash
curl -s "https://www.federalregister.gov/api/v1/documents.json?per_page=3&order=newest" | python3 -m json.tool | head -40
```

### SEC EDGAR
```bash
# Apple (CIK 0000320193)
curl -s -H "User-Agent: TraderBot/1.0 contact@traderbot.dev" "https://www.sec.gov/api/xbrl/companyfacts/CIK0000320193.json" | python3 -m json.tool | head -30
```

### Alpha Vantage
```bash
# TOP_GAINERS_LOSERS (demo key - heavily rate limited)
curl -s "https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey=demo" | python3 -m json.tool | head -30
```

### PubMed
```bash
# Search for health-related articles
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=influenza+OR+vaccination&retmax=3&retmode=json" | python3 -m json.tool

# Fetch article details
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=38123456&retmode=json" | python3 -m json.tool | head -40
```