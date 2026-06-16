---
name: autodev-deploy
description: "Deploy a merged AutoDev PR to the Traderbot environment and verify health. Triggers after PR merge. Also used when the user says 'deploy', 'autodev deploy', 'push to production', 'ship it'."
---

# AutoDev Deploy

## Objective

After a PR is merged, deploy the change to the Traderbot environment and verify it's healthy before signaling completion to the liaison.

## Pre-conditions

- PR has been merged to the target branch
- CI was green on the merged commit
- Issue has label `autodev-merged`

## Workflow

### Step 1: Pull the latest

```bash
cd <traderbot-repo>
git pull origin <target-branch>
```

### Step 2: Deploy

The deployment method depends on Traderbot's setup. Adjust this section when Traderbot's deployment pipeline is defined. Initial assumption: manual deployment via shell commands.

```bash
# Example: restart the OpenClaw gateway with new code
cd <traderbot-repo>
openclaw gateway restart
```

If Traderbot uses Docker:
```bash
docker compose pull && docker compose up -d
```

If Traderbot uses systemd:
```bash
sudo systemctl restart traderbot
```

### Step 3: Health check

Wait for the deployment to stabilize (30 seconds minimum), then verify:

```bash
# Gateway is running
openclaw gateway status

# Agent responds to a test message
openclaw agent --message "ping" --no-deliver

# No error spikes in logs
journalctl -u traderbot --since "2 minutes ago" | grep -i error | wc -l
```

For Traderbot specifically:
- Can the agent still connect to Kalshi?
- Are positions and P&L reporting correctly?
- Is the cron schedule running?

### Step 4: Signal completion

If healthy:

1. Post completion comment on the original issue:
```
AutoDev delivery complete. PR #<number> merged and deployed.
Deployment health verified at <timestamp>.
```

2. Send webhook to liaison (completion signal):
```bash
curl -X POST <openclaw-webhook-url> \
  -H "Content-Type: application/json" \
  -d '{
    "event": "autodev:completed",
    "instruction": "PR #'"$PR"' merged and deployed for issue #'"$ISSUE"'",
    "text": "Issue #'"$ISSUE"' resolved. Deployment healthy.",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "context": {
      "issueNumber": "'"$ISSUE"'",
      "prNumber": "'"$PR"'",
      "status": "deployed"
    }
  }'
```

### Step 5: Rollback if unhealthy

If the health check fails:

1. Roll back to the previous known-good state
2. Label the issue `autodev-blocked`
3. Comment on the issue with the failure details
4. Do NOT signal the liaison — the work is not complete

```bash
# Rollback
git revert HEAD
# Redeploy
openclaw gateway restart
```

## Anti-Patterns

| Violation | Why it fails |
|-----------|-------------|
| Deploying without health check | A broken deployment defeats the purpose of the entire pipeline |
| Skipping rollback on failure | Leaving a broken deployment running causes real trading risk |
| Not signaling the liaison | Traderbot agents won't know the work is done |
| Deploying multiple PRs at once | Can't isolate which change caused a failure |
