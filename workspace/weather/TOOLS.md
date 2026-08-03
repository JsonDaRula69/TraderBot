# TraderBot Tools — Weather Agent

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

- `traderbot__weather_forecast_prob` — Calibrated probability estimate with confidence interval
- `traderbot__weather_accuracy` — Historical forecast accuracy by source, city, and lead time
- `traderbot__weather_seasonal_context` — Historical temperature distributions and recent anomalies
- `traderbot__weather_decision_brief` — Assembled analytical brief combining forecast probability, accuracy, market edge, and seasonal context
- `traderbot__market_prices` — Current and historical price data from Kalshi WebSocket/cache
- `traderbot__trade` — Execute a trade (mode-aware routing)
- `traderbot__positions` — Get current positions for the agent's profile and mode
- `traderbot__heartbeat` — Get heartbeat data — health, status, and recent activity summary
- `traderbot__performance` — Get performance metrics (P&L, Sharpe, win rate, drawdown, etc.)
- `traderbot__audit` — Get audit trail — all decisions with full reasoning for a time range
- `traderbot__learnings` — Get or update learnings for this agent's category
- `traderbot__news_context` — Get relevant news context for a category
- `traderbot__data_points` — Get quantitative data points for a category
