# ADR-016: Always-on service with continuous data pipeline

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-016
**Tags:** service, daemon, data-pipeline, websocket

## Context

Trading agents need continuous data to make decisions. Stopping and restarting the service creates data gaps that could lead to stale or incorrect decisions.

## Decision

TraderBot runs as an always-on daemon. The data pipeline (Kalshi WebSocket, news, weather, FRED, settlement monitoring, token rotation) runs continuously. MCP server and data workers are always available.

## Consequences

- Kalshi WebSocket is the primary real-time data source (REST only for fallback/history)
- Any REST call for data that WebSocket already provides is a bug
- Scheduled workers: news (30m), weather (1h), FRED (daily), settlement (1h), token rotation (4h)
- Service is registered during `traderbot deploy` (DD-004)
- `traderbot deploy` starts the service after setup

## Notes for AutoDev Agents

The data pipeline is critical infrastructure. If the WebSocket disconnects, the service must reconnect and seed the cache from REST API (not error out). Token rotation happens every 4 hours via Infisical (DD-037). Never implement polling where WebSocket data is available.
