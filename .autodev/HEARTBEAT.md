# AutoDev Heartbeat

Run on every heartbeat cycle (default every 30 minutes). These checks keep the team responsive even when no webhook wake signal arrives from the liaison.

## 1. Check for new autodev-request issues

```bash
gh issue list --label "autodev-request" --state open --json number,title,createdAt --limit 10
```

If any issues exist that were not previously triaged (not in `.omo/` boulder state), invoke the `autodev-triage` skill.

## 2. Check for PRs awaiting attention

```bash
gh pr list --label "autodev-review" --state open --json number,title,createdAt --limit 10
```

If CI has completed on any of these PRs, update labels accordingly:
- CI green + no review comments → `autodev-ready`
- CI red → fix and push, then re-enter verification loop

## 3. Check for stalled PRs

```bash
gh pr list --label "autodev-ci-running" --state open --json number,title,updatedAt --limit 10
```

If any PR has had `autodev-ci-running` for more than 30 minutes without a status change, investigate:
- Check CI status: `gh pr checks <number>`
- If CI is stuck, label `autodev-blocked` and comment

## 4. Check for human review comments

```bash
gh pr list --label "autodev-review" --state open --json number --limit 10 | \
  jq -r '.[].number' | while read pr; do
    gh api repos/{owner}/{repo}/pulls/$pr/comments --jq '.[].body' 2>/dev/null
  done
```

If new review comments exist that haven't been addressed, address them per the `work-with-pr` skill.

## 5. Check for autodev-blocked issues

```bash
gh issue list --label "autodev-blocked" --state open --json number,title --limit 10
```

Report blocked items in the heartbeat summary. Do not attempt to resolve blocks autonomously — these require human input.

## 6. Check auto-merge eligibility

For any PR with label `autodev-ready` that has been in that state for more than 2 hours:

```bash
# Check if it's a critical change (security, auth, money handling)
gh pr view <number> --json labels,body
```

- **Non-critical:** Auto-merge if grace period has passed
- **Critical:** Do NOT auto-merge. Comment reminding that human approval is required.

## 7. Run auditor checks

```bash
bash .autodev/AUDITOR.md 2>/dev/null || true
```

Report any FAIL or WARN items in the heartbeat summary.

## Heartbeat Summary Format

```
AutoDev Heartbeat — $(date -u +%Y-%m-%dT%H:%MZ)
  New issues:      <count> autodev-request
  Open PRs:        <count> in review, <count> ci-running, <count> ready
  Blocked:         <count> issues, <count> PRs
  Lore drafts:      <count> pending review
  Conflicts:       <count> unresolved
  Bootstrap size:  <bytes> bytes
```

If no work items exist and no issues require attention, output only:

```
AutoDev heartbeat: idle. No pending work.
```
