# Deploy Wizard Steps 1-8

`traderbot deploy` implements all eight ordered deploy steps. Steps 6 and 8 compose the exact standalone typed backfill and read-only verification boundaries. Step 7 remains an intentional Phase 5 sandbox stub: it starts no sandbox or simulation and mutates no Gateway scheduling state.

## Interactive Mode

Run `traderbot deploy`. A Rich table lists the exact nine `MarketCategory` values: `weather`, `economics`, `crypto`, `sports`, `politics`, `entertainment`, `financial`, `world`, and `other`. After selection, read-only inventory requires the pre-existing `main` agent and shows selected-agent workspaces; deploy never creates `main`. Existing paths are adopted unchanged. For every missing selected category agent, Rich shows a proposed absolute path and requires explicit creation confirmation. Installation, baseline setup, and dormant `0m` heartbeat changes have separate confirmations. Category profiles always start in `backtest` mode. The stricter existing-agents-only contract plus per-agent paper/live, channel, and same-name Telegram requirements are deferred to Phase 4b.

## Config Mode

`traderbot deploy --config deploy.json --json` is prompt-free. It requires explicit approval flags and an absolute path for every selected agent that may be missing:

```json
{
  "categories": ["weather", "crypto"],
  "mode": "backtest",
  "kalshi_environment": "demo",
  "infisical_url": "http://127.0.0.1:8080",
  "tokens": {
    "kalshi_api_key_env": "TRADERBOT_DEPLOY_KALSHI_KEY",
    "kalshi_private_key_pem_env": "TRADERBOT_DEPLOY_KALSHI_PEM"
  },
  "category_workspaces": {
    "crypto": "/srv/openclaw/agents/crypto"
  },
  "approvals": {
    "install_openclaw": false,
    "setup_openclaw": false,
    "create_agents": true,
    "heartbeat_change": true
  },
  "heartbeat_every": "0m"
}
```

In this example, `weather` already exists and therefore needs no path assertion; `crypto` may be missing and has an approved creation path. `sysadmin_workspace` and paths for existing selected agents are optional equality assertions, never rebind requests. Assertions must be absolute and non-linked. The token fields are environment variable names, not secret values. Raw token fields, incomplete reference pairs, invalid variable names, remote Infisical URLs, empty/duplicate categories, extra fields, and missing-agent-without-path input fail before steps 1-3 mutation.

JSON output is exactly one stdout line and includes deterministic `categories`, `required_new_agent_paths`, `approvals`, `heartbeat_every`, eight ordered typed step records, `completed_steps`, `deployment_complete`, and `remaining_steps`. Step 6 embeds its `BackfillResult`; Step 8 embeds every verification check ID, status, action, and dependency. Secret values are never included. Human output uses stderr only and reuses the shared backfill and verification Rich reporters.

## Kalshi Secrets

Step 4 probes the configured loopback HTTP Infisical origin at `GET /api/status` with a one-second timeout and environment proxies disabled. In production, `http://localhost:8080` is target-local: Infisical runs on macpro-linux beside TraderBot, so `localhost` is resolved by that target host. Development verification uses isolated fake clients and loopback servers and does not prove target integration; actual Infisical integration is deferred to Final-Wave QA on macpro-linux. Because the supported SDK exposes no public proxy-free transport, any nonempty HTTP/HTTPS/ALL proxy environment variable refuses SDK use. After universal-auth login, deploy checks non-value list access to both required project roots with caching disabled. A denied or unusable setup is closed, selects `LocalEncryptedStore` through the same `SecretsStore` facade, and reports `backend=local-encrypted`; deploy never starts Docker or creates a machine identity.

Only the environment-scoped Kalshi pair is eligible: `kalshi_api_key` and `kalshi_private_key_pem` (service `kalshi`) for production, `kalshi_demo_api_key` and `kalshi_demo_private_key_pem` (service `kalshi_demo`) for demo. The daemon consumes the production pair; demo deploy, backfill, and verification consume the demo pair. There is no cross-environment fallback. Secret-bearing values use redacted typed objects. A valid existing complete pair is parsed and reused without writes. An incomplete pair requires explicit `reconcile_incomplete`; a malformed or differing durable field requires separate `replace_existing`, and both approvals require a complete environment-reference pair. Otherwise config mode resolves the named environment variables, while interactive mode uses hidden password prompts. The API key must be nonempty and the PEM must parse locally as an RSA private key before the first write. No live Kalshi request is made. News, weather, embedding, social, economics, crypto, and sports service credentials are not prompted or stored by deploy.

The pair is prevalidated as one decision. Every set is post-read verified. First-write, second-write, and no-op backend failures re-read durable state and report only exact canonical written/pending names. A matching durable field is never rewritten on a forward rerun. If Infisical becomes unavailable mid-operation, remote partial state is preserved and reported while the same validated pair reconciles through encrypted local fallback; no backend state is deleted.

