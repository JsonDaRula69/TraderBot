# ADR-027: All data sources collect at install time

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-027
**Tags:** data, backfill, installation, pipeline

## Context

Originally, data backfill was filtered by enabled categories. This meant backtesting for a future category required enabling it first.

## Decision

All data sources begin collection at install time, regardless of which categories are enabled. This ensures backfill data is available when a new category is activated later.

## Consequences

- Backfill runs for all data sources, not just enabled categories
- Data is stored but only active category agents access it
- Enables future category activation without waiting for backfill
- Install time is longer but future category onboarding is instant

## Notes for AutoDev Agents

This affects the `traderbot deploy` flow (DD-009, step 6). The backfill step must process all data sources, not just the enabled ones. The data pipeline must handle multiple concurrent source collections.
