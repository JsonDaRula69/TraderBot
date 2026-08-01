# API Reference

## traderbot CLI

TraderBot's command-line interface. All commands support `--json` for machine-readable output.

### Global Options

| Flag | Description |
|---|---|
| `--json` | Output as JSON instead of Rich-formatted text |

### traderbot scan

```bash
traderbot scan [--limit N] [--category STR]
```

List open markets from Kalshi.

| Arg | Default | Description |
|---|---|---|
| `--limit` | 500 | Max markets to return |
| `--category` | None | Filter by market category |

### traderbot analyze

```bash
traderbot analyze TICKER [--json]
```

Get market details, orderbook, indicators, and edge estimate.

### traderbot trade

```bash
traderbot trade TICKER --direction yes|no --quantity N --price CENTS \
    --estimated-prob 0.75 --confidence 0.8 [--no-confirm] [--json]
```

Place a trade through the risk pipeline. Returns sized position in cents or rejection reason.

**Requires master password.** Run `traderbot auth setup-master-password` first if not already configured.

| Arg | Default | Description |
|---|---|---|
| `--direction` | yes | Trade direction: `yes` or `no` |
| `--quantity` | 1 | Number of contracts |
| `--price` | 50 | Limit price in cents |
| `--estimated-prob` | None | Your estimated probability (0.0–1.0) — overrides market-implied |
| `--confidence` | None | Your confidence in the estimate (0.0–1.0) — default 0.5 if not set |
| `--no-confirm` | — | Skip confirmation prompt (for automation) |

### traderbot positions

```bash
traderbot positions [--db PATH] [--json]
```

List current positions from SQLite.

### traderbot audit

```bash
traderbot audit [--ticker STR] [--start ISO] [--end ISO] [--outcome STR] [--db PATH] [--json]
```

Show decision history with filters.

### traderbot heartbeat

```bash
traderbot heartbeat [--db PATH] [--dry-run] [--json]
```

Periodic self-review: performance, adaptation, risk state, and learning promotion.

### traderbot halt

```bash
traderbot halt [--force] [--json]
```

Check circuit breaker status or force a halt.

### traderbot backtest

```bash
traderbot backtest --strategy NAME [--from ISO] [--to ISO] [--bankroll N] [--db PATH] [--json]
```

Run backtests against historical data.

### traderbot paper

```bash
traderbot paper --strategy NAME --duration N [--initial-balance DOLLARS] [--reconcile] [--db PATH] [--json]
```

Run a paper trading session with real market data. Connects to the live Kalshi API, fetches open markets, runs the specified strategy through risk checks, and tracks simulated positions and P&L. Press Ctrl+C to stop early and see final results.

**Requires master password.** Run `traderbot auth setup-master-password` first if not already configured. Paper trades use real market data but do not place actual orders.

| Arg | Default | Description |
|---|---|---|
| `--strategy` | momentum | Strategy name to run |
| `--duration` | 60 | Run duration in minutes |
| `--initial-balance` | None | Starting cash in dollars (0 = fetch from prod API) |
| `--reconcile` | False | Run settlement reconciliation on startup (not yet implemented) |

### traderbot compare

```bash
traderbot compare --profiles PRESETA,PRESETB --strategy NAME [--from ISO] [--to ISO] [--bankroll N] [--db PATH] [--json]
```

Compare strategy performance across risk profiles. Profiles must be valid strategy presets: `Conservative`, `Moderate`, or `Aggressive`.

### traderbot performance

```bash
traderbot performance [--from ISO] [--to ISO] [--db PATH] [--json]
```

Show performance metrics and P&L.

### traderbot learnings

```bash
traderbot learnings [--status STR] [--category STR] [--promote KEY] [--db PATH] [--json]
```

List learned patterns and trigger promotions.

### traderbot signals

```bash
traderbot signals [--category STR] [--limit N] [--json]
```

Compute and display trading signals across open markets. Blends statistical indicators, market data, and news sentiment (when available) into a combined signal for each market.

| Arg | Default | Description |
|---|---|---|
| `--category` | None | Filter by market category (Economics, Politics, Weather, etc.) |
| `--limit` | 10 | Max markets to scan |

### traderbot sentiment

```bash
traderbot sentiment TICKER [--json]
```

Analyze market sentiment for a specific ticker from news and social media sources.

### traderbot news-ingest

```bash
traderbot news-ingest [--limit N]
```

Fetch, classify, embed, and store news articles and data points into ChromaDB. Standalone data pipeline — no LLM required. Runs via systemd timer every 30 minutes on remote deployments (see also `backfill` for daily historical enrichment of the `data_points` collection).

