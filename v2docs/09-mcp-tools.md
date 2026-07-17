# TraderBot v2 — MCP Tools Reference

> This document provides a complete reference for all MCP tools exposed by TraderBot's MCP server, including category-specific toolkits, SysAdmin tools, and the token-based authentication mechanism. Grounded in DD-015, DD-025, DD-035, DD-036.

---

## MCP Server Architecture

TraderBot registers as an MCP server with the OpenClaw gateway via stdio:

```bash
openclaw mcp add traderbot \
  --command traderbot-mcp-server \
  --env TRADERBOT_SECRETS_PATH="$HOME/.traderbot/secrets/secrets.json"
```

The MCP server reads `TRADERBOT_SECRETS_PATH` from its own environment to locate the secrets store (or Infisical connection config).

All tools accept a `token` parameter for authentication and identity resolution. The MCP server resolves `token → profile → categories + mode + permissions` on every call.

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
Load profile → enabled_categories, permissions, mode
  │
  ├── Category not in enabled_categories → return {"error": "Category not enabled"}
  ├── Tool not in permissions → return {"error": "Permission denied"}
  │
  ▼
Execute tool with mode-aware routing (backtest/paper/live)
  │
  ▼
Return result
```

---

## General-Purpose Tools (All Categories)

### `traderbot__market_edge`

Returns market-implied probability, spread, liquidity, and edge assessment for a ticker.

**Parameters**: `token` (str), `ticker` (str)

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

**Mode behavior**: Backtest returns market edge at sim-time. Paper/Live returns current data from WebSocket cache.

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

Available only to the weather agent via OpenClaw `alsoAllow` filtering.

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
| `traderbot__auth_check` | Verify all credentials are valid |
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
| `traderbot__auth_check` | Credential verification |
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

## OpenClaw Tool Configuration

Each category agent's OpenClaw configuration includes:

```json5
{
  id: "weather",
  sandbox: { mode: "all" },  // Mandatory Docker sandbox (DD-010)
  tools: {
    deny: ["group:runtime", "group:fs"],  // Block filesystem and runtime access
    alsoAllow: [
      "bundle-mcp",  // Required for MCP tool access
      // Weather toolkit
      "traderbot__weather_forecast_prob",
      "traderbot__weather_accuracy",
      "traderbot__weather_seasonal_context",
      "traderbot__weather_decision_brief",
      // General tools
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
  },
  env: {
    TRADERBOT_PROFILE_TOKEN: { secretRef: "traderbot_weather_token" }
  }
}
```

MCP server-side filtering (`alsoAllow` at the OpenClaw config level) and server-side validation (`resolve_token → profile → categories + permissions`) provide defense in depth. Even if an agent's TOOLS.md is modified, the MCP server will reject out-of-category tool calls.
