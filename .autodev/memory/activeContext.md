# AutoDev Active Context

## Phase: Framework build-out

Populating knowledge base with v2 architecture. No TraderBot v2 codebase exists yet — it needs to be built from scratch per v2roadmap.md and v2docs/.

## Exists

- v2roadmap.md (38 DDs, immutable)
- v2docs/ (architecture docs, immutable)
- .autodev/ (framework, skills, config)
- .autodev/reference/v2docs/ + v2roadmap.md (copies for on-demand access)

## Not Yet Built

- TraderBot v2 codebase
- OpenClaw gateway with TraderBot agents
- Dev-Liaison workspace files
- Infisical setup on macpro-linux
- `traderbot` pip package

## Key Constraints

1. v2roadmap.md + v2docs/ are immutable truth
2. AutoDev deploys to ssh macpro-linux
3. Real money system — standing order #1
4. Evidence or it didn't happen — standing order #2
5. Existing codebase is older version needing full v2 overhaul

## Open Questions

- Backtest→paper→live promotion thresholds (TBD in roadmap)
- Category toolkit designs beyond weather (pending)
- GRIB2 Phase 2 timeline (pending)
