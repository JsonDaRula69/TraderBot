# TraderBot v2 — MCP Tools Reference

> This document provides a complete reference for all MCP tools exposed by TraderBot's MCP server, including category-specific toolkits, SysAdmin tools, and the token-based authentication mechanism. Grounded in DD-015, DD-025, DD-035, DD-036.

> **Implementation status:** the current Phase 1 development server exposes
> only `health`, `auth_check`, `profile_list`, and `market_edge`. Later sections
> describe the planned tool surface and are not claims of implementation,
> deployment, CI, or on-target verification. Per-agent token injection is
> architecturally resolved in issue #187; the plugin hook is not yet implemented.
> Issue #164 remains open until macpro-linux testing succeeds.

---

## MCP Server Architecture

A Phase 1 configuration remediation registers TraderBot once at root scope:

```json
{
  "mcp": {
    "servers": {
      "traderbot": {
        "command": "traderbot-mcp-server",
        "transport": "stdio"
      }
    }
  }
}
```

The agent fragments in `configs/openclaw/` remove the legacy unsupported per-agent `env` and nested `mcp` fields. The example above describes the checked-in remediation.

The MCP server uses `TRADERBOT_USE_HARDCODED_AUTH` env var to select auth mode.
Default (any value other than "0") uses hardcoded Phase 0 tokens.
`TRADERBOT_USE_HARDCODED_AUTH=0` enables real auth via `TokenStore` (Phase 1) or
Infisical (Phase 1.5).

All tools accept a `token` parameter for authentication and identity
resolution. The MCP server resolves `token → profile`, checks the tool
permission, then checks the category for category-bearing tools. The profile
also supplies mode and access context.

---

## Authentication Flow

```
Agent calls traderbot__weather_forecast_prob(token, ticker, ...)
  │
  ▼
MCP Server receives tool call
  │
  ▼
resolve_token(token) → (profile_name, agent_id)
  │
  ├── Invalid/expired token → return {"error": "Invalid or expired profile token"}
  │
  ▼
Load profile → permissions, enabled_categories, mode
  │
  ├── Tool not in permissions → return {"error": "Permission denied"}
  │
  ▼
Validate category for category-bearing tools
  │
  ├── Unknown category → return {"error": "Unknown category"}
  ├── Category not in enabled_categories → return {"error": "Category not enabled"}
  │
  ▼
Execute current handler (future handlers add mode-aware routing)
  │
  ▼
Return result

> **Token injection (Phase 1.5):** The `token` parameter on all `traderbot__*`
> tools is injected host-side by an OpenClaw `before_tool_call` plugin hook, not
> provided by the model. The `token` field MUST be declared in each tool's
> `inputSchema` or the MCP SDK silently strips it before dispatch. See
> `04-security-and-auth.md` for the full architecture and critical constraints.
```

---

The enforced order is **token → tool permission → category**. Tools without a
category skip the final check.

## Current Phase 1 Tools

| Tool | Actual current behavior |
|---|---|
| `traderbot__health` | Authenticates the caller and reports profile context plus placeholder component states. |
| `traderbot__auth_check` | Validates the profile token and `auth_check` permission, then reports profile, agent, mode, enabled categories, and permissions. It does **not** validate external provider credentials. |
| `traderbot__profile_list` | Authenticates and authorizes the caller, then lists the in-process profile registry. |
| `traderbot__market_edge` | Authenticates, checks `market_edge` permission, enforces DD-011 category access, validates strict input, and returns a stub response. |

External API credential validation is deferred to the secrets, provider, and
deploy phases. Infisical and automatic rotation remain Phase 1.5 plans.

## Planned Tool Surface

Unless explicitly described as current above, the tools and rich responses in
the following sections are target designs.

### `traderbot__market_edge` (current stub, planned full response)

The current implementation returns a placeholder while preserving auth,
permission, category, and input-validation behavior. Its response is:

```json
{
  "status": "stub",
  "message": "market_edge not yet implemented (Phase 0 skeleton)",
  "category": "weather",
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "edge_pct": 0.0,
  "confidence": 0.0,
  "sample_size": 0
}
```

The target implementation will return market-implied probability, spread,
liquidity, and edge assessment for a ticker.

**Parameters**: `token` (str), `category` (str), `ticker` (str)

