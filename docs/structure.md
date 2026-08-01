# TraderBot Module Structure

Complete module map of `src/traderbot/`, organized by package.

## Directory Tree

```
src/traderbot/
├── __init__.py
├── auth.py
├── cli.py
├── cron_loops.py
├── fileops.py
├── heartbeat.py
├── learning.py
├── logging_config.py
├── master_password.py
├── paths.py
├── platform_compat.py
├── sandbox.py
├── update_config.py
├── updater.py
├── wal.py
├── windows_service.py
├── analysis/
├── cli/
├── data/
├── db/
├── experiment/
├── kalshi/
├── llm/
├── news/
├── profiles/
├── risk/
└── simulation/
```

---

## Root Modules

- `__init__.py` — Package init, version exports
- `auth.py` — AuthManager: credential resolution via keyring → env → .env fallback chain
- `cli.py` — Legacy CLI entry point (delegated to `cli/` package)
- `cron_loops.py` — DecisionLoopPayload, HeartbeatLoopPayload, NewsLoopPayload for scheduled execution
- `fileops.py` — File operation utilities (workspace file propagation)
- `heartbeat.py` — 7-step self-review cycle runner
- `learning.py` — Learning pattern management and persistence
- `logging_config.py` — Logging configuration and setup
- `master_password.py` — Master password enforcement and validation
- `paths.py` — Workspace paths: get_workspace_dir(), get_agent_workspace_dir(), get_data_dir()
- `platform_compat.py` — Cross-platform helpers: systemd_remove_services(), launchd_remove_services()
- `sandbox.py` — Application-level sandbox (chmod + sandbox-exec)
- `update_config.py` — UpdateConfig model for self-update configuration
- `updater.py` — apply_update(): git pull + pip install + workspace file refresh
- `wal.py` — Write-Ahead Log: WalStatus (PENDING/COMPLETED/REJECTED/EXECUTED/CANCELLED/EXPIRED), WalAction (BUY/SELL), write_intent(), update_status(), reconcile(), get_pending()
- `windows_service.py` — Windows service integration

---

## cli/ — CLI Commands

- `__init__.py` — CLI entry point, registers all sub-apps and flat commands
- `admin.py` — Admin commands: bootstrap, heartbeat, halt, resume, learnings, cache-warm, reconcile, check-settlements
- `auth.py` — Auth commands: set-kalshi, set-key, list-keys, delete-key, rotate, migrate, check, detect-tier, clear-session, setup-master-password, change-master-password, check-master-password
- `cron.py` — Cron commands: setup-heartbeat-tasks, remove-heartbeat-tasks; _write_heartbeat_config() using openclaw config set CLI
- `data.py` — Data sub-app commands: forecasts, signals, bias
- `helpers.py` — Shared utilities: _SUDO, _SYSTEMCTL, app (main typer), _resolve_db_path, _with_db, _get_strategy
- `market.py` — Market commands: scan, signals, sentiment
- `news.py` — News commands: news-ingest, news-context, news-summary, data-points, backfill
- `profile.py` — Profile commands: create, update, assign, revoke, list, show, assignments, delete, get-token, discover-agents
- `sandbox.py` — Sandbox enter command
- `trade.py` — Trade commands: analyze, trade, positions, backtest, paper, compare, performance, audit

---

## kalshi/ — Kalshi Exchange Integration

