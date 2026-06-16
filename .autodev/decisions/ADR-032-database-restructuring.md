# ADR-032: Database restructuring for multi-agent multi-mode

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-032
**Tags:** database, sqlite, chromadb, isolation, architecture

## Context

The original database design used a single shared database. With multiple agents in different modes, this creates data leakage and isolation concerns.

## Decision

Per-agent per-mode SQLite isolation. Each agent gets its own SQLite database for each mode (backtest, paper, live). ChromaDB is shared with category metadata filtering.

## Consequences

- Directory structure: `~/.traderbot/<agent>/<mode>/decisions.db`
- SysAdmin has cross-agent access (`enabled_categories: []`)
- Unified SQL schema across all databases
- Generalized bias tracking and forecast snapshots
- Connection pooling and PRAGMA optimization
- Migration system for schema changes
- Settlement cache consolidation
- Circuit breaker extends to DB operations
- Retention policy for old data

## Consequences (ChromaDB)
- Shared collections with category metadata filtering
- Per-agent collections for decisions/learnings
- ChromaDB model migration path defined

## Notes for AutoDev Agents

Database isolation is a hard constraint. Never access another agent's database directly. Use the MCP tools which handle routing. The `traderbot profile update <agent> --mode <mode>` command switches the active database. Connection pooling prevents resource exhaustion.
