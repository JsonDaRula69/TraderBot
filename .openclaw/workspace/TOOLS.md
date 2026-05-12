<!-- TRADERBOT_TOOLS_START -->
# TOOLS.md - CLI Reference

## Market Analysis

| Command | Purpose |
|---|---|
| `traderbot scan --json` | List open markets (`--category`, `--limit`) |
| `traderbot analyze TICKER --json` | Orderbook + implied probability |
| `traderbot signals --json` | Active trading signals (`--category`, `--limit`) |

## Trading & Positions

| Command | Purpose |
|---|---|
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --json` | Place trade through risk checks |
| `traderbot positions --json` | List current positions from DB |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |

## News & Sentiment

| Command | Purpose |
|---|---|
| `traderbot news --json` | Fetch news (`--category`, `--limit`, `--source`) |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker |

> **Note:** `traderbot news` uses your profile's `enabled_categories` to target relevant NewsAPI queries. Without `--category`, it queries all profile-enabled categories. Use `--source reddit` as a fallback if NewsAPI results are thin for niche topics.

## Simulation & Backtesting

| Command | Purpose |
|---|---|
| `traderbot backtest --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Historical backtest |
| `traderbot paper --strategy momentum --json` | Paper trade against demo API |
| `traderbot compare --profiles name1,name2 --json` | Compare across risk profiles |
| `traderbot performance --json` | P&L and win rate (`--from`, `--to`) |

## Self-Improvement

| Command | Purpose |
|---|---|
| `traderbot heartbeat --json` | 7-step review cycle (`--dry-run`) |
| `traderbot learnings --json` | List learning patterns (`--status`, `--category`, `--promote`) |

## Profile Management

| Command | Purpose |
|---|---|
| `traderbot profile list --json` | List all profiles |
| `traderbot profile show NAME --json` | Show profile details |
| `traderbot profile create NAME --risk-multiplier 0.8` | Create profile (`--skip-auth` to import global Kalshi creds) |
| `traderbot profile delete NAME` | Delete profile |
| `traderbot profile assign NAME --token TOKEN` | Assign token to agent |
| `traderbot profile revoke TOKEN` | Revoke a token |
| `traderbot profile assignments --json` | List token assignments |
| `traderbot profile update NAME --risk-multiplier 0.9` | Update profile parameters |
| `traderbot profile discover-agents --json` | Map OpenClaw agents to profiles |
| `traderbot profile set-auth NAME --provider kalshi` | Set per-profile credentials |
| `traderbot profile auth NAME --json` | Check profile auth status |

## System

| Command | Purpose |
|---|---|
| `traderbot --version` | Show version |
| `traderbot halt --json` | Check circuit breaker state |
| `traderbot halt --force` | Force FULL_STOP (user only) |
| `traderbot cron status [--json]` | Check status of TraderBot cron loops (requires OpenClaw 2026.5.7+) |
| `traderbot cron setup --agent ID [--channel CH] [--to TARGET]` | Register TraderBot cron loops with OpenClaw |
| `traderbot update` | Pull and install latest update from main branch |
| `traderbot update --check` | Check for available updates (don't install) |
| `traderbot update --dev` | Update from dev branch (one-time, no config persistence) |
| `traderbot update configure` | Configure auto-update settings |

## Market Categories

| CLI Value | API Name | Description |
|---|---|---|
| economics | Economics | Macroeconomic indicators |
| politics | Politics | Political outcomes |
| weather | Climate and Weather | Climate and weather events |
| sports | Sports | Sporting event outcomes |
| science_and_technology | Science and Technology | Science and tech outcomes |
| crypto | Crypto | Cryptocurrency |
| commodities | Commodities | Commodity prices |
| companies | Companies | Company-specific outcomes |
| elections | Elections | Election outcomes |
| entertainment | Entertainment | Entertainment events |
| financials | Financials | Financial markets |
| health | Health | Health and medical |
| mentions | Mentions | Kalshi mention counts |
| social | Social | Social media trends |

Used with `--category` flag on `scan` and `signals`. Profile `enabled_categories` restricts which categories the agent can access. Category values for `--category` must match the CLI Value column (lowercase).

## Modules

- **kalshi** — Exchange adapter: markets, trading, client, history
- **analysis** — Statistical indicators, odds, signal generation
- **risk** — Circuit breaker, position sizing, trade evaluation
- **news** — Aggregation, classification, sentiment scoring

All monetary values in cents (int). Always use `--json` for machine-readable output.
<!-- TRADERBOT_TOOLS_END -->

## Environment Variables

- `TRADERBOT_PROFILE_TOKEN`: Assigned profile token (set by the system at deploy time, do not modify)
- `NEWSAPI_API_KEY`: News API key for `traderbot news` and `traderbot sentiment`. Set in `~/.traderbot/.env` or environment.

Source the workspace `.env` file before running traderbot commands:
```sh
source .env 2>/dev/null || true
```
