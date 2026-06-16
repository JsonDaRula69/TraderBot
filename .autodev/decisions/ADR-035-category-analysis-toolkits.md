# ADR-035: Category-specific analysis toolkits — analysis, not trading signals

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-035
**Tags:** analysis, mcp, tools, categories, signals

## Context

The old `generate_signal()` approach produced directional trading calls ("yes"/"no"/"neutral"). This violated the principle that TraderBot provides tools and data, while agents make decisions.

## Decision

Replace the generic signal engine with per-category MCP toolkits. Each category gets analysis tools that provide structured analytical data, not directional calls. Weather is the first category.

## Consequences

- `generate_signal()` is retired
- Weather toolkit provides: `weather_forecast_prob`, `weather_accuracy`, `weather_decision_brief`
- Each toolkit follows the same pattern: probability estimates with confidence intervals, historical accuracy, market-implied data
- Agents receive interpretive statistical outputs, not trading signals
- Category toolkits are namespaced: `traderbot__weather_*`, `traderbot__economics_*`, etc.

## Notes for AutoDev Agents

When implementing category toolkits, follow the weather toolkit pattern. Each tool returns structured data (probabilities, confidence intervals, historical metrics). Never return directional trading calls ("buy"/"sell"/"hold"). The agent decides what to do with the analysis. This is a fundamental architectural principle (DD-002: TraderBot provides tools, agents make decisions).
