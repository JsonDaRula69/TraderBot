# Experiment Database Seed Format

This document describes the actual schema of `experiments/experiment_data.db` for developers implementing the methodology framework. **The database already exists and is fully populated** — this document is for reference only.

## Overview

| Table | Rows | Purpose |
|-------|------|---------|
| markets | 25 | Kalshi weather market definitions |
| forecast_snapshots | 250 | Synthesized daily weather forecasts per market |
| market_prices | 250 | YES/NO prices at each timestep per market |
| settlement_actuals | 25 | Historical weather observations (evaluation-only) |
| calibration_bins | 0 | Methodology calibration buckets (populated by runner) |
| agent_decisions | 0 | Agent trading decisions (populated by runner) |
| methodology_outputs | 0 | Methodology probability estimates (populated by runner) |

## Ticker Format

```
KXHIGH{CITY_PREFIX}-{DDMMMYY}-B{THRESHOLD}
```

Example: `KXHIGHAUS-26MAY16-B95.5` = "Will Austin's high temp on May 16, 2026 be 95.5–96.5°F?"

## City Prefix Mapping

| City | Prefix |
|------|--------|
| Atlanta | KXHIGHTATL |
| Austin | KXHIGHAUS |
| Boston | KXHIGHTBOS |
| Chicago | KXHIGHCHI |
| Dallas | KXHIGHTDAL |
| Denver | KXHIGHDEN |
| Houston | KXHIGHTHOU |
| Las Vegas | KXHIGHTLV |
| Los Angeles | KXHIGHLAX |
| Miami | KXHIGHMIA |
| New York | KXHIGHNY |
| Philadelphia | KXHIGHPHIL |
| Washington DC | KXHIGHTDC |

## Table Schemas

### markets

Core market definitions. `ticker` is the primary key.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| ticker | TEXT | PRIMARY KEY | e.g. `KXHIGHAUS-26MAY16-B95.5` |
| question | TEXT | NOT NULL | Human-readable question text |
| city | TEXT | NOT NULL | Full city name |
| city_prefix | TEXT | NOT NULL | Short prefix used in ticker |
| lat | REAL | NOT NULL | Latitude |
| lon | REAL | NOT NULL | Longitude |
| timezone | TEXT | NOT NULL | e.g. `America/Chicago` |
| resolution_date | TEXT | NOT NULL | Resolution date |
| close_time | TEXT | NOT NULL | ISO 8601 close time |
| settlement_result | TEXT | — | `yes` or `no` |
| actual_value | REAL | — | Observed value at resolution |
| strike_value | REAL | — | Lower bound of the band |
| strike_type | TEXT | — | Always `band` |
| market_type | TEXT | — | Always `band` |
| yes_price_dollars | REAL | — | Price in dollars (0.0–1.0), **not cents** |
| volume | REAL | — | Trading volume |
| open_interest | REAL | — | Open interest |
| event_ticker | TEXT | — | Kalshi event ticker |
| series_ticker | TEXT | — | Kalshi series ticker |

**Data characteristics:** 25 markets, all `strike_type=band`, 3 YES / 22 NO.

### forecast_snapshots

Daily weather forecasts. `source` is always `'synthesized'` (not live API data).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| ticker | TEXT | NOT NULL, FK → markets | Parent market |
| timestep | INTEGER | NOT NULL | 1–10 |
| forecast_date | TEXT | NOT NULL | Forecast made on |
| target_date | TEXT | NOT NULL | Forecast targets |
| temp_max_f | REAL | — | Forecasted high (°F) |
| temp_min_f | REAL | — | Forecasted low (°F) |
| precip_mm | REAL | — | Precipitation (mm) |
| wind_speed_max_kmh | REAL | — | Max wind (km/h) |
| humidity_max_pct | REAL | — | Max humidity (%) |
| weather_code | INTEGER | — | WMO code |
| source | TEXT | DEFAULT 'synthesized' | Always `'synthesized'` here |

