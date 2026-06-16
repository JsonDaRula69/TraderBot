# ADR-030: CLI circular imports — extract DB code from helpers

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-030
**Tags:** cli, architecture, imports, refactoring

## Context

The CLI module (`cli/helpers.py`) contained database access code, creating circular import dependencies that made the module structure fragile.

## Decision

Extract database code from `cli/helpers.py` into `db/connections.py`. CLI helpers should only handle CLI-specific concerns (formatting, argument parsing, display). Database access goes through the proper DB module.

## Consequences

- `cli/helpers.py` no longer imports from `db/`
- `db/connections.py` handles connection pooling and session management
- CLI commands that need data go through the service layer, not direct DB queries
- Circular import issues resolved

## Notes for AutoDev Agents

When adding CLI commands, never import database modules directly in CLI helper files. Use the service layer or MCP tools. The CLI is a thin presentation layer.
