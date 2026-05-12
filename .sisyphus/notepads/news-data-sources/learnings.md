# Learnings — News Data Sources

## T15: Update workspace documentation

- **Fenced block markers**: TOOLS.md uses `<!-- TRADERBOT_TOOLS_START -->` / `<!-- TRADERBOT_TOOLS_END -->`. AGENTS.md uses `<!-- TRADERBOT_RULES_START -->` / `<!-- TRADERBOT_RULES_END -->`. All injections must stay within these boundaries.
- **No LSP for .md files** in this workspace — verification is visual/manual for markdown edits.
- **TOOLS.md structure**: Market Analysis → Trading → News → Simulation → Self-Improvement → Profile Management → System → Market Categories → Data Sources (new) → Modules. The Data Sources section was inserted between Market Categories and Modules to keep the logical flow: categories → which sources cover them → which modules implement them.
- **AGENTS.md structure**: The new Multi-Source Data Fetching section was placed after the Market Categories table (which lists all 16 Kalshi categories) and before the closing fence, giving agents context on how to query across sources for those categories.
- **API key env vars**: `OPENWEATHER_API_KEY`, `FRED_API_KEY` — never hardcode values, always use env vars or keyring.
- **11 sources total**: NewsAPI, Twitter (not documented in table per plan specs), Reddit, Open-Meteo, CoinGecko, TheSportsDB, CoinCap, OpenWeatherMap, Ballotpedia, FRED, Google Trends. Plan says 11 sources but lists 10 in the table — the 11th (Twitter) is excluded from the table per the task spec.

## T17: Live integration tests for 8 new data sources

- **pytest mark registration**: `live` marker was not in `pyproject.toml` markers list — added it as `"live: live integration tests (real API calls, skip on missing keys)"`.
- **DataPoint assertions**: `DataPoint.category` is `NewsCategory | None` where `NewsCategory = MarketCategory` (a StrEnum). Assertions like `dp.category == NewsCategory.WEATHER` work because StrEnum compares equal to its string value.
- **Method signatures**: All 8 `_fetch_*` methods have `(self, category_filter: list[NewsCategory] | None = None, limit: int = 20) -> list[DataPoint]`. Tests call with `limit=N` keyword arg.
- **5 no-key sources**: Open-Meteo, CoinGecko, TheSportsDB, CoinCap, Ballotpedia
- **2 key-required sources**: OpenWeatherMap (needs `OPENWEATHER_API_KEY`), FRED (needs `FRED_API_KEY`) — both use `_requires_env()` to skip
- **1 best-effort source**: Google Trends — may return empty list if pytrends not installed or Google blocks
- **uv run pytest**: Must use `uv run pytest` not bare `python3 -m pytest` — project uses uv-managed venv with Python 3.12, system python is 3.14 and doesn't see traderbot package.

## T18: Unit tests for all 8 data sources with mocked httpx responses

- **`httpx.MockTransport` pattern**: Create a handler function `(request: httpx.Request) -> httpx.Response`, wrap in `httpx.MockTransport(handler)`, pass to `httpx.AsyncClient(transport=transport)`. The handler receives every request made through that client so you can match on URL/path or just return the canned response — no need to filter by endpoint unless a fetch method hits multiple URLs.
- **MockTransport vs respx**: The project already depends on `respx>=0.22` (in dev deps), but `httpx.MockTransport` is built into httpx and avoids adding a dependency. Both work fine — MockTransport is simpler for the "one-handler-per-test-case" pattern used here.
- **`DataSourcesConfig` is a plain dataclass, not a Pydantic model**: Despite the project's convention of using Pydantic models everywhere, `DataSourcesConfig` is a `@dataclass`. This matters because you can't pass `extra` fields and it won't validate types strictly. The `__init__` method of `NewsAggregator` does manual extraction (`config.newsapi_key`, etc.) rather than using `.model_dump()`.
- **`resolve_openweather_key` and `resolve_fred_key` are imported from `traderbot.profiles.config`**: These are full functions (not class methods) that accept `profile: TradingProfile | None` and attempt keyring/env resolution. To mock them in `_fetch_openweathermap` / `_fetch_fred`, use `patch("traderbot.news.sources.resolve_openweather_key", return_value=...)` since they're imported at module level into `sources.py`.
- **CoinGecko 429 handling**: The implementation retries up to 2 times with exponential backoff. A test that returns 429 on every `get()` call will hit all 3 attempts (initial + 2 retries) before returning `[]`. Use `asyncio.sleep` mocking if test speed matters — but for these unit tests the total runtime is negligible (~0.5s per retry).
- **Banker's rounding trap**: `round(72.5)` = 72 on Python 3 (banker's rounding rounds .5 to nearest even). The `_fetch_open_meteo` code uses `round()`, so `temp_f` from 72.5 becomes 72, not 73. Documented with inline comment since this is genuinely non-obvious.
- **Google Trends import mock**: Mocking `pytrends` not installed requires `patch.dict(sys.modules, {}, clear=False)` and then popping `pytrends` / `pytrends.request` from `sys.modules`. A simpler `with patch.dict("sys.modules", {"pytrends": None})` was attempted but the module-level `from pytrends.request import TrendReq` happens inside the try/except block, so removing the module from `sys.modules` is the most reliable approach.
- **20 tests total**: 14 async unit tests (8 sources × 1-3 tests each) + 6 sync tests for config/coverage/requires_key. All pass in ~19s with `uv run pytest`.
