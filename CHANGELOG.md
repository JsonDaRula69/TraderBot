# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0a115] — 2026-10-10

- Consolidated the Windows quarantine for the 82 pre-existing portability-debt test failures (issue #222) into a single registry module (`tests/windows_quarantine.py`) keyed by exact node ids from CI run 38108188505, applied by one `pytest_collection_modifyitems` hook that skips only on win32; `TRADERBOT_WINDOWS_QUARANTINE=off` re-enables them all; quarantined test files carry zero diff.

## [2.0.0a114] — 2026-10-10

- Upgraded the transitive `pyjwt` (mcp crypto extra) lock entry from 2.13.0 to 2.15.1, clearing PYSEC-2026-4142 and PYSEC-2026-4183; the Kalshi signing path (RSA-PSS over `cryptography`, not JWT) verified unaffected by the Kalshi client and MCP auth E2E suites.

## [2.0.0a113] — 2026-10-10

- Made the `test_verify_openclaw_contract` inventory fixtures platform-neutral (workspace paths rooted at the test's absolute temp dir instead of POSIX-only `/deploy/<id>` literals), fixing the 11 Windows AgentSummary validation failures without touching any required/advisory assertion.

## [2.0.0a112] — 2026-10-10

- Made `test_infisical_credentials_path_uses_data_dir`'s mock-read assertion set-based rather than order-based, so machine-key reads (`/etc/machine-id`) no longer break the credentials-path check on Linux.

## [2.0.0a110] — 2026-10-10

- Minted DD-039 (verification requiredness) as a numbered design decision in the roadmap twins and decision index: required checks assert exactly the deploy-written postconditions carried on the verification request, preserved posture and wizard-path daemon liveness report as advisory divergence, and standalone `traderbot verify` keeps daemon health required; cross-referenced from the v2docs/02 Step 8 contract.

## [2.0.0a109] — 2026-10-10

- Real-CLI deploy E2E fixtures now own a clean workspace root (`clean_workspace_root`) so the suite passes under any default basetemp, and the CI test matrix pins `--basetemp` under `$HOME` as a stopgap — the injection publication guard rejects group-writable workspace ancestors, which the sticky bit does not exempt.

## [2.0.0a108] — 2026-10-10

- Deploy-wizard Step 8 now requires only deploy-asserted postconditions: wizard step 8 completes when no required check fails, embedding preserved-posture and daemon advisories; sandbox posture is required only for created agents and heartbeat `0m` only under approved policy; the bootstrap cron probe is lifecycle-aware against deploy state; standalone `traderbot verify` keeps daemon health required.

## [2.0.0a107] — 2026-10-10

### Fixed

- Deploy wizard step 8 is now required-aware: it completes when no required check fails, embedding advisory divergences (preserved sandbox/heartbeat posture, daemon liveness) and required-but-degraded state (sanctioned encrypted fallback) visibly in its result, while any required failure still fails the deployment.

## [2.0.0a106] — 2026-10-10

### Fixed

- Verification now requires exactly the postconditions a deployment wrote instead of a fresh-install posture: `VerificationRequest` carries `heartbeat_policy` (dormancy required only when the deploy approved `0m`), `created_agents` (sandbox required only for agents the deploy created), and `daemon_required` (strict standalone default; the wizard path reports daemon liveness as advisory since no wizard step owns the daemon lifecycle). The OpenClaw probes report preserved posture as advisory divergence with actual values, and the bootstrap cron probe is lifecycle-aware — a completed retained one-shot passes with its own action, absence after a recorded firing is honest degraded state, and only a never-registered or conflicting contract fails closed.

## [2.0.0a105] — 2026-10-04

### Fixed

- Deploy and verify bootstrap-cron readback now accepts the deployed pending one-shot envelope instead of fail-closing a successful registration as a conflict: OpenClaw 2026.7.1-2 populates `state: {"nextRunAtMs": <positive int>}` plus top-level `nextRunAtMs` and `status: "idle"` the moment a job is scheduled (recorded on-target in `.omo/evidence/f3-a104-r5-receipts/recorded-cron-job.json`). A pending one-shot is exact whether `state` is `{}` or exactly `{"nextRunAtMs": <positive int>}`, and unrelated deployed top-level extras are ignored. Identity fields stay strict fail-closed: job name, agent, schedule, session, wake mode, payload message, and delete-after-run; garbage `nextRunAtMs` values (non-int, non-positive, bool) and state shapes indicating an already-run or errored job still classify as conflict. This repairs both wizard step 3's post-registration verification (C1, "bootstrap cron final verification failed") and the standalone verify cron probe (C5, `bootstrap_cron_mismatch`), which share the same classifier.

## [2.0.0a104] — 2026-10-03

### Fixed

- Deploy and verify OpenClaw config reads now classify a missing config path from the deployed CLI's plain-text STDERR error (empty STDOUT) as well as the legacy STDOUT JSON error envelope, so the `agents.list[index]` fallback is reachable against the deployed `agents.list[]` config shape and wizard step 1 no longer fails with "config inventory is unreadable" on OpenClaw 2026.7.1-2.
- Kalshi series discovery tolerates production's observed empty-series encoding — HTTP 200 `{"series": null}` for an empty or unmatched `category` query — and normalizes it to an empty list; a missing `series` key still fails validation. The request mapping is unchanged: official Get Series List schema (OpenAPI 3.32.0, re-verified 2026-10-03) declares `category` a plain string filter with exact, case-sensitive matching, so an unmatched value legally yields an empty result and only the response's observed null form required repair.

## [2.0.0a103] — 2026-10-03

### Fixed

- Infisical selection now tolerates unrelated routing metadata in the shared credentials document instead of incorrectly falling back to encrypted local storage; required login fields remain enforced.

## [2.0.0a102] — 2026-10-03

### Fixed

- Deploy preflight accepts OpenClaw's canonical `main`-container workspace layout, including symlink-resolved containment. Equal/same-file ownership and non-`main` containment remain rejected across selected and unselected agents.

## [2.0.0a101] — 2026-10-03

### Removed

- Removed the Phase-4 hosted Kalshi demo surface per the 2026-08-20 contract correction: TraderBot Phase 4 demo/QA is local backtest simulation plus canonical read-only production market-data/auth reads, and TraderBot never uses Kalshi's hosted demo endpoint. Reverts the a100 standalone endpoint routing and removes the `kalshi_environment` request/config threading, the standalone backfill/verify `--environment` flags, the `kalshi_demo_*` secret-name routing, and the `KALSHI_ENVIRONMENTS` constant; deploy, backfill, and verify always read the canonical `kalshi` service (`kalshi_api_key`/`kalshi_private_key_pem`) against production. Generic `KalshiClient` environment support and the daemon `--environment` flag are unchanged.

## [2.0.0a100] — 2026-08-19

### Fixed

- Added strict `production|demo` routing to standalone backfill and verification, including typed request propagation, exact demo REST endpoint selection, production-compatible defaults, and pre-dispatch rejection of invalid environments.
- Routed deploy secret provisioning, standalone backfill credentials, and verification Kalshi probes by Kalshi environment: production reads/writes only `kalshi_api_key`/`kalshi_private_key_pem` (service `kalshi`), demo only `kalshi_demo_api_key`/`kalshi_demo_private_key_pem` (service `kalshi_demo`), with missing or malformed demo credentials failing closed and no cross-environment fallback.

## [2.0.0a99] — 2026-08-19

### Fixed

- Removed the production environment-selected deploy test-provider path and packaged success fake, moved subprocess injection into a distribution-excluded test runner, and closed the final Phase 4 typing, formatting, module-documentation, and cleanup blockers.

## [2.0.0a98] — 2026-08-18

### Changed

- Synchronized the Phase 4 deploy contract across v2docs, README, roadmaps, and issue tracking: authoritative `{mode}-{name}` storage, nine categories, pre-existing `main`, explicitly approved missing-agent creation, Phase 4b deferrals, scheduling ownership, the read-only Phase 5 sandbox stub, AGENTS-only exact-five-tool guidance, Infisical/encrypted fallback, canonical Kalshi secrets and environment routing, one data root, lazy Chroma, and no SysAdmin decisions database.
- Recorded Todo 12 at local commit `498ddc1` / VERSION `2.0.0a97`: 917 full tests and 192 targeted deploy/backfill/verify tests passed, including isolated config-mode CLI and malformed-JSON coverage with no live/default-state mutation.

## [2.0.0a96] — 2026-08-12

### Fixed

- Hardened workspace-write TOCTOU race, propagated configured `data_root` through all deploy phases, threaded `kalshi_environment` through backfill and verification, forced `TRADERBOT_USE_HARDCODED_AUTH=0` for `traderbot verify`, broke the deploy import cycle, fixed two stale/dependency tests, and split `wizard_command.py` via `wizard_request.py`.

## [2.0.0a95] — 2026-08-11

### Added

- Completed deploy wizard Steps 6-8 by composing typed backfill and read-only verification runtimes with an explicit non-mutating Phase 5 sandbox stub and strict Gateway cron outcome.
- Repaired late-step snapshot ownership, invalid-input ordering, one-shot lifecycle evidence, selective resumability, cleanup truthfulness, and actual CLI-dispatch E2E coverage.
- Hardened pre-factory data-root and deploy-state trust checks, completed one-shot lifecycle parsing, and suppression-free typed ordinary-exception boundaries.
- Closed persisted-false cron registration, post-open deploy-state metadata races, and cleanup-error exit classification; split bootstrap cron contracts from the wizard runtime.

## [2.0.0a94] — 2026-08-11

### Added

- Added the read-only `traderbot verify` command with dependency-aware deployment checks, signed Kalshi balance authentication, strict storage manifests, and stable JSON/Rich results.

## [2.0.0a93] — 2026-08-11

### Added

- Added the idempotent `traderbot backfill` command with read-only collector import, current/archive Kalshi weather history, typed partial results, and strict JSON output.

## [2.0.0a92] — 2026-08-11

### Added

- Added global migration v2 and strict official Kalshi v2 series, market, live/historical candlestick, and signed forecast-history methods for deterministic historical backfill.

## [2.0.0a91] — 2026-08-11

### Added

- Added deploy wizard steps 4-5 with secret-safe Kalshi credential provisioning, encrypted Infisical fallback, selected-category database initialization, read-only SysAdmin enumeration, and lazy embedded Chroma validation.

## [2.0.0a90] — 2026-08-11

### Fixed

- Reconciled deploy wizard steps 1-3 through a global read-only OpenClaw inventory/config/workspace preflight, explicit creation and heartbeat approvals, stable partial-agent adoption, atomic SecretRef preservation, and bootstrap-last Gateway ordering.

## [2.0.0a89] — 2026-08-11

### Fixed

- Aligned workspace injection with stable/current OpenClaw by moving exact-five-tool guidance into AGENTS, preserving legacy TOOLS/HEARTBEAT files, and restricting live allowlists to implemented tools.

## [2.0.0a88] — 2026-08-10

### Added

- Added resumable deploy wizard steps 1-3 for prompt-free OpenClaw baseline setup, SysAdmin identity/bootstrap, and explicitly selected category agents with encrypted profile-token persistence.

### Fixed

- Validate the complete managed SysAdmin cron contract and re-inspect newly added jobs instead of reusing same-name mismatches.
- Accept the documented Todo-1 deploy JSON by deriving invocation-scoped OpenClaw workspaces, narrow deploy mode to backtest, and report that steps 4-8 remain incomplete.

## [2.0.0a87] — 2026-08-10

### Added

- Added safe, idempotent workspace template restoration and restrictive OpenClaw configuration for all nine market categories.

### Fixed

- Rejected symlinked workspace ancestors, preserved existing permission bits through update and rollback, closed failed descriptor handoffs, and documented `market_edge` as a current stub.

## [2.0.0a86] — 2026-08-10

### Added

- Added bounded, noninteractive OpenClaw CLI wrappers for deployment setup, agents, cron jobs, health checks, and strict JSON configuration.

## [2.0.0a83] — 2026-08-10

### Fixed

- Resolved flaky `test_exclusive_checkout_waits_until_timeout` on Windows CI by increasing timeout from 20ms to 200ms (#200)

## [2.0.0a82] — 2026-08-10

### Fixed

- Corrected GRIB2 (DD-033) phase assignment from Phase 4 to Phase 7a backtesting (#171, #194)

## [2.0.0a81] — 2026-08-10

### Changed

- Updated DD-033 status: Stage 1 folded into Phase 4 backtesting, Stage 2 is post-Phase 4 follow-up
- Closed ChromaDB security review tracker #195 (findings preserved in #196)
- Closed Phase 3 parent issue #167 (PR #197 merged, all QA passed)
- Updated roadmap and database schema docs to reflect Phase 3 completion and GRIB2 Phase 4 incorporation

## [2.0.0a80] — 2026-08-10

### Fixed

- Resolved Windows CI failures: fsync O_RDWR, /tmp path via tempfile.gettempdir(), USERPROFILE env, ACL best-effort validation

## [2.0.0a76] — 2026-08-10

### Fixed

- Preserved pre-existing ChromaDB directories when secure root creation rejects an existing target
- Consolidated Phase 3 QA into the single allowed `scripts/phase3-qa.py` entry point and removed its package/helper scope violations
- Kept existing basedpyright warnings visible while allowing warnings-only checks with zero type errors to exit successfully

## [2.0.0a74] — 2026-08-10

### Added

- Added `chromadb==1.5.9` with embedded-only security guards, explicit vectors, owner-only storage, and an exact GHSA-f4j7-r4q5-qw2c scanner waiver
- Added the central `db/` module with a typed migration runner, bounded SQLite connection pool, `ChromaStore`, and identity-aware `DatabaseAccess`
- Added isolated per-profile, per-mode `decisions.db` databases with seven tables for decisions, positions, forecast snapshots, bias tracking, learnings, circuit-breaker state, and portfolio summaries
- Integrated global migrations, pooled storage, and embedded ChromaDB into the daemon lifecycle with database, ChromaDB, and ownership-lock health reporting
- Added the full Phase 3 component test suite and isolated `scripts/phase3-qa.py` runner for migration, rollback, access isolation, ChromaDB filtering, and performance checks

### Changed

- Deferred the GRIB2 processing pipeline from Phase 3 to [issue #194](https://github.com/JsonDaRula69/TraderBot/issues/194)
- Documented the completed ChromaDB security review and accepted-risk tracking in [issue #195](https://github.com/JsonDaRula69/TraderBot/issues/195) and [issue #196](https://github.com/JsonDaRula69/TraderBot/issues/196)

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
