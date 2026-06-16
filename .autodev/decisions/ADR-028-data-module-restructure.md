# ADR-028: news/ and data/ module restructure

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-028
**Tags:** data, modules, architecture, restructure

## Context

The existing `news/` module was a separate data silo. Data sources (news, weather, economics, etc.) need unified processing and storage.

## Decision

Replace the separate `news/` module with a unified `data/` module. Per-source providers feed into a common processing pipeline. Each provider handles its own fetching, parsing, and storage.

## Consequences

- `news/` module retired, replaced by `data/`
- Per-source providers: `data/weather.py`, `data/news.py`, `data/fred.py`, etc.
- Common processing pipeline: fetch → parse → embed → store
- ChromaDB stores embedded content with category metadata
- All providers follow the same interface

## Notes for AutoDev Agents

This is a module-level restructuring. When implementing data providers, follow the common interface pattern. Each provider must implement: `fetch()`, `parse()`, `embed()`, `store()`. The unified module handles scheduling and error handling.
