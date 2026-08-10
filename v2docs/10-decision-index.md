# TraderBot v2 — Decision Index

> Cross-referenced index of all 38 design decisions with status, dependencies, and key consequences.

---

## Active Decisions

| DD | Topic | Key Decision | Depends On |
|---|---|---|---|
| DD-001 | pipx as sole installation method | Remove installer script, plain pip, venv. pipx-only. | — |
| DD-002 | OpenClaw is a hard dependency | TraderBot requires OpenClaw. Not for standalone human use. | — |
| DD-003 | Docker sandbox in setup | Docker sandbox step included in deploy, not optional. | DD-010 |
| DD-004 | Service registration in setup | System service registration during deploy. | DD-007, DD-022 |
| DD-005 | Retire bootstrap, rename to deploy | Remove `traderbot bootstrap`. First-time config is "deploy". | — |
| DD-006 | OS-aware capability detection | Detect OS, adjust prompts (no keyring on headless Linux). | DD-037 |
| DD-007 | Service templates as package data | Templates in `src/traderbot/services/`, read via `importlib.resources`. | DD-001, DD-022 |
| DD-008 | Prebuilt agent workspaces | No user customization. Shipped by TraderBot. | — |
| DD-009 | 8-step deploy flow | OpenClaw config → SysAdmin → Categories → API tokens → DB → Backfill → Simulate → Verify | DD-001–DD-008, DD-023, DD-037 |
| DD-010 | Mandatory Docker sandbox | All category agents run in Docker. No opt-out. | DD-002 |
| DD-011 | Per-agent data source access control | Category filtering at CLI/MCP level. `enabled_categories` enforcement. | DD-015, DD-025 |
| DD-013 | Three-mode trading | Backtest → Paper → Live → (Suspended). Profile-aware MCP routing. | DD-017, DD-019, DD-021 |
| DD-015 | TraderBot as MCP server | TraderBot registers as MCP server via OpenClaw gateway. Agents call tools through MCP. | DD-002 |
| DD-016 | Always-on service | TraderBot runs as daemon. Data pipeline, MCP server, token rotation in one process. | DD-015, DD-037 |
| DD-017 | Agent lifecycle | Four states: BACKTESTING → PAPER → LIVE → SUSPENDED. SysAdmin manages transitions. | DD-019, DD-021, DD-023 |
| DD-018 | Three-layer self-improvement | Layer 1: Reactive learnings. Layer 2: Agent-debate pipeline. Layer 3: Autonomous dev team. | DD-034, DD-038 |
| DD-019 | Time-lapse behavioral simulation | Backtesting is not just statistical replay. Simulates agent decision-making on historical data. | DD-013, DD-020, DD-033 |
| DD-020 | Historical data sources | Tier 1 (day-0 forecasts), Tier 2 (GRIB2 pipeline), Tier 3 (Kalshi market archive). | DD-033 |
| DD-021 | Paper trading simulation | Same tools, same responses. MCP routes on backend. PaperSlippageModel for fills. | DD-013, DD-029 |
| DD-022 | Service template path resolution | `{placeholder}` syntax resolved at install time via `shutil.which('traderbot')`. | DD-001, DD-007 |
| DD-023 | SysAdmin cron/heartbeat activation | Jobs dormant until SysAdmin activates them. One-shot bootstrap job triggers activation protocol. | DD-017 |
| DD-025 | MCP identity resolution | Profile token as explicit tool parameter. Server resolves token → profile → categories. | DD-015, DD-037 |
| DD-027 | All data sources collect at install | Backfill all categories, not just enabled ones. Ensures data for future categories. | DD-016 |
| DD-028 | news/ and data/ module restructure | Unified `data/` module replaces `news/`. Per-source providers, processing pipeline. | DD-016, DD-035 |
| DD-029 | P&L and settlement consolidation | Single `trading.py` module. Unified `compute_pnl()` and `settle_position()`. | DD-013 |
| DD-030 | CLI circular imports | Extract DB code from `cli/helpers.py` into `db/connections.py`. | — |
| DD-031 | Module-by-module review findings | Simulation, profiles, kalshi, analysis, risk, CLI, experiment, DB findings documented. | DD-029, DD-032 |
| DD-032 | Database restructuring | Per-agent per-mode isolation. Unified schema. Forecast snapshots. Generalized bias tracking. | DD-011, DD-021 |
| DD-033 | GRIB2 processing pipeline | Two phases. Phase 1: day-0 forecasts. Phase 2: multi-day lead time via GFS/ECMWF. | DD-019, DD-020 |
| DD-034 | Dev-Liaison | Subject matter expert on TraderBot. Liaison between SysAdmin and Layer 3 dev team. Not autonomous developer. | DD-018 |
| DD-035 | Category-specific analysis toolkits | Replace generic signal engine with per-category MCP toolkits. Weather first. | DD-015, DD-025 |
| DD-036 | SysAdmin sandbox | Unsandboxed with principled restrictions: no trading tools, workspace file immutability, lifecycle confirmation. | DD-010 |
| DD-037 | Infisical as primary secrets vault | Two-project structure. Machine identity. 4-hour token rotation. Local encrypted fallback. | DD-012, DD-014, DD-024, DD-026 |
| DD-038 | Agent-debate integration | gumbel-ai/agent-debate via OpenClaw sessions_spawn/send/yield. 5-round cycle. TEMPLATE.md modifications. | DD-018, DD-034 |