The local encrypted root rejects relative, escaping, linked, wrong-type, and foreign-owned components. Accepted existing POSIX storage is hardened to directory mode `0700` and file mode `0600` before use and revalidated immediately before atomic publication; Windows ACL hardening fails closed when owner-only access cannot be proven.

## Database Creation

Step 5 mirrors daemon ownership order under `TRADERBOT_DATA_DIR`: apply every currently registered global migration, construct one `SQLiteConnectionPool`, create or validate the hardened embedded Chroma root, acquire and health-check `ChromaStore`, then initialize selected category decisions databases through `DatabaseAccess.writable_decisions`. Global migration v2 adds weather observations and typed Kalshi market, candlestick, and forecast-history storage automatically on new or existing v1 databases. Chroma close and pool shutdown are attempted in order on every path; dual cleanup failures retain both diagnostic identities, and a client-close fault still releases Chroma ownership.

Each selected category receives `{mode}-{name}/db/decisions.db` with the current seven domain tables plus `schema_version`, and an actual writable transaction is committed. Canonical `(sysadmin, sysadmin)` uses `DatabaseAccess.all_agent_decisions` for read-only enumeration; deploy never creates a SysAdmin decisions database. The exact shared manifest is `news`, `data_points`, `market_patterns`, `news_signals`, and `market_conditions`, but deploy creates no collection because no production embedding dimension exists. Collection creation remains lazy until a real embedding write supplies an explicit dimension.

An existing Chroma ownership lock is a non-destructive blocker. Deploy does not kill the owner, remove the lock, retry blindly, or delete state. Matching reruns reuse migrations, schemas, encrypted secrets, and the empty-or-existing Chroma root without duplicate mutation.

## Standalone Backfill

Run `traderbot backfill [--environment production|demo] --months 6 [--collector-db PATH] [--json]`. The option defaults explicitly to `production`; `demo` is carried through the typed request and every owned Kalshi history-client factory to the demo REST base URL. The command resolves the existing canonical Kalshi credential pair without prompting, opens one target `SQLiteConnectionPool`, optionally imports the legacy collector read-only, and fetches both current and archived Kalshi weather history around one cutoff. It never initializes Chroma.

The default collector path is optional; an absent default produces a warning while an invalid explicitly supplied path exits 2 before target or API writes. Complete runs exit 0. Isolated item failures or systemic Kalshi failures after committed work return a redacted typed partial result and exit 1; total runtime failures also exit 1. JSON mode reserves stdout for one result line and sends no Rich output there.

## Standalone Verification

Run `traderbot verify [--environment production|demo] --categories weather [crypto ...] [--mode backtest] [--json]` on the host that owns the deployment. The option defaults explicitly to `production`; `demo` reaches the typed verification request and signed Kalshi balance client without a production fallback. Production loopback means macpro-linux-local; development localhost is not the production target, and local QA uses isolated fakes only.

The command runs a fixed, sequential, read-only graph. It verifies Gateway RPC, selected OpenClaw inventory/workspaces/config, the exact managed bootstrap cron, persisted dormant heartbeat config, exact real-auth mode, selected five-field durable token documents, signed Kalshi `GET /portfolio/balance`, global and selected decisions database manifests, service-manager status, actual MCP `health`, daemon-owned Chroma health, and Infisical primary or encrypted fallback state. Gateway failures skip only Gateway children; unavailable token credentials skip signed Kalshi and daemon runtime; unavailable daemon runtime prevents a false embedded-Chroma pass.

SQLite files are opened with URI `mode=ro`, `query_only`, `quick_check`, and exact latest schema/table/index manifests after no-link ownership checks. Verification never probes writability, creates WAL/journal files, opens daemon-owned embedded Chroma, installs or changes services, creates agents, edits config/cron/heartbeat, or writes secrets. JSON mode emits exactly one stdout line. Human mode emits one Rich table to stderr. Exit codes are 0 for `ok`, 1 for `failed` or `degraded`, and 2 for invalid input.

Both standalone commands restrict the environment to `production` or `demo` at argparse. Invalid values exit 2 before handlers, secret/client factories, external calls, or filesystem mutation. Standalone verify continues to force `TRADERBOT_USE_HARDCODED_AUTH=0` before dispatch.

## Wizard Steps 6-8

Step 6 validates the complete backfill and verification request graph during global read-only preflight, before the first OpenClaw mutation. It calls `run_backfill` through `OwnedBackfillDependencies`, so explicit collector validation precedes credential, target, client, and pool construction. Complete results finish the step; partial or failed results preserve typed counts and committed progress, return nonzero, and do not suppress safe independent Step 8 verification.

An explicit collector is converted into one immutable prepared snapshot before secret or runtime factories are constructed. The deploy command owns that snapshot until Step 6 consumes it, never reopens the original source, and removes the snapshot exactly once on success or abort. `invalid_input` is a deploy-level invalid request and exits 2.

