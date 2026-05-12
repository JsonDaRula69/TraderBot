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
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --json` | Place trade with your probability estimate through risk checks. **Always provide `--estimated-prob` and `--confidence`** — without these, Kelly sizing defaults to market-implied probability and rejects all trades. |
| `traderbot positions --json` | List current positions from DB |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |

## News & Sentiment

| Command | Purpose |
|---|---|
| `traderbot news --json` | Fetch news (`--category`, `--limit`, `--source`) |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker |

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
| `traderbot profile create NAME --risk-multiplier 0.8` | Create profile |
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
| `traderbot bootstrap` | One-time setup wizard |

## Market Categories

economics, politics, weather, sports, culture, technology, science, crypto, commodities, companies, elections, entertainment, financials, health, mentions, social (16 values)

Used with `--category` flag on `scan` and `signals`. Profile `enabled_categories` restricts which categories apply.

## Data Sources

The `traderbot news` command fetches from multiple sources. Use `--source` to select:

| Source | CLI Flag | Categories | Key Required | Free Tier |
|---|---|---|---|---|
| NewsAPI | `--source newsapi` | All 14 | ✅ Required | 100 req/day |
| Reddit | `--source reddit` | All 14 | ❌ None | No rate limit documented |
| Open-Meteo | `--source open-meteo` | Weather | ❌ None | 10,000 req/day |
| TheSportsDB | `--source thesportsdb` | Sports | ❌ None (key "3") | 30 req/min |
| CoinGecko | `--source coingecko` | Crypto, Mentions | ❌ None | 30 req/min |
| OpenWeatherMap | `--source openweathermap` | Weather | ✅ Required | 1,000 req/day |
| FRED | `--source fred` | Economics, Financials | ✅ Required | 120 req/min |
| Google Trends | `--source google-trends` | Mentions, Social | ❌ None (optional pytrends) | Best-effort only |

Use `--source all` to query all matching sources in parallel.

Weather sources (Open-Meteo, OpenWeatherMap) return structured `DataPoint` objects with forecasts in Fahrenheit.
Crypto sources (CoinGecko, CoinCap) return `DataPoint` objects with prices in integer cents.
FRED returns economic indicators as `DataPoint` objects.
Google Trends returns trending topics as best-effort `DataPoint` objects.

### Setting Up API Keys

```
traderbot auth login                        # Interactive setup for ALL services
traderbot auth set-key openweathermap api_key  # Set OpenWeatherMap key
traderbot auth set-key fred api_key            # Set FRED key
```

Or set environment variables: `OPENWEATHER_API_KEY`, `FRED_API_KEY`

### Category Coverage

Not all sources cover all categories. Sources are only queried for categories they support:
- **Weather**: Open-Meteo, OpenWeatherMap, NewsAPI, Reddit
- **Crypto**: CoinGecko, CoinCap, NewsAPI, Reddit
- **Sports**: TheSportsDB, NewsAPI, Reddit
- **Elections/Politics**: Ballotpedia, NewsAPI, Reddit
- **Economics/Financials**: FRED, NewsAPI, Reddit
- **Mentions/Social**: Google Trends, CoinGecko, NewsAPI, Reddit
- **All other categories**: NewsAPI, Reddit

## Modules

- **kalshi** — Exchange adapter: markets, trading, client, history
- **analysis** — Statistical indicators, odds, signal generation
- **risk** — Circuit breaker, position sizing, trade evaluation
- **news** — Aggregation, classification, sentiment scoring

All monetary values in cents (int). Always use `--json` for machine-readable output.
<!-- TRADERBOT_TOOLS_END -->

## Environment Variables

- `TRADERBOT_PROFILE_TOKEN`: Assigned profile token (set by the system at deploy time, do not modify)
