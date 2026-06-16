# ADR-038: Agent-debate integration, sub-agent configuration, TEMPLATE.md

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-038
**Tags:** self-improvement, agent-debate, sub-agents, improvement

## Context

Layer 2 self-improvement needs a structured, rigorous process for proposing and evaluating pipeline improvements. Previous iterations (Rounds 1-4) had various issues with rigor and evaluation.

## Decision

Round 5 of the improvement framework uses gumbel-ai/agent-debate integrated via OpenClaw's `sessions_spawn`/`sessions_send`/`sessions_yield`. 5-round cycle with specific roles and statistical rigor requirements.

## 5-Round Improvement Cycle

1. **Identify Suboptimal Outcomes**: Each agent analyzes the pipeline, traces 10 root causes per agent (40 total, no duplicates)
2. **White Paper Development & Cross-Examination**: Each agent produces a white paper; cross-examined by other 3 agents sequentially
3. **Blind Vote**: All 6 participants cast one vote. Top 5 proposals advance
4. **In-Depth White Paper & Experiment Design**: Current code review, deep research, statistical experimental design
5. **Final Selection & Implementation**: SysAdmin selects top proposal; implementation path determined by root cause classification

## Consequences

- SysAdmin orchestrates via `sessions_spawn`, `sessions_send`, `sessions_yield`
- Debate sub-agents are spawned with target agent's tool allowlist + `sessions_send`
- Sub-agents are ephemeral — terminated after convergence
- `maxSpawnDepth: 1` prevents recursive spawning
- One concept per cycle — measured and validated before moving on

## Notes for AutoDev Agents

This is Layer 2 of the self-improvement architecture. AutoDev is Layer 3. When the debate cycle produces a proposal that requires code changes (root cause: TraderBot code issue), SysAdmin files a GitHub issue with `autodev-request` label. This is how work enters our pipeline. When the root cause is agent behavior, the workspace files are updated instead.
