<!-- TRADERBOT_SYSADMIN_TOOLS_START -->
# TOOLS.md - Sysadmin CLI Reference

## ⚠️ Permission Model

**All `traderbot` commands are classified into TWO tiers:**

| Tier | Rule |
|---|---|
| **🟢 Sysadmin-autonomous** | Run freely without asking. No permission needed. These are read-only / analytical. |
| **🔴 Human-only / Escalation** | You MUST either request EXPLICIT permission or escalate to the human BEFORE acting. Do not execute these on your own. If unsure, ask. |

If a command is not listed below, assume it requires permission (🔴 Human-only).

---

## 🟢 Sysadmin-Autonomous Commands

### Oversight & Monitoring

| Command | Purpose |
|---|---|
| `traderbot scan --json` | List open markets (read-only overview for all categories) |
| `traderbot heartbeat --json` | Run the 7-step self-review cycle on behalf of managed agents |
| `traderbot performance --json` | Review P&L and win rate across agents (`--from`, `--to`) |
| `traderbot halt` | Check circuit breaker status (read-only for sysadmin) |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) |
| `traderbot learnings list --json` | List learning patterns (`--status`, `--category`) |
| `traderbot compare --profiles name1,name2 --json` | Compare performance across profiles/agents |

### Test Lab (Sysadmin Domain)

| Command | Purpose |
|---|---|
| `traderbot backtest --strategy momentum --from YYYY-MM-DD --to YYYY-MM-DD --json` | Historical backtest (test lab only) |
| `traderbot paper TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --confirm --json` | Paper trade (requires `--confirm` and master password) |

### Analysis & Context

| Command | Purpose |
|---|---|
| `traderbot news-summary --since <last_session_end> --json` | Query accumulated news from ChromaDB |
| `traderbot news-context CATEGORY --json` | Pre-trade news context by category (read-only) |
| `traderbot data-points CATEGORY --json` | Query quantitative data points |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker |

### Agent Management

| Command | Purpose |
|---|---|
| `traderbot profile assignments --json` | List token assignments (see which agents are paired) |
| `traderbot profile list --json` | List all profiles |
| `traderbot profile show <name> --json` | Show profile details |

---

## 🔴 Human-only / Escalation Commands

| Command | Purpose | Why Human-only |
|---|---|---|
| `traderbot profile create <name> --mode paper \ --categories ...` | Create a new trading profile | Defines risk parameters and trading scope |
| `traderbot profile assign <agent-id> <profile>` | Assign an agent to a profile | Gives an agent real trading authority |
| `traderbot profile revoke <profile>` | Revoke an agent assignment | Removes an agent's authority |
| `traderbot trade TICKER ...` | Live trade | Real monetary risk — only category agents, never sysadmin |
| `traderbot profile set-auth <name> kalshi` | Set Kalshi API credentials | Credential management |
| `traderbot auth setup-master-password` | Set master password | Security-critical |

**IMPORTANT:** The sysadmin does NOT execute `traderbot trade`. If you see a trade command, it is either:
- A category agent running autonomously (report it if anomalous), or
- A user request that should be routed to the appropriate category agent, or
- A test-lab paper trade (requires approval and master password)

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
