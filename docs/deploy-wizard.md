# Deploy Wizard Steps 1-5 And Verification

`traderbot deploy` currently implements the first five deploy steps: OpenClaw baseline configuration, SysAdmin setup on agent `main`, explicit category-agent selection, Kalshi secret provisioning, and database creation. The standalone Step 6 backfill and Step 8 verification commands are implemented. Steps 6-8 remain unwired in the wizard until Todo 9.

## Interactive Mode

Run `traderbot deploy`. A Rich table lists the nine `MarketCategory` values. After selection, read-only inventory shows the existing `main` and selected-agent workspaces. Existing paths are adopted unchanged. For every missing selected agent, Rich shows a proposed absolute path and requires explicit creation confirmation. Installation, baseline setup, and dormant `0m` heartbeat changes have separate confirmations. Category profiles always start in `backtest` mode; paper/live transitions belong to Phase 7 lifecycle setup.

## Config Mode

`traderbot deploy --config deploy.json --json` is prompt-free. It requires explicit approval flags and an absolute path for every selected agent that may be missing:

```json
{
  "categories": ["weather", "crypto"],
  "mode": "backtest",
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

JSON output includes deterministic `categories`, `required_new_agent_paths`, `approvals`, `heartbeat_every`, five ordered step records, `completed_steps`, `deployment_complete`, and `remaining_steps`. A successful current run reports `completed_steps: [1, 2, 3, 4, 5]`, `deployment_complete: false`, and `remaining_steps: [6, 7, 8]`. Secret values are never included.

## Kalshi Secrets

Step 4 probes the configured loopback HTTP Infisical origin at `GET /api/status` with a one-second timeout and environment proxies disabled. In production, `http://localhost:8080` is target-local: Infisical runs on macpro-linux beside TraderBot, so `localhost` is resolved by that target host. Development verification uses isolated fake clients and loopback servers and does not prove target integration; actual Infisical integration is deferred to Final-Wave QA on macpro-linux. Because the supported SDK exposes no public proxy-free transport, any nonempty HTTP/HTTPS/ALL proxy environment variable refuses SDK use. After universal-auth login, deploy checks non-value list access to both required project roots with caching disabled. A denied or unusable setup is closed, selects `LocalEncryptedStore` through the same `SecretsStore` facade, and reports `backend=local-encrypted`; deploy never starts Docker or creates a machine identity.

Only `kalshi_api_key` and `kalshi_private_key_pem`, the two secrets consumed by the daemon, are eligible. Secret-bearing values use redacted typed objects. A valid existing complete pair is parsed and reused without writes. An incomplete pair requires explicit `reconcile_incomplete`; a malformed or differing durable field requires separate `replace_existing`, and both approvals require a complete environment-reference pair. Otherwise config mode resolves the named environment variables, while interactive mode uses hidden password prompts. The API key must be nonempty and the PEM must parse locally as an RSA private key before the first write. No live Kalshi request is made. News, weather, embedding, social, economics, crypto, and sports service credentials are not prompted or stored by deploy.

The pair is prevalidated as one decision. Every set is post-read verified. First-write, second-write, and no-op backend failures re-read durable state and report only exact canonical written/pending names. A matching durable field is never rewritten on a forward rerun. If Infisical becomes unavailable mid-operation, remote partial state is preserved and reported while the same validated pair reconciles through encrypted local fallback; no backend state is deleted.

The local encrypted root rejects relative, escaping, linked, wrong-type, and foreign-owned components. Accepted existing POSIX storage is hardened to directory mode `0700` and file mode `0600` before use and revalidated immediately before atomic publication; Windows ACL hardening fails closed when owner-only access cannot be proven.

## Database Creation

Step 5 mirrors daemon ownership order under `TRADERBOT_DATA_DIR`: apply every currently registered global migration, construct one `SQLiteConnectionPool`, create or validate the hardened embedded Chroma root, acquire and health-check `ChromaStore`, then initialize selected category decisions databases through `DatabaseAccess.writable_decisions`. Global migration v2 adds weather observations and typed Kalshi market, candlestick, and forecast-history storage automatically on new or existing v1 databases. Chroma close and pool shutdown are attempted in order on every path; dual cleanup failures retain both diagnostic identities, and a client-close fault still releases Chroma ownership.

Each selected category receives `{mode}-{profile}/db/decisions.db` with the current seven domain tables plus `schema_version`, and an actual writable transaction is committed. Canonical `(sysadmin, sysadmin)` uses `DatabaseAccess.all_agent_decisions` for read-only enumeration; deploy never creates a SysAdmin decisions database. The exact shared manifest is `news`, `data_points`, `market_patterns`, `news_signals`, and `market_conditions`, but deploy creates no collection because no production embedding dimension exists. Collection creation remains lazy until a real embedding write supplies an explicit dimension.