- `__init__.py` — Package init, exports
- `_normalize.py` — Internal normalization utilities for Kalshi data
- `cache.py` — MarketDataCache for caching market data
- `client.py` — KalshiClient: HTTP client with RS256 signing, rate limiter (TokenBucketRateLimiter 20rps), retry logic
- `config.py` — KalshiConfig: API key, private key, base URL settings
- `events.py` — EventService: get_event, get_events, get_multivariate_events
- `exchange.py` — Exchange info and status queries
- `history.py` — HistoryService: historical fills, trades, orders, markets, candlesticks
- `markets.py` — MarketService: get_market, get_orderbook, get_markets (pagination), get_portfolio
- `models.py` — Pydantic models: Market, OrderBook, OrderRequest (V2 bid/ask sides, dollar pricing), OrderResult, PortfolioState, TradeRequest, TradingOrder, StrikeType, Position, Settlement
- `pinning.py` — TLS certificate pinning via SPKI verification
- `portfolio.py` — PortfolioService: get_balance, get_positions, get_fills, get_settlements (returns typed Settlement models)
- `provider.py` — ProdDataProvider: production data provider integration
- `rate_limit.py` — TokenBucketRateLimiter rate limiting
- `signing.py` — RS256 signing with PEM key, auth_headers with nonce/timestamp
- `trading.py` — TradingService: place_order (V2 endpoint /portfolio/events/orders/v2), cancel_order, get_order, list_orders
- `websocket.py` — KalshiWebSocket: async WebSocket client for orderbook_delta, ticker, fill, user_orders channels

---

## risk/ — Risk Management

- `__init__.py` — evaluate_trade(): Full Kelly sizing, position limits, daily loss, max drawdown, circuit breaker check. Returns dict with approved/adjusted/quantity/price
- `agent_limits.py` — Per-agent risk limits and enforcement
- `audit.py` — Trade audit logging and review
- `circuit_breaker.py` — CircuitBreaker state machine (OK→SLOW→HALT→FULL_STOP) with persistence
- `limits.py` — HARD_LIMITS dict, run_all_checks(), per-profile limits override
- `sizing.py` — sized_position_for_trade(), fractional_kelly() (no longer clamps)

---

## analysis/ — Analysis & Indicators

- `__init__.py` — Package init, exports
- `indicators.py` — Technical indicators computation
- `odds.py` — implied_probability() derivation, mid_price_cents calculation
- `portfolio.py` — Portfolio analysis: edge_realization, brier_score, sharpe, win_rate
- `registry.py` — Analysis registry for indicator/signal lookup
- `signals.py` — Signal generation and scoring

---

## news/ — News Pipeline

- `__init__.py` — Package init, exports
- `cache_paths.py` — Cache path management for news data
- `classifier.py` — News classification and categorization logic
- `embeddings.py` — VoyageClient: ChromaDB embedding via voyage-4-large, .env fallback
- `impact_assessor.py` — News impact assessment on markets
- `ingest.py` — ingest_news(): multi-source fetch, classify, embed, store to ChromaDB; .env fallback for NewsAPI + Voyage
- `models.py` — NewsItem, NewsCategory, NewsSource (NWS_ALERTS = "nws_alerts"), NewsItemMetadata
- `sentiment_scorer.py` — Sentiment scoring for news items
- `sources.py` — NewsAggregator: all data source fetchers, _fetch_nws_alerts(), _fetch_open_meteo, _fetch_coingecko, etc. DataSourcesConfig, SOURCE_CATEGORY_COVERAGE

---

## db/ — Database Layer

- `__init__.py` — get_connection(), init_schema()
- `decisions.py` — Decision persistence and retrieval
- `experiment_schema.py` — 5-table experiment DB schema
- `forecast_bias.py` — Forecast bias tracking: record_forecast(), query_bias(), query_all_cities()
- `learnings.py` — Learning pattern persistence and queries
- `positions.py` — Position persistence: upsert, list_positions, update_settlement(), mark_closed(); pnl_cents column
- `reconciliation.py` — reconcile_positions(), reconcile_settlements(), reconcile_all()
- `vectors.py` — ChromaDB vector store setup and queries

---

## experiment/ — Experiment Framework