## Superseded Decisions

| DD | Original Decision | Superseded By | Reason |
|---|---|---|---|
| DD-004 | Bootstrap command | DD-005 | Renamed to "deploy" to avoid confusion with OpenClaw bootstrap |
| DD-012 | Encrypted vault + SecretRef hybrid | DD-037 | Infisical replaces custom encrypted vault. OpenClaw SecretRef still used for token injection. |
| DD-014 | Auth and secrets architecture | DD-037 | Phase 1 (secrets store) replaced by Infisical. Phase 2 (daemon) replaced by MCP server (DD-015). |
| DD-024 | Auth implementation details | DD-037 | `secrets.json` replaced by Infisical. Migration, bind mounts, and token provisioning updated. |
| DD-026 | 1Password as primary secrets vault | DD-037 | 1Password Connect requires paid plan ($7.99+/mo). Infisical is free and open source. |

---

## Reconciled Inconsistencies

| Topic | Original (DD-009) | Current | Reference |
|---|---|---|---|
| Step 7: Simulation start | "paper trading mode" | Agents begin in backtesting | DD-017, DD-019 |
| Step 4: API tokens | "prompt for tokens" | Infisical health check, vault creation, token entry, SecretRef config | DD-037 |
| Step 2: SysAdmin setup | "choose whether to use pre-existing main agent" | SysAdmin is always `main` (non-optional) | DD-036 |
| Step 6: Backfill | "filtered by enabled categories" | All data sources collect at install | DD-027 |
| MCP tool names | Generic names (scan, analyze, weather_forecast) | Category-specific toolkits (weather_forecast_prob, weather_accuracy, etc.) | DD-035, DD-036 |
| Secrets management | 1Password Connect | Infisical (free, open source) | DD-037 |
| DD-012, DD-014, DD-024 | Various auth approaches | Infisical as primary vault, profile tokens as MCP parameters | DD-037 |

---

## Open Items and TBDs

| Item | Status | Notes |
|---|---|---|
| Update pipeline | Deferred | `traderbot update` for pipx, to be designed after roadmap completes |
| Category workspace templates | Shelved | Focusing on SysAdmin, Dev-Liaison, Weather first |
| Docs/code drift | Deferred | To be addressed after roadmap completes |
| Exact promotion metrics | TBD | Deployment bar thresholds (Sharpe, win rate, sample size) to be determined |
| Election toolkit | Design pending | Will follow same pattern as weather toolkit |
| Crypto toolkit | Design pending | Will follow same pattern as weather toolkit |
| Other category toolkits | Design pending | Sports, politics, entertainment, science, health, social |
| GRIB2 Phase 2 implementation | Pending | Tier 2 data pipeline for true multi-day lead time forecasts |
| Layer 3 autonomous dev team | In development | Future: isolated dev agents for GitHub issue pickup |
| TEMPLATE.md modifications | Pending | Review and update for TraderBot-specific agent-debate use |

## Phase 2 Implementation Status (issue #166)

Implemented in Phase 2 (PR on `feat/v2-data-pipeline` → `v2-main`):

- **DD-016 (Always-on service)**: `traderbot daemon` runs the Kalshi WebSocket
  stream, the data pipeline, and the MCP server over streamable-http on loopback
  (`127.0.0.1:8765/mcp`) in one process. `traderbot service install|uninstall|status`
  drives the platform service lifecycle (systemd / launchd / Windows Task Scheduler).
- **DD-022 (Service template path resolution)**: `services/paths.py` `BinPaths` +
  `resolve_bin_paths()` resolve `{placeholder}` templates at install time.
- **DD-028 (news/ and data/ module restructure)**: unified `data/` module with
  `BaseDataProvider`, `DataScheduler`, `ProviderRegistry`, `DataCollectionService`,
  and providers (`OpenMeteoProvider`, `NwsProvider`, `NewsProvider` stub,
  `SettlementMonitor`).
- **WS-first real-time data**: the Kalshi WebSocket is the sole source of
  real-time market data; REST is used only for startup seeding, disconnect
  recovery, and historical data. `traderbot__market_prices` reads from the
  in-memory `MarketCache` with zero REST calls.

Deferred to later phases: ChromaDB (Phase 3), GRIB2 multi-day forecasts (DD-033),
crypto/sports workers, full news NLP/sentiment, Docker sandbox (Phase 5),
per-agent DB isolation (Phase 3), three-mode trading engine (Phase 6/7),
category toolkits (Phase 6), full `traderbot deploy` wizard (Phase 4).
