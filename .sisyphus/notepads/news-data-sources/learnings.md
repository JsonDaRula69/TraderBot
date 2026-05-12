- Added DataSourcesConfig dataclass to centralize source API keys/settings.
- SOURCE_CATEGORY_COVERAGE maps all 11 sources to their NewsCategory coverage.
- SOURCE_REQUIRES_KEY frozenset flags key-requiring sources.
- NewsAggregator.__init__ accepts config while keeping legacy params; config takes precedence when param not explicitly passed.
- requires_api_key helper added to NewsAggregator.
- Verified backward compat via PYTHONPATH=src python3 one-liner (legacy ok, config ok).

## _fetch_openweathermap implementation (T5)
- `_KALSHI_WEATHER_CITIES` type annotation says `tuple[float, float]` but runtime values are `(str, float, float)` — unpacking `for ticker, (city_name, lat, lon)` works at runtime despite annotation mismatch
- `resolve_openweather_key` was already imported alongside `resolve_fred_key` on line 19 — edit tool merged the import cleanly
- Budget pattern: similar to `_check_daily_budget()` but uses separate `_owm_daily_count` / `_owm_budget_date` instance vars with 900-call cap
- OpenWeatherMap API uses `units=imperial` for Fahrenheit, `q={city_name}` for city lookup
- Pre-existing test failures: `test_all_sources_present` (expects 3 sources, 11 exist) and `test_news_no_api_keys_json` (CLI test) — both unrelated
