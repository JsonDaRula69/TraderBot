# TraderBot v2 — Self-Improvement Framework

> This document covers the three-layer self-improvement architecture, agent-debate integration, lifecycle transitions, and the improvement cycle. Grounded in DD-017, DD-018, DD-034, DD-038.

---

## Three-Layer Self-Improvement Architecture

### Layer 1: Reactive Agent Learnings

- **Scope**: Category-specific operational quirks and recurring patterns
- **Trigger**: Discovered by category agents during normal operations
- **Mechanism**: Category agents document findings in their `.learnings/` folder. After 3+ recurrences, the finding is flagged for promotion
- **Examples**: Kalshi markets that don't auto-settle when results go public (creating a narrow 0%-risk trading window); climate/weather markets misassigned to wrong categories
- **Resolution**: SysAdmin investigates, verifies root cause, and files a GitHub issue. Most repeated-learnings issues are resolved by updating parameters in `AGENTS.md` or `TOOLS.md`

### Layer 2: Proactive Pipeline Improvement (Primary Focus)

- **Scope**: Strictly limited to the data–analysis–decision pipeline — data sources, ingestion, processing, statistical interpretation, and agent decision frameworks
- **Trigger**: Continuous and proactive. Runs indefinitely with no final goal; the only required outcome is **incremental improvement every cycle**
- **Boundary**: Issues outside this scope (API token failures, profile auth issues, rate limiting) are documented in `Errors.md` and must recur 3 times before SysAdmin investigates and files a GitHub issue. The one gray area: if stale data led to a bad decision, that's a **decision-framework issue** (Layer 2), not an infrastructure issue
- **Framework**: gumbel-ai/agent-debate integrated via OpenClaw's `sessions_spawn`, `sessions_send`, `sessions_yield`

### Layer 3: AutoDev Team

- **Scope**: Full system architecture — any GitHub issue
- **Trigger**: GitHub issues filed by SysAdmin, agents, or humans
- **Mechanism**: AutoDev (OpenCode + OmO) picks up issues, investigates, deploys fixes, updates `CHANGELOG.md`. The Dev-Liaison coordinates between TraderBot agents and AutoDev via webhook communication (DD-034 §10).
- **Communication**: AutoDev sends webhook notifications (`autodev-completed`, `autodev-blocked`, `autodev-deployed`) to the Dev-Liaison via OpenClaw hooks. Dev-Liaison sends wake signals (`autodev:wake`, `autodev:cancel`, `autodev:priority`) to AutoDev via shared Discord channel. GitHub is the shared source of truth for all state and data.

---

## Agent-Debate Integration (DD-038)

### Framework: gumbel-ai/agent-debate

Adopted into existing infrastructure. Role mapping:

| Role | Our Agent | Notes |
|---|---|---|
| Orchestrator | SysAdmin (primary instance) | Manages process flow |
| Watcher | Dev-Liaison | Monitors and provides feasibility perspective |
| Adversarial Agent ×4 | 2× Category Agent subs + 2× SysAdmin subs | Debaters/researchers |

OpenClaw supports configuring agents to spawn subs with specific models, enabling multi-model debate.

### Session Tools

OpenClaw provides three tools for inter-agent communication during debate:

- **`sessions_spawn`**: Creates an isolated sub-agent session. `maxSpawnDepth: 1` means debate subs cannot spawn further children. Debate subs get `sessions_send` in their `alsoAllow` for cross-examination.
- **`sessions_send`**: Delivers debate prompts and collects responses. Fire-and-forget for debate coordination (more control than ping-pong loop).
- **`sessions_yield`**: Ends the current turn and waits for follow-up sub-agent results. SysAdmin uses this after spawning all 4 debate agents.

### Sub-Agent Configuration

```json5
// SysAdmin (orchestrator)
{
  id: "sysadmin",
  sandbox: { mode: "off" },
  tools: {
    allow: ["read", "write", "exec", "github"],
    alsoAllow: [
      // SysAdmin management tools (DD-036)
      "traderbot__health", "traderbot__auth_check", /* ... */,
      // Session orchestration for debate coordination
      "sessions_spawn", "sessions_send", "sessions_yield",
      "sessions_list", "sessions_history", "subagents",
    ],
    deny: ["traderbot__trade", "traderbot__scan", "traderbot__analyze",
           "traderbot__weather_*", "traderbot__market_edge", "traderbot__market_prices"],
  },
}

// Debate sub-agent (spawned dynamically)
sessions_spawn({
  agentId: "weather",          // Inherit weather agent's tool allowlist
  model: "openai/gpt-5",       // Model override for perspective diversity
  sandbox: "require",           // Force sandboxing even for sysadmin subs
  context: "isolated",         // Clean session, no inherited transcript
  prompt: "You are participating in a TraderBot improvement debate...",
})
```

### Important Constraints

1. **Sandbox inheritance guard**: If SysAdmin (unsandboxed) spawns a sub-agent targeting a sandboxed agent (weather), the sub-agent WILL be sandboxed. It inherits the target agent's sandbox settings.
2. **Tool profile inheritance**: Sub-agents inherit the target agent's tool allowlist AND deny list. A weather debate sub gets weather tools but NOT trading or SysAdmin management tools.
3. **Cross-examination needs `sessions_send`**: Added to each debate sub's `alsoAllow` list since leaf sub-agents don't get messaging tools by default.
4. **Ephemeral sessions**: Debate sub-agents are created for a single cycle and terminated after convergence.
5. **No recursive spawning**: Debate subs are leaf agents (depth 1). They cannot spawn further children.

