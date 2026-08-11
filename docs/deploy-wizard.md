# Deploy Wizard Steps 1-3

`traderbot deploy` currently implements the first three deploy steps: OpenClaw baseline configuration, SysAdmin setup on agent `main`, and explicit category-agent selection. Steps 4-8 remain out of scope.

## Interactive Mode

Run `traderbot deploy`. A Rich table lists the nine `MarketCategory` values. Enter one or more comma-separated agent IDs, then explicitly supply the SysAdmin and selected category workspace paths. Category profiles always start in `backtest` mode; paper/live transitions belong to Phase 7 lifecycle setup.

## Config Mode

`traderbot deploy --config deploy.json --json` is prompt-free. The documented Todo-1 keys are sufficient:

```json
{
  "categories": ["weather", "crypto"],
  "mode": "backtest"
}
```

When workspace extensions are omitted, deploy derives `<HOME>/.openclaw/workspace` for `main` and `<HOME>/.openclaw/workspace-<category>` for each selection at invocation time. Optional `sysadmin_workspace` and `category_workspaces` overrides must be absolute, non-linked paths; unspecified selected categories still use their standard path. Empty, duplicate, extra, and invalid categories fail before mutation.

JSON output has deterministic `success`, `categories`, three ordered step records, `completed_steps`, `deployment_complete`, and `remaining_steps`. A successful current run reports `completed_steps: [1, 2, 3]`, `deployment_complete: false`, and `remaining_steps: [4, 5, 6, 7, 8]`. Steps 4-8 remain incomplete. Raw profile-token values are never included.

## Resumability And Identity

OpenClaw is installed only when PATH detection fails. Setup uses `openclaw setup --baseline --json`, gateway verification requires RPC, and doctor uses the read-only `--lint --json` path.

SysAdmin workspace files are injected only into the validated explicit or derived path. SysAdmin duties remain on OpenClaw agent `main`; no separate SysAdmin agent is created.

The canonical OpenClaw 2026.8.1 bootstrap inventory contract is: name `traderbot-main-at-5m`, `agentId: main`, `enabled: true`, an `at` one-shot schedule representing five minutes after `createdAtMs` (OpenClaw may store the submitted relative `5m` as an absolute timestamp), `sessionTarget: isolated`, `wakeMode: now`, an `agentTurn` payload with the exact SysAdmin activation intent, and `deleteAfterRun: true`. A matching job is reused. Any same-name mismatch fails closed without add/edit/delete. A newly added job is re-read and must satisfy the same contract before step 2 succeeds.

Only categories selected in the current invocation are created or configured. Matching partial state is reused on rerun. Conflicts fail closed without deleting user-owned state.

Profile tokens are generated as opaque values and stored through `SecretsStore` under `<agent_id>_token`. OpenClaw receives only SecretRef metadata (`source: exec`, `provider: infisical`, and the secret ID). Every `MarketCategory` has a restart-available registry profile, so persisted tokens still resolve after the deploy process exits and the daemon starts.