`category` enables per-agent access control per DD-011 (market edge is only computed for the caller's enabled categories).

**Response**:
```json
{
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "market_implied_prob": 0.38,
  "bid": 37,
  "ask": 39,
  "spread": 2,
  "volume": 15234,
  "open_interest": 45678,
  "estimated_edge": 0.30,
  "liquidity_rating": "high",
  "mode": "paper"
}
```

**Planned mode behavior**: Backtest returns market edge at sim-time. Paper/Live returns current data from WebSocket cache.

---

### `traderbot__market_prices`

Returns current and historical price data from Kalshi WebSocket/cache.

**Parameters**: `token` (str), `ticker` (str), `resolution` (str, optional: "1min", "1hr", "1day")

**Response**:
```json
{
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "current_price": 38,
  "prices": [
    {"timestamp": "2026-06-15T10:00:00Z", "open": 36, "high": 39, "low": 35, "close": 38, "volume": 1200},
    ...
  ],
  "mode": "paper"
}
```

**Mode behavior**: Backtest returns prices at sim-time. Paper/Live returns current data.

---

### `traderbot__trade`

Execute a trade (mode-aware routing).

**Parameters**: `token` (str), `ticker` (str), `direction` (str: "yes"/"no"), `quantity` (int), `price` (int, cents)

**Mode behavior**:
- **Backtest**: Record in backtest DB, return simulated fill at sim-time price
- **Paper**: Record in paper DB, return simulated fill with slippage model
- **Live**: Submit to Kalshi API, record in live DB, return fill confirmation

**Response** (same format regardless of mode):
```json
{
  "status": "filled",
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "direction": "yes",
  "quantity": 5,
  "fill_price_cents": 34,
  "slippage_cents": 1,
  "estimated_prob": 0.38,
  "confidence": 0.72,
  "remaining_balance_cents": 9830,
  "mode": "paper"
}
```

---

### `traderbot__positions`

Get current positions for the agent's profile and mode.

**Parameters**: `token` (str), `ticker` (str, optional), `status` (str, optional: "open"/"closed"/"settled")

**Mode behavior**: Returns positions from the agent's current mode database.

---

### `traderbot__heartbeat`

Get heartbeat data — health, status, and recent activity summary.

**Parameters**: `token` (str)

---

### `traderbot__performance`

Get performance metrics (P&L, Sharpe, win rate, drawdown, etc.).

**Parameters**: `token` (str), `from` (str, optional date), `to` (str, optional date)

---

### `traderbot__audit`

Get audit trail — all decisions with full reasoning for a time range.

**Parameters**: `token` (str), `from` (str), `to` (str)

---

### `traderbot__learnings`

Get or update learnings for this agent's category.

**Parameters**: `token` (str), `action` (str: "list"/"add"/"update"), `data` (dict, optional)

---

### `traderbot__news_context`

Get relevant news context for a category.

**Parameters**: `token` (str), `category` (str), `query` (str, optional), `limit` (int, default 10)

---

### `traderbot__data_points`

Get quantitative data points for a category.

**Parameters**: `token` (str), `category` (str), `metric` (str, optional), `from` (str, optional), `to` (str, optional)

---

## Weather Toolkit

The planned weather toolkit is restricted through the weather agent's explicit
OpenClaw `allow` policy and TraderBot's server-side authorization.

### `traderbot__weather_forecast_prob`

Calibrated probability estimate with confidence interval. Replaces the hardcoded logistic function.

**Parameters**: `token` (str), `ticker` (str), `snapshot_date` (str, optional, defaults to now)

**Response**:
```json
{
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "city": "Chicago",
  "target_date": "2026-06-02",
  "lead_time_days": 4,
  "forecast_temp_f": 83.2,
  "strike_type": "less",
  "threshold": 81,
  "estimated_prob": 0.68,
  "confidence_interval": {"low": 0.52, "high": 0.82},
  "calibration_score": 0.74,
  "sources": [
    {"source": "nws", "forecast_f": 84.0, "weight": 0.4},
    {"source": "gfs", "forecast_f": 82.5, "weight": 0.3},
    {"source": "ecmwf", "forecast_f": 83.0, "weight": 0.3}
  ],
  "model_consensus": {
    "mean_temp_f": 83.2,
    "std_dev_f": 1.8,
    "spread_f": 4.0,
    "agreement_score": 0.85,
    "models_used": ["nws", "gfs", "ecmwf"]
  },
  "method": "calibrated_logistic",
  "note": "Probability calibrated against historical accuracy for this city/month/lead_time combination"
}
```

**Key improvements over old signal engine**:
- City-month-specific σ values from historical distributions (no hardcoded sigma=5.0)
- Calibration curves from Brier score decomposition
- Lead-time decay: probability estimates widen as lead time increases
- Multi-source model consensus with agreement scores

### `traderbot__weather_accuracy`

Historical forecast accuracy by source, city, and lead time.

**Parameters**: `token` (str), `city` (str), `source` (str, optional), `lead_time_days` (int, optional), `lookback_days` (int, default 90)

**Response**:
```json
{
  "city": "Chicago",
  "source": "all",
  "lookback_days": 90,
  "sample_size": 87,
  "brier_score": 0.142,
  "calibration_error": 0.068,
  "mean_error_f": 1.3,
  "mean_abs_error_f": 3.1,
  "std_error_f": 4.2,
  "by_lead_time": {
    "0": {"brier_score": 0.08, "mean_abs_error_f": 1.8, "sample_size": 87},
    "1": {"brier_score": 0.12, "mean_abs_error_f": 2.4, "sample_size": 85},
    "2": {"brier_score": 0.19, "mean_abs_error_f": 3.5, "sample_size": 82},
    "3": {"brier_score": 0.24, "mean_abs_error_f": 4.1, "sample_size": 78},
    "4": {"brier_score": 0.31, "mean_abs_error_f": 5.1, "sample_size": 72}
  },
  "recent_trend": "improving",
  "note": "Brier scores below 0.25 indicate useful forecasts; below 0.15 indicates strong forecasts"
}
```

### `traderbot__weather_seasonal_context`

Historical temperature distributions and recent anomalies.

**Parameters**: `token` (str), `city` (str), `target_date` (str, optional)

**Response**:
```json
{
  "city": "Chicago",
  "month": "June",
  "historical_distribution": {
    "mean_high_f": 82.3,
    "std_dev_f": 6.8,
    "percentile_10": 72.0,
    "percentile_25": 77.0,
    "percentile_50": 82.0,
    "percentile_75": 87.0,
    "percentile_90": 92.0,
    "sample_size": 30
  },
  "recent_anomaly": {
    "last_7_days_mean_f": 79.5,
    "departure_from_normal_f": -2.8,
    "trend": "cooling",
    "trend_days": 3
  },
  "climate_patterns": {
    "enso_status": "neutral",
    "enso_impact": "minimal predictable effect on Chicago June temperatures"
  },
  "note": "Chicago June highs have σ≈6.8°F. A threshold of 81°F is near the median — roughly even odds without any forecast information."
}
```

### `traderbot__weather_decision_brief`

Assembled analytical brief combining forecast probability, accuracy, market edge, and seasonal context. This is the primary tool the weather agent calls during its trading cycle.

**Parameters**: `token` (str), `ticker` (str)

**Response**: Combined analytical brief with all weather tool outputs plus market edge. No directional call — the agent decides.

---

## SysAdmin Tools

SysAdmin has a restricted toolset focused on oversight and management, with no trading tools:

### Management Tools

| Tool | Purpose |
|---|---|
| `traderbot__health` | Combined health check: service, WS, data, auth, circuit breakers |
| `traderbot__auth_check` | Validate the profile token and report its access context; does not validate provider credentials |
| `traderbot__profile_list` | List all profiles and their modes |
| `traderbot__profile_update` | Update profile mode (backtest → paper → live), risk parameters |
| `traderbot__performance` | View any agent's performance metrics |
| `traderbot__audit` | View any agent's audit trail |
| `traderbot__learnings` | View and manage learnings across all agents |
| `traderbot__cron_setup` | Manage cron job templates |
| `traderbot__session_send` | Send messages to agents |
| `traderbot__experiment` | Design and run experiments |
| `traderbot__data_status` | Check data freshness per category |
| `traderbot__ws_status` | Check WebSocket connection status |
| `traderbot__backfill` | Trigger data backfill |
| `traderbot__reference` | Access TraderBot documentation and code |

### Explicitly Denied

| Tool | Reason |
|---|---|
| `traderbot__trade` | SysAdmin does not trade |
| `traderbot__scan` | No category scanning |
| `traderbot__analyze` | No category analysis |
| `traderbot__weather_*` | No category-specific tools |
| `traderbot__market_edge` | No market edge access |
| `traderbot__market_prices` | No market price access |

## Dev-Liaison Tools

The Dev-Liaison agent has a focused toolset for architecture expertise, experiment management, and AutoDev coordination:

| Tool | Purpose |
|---|---|
| `traderbot__reference` | Knowledge retrieval (searches indexed source code, docs, and design decisions) |
| `traderbot__experiment` | Experiment harness tools (create, run, verify treatments) |
| `traderbot__auth_check` | Profile-token validation and access-context reporting |
| `traderbot__health` | System health checks |
| `sessions_spawn` | Spawn sub-agents for debate coordination |
| `sessions_send` | Send messages to agents |
| `sessions_yield` | Wait for sub-agent results |
| `sessions_list` | List sessions |
| `sessions_history` | Read session transcripts |
| `subagents` | List spawned sub-agent status |

### Dev-Liaison Explicitly Denied

| Tool | Reason |
|---|---|
| `traderbot__trade` | Dev-Liaison does not trade |
| `traderbot__scan` | No market scanning |
| `traderbot__analyze` | No market analysis |
| `traderbot__weather_*` | No category-specific tools |
| `traderbot__market_edge` | No market edge access |
| `traderbot__market_prices` | No market price access |

### AutoDev Webhook Integration

The Dev-Liaison receives webhook notifications from AutoDev through OpenClaw's webhook server. Three webhook paths are configured:

| Path | Event | Dev-Liaison Action |
|---|---|---|
| `/hooks/autodev-completed` | AutoDev finished work | Verify on GitHub, notify requesting TraderBot agent |
| `/hooks/autodev-blocked` | AutoDev needs human input | Escalate to operator immediately |
| `/hooks/autodev-deployed` | AutoDev deployed a change | Ask relevant TraderBot agent to validate health |

The Dev-Liaison sends wake signals to AutoDev via a shared Discord channel: `autodev:wake` (new work), `autodev:cancel` (work no longer needed), `autodev:priority` (critical bug).

---

## OpenClaw Tool Configuration Status

The separate configuration remediation is split into one gateway artifact and strict agent fragments. The `configs/openclaw/gateway.json` registers the stdio MCP server once at root `mcp.servers`; its agent entries contain only `id`, `sandbox`, and `tools`. The pinned OpenClaw schema rejects per-agent `env`, nested `mcp`, and annotation fields.

Remediation weather policy excerpt:

```json5
{
  id: "weather",
  sandbox: { mode: "all" },  // Mandatory Docker sandbox (DD-010)
  tools: {
    allow: [
      // Weather toolkit
      "traderbot__weather_forecast_prob",
      "traderbot__weather_accuracy",
      "traderbot__weather_seasonal_context",
      "traderbot__weather_decision_brief",
      // General tools
      "traderbot__health",
      "traderbot__auth_check",
      "traderbot__profile_list",
      "traderbot__market_edge",
      "traderbot__market_prices",
      "traderbot__trade",
      "traderbot__positions",
      "traderbot__heartbeat",
      "traderbot__performance",
      "traderbot__audit",
      "traderbot__learnings",
      "traderbot__news_context",
      "traderbot__data_points",
      // Session tools (for debate subs)
      "sessions_send",
    ],
    deny: ["group:runtime", "group:fs"],
    sandbox: {
      tools: { allow: ["bundle-mcp", "sessions_send"] },
    },
  }
}
```

The normal policy uses `allow`, not `alsoAllow`, because `alsoAllow` is
additive to an implicit wildcard in OpenClaw. `bundle-mcp` appears only in the
sandbox gate; exact `traderbot__*` names are used in the normal agent allowlist.
TraderBot then validates `token → tool permission → category` server-side.

The remediation fragments do **not** inject `TRADERBOT_PROFILE_TOKEN`. Root
`env.vars` is global and `mcp.servers.*.env` applies to the shared MCP process,
so neither the legacy nor remediation config can securely deliver distinct
agent tokens. Secure per-agent token injection will be implemented with a Phase
1.5 OpenClaw `before_tool_call` plugin hook that resolves per-agent Vault
SecretRefs and rewrites tool call params (see `04-security-and-auth.md`). That
plugin is not yet in `HEAD`; neither config state is deployable until the hook
is implemented and tested on macpro-linux.
