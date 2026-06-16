# TraderBot v2 — Architecture Overview

> This document describes the complete system architecture emerging from the 38 design decisions in v2roadmap.md.

---

## System Boundary Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Host Machine                                 │
│                                                                     │
│  ┌─────────────────────┐    ┌──────────────────────────────────┐   │
│  │    OpenClaw Gateway  │    │      TraderBot Service           │   │
│  │                      │    │      (always-on daemon + MCP)     │   │
│  │  - Agent sessions    │◄──►│                                  │   │
│  │  - Cron/heartbeat    │    │  ┌─────────────────────────┐    │   │
│  │  - Session comms     │    │  │   Data Collection Workers│    │   │
│  │  - SecretRef resolve │    │  │  ├─ Kalshi WebSocket     │    │   │
│  │  - MCP tool routing  │    │  │  ├─ News ingest (30m)    │    │   │
│  │                      │    │  │  ├─ Weather data (1h)    │    │   │
│  └──────┬───────────────┘    │  │  ├─ FRED data (daily)   │    │   │
│         │                    │  │  ├─ Settlement monitor   │    │   │
│         │                    │  │  └─ Token rotation (4h)  │    │   │
│         │                    │  └─────────────────────────┘    │   │
│         │                    │                                  │   │
│         │                    │  ┌─────────────────────────┐    │   │
│         │                    │  │   MCP Server (stdio)    │    │   │
│         │                    │  │  Resolves token → profile│    │   │
│         │                    │  │  Enforces category ACLs  │    │   │
│         │                    │  │  Routes by mode          │    │   │
│         │                    │  └─────────────────────────┘    │   │
│         │                    │                                  │   │
│         │                    │  ┌─────────────────────────┐    │   │
│         │                    │  │   Infisical Client       │    │   │
│         │                    │  │  (secrets resolution)    │    │   │
│         │                    │  └─────────────────────────┘    │   │
│         │                    └──────────────────────────────────┘   │
│         │                                                           │
│         │    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│         │    │  Infisical   │  │  Local DBs   │  │  ChromaDB    │ │
│         │    │  (secrets)   │  │  (SQLite)    │  │  (vectors)   │ │
│         │    └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                                                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          │  Docker sandbox (per category agent)
          │  ┌──────────────────────────────────────────┐
          │  │  Agent Container                          │
          │  │  ├─ Workspace files (RO: AGENTS.md, etc) │
          │  │  ├─ Agent data dir (RW: .traderbot/)     │
          │  │  ├─ TRADERBOT_PROFILE_TOKEN (SecretRef)  │
          │  │  └─ OpenClaw agent runtime                │
          │  └──────────────────────────────────────────┘
          │
     ┌────┴────┐
     │  SysAdmin │  (unsandboxed, on host, mode: off)
     └──────────┘
