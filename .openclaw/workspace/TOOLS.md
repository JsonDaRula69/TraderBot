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
| `traderbot news-context CATEGORY --json` | Pre-trade news context by category (aggregated sentiment + articles, add `--include-data` for quantitative readings) |
| `traderbot data-points CATEGORY --json` | Query quantitative data points (weather, econ, crypto, sports) for a category |
| `traderbot news-summary --json` | Query accumulated news from ChromaDB (`--since`, `--category`, `--query`, `--signalsonly`) |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker |

### Trading & Positions

| Command | Purpose |
|---|---|
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --confirm --json` | Place trade with your probability estimate through risk checks. **Requires `--confirm` flag and master password**. **Always provide `--estimated-prob` and `--confidence`** — without these, Kelly sizing defaults to market-implied probability and rejects all trades. |
| `traderbot paper TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --confirm --json` | Paper trade (no real money). **Requires `--confirm` flag and master password** for live-like execution. |
| `traderbot positions --json` | List current positions from DB |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |

### Simulation & Backtesting

| Command | Purpose |
|---|---|
| `traderbot backtest --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Historical backtest |
| `traderbot performance --json` | P&L and win rate (`--from`, `--to`) |

### Self-Improvement

| Command | Purpose |
|---|---|
| `traderbot heartbeat --json` | 7-step review cycle (`--dry-run`) |
| `traderbot learnings list --json` | List learning patterns (`--status`, `--category`) |
| `traderbot compare --profiles name1,name2 --json` | Compare across risk profiles |
| `traderbot --version` | Show version |
| `traderbot halt --json` | Check circuit breaker state (read-only) |

### Profile Inspection (read-only)

| Command | Purpose |
|---|---|
| `traderbot profile list --json` | List all profiles |
| `traderbot profile show NAME --json` | Show profile details |
| `traderbot profile assignments --json` | List token assignments |

---

## 🔴 Human-Only Commands (REQUIRE EXPLICIT PERMISSION)

**You MUST ask for permission before running ANY of these commands. State which command you want to run and why, then wait for explicit user approval.**

### Risk & Safety

| Command | Why Restricted |
|---|---|
| `traderbot halt --force` | Emergency override — requires human judgment |
| `traderbot resume` | Clears circuit breaker halt — agent must alert, not auto-resume |

### Profile Management (changes config or credentials)

| Command | Why Restricted |
|---|---|
| `traderbot profile create NAME --risk-multiplier 0.8` | Creates config — human decides profiles |
| `traderbot profile delete NAME` | Destructive — could remove active config |
| `traderbot profile assign NAME --token TOKEN` | Binds agent to profile — deployment decision |
| `traderbot profile revoke TOKEN` | Revokes access — security boundary |
| `traderbot profile update NAME [OPTIONS]` | Changes risk limits, categories — **must request permission each time** |
| `traderbot profile auth NAME --json` | Inspect profile's credential status |
| `traderbot profile discover-agents --json` | Maps agents to profiles — deployment decision |

### Auth & Credentials

| Command | Why Restricted |
|---|---|
| `traderbot auth list-keys` | List configured services (never reveals values) |
| `traderbot auth rotate SERVICE` | Rotate credentials in .env — security boundary |
| `traderbot auth check` | Verify KALSHI_API_KEY is configured |

### System

| Command | Why Restricted |
|---|---|
| `traderbot bootstrap` | One-time setup — should not run mid-session |
| `traderbot update` | Modifies installed package — human decides timing |
| `traderbot news-ingest` | Triggers full news pipeline fetch — runs via systemd timer, not agent |
| `traderbot news --json` | Fetches live news from external APIs — agent should use `news-summary` (accumulated) instead |
| `traderbot backfill` | One-time historical data load — not a recurring task |
| `traderbot uninstall` | Destructive — removes all TraderBot services |
| `traderbot cache warm` | Pre-populates event category cache — system maintenance |

---

## Market Categories

economics, politics, weather, sports, science_and_technology, crypto, commodities, companies, elections, entertainment, financials, health, mentions, social (13 values — matches `kalshi.models.MarketCategory`).
<!-- TRADERBOT_TOOLS_END -->
