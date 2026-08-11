# Kalshi Historical Data

TraderBot keeps the Kalshi WebSocket as the only real-time market source. The REST methods below exist for startup/recovery metadata and deterministic historical backfill.

## Typed REST Methods

| Method | Official path | Authentication | Return type |
|---|---|---|---|
| `get_series(category)` | `GET /series?category=...` | Public | `SeriesListResponse` |
| `get_markets(...)` | `GET /markets` | Public | `MarketListResponse` with explicit cursor |
| `get_candlesticks(...)` | `GET /series/{series_ticker}/markets/{ticker}/candlesticks` | Public | `LiveCandlestickResponse` |
| `get_historical_candlesticks(...)` | `GET /historical/markets/{ticker}/candlesticks` | Public | `HistoricalCandlestickResponse` |
| `get_forecast_percentile_history(...)` | `GET /series/{series_ticker}/events/{event_ticker}/forecast_percentile_history` | Signed | `ForecastHistoryResponse` |

`get_markets` returns one page and its cursor; callers decide when to request the next page. It exposes only the official status, limit, cursor, event, series, and supported timestamp filters. Empty optional values are omitted.

Ticker path values are checked before interpolation. Empty values, separators, query fragments, control characters, and traversal syntax do not reach transport.

## Wire Precision

`FixedPointDollars` and `FixedPointCount` remain strings through validation and persistence. Dollar strings accept the official OpenAPI maximum of six decimal places; response count strings require two decimal places. The client does not parse either through `float`.

Live candles use `open_dollars`, `volume_fp`, and related current field names. Archived candles use legacy `open`, `volume`, and related names. They have separate response models and are normalized only when Task 8 writes them with an explicit `live` or `historical` source.

Forecast raw and normalized numerical values use `Decimal` in Python and TEXT in SQLite, preserving decimal values for Task 8 persistence.

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
- <https://docs.kalshi.com/api-reference/market/get-market-candlesticks>
- <https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks>
- <https://docs.kalshi.com/api-reference/events/get-event-forecast-percentile-history>
- <https://docs.kalshi.com/getting_started/fixed_point_migration>
- <https://docs.kalshi.com/getting_started/quick_start_authenticated_requests>
