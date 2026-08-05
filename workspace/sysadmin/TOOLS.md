# TraderBot Tools — SysAdmin Agent

Your profile `token` is injected host-side by the TraderBot Token Injector plugin. The `token` parameter remains in the tool schema (required by the MCP SDK), but you do not need to provide it yourself.

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

### `traderbot__market_prices`

Return current market prices from the live WebSocket cache.

**Parameters**: `token` (str), `ticker` (str), `resolution` (str, optional: `1min`/`1hr`/`1day`)

## Planned Tools (not yet available)

The following tools are planned for future phases and are not yet implemented:

- `traderbot__profile_update` — Update profile mode (backtest → paper → live), risk parameters
- `traderbot__performance` — View any agent's performance metrics
- `traderbot__audit` — View any agent's audit trail
- `traderbot__learnings` — View and manage learnings across all agents
- `traderbot__cron_setup` — Manage cron job templates
- `traderbot__session_send` — Send messages to agents
- `traderbot__experiment` — Design and run experiments
- `traderbot__data_status` — Check data freshness per category
- `traderbot__ws_status` — Check WebSocket connection status
- `traderbot__backfill` — Trigger data backfill
- `traderbot__reference` — Access TraderBot documentation and code
