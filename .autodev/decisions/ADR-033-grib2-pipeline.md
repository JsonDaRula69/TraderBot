# ADR-033: GRIB2 processing pipeline for historical weather data

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-033
**Tags:** data, weather, grb2, backtesting, pipeline

## Context

Tier 2 historical weather data (multi-day lead time forecasts from GFS/ECMWF) requires processing GRIB2 files, which are binary meteorological data formats.

## Decision

Two-phase GRIB2 processing:
- Phase 1: Day-0 forecasts (NWS forecast data, already available via Tier 1)
- Phase 2: Multi-day lead time forecasts (GFS/ECMWF GRIB2 processing)

## Consequences

- Phase 1 is available immediately for backtesting
- Phase 2 requires GRIB2 parsing library and processing pipeline
- Weather agent backtesting can start with Phase 1 data
- Phase 2 adds multi-day forecast capability for improved backtesting

## Notes for AutoDev Agents

Phase 2 implementation is pending. When implementing, use a GRIB2 parsing library (e.g., pygrib or cfgrib) to process GFS/ECMWF files. The processing pipeline follows the same pattern as other data providers in the unified `data/` module (DD-028).
