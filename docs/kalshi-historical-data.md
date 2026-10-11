# Kalshi Historical Data

TraderBot keeps the Kalshi WebSocket as the only real-time market source. The REST methods below exist for startup/recovery metadata and deterministic historical backfill.

## Typed REST Methods

| Method | Official path | Authentication | Return type |
|---|---|---|---|
| `get_series(category)` | `GET /series?category=...` | Public | `SeriesListResponse` |
| `get_markets(...)` | `GET /markets` | Public | `MarketListResponse` with explicit cursor |
| `get_historical_cutoff()` | `GET /historical/cutoff` | Public | `CutoffTimestamps` |
| `get_historical_markets(...)` | `GET /historical/markets` | Public | `MarketListResponse` with explicit cursor |
| `get_candlesticks(...)` | `GET /series/{series_ticker}/markets/{ticker}/candlesticks` | Public | `LiveCandlestickResponse` |
| `get_historical_candlesticks(...)` | `GET /historical/markets/{ticker}/candlesticks` | Public | `HistoricalCandlestickResponse` |
| `get_forecast_percentile_history(...)` | `GET /series/{series_ticker}/events/{event_ticker}/forecast_percentile_history` | Signed | `ForecastHistoryResponse` |

Both market-list methods return one page and its cursor; callers decide when to request the next page. The live method exposes only the official status, limit, cursor, event, series, and supported timestamp filters. The archive method exposes limit/cursor and at most one official ticker, event, series, or MVE selector; it has no status, category, or settled-time query.

`get_series` returns the official required `series` array. Production additionally emits HTTP 200 `{"series": null}` for an empty or unmatched category query (re-verified 2026-10-03); the typed boundary normalizes only that observed null value to an empty list, while a missing `series` key still fails validation.

Ticker path values are checked before interpolation. Empty values, separators, query fragments, control characters, and traversal syntax do not reach transport.

## Wire Precision

`FixedPointDollars` and `FixedPointCount` remain strings through validation and persistence. Dollar strings accept the official OpenAPI maximum of six decimal places; response count strings require two decimal places. The client does not parse either through `float`.

Live candles use `open_dollars`, `volume_fp`, and related current field names. Archived candles use legacy `open`, `volume`, and related names. They have separate response models and the backfill writer normalizes them with an explicit `live` or `historical` source.

Forecast raw and normalized numerical values use `Decimal` in Python and TEXT in SQLite, preserving their lexical decimal values during persistence.

## Backfill Command

`traderbot backfill --months 6 --json` computes one aware UTC calendar-month window and fetches one runtime historical cutoff. Weather series are discovered once. Settled markets at or after the cutoff come from live `/markets`; earlier markets come from `/historical/markets` and are bounded client-side. Markets merge by ticker, candles use the matching tier, and forecast percentiles are fetched once per unique series/event pair.

The optional collector import opens `~/.data-collector/collector.db` read-only. A missing default is a warning, while an explicit invalid path exits 2 before target or Kalshi writes. All three source schemas are preflighted in one pinned snapshot. Rows copy in deterministic 1,000-row transactions with `INSERT OR IGNORE`, so interrupted and repeated runs converge without deleting prior data.

JSON mode writes exactly one typed result line to stdout. Human Rich output and progress use stderr. Exit 0 means complete, exit 1 means partial or runtime failure, and exit 2 means invalid input.

## Global Migration V2

Migration v2 appends:

- `weather_observations`, matching the collector import columns and `(date, city, variable)` identity.
- `kalshi_markets`, keyed by ticker and indexed by event, series, category/status, and status/close timestamp.
- `kalshi_candlesticks`, keyed by `(ticker, period_interval, end_period_ts, source)`.
- `kalshi_forecast_history`, keyed by event, series, period timestamp, interval, and percentile.

Rollback removes only these four tables and their indexes. Migration v1 remains unchanged and irreversible.

## Official Sources

Contracts were verified on 2026-08-11 against:

- <https://docs.kalshi.com/api-reference/market/get-series-list>
- <https://docs.kalshi.com/api-reference/market/get-markets>
- <https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps>
- <https://docs.kalshi.com/api-reference/historical/get-historical-markets>
- <https://docs.kalshi.com/api-reference/market/get-market-candlesticks>
- <https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks>
- <https://docs.kalshi.com/api-reference/events/get-event-forecast-percentile-history>
- <https://docs.kalshi.com/getting_started/fixed_point_migration>
- <https://docs.kalshi.com/getting_started/quick_start_authenticated_requests>