Step 7 prints the Phase 5 sandbox notice once in human mode and inspects the exact Gateway-owned `traderbot-main-at-5m` one-shot contract. It never calls add, update, delete, run, or heartbeat mutation. One exact persisted job completes the step. Unreadable, duplicate, malformed, disabled, completed, deleted, or conflicting inventory is nonzero. Because `deleteAfterRun: true` makes post-execution absence expected operationally, the read-only wizard records that absence as `phase5_sandbox_stub_cron_absent` with an action-required partial outcome; it does not recreate the job.

Step 8 constructs `VerificationRequest` from the same validated categories, mode, workspaces, explicit data root, Infisical origin, daemon MCP URL, and `production`/`demo` Kalshi environment and calls `run_verification`. The same data root and environment also flow through Steps 5 and 6 and deploy state. `ok` completes the step; `degraded` is partial; `failed` fails. Exit 0 requires all eight steps complete, exit 1 covers partial/runtime/verification outcomes, and exit 2 covers invalid configuration before mutation.

Late-step outcomes are stored in owner-only `deploy-state.json` under the selected data root with schema version and per-step configuration fingerprints. Completed unchanged Steps 6-8 are reused by default; partial, failed, and skipped steps rerun. Changing the backfill window/source invalidates Step 6 and downstream Step 8. Verification is intentionally not refreshed implicitly after a completed unchanged run; operators use the standalone `traderbot verify` command when fresh health evidence is required.

The configured data root is validated without creation before secret or runtime factories: it must be absolute, traversal-free, have no linked/non-directory existing ancestor, and any existing root must be owner-owned mode `0700`. Existing deploy state is trusted only when it is an owner-owned regular no-follow file at exact mode `0600`, at most 1 MiB, and valid for the current schema. Unsafe state makes the request invalid before OpenClaw mutation; it is never silently hardened during a read.

The bootstrap lifecycle distinguishes active pending, completed retained, known completed then deleted, never registered missing, unknown absence, and conflict/failure. Completed retained or authoritatively recorded deletion reaches Step 7 as action-required partial without recreation. Unknown absence fails closed. Disabled, errored, stale, duplicate, or malformed jobs never satisfy the active canonical matcher.

A persisted state file is authoritative even when `bootstrap_registered` is false: missing Gateway inventory is then unknown absence and cannot trigger registration. Only a truly fresh deployment with no state may register the initial one-shot. State trust is checked again on the opened descriptor for regular-file type, current owner, exact `0600`, size, and device/inode identity.

## Resumability And Identity

Before category or workspace mutation, deploy performs one global read-only preflight: checked agent inventory, every configured workspace identity, selected config/SecretRefs, token metadata, injection plans, heartbeat desired state, and the exact bootstrap cron contract. It rejects exact, normalized, realpath, same-file, and ancestor/descendant workspace ownership across selected and unselected agents.

OpenClaw is installed only when PATH detection fails and installation is approved. Setup uses `openclaw setup --baseline --json` only when `main` is absent and setup is approved; setup is never a probe. Every approved prerequisite mutation is followed by a complete preflight restart. Existing `main` is required, never passed to `agents add`, and its inventory workspace is authoritative. Deploy never invokes doctor because doctor may repair or migrate user-owned OpenClaw state.

SysAdmin workspace files are injected only into the preflight-approved inventory path. Managed MCP guidance lives in the canonical `AGENTS.md ## Tools` section; TraderBot never creates or updates `TOOLS.md` or `HEARTBEAT.md`, and pre-existing legacy files remain byte- and mode-identical. SysAdmin duties remain on OpenClaw agent `main`; no separate SysAdmin agent is created.

The canonical OpenClaw bootstrap inventory contract is: name `traderbot-main-at-5m`, `agentId: main`, `enabled: true`, an `at` one-shot schedule representing five minutes after `createdAtMs`, `sessionTarget: isolated`, `wakeMode: now`, an exact `agentTurn` activation payload, and `deleteAfterRun: true`. A matching job is reused. Any same-name mismatch fails closed without add/edit/delete. The Gateway CLI/RPC add request occurs only after all selected agent/config postconditions pass, and the new inventory must satisfy the same contract.

Only categories selected in the current invocation are created, configured, injected, or tokenized. Existing selected agents retain inventory workspaces and user sandbox/heartbeat state. Approved `heartbeat_every: "0m"` is written through OpenClaw config only; TraderBot creates no heartbeat cron, monitor, scratch, file, or SQLite row. Stable config-first partial `agents add` state is adopted only after a complete inventory reread proves exact ID/path ownership. Conflicts fail closed without deleting user-owned state.

Profile tokens are generated as opaque values and stored through `SecretsStore` under `<agent_id>_token`. Exact SecretRefs are preserved; absent mappings are set as one atomic object; any mismatch fails preflight without overwrite. Every `MarketCategory` has a restart-available registry profile, so persisted tokens still resolve after the deploy process exits and the daemon starts.
