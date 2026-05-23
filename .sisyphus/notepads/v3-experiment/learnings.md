2025-05-18: Completed Phase 0b - Created documentation files
treatment_spec.md and scope_boundaries.md are both created under experiments/docs/

2025-05-18: Completed scoring.py — TDD implementation
- Created experiments/v3/scoring.py with 7 functions: compute_pnl, compute_brier, compute_delta_profit, compute_weighted_brier, compute_skip_rate, score_run
- Created experiments/v3/tests/test_scoring.py with 25 tests (all pass)
- POSITION_SIZE=100 (cents) in compute_pnl matches spec
- P&L formulas: buy_yes+YES=int(100*(1-yes_price)), buy_yes+NO=int(-100*yes_price), buy_no+NO=int(100*yes_price), buy_no+YES=int(-100*(1-yes_price))
- Weighted Brier: 2.0x for contested (0.20≤yes_price≤0.80), 0.5x for blowout — weight applied AFTER averaging briers
- score_run() groups decisions by treatment→replicate, averages P&L across replicates, computes weighted Brier per treatment
- delta_profit = best_model_pnl - control_pnl (spec says "treatment - control", best_model is the treatment if only one non-control exists)
- All monetary in cents (int), probabilities as float
- Per-replicate PNL averaging: sum PNLS per replicate, then mean across replicates

2025-05-18: Completed openmeto_fetcher — Open-Meteo Previous Runs API integration
- Created experiments/v3/data_sources/openmeto_fetcher.py with 4 functions: fetch_historical_forecast, fetch_forecast_series, fetch_city_forecast_series, save_forecasts
- Created experiments/v3/tests/test_openmeto_fetcher.py (12 tests, all pass)
- Previous Runs API URL: https://previous-runs-api.open-meteo.com/v1/forecast (free, no auth)
- Archive API URL: https://archive-api.open-meteo.com/v1/archive (for actuals)
- forecast_snapshots table uses column "forecast_temp_f" but we store Celsius — schema naming is a known mismatch, V3 stores raw API values (Celsius)
- Rate limit: 250ms courtesy delay between requests
- Error handling: exceptions return None, series skips failed fetches
- fetch_forecast_series returns T-4 through T-0 (5 timesteps, lead_days 4→0)

2025-05-18: Completed kalshi_fetcher.py — TDD implementation
- Created experiments/v3/data_sources/kalshi_fetcher.py with 6 public functions
- Created experiments/v3/tests/test_kalshi_fetcher.py with 14 tests (all pass)
- Key: HistoryService(client) for settled markets + historical trades; MarketService(client) for orderbook
- Market model has settlement_result (bool) but NO strike fields — must use raw API via client.get(f"/markets/{ticker}") for floor_strike/ceiling_strike
- Price convention: Kalshi uses cents (int 0-100), DB schema uses REAL (0.0-1.0 probability). Convert in fetch_trade_history and fetch_orderbook_snapshot.
- Future peeking prevention: extract_prices_at_timestep uses strict < on window end (not <=)
- PYTHONPATH=.:src needed for tests (traderbot lives in src/, not in system Python)
- Ruff TC003 false positive for sqlite3 (runtime import, not type-only)

2025-05-18: Completed ticker_parser.py — TDD implementation
- Created experiments/v3/ticker_parser.py with parse_ticker() and is_high_temp()
- Created experiments/v3/tests/test_ticker_parser_v3.py with 18 tests (all pass)
- Kalshi date format: YYMMMDD (e.g., 26APR01 = 2026-04-01), NOT DDMMMYY
  - I initially parsed it as DDMMMYY and all date assertions failed
  - The first two chars are the year, last two are the day
- Regex for ticker: ^(KXHIGH|KXLOW)([A-Z]{3,5})-(\d{2}[A-Z]{3}\d{2})-([BT])(\d+(?:\.\d+)?)$
- Strike type rules: B prefix → between; T prefix → less if threshold <= 70 else greater
  - Applies to all 10 V3 tickers correctly
- City code mapping includes both short (SEA) and V2-prefixed variants (TSEA) for backward compatibility
- between strike: floor = int(threshold - 0.5), ceiling = int(threshold + 0.5) when .5
- Between and T-strike parsing return floor/ceiling as None; B-strike returns populated values

