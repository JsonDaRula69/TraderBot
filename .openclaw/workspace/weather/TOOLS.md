<!-- TRADERBOT_WEATHER_TOOLS_START -->
# TOOLS.md - Vane's CLI Reference

## ⚠️ Permission Model

**All `traderbot` commands are classified into TWO tiers:**

| Tier | Rule |
|---|---|
| **🟢 Agent-autonomous** | Run freely. No permission needed. I am an autonomous trader. |
| **🔴 Sysadmin-routed** | I surface these to the sysadmin. I do not execute them myself. |

If a command is not listed, check the sysadmin's `TOOLS.md`. If it's not there either, surface as a feature request.

---

## 🟢 Agent-Autonomous Commands

### Sub-Agent Orchestration

| Tool | Purpose | Notes |
|---|---|---|
| `sessions_spawn` | Spawn isolated sub-agent for experiment design | Non-blocking. Returns `runId` + `childSessionKey`. |
| `sessions_yield` | End current turn, wait for sub-agent completion | Use AFTER `sessions_spawn`. Do NOT poll for completion. |
| `subagents` | List spawned sub-agent status (on-demand only) | Debug/status only. Do not poll in a loop. |

### Market Analysis (Weather-Specific)

| Command | Purpose | Notes |
|---|---|---|
| `traderbot scan --category weather --limit 500 --json` | List all open weather markets | Primary. Filter by subcategory manually. |
| `traderbot analyze TICKER --json` | Orderbook + implied probability | Required before every trade. |
| `traderbot signals --category weather --json` | Blended trading signals (70% stat / 30% news) | Run each decision cycle. |
| `traderbot data-points weather --json` | Daily historical weather (Open-Meteo), economic indicators (FRED), crypto prices (CoinGecko) from ChromaDB | Data pipeline populates this via daily backfill. **This is NOT real-time GFS/ECMWF/CMC model data** — it's historical records for edge calibration and bias tracking. For live forecasts use NWS web pages, wttr.in, or Open-Meteo Currents. If unavailable → check pipeline timers, log warning, continue with live NWS data. |
| `traderbot news-context weather --json` | Pre-trade news context (filter for NOAA/NWS only) | Run each cycle. Ignore non-authoritative results. |
| `traderbot news-summary --signals --json` | High-impact signal detection | Run each heartbeat. |
| `traderbot sentiment TICKER --json` | Aggregate sentiment for a ticker | Supplementary only. Never trade on sentiment alone. |

### Trading & Positions

| Command | Purpose | Notes |
|---|---|---|
| `traderbot trade TICKER --direction yes/no --quantity N --price CENTS --estimated-prob 0.75 --confidence 0.8 --json` | Place live trade through risk pipeline | Always provide `--estimated-prob` (my assessment) and `--confidence` (model agreement strength). Use `--no-confirm` for automation. |
| `traderbot positions --json` | List current open positions | Run every cycle. |
| `traderbot audit --json` | Decision history (`--ticker`, `--start`, `--end`, `--outcome`) | Post-settlement review, pattern discovery. |

### Performance & Self-Improvement

| Command | Purpose | Notes |
|---|---|---|
| `traderbot heartbeat --json` | Run 7-step self-review cycle | Every 30 min. Updates HEARTBEAT_DATA.md. |
| `traderbot performance --json` | My win rate and P&L (`--from`, `--to`) | Every 6h cycle. |
| `traderbot learnings --status active --json` | List my learning patterns (`--status`, `--category`, `--promote`) | Use `--promote <pattern-key>` to promote to PENDING_REVIEW. |
| `traderbot experiment list-treatments` | List available experiment treatments | Read-only, to know what's available. |
| `traderbot profile assignments --json` | Verify my profile is assigned | Read-only. |
| `traderbot profile show <name> --json` | Check my risk parameters | Read-only. |
| `traderbot profile list --json` | See all profiles | Read-only. |

---

## 🔴 Sysadmin-Routed Commands

| Command | Why I Don't Execute It |
|---|---|
| `traderbot profile update` | Profile parameters are the sysadmin's domain. |
| `traderbot profile create` | Creating profiles is fleet management, not trading. |
| `traderbot profile assign` | Agent assignment is fleet management. |
| `traderbot profile revoke` | Agent revocation is fleet management. |
| `traderbot profile set-auth` | Credential management is not my role. |
| `traderbot auth setup-master-password` | Master password is system-level setup. |
| `traderbot shutdown` | Fleet-level shutdown is the sysadmin or human's call. |

---

## Weather-Specific CLI Notes

### Model Data Interpretation

`traderbot data-points weather --json` returns fields I use to make decisions:

| Field | My Use |
|---|---|
| `gfs_ensemble_mean` | Primary temperature/precip signal. |
| `ecmwf_ensemble_mean` | Secondary confirmation. If diverges from GFS > threshold, reduce conviction. |
| `cmc_ensemble_mean` | Tiebreaker when GFS and ECMWF disagree. |
| `model_spread` | Standard deviation across models. < 0.5 SD = high conviction. > 1.5 SD = reduced exposure. |
| `cpc_outlook` | Seasonal and subseasonal baseline. Authoritative for long-lead contracts. |
| `nhc_advisory` | Active tropical cyclone guidance. Highest priority signal during hurricane events. |
| `nws_warnings` | Active watches/warnings. Overrides model-only signals. |

### News Context Priority

`traderbot news-context weather --json` returns articles and sentiment. I prioritize by source:

1. **NOAA / NWS** — Highest. Official government forecasts and warnings.
2. **National Hurricane Center** — All hurricane-related. Separate from general NOAA.
3. **CPC (Climate Prediction Center)** — ENSO, MJO, seasonal outlooks.
4. **World Meteorological Organization** — International storm names, global climate events.
5. **Emergency Management Agencies (FEMA, state-level)** — Emergency declarations.
6. **AccuWeather / WeatherChannel** — Secondary. Commercial forecasts may diverge from official.
7. **All other sources** — Noise. Do not trade on. Logged as context only.

### Position Sizing Reference

| Condition | Sizing Factor |
|---|---|
| Normal conditions, model convergence < 0.5 SD | 1.0x (profile default) |
| Model convergence < 0.5 SD + short horizon (0-3d) | 1.5x (max) |
| Seasonal transition period | 0.7x for temp, 1.3x for precip |
| Active hurricane with NHC Warning | 1.5x (within profile limits) |
| Hurricane with Rapid Intensification forecast | 0.5x |
| Model divergence > 1.5 SD | 0.5x |
| Data source failure | 0.0x (halt new trading) |
| 7+ day horizon, any market type | 0.25x |
<!-- TRADERBOT_WEATHER_TOOLS_END -->
