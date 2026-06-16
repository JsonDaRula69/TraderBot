# ADR-020: Historical data sources for backtesting

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-020
**Tags:** backtesting, data, historical, weather

## Context

Backtesting needs historical data. Different data sources have different availability and quality levels.

## Decision

Three tiers of historical data:
- **Tier 1 (day-0 forecasts)**: NWS forecasts valid on the day they were issued, available immediately
- **Tier 2 (GRIB2 pipeline)**: Multi-day lead time forecasts from GFS/ECMWF, processed via the GRIB2 pipeline (DD-033)
- **Tier 3 (Kalshi market archive)**: Historical market data from Kalshi, available via REST API

## Consequences

- Weather agent backtesting starts with Tier 1 data
- GRIB2 processing adds multi-day forecast capability (DD-033)
- Kalshi market archive provides ground truth for all categories
- All data sources begin collection at install time (DD-027)

## Notes for AutoDev Agents

Tier 1 data is available from day one. Tier 2 (GRIB2) requires the processing pipeline to be implemented (DD-033). Tier 3 (Kalshi archive) requires REST API access. The simulation engine (DD-019) must be able to select which tier of data to use for a given backtesting run.
