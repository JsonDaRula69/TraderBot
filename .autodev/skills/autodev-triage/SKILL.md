---
name: autodev-triage
description: "Triage incoming autodev-request issues from the Traderbot liaison. Reads the GitHub issue, classifies priority and type, routes to the Planner agent for plan creation. Triggers when an autodev:wake webhook event arrives or when heartbeat polling finds a new autodev-request issue. Also used when the user says 'triage', 'new task', 'autodev triage', or 'process issue'."
---

# AutoDev Triage

## Objective

When a new `autodev-request` issue appears, triage it and route it into the AutoDev workflow. This is the entry point for all Traderbot development work.

## Trigger

This skill fires when:

1. A webhook wake event arrives from the liaison (`autodev:wake`)
2. Heartbeat polling discovers a new issue with the `autodev-request` label
3. A human manually invokes triage

## Workflow

### Step 1: Fetch the issue

```bash
gh issue view <number> --json title,body,labels,assignees,comments
```

Extract:
- Title and description
- Priority (from body or label: `priority:critical`, `priority:high`, `priority:medium`, `priority:low`)
- Type (from body or label: `type:bug`, `type:feature`, `type:refactor`, `type:security`, `type:docs`)
- Source agent (from body: which Traderbot agent filed this)
- Acceptance criteria (from body)
- Constraints (from body)

### Step 2: Validate the request

Check that the issue has:

- [ ] Clear description of what needs to be done
- [ ] At least one acceptance criterion
- [ ] Type classification (bug/feature/refactor/security/docs)
- [ ] Priority classification (critical/high/medium/low)

If any are missing, comment on the issue asking the liaison or human to provide them. Apply `autodev-blocked` label. Do not proceed until resolved.

### Step 3: Quick scope assessment

Use Explore and Librarian to quickly assess the change scope:

```bash
rg -l "<keywords from issue>" --type py --type ts
```

Classify the effort:

| Scope | Files touched | Route |
|-------|-------------|-------|
| Small | 1-3 files | Direct implementation via `work-with-pr`, no plan needed |
| Medium | 4-10 files | Dispatch to Planner (Prometheus) for plan |
| Large | 11+ files | Full Prometheus planning with hyperplan |

### Step 4: Route

- **Small scope + non-critical:** Label `autodev-planned`, implement directly via `work-with-pr`
- **Medium scope:** Dispatch to Planner agent for plan creation
- **Large scope or critical priority:** Dispatch to Prometheus for adversarial planning (hyperplan)
- **Security type:** Always use full planning + security-research skill regardless of scope

### Step 5: Acknowledge

Comment on the issue:

```
AutoDev has triaged this request.
- **Type:** <type>
- **Priority:** <priority>
- **Scope:** <small/medium/large>
- **Route:** <direct / planned / hyperplan>

Work will begin shortly.
```

## Anti-Patterns

| Violation | Why it fails |
|-----------|-------------|
| Starting implementation without triage | Skips scope assessment, may hit blockers mid-work |
| Guessing missing acceptance criteria | AutoDev should not decide what "done" means for Traderbot |
| Treating all issues the same priority | Critical bugs need different workflow than docs typos |
| Triage without codebase exploration | Scope assessment based on issue text alone is unreliable |
