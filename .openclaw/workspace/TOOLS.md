<!-- TRADERBOT_TOOLS_START -->
# TOOLS.md - CLI Reference

## ⚠️ Permission Model

**All `traderbot` commands are classified into TWO tiers:**

| Tier | Rule |
|---|---|
| **🟢 Agent-autonomous** | Run freely without asking. No permission needed. |
| **🔴 Human-only** | You MUST request EXPLICIT permission from the user BEFORE running. Do not execute these on your own. If unsure, ask. |

If a command is not listed below, assume it requires permission (🔴 Human-only).

---

## 🟢 Agent-Autonomous Commands

### Market Analysis

| Command | Purpose |
|---|---|
| `traderbot scan --json` | List open markets (`--category`, `--limit`, default 500) |
| `traderbot analyze TICKER --json` | Orderbook + implied probability |
| `traderbot signals --json` | Active trading signals (`--category`, `--limit`) |
| `traderbot news --json` | Fetch news (`--category`, `--limit`, `--source`) |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker |

### Trading & Positions

| Command | Purpose |
|---|---|
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --json` | Place trade with your probability estimate through risk checks. **Always provide `--estimated-prob` and `--confidence`** — without these, Kelly sizing defaults to market-implied probability and rejects all trades. |
| `traderbot positions --json` | List current positions from DB |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |

### Simulation & Backtesting

| Command | Purpose |
|---|---|
| `traderbot backtest --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Historical backtest |
| `traderbot paper --strategy momentum --json` | Paper trading with real market data |
| `traderbot performance --json` | P&L and win rate (`--from`, `--to`) |

### Self-Improvement

| Command | Purpose |
|---|---|
| `traderbot heartbeat --json` | 7-step review cycle (`--dry-run`) |
| `traderbot learnings --json` | List learning patterns (`--status`, `--category`, `--promote`) |
| `traderbot compare --profiles name1,name2 --json` | Compare across risk profiles |
| `traderbot --version` | Show version |
| `traderbot halt --json` | Check circuit breaker state (read-only) |
| `traderbot update` | Update TraderBot to latest version |

### Profile Inspection (read-only)

| Command | Purpose |
|---|---|
| `traderbot profile list --json` | List all profiles |
| `traderbot profile show NAME --json` | Show profile details |
| `traderbot profile assignments --json` | List token assignments |
| `traderbot profile auth NAME --json` | Check profile auth status |

---

## 🔴 Human-Only Commands (REQUIRE EXPLICIT PERMISSION)

**You MUST ask for permission before running ANY of these commands. State which command you want to run and why, then wait for explicit user approval.**

### Risk & Safety

| Command | Why Restricted |
|---|---|
| `traderbot halt --force` | Emergency override — requires human judgment |
| `traderbot resume` | Clears circuit breaker halt — agent must alert, not auto-resume |
| `traderbot resume` | Clears circuit breaker halt — requires human judgment (agent should alert, not auto-resume) |

### Profile Management (changes config or credentials)

| Command | Why Restricted |
|---|---|
| `traderbot profile create NAME --risk-multiplier 0.8` | Creates config — human decides profiles |
| `traderbot profile delete NAME` | Destructive — could remove active config |
| `traderbot profile assign NAME --token TOKEN` | Binds agent to profile — deployment decision |
| `traderbot profile revoke TOKEN` | Revokes access — security boundary |
| `traderbot profile update NAME [OPTIONS]` | Changes risk limits, categories — **must request permission each time** |
| `traderbot profile set-auth NAME --provider kalshi` | Configures .env credentials — security boundary |
| `traderbot profile discover-agents --json` | Maps agents to profiles — deployment decision |

### Auth & Credentials

| Command | Why Restricted |
|---|---|
| `traderbot auth login` | Interactive credential setup — security boundary |
| `traderbot auth set-key SERVICE KEY` | Stores credential — security boundary |
| `traderbot auth rotate SERVICE` | Rotates credential — security boundary |
| `traderbot auth check` | Verifies .env credentials — informational but best with human awareness |

### System

| Command | Why Restricted |
|---|---|
| `traderbot bootstrap` | One-time setup — should not run mid-session |

