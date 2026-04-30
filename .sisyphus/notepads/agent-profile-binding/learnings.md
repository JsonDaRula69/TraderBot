# Agent-Profile Binding — Learnings

## 2026-04-30 Session: Verification & Continuation

### Branch State
- main is at `34ee818` (v0.08.50)
- origin/BOB is at `e0e3d1f` (behind main)
- BOB was merged into main at `fcc2107` (Merge branch 'BOB')
- Main then got additional commits: security fixes, updater system, etc.
- BOB branch has DELETIONS vs main: updater.py, update_config.py, test_evaluate_trade_profile.py
- These deletions would LOSE work if BOB were merged as-is

### Test State
- Profile suite: 169 tests PASS (profiles/ + risk/agent_limits + risk/evaluate_trade_profile + install/)
- Known failures (pre-existing, NOT profile-related):
  - 9 sentiment/NLP tests (vader/textblob) — likely env/dependency issue
  - 1 launchd template test — expects hardcoded `/usr/local/bin/traderbot` but template uses `TRADERBOT_BIN_PATH` placeholder
- All T1-T17 implementation verified ON DISK (all source + test files exist)

### Plan State
- ALL 17 tasks checked [x] in plan file
- ALL 4 Final Wave tasks checked [x] with APPROVE verdicts
- ALL Definition of Done items checked [x]
- ALL Final Checklist items checked [x]
- Plan appears FULLY COMPLETE