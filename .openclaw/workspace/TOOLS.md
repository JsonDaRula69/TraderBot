<!-- TRADERBOT_SYSADMIN_TOOLS_START -->
# TOOLS.md - Sysadmin CLI Reference

## ⚠️ Permission Model

**All `traderbot` commands are classified into TWO tiers:**

| Tier | Rule |
|---|---|
| **🟢 Sysadmin-autonomous** | Run freely without asking. No permission needed. The sysadmin manages the entire fleet lifecycle autonomously. |
| **🔴 Exception only** | Reserved for system-critical operations that the human should handle personally. These are rare. |

If a command is not listed below, assume it is 🟢 Sysadmin-autonomous (it's probably covered by a general category below).

---

## 🟢 Sysadmin-Autonomous Commands

### Sub-Agent & Session Tools

| Tool | Purpose |
|---|---|
| `sessions_list` | List all sessions (filter by kind, label, agent) — discover agent sessions |
| `sessions_history` | Read agent SESSION-STATE.md and Pending Actions across the fleet |
| `sessions_send` | Notify agents of experiment status (RECEIVED, DEPLOYED, REJECTED) |
| `sessions_spawn` | Spawn isolated test-lab execution sub-agents if needed |
| `subagents` | List spawned sub-agent status |

### Fleet Management

| Command | Purpose | Signature |
|---|---|---|
| `traderbot profile create <name>` | Create a new profile | `--mode paper/live --categories ... --risk-multiplier 0.5 --max-position-pct 10 --min-edge-pct 3` |
| `traderbot profile update <name>` | Update profile parameters | `--risk-multiplier --max-position-pct --max-daily-loss-pct --max-drawdown-pct --max-open-positions --min-liquidity --min-edge-pct --initial-balance-cents` |
| `traderbot profile assign <agent-id> <profile>` | Assign an agent to a profile | No named options |
| `traderbot profile revoke <profile>` | Revoke an agent's profile | No named options |
| `traderbot profile list --json` | List all profiles | |
| `traderbot profile show <name> --json` | Show profile details | |
| `traderbot profile assignments --json` | List token assignments | |
| `traderbot profile delete <name>` | Delete a profile | |
| `traderbot profile get-token <name>` | Get profile token for service install | |
| `traderbot auth setup-master-password` | Set master password | Required for paper trades |
| `traderbot auth set-kalshi` | Set Kalshi API credentials (interactive prompt) | |
| `traderbot auth check` | Validate all API credentials | `--json` for machine-readable output |
| `traderbot cron setup --agent <name> --role <role> --replace` | Register fleet cron jobs | Isolated sessions per task |

### Oversight & Monitoring

| Command | Purpose |
|---|---|
| `traderbot scan --json` | List open markets (`--category`, `--limit`) |
| `traderbot heartbeat --json` | Run the 7-step self-review cycle |
| `traderbot performance --json` | Review P&L and win rate (`--from`, `--to`, per-agent) |
| `traderbot halt --json` | Check circuit breaker status |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |
| `traderbot reconcile --json` | Sync local positions with Kalshi |
| `traderbot ws status` | WS daemon health — connection state, cache size, uptime |
| `traderbot ws cache` | Event category cache breakdown by category |

### Test Lab (Experiments & Backtesting)

| Command | Purpose | Signature |
|---|---|---|
| `traderbot backtest --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Historical backtest against Kalshi API data | `--strategy <name> --from <date> --to <date> --bankroll <cents> --json` |
| `traderbot compare --profiles Conservative,Moderate --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Compare strategy performance across risk profiles | Uses PRESETS names (Conservative, Moderate, Aggressive). `--strategy`, `--from`, `--to`, `--bankroll`, `--json` |
| `traderbot paper --strategy momentum --duration 60 --initial-balance 10000 --json` | Run a paper trading session with real market data | Session-based. `--strategy <name>`, `--duration <minutes>`, `--initial-balance <dollars>`, `--json` |
| `traderbot experiment populate --category KXHIGH --max-markets 200` | Populate experiment DB with market + forecast data | `--category`, `--max-markets`, `--db` |
| `traderbot experiment verify` | Verify experiment DB coverage | `--db` |
| `traderbot experiment run --treatments control,variant --replicates 3 --model glm-5.1:cloud` | Run within-subjects A/B experiment over treatments | `--treatments`, `--control`, `--replicates`, `--seed`, `--model`, `--dry-run`, `--run-id` |
| `traderbot experiment results <run-id>` | Score a completed experiment run | `--db`, `--output-format json/text` |
| `traderbot experiment list-treatments` | List all available treatments from registry | `--output-format json/text` |

### Analysis & Context

| Command | Purpose |
|---|---|
| `traderbot news-summary --since <timestamp> --json` | Query accumulated news from ChromaDB. `--signals` for high-impact only. `--category`, `--query`, `--source`, `--limit`. |
| `traderbot news-context <CATEGORY> --include-data --json` | Pre-trade news context by category. `--hours`, `--limit`, `--include-data` for quantitative readings. |
| `traderbot data-points <CATEGORY> --json` | Query quantitative data points (weather, economics, etc.). `--hours`, `--limit`. |
| `traderbot sentiment <TICKER> --json` | Aggregate sentiment for a ticker. |
| `traderbot learnings --status active --json` | List learning patterns. `--status`, `--category`, `--promote <pattern-key>` |
| `traderbot scan --category <cat> --limit 500 --json` | List open markets. `--continuous` for 5min polling mode. |

---

## 🔴 Exception Only

| Command | Reason |
|---|---|
| `traderbot halt --force` | Halts all agents (FULL_STOP). Human decision. |
| Modify `AGENTS.md`, `SOUL.md`, `TOOLS.md` | Immutable operating constraints. Requires human approval. |

All other commands are 🟢 autonomous. The sysadmin manages the fleet end-to-end.

---

## News Data

A systemd timer runs `traderbot news-ingest` every 30 minutes. It fetches news, embeds with VoyageAI, and stores in ChromaDB — **no LLM required, works through outages**.

On every wake, run:
```
traderbot news-summary --since <last_session_end> --json
```
Store the `--since` timestamp in `SESSION-STATE.md` so you know where you left off.

For pre-trade news context with quantitative data: `traderbot news-context <cat> --include-data --json`

For standalone quantitative data: `traderbot data-points <category> --json`

For news-blended signals (15% weight): `traderbot signals --category <cat> --json`
<!-- TRADERBOT_SYSADMIN_TOOLS_END -->
