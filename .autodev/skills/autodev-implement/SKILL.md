---
name: autodev-implement
description: "Implement a planned autodev task with evidence-bound QA. Extends the work-with-pr skill with Traderbot-specific validation gates. Use when implementing an autodev-planned issue. Triggers: 'autodev-implement', 'implement plan', 'execute plan', 'start work on issue'."
---

# AutoDev Implement

## Objective

Implement a planned change from `.autodev/plans/<slug>.md`, validate it with evidence, open a PR, and drive it through the verification loop until merged.

This skill extends OmO's `work-with-pr` skill with Traderbot-specific validation. The base work-with-pr flow (worktree setup, implementation, PR creation, CI/review/merge loop) still applies. This skill adds the Traderbot-specific gates.

## Pre-conditions

Before starting implementation:

1. A plan exists at `.autodev/plans/<slug>.md`
2. The GitHub issue has label `autodev-planned`
3. The plan includes acceptance criteria, affected files, and test strategy

## Workflow

### Phase 0: Setup (inherited from work-with-pr)

Create an isolated worktree from the target branch. Install dependencies.

### Phase 1: Implement (inherited from work-with-pr with additions)

Drive implementation through the `ulw-loop` skill. In addition to the standard evidence-bound QA, enforce these Traderbot-specific gates:

#### Gate T1: No breaking Kalshi API changes

If the change touches any file that interfaces with the Kalshi API:

```bash
# Verify API contract is preserved
rg "kalshi" --type py -l | xargs python -m pytest tests/test_kalshi_contract.py
```

Evidence required: test output showing contract tests pass.

#### Gate T2: No gateway-breaking config changes

If the change touches `openclaw.json`, `openclaw.yaml`, or any agent config:

```bash
# Validate config schema
openclaw doctor --config <changed-config-file>
```

Evidence required: doctor output showing valid config.

#### Gate T3: No trade execution regressions

If the change touches any file in the trade execution path:

```bash
# Run the full trade execution test suite
python -m pytest tests/test_trade_execution.py -v
```

Evidence required: test output showing all trade execution tests pass.

#### Gate T4: Evidence on disk

Every gate result must be written to `.autodev/evidence/<YYYYMMDD>-<slug>/`. No evidence file = QA did not happen = no commit.

### Phase 2: PR Creation (inherited from work-with-pr)

Open a PR targeting the appropriate branch. Use the autodev-delivery PR template:

```markdown
## Autodev Delivery

**Resolves:** #<issue-number>
**Plan:** `.autodev/plans/<slug>.md`
**Evidence:** `.autodev/evidence/<YYYYMMDD>-<slug>/`

### Changes
<What was implemented and why>

### Evidence Summary
- CI: <green/failing>
- Tests: <N new, M modified, all passing>
- Traderbot gates: <which gates were checked, results>

### Verification Steps
<How a human can verify this works>

### Risk Assessment
<What could go wrong, what was tested, what wasn't>
```

Update the issue label: `autodev-planned` -> `autodev-in-progress` -> `autodev-review`.

### Phase 3: Verification Loop (inherited from work-with-pr)

CI runs automatically. If CI fails, fix and re-push. If review comments arrive, address them. Keep cycling until all gates pass.

Add Traderbot-specific verification:

- Check that CI includes the Traderbot test suite
- If CI doesn't include Traderbot-specific tests, run them locally and capture evidence
- Monitor for the `autodev-ci-running` -> `autodev-ready` label transition

### Phase 4: Merge (modified from work-with-pr)

Apply the AutoDev merge policy:

1. **Default path:** After CI green + review-clean, wait 2 hours for human review
2. **If no human review after grace period:** Auto-merge
3. **If human comments `@autodev hold`:** Do not merge, label `autodev-blocked`
4. **If critical change (security, auth, money handling):** Require human `approve` review regardless of grace period

After merge:

1. Update issue label: `autodev-ready` -> `autodev-merged`
2. Trigger the `autodev-deploy` skill
3. Post completion comment on the issue

## Anti-Patterns

| Violation | Why it fails |
|-----------|-------------|
| Skipping Traderbot-specific gates | Kalshi contract or trade execution regressions could cause real financial loss |
| Merging without grace period on critical changes | Money-handling code always needs human eyes |
| Implementing beyond the plan | Scope creep causes new failures in the verification loop |
| Not writing evidence for Traderbot gates | Gate T1-T3 areTraderbot-specific; standard CI doesn't cover them |
