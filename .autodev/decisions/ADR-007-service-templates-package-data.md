# ADR-007: Service templates as package data

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-007
**Tags:** packaging, service, deployment

## Context

Service templates (systemd units, launchd plists) need to be accessible from a pipx-installed package. The `install/` directory won't exist in a pipx install.

## Decision

Move service templates into `src/traderbot/services/` as package data files. `traderbot deploy` reads them via `importlib.resources` and does path substitution before deploying.

## Consequences

- `install/services/` directory retired (templates move to `src/traderbot/services/`)
- `install/docker/` remains as a build artifact (Dockerfile ships with the repo, not the package)
- Shell install scripts are retired — their logic moves into Python
- Template path substitution uses `shutil.which('traderbot')` (DD-022)

## Notes for AutoDev Agents

All service templates must use `{placeholder}` variables for paths (e.g., `{traderbot_path}`, `{python_path}`). These are resolved at deploy time. Never hardcode absolute paths in templates.