### traderbot data-points

```bash
traderbot data-points CATEGORY [--hours 48] [--limit 10] [--json]
```

Query ChromaDB for structured data point readings. Returns weather (Open-Meteo, OpenWeatherMap), economic (FRED), and crypto (CoinGecko) data stored by the offline pipeline.

| Argument | Description |
|---|---|
| `CATEGORY` | Market category — `weather`, `economics`, etc. |
| `--hours` | Look back window (default 48) |
| `--limit` | Max data points to return (default 10) |
| `--json` | JSON output |

**Empty results?** If `data-points weather` returns 0 items, the ChromaDB `data_points` collection has not been seeded yet. Run `traderbot backfill --months 6` to bootstrap historical data, then verify the data pipeline timers are active (see deployment guide). The agent's heartbeat checks this automatically and surfaces pipeline health alerts.

### traderbot backfill

```bash
traderbot backfill [--months 6]
```

One-time or recurring historical data backfill for weather, economic, and crypto data. Fetches Open-Meteo weather, FRED economic indicators, and CoinGecko crypto prices into the ChromaDB `data_points` collection.

| Option | Default | Description |
|---|---|---|
| `--months`, `-m` | 6 | Months of history to fetch |

**Idempotent** — skips already-stored doc IDs. Safe to run repeatedly.
**First run** seeds the collection (~1-3 min). **Daily runs** (`traderbot-backfill-data@.timer`) incrementally add new data.
**Used by**: systemd timer `traderbot-backfill-data@.timer` (daily, installed by `install-data-pipeline.sh`).

### traderbot cache warm

```bash
traderbot cache warm [--json]
```

Pre-populate the event category cache independent of any agent session. Useful for speeding up subsequent market scans.

### traderbot profile create

```bash
traderbot profile create NAME --mode paper|live \
    [--description TEXT] \
    [--categories CAT1,CAT2,...] \
    [--risk-multiplier N] \
    [--max-position-pct N] \
    [--max-daily-loss-pct N] \
    [--max-drawdown-pct N] \
    [--max-open-positions N] \
    [--min-liquidity N] \
    [--min-edge-pct N]
```

Create a new trading profile. All risk parameters default to HARD_LIMITS values if not specified.

> **Note**: The CLI option `--min-liquidity` maps to the model field `min_liquidity_threshold`.

### traderbot profile list

```bash
traderbot profile list [--json]
```

List all trading profiles.

### traderbot profile show

```bash
traderbot profile show NAME [--json]
```

Show details for a specific profile.

### traderbot profile delete

```bash
traderbot profile delete NAME [--keep-data]
```

Delete a trading profile. Use `--keep-data false` to also delete data directories.

### traderbot profile update

```bash
traderbot profile update NAME [--mode paper|live] [--description TEXT] \
    [--categories CAT1,CAT2,...] [--risk-multiplier N] \
    [--max-position-pct N] [--max-daily-loss-pct N] \
    [--max-drawdown-pct N] [--max-open-positions N] \
    [--min-liquidity N] [--min-edge-pct N] \
    [--initial-balance-cents N]
```

Update specific fields of an existing profile. Without a name, enters interactive mode. All risk parameters validated against HARD_LIMITS ceilings.

> **Note**: The CLI option `--min-liquidity` maps to the model field `min_liquidity_threshold`.

### traderbot profile get-token

```bash
traderbot profile get-token PROFILE-NAME
```

Retrieve the masked token for a profile assignment.

### traderbot profile assign

```bash
traderbot profile assign AGENT-ID PROFILE-NAME
```

Generate a token and assign an agent to a profile. Injects token into the agent's `TOOLS.md`.

### traderbot profile revoke

```bash
traderbot profile revoke PROFILE-NAME
```

Revoke the token for a profile. Removes token from `TOOLS.md`.

### traderbot profile assignments

```bash
traderbot profile assignments [--json]
```

List all token assignments (masked token values).

## traderbot cron

```bash
traderbot cron setup --agent AGENT-ID [--heartbeat-every 6h] [--news-ingest-every N] [--channel CHANNEL --to TARGET] [--skip-heartbeat-config] [--dry-run] [--json]
```

Register decision, heartbeat, and news cron loops with OpenClaw for an agent. The `--channel` and `--to` flags configure delivery for announcements (e.g., telegram, slack, whatsapp).

## traderbot experiment

Experiment management sub-app: A/B test harness for prediction-market treatments.