2025-05-18: Fixed Celsius/Fahrenheit mismatch in openmeto_fetcher.py
- Open-Meteo returns Celsius but DB schema expects Fahrenheit (column forecast_temp_f)
- fetch_historical_forecast() now converts: temp_f = round(temps[0] * 9/5 + 32, 1)
- Dict key changed from 'forecast_temp_c' to 'forecast_temp_f'
- Tests updated: renamed test, added 0C/30C conversion assertions, updated test data
- All 14 tests pass (14 passed in 3.18s)

2025-05-18: Completed accuracy_calculator — TDD implementation
- Created experiments/v3/data_sources/accuracy_calculator.py with 3 functions: compute_city_accuracy, compute_accuracy, save_accuracy
- Created experiments/v3/tests/test_accuracy_calculator.py with 6 tests (all pass)
- DB tables used: forecast_snapshots, settlement_results, markets, forecast_accuracy
- JOIN pattern: forecast_snapshots f JOIN settlement_results s ON f.ticker = s.ticker JOIN markets m ON f.ticker = m.ticker
- Grouping: per-city, per-lead_time (days_before column) using dict grouping
- low_confidence flag: set to 1 when sample_count < 3 (matching task spec)
- save_accuracy uses DELETE + INSERT per row (upsert semantics) since forecast_accuracy has no UNIQUE constraint on (city, lead_time)
- No synthesized bias values — all computed from real DB data (unlike V2's CITY_BIAS_F dictionary)
2025-05-18: Completed llm_client.py — LLM call handler with rate limiting, retry, and graceful degradation
- Created experiments/v3/llm_client.py with TokenBucket rate limiter and LLMClient
- Created experiments/v3/tests/test_llm_client.py with 14 tests (all pass)
- TokenBucket: max 10 calls/minute, burst 10, returns wait seconds when depleted
- LLMClient: exponential backoff on 429/503 (up to 3 retries), timeout fallback, malformed JSON fallback
- API key from OLLAMA_API_KEY env var only (no hardcoded keys — fixes V2 violation)
- Base URL from OLLAMA_BASE_URL env var with localhost:11434 default
- Fallback response: decision="skip", confidence=0.1
- V2 had zero error handling and hardcoded API key — both fixed here

2025-05-18: Completed probability.py — Bayesian probability computation using scipy.stats.norm
- Created experiments/v3/probability.py with 4 functions: prob_less, prob_greater, prob_between, compute_ci
- Created experiments/v3/tests/test_probability.py with 12 tests (all pass)
- CRITICAL BUG FIX: prob_greater uses 1 - norm.cdf(threshold), NOT the prob_between formula
  - V3.md has copypasta bug where prob_greater reuses floor/ceiling params from prob_between
  - Regression test: test_bug_fix_not_prob_between verifies the correct formula
- Key math: loc = forecast - city_bias (mean of the error-adjusted distribution)
- compute_ci uses Wilson score approximation: se = city_mae / sqrt(sample_count), CI = prob ± z*se/10
- scipy needed separate install (not in project pyproject.toml yet)
- Test correction: prob_less(88.9, 66, ...) ≈ 0 (not >0.99) — when forecast >> threshold, P(actual < threshold) is near 0

2025-05-18: Completed market_selector.py — stratified sampling with TDD
- Created experiments/v3/market_selector.py with Stratum (frozen dataclass), compute_stratum(), select_markets()
- Created experiments/v3/tests/test_market_selector.py (14 tests, all pass)
- 2×3×2 grid: difficulty (contested/blowout) × strike_type (less/greater/between) × lead_time (short/long) = 12 strata
- contested = yes_price 0.20-0.80 inclusive; blowout = outside that range
- Lead time computed from resolution_date vs reference_date: ≤2d=short, ≤7d=medium, >7d=long
- select_markets() uses seed for reproducibility via random.Random(seed)
- Filters to settled markets only (settlement_result IS NOT NULL), joins market_prices at timestep=0
- Undersampled strata return min(markets_per_cell, available) — no crash on sparse cells
- reference_date parameter for test determinism (defaults to date.today())
- Ruff I001 auto-fixed with ruff format; B017/B007 in tests fixed to FrozenInstanceError and _idx
