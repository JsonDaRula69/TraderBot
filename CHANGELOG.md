# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0a61] — 2026-08-04

### Added

- Phase 2 always-on service (issue #166): `traderbot daemon` runs the Kalshi WebSocket stream, the data pipeline, and the MCP server over streamable-http on loopback (`127.0.0.1:8765/mcp`) in one process
- Resurrected Kalshi REST + WebSocket clients (v2-only, per-environment TLS pins, token-bucket rate limiting, exponential-backoff reconnect)
- `MarketCache` with SQLite write-behind persistence — the read source for `traderbot__market_prices` (zero REST calls)
- Unified `data/` module (DD-028): `BaseDataProvider`, `DataScheduler`, `ProviderRegistry`, `DataCollectionService`, and providers (OpenMeteo, NWS, news stub, settlement monitor)
- `services/` package (DD-022): systemd / launchd / Windows Task Scheduler templates with `BinPaths` resolution
- `traderbot service install|uninstall|status` CLI (sudo-elevated unit writes, enable/start on install)
- `traderbot__market_prices` MCP tool reading from the WS cache
- OpenClaw config migrated from stdio to streamable-http; `TRADERBOT_USE_HARDCODED_AUTH=0` moved to the daemon service unit

### Fixed

- Kalshi TLS SPKI pins made environment-aware (stale prod pin rejected all connections)
- `orderbook_delta` WS channel excluded from the default subscription set (it requires `market_tickers`)
- `traderbot daemon` CLI subcommand forwards host/port/environment to the daemon entry point
- Daemon `build_components` wires the Infisical-backed `SecretsStore` (was falling back to an unconfigured local store)

## [2.0.0a44] — 2026-08-04

### Docs

- docs: fix stale DD-037 config example (source vs type, wrapper script) and update implementation status to deployment-verified

## [2.0.0a43] — 2026-08-04

### Docs

- docs: Phase 1.5 Infisical deployment verified on macpro-linux — live agent E2E passes (weather agent → plugin → Infisical exec provider → token extracted → MCP server resolves via Infisical-backed SecretsStore); fail-closed unknown agent; token never in model context; four deployment-discovered fixes documented (wrapper extra=ignore, plugin JSON-doc extraction, with-plugin.json source vs type, exec provider command ownership)

## [2.0.0a42] — 2026-08-03

### Fixed

- Deployment-discovered Phase 1.5 fixes: wrapper `InfisicalCredentials` allows extra fields (6419dc5), token-injector plugin extracts the raw token from the 5-field JSON document (6419dc5), with-plugin.json exec provider uses `source` not `type` per the OpenClaw schema (6b6772e)
- Windows CI fix: `LocalEncryptedStore` writes in binary mode to avoid `\r\n` line-ending corruption of the integrity hash (d55cebd)

### Added

- Phase 1.5 deployment testing on macpro-linux: server-side Infisical integration verified (wrapper, migration, resolve_token, rotation, MCP stdio E2E, gateway exec provider)

## [2.0.0a38] — 2026-08-03

### Added

- feat: Phase 1.5 Infisical secrets store — `SecretsStore` unified facade (`src/traderbot/secrets/store.py`) selecting Infisical primary or `LocalEncryptedStore` fallback
- feat: `LocalEncryptedStore` encrypted local fallback (`src/traderbot/secrets/local_encrypted.py`) — whole-payload Fernet encryption, machine-derived key, SHA-256 integrity monitoring
- feat: `TokenStoreAdapter` (`src/traderbot/secrets/adapter.py`) — installs `SecretsStore` behind the existing `TokenStore` ABC seam
- feat: `SecretsResolver` (`src/traderbot/secrets/resolver.py`) — lazy Infisical SDK init from `~/.traderbot/infisical-credentials.json` with local fallback
- feat: `TokenRotationManager` + `RotationScheduler` (`src/traderbot/secrets/rotation.py`) — 4-hour asyncio rotation, per-agent failure tracking, 24-hour fleet suspension via `_SUSPENDED_PROFILES`
- feat: `scripts/openclaw-infisical-resolver` exec provider — OpenClaw SecretRef bridge to Infisical
- feat: migrate plugin SecretRef provider from `vault` to `infisical` in `configs/openclaw/with-plugin.json`
- feat: local-to-Infisical token migration script (`src/traderbot/secrets/migrate.py`)
- test: integration test suite (`tests/test_integration_secrets.py`) covering resolver → adapter → store → rotation → suspended profiles
- feat: `TradingProfile.suspended: bool` field and `_SUSPENDED_PROFILES` module state in `mcp/resolver.py`

### Changed

- deps: replace `infisical-python` design references with `infisicalsdk` (current official SDK)
- docs: update DD-037 in `v2roadmap.md` and `v2docs/v2roadmap.md` — `infisicalsdk`, `prod` environment slug, consolidated SDK integration in `store.py`, Phase 1.5 implemented
- docs: rewrite `v2docs/04-security-and-auth.md` to reflect Phase 1.5 implemented status, `LocalEncryptedStore`, and Infisical exec provider
- docs: update `docs/dev-liaison-testing-protocols.md` Phase 1.5 section with implemented commands and current test count
- docs: comment GitHub issue #165 with Phase 1.5 completion status


## [2.0.0a25] — 2026-08-03

### Fixed

- fix: set `TRADERBOT_USE_HARDCODED_AUTH=0` in MCP server env config — subprocess does not inherit gateway systemd drop-in env vars (0dbc981)

### Changed

- docs: update v2docs/04-security-and-auth.md and 09-mcp-tools.md with Phase 1.1 deployment findings: token optional in schema, gateway version requirement, manifest requirements, MCP server env inheritance
- docs: mark Phase 1.1 deployment verification complete in v2roadmap
- docs: add standing documentation-sync rule to AGENTS.md

## [2.0.0a24] — 2026-08-03

### Fixed

- fix: make `token` optional in MCP tool schemas (`str | None = None`) — SDK validates schema BEFORE the before_tool_call hook runs, so a required token field rejects the call before injection (f1aa518)

## [2.0.0a23] — 2026-08-03

### Fixed

- fix: add `openclaw` metadata and `configSchema` to plugin manifest — required for OpenClaw gateway plugin loading

## [2.0.0a22] — 2026-08-02

### Added

- docs: add comprehensive dev-liaison testing protocols for all v2 phases (docs/dev-liaison-testing-protocols.md).
  Defines per-phase testing objectives, executable procedures (exact commands), metrics, deliverables, and
  pass/fail criteria for Phase 1.1 (token injector), 1.5 (Infisical secrets), 2 (daemon/data pipeline/WS),
  3 (database isolation), 4 (deploy wizard), 5 (Docker sandbox), 6 (weather toolkit), 7a (backtesting),
  7b (paper/live trading + risk), 7c (lifecycle), 8 (self-improvement), and 9 (additional categories),
  plus a shared general protocol for environment verification and reporting.

## [2.0.0a21] — 2026-08-02

### Changed

- docs: correct Phase 1.1 status to "code complete and locally tested" across roadmap and docs. The plugin code is written and tests pass locally (113 Python + 11 TypeScript), but it is NOT yet deployed to a real OpenClaw gateway, tested with real Vault SecretRefs, or verified on macpro-linux.

## [2.0.0a20] — 2026-08-02

### Changed

- docs: update stale documentation and roadmap references to reflect that the Phase 1.1 `before_tool_call` token injector plugin is now implemented and committed (commit 5b5088e, issue #187).

## [2.0.0a19] — 2026-08-03

### Added

- feat: Phase 1.1 token injector plugin — add `plugins/traderbot-token-injector/` OpenClaw plugin implementing the `before_tool_call` hook for host-side profile-token injection.
- feat: add unit and integration test suites for the token injector plugin (8 unit + 3 integration, Vitest).
- feat: add OpenClaw config example `configs/openclaw/with-plugin.json` registering the token injector plugin.
- feat: update workspace TOOLS.md files (weather, sysadmin, dev-liaison) to document host-side token injection via the plugin.
- test: add Python negative regression test `tests/test_missing_token.py` verifying missing-token behavior.

## [2.0.0a18] — 2026-08-02

### Changed

- docs: rename token injection phase from Phase 1.5 to Phase 1.1 across roadmap, security, and MCP docs; reference implementation plan at `.omo/plans/phase1-1-token-injector.md`; update issue #187 and issue #164 comments.

## [2.0.0a17] — 2026-08-02

### Added

- docs: document `before_tool_call` plugin hook token injection solution for Phase 1.5 — architecture, security properties, critical constraints, and roadmap synchronization across `v2roadmap.md` and `v2docs/`.

## [2.0.0a15] — 2026-08-02

### Fixed

- fix: harden MCP request typing and add real-auth transport E2E — MCP request typing hardened and real-auth transport E2E added.

## [2.0.0a14] — 2026-08-02

### Fixed

- fix: harden LocalTokenStore persistence and typed payload handling — LocalTokenStore persistence and typed payload handling hardened.

## [2.0.0a13] — 2026-08-01

### Changed

- docs: reconcile Phase 1 authentication status — Roadmap copies and security references aligned with verified local auth behavior.

## [2.0.0a12] — 2026-08-01

### Added

- feat: add OpenClaw per-agent tool configs — OpenClaw per-agent tool configs for sysadmin, dev-liaison, and weather.

## [2.0.0a11] — 2026-08-01

### Added

- test: comprehensive test suite for Phase 1 real auth — Comprehensive test suite covers Phase 1 real authentication.

## [2.0.0a10] — 2026-08-01

### Added

- test: enforce weather permissions and MCP E2E validation — Tests enforce weather permissions and validate MCP end-to-end behavior.

## [2.0.0a9] — 2026-08-01

### Added

- test: cover MCP auth and resolver paths — Tests cover MCP auth and resolver paths.

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

## [2.0.0a26] — 2026-08-03

### Fixed

- fix: ruff E501 line-too-long in test_mcp_server.py comment (CI lint failure)

## [2.0.0a27] — 2026-08-03

### Fixed

- fix: remove duplicate unreachable `return err` in tools.py (AFT warning)
- fix: type-check `properties` with isinstance in test_mcp_server.py (AFT error)
- fix: add basedpyright venv config to pyproject.toml (AFT import error)

## [2.0.0a28] — 2026-08-03

### Changed

- docs: close #187 (Phase 1.1 complete), fix stale "pending"/"blocked" references across v2roadmap DD-025 and v2docs/09-mcp-tools.md

## [2.0.0a42] — 2026-08-03

### Fixed

- fix(config): `with-plugin.json` Infisical exec provider used `type: "exec"` but the OpenClaw schema requires `source: "exec"` — discovered during macpro-linux deployment testing when the gateway rejected the config (`secrets.providers.infisical: Invalid input`). Updated the config and the two tests that asserted the wrong field (`test_with_plugin_config.py`, `test_integration_secrets.py`).
- fix(plugin): token-injector plugin now extracts the raw `token` field from the 5-field Infisical JSON document (DD-037 §4) before injecting into MCP params, falling back to the raw string for env/file providers; fails closed on a JSON document lacking a string `token` field.