---

## Market Categories

economics, politics, weather, sports, science_and_technology, crypto, commodities, companies, elections, entertainment, financials, health, mentions, miscellaneous (14 values — matches Kalshi API)

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
Crypto sources (CoinGecko) return `DataPoint` objects with prices in integer cents.
FRED returns economic indicators as `DataPoint` objects.
Google Trends returns trending topics as best-effort `DataPoint` objects.

### Category Coverage

Not all sources cover all categories. Sources are only queried for categories they support:
- **Weather**: Open-Meteo, OpenWeatherMap, NewsAPI, Reddit
- **Crypto**: CoinGecko, NewsAPI, Reddit
- **Sports**: TheSportsDB, NewsAPI, Reddit
- **Elections/Politics**: NewsAPI, Reddit
- **Economics/Financials**: FRED, NewsAPI, Reddit
- **Mentions/Social**: Google Trends, CoinGecko, NewsAPI, Reddit
- **All other categories**: NewsAPI, Reddit

## Modules

- **kalshi** — Exchange adapter: markets, trading, client, history
- **analysis** — Statistical indicators, odds, signal generation
- **risk** — Circuit breaker, position sizing, trade evaluation
- **news** — Aggregation, classification, sentiment scoring

All monetary values in cents (int). Always use `--json` for machine-readable output.

## Signal Computation

`traderbot signals` combines weighted sources into a direction (`yes`/`no`/`neutral`) and a confidence score [0, 1]. Two weight models exist:

| Model | Sources & Weights |
|---|---|
| 3-source (default) | indicators **0.30** + odds **0.50** + momentum **0.20** |
| 4-source (with sentiment) | indicators **0.25** + odds **0.45** + momentum **0.15** + sentiment **0.15** |

### Source Details

**Indicators**
- RSI (14-period): <30 → `yes`, >70 → `no`
- Bollinger Bands (20-period, k=2.0) fallback when RSI is 30–70:
  - price < lower band → `yes` (strength 0.7)
  - price > upper band → `no` (strength 0.7)
  - inside bands → `neutral` with strength proportional to distance from middle band

**Odds / Edge**
- Compares agent `estimated_prob` against market-implied probability from the order book (`best_yes_bid / 100`)
- Edge = `estimated_prob - market_prob`
- `|edge| < 0.01` → `neutral`; otherwise direction follows sign of edge
- Strength = `min(1.0, abs(edge) * 5)`

**Momentum**
- EMA(5) vs EMA(20) crossover
- Requires at least 20 price observations
- Strength = `min(1.0, abs(short - long) / long * 10)` (capped at 1.0)

**Sentiment** (optional 4th source)
- Provided by `news_sentiment` when available
- `> 0.1` → `yes`, `< -0.1` → `no`, else `neutral`
- Strength = `min(abs(sentiment), 1.0)`

### Confidence & Direction

For each source: `signed_contribution = strength * weight * (+1 / -1 / 0)` depending on direction.

- **Direction**: sum of signed contributions > 0.01 → `yes`, < -0.01 → `no`, else `neutral`
- **Confidence**: `|sum| / total_weight`, clamped to [0, 1]

> **Note:** `traderbot signals` may return an empty list when no scanned markets have active order books. This is common for low-liquidity categories.

## ⚠️ CRITICAL: Profile Token Required

Most traderbot commands require TRADERBOT_PROFILE_TOKEN to access the profile-specific database. Without it, commands like positions, performance, audit, and heartbeat will use the global default DB which has NO data.

Always run this before any traderbot command:
  source .env 2>/dev/null || true

The .env file in the workspace root contains TRADERBOT_PROFILE_TOKEN. The cron jobs already source this, but manual CLI calls will miss it without sourcing.

Symptoms of missing profile token:
  - positions --json returns empty list
  - performance --json shows trade_count: 0
  - heartbeat --json shows open_positions: 0

## Environment Variables

- TRADERBOT_PROFILE_TOKEN: Assigned profile token. MUST source .env before commands. Set by the system at deploy time.
<!-- TRADERBOT_TOOLS_END -->