**Data characteristics:** 250 rows = 25 markets × 10 timesteps. Forecast values vary across timesteps.

### market_prices

YES/NO contract prices at each timestep. Prices in dollars (0.0–1.0).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| ticker | TEXT | NOT NULL, FK → markets | Parent market |
| timestep | INTEGER | NOT NULL | 1–10 |
| yes_price | REAL | NOT NULL | Price in dollars |
| no_price | REAL | NOT NULL | Price in dollars |
| volume | REAL | — | Trading volume |
| open_interest | REAL | — | Open interest |

**Data characteristics:** 250 rows = 25 markets × 10 timesteps. `yes_price + no_price ≈ 1.0`.

### settlement_actuals

Historical weather observations. **Evaluation-only** — never exposed to agents during simulation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| ticker | TEXT | PRIMARY KEY, FK → markets | |
| actual_temp_max_f | REAL | — | Observed high (°F) |
| actual_temp_min_f | REAL | — | Observed low (°F) |
| actual_precip_mm | REAL | — | Observed precipitation (mm) |
| actual_weather_code | INTEGER | — | Observed WMO code |

**Data characteristics:** 25 rows, one per market.

### calibration_bins

Empty at seed time — populated by the methodology runner. When empty, `bin_cal` falls back to uniform prior.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| methodology | TEXT | NOT NULL | Methodology name |
| bin_label | TEXT | NOT NULL | e.g. "0.0-0.1" |
| bin_lower | REAL | NOT NULL | Lower bound |
| bin_upper | REAL | NOT NULL | Upper bound |
| count | INTEGER | NOT NULL DEFAULT 0 | Forecasts in bin |
| actual_rate | REAL | — | Empirical YES rate |
| created_at | TEXT | DEFAULT datetime('now') | |

**Constraints:** UNIQUE(methodology, bin_label). Currently 0 rows.

### agent_decisions

Empty at seed time — populated by the runner.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| ticker | TEXT | NOT NULL, FK → markets | |
| timestep | INTEGER | NOT NULL | 1–10 |
| methodology | TEXT | NOT NULL | Methodology used |
| decision | TEXT | NOT NULL | `buy_yes`, `buy_no`, or `hold` |
| estimated_prob | REAL | — | Estimated YES probability |
| confidence | REAL | — | Confidence score |
| edge_estimate | REAL | — | Edge vs market price |
| position_size_cents | INTEGER | — | In **cents**, not dollars |
| reasoning | TEXT | — | Free-form reasoning |
| created_at | TEXT | DEFAULT datetime('now') | |

### methodology_outputs

Empty at seed time — populated by the runner.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| ticker | TEXT | NOT NULL, FK → markets | |
| timestep | INTEGER | NOT NULL | 1–10 |
| methodology | TEXT | NOT NULL | Methodology name |
| estimated_prob | REAL | NOT NULL | Estimated YES probability |
| confidence | REAL | NOT NULL | Confidence score |
| reasoning_data | TEXT | — | JSON or free-form data |
| created_at | TEXT | DEFAULT datetime('now') | |

**Constraints:** UNIQUE(ticker, timestep, methodology).

## Key Relationships

```
markets.ticker
  ├─→ forecast_snapshots.ticker    (1:N, 10 rows)
  ├─→ market_prices.ticker          (1:N, 10 rows)
  ├─→ settlement_actuals.ticker      (1:1)
  ├─→ agent_decisions.ticker        (1:N, at runtime)
  └─→ methodology_outputs.ticker   (1:N, at runtime)
```

## Important Notes

1. **`ticker` is the primary key** — no integer `market_id`.
2. **Prices are in dollars** — 0.0–1.0, not cents.
3. **`settlement_actuals` is evaluation-only** — agents never see it during simulation.
4. **`source` is `'synthesized'`** — not live API data.
5. **`calibration_bins` is empty** at seed time — runner populates it.
6. **All markets are `band` type** — this dataset contains only band markets.
