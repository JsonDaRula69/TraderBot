# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0a8] — 2026-08-01

### Added

- test: cover isolated token storage and profile registry — Tests cover isolated token storage and the profile registry.

## [2.0.0a7] — 2026-08-01

### Added

- feat: add workspace TOOLS.md files with token parameter instructions — Per-agent workspace TOOLS.md files document token parameter usage.

## [2.0.0a6] — 2026-08-01

### Added

- feat: add DD-011 category enforcement and Pydantic input validation to MCP tools — MCP tools enforce DD-011 category rules and validate inputs with strict Pydantic models.

## [2.0.0a5] — 2026-08-01

### Added

- feat: add mcp/auth.py with DD-011 category enforcement — check_category_access() enforces per-agent category isolation at the MCP tool layer.

## [2.0.0a4] — 2026-08-01

### Added

- feat: wire resolver.py Phase 1 swap point to real auth — The resolver swap point now selects real authentication.

## [2.0.0a3] — 2026-08-01

### Added

- feat: add profiles/registry.py with ProfileRegistry — ProfileRegistry loads profiles from factory functions for the Phase 1 resolver swap point.

## [2.0.0a2] — 2026-08-01

### Fixed

- fix: correct weather profile tool names to match v2docs/09-mcp-tools.md — Weather profile tools now use the authoritative names from v2docs/09-mcp-tools.md.

## [2.0.0a1] — 2026-08-01

### Added

- feat: add profiles/tokens.py with TokenStore ABC and LocalTokenStore — TokenStore ABC and LocalTokenStore provide 256-bit profile-token persistence.
