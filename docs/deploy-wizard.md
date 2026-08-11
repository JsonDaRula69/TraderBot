# Deploy Wizard Steps 1-3

`traderbot deploy` currently implements the first three deploy steps: OpenClaw baseline configuration, SysAdmin setup on agent `main`, and explicit category-agent selection. Steps 4-8 remain out of scope.

## Interactive Mode

Run `traderbot deploy`. A Rich table lists the nine `MarketCategory` values. After selection, read-only inventory shows the existing `main` and selected-agent workspaces. Existing paths are adopted unchanged. For every missing selected agent, Rich shows a proposed absolute path and requires explicit creation confirmation. Installation, baseline setup, and dormant `0m` heartbeat changes have separate confirmations. Category profiles always start in `backtest` mode; paper/live transitions belong to Phase 7 lifecycle setup.

## Config Mode

`traderbot deploy --config deploy.json --json` is prompt-free. It requires explicit approval flags and an absolute path for every selected agent that may be missing:

```json
{
  "categories": ["weather", "crypto"],
  "mode": "backtest",
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

In this example, `weather` already exists and therefore needs no path assertion; `crypto` may be missing and has an approved creation path. `sysadmin_workspace` and paths for existing selected agents are optional equality assertions, never rebind requests. Assertions must be absolute and non-linked. Empty, duplicate, extra, invalid, unapproved, or missing-agent-without-path input fails before mutation.

JSON output includes deterministic `categories`, `required_new_agent_paths`, `approvals`, `heartbeat_every`, three ordered step records, `completed_steps`, `deployment_complete`, and `remaining_steps`. A successful current run reports `completed_steps: [1, 2, 3]`, `deployment_complete: false`, and `remaining_steps: [4, 5, 6, 7, 8]`. Steps 4-8 remain incomplete. Raw profile-token values are never included.

## Resumability And Identity

Before category or workspace mutation, deploy performs one global read-only preflight: checked agent inventory, every configured workspace identity, selected config/SecretRefs, token metadata, injection plans, heartbeat desired state, and the exact bootstrap cron contract. It rejects exact, normalized, realpath, same-file, and ancestor/descendant workspace ownership across selected and unselected agents.

OpenClaw is installed only when PATH detection fails and installation is approved. Setup uses `openclaw setup --baseline --json` only when `main` is absent and setup is approved; setup is never a probe. Every approved prerequisite mutation is followed by a complete preflight restart. Existing `main` is required, never passed to `agents add`, and its inventory workspace is authoritative. Deploy never invokes doctor because doctor may repair or migrate user-owned OpenClaw state.

SysAdmin workspace files are injected only into the preflight-approved inventory path. Managed MCP guidance lives in the canonical `AGENTS.md ## Tools` section; TraderBot never creates or updates `TOOLS.md` or `HEARTBEAT.md`, and pre-existing legacy files remain byte- and mode-identical. SysAdmin duties remain on OpenClaw agent `main`; no separate SysAdmin agent is created.

The canonical OpenClaw bootstrap inventory contract is: name `traderbot-main-at-5m`, `agentId: main`, `enabled: true`, an `at` one-shot schedule representing five minutes after `createdAtMs`, `sessionTarget: isolated`, `wakeMode: now`, an exact `agentTurn` activation payload, and `deleteAfterRun: true`. A matching job is reused. Any same-name mismatch fails closed without add/edit/delete. The Gateway CLI/RPC add request occurs only after all selected agent/config postconditions pass, and the new inventory must satisfy the same contract.

Only categories selected in the current invocation are created, configured, injected, or tokenized. Existing selected agents retain inventory workspaces and user sandbox/heartbeat state. Approved `heartbeat_every: "0m"` is written through OpenClaw config only; TraderBot creates no heartbeat cron, monitor, scratch, file, or SQLite row. Stable config-first partial `agents add` state is adopted only after a complete inventory reread proves exact ID/path ownership. Conflicts fail closed without deleting user-owned state.

Profile tokens are generated as opaque values and stored through `SecretsStore` under `<agent_id>_token`. Exact SecretRefs are preserved; absent mappings are set as one atomic object; any mismatch fails preflight without overwrite. Every `MarketCategory` has a restart-available registry profile, so persisted tokens still resolve after the deploy process exits and the daemon starts.
