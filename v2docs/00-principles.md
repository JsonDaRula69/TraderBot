# TraderBot v2 — Core Design Principles

> This document establishes the foundational principles governing TraderBot v2's architecture. Every design decision in the v2 roadmap traces back to one or more of these principles. When in doubt, refer here.

---

## 1. Division of Responsibilities

TraderBot and OpenClaw have a strict separation of concerns:

**TraderBot provides tools and data. OpenClaw agents make decisions.**

| Layer | Responsibility | Does NOT |
|---|---|---|
| **TraderBot** | Data sourcing, organization, and persistence. Statistical analysis and interpretive outputs. Risk enforcement (hard limits). Trade execution routing. Database management. Profile and credential management. Access control enforcement. | Decide what to trade, when, or how much. Override risk limits. Interpret analysis outputs for the agent. |
| **OpenClaw** | Agent lifecycle, LLM orchestration, session management, cron/heartbeat scheduling, inter-agent communication, channel integration. | Manage data pipelines. Store trade records. Enforce risk limits. |
| **Agent Workspace** | Operating rules, identity, tool permissions, heartbeat tasks. Prebuilt and immutable — agents cannot modify core workspace files. | Customize their own instructions. Access tools outside their category. Override guardrails. |
| **SysAdmin** | Fleet oversight, lifecycle management, self-improvement coordination, circuit breaker monitoring. | Trade. Modify risk parameters. Access raw API tokens. |
| **Category Agents** | Trade within their assigned category using TraderBot tools. Log learnings. Design experiments via sub-agents. | Access other categories' data. Modify their own profiles. Bypass risk limits. |

This division is enforced at the architecture level — not just by workspace instructions. The MCP server enforces category access control (DD-011). Risk limits are immutable (DD-031). Agents never see API tokens (DD-037).

---

## 2. TraderBot Is a Toolkit, Not a Trader

TraderBot produces *interpretive statistical outputs*, not directional trading calls. The old signal engine (`generate_signal()` returning "yes"/"no"/"neutral") has been retired (DD-035). In its place, each category gets a custom analysis toolkit that provides structured analytical data. The agent receives:

- Calibrated probability estimates with confidence intervals
- Historical accuracy metrics by source, city, and lead time
- Market-implied edge and liquidity data
- Seasonal context and anomaly detection
- Assembled decision briefs combining all analytical outputs

The agent *decides* what to do with this information. TraderBot's job is to ensure the data is accurate, timely, and statistically sound — not to tell the agent which direction to bet.

---

## 3. Full Autonomy

TraderBot is designed to be fully autonomous in operation, development, and self-learning:

- **Operational autonomy**: TraderBot runs as an always-on service (DD-016). Data collection, WebSocket streams, health checks, and cron management run without human intervention.
- **Development autonomy**: SysAdmin can file GitHub issues for code-level improvements. The autonomous dev team (Layer 3, DD-018) picks up issues, investigates, and deploys fixes.
- **Self-learning autonomy**: The three-layer self-improvement architecture (DD-018) enables continuous improvement without human approval for each cycle.

Agents never stop and wait for human permission. They operate with clear guidelines, checks and balances, and a chain of command to validate each other's decisions (DD-038).

---

## 4. One Concept Per Improvement Cycle

Each improvement cycle targets exactly one concept to modify, replace, or add. A "concept" can be open-ended — "implement ML models to improve weather analysis" is one concept, but it may apply differently across pipeline layers. The point is one design decision at a time, measured and validated before moving on (DD-038).

---

## 5. Statistical Rigor as Foundational Philosophy

Every analysis output, calibration, and decision framework is grounded in principles of statistical analysis:

- Base every decision, calculation, and data derivation in statistical principles.
- Create hypotheses. Design tests to validate them.
- Build models to measure correlation and causation. Track trends.
- Keep detailed, complete historical records — good and bad.
- Never take data at face value — interpret from a statistical-science perspective, considering margin of error, forecast accuracy, and what the numbers mean in real Kalshi market conditions.
- Kalshi market specificity: the goal is better performance on Kalshi markets specifically, not general prediction improvement (DD-038).

---

## 6. Category Isolation

Each category agent operates in isolation from other categories:

- **Data isolation**: Each agent can only access data sources and trade history relevant to its category (DD-011).
- **Tool isolation**: MCP tools are namespaced by category. Each agent only receives its category's toolkit via OpenClaw `alsoAllow` filtering (DD-025, DD-035).
- **Database isolation**: Per-agent per-mode SQLite databases. No cross-category data access (DD-032).
- **Container isolation**: Mandatory Docker sandbox for all category agents (DD-010).
- **Credential isolation**: Per-agent bind mounts, scoped profile tokens, Infisical namespaced secrets (DD-037).

SysAdmin has access to all categories (via `enabled_categories: []`), but is explicitly denied trading tools (DD-036).

---

## 7. WebSocket-First Data Architecture

The Kalshi WebSocket is the sole source for all real-time Kalshi data. REST API is used only for:
1. Seeding the cache on startup when WebSocket is not yet connected
2. Recovering from WebSocket disconnections
3. Fetching historical data (settled markets, candlesticks)

Any REST call for data that the WebSocket already provides is a bug (DD-016).

---

## 8. Prebuilt Agents, No Customization

Agents are shipped prebuilt with immutable workspace files (DD-008). Users cannot modify core agent files (AGENTS.md, TOOLS.md, SOUL.md, IDENTITY.md). This minimizes variability and user error, and enables us to fine-tune agent behavior across the fleet.

---

## 9. Profile-Aware, Mode-Aware Tooling

MCP tools are profile-aware and mode-aware. The same tool call returns different data depending on the agent's mode (backtesting, paper, live). The agent never needs to track its mode or use different commands — the MCP server routes on the backend based on the agent's profile (DD-019, DD-021).

---

## 10. SysAdmin Manages Lifecycle Transitions

Phase transitions (backtest → paper → live → suspended) are driven by SysAdmin, not automated. SysAdmin follows a predefined activation protocol but can deviate when circumstances require. Cron/heartbeat jobs are not registered at deploy time — SysAdmin activates them phase by phase (DD-023).

---

## 11. Minimum Footprint, Maximum Respect

- TraderBot installs only the required dependencies and modules for the user's OS and enabled categories (DD-001, DD-009).
- The installer shows relevant messages for the detected OS. No keyring questions on headless Linux (DD-006).
- Data collection begins for all sources at install time (for backtesting availability), but only enabled categories have active trading agents (DD-027).
- Kalshi WebSocket minimizes REST API calls and respects rate limits (DD-016).

---

## 12. OpenClaw Is Not a Trust Boundary

OpenClaw is the agent runtime, not a security boundary. Authentication and access control are enforced by TraderBot's MCP server, not by OpenClaw. Secrets are stored in Infisical (not in OpenClaw's config). Profile tokens are validated by the MCP server on every tool call (DD-025). The division is: OpenClaw manages agent lifecycle and LLM orchestration; TraderBot manages data, security, and enforcement.

---

## 13. Idempotency and Safety

All setup, deploy, and registration operations must be idempotent (AGENTS.md). Before creating a resource, check if it exists. Use `--replace` semantics for cron job registration. Every resource must have a corresponding cleanup path in uninstall.

---

## 14. Cross-Platform Compatibility

TraderBot supports macOS, Windows, and Linux (including headless). The user flow is identical across all three: `pipx install traderbot` → `traderbot deploy`. OS-specific behavior is detected automatically and adjusted (DD-006). Service templates use `shutil.which('traderbot')` for path resolution (DD-007). Infisical runs on all platforms including headless Linux (DD-037).