---

## The 5-Round Improvement Cycle

### Round 1: Identify Suboptimal Outcomes (Debate Phase)

**Goal**: Identify, categorize, and trace root causes of every suboptimal outcome.

**Definition of "suboptimal outcome"** — any bad choice the agent made:
- Incorrect interpretation of data
- Poorly timed trade that missed full potential profit
- Trade that resulted in a loss
- Submitted offer that didn't fill or filled at wrong price (slippage)
- Underestimated prediction confidence → conservative trade → missed profit
- Overestimated confidence → trade settled much lower than predicted

**Process**:
1. Each agent analyzes the entire pipeline — code, logs, reports, everything
2. Trace each suboptimal outcome to the **root cause** (the "first domino")
3. Each agent produces a list of **10 unique suboptimal outcomes** with evidence documenting the full timeline
4. **40 unique root causes total** (4 agents × 10, no duplicates)
5. Central coordination space (category workspace) ensures no duplicates

### Round 2: White Paper Development & Cross-Examination (Debate Phase)

**Goal**: Develop and rigorously defend/refine each proposed improvement.

**Step 1 — White Paper**: Each agent produces a detailed white paper for each of their 10 suggestions:
- Statistically validatable hypothesis statement specifying which KPI the suggestion will improve
- Research it's based on
- Logical analysis of whether it will help in the specific Kalshi category
- Professional experimental design considerations

**Step 2 — Sequential Cross-Examination**: Each plan is cross-examined by the other 3 debate agents, one at a time:
1. Examiner presents evidence-supported critique (flaws, weaknesses, logical fallacies) OR approves with detailed independent validation
2. Defendant responds: refute with evidence OR accept and revise
3. If refuted, debate continues until resolved
4. Next examiner reviews the full history and brings new perspectives
5. Cross-examiners are incentivized to find flaws, gaps, and feedback

### Round 3: Blind Vote (Debate Phase)

**Goal**: Narrow the field to the 5 strongest proposals.

- All 6 participants (4 debate agents + watcher/coder + orchestrator) cast one blind vote
- Agents may vote for their own plans
- **Voting criteria**: Which hypothesis is most likely proven correct? Which yields largest improvement relative to effort? Which yields largest increase in profitability?
- Tie-breaking: tied agents give final evidence-based statements, all agents vote again
- Dev-Liaison provides a **top-line feasibility check** on each proposal

### Round 4: In-Depth White Paper & Experiment Design (Research Phase)

**Goal**: Transform each surviving idea into a rigorous, implementable experiment.

Each proposal undergoes:
- Current code state review
- Deep conceptual research (understand the principles behind the concept)
- Existing implementation search (find real examples on GitHub — directly analogous or ideologically analogous)
- Statistical experimental design (validatable hypothesis, highest reasonable validation standards, experiment must predict whether hypothesis is valid or invalid)

### Round 5: Final Selection & Implementation (Execution Phase)

SysAdmin selects the top proposal. Implementation path determined by root cause classification:

| Root Cause | Implementation Path |
|---|---|
| TraderBot code issue (broken auth, bug, insufficient analysis model) | GitHub issue for Layer 3 dev team |
| Agent behavior issue (missing/vague instructions, insufficient operating procedure) | Workspace file update (AGENTS.md, TOOLS.md) |
| Both (new module added → agent needs instructions, SysAdmin needs to know) | Coordinated: GitHub issue + workspace update |

---

## Root Cause Classification

Problems can originate from TraderBot (toolkit) or the agent (decision-maker):

**TraderBot problems**:
- Broken auth/handshake between agent and TraderBot
- Broken TraderBot functions
- Bugs and glitches
- Poorly designed or insufficient analysis and data models
- Missing or insufficient data sources
- Insufficient statistical analysis methods

**Agent problems**:
- Missing, insufficient, or inaccurate instructions regarding operating procedure
- Insufficient or vague instructions on decision making and analysis methods
- Poorly designed automation cycles (cron/heartbeat)
- Failure to consider subtle category-specific nuances (e.g., weather prediction certainty increases closer to settlement, but edge decreases)

**Both**:
- New module added in code → agent needs instructions on how to use it
- SysAdmin needs to know what the module is and how it works for oversight

---

## Guardrails

- **Full autonomy**: Agents develop their own hypotheses, establish their own success criteria, design and test their own proposals. They never stop and wait for human permission.
- **One concept per cycle**: Each cycle targets exactly one concept to modify, replace, or add.
- **Critical perspectives grounded in evidence**: Agents are encouraged to debate, investigate, and dissent. Every claim must be grounded in verifiable evidence modeling how performance will be affected under Kalshi market conditions.
- **Kalshi market specificity**: The goal is not to be better at predicting things in general. The goal is better performance on Kalshi markets specifically.
- **Statistical rigor**: Base every decision, calculation, and data derivation in principles of statistical analysis. Create hypotheses. Design tests. Build models. Track trends. Keep detailed historical records.
