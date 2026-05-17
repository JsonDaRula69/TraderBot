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
| `--limit` | 20 | Max markets to return |
| `--category` | None | Filter by market category |

### traderbot analyze

```bash
traderbot analyze TICKER [--json]
```

Get market details, orderbook, indicators, and edge estimate.

### traderbot trade

```bash
traderbot trade TICKER --direction yes|no --quantity N --price CENTS \
    --estimated-prob 0.75 --confidence 0.8 [--json]
```

Place a trade through the risk pipeline. Returns sized position in cents or rejection reason.

| Arg | Default | Description |
|---|---|---|
| `--direction` | — | Trade direction: `yes` or `no` |
| `--quantity` | — | Number of contracts |
| `--price` | — | Limit price in cents |
| `--estimated-prob` | — | Your estimated probability (0.0–1.0) — required for Kelly sizing |
| `--confidence` | — | Your confidence in the estimate (0.0–1.0) — adjusts position size |

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
traderbot paper --strategy NAME [--duration N] [--db PATH] [--json]
```

Paper trade a strategy with simulated orders.

### traderbot compare

```bash
traderbot compare --profiles NAMEA,NAMEB --strategy NAME [--from ISO] [--to ISO] [--bankroll N] [--db PATH] [--json]
```

Compare strategy performance across risk profiles.

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

Fetch, classify, embed, and store news articles and data points into ChromaDB. Standalone data pipeline — no LLM required. Runs via systemd timer every 30 minutes on remote deployments.

### traderbot news-context

```bash
traderbot news-context CATEGORY [--since ISO] [--json]
```

Get aggregated news context for a market category — overall sentiment score + top articles. Designed for pre-trade context gathering.

| Arg | Default | Description |
|---|---|---|
| `--since` | 48 hours ago | Filter articles published after this timestamp |
| `--json` | — | JSON output for machine consumption |

### traderbot news-summary

```bash
traderbot news-summary [--since ISO] [--category STR] [--query STR] [--limit N] [--signalsonly] [--json]
```

Query accumulated news from ChromaDB. Supports semantic search via `--query` (uses VoyageAI embeddings) and category filtering.

| Arg | Default | Description |
|---|---|---|
| `--since` | — | Filter by publication date (ISO 8601) |
| `--category` | — | Filter by market category |
| `--query` | — | Semantic search query string |
| `--limit` | 30 | Max results |
| `--signalsonly` | — | Show only high-impact signals (>0.7) |
| `--json` | — | JSON output |

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

### traderbot profile discover-agents

```bash
traderbot profile discover-agents [--json]
```

Scan `.openclaw/workspace/` for available agents.

### traderbot profile set-auth

```bash
traderbot profile set-auth PROFILE-NAME SERVICE
```

Store credentials for a service under a profile's configuration namespace. Prompts for key and secret.

### traderbot profile auth

```bash
traderbot profile auth PROFILE-NAME [--json]
```

Show configured credentials for a profile.

### traderbot auth login

```bash
traderbot auth login
```

Interactive credential setup for all services.

### traderbot auth set-key

```bash
traderbot auth set-key SERVICE KEY
```

Store a specific credential in the global `.env` file.

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

Verify all required credentials are configured.
