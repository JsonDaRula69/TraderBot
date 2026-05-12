
## F3: Real Manual QA — News Module

### Sources Configuration
- 11 NewsSource enum members: newsapi, twitter, reddit, open_meteo, coingecko, thesportsdb, coincap, openweathermap, ballotpedia, fred, google_trends
- SOURCE_CATEGORY_COVERAGE: All 11 sources have entries. TWITTER has empty list (stub).
- SOURCE_REQUIRES_KEY: Only OPENWEATHERMAP and FRED require keys (frozenset of 2).
- DataSourcesConfig has 5 fields: newsapi_key, openweather_key, fred_key, reddit_subreddits, daily_budget

### Backward Compatibility
- `NewsAggregator(newsapi_key='test')` — works
- `NewsAggregator(config=DataSourcesConfig(...))` — works
- Individual params override config values — confirmed

### Category Filter Behavior
- All sources check category_filter early and return [] if their categories don't intersect
- Sources with single category: OPEN_METEO (weather), THESPORTSDB (sports), COINCAP (crypto), OPENWEATHERMAP (weather)
- Sources with multiple categories: COINGECKO (crypto, mentions), BALLOTPEDIA (elections, politics), FRED (economics, financials), GOOGLE_TRENDS (mentions, social)
- Tested all 7 non-trivial sources with wrong category → all return []

### Missing Key Behavior
- OpenWeatherMap without key: calls resolve_openweather_key(), returns [] with warning
- FRED without key: calls resolve_fred_key(), returns [] with warning
- fetch_all properly skips key-requiring sources when keys are missing

### Test Counts
- Unit tests: 20/20 pass
- Live tests: 8 discovered (not run — require internet + API keys)
- Edge case tests: 15/15 pass

### Note
- `traderbot.profiles.config` does NOT export `get_current_profile` or `TradingProfile`/`AgentRiskLimits` classes
- It only exports 4 resolve functions: resolve_kalshi_credentials, resolve_newsapi_key, resolve_openweather_key, resolve_fred_key
