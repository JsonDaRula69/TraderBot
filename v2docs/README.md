# TraderBot v2 Documentation

> Authoritative documentation for the TraderBot v2 architecture, grounded in the 38 design decisions recorded in v2roadmap.md. Where there are contradictions between these docs and the roadmap, the roadmap takes precedence.

## Document Index

| Document | Description |
|---|---|
| [00-principles.md](00-principles.md) | Core design principles and philosophy (14 principles) |
| [01-architecture-overview.md](01-architecture-overview.md) | System architecture, component relationships, data flow, latency model |
| [02-installation-and-deploy.md](02-installation-and-deploy.md) | pipx installation, 8-step deploy flow, OS-specific behavior, what gets retired |
| [03-agents-and-lifecycle.md](03-agents-and-lifecycle.md) | Agent types, lifecycle states, SysAdmin activation protocol, cron/heartbeat architecture, self-improvement |
| [04-security-and-auth.md](04-security-and-auth.md) | Infisical secrets management, MCP auth, per-agent isolation, token rotation, division of secrets responsibility |
| [05-data-pipeline.md](05-data-pipeline.md) | Always-on data collection, WebSocket-first Kalshi, unified data module, category toolkits, P&L consolidation |
| [06-trading-and-simulation.md](06-trading-and-simulation.md) | Three-mode trading, paper trading, backtesting, profile-aware MCP routing, module changes |
| [07-self-improvement.md](07-self-improvement.md) | Three-layer improvement framework, agent-debate integration, 5-round cycle, root cause classification, guardrails |
| [08-database-schema.md](08-database-schema.md) | Per-agent per-mode isolation, unified SQL schema, ChromaDB collections, efficiency improvements, GRIB2 pipeline |
| [09-mcp-tools.md](09-mcp-tools.md) | Complete MCP tool reference, weather toolkit, SysAdmin tools, OpenClaw tool configuration, authentication flow |
| [10-decision-index.md](10-decision-index.md) | Cross-referenced index of all 38 DDs with status, dependencies, and reconciled inconsistencies |

## Relationship to v2roadmap.md

These documents are derived from and grounded in the design decisions in `v2roadmap.md`. They synthesize the 38 decisions into coherent, topic-focused documentation suitable for implementation reference.

### Reconciled Inconsistencies

The following inconsistencies were found during the v2 roadmap review and have been reconciled in these docs:

| Topic | DD-009 (original) | Superseding DD | Resolution |
|---|---|---|---|
| Step 7: Simulation start | "Paper trading mode" | DD-017, DD-019 | Agents begin by backtesting, not paper trading |
| Step 4: API tokens | "Prompt for tokens" | DD-037 | Infisical health check, vault creation, token entry, SecretRef config |
| Step 2: SysAdmin setup | "Choose whether to use pre-existing main agent" | DD-036 | SysAdmin is always `main` (non-optional) |
| Step 6: Backfill | "Filtered by enabled categories" | DD-027 | All data sources begin collection at install |
| MCP tool names | Generic names (scan, analyze, weather_forecast) | DD-035, DD-036 | Category-specific toolkits replace generic names |
| Secrets management | 1Password Connect | DD-037 | Infisical replaces 1Password as primary vault |
| DD-012, DD-014, DD-024 | Various auth approaches | DD-026 → DD-037 | All superseded by Infisical as primary vault |

### Remaining Open Items

| Item | Status | Notes |
|---|---|---|
| Update pipeline | Deferred | To be designed after roadmap completes |
| Category workspace templates | Shelved | Focus on SysAdmin, Dev-Liaison, Weather first |
| Exact promotion metrics | TBD | Deployment bar thresholds to be determined |
| Other category toolkits | Design pending | Election, crypto, sports, etc. follow weather pattern |
| GRIB2 Phase 2 | Pending | True multi-day lead time forecasts |
| Layer 3 dev team | In development | Future: autonomous dev agents |
| TEMPLATE.md modifications | Pending | Review for TraderBot-specific use |

## Key Design Principles (Summary)

1. **TraderBot provides tools and data; OpenClaw agents make decisions.** No directional trading calls from TraderBot.
2. **Full autonomy.** Agents never wait for human permission. Clear guidelines, checks and balances.
3. **One concept per improvement cycle.** Measured and validated before moving on.
4. **Statistical rigor as foundational philosophy.** Hypotheses, tests, calibration, historical records.
5. **Kalshi market specificity.** Not general prediction improvement — Kalshi market performance specifically.
6. **Category isolation.** Per-agent data, tools, Docker sandbox, and credential access.
7. **WebSocket-first data.** REST API only for fallback, recovery, and historical data.
8. **Profile-aware, mode-aware tooling.** Same tools regardless of mode; MCP routes on backend.
9. **SysAdmin manages lifecycle transitions.** Not automated. Follows predefined protocol but can deviate.
10. **Prebuilt agents, no customization.** Immutable workspace files minimize variability.
11. **OpenClaw is not a trust boundary.** Auth and access control enforced by TraderBot MCP server.
12. **Minimum footprint.** Only required dependencies and modules for the user's OS and categories.
13. **Idempotency and safety.** All operations idempotent. Every resource has a cleanup path.
14. **Cross-platform.** macOS, Windows, Linux (including headless). Identical user flow.
