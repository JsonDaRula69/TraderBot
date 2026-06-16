# ADR-022: Service template path resolution

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-022
**Tags:** deployment, service, paths, templates

## Context

Service templates need to reference the TraderBot executable and Python paths, but these vary by installation method and OS.

## Decision

Service templates use `{placeholder}` syntax resolved at deploy time via `shutil.which('traderbot')`. Templates are package data read via `importlib.resources`.

## Consequences

- No hardcoded paths in service templates
- `shutil.which('traderbot')` resolves the actual binary location
- Works across pipx, venv, and development installations
- Templates are portable across OSes

## Notes for AutoDev Agents

When creating or modifying service templates, always use `{placeholder}` variables. Never hardcode paths. The resolution happens in `traderbot deploy` using `shutil.which()` and string replacement.