- `cli.py` — Experiment CLI: populate, verify, run, results, list-treatments
- `harness.py` — Harness: within-subjects experiment executor
- `populate.py` — populate_cmd(): Kalshi market data + forecast data into experiment DB
- `registry.py` — Treatment auto-discovery: discover_treatments(), get_treatment(), list_treatments()
- `results.py` — ExperimentResults: paired t-test, Cohen's d, improvement scoring
- `shared.py` — TreatmentInterface ABC, TreatmentContext, ValidatedDecision
- `methodologies/` — DB utilities for market stratification
  - `__init__.py` — Package init
  - `db_utils.py` — Database utility functions for experiment methodologies
- `treatments/` — Treatment implementations
  - `__init__.py` — Package init
  - `control.py` — ControlTreatment: bypass_llm=True
  - `calibration_bundle.py` — CalibrationBundleTreatment
- `tests/` — Test suite
  - `__init__.py` — Package init
  - `test_env_fallback.py` — Environment fallback tests
  - `test_harness.py` — Harness execution tests
  - `test_installer.py` — Installer tests
  - `test_nws_client.py` — NWS client tests
  - `test_registry.py` — Treatment registry tests
  - `test_results.py` — Results analysis tests
  - `test_schema.py` — Schema validation tests
  - `test_shared.py` — Shared module tests
  - `test_trade_routing.py` — Trade routing tests
  - `test_trading_v2.py` — V2 trading tests
  - `test_treatments.py` — Treatment implementation tests
  - `test_wal.py` — Write-Ahead Log tests

---

## profiles/ — Profile Management

- `__init__.py` — Package init, exports
- `auth.py` — Profile-based authentication and credential resolution
- `config.py` — API key resolution functions
- `discovery.py` — OpenClaw agent discovery from openclaw.json
- `injection.py` — propagate_workspace_files(): template selection by enabled_categories
- `injection_strategies.py` — FENCED_BLOCK_MARKERS, FILE_STRATEGIES, _detect_markers(), fenced_merge()
- `isolation.py` — Agent isolation boundaries and enforcement
- `models.py` — TradingProfile Pydantic model: mode (paper/live), enabled_categories, risk params, paper_mode computed field
- `openclaw_config.py` — Bootstrap hook deployment (agent:bootstrap event), TypeScript handler
- `registry.py` — ProfileRegistry: create, read, update, delete, list profiles
- `runtime.py` — get_current_profile() runtime resolution
- `sysadmin.py` — create_sysadmin_profile(): 0.001 risk multiplier, all categories
- `tokens.py` — Token generation and assignment

---

## data/ — Data Provider Framework

- `__init__.py` — Package init, exports
- `base_provider.py` — BaseDataProvider ABC
- `base_signals.py` — BaseSignalEngine ABC
- `models.py` — CityForecast, ModelConsensus, BiasReport, TradingSignal dataclasses
- `registry.py` — ProviderRegistry for data source management
- `weather/` — Weather data sub-package
  - `__init__.py` — Weather package exports
  - `nws_client.py` — NWS API client: gridpoint resolution (cached), forecast fetch, city alias map (NYC→New York, etc.)
  - `provider.py` — WeatherDataProvider: NWS forecasts + Open-Meteo ensemble (GFS/ECMWF/GEM), get_model_consensus(), get_historical_bias()
  - `signals.py` — WeatherSignalEngine: logistic prob model, model consensus scoring, bias adjustment

---

## llm/ — LLM Integration

- `__init__.py` — Package init, exports
- `client.py` — LLMClient with retry (3 attempts, exponential backoff)
- `ollama.py` — OllamaProvider for local LLM inference

---

## simulation/ — Simulation & Backtesting

- `__init__.py` — Package init, exports
- `adaptation.py` — Strategy adaptation logic
- `adapter_state.py` — Adapter state management for simulation runs
- `data_loader.py` — Historical data loading for backtesting
- `engine.py` — Simulation engine core
- `paper_trader.py` — Paper trading simulation
- `performance.py` — Performance metrics and tracking
- `profiles.py` — Simulation profile configuration
- `settlement.py` — Settlement simulation and processing
- `strategies/` — Strategy implementations
  - `__init__.py` — Strategy package init