An existing Chroma ownership lock is a non-destructive blocker. Deploy does not kill the owner, remove the lock, retry blindly, or delete state. Matching reruns reuse migrations, schemas, encrypted secrets, and the empty-or-existing Chroma root without duplicate mutation.

## Standalone Backfill

Run `traderbot backfill --months 6 [--collector-db PATH] [--json]`. The command resolves the existing canonical Kalshi credential pair without prompting, opens one target `SQLiteConnectionPool`, optionally imports the legacy collector read-only, and fetches both current and archived Kalshi weather history around one cutoff. It never initializes Chroma.

The default collector path is optional; an absent default produces a warning while an invalid explicitly supplied path exits 2 before target or API writes. Complete runs exit 0. Isolated item failures or systemic Kalshi failures after committed work return a redacted typed partial result and exit 1; total runtime failures also exit 1. JSON mode reserves stdout for one result line and sends no Rich output there.

## Standalone Verification

Run `traderbot verify --categories weather [crypto ...] [--mode backtest] [--json]` on the host that owns the deployment. Production loopback means macpro-linux-local; development localhost is not the production target, and local QA uses isolated fakes only.

The command runs a fixed, sequential, read-only graph. It verifies Gateway RPC, selected OpenClaw inventory/workspaces/config, the exact managed bootstrap cron, persisted dormant heartbeat config, exact real-auth mode, selected five-field durable token documents, signed Kalshi `GET /portfolio/balance`, global and selected decisions database manifests, service-manager status, actual MCP `health`, daemon-owned Chroma health, and Infisical primary or encrypted fallback state. Gateway failures skip only Gateway children; unavailable token credentials skip signed Kalshi and daemon runtime; unavailable daemon runtime prevents a false embedded-Chroma pass.

SQLite files are opened with URI `mode=ro`, `query_only`, `quick_check`, and exact latest schema/table/index manifests after no-link ownership checks. Verification never probes writability, creates WAL/journal files, opens daemon-owned embedded Chroma, installs or changes services, creates agents, edits config/cron/heartbeat, or writes secrets. JSON mode emits exactly one stdout line. Human mode emits one Rich table to stderr. Exit codes are 0 for `ok`, 1 for `failed` or `degraded`, and 2 for invalid input.

## Resumability And Identity

Before category or workspace mutation, deploy performs one global read-only preflight: checked agent inventory, every configured workspace identity, selected config/SecretRefs, token metadata, injection plans, heartbeat desired state, and the exact bootstrap cron contract. It rejects exact, normalized, realpath, same-file, and ancestor/descendant workspace ownership across selected and unselected agents.

OpenClaw is installed only when PATH detection fails and installation is approved. Setup uses `openclaw setup --baseline --json` only when `main` is absent and setup is approved; setup is never a probe. Every approved prerequisite mutation is followed by a complete preflight restart. Existing `main` is required, never passed to `agents add`, and its inventory workspace is authoritative. Deploy never invokes doctor because doctor may repair or migrate user-owned OpenClaw state.

SysAdmin workspace files are injected only into the preflight-approved inventory path. Managed MCP guidance lives in the canonical `AGENTS.md ## Tools` section; TraderBot never creates or updates `TOOLS.md` or `HEARTBEAT.md`, and pre-existing legacy files remain byte- and mode-identical. SysAdmin duties remain on OpenClaw agent `main`; no separate SysAdmin agent is created.

The canonical OpenClaw bootstrap inventory contract is: name `traderbot-main-at-5m`, `agentId: main`, `enabled: true`, an `at` one-shot schedule representing five minutes after `createdAtMs`, `sessionTarget: isolated`, `wakeMode: now`, an exact `agentTurn` activation payload, and `deleteAfterRun: true`. A matching job is reused. Any same-name mismatch fails closed without add/edit/delete. The Gateway CLI/RPC add request occurs only after all selected agent/config postconditions pass, and the new inventory must satisfy the same contract.

Only categories selected in the current invocation are created, configured, injected, or tokenized. Existing selected agents retain inventory workspaces and user sandbox/heartbeat state. Approved `heartbeat_every: "0m"` is written through OpenClaw config only; TraderBot creates no heartbeat cron, monitor, scratch, file, or SQLite row. Stable config-first partial `agents add` state is adopted only after a complete inventory reread proves exact ID/path ownership. Conflicts fail closed without deleting user-owned state.

Profile tokens are generated as opaque values and stored through `SecretsStore` under `<agent_id>_token`. Exact SecretRefs are preserved; absent mappings are set as one atomic object; any mismatch fails preflight without overwrite. Every `MarketCategory` has a restart-available registry profile, so persisted tokens still resolve after the deploy process exits and the daemon starts.
