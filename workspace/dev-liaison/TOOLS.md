# TraderBot Tools — Dev-Liaison Agent

When calling any TraderBot tool, always include your profile token as the `token` parameter. Your token is available as the TRADERBOT_PROFILE_TOKEN environment variable.

## Currently Available Tools

### `traderbot__health`

Combined health check: service, WebSocket, data, auth, circuit breakers.

**Parameters**: `token` (str)

### `traderbot__auth_check`

Verify all API credentials are valid.

**Parameters**: `token` (str)

### `traderbot__profile_list`

List all profiles and their modes.

**Parameters**: `token` (str)

### `traderbot__market_edge`

Compute the estimated edge for a market.

**Parameters**: `token` (str), `category` (str), `ticker` (str)

## Planned Tools (not yet available)

The following tools are planned for future phases and are not yet implemented:

- `traderbot__reference` — Knowledge retrieval (searches indexed source code, docs, and design decisions)
- `traderbot__experiment` — Experiment harness tools (create, run, verify treatments)
- `sessions_spawn` — Spawn sub-agents for debate coordination
- `sessions_send` — Send messages to agents
- `sessions_yield` — Wait for sub-agent results
- `sessions_list` — List sessions
- `sessions_history` — Read session transcripts
- `subagents` — List spawned sub-agent status
