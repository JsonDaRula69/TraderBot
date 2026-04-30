# Agent-Profile Binding — Issues

## 2026-04-30 Session
- BOB branch has deletions (updater.py, update_config.py, test_evaluate_trade_profile.py) that would lose work on main
- Launchd template test `test_template_program_arguments_structure` expects hardcoded path but template uses placeholder
- 9 sentiment test failures (pre-existing, env issue, not profile-related)