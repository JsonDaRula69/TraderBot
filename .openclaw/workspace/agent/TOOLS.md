<!-- TRADERBOT_AGENT_TOOLS_START -->
# TOOLS.md - Agent CLI Reference

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
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --json` | Place trade with your probability estimate through risk checks. Bypasses confirmation in automation contexts (TRADERBOT_CONFIRM_TRADES=false). **Always provide `--estimated-prob` and `--confidence`** — without these, Kelly sizing defaults to market-implied probability and rejects all trades. |
| `traderbot paper TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --json` | Paper trade (no real money). Same risk pipeline as trade.
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
| `traderbot compare --profiles name1,name2 --json` | Compare across profiles |

---

## 🔴 Human-only Commands

| Command | Purpose | Why Human-only |
|---|---|---|
| `traderbot profile create` | Create a new trading profile | Defines risk parameters |
| `traderbot profile assign` | Assign agent to profile | Trading authority |
| `traderbot profile revoke` | Revoke an agent assignment | Removes authority |
| `traderbot profile set-auth` | Set Kalshi API credentials | Credential management |
| `traderbot auth setup-master-password` | Set master password | Security-critical |

---

## News Data

A systemd timer runs `traderbot news-ingest` every 30 minutes.

On every wake, run:
```
traderbot news-summary --since <last_session_end> --json
```
Store the `--since` timestamp in `SESSION-STATE.md.So you know where you left off.

For pre-trade news context with quantitative data: `traderbot news-context <cat> --include-data --json`

For standalone quantitative data: `traderbot data-points <category> --json`

For news-blended signals (15% weight): `traderbot signals --category <cat> --json`
<!-- TRADERBOT_AGENT_TOOLS_END -->