Default output is JSON (for agent consumption). Exit codes: 0 = success / no improvement, 1 = failure, 2 = statistically significant improvement detected.

```bash
traderbot experiment {populate|verify|run|results|list-treatments}
```

### traderbot experiment populate

```bash
traderbot experiment populate [--category KXHIGH] [--max-markets 200] [--db PATH]
```

Fetch market data from Kalshi and forecast data from Open-Meteo, storing them in the experiment database.

| Arg | Default | Description |
|---|---|---|
| `--category`, `-c` | `KXHIGH` | Market category prefix to fetch |
| `--max-markets`, `-m` | 200 | Maximum number of markets to fetch |
| `--db`, `-d` | `~/.traderbot/experiments/experiment.db` | Database path (or `EXPERIMENT_DB` env var) |

### traderbot experiment verify

```bash
traderbot experiment verify [--db PATH]
```

Verify experiment database: report market counts, forecast coverage, price coverage, and settled market counts.

| Arg | Default | Description |
|---|---|---|
| `--db`, `-d` | `~/.traderbot/experiments/experiment.db` | Database path (or `EXPERIMENT_DB` env var) |

### traderbot experiment run

```bash
traderbot experiment run [--treatments control,calibration_bundle] [--control control] \
    [--replicates 3] [--seed 42] [--model glm-5.1:cloud] [--db PATH] \
    [--output PATH] [--output-format json|text] [--dry-run] [--run-id UUID]
```

Run a within-subjects experiment. Auto-scores after harness completion.

| Arg | Default | Description |
|---|---|---|
| `--treatments`, `-t` | None | Comma-separated treatment names (must exist in registry) |
| `--control` | `control` | Control treatment name |
| `--replicates`, `-r` | 3 | Number of replicates per market |
| `--seed`, `-s` | 42 | Random seed for market stratification |
| `--model`, `-m` | `glm-5.1:cloud` | LLM model identifier for Ollama provider |
| `--db`, `-d` | `~/.traderbot/experiments/experiment.db` | Database path (or `EXPERIMENT_DB` env var) |
| `--output`, `-o` | None | Write results JSON to this file path |
| `--output-format` | `json` | Output format: `json` or `text` |
| `--dry-run` | False | Validate treatments and preview market selection without LLM calls |
| `--run-id` | Auto-generated UUID | Unique run identifier |

### traderbot experiment results

```bash
traderbot experiment results RUN-ID [--db PATH] [--output-format json|text]
```

Regenerate results for a completed experiment run from the database.

| Arg | Default | Description |
|---|---|---|
| `RUN-ID` | (required) | Run ID to score |
| `--db`, `-d` | `~/.traderbot/experiments/experiment.db` | Database path (or `EXPERIMENT_DB` env var) |
| `--output-format` | `json` | Output format: `json` or `text` |

### traderbot experiment list-treatments

```bash
traderbot experiment list-treatments [--output-format json|text]
```

List available treatments from the registry (auto-discovered from `experiment/treatments/`).

| Arg | Default | Description |
|---|---|---|
| `--output-format` | `json` | Output format: `json` or `text` |

### traderbot profile discover-agents

```bash
traderbot profile discover-agents [--json]
```

Scan `.openclaw/workspace/` for available agents.

### traderbot profile auth

```bash
traderbot profile auth PROFILE-NAME [--json]
```

Show configured credentials for a profile.

### traderbot auth set-kalshi

```bash
traderbot auth set-kalshi
```

Store Kalshi credentials in OS keyring (or .env fallback). Reads existing .env credentials first; only prompts for missing values.

### traderbot auth migrate

```bash
traderbot auth migrate [--service SERVICE]
```

Migrate credentials from .env to OS keyring for better security.

### traderbot auth delete-key

```bash
traderbot auth delete-key SERVICE
```

Delete a stored credential for a service.

### traderbot auth clear-session

```bash
traderbot auth clear-session
```

Clear the current session's decrypted credential cache.

### traderbot auth change-master-password

```bash
traderbot auth change-master-password
```

Change the master password used for credential encryption.

### traderbot auth check-master-password

```bash
traderbot auth check-master-password
```

Verify the master password is correctly configured without exposing credentials.

### traderbot auth list-keys

```bash
traderbot auth list-keys
```

List configured services and keys (values are never shown).

### traderbot auth rotate

```bash
traderbot auth rotate SERVICE
```

Rotate credentials for a service.

### traderbot auth check

```bash
traderbot auth check
```

Verify KALSHI_API_KEY is configured (checks keyring, .env, and environment).
