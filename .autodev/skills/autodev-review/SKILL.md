---
name: autodev-review
description: "Automated PR review for AutoDev deliveries. Runs architecture review, security checks, and code review before human review. Posts findings as PR comments. Triggers when a PR is opened from an autodev branch or when the user says 'review PR', 'autodev review', 'check this PR'."
---

# AutoDev Review

## Objective

Review an AutoDev PR before it reaches human review. Catch issues that CI doesn't: architectural drift, security concerns, pattern violations, and incomplete evidence.

## Workflow

### Step 1: Gather context

```bash
gh pr view <number> --json title,body,files,commits,additions,deletions
gh pr diff <number>
```

Identify:
- Which issue this PR resolves
- Which plan it follows (`.autodev/plans/<slug>.md`)
- Evidence directory (`.autodev/evidence/<YYYYMMDD>-<slug>/`)
- Files changed

### Step 2: Architecture review (Oracle)

Dispatch to Oracle with the diff and plan:

- Does the implementation match the plan's architecture?
- Are new dependencies justified?
- Does the change respect Traderbot's module boundaries?
- Does it introduce coupling that the plan didn't call for?

### Step 3: Security review

For any PR that touches:

- **API keys or auth:** Check for hardcoded secrets, proper secret management
- **Kalshi interaction:** Check for unauthorized order placement, position limits bypass
- **Trade execution:** Check for rounding errors, race conditions in order flow
- **User data:** Check for data leakage, improper access control
- **Dependencies:** Check for known vulnerabilities in new packages

### Step 4: Pattern review

Compare against Traderbot's existing patterns:

- Naming conventions match
- Error handling follows project style
- Logging is consistent with existing loggers
- Type annotations follow project conventions
- No AI slop (unnecessary abstractions, over-engineering, scope creep)

### Step 5: Evidence review

Check `.autodev/evidence/<YYYYMMDD>-<slug>/`:

- [ ] Every acceptance criterion from the plan has evidence
- [ ] Evidence shows BEFORE/AFTER (red/green) where applicable
- [ ] Traderbot-specific gates (T1-T3 from autodev-implement) have evidence if relevant
- [ ] Evidence is not just "tests pass" but shows actual validation on a real surface

### Step 6: Post findings

Post review as a PR comment:

```markdown
## AutoDev Review

### Summary
<1-line verdict: APPROVE / REQUEST CHANGES / BLOCK>

### Findings

| # | Severity | Category | Finding | File:Line |
|---|----------|----------|---------|-----------|
| 1 | High | Security | ... | ... |
| 2 | Medium | Pattern | ... | ... |

### Evidence Check
- [ ] <criterion>: <evidence status>
- [ ] <criterion>: <evidence status>

### Recommendation
<What should happen next>
```

Apply labels:
- All clean: `autodev-ready`
- Non-blocking findings: `autodev-ready` (with findings noted)
- Blocking findings: `autodev-blocked`

## Anti-Patterns

| Violation | Why it fails |
|-----------|-------------|
| Approving without checking evidence | "Tests pass" is not validation |
| Treating all findings as blocking | Minor style issues shouldn't block merge |
| Not checking plan conformance | Implementation may drift from plan without anyone noticing |
| Reviewing only the diff | Plan and evidence provide context the diff doesn't |