```

---

## Component Responsibilities

### TraderBot Service (Always-On Daemon)

The TraderBot service is a single process that combines the data pipeline, MCP server, and token rotation. It starts at boot and runs continuously (DD-016).

**Startup sequence** (DD-037):
1. Read `INFISICAL_TOKEN` from environment (via OpenClaw SecretRef)
2. Authenticate with Infisical
3. Load all secrets from "TraderBot" and "TraderBot Agent Tokens" projects
4. Start the MCP server (stdio, launched by OpenClaw gateway)
5. Start the token rotation timer (4-hour cycle)
6. Start data collection workers (WebSocket, news, weather, etc.)
7. Run health checks and register as ready

**Data Collection Workers** — Proactive, scheduled fetchers (NOT triggered by agent cron jobs):

| Worker | Interval | Data |
|---|---|---|
| Kalshi WebSocket | Continuous | Real-time market prices, orderbooks, fills, market lifecycle |
| News ingest | 30 min | NewsAPI, Reddit, Twitter articles, embedded via VoyageAI |
| Weather data | 1 hour | NWS forecasts + Open-Meteo historical |
| Economic indicators | Daily | FRED data |
| Settlement monitor | 1 hour | Checks recently settled markets |
| Token rotation | 4 hours | Rotates all agent profile tokens via Infisical |

**MCP Server** — Responds to agent tool calls. Reads from local databases (not external APIs). Returns WebSocket-cached data for real-time requests. Validates agent identity and category permissions on every call.

**Latency model** (DD-016):

| Data type | Source | Freshness | Latency to agent |
|---|---|---|---|
| Market prices | WebSocket cache | Real-time (<1s) | <1ms (local read) |
| Orderbook | WebSocket cache | Real-time (<1s) | <1ms (local read) |
| News context | News ingest worker | ≤30 min | <1ms (local read) |
| Weather forecasts | Weather worker | ≤1 hr | <1ms (local read) |
| Economic indicators | FRED worker | ≤24 hr | <1ms (local read) |
| Trading signals | Computed on query | Uses latest cache | <10ms (computation) |
| Trade execution | Live API call | N/A | Variable (API latency) |

### OpenClaw Gateway

OpenClaw manages the agent runtime layer:
- Agent sessions, LLM orchestration, model selection
- Cron/heartbeat scheduling (agent decision loops, health checks)
- Inter-agent communication (`sessions_spawn`, `sessions_send`, `sessions_yield`)
- MCP tool routing (forwards agent tool calls to the TraderBot MCP server)
- SecretRef resolution (injects `TRADERBOT_PROFILE_TOKEN` and `INFISICAL_TOKEN` into agent environments)
- Docker sandbox management (container creation, bind mounts)
- Webhook server (routes AutoDev notifications to the Dev-Liaison agent)

### AutoDev Team (OpenCode + OmO)

The AutoDev team is responsible for all engineering and development of TraderBot, including v2 implementation. The Dev-Liaison agent serves as the communication bridge between the TraderBot agent fleet and AutoDev.

**Communication architecture:**

| Channel | Direction | Mechanism | What it carries | Latency |
|---|---|---|---|---|
| Wake signal | Either direction | OpenClaw webhooks / Discord bot | "Hey, check GitHub" | Seconds |
| GitHub | Both directions | Issues, PRs, labels, comments | All state and data | 30 min (heartbeat) |

- **AutoDev → Dev-Liaison**: Webhook POST requests to `/hooks/autodev-completed`, `/hooks/autodev-blocked`, `/hooks/autodev-deployed` on the OpenClaw gateway
- **Dev-Liaison → AutoDev**: Discord channel messages (`autodev:wake`, `autodev:cancel`, `autodev:priority`)
- **Fallback**: Wake signals are acceleration, not critical path. GitHub is always the source of truth. If any channel fails, the heartbeat eventually catches everything.

### Infisical

Self-hosted secrets vault (free, open source, MIT license). Two projects:
1. **"TraderBot"** — API keys (Kalshi, VoyageAI, NewsAPI, etc.), namespace-organized (global + per-category)
2. **"TraderBot Agent Tokens"** — Profile tokens, one per agent

Machine identity `traderbot-service` has read/write access. Each agent's machine identity has read access only to its own token. The `INFISICAL_TOKEN` bootstrap secret is stored via OpenClaw SecretRef.

Fallback: local encrypted `secrets.json` with machine-derived encryption for air-gapped systems.

### Local Databases

**SQLite** (per-agent per-mode isolation):
```
~/.traderbot/
├── traderbot.db                         # Global (schema version, config, profile registry)
├── sysadmin/db/decisions.db             # SysAdmin oversight decisions
├── paper-weather/db/decisions.db        # Weather agent paper trades
├── live-weather/db/decisions.db         # Weather agent live trades (created on promotion)
├── paper-economics/db/decisions.db      # Economics agent paper trades
└── ...
```

**ChromaDB** (shared with category metadata filtering):
```
~/.traderbot/chromadb/
├── news/                  # News embeddings (category metadata)
├── data_points/           # Quantitative data (category metadata)
├── market_patterns/       # Pattern signatures (category metadata)
├── news_signals/          # Processed signals (category metadata)
└── market_conditions/     # Market resolution conditions
```

### Docker Sandbox

All category agents run in Docker containers (mandatory, DD-010). Configuration:
- Base image: `python:3.12-slim-bookworm`
- Bind mounts: agent data dir (RW), workspace files (RO), no blanket `~/.traderbot/` mount
- No API tokens or secrets inside containers — only `TRADERBOT_PROFILE_TOKEN` via SecretRef
- SysAdmin runs unsandboxed on host (DD-036)

---

## Data Flow

### Trading Decision Flow (Agent Perspective)

```
Agent decision loop (cron, e.g., every 5 minutes)
  │
  ├─► Call traderbot__weather_forecast_prob(token, ticker)
  │     └─► MCP server resolves token → profile → mode
  │     └─► Returns forecast data from local DB (or simulated data if backtesting)
  │
  ├─► Call traderbot__weather_accuracy(token, city)
  │     └─► Returns historical accuracy metrics from bias_tracking table
  │
  ├─► Call traderbot__market_edge(token, ticker)
  │     └─► Returns market-implied probability, spread, liquidity from WebSocket cache
  │
  ├─► Call traderbot__weather_decision_brief(token, ticker)
  │     └─► Assembled brief combining all analytical outputs
  │
  └─► Call traderbot__trade(token, ticker, direction, quantity, price)
        └─► MCP server:
            ├─► Backtest mode: simulate fill at historical price, record in backtest DB
            ├─► Paper mode: simulate fill with slippage model, record in paper DB
            └─► Live mode: submit to Kalshi API, record in live DB
