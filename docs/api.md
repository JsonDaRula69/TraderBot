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
traderbot trade TICKER --direction yes|no --quantity N --price CENTS [--json]
```

Place a trade through the risk pipeline. Returns sized position in cents or rejection reason.

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

Store credentials for a service under a profile's keyring namespace. Prompts for key and secret.

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

Store a specific credential in the global keyring.

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
