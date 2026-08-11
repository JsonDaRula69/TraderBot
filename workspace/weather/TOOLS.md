# TraderBot Tools — Weather Agent

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

Current stub: returns `status: stub` and does not compute market edge yet.

**Parameters**: `token` (str), `category` (str), `ticker` (str)

### `traderbot__market_prices`

Return current market prices from the live WebSocket cache.

**Parameters**: `token` (str), `ticker` (str), `resolution` (str, optional: `1min`/`1hr`/`1day`)

## Planned Tools

No planned tools are available through this workspace.