```

### Data Collection Flow (Service Perspective)

```
TraderBot Service starts
  │
  ├─► Connect Kalshi WebSocket
  │     └─► Subscribe to market lifecycle, ticker, orderbook channels
  │     └─► Cache all real-time data locally
  │
  ├─► Start scheduled workers
  │     ├─► News ingest (every 30 min): NewsAPI → embed → ChromaDB
  │     ├─► Weather fetch (every 1 hr): NWS + Open-Meteo → SQLite + ChromaDB
  │     ├─► FRED fetch (daily): FRED API → SQLite
  │     ├─► Settlement check (every 1 hr): Kalshi REST → settlement_cache
  │     └─► Token rotation (every 4 hrs): Infisical API → rotate all profile tokens
  │
  └─► Listen for MCP tool calls (via stdio from OpenClaw gateway)
        └─► Resolve token → profile → categories → mode
        └─► Query local databases, return results
```

---

## Key Architectural Decisions Summary

| Decision | Key | Reference |
|---|---|---|
| Installation | pipx-only, OS-aware | DD-001, DD-006 |
| First-time config | 8-step "deploy" flow | DD-005, DD-009 |
| Agent isolation | Docker sandbox (mandatory for categories) | DD-010 |
| Data access control | Per-agent MCP filtering | DD-011, DD-025 |
| Trading modes | Backtesting → Paper → Live → Suspended | DD-013, DD-017 |
| Tool architecture | MCP server via OpenClaw gateway | DD-015 |
| Service model | Always-on daemon + data pipeline + MCP | DD-016 |
| Self-improvement | Three-layer architecture + agent-debate | DD-018, DD-038 |
| Simulation | Time-lapse behavioral, not just statistical | DD-019 |
| Secrets | Infisical (primary), local encrypted (fallback) | DD-037 |
| Analysis | Category-specific toolkits, not generic signals | DD-035 |
| SysAdmin | Unsandboxed with principled restrictions | DD-036 |
| Dev-Liaison | Subject matter expert, AutoDev liaison, webhook communication | DD-034 |
| Data pipeline | Unified `data/` module, all sources collect at install | DD-027, DD-028 |
| Kalshi data | WebSocket-first, REST only for fallback/history | DD-016 |
| Lifecycle transitions | Driven by SysAdmin, not automated | DD-017, DD-023 |
