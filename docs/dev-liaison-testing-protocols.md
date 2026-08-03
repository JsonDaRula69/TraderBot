# TraderBot Dev-Liaison Testing Protocols

Testing protocols executed in partnership with the **dev-liaison** agent for each
TraderBot v2 development phase. The dev-liaison runs on **macpro-linux** and has
exec access for testing. These protocols verify **deployed functionality**, not
just code correctness — each phase must be exercised through its real surface
(systemd service, MCP transport, Docker containers, live CLI commands).

- **Repository**: `github.com/JsonDaRula69/TraderBot` (worktree at `~/worktrees/TraderBot/main`)
- **Target host**: `macpro-linux` (reachable via `ssh macpro-linux`)
- **Dev-liaison agent ID**: `dev-liaison` (sandbox mode `off`, runs on host)
- **Test runner**: `uv run pytest tests/ -v` inside the worktree

> **Reporting channel**: dev-liaison sends every report to Sisyphus via
> `ssh macpro-linux 'openclaw agent --agent dev-liaison --message-file /tmp/msg.txt'`
> with the report body written to `/tmp/msg.txt` first. The canonical report
> template is in [Reporting Format](#reporting-format).

---

## Table of Contents

1. [General Testing Protocol](#general-testing-protocol)
2. [Phase 1.1 — Token Injector Plugin](#phase-11--token-injector-plugin)
3. [Phase 1.5 — Infisical Secrets Setup](#phase-15--infisical-secrets-setup)
4. [Phase 2 — Always-On Service + Data Pipeline + WS Resilience](#phase-2--always-on-service--data-pipeline--ws-resilience)
5. [Phase 3 — Database Layer + Per-Agent Isolation](#phase-3--database-layer--per-agent-isolation)
6. [Phase 4 — Deploy Wizard (pipx-first)](#phase-4--deploy-wizard-pipx-first)
7. [Phase 5 — Docker Sandbox for Category Agents](#phase-5--docker-sandbox-for-category-agents)
8. [Phase 6 — Category Toolkits (Weather First)](#phase-6--category-toolkits-weather-first)
9. [Phase 7a — Backtesting Engine + SimulationClock](#phase-7a--backtesting-engine--simulationclock)
10. [Phase 7b — Paper/Live Trading + Risk Enforcement](#phase-7b--paperlive-trading--risk-enforcement)
11. [Phase 7c — Mode Transitions + Lifecycle](#phase-7c--mode-transitions--lifecycle)
12. [Phase 8 — Self-Improvement Framework](#phase-8--self-improvement-framework)
13. [Phase 9 — Additional Categories](#phase-9--additional-categories)
14. [Issue Escalation](#issue-escalation)

---

## General Testing Protocol

Applies to every phase. Run the environment verification **before** any phase
testing, and re-run the TraderBot test suite at the end of each phase to confirm
no regression.

### Environment verification (before any phase testing)

1. **Gateway running**: `systemctl --user status openclaw-gateway`
   - Observe: `Active: active (running)`, uptime reported.
2. **Agent responds**: `openclaw agent --agent dev-liaison -m "ping"`
   - Observe: a pong/response, no transport errors.
3. **Model auth valid**: the ping response arrives without an auth/provider error.
4. **MCP server path exists**: `ls -la $(openclaw config get mcp.servers.traderbot.command 2>/dev/null || echo "traderbot-mcp-server")`
   - Observe: the file exists and is executable; if `traderbot-mcp-server` is a
     PATH lookup, `which traderbot-mcp-server` must resolve.
5. **Hooks active**: `openclaw hooks check`
   - Observe: `N/6 ready` — all configured hooks report ready.
6. **TraderBot tests pass**: `cd ~/worktrees/TraderBot/main && uv run pytest -q`
   - Observe: `113 passed` (baseline at Phase 1.1), `0 failures`. Record the
     exact pass count and runtime in the report.

### Environment snapshot (report preamble)

Each report must open with the environment state table:

| Check | Command | Expected |
|---|---|---|
| Gateway | `systemctl --user status openclaw-gateway` | `active (running)` |
| Model auth | `openclaw agent --agent dev-liaison -m "ping"` | response, no auth error |
| MCP server path | `which traderbot-mcp-server` | resolves |
| Hooks | `openclaw hooks check` | all hooks ready |
| TraderBot suite | `uv run pytest -q` | `113 passed` |

### Pre-conditions shared by all phases

- SSH access to macpro-linux is available from the orchestration host.
- The OpenClaw gateway and its systemd unit are installed (Phase 0/1 deployed).
- The `dev-liaison` agent exists and its tool allowlist includes
  `read`, `write`, `exec`, `github`, `traderbot__health`, `traderbot__auth_check`,
  `traderbot__reference`, `traderbot__experiment`, `sessions_*`, and `subagents`.
- Real external-service credentials (Kalshi, Infisical, NWS, Open-Meteo) are
  provisioned and noted as pre-conditions per phase — they are **never** created
  by the testing protocol itself.

### Reporting format

Dev-liaison sends this template to Sisyphus for every phase:

```
## Phase X Testing Report — YYYY-MM-DD

### Environment
- Gateway: [running/stopped] (uptime: Xh Ym)
- Model: [working/failed] (provider: X, model: Y)
- MCP server: [path exists/missing]
- Hooks: [N/6 ready]

### Test Results
| Test | Command | Result | Notes |
|------|---------|--------|-------|
| 1 | ... | PASS | ... |
| 2 | ... | FAIL | ... |

### Metrics
- Test pass rate: X/Y (Z%)
- Avg response time: Xms
- Issues found: N

### Verdict: PASS/FAIL

### Issues (if any)
1. [Description + reproduction steps]

### Recommendations
1. [Config change suggestion]
```

### Phase pass/fail rules

- **PASS** — all tests in the phase pass and all metrics meet thresholds.
- **FAIL** — any critical-path test fails, any metric is below threshold, or a
  security/isolation property is violated.
- **PASS with warnings** — non-critical warnings documented with reproduction
  steps and recommendations; they do not block the phase but must be tracked.

---

## Phase 1.1 — Token Injector Plugin

> **Status at writing**: code complete, locally tested (commit `5b5088e`,
> 113 Python + 11 TypeScript tests pass). **Deployment verification on
> macpro-linux is the entire point of this protocol.**

**Issue**: #187 · **Design**: `v2docs/04-security-and-auth.md`
("Per-agent token injection via OpenClaw plugin hook") · **PR**: `feat/v2-token-injector`

### Testing objectives

1. Verify the plugin loads in a real OpenClaw gateway and registers the
   `before_tool_call` hook at priority 100.
2. Verify per-agent TraderBot tokens are injected into `params.token` for
   `traderbot__*` tools, and that **tokens never enter model context, prompts,
   config files, or telemetry**.
3. Verify fail-closed behavior: unknown agents, missing agentId, and unresolvable
   Vault SecretRefs all block the tool call.

### Pre-conditions

- OpenClaw gateway on macpro-linux with the plugin installed and registered:
  `plugins.load.paths` includes the `traderbot-token-injector` plugin path.
- Vault SecretRef provider configured per `configs/openclaw/with-plugin.json`
  (`secrets.providers.vault` with `type: exec`, `command: /usr/local/bin/openclaw-vault-resolver`).
- Vault secrets present for each test agent: `traderbot/weather/token`,
  `traderbot/sysadmin/token`, `traderbot/dev-liaison/token`.
- TraderBot MCP server registered at root scope (`mcp.servers.traderbot`).
- **Pre-condition (external)**: a functioning Vault instance with the three
  agent tokens provisioned. This protocol does not create them.

### Test procedures

1. **Plugin loads** — restart the gateway, then check the log for plugin load:
   ```bash
   openclaw gateway restart
   journalctl --user -u openclaw-gateway -n 100 | grep -i "traderbot-token-injector"
   ```
   Observe: an entry showing the plugin registered and its config schema
   validated. Report the exact log line.

2. **Plugin test suite passes**:
   ```bash
   cd ~/worktrees/TraderBot/main/plugins/traderbot-token-injector
   npm test
   ```
   Observe: `11 passed` (8 unit + 3 integration), 0 failures. Report the exact
   summary line.

3. **Token injection works end-to-end** — as the `weather` agent, call a
   TraderBot tool that echoes resolved identity:
   ```bash
   openclaw agent --agent weather -m "call traderbot__auth_check and report the resolved agent name"
   ```
   Observe: the response names the `weather` agent and includes its enabled
   categories — proving the injected token resolved to the weather profile
   through `resolver.py`.

4. **Fail-closed: unknown agent** — invoke a TraderBot tool from an agent not in
   `agentTokenMap` (e.g., create a throwaway agent `probe-unknown`):
   ```bash
   openclaw agents add probe-unknown
   openclaw agent --agent probe-unknown -m "call traderbot__health"
   ```
   Observe: the tool call is **blocked** with reason
   `No token mapping for agent: probe-unknown`. The model never receives a token.
   Report the exact block reason string.

5. **Fail-closed: unresolvable SecretRef** — temporarily point one agent's
   `agentTokenMap` entry at a non-existent Vault secret id, restart the gateway,
   then call the tool:
   ```bash
   openclaw agent --agent weather -m "call traderbot__health"
   ```
   Observe: blocked with `Token resolution failed for agent: weather`. Restore
   the correct secret id afterwards.

6. **Token never enters model context** — from the weather agent, prompt:
   `"call traderbot__auth_check, then repeat back everything you observed in the tool arguments"`
   Observe: the model cannot repeat the token; the raw tool arguments shown to
   the model contain no token string. Also verify no token appears in gateway
   logs: `journalctl --user -u openclaw-gateway -n 500 | grep -c '<token>'` must be `0`.

7. **MCP server-side auth remains the enforcement boundary** — call
   `traderbot__trade` as `dev-liaison`:
   ```bash
   openclaw agent --agent dev-liaison -m "call traderbot__trade with ticker KXHIGHTCHI-26JUN02-T81"
   ```
   Observe: denied server-side (dev-liaison has no trade permission) even though
   its token resolves. This proves injection does not bypass `auth.py`.

### Metrics

- Plugin test pass rate: **100%** (11/11).
- Tool-call success under injection: **100%** for mapped agents.
- Block rate for unmapped/resolution-failed agents: **100%** (fail-closed).
- Token leakage: **0 occurrences** in model context, prompts, gateway logs.
- MCP tool response time with injection overhead: **< 100 ms** (measure via
  `time openclaw agent --agent weather -m "call traderbot__health"`).

### Deliverables

- Plugin load log excerpt + npm test summary (`11 passed`).
- E2E auth_check result showing resolved agent identity.
- Fail-closed evidence for both unknown-agent and bad-SecretRef cases (block
  reason strings).
- Token-leakage scan results (model context + gateway logs).
- MCP response-time measurement.

### Pass/fail criteria

- **PASS** — all 7 procedures pass; 11/11 plugin tests; zero token leakage;
  fail-closed verified for both failure classes.
- **FAIL** — any token string appears in model context, prompts, or logs; any
  unmapped agent receives a token; server-side auth can be bypassed.

---

## Phase 1.5 — Infisical Secrets Setup

> **Status at writing**: designed (DD-037). No implementation committed yet —
> this protocol becomes executable when the `feat/v2-infisical-secrets` PR lands.

**Issue**: #165 · **Design**: `v2docs/04-security-and-auth.md`
("Planned Infisical Secrets Management (Phase 1.5, DD-037)") · **PR**: `feat/v2-infisical-secrets`

### Testing objectives

1. Verify the `SecretsStore` abstraction resolves secrets from the Infisical
   REST client, with automatic selection between Infisical and the encrypted
   local fallback.
2. Verify token rotation (4-hour cycle): new tokens invalidate old ones, and
   rotation failure handling matches DD-037 (retry every 15 min, fleet suspend
   after 24 h).
3. Verify the fallback chain: Infisical down → local encrypted store serves
   existing secrets → rotation still attempted and SysAdmin alerted.

### Pre-conditions

- Infisical server reachable (dev: `http://localhost:8080`) with two projects:
  `TraderBot` (API keys) and `TraderBot Agent Tokens` (per-agent profile tokens).
- `traderbot-service` machine identity provisioned (read/write both projects);
  its bootstrap secret installed in OpenClaw as `INFISICAL_TOKEN` SecretRef.
- Per-agent machine identities (read-only, own token only).
- **Pre-condition (external)**: live Infisical instance and machine identities.
  The protocol verifies them; it does not create them.

### Test procedures

1. **SecretsStore unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_secrets.py tests/test_infisical.py -v
   ```
   Observe: all tests pass; report count and runtime.

2. **Secrets resolution (live Infisical)**:
   ```bash
   traderbot auth list --json
   ```
   Observe: JSON lists the configured services (kalshi, voyage, newsapi, ...)
   with values sourced from Infisical. Report the key names present; never echo
   secret values into the report.

3. **Fallback chain — Infisical down**: stop Infisical (or point the client at
   an unreachable URL), then:
   ```bash
   traderbot auth check --json
   ```
   Observe: secrets still resolve from `~/.traderbot/secrets/secrets.json`
   (0600 perms; integrity check against `secrets.json.sha256` passes), and a
   warning reports Infisical unreachable. Verify perms:
   `stat -c '%a' ~/.traderbot/secrets/secrets.json` → `600`.

4. **Token rotation**:
   ```bash
   traderbot token rotate --agent weather
   traderbot auth check --json
   ```
   Observe: (a) rotation returns a new 256-bit token id and writes it to
   Infisical; (b) the old token immediately fails `traderbot__auth_check`
   (verify via MCP: `openclaw agent --agent weather -m "call traderbot__auth_check"`
   fails with token-invalid before the new token's SecretRef refresh completes);
   (c) after OpenClaw refreshes the SecretRef, auth_check succeeds again.

5. **Rotation failure handling** — with Infisical stopped:
   ```bash
   traderbot token rotate --agent weather
   ```
   Observe: rotation reports failure, current token remains valid, retry is
   scheduled (log line `rotation retry in 15m`), and SysAdmin is alerted.
   Do **not** wait out the 24 h suspend threshold in a test — verify the
   suspend path is unit-tested instead:
   ```bash
   uv run pytest tests/test_rotation_suspend.py -v
   ```

6. **Migration from local store**:
   ```bash
   traderbot auth migrate --from local --dry-run
   ```
   Observe: migration report lists what would move to Infisical; then run
   without `--dry-run` and confirm `traderbot auth list --json` shows the
   migrated entries.

### Metrics

- Unit suite pass rate: **100%**.
- Secret resolution latency: **< 500 ms** for Infisical, **< 100 ms** for local.
- Rotation success: **100%** with Infisical up.
- Old-token invalidation after rotation: **immediate** (0 valid calls with old token).
- Rotation-failure retry interval: exactly **15 minutes** (verify in logs).
- Fleet-suspend threshold: exactly **24 hours** (unit-verified).

### Deliverables

- `traderbot auth list --json` key inventory (names only, no values).
- Fallback-chain proof: auth check output with Infisical down + `stat` output.
- Rotation before/after evidence: old token rejected, new token accepted.
- Migration dry-run + real-run reports.
- Rotation-failure log excerpt showing the 15-minute retry.

### Pass/fail criteria

- **PASS** — resolution, rotation, invalidation, and fallback all behave per
  DD-037; local file perms are `600`; no secret value ever appears in reports.
- **FAIL** — old token remains valid after rotation; fallback fails to serve
  existing secrets with Infisical down; local store file perms are not `600`.

---

## Phase 2 — Always-On Service + Data Pipeline + WS Resilience

> **Status at writing**: designed (DD-016/027/028). Protocol becomes executable
> when `feat/v2-data-pipeline` lands.

**Issue**: #166 · **Design**: `v2docs/05-data-pipeline.md`,
`v2docs/01-architecture-overview.md` · **PR**: `feat/v2-data-pipeline`

### Testing objectives

1. Verify the `traderbot daemon` starts as an always-on service, connects the
   Kalshi WebSocket, and keeps data collection workers running on schedule.
2. Verify WebSocket resilience: disconnection → reconnection with cache seeding
   from REST, no data gaps beyond the outage window, no duplicate workers.
3. Verify health checks pass and the MCP server (same process) serves cached
   data with sub-millisecond local reads.

### Pre-conditions

- Phase 4 deploy (or manual `traderbot deploy`) completed; service unit
  installed. **Pre-condition (external)**: valid Kalshi API credentials for the
  WebSocket handshake; a reachable Kalshi WebSocket endpoint.

### Test procedures

1. **Service starts and stays up**:
   ```bash
   systemctl --user status traderbot
   ```
   Observe: `active (running)`, uptime increasing. Record start time.

2. **Unit + integration suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_data_pipeline.py tests/test_ws_daemon.py -v
   ```
   Observe: all pass; report count.

3. **WebSocket connects and subscribes**:
   ```bash
   journalctl --user -u traderbot -n 200 | grep -i "websocket\|subscribe\|ticker\|orderbook"
   ```
   Observe: log lines showing connection established and channels subscribed:
   `market_lifecycle_v2`, ticker updates, orderbook snapshots, user fills/orders.

4. **Data workers run on schedule** — check worker execution timestamps:
   ```bash
   traderbot daemon status --json
   ```
   Observe: JSON lists each worker (market scanner, news ingest, weather,
   settlement monitor) with last-run timestamps no older than 2× its schedule
   interval (news ≤ 60 min, weather ≤ 2 h, settlement ≤ 2 h).

5. **No REST polling for real-time data** — grep the service log for REST
   market-price calls:
   ```bash
   journalctl --user -u traderbot -n 500 | grep -c "GET /markets"
   ```
   Observe: `0` during steady-state operation (REST only at startup seed and
   after disconnection recovery). Any nonzero count in steady state is a bug.

6. **WS resilience — kill and reconnect**:
   ```bash
   # Simulate network drop on the WS endpoint (firewall rule or kill the socket)
   # then observe recovery:
   journalctl --user -u traderbot -n 200 | grep -i "disconnect\|reconnect\|resubscribe"
   ```
   Observe: reconnect logged within the retry window, all channels re-subscribed,
   and cache re-seeded from REST on reconnect. Data freshness resumes; no worker
   restart or service restart required.

7. **Health check passes**:
   ```bash
   curl -s http://localhost:<port>/health || openclaw agent --agent dev-liaison -m "call traderbot__health"
   ```
   Observe: `"status": "ok"` (or the MCP equivalent) with component states
   (websocket, workers, database) all reported healthy.

8. **Cached-data latency** — from the MCP surface, measure a market-prices call:
   ```bash
   time openclaw agent --agent weather -m "call traderbot__market_prices"
   ```
   Observe: response served from local cache; target **< 10 ms** tool round-trip
   (excluding model latency — use direct MCP invocation if available).

### Metrics

- Service uptime during the test window: **continuous** (no restart).
- WS reconnect: within **5 s** of disconnect detection; all channels re-subscribed.
- Steady-state REST polling calls: **0**.
- Worker freshness: all workers within **2× schedule interval**.
- Cached MCP tool response: **< 10 ms** (local read), **< 1 ms** target for
  WebSocket-cached prices.
- Test pass rate: **100%**.

### Deliverables

- Service status + uptime snapshot.
- WS connect/subscribe log excerpt.
- `traderbot daemon status --json` worker freshness table.
- Reconnect drill evidence (disconnect/reconnect timestamps, re-subscribe log).
- Health check output.
- Latency measurements for cached reads.

### Pass/fail criteria

- **PASS** — service stable, WS connected with all channels, workers fresh,
  steady-state REST polling = 0, reconnect drill succeeds without manual
  intervention, cached reads under threshold.
- **FAIL** — service crashes/restarts during the window; WS fails to reconnect;
  any REST polling for real-time data in steady state; workers starved past 2×
  interval.

---

## Phase 3 — Database Layer + Per-Agent Isolation

> **Status at writing**: designed (DD-032). Protocol becomes executable when
> `feat/v2-database` lands.

**Issue**: #167 · **Design**: `v2docs/08-database-schema.md` · **PR**: `feat/v2-database`

### Testing objectives

1. Verify per-agent per-mode SQLite databases and the global `traderbot.db`
   are created with the unified schema and migrations applied.
2. Verify isolation: an agent can only write to its own current-mode database;
   category agents cannot read other categories' databases; SysAdmin reads all.
3. Verify ChromaDB shared collections use category metadata filtering and
   per-agent collections for decisions/learnings.

### Pre-conditions

- Phase 4 deploy completed (databases created in deploy step 5) or databases
  manually initialized with `traderbot db init`.
- **Pre-condition (external)**: ChromaDB available (local or remote).

### Test procedures

1. **Directory layout exists**:
   ```bash
   find ~/.traderbot -maxdepth 3 -name "*.db" | sort
   ```
   Observe: `traderbot.db` (global), `sysadmin/db/decisions.db`, and
   `paper-{category}/db/decisions.db` per enabled category. Record the full list.

2. **Migration system**: check schema version:
   ```bash
   traderbot db version
   ```
   Observe: a version number matching the current migration head. Then run a
   migration from the previous version on a scratch DB:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_migrations.py -v
   ```
   Observe: up/down migrations apply cleanly; all pass.

3. **Isolation: write to own mode only** — with the weather agent in paper mode,
   place a paper trade, then verify:
   ```bash
   sqlite3 ~/.traderbot/paper-weather/db/decisions.db "SELECT count(*) FROM trades;"
   sqlite3 ~/.traderbot/live-weather/db/decisions.db "SELECT count(*) FROM trades;" 2>&1
   ```
   Observe: paper DB has the trade; the live DB either does not exist yet or has
   zero trades written by this call.

4. **Isolation: cross-category denial** — as the weather agent, attempt a
   read/write on another category's DB via MCP:
   ```bash
   openclaw agent --agent weather -m "call traderbot__positions with category economics"
   ```
   Observe: denied (protocol error) — weather has no access to economics data.

5. **SysAdmin reads all**:
   ```bash
   openclaw agent --agent sysadmin -m "call traderbot__audit"
   ```
   Observe: SysAdmin can enumerate per-agent database status across categories.

6. **ChromaDB collections**:
   ```bash
   traderbot db chroma list
   ```
   Observe: shared collections present: `news`, `data_points`, `market_patterns`,
   `news_signals`, `market_conditions`; plus per-agent `decisions` and
   `learnings` collections. Verify metadata filtering:
   ```bash
   traderbot db chroma query --collection news --where '{"category": "weather"}'
   ```
   Observe: only weather-tagged documents returned.

7. **Connection pooling + PRAGMA** — verify the global DB was opened with the
   expected pragmas via a scratch query:
   ```bash
   sqlite3 ~/.traderbot/traderbot.db "PRAGMA journal_mode; PRAGMA synchronous;"
   ```
   Observe: `wal` and `normal` (or per DD-032 spec). Report actual values.

### Metrics

- Migration tests: **100%** pass.
- Write isolation: **0** writes land in a non-current-mode DB.
- Cross-category access attempts: **100%** denied.
- ChromaDB filter precision: **100%** of returned docs match the category filter.
- DB open latency / pooled connection reuse: **no `database is locked` errors**
  in service logs during the test window.

### Deliverables

- DB inventory (`find` output) and `traderbot db version`.
- Isolation evidence: paper vs live write counts, cross-category denial output.
- ChromaDB collection list + filter query result.
- Migration test summary.

### Pass/fail criteria

- **PASS** — layout + schema + migrations correct; isolation enforced at
  directory, token, tool, and mount levels; ChromaDB filtering returns only the
  requested category.
- **FAIL** — any write to a non-current-mode DB; any cross-category read;
  migration failure; `database is locked` errors during normal operation.

---

## Phase 4 — Deploy Wizard (pipx-first)

> **Status at writing**: designed (DD-001, DD-003–009, DD-022). Protocol becomes
> executable when `feat/v2-deploy-wizard` lands.

**Issue**: #168 · **Design**: `v2docs/02-installation-and-deploy.md` · **PR**: `feat/v2-deploy-wizard`

### Testing objectives

1. Verify `pipx install traderbot` is the sole installation path and the
   `traderbot deploy` 8-step flow completes end-to-end on a clean host.
2. Verify service registration (systemd on macpro-linux) with correct
   template-path resolution, and idempotent re-deploy.
3. Verify legacy install/ scripts and the `bootstrap` command are retired.

### Pre-conditions

- A **clean test user or disposable host** for the deploy run (installing over a
  live installation would invalidate the test). macpro-linux staging user is
  preferred.
- OpenClaw CLI available or installable (`npm install -g @openclaw/cli`).
- **Pre-condition (external)**: Infisical server for step 4a (or accept local
  fallback), valid API tokens for any category selected.

### Test procedures

1. **pipx install**:
   ```bash
   pipx install traderbot
   which traderbot
   traderbot --version
   ```
   Observe: binary resolves; version prints. Verify no venv/git-clone install
   path remains: `ls install/` must not exist in the installed package.

2. **Legacy commands retired**:
   ```bash
   traderbot bootstrap --help 2>&1
   ls ~/worktrees/TraderBot/main/install 2>&1
   ```
   Observe: `bootstrap` is not a recognized command; `install/` directory is gone.

3. **Deploy flow — Step 1 (OpenClaw config)** — run the wizard:
   ```bash
   traderbot deploy
   ```
   Observe step 1: OpenClaw detected/installed, `openclaw setup` invoked,
   `openclaw gateway status` reports running.

4. **Step 2 (SysAdmin setup)** — observe: sysadmin workspace files injected
   (`~/.openclaw/workspace/sysadmin/` contains AGENTS.md, SOUL.md, TOOLS.md,
   IDENTITY.md, HEARTBEAT.md, USER.md, SESSION-STATE.md, `.learnings/`); exactly
   one cron job registered:
   ```bash
   openclaw cron list
   ```
   Observe: `sysadmin-bootstrap` with `--at 5m`, `--delete-after-run`.
   Then verify profile created and auth works:
   ```bash
   traderbot auth check --json
   ```

5. **Step 3 (Category selection)** — select weather; observe agent created and
   workspace injected:
   ```bash
   openclaw agents list
   ls ~/.openclaw/workspace/weather/
   openclaw doctor
   ```
   Observe: `weather` agent present with workspace files; `openclaw doctor`
   reports no blocking issues.

6. **Step 4 (Infisical + API tokens)** — observe: step 4a health-checks
   Infisical (or falls back); 4b validates each entered token against its
   service before storing (a deliberately wrong OpenWeatherMap key must be
   **rejected**); 4c creates the `traderbot-service` machine identity and stores
   `INFISICAL_TOKEN` SecretRef.

7. **Step 5 (Database creation)** — observe DB creation per
   [Phase 3 procedure 1](#test-procedures); verify writability:
   ```bash
   touch ~/.traderbot/sysadmin/db/decisions.db
   ```
   Observe: writable; remove the test file afterwards.

8. **Step 6 (Backfill)**:
   ```bash
   traderbot backfill --months 6 --json
   ```
   Observe: JSON progress reporting; completes without error; verify data lands
   in the data cache.

9. **Step 7 (Simulation start)** — observe agents are in `backtest` mode:
   ```bash
   traderbot profile list --json
   ```
   Observe: weather profile mode is `backtest`, not `paper`.

10. **Step 8 (Verification summary)** — observe the final summary prints agent
    names, profiles, token status, and health; each line verified by:
    ```bash
    traderbot deploy --verify
    ```
    Observe: idempotent re-run reports everything already in place.

11. **Service registration + template resolution**:
    ```bash
    systemctl --user status traderbot
    grep -o "ExecStart=.*" ~/.config/systemd/user/traderbot.service
    ```
    Observe: unit present, `ExecStart` points at the resolved pipx binary path
    (`$(which traderbot) daemon`), and the service is active.

### Metrics

- Deploy completion: **8/8 steps** succeed on first attempt.
- pipx-install → running service: **< 10 minutes** wall clock.
- Invalid API token rejection: **100%** of deliberately bad tokens rejected at entry.
- Idempotency: `traderbot deploy --verify` re-run reports **no changes needed**.
- Service `ExecStart` path: matches `which traderbot` exactly.

### Deliverables

- Deploy wizard transcript (step-by-step output).
- `openclaw cron list`, `openclaw agents list`, `openclaw doctor` outputs.
- Service unit content + resolved paths.
- Backfill JSON summary.
- Idempotent re-run output.

### Pass/fail criteria

- **PASS** — full 8-step flow completes on the clean host; tokens validated;
  service registered and running; re-run idempotent; legacy paths gone.
- **FAIL** — any step fails; invalid tokens accepted; service unit broken or
  wrong path; `deploy --verify` reports drift on a fresh deployment.

---

## Phase 5 — Docker Sandbox for Category Agents

> **Status at writing**: designed (DD-003, DD-010, DD-036). Protocol becomes
> executable when `feat/v2-docker-sandbox` lands.

**Issue**: #169 · **Design**: `v2docs/02-installation-and-deploy.md`,
`v2docs/04-security-and-auth.md` ("Per-Agent Isolation") · **PR**: `feat/v2-docker-sandbox`

### Testing objectives

1. Verify the sandbox image builds from the shipped Dockerfile and the
   `generate_docker_run_command()` output runs a correct, isolated container.
2. Verify bind mounts: agent data dir RW, workspace RO, **no blanket
   `~/.traderbot/` mount**, no secrets/keys/tokens mounted.
3. Verify isolation at runtime: the container cannot reach host-only paths,
   other agents' data, or the host Docker socket.

### Pre-conditions

- Docker installed and running on macpro-linux.
- OpenClaw sandbox configs deployed per agent (`sandbox: { mode: "all" }` for
  category agents; SysAdmin unsandboxed per DD-036).
- **Pre-condition (external)**: Docker daemon; base image pull access
  (`python:3.12-slim-bookworm`).

### Test procedures

1. **Image builds**:
   ```bash
   cd ~/worktrees/TraderBot/main && docker build -f install/docker/Dockerfile -t traderbot-sandbox:test .
   ```
   Observe: build completes; report duration. Verify base:
   `docker inspect traderbot-sandbox:test --format '{{.Config.Image}}'` matches
   `python:3.12-slim-bookworm`.

2. **Generated run command is valid** — unit test the generator and print the
   command for inspection:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_sandbox_config.py -v
   uv run python -c "from traderbot.sandbox import generate_docker_run_command; print(generate_docker_run_command('weather'))"
   ```
   Observe: all tests pass; the printed command contains exactly:
   `-v ~/.traderbot/paper-weather:/data` (RW), `-v ~/.openclaw/workspace/weather:/workspace:ro`
   (RO), and **no** `-v ~/.traderbot` blanket mount, no `.env`/`keys`/`tokens.enc`
   mounts, no `-v /var/run/docker.sock`.

3. **Sandbox runtime verification** — start a weather sandbox container from the
   generated command and verify inside it:
   ```bash
   docker exec <container> sh -c 'ls /data && ls /workspace && echo SANDBOX_OK'
   docker exec <container> sh -c 'cat ~/.traderbot/tokens.enc 2>&1'
   docker exec <container> sh -c 'cat /.dockerenv 2>&1'
   docker exec <container> sh -c 'curl -s http://host.docker.internal:8080 2>&1 || echo HOST_NET_BLOCKED'
   ```
   Observe: `/data` and `/workspace` present with expected contents; the
   second command fails (host `~/.traderbot` not mounted); Docker socket access
   is absent; direct host network access is not available from the container.

4. **Cross-agent isolation** — from the weather container, attempt to read the
   economics agent's data dir:
   ```bash
   docker exec <container> sh -c 'ls /workspace/../economics 2>&1'
   ```
   Observe: not accessible — economics data is not mounted into the weather
   container.

5. **SysAdmin unsandboxed (DD-036)** — verify the sysadmin agent runs on the
   host, not in a container:
   ```bash
   openclaw agent --agent sysadmin -m "run: echo $HOSTNAME && pwd"
   ```
   Observe: host hostname/paths, not a container id.

6. **Security test suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_sandbox_security.py -v
   ```
   Observe: all pass.

### Metrics

- Image build: **succeeds**, ≤ 5 min on first build.
- Bind mounts: **exact** — RW on agent data, RO on workspace, zero disallowed
  mounts.
- Container escape probes: **0** successful (all `cat`/`curl`/`ls` probes fail
  as expected).
- Cross-category mount leak: **0**.
- Security suite pass rate: **100%**.

### Deliverables

- Build log + image inspect output.
- Printed `docker run` command (sanitized) for audit.
- Per-probe runtime evidence (pass/fail per command above).
- Security suite summary.

### Pass/fail criteria

- **PASS** — image builds; generated command has exactly the required mounts
  and no forbidden ones; every runtime isolation probe fails as intended.
- **FAIL** — any forbidden mount present (blanket `~/.traderbot`, docker.sock,
  secrets); any probe unexpectedly succeeds; container can read another agent's
  data.

---

## Phase 6 — Category Toolkits (Weather First)

> **Status at writing**: designed (DD-033/035). Protocol becomes executable when
> `feat/v2-weather-toolkit` lands.

**Issue**: #170 · **Design**: `v2docs/09-mcp-tools.md` (Weather Toolkit),
`v2docs/05-data-pipeline.md` · **PR**: `feat/v2-weather-toolkit`

### Testing objectives

1. Verify the four weather tools (`weather_forecast_prob`, `weather_accuracy`,
   `weather_seasonal_context`, `weather_decision_brief`) work over MCP with
   real data providers (NWS, Open-Meteo).
2. Verify category isolation: the weather tools are callable only by agents
   with the weather category enabled; other agents get a protocol error.
3. Verify response quality: calibrated probabilities with confidence intervals,
   Brier scores, seasonal distributions — not hardcoded values.

### Pre-conditions

- Weather category deployed (deploy step 3); weather profile has
  `enabled_categories: ["weather"]` and tool permissions for all four weather
  tools.
- Data providers (NWS, Open-Meteo) reachable from macpro-linux.
- **Pre-condition (external)**: NWS and Open-Meteo APIs reachable (public, no
  key required); optionally OpenWeatherMap key if configured as a source.

### Test procedures

1. **Provider unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_weather_toolkit.py tests/test_weather_providers.py -v
   ```
   Observe: all pass; report count.

2. **Weather tools live over MCP** — as the weather agent:
   ```bash
   openclaw agent --agent weather -m "call traderbot__weather_forecast_prob with ticker KXHIGHTCHI-26JUN02-T81"
   openclaw agent --agent weather -m "call traderbot__weather_accuracy with city Chicago"
   openclaw agent --agent weather -m "call traderbot__weather_seasonal_context with city Chicago target_date 2026-06-02"
   openclaw agent --agent weather -m "call traderbot__weather_decision_brief with ticker KXHIGHTCHI-26JUN02-T81"
   ```
   Observe per tool:
   - `forecast_prob`: returns `estimated_prob` in [0,1], a `confidence_interval`,
     `sources` array with real source weights, `method: "calibrated_logistic"`.
   - `accuracy`: returns `sample_size ≥ 1`, real `brier_score` and
     `mean_abs_error_f`, per-lead-time breakdown.
   - `seasonal_context`: returns a `historical_distribution` with real
     `sample_size` and percentiles, plus a `recent_anomaly`.
   - `decision_brief`: returns the assembled brief including market edge.

3. **Real data, not stubs** — verify values change over time / are grounded:
   run `forecast_prob` for two different lead times and confirm the
   `confidence_interval` widens with lead time (lead-time decay behavior from
   DD-035). Record both responses.

4. **Category isolation enforced** — as `dev-liaison` (no enabled categories):
   ```bash
   openclaw agent --agent dev-liaison -m "call traderbot__weather_forecast_prob with ticker KXHIGHTCHI-26JUN02-T81"
   ```
   Observe: **denied** — server-side category check in `auth.py` rejects the
   call even though dev-liaison's token resolves. This is a protocol error, not
   a data error.

5. **Tool permission isolation** — verify the weather agent **cannot** call
   tools outside its allowlist (e.g., `traderbot__audit` reserved for SysAdmin):
   ```bash
   openclaw agent --agent weather -m "call traderbot__audit"
   ```
   Observe: denied.

6. **MCP tool schema sync** — verify the OpenClaw tool surface matches the
   server's declared input schemas:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_tool_schema_sync.py -v
   ```
   Observe: all pass.

### Metrics

- Tool call success rate: **100%** for the weather agent.
- `forecast_prob` probability range validity: **100%** in [0,1].
- Lead-time decay: CI width at lead 4 > CI width at lead 0 (verified on real data).
- Unauthorized call rejection: **100%** (dev-liaison weather call, weather
  agent audit call).
- Provider test pass rate: **100%**.

### Deliverables

- Provider + toolkit test summaries.
- Live responses for all four tools (sanitized).
- Lead-time decay comparison (two responses).
- Isolation denial evidence for both unauthorized paths.

### Pass/fail criteria

- **PASS** — all four tools return grounded, schema-valid responses; category
  and tool isolation reject every unauthorized call; no hardcoded/stub values
  in responses.
- **FAIL** — any tool returns a stub/hardcoded response; any unauthorized call
  succeeds; probability outside [0,1]; lead-time decay absent.

---

## Phase 7a — Backtesting Engine + SimulationClock

> **Status at writing**: designed (DD-019/020). Protocol becomes executable when
> `feat/v2-backtesting` lands.

**Issue**: #171 · **Design**: `v2docs/06-trading-and-simulation.md`
(Backtesting, DD-019) · **PR**: `feat/v2-backtesting`

### Testing objectives

1. Verify the `SimulationClock` advances on a sped-up timeline and all MCP data
   calls return **as-of** the simulated time (no look-ahead).
2. Verify backtest runs complete with valid performance metrics (Sharpe, win
   rate, sample size) and results persist.
3. Verify the same tools/response format are used in backtest as in paper/live
   (mode-aware, agent-agnostic).

### Pre-conditions

- Weather category deployed in `backtest` mode with `traderbot__trade`,
  `traderbot__scan`, `traderbot__analyze`, `traderbot__market_edge` allowed.
- 6-month backfill completed (deploy step 6).
- **Pre-condition (external)**: historical data available (Kalshi history,
  Open-Meteo archive, NWS).

### Test procedures

1. **Backtest engine unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_backtesting.py tests/test_simulation_clock.py -v
   ```
   Observe: all pass; report count.

2. **Phase A: statistical backtest**:
   ```bash
   traderbot backtest --category weather --months 6 --json
   ```
   Observe: JSON report with performance metrics (Sharpe, win rate, sample size,
   max drawdown, Brier score) and per-market results. Report the key numbers;
   verify sample_size ≥ 30 and metrics are computed, not defaulted.

3. **SimulationClock advances and drives as-of queries** — with a backtesting
   weather agent active, observe the clock:
   ```bash
   traderbot sim status --json
   ```
   Observe: `sim_time` is in the historical window and **advances** between two
   readings taken minutes apart (e.g., +X simulated hours per real minute).
   Record both timestamps and the advance rate.

4. **No look-ahead** — at a known historical point, call the scan tool and
   confirm data freshness respects sim time:
   ```bash
   openclaw agent --agent weather -m "call traderbot__scan"
   ```
   Observe: the response's data timestamps are all ≤ `sim_time`; no future-dated
   news/forecasts. Verify forecast for the simulation target reflects the
   forecast available at sim_time (lead time = target − sim_time), not today's
   forecast.

5. **Mode-aware trade routing** — as the weather agent in backtest mode:
   ```bash
   openclaw agent --agent weather -m "call traderbot__trade with ticker KXHIGHTCHI-26JUN02-T81 direction yes quantity 5"
   ```
   Observe: fill returned with `"mode": "backtest"`, fill price consistent with
   the sim-time orderbook, and the trade persisted in the backtest DB:
   ```bash
   sqlite3 ~/.traderbot/paper-weather/db/decisions.db "SELECT count(*) FROM trades;"
   ```
   Observe: count increments by exactly the number of trades placed.

6. **Phase B: behavioral simulation (smoke)** — trigger a short behavioral run
   and observe SysAdmin driving the agent via `sessions_send`:
   ```bash
   traderbot backtest --category weather --phase B --days 1 --json
   ```
   Observe: the agent's decision loop executes at accelerated sim time with
   real LLM calls, and completes with a summary of decisions taken. (Full 6-month
   Phase B is 8–16 h; the 1-day smoke run verifies the mechanism.)

7. **Consistency of tool surface** — compare the backtest response shape with
   the paper-mode response for the same tool (should be identical except `mode`).

### Metrics

- Unit suite pass rate: **100%**.
- Phase A backtest: completes with **sample_size ≥ 30**, no NaN metrics.
- Sim clock advance rate: **verifiable positive** (recorded ratio, e.g.,
  X:1 simulated:real).
- Look-ahead violations: **0** (all data timestamps ≤ sim_time).
- Backtest trades persisted: **1:1** with trades placed.
- Phase B smoke run: completes within the configured window.

### Deliverables

- Backtest JSON result (metrics table).
- Two `sim status` snapshots showing clock advance.
- Scan response with timestamp check against sim_time.
- Trade fill + DB count evidence.
- Phase B smoke summary.

### Pass/fail criteria

- **PASS** — clock advances; zero look-ahead; metrics valid; trades persist to
  the correct DB; tool surface identical across modes.
- **FAIL** — any future-dated data at sim_time; metrics NaN/zero; fill at a
  price inconsistent with sim-time orderbook; trade lost on persistence.

---

## Phase 7b — Paper/Live Trading + Risk Enforcement

> **Status at writing**: designed (DD-013/021). Protocol becomes executable when
> `feat/v2-trading` lands.

**Issue**: #172 · **Design**: `v2docs/06-trading-and-simulation.md`
(Paper Trading, Live Trading) · **PR**: `feat/v2-trading`

### Testing objectives

1. Verify paper trades simulate fills locally (no Kalshi submission) with
   realistic slippage, correct balance accounting, and settlement.
2. Verify risk enforcement: immutable hard limits, circuit breaker states, and
   block-on-breach behavior.
3. Verify live trading (if credentials permit) submits real orders and
   reconciles with Kalshi.

### Pre-conditions

- Weather agent promoted to **paper** mode.
- **Pre-condition (external)**: Kalshi API credentials present (paper uses
  market data + orderbook; live uses order submission). Live-trade tests are
  **skipped** if no valid live credentials — paper is the primary verification.

### Test procedures

1. **Trading unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_trading.py tests/test_risk.py -v
   ```
   Observe: all pass; report count.

2. **Paper fill simulation** — as weather (paper mode):
   ```bash
   openclaw agent --agent weather -m "call traderbot__trade with ticker KXHIGHTCHI-26JUN02-T81 direction yes quantity 5 price 34"
   ```
   Observe: response has `"status": "filled"`, `"mode": "paper"`, a
   `fill_price_cents` near the requested price with non-negative
   `slippage_cents`, and a reduced `remaining_balance_cents`. Verify no Kalshi
   order was created (no order-id in the response; no REST order POST in logs).

3. **Paper balance accounting** — place two opposing trades and verify balance:
   ```bash
   sqlite3 ~/.traderbot/paper-weather/db/decisions.db "SELECT remaining_balance_cents FROM portfolios ORDER BY rowid DESC LIMIT 1;"
   ```
   Observe: balance equals `initial − cost(at open) + settlement_payouts`; then
   run settlement for a settled market and confirm a payout of +100¢ per winning
   contract appears. Verify: `remaining = initial - cost + payouts` holds exactly.

4. **Risk limit enforcement — position cap**: configure a scratch profile with
   `max_position_per_market_pct` at a tiny value, then attempt an oversized
   trade. Observe: **blocked** with a risk error, no DB write.

5. **Circuit breaker states**:
   ```bash
   traderbot halt --json
   ```
   Observe: JSON with current breaker state (`GREEN`/`YELLOW`/`RED`/`FULL_STOP`)
   and per-limit values. Trigger a breach via a scratch profile (e.g., daily
   loss past `max_daily_loss_pct`): state moves `GREEN → RED`; retry the halt
   and confirm the state persists. Then reset via the approved operator path
   (SysAdmin `traderbot halt --reset` after investigation).

6. **YELLOW reduces sizing** — with a near-threshold scratch profile, verify the
   breaker returns `YELLOW` and a trade is rejected at full size but accepted at
   reduced size (per DD-021).

7. **Live trading (conditional)** — only with valid live credentials and on
   **SysAdmin-approved** conditions:
   ```bash
   traderbot auth check --json
   ```
   Observe: kalshi credential status `valid`. Then a single 1-contract live
   paper-threshold trade via `traderbot__trade` and confirm: real order
   submission, order confirmation from Kalshi, and position recorded in
   `live-weather/db/decisions.db`. Report the order id (never API secrets).

8. **Settlement reconciliation** — run:
   ```bash
   traderbot reconcile-settlements --agent weather
   ```
   Observe: settled markets synced; report count of reconciled settlements.

### Metrics

- Paper fill simulation: **100%** success, slippage within [0, expected spread].
- Balance identity holds: `remaining = initial − cost + payouts` **exactly**
  (assert on test data).
- Risk-limit breach blocks: **100%** of oversize trades blocked with no DB write.
- Breaker state transitions: correct per DD-021 (GREEN→YELLOW→RED→FULL_STOP).
- Live (if tested): order accepted, position recorded 1:1, reconciliation delta = 0.

### Deliverables

- Fill response JSON (paper) + log proof of no Kalshi submission.
- Balance ledger excerpt proving the identity.
- Risk-breach block evidence (error + no-write confirmation).
- `traderbot halt --json` snapshots across states.
- Live-trade confirmation + reconciliation report (if performed).

### Pass/fail criteria

- **PASS** — paper fills simulate without Kalshi submission; balance identity
  exact; all risk breaches blocked; breaker states correct.
- **FAIL** — paper order leaked to Kalshi; balance arithmetic wrong; any
  oversize trade fills; breaker fails to trip on breach.

---

## Phase 7c — Mode Transitions + Lifecycle

> **Status at writing**: designed (DD-017). Protocol becomes executable when
> `feat/v2-lifecycle` lands.

**Issue**: #173 · **Design**: `v2docs/03-agents-and-lifecycle.md`
(Lifecycle States) · **PR**: `feat/v2-lifecycle`

### Testing objectives

1. Verify the `BACKTESTING → PAPER → LIVE → SUSPENDED` state machine,
   including demotion paths.
2. Verify explicit human/SysAdmin confirmation is required for promotion, and
   demotion/suspension happen automatically on risk breach.
3. Verify lifecycle transitions are reflected in profiles, DB routing, and
   cron/heartbeat job swaps.

### Pre-conditions

- Weather agent in `backtest` mode with a passing backtest record meeting the
  deployment bar (Sharpe ≥ 1.0, win rate ≥ 55%, ≥ 30 trades).
- **Pre-condition (external)**: promotion requires SysAdmin action — this
  protocol drives SysAdmin via `sessions_send`; live promotion additionally
  requires valid Kalshi credentials.

### Test procedures

1. **Lifecycle unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_lifecycle.py -v
   ```
   Observe: all pass; report count.

2. **Initial state**:
   ```bash
   traderbot profile list --json
   ```
   Observe: weather profile `mode: "backtest"`. Confirm invalid direct
   transition is rejected:
   ```bash
   traderbot profile update weather --mode live
   ```
   Observe: **rejected** — backtest→live skips paper and is not allowed.

3. **Promotion backtest→paper** — drive SysAdmin to evaluate and promote:
   ```bash
   openclaw agent --agent sysadmin -m "evaluate weather backtest metrics and, if the deployment bar is met, promote to paper trading"
   ```
   Observe: SysAdmin first **verifies the metrics** (Sharpe ≥ 1.0, win rate
   ≥ 55%, ≥ 30 trades), then confirms promotion explicitly. After promotion:
   - `traderbot profile list --json` shows `mode: "paper"`.
   - A paper trade routes to `paper-weather` (Phase 7b procedure 2).
   - Cron jobs swap: `openclaw cron list` shows backtest jobs removed, paper
     jobs registered.

4. **Demotion on metrics fall** — with the weather agent in paper, inject (via a
   scratch profile or test hook) metrics below threshold; observe SysAdmin
   demoting back to backtest and profile mode returning to `backtest`.

5. **Promotion paper→live (conditional)** — only with live credentials and
  SysAdmin confirmation: promote weather to live and verify:
   - `traderbot profile list --json` shows `mode: "live"`.
   - Trades route to `live-weather/db/decisions.db`.
   - Paper DB becomes read-only reference for the agent.
   - SysAdmin heartbeat switches to 30-minute cadence.

6. **Suspension on circuit breaker** — trigger a FULL_STOP (scratch profile
   breaching `max_drawdown_pct`):
   ```bash
   traderbot halt --json
   ```
   Observe: state `FULL_STOP`; profile mode becomes `suspended`; all trading
   tools block:
   ```bash
   openclaw agent --agent weather -m "call traderbot__trade with ticker KXHIGHTCHI-26JUN02-T81"
   ```
   Observe: blocked with suspension error.

7. **Recovery path** — SysAdmin investigates (suspension report), then re-runs
   the agent through backtest validation before resuming. Observe: the agent
   cannot resume at paper/live directly — it must pass backtest again.

### Metrics

- State machine transitions: **all valid transitions** allowed; **all invalid
  transitions** rejected (verify the full matrix in the unit suite).
- Promotion requires confirmation: **100%** of promotions blocked without
  explicit SysAdmin confirmation.
- Demotion/suspension automation: triggers within **1 heartbeat cycle** of a
  breach.
- DB routing follows mode: **1:1** (paper→paper DB, live→live DB).
- Cron job swap: backtest jobs gone, paper/live jobs present after each
  transition.

### Deliverables

- Profile mode snapshots across each transition.
- SysAdmin promotion confirmation transcript (metrics check + explicit action).
- Cron job list before/after each transition.
- Suspension trigger evidence + blocked-trade error.
- Recovery-path transcript.

### Pass/fail criteria

- **PASS** — all legal transitions verified; illegal ones rejected; promotions
  gated on confirmation; breaches auto-demote/suspend within one heartbeat;
  DB routing and cron jobs follow mode.
- **FAIL** — any illegal transition succeeds; promotion without confirmation;
  breach does not demote/suspend; trading continues while suspended.

---

## Phase 8 — Self-Improvement Framework

> **Status at writing**: designed (DD-018/038). Protocol becomes executable when
> `feat/v2-self-improvement` lands.

**Issue**: #174 · **Design**: `v2docs/07-self-improvement.md` · **PR**: `feat/v2-self-improvement`

### Testing objectives

1. Verify the 5-round improvement cycle runs: debate (Rounds 1–3), research
   (Round 4), selection/implementation (Round 5).
2. Verify learning promotion: findings in `.learnings/` promote after 3+
   recurrences, and Errors.md items recur 3× before investigation.
3. Verify the experiment harness runs A/B experiments with validatable
   hypotheses and reports results.

### Pre-conditions

- SysAdmin, Dev-Liaison, and at least one category agent deployed.
- `sessions_spawn`/`sessions_send`/`sessions_yield` allowed for SysAdmin;
  `sessions_send` in debate-sub `alsoAllow`.
- `gumbel-ai/agent-debate` framework available to the orchestrator.
- **Pre-condition (external)**: LLM providers for multi-model debate
  (SysAdmin + category subs with model overrides).

### Test procedures

1. **Self-improvement unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_self_improvement.py tests/test_learnings.py -v
   ```
   Observe: all pass; report count.

2. **Learning capture and recurrence counting** — create a `.learnings/` entry
   in the weather workspace, then simulate recurrences via the harness:
   ```bash
   traderbot learnings status --agent weather
   ```
   Observe: entry tracked with recurrence count; at **3+ recurrences** the entry
   is flagged `promote-ready`. Verify the promotion flag flips only at count ≥ 3.

3. **Error recurrence gating** — append an error to `ERRORS.md` (scratch),
   verify it is **not** auto-investigated until 3 recurrences:
   ```bash
   traderbot errors status --agent weather
   ```
   Observe: gating works (count < 3 → no action; ≥ 3 → flagged for SysAdmin).

4. **Debate cycle — Round 1** — drive SysAdmin to start an improvement cycle:
   ```bash
   openclaw agent --agent sysadmin -m "start improvement debate for weather category, round 1"
   ```
   Observe: 4 debate subs spawned via `sessions_spawn` (2 category subs +
   2 SysAdmin subs, `maxSpawnDepth: 1`); each produces **10 suboptimal
   outcomes** with evidence; central coordination yields **40 unique root
   causes** (deduplicated). Report the dedup count.

5. **Round 2 — white papers + cross-examination** — observe: each proposal gets
   a white paper (hypothesis, KPIs, experimental design); sequential
   cross-examination runs with examiner/defendant turns; Dev-Liaison provides a
   **top-line feasibility check**.

6. **Round 3 — blind vote** — observe: all 6 participants cast one blind vote
   each; ties trigger a re-vote with final evidence statements; field narrows to
   **5 proposals**.

7. **Round 4 — research + experiment design** — observe: surviving proposals
   get code-state review, conceptual research, GitHub precedent search, and a
   statistical experiment design that can falsify the hypothesis.

8. **Round 5 — selection and implementation** — observe: SysAdmin selects the
   top proposal; implementation path matches the root-cause classification
   (GitHub issue for TraderBot-code causes, workspace update for agent-behavior
   causes, both for mixed). Verify a GitHub issue (or workspace diff) appears.

9. **Experiment harness** — run a scratch A/B experiment:
   ```bash
   traderbot experiment run --name scratch-ab --variant A --variant B --days 1 --json
   ```
   Observe: both variants execute, results report per-variant metrics, and the
   harness returns a verdict on statistical validity (no claim of significance
   from tiny samples).

### Metrics

- Round 1 dedup: **40 unique root causes** from 4×10.
- Round 3 field: narrowed to exactly **5 proposals**.
- Learning promotion: flag flips exactly at **3 recurrences**.
- Error gating: investigation triggers exactly at **3 recurrences**.
- Round 5: **1 selection**, implementation artifact produced (issue or diff).
- Experiment harness: runs to completion, reports metrics + validity caveat.

### Deliverables

- Unit test summaries.
- `.learnings/` recurrence/promotion status output.
- Debate round transcripts (or structural summaries per round).
- Round-3 vote result and Round-5 selection + artifact.
- Experiment run JSON.

### Pass/fail criteria

- **PASS** — all 5 rounds complete in order with expected counts; learning and
  error recurrence thresholds honored; experiment harness reports honestly
  (incl. statistical caveats).
- **FAIL** — any round skipped; dedup/vote/selection counts off; learnings
  promote before 3 recurrences; harness claims significance without validity.

---

## Phase 9 — Additional Categories

> **Status at writing**: designed (DD-033/035). Protocol becomes executable as
> each category PR (`feat/v2-{category}-toolkit`) lands. Run this protocol once
> **per category**.

**Issue**: #175 · **Design**: `v2docs/09-mcp-tools.md` (category toolkits),
`v2docs/05-data-pipeline.md` (providers) · **PRs**: `feat/v2-economics-toolkit`,
`feat/v2-sports-toolkit`, `feat/v2-crypto-toolkit`, `feat/v2-politics-toolkit`

### Testing objectives

1. Verify each new category agent deploys, isolates, and trades correctly —
   profile, workspace, sandbox, permissions.
2. Verify the category's toolkit tools work over MCP with real providers
   (FRED, TheSportsDB, CoinGecko, NewsAPI+Reddit).
3. Verify cross-category isolation for the new category (no data or tool leaks).

### Pre-conditions

- The category under test is enabled at deploy (or added via
  `traderbot deploy` step 3 re-run).
- **Pre-condition (external)**: the category's provider credentials are valid:
  FRED key (economics), TheSportsDB key (sports), CoinGecko (crypto, tier
  detection), NewsAPI + Reddit (politics). These must be provisioned before
  testing; the protocol only validates them.

### Test procedures

For each category `{cat}` in {economics, sports, crypto, politics, ...}:

1. **Deploy and workspace**:
   ```bash
   openclaw agents list | grep {cat}
   ls ~/.openclaw/workspace/{cat}/
   traderbot profile list --json | grep {cat}
   ```
   Observe: agent exists, workspace files injected, profile created with
   `enabled_categories: ["{cat}"]` and mode `backtest`.

2. **Sandbox running**:
   ```bash
   docker ps --format '{{.Names}}' | grep {cat}
   ```
   Observe: a sandbox container for the category is running (Phase 5
   properties apply).

3. **Provider + toolkit unit suite**:
   ```bash
   cd ~/worktrees/TraderBot/main && uv run pytest tests/test_{cat}_toolkit.py tests/test_{cat}_providers.py -v
   ```
   Observe: all pass; report count.

4. **Toolkit live over MCP** — as the {cat} agent, call each of the category's
   toolkit tools with a real ticker/query and verify grounded responses:
   - Economics: FRED indicator query (e.g., GDP, CPI series) returns a real
     value with a timestamp.
   - Sports: team/market query against TheSportsDB returns real event data.
   - Crypto: price query against CoinGecko returns a real price with freshness.
   - Politics: news context query returns real recent articles with timestamps.
   Observe: values are grounded and current; no stub data.

5. **Provider credentials validated** — for each category, verify a bad
   credential is rejected:
   ```bash
   traderbot auth set-key {cat}_provider api_key INVALID && traderbot auth check --json
   ```
   Observe: `invalid` status for the provider. Restore the real key afterwards
   and re-check to `valid`.

6. **Cross-category isolation** — as the weather agent, attempt the new
   category's tools:
   ```bash
   openclaw agent --agent weather -m "call traderbot__{cat}_<tool>"
   ```
   Observe: **denied** (weather has no {cat} category). And the reverse — {cat}
   agent denied weather tools.

7. **Backtest smoke for the category**:
   ```bash
   traderbot backtest --category {cat} --months 6 --json
   ```
   Observe: completes with metrics (Phase 7a criteria); report Sharpe/win rate/
   sample size.

8. **Paper-trade smoke (conditional on Phase 7b)** — with the {cat} agent
   promoted to paper, place one paper trade and verify routing to
   `paper-{cat}/db/decisions.db` with `"mode": "paper"`.

### Metrics

- Deploy artifacts: agent + workspace + profile **all present**.
- Toolkit + provider suite: **100%** pass.
- Grounded responses: **100%** of live tool calls return real, current data.
- Credential validation: bad key → `invalid`, restored key → `valid`.
- Cross-category denial: **100%** of cross-category tool calls rejected.
- Backtest smoke: completes, sample_size ≥ 30, no NaN metrics.

### Deliverables

- Per-category deploy inventory (agent, workspace, profile).
- Provider + toolkit test summaries.
- Live tool responses (grounded data, sanitized).
- Credential validation before/after evidence (bad → invalid → valid).
- Cross-category denial evidence.
- Backtest metrics table.

### Pass/fail criteria

- **PASS** — every category in the phase deploys, isolates, passes its suites,
  returns grounded data, and completes the backtest smoke.
- **FAIL** — any category fails to deploy/isolate; any toolkit returns stub
  data; bad credentials accepted; cross-category calls succeed.

---

## Issue Escalation

When a test fails:

1. Capture the exact failing command, full output, and reproduction steps.
2. Open a GitHub issue on `JsonDaRula69/TraderBot` with the phase, test number,
   environment snapshot, and reproduction block. Reference the phase issue
   (e.g., "blocks #166").
3. Send the report to Sisyphus with the FAIL verdict and the issue link.
4. Do **not** attempt to fix code — dev-liaison does not write production code.
   Implementation belongs to the AutoDev team via the Layer 3 loop
   (DD-034 §10 webhook wake signal `autodev:wake`).
5. A phase is not complete until either all tests pass, or every failure has an
   open issue with reproduction steps and a documented workaround (non-critical
   only).

### Critical-path definition

A test is **critical** when its failure implies a security, isolation, data
integrity, or money-safety violation:

- Any token leakage or auth bypass (Phase 1.1, 1.5).
- Any cross-agent/cross-category data or tool access (Phases 3, 5, 6, 9).
- Any risk-limit or circuit-breaker bypass (Phase 7b, 7c).
- Any look-ahead in backtesting (Phase 7a).
- Any real-money order placed incorrectly (Phase 7b live).

Critical failures block the phase regardless of other results.
