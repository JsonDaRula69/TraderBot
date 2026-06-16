# AutoDev Architecture

Autonomous engineering team for Traderbot development. Runs on OpenCode + oh-my-openagent (OmO), coordinated with Traderbot's OpenClaw gateway through a liaison agent and GitHub.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Your Machine                           │
│                                                               │
│  ┌─────────────────────┐         ┌─────────────────────────┐ │
│  │  OpenClaw Gateway    │         │  OpenCode + OmO          │ │
│  │  (Traderbot agents)  │         │  (AutoDev Team)          │ │
│  │                      │         │                          │ │
│  │  • Traderbot main    │  webhook│  • Sisyphus (lead)      │ │
│  │  • Autodev Liaison   │◄───────►│  • Prometheus (plan)    │ │
│  │  • Cron + Heartbeat  │  reply  │  • Atlas (execute)       │ │
│  │  • Discord/Telegram  │  daemon │  • Oracle (arch)         │ │
│  │                      │         │  • Background agents     │ │
│  └──────┬──────────────┘         │  • Team Mode             │ │
│         │                        │  • Skills + Hooks        │ │
│         │                        │  • .omo/ state           │ │
│         │                        └──────────┬──────────────┘ │
│         │                                   │                │
└─────────┼───────────────────────────────────┼────────────────┘
          │                                   │
          │         ┌─────────────┐           │
          └────────►│   GitHub     │◄──────────┘
                    │              │
                    │  Issues ────│─── Task board
                    │  PRs ───────│─── Review gate
                    │  Labels ────│─── Status signals
                    │  Comments ──│─── Communication
                    │  CI ──────── │─── Validation gate
                    │  Branches ──│─── Work isolation
                    └─────────────┘
```

## Process Topology

Two long-running processes on the same machine:

| Process | Runtime | Port | Role |
|---------|---------|------|------|
| OpenClaw Gateway | `openclaw gateway run` | 3000 (default) | Traderbot agents, channels, cron |
| OpenCode + OmO | `opencode` / `omo run` | None (TUI) or custom (API mode) | AutoDev team orchestration |

They are independent processes that communicate through:

1. **HTTP webhooks** — Liaison sends POST to OmO's gateway dispatcher; OmO sends POST to OpenClaw's webhook endpoint
2. **Discord/Telegram** — OmO's reply listener daemon polls channels for messages from Traderbot agents
3. **GitHub** — Shared coordination platform (issues, PRs, labels, CI)

No shared state directory. No shared port. No shared config.

---

## The Liaison Bridge

The Autodev Liaison is a named agent running on the OpenClaw gateway alongside the Traderbot main agent. Its job is narrow: translate Traderbot needs into AutoDev signals and relay AutoDev results back.

### Liaison responsibilities

- **Inbound (Traderbot → AutoDev):** When Traderbot needs development work (bug fix, feature, refactor), the liaison creates a GitHub issue with the `autodev-request` label and sends a webhook wake signal to the AutoDev team.
- **Outbound (AutoDev → Traderbot):** When AutoDev completes work (PR merged, deployment done), the liaison detects the GitHub state change (via label transitions or polling) and notifies the relevant Traderbot agent.

### Liaison is NOT an engineer

The liaison does not write code, review PRs, or run tests. It is a router. It translates between OpenClaw's event model and GitHub's issue/PR model. If the liaison goes down, AutoDev still works — it just doesn't receive new tasks from Traderbot until the liaison recovers. The AutoDev team can also pick up `autodev-request` issues independently via heartbeat polling.

---

## GitHub as the Coordination Layer

GitHub is the single source of truth for all cross-system state. Both OpenClaw and OpenCode+OmO read/write to the same repository.

### Label taxonomy

| Label | Who sets it | Meaning |
|-------|-------------|---------|
| `autodev-request` | Liaison or human | New work requested from AutoDev |
| `autodev-planned` | AutoDev (Prometheus) | Plan written, ready for implementation |
| `autodev-in-progress` | AutoDev (Atlas) | Actively being implemented |
| `autodev-review` | AutoDev | PR opened, awaiting review |
| `autodev-ci-running` | AutoDev | CI validation in progress |
| `autodev-ready` | AutoDev or CI | CI green, review-clean, ready for merge |
| `autodev-merged` | AutoDev or human | PR merged to target branch |
| `autodev-blocked` | AutoDev | Blocked on human input or external dependency |
| `autodev-rejected` | Human | Human rejected the PR, needs rework |

### Issue template: autodev-request

When the liaison files an issue, it uses this structure:

```markdown
## Autodev Request

**Source:** Traderbot agent: `<agent-name>`
**Priority:** critical | high | medium | low
**Type:** bug | feature | refactor | security | docs

### Description
<What needs to be done, from Traderbot's perspective>

### Acceptance Criteria
- [ ] <Concrete, testable outcome>
- [ ] <Concrete, testable outcome>

### Context
<Relevant codebase pointers, error logs, user reports>

### Constraints
<Things the implementation must NOT do or MUST preserve>
```

### PR template: autodev-delivery

When AutoDev opens a PR, it uses this structure:

```markdown
## Autodev Delivery

**Resolves:** #<issue-number>
**Plan:** `.autodev/plans/<plan-slug>.md`
**Evidence:** `.autodev/evidence/<YYYYMMDD>-<slug>/`

### Changes
<What was implemented and why>

### Evidence Summary
- CI: <green/failing>
- Tests: <N new, M modified, all passing>
- Manual QA: <what was validated on a real surface>

### Verification Steps
<How a human can verify this works>

### Risk Assessment
<What could go wrong, what was tested, what wasn't>
```

---

## AutoDev Team Structure

Based on OmO's orchestration model with Traderbot-specific customization.

### Agent Roster

| Agent | OmO Role | AutoDev Purpose | Category |
|-------|----------|----------------|----------|
| **Sisyphus** | Lead orchestrator | Receives liaison signals, triages issues, delegates work | `unspecified-high` |
| **Prometheus** | Strategic planner | Reads `autodev-request` issues, researches codebase, creates plans | Primary (plan) |
| **Atlas** | Todo conductor | Executes plans via `/start-work`, delegates to workers | Primary (atlas) |
| **Oracle** | Architecture consultant | Reviews designs, answers architectural questions | subagent |
| **Librarian** | Docs/code search | Finds Traderbot API contracts, Kalshi docs, OpenClaw patterns | subagent |
| **Explore** | Fast codebase grep | Rapid pattern search across the Traderbot repo | subagent |
| **Sisyphus-Junior** | Task executor | Implements individual tasks delegated by Atlas | category-based |

### Workflow: Issue to Deploy

```
1. LIAISON creates GitHub issue with `autodev-request` label
2. LIAISON sends webhook wake to AutoDev (OpenCode session)
3. SISYPHUS triages: reads issue, checks priority, assigns to Prometheus
4. PROMETHEUS plans: interviews codebase (Explore, Librarian, Oracle)
5. PROMETHEUS writes plan: `.autodev/plans/<slug>.md`
6. PROMETHEUS updates issue label: `autodev-request` → `autodev-planned`
7. ATLAS executes: `/start-work` reads plan, creates boulder state
8. ATLAS delegates: Sisyphus-Junior implements tasks in worktree
9. ATLAS updates issue label: `autodev-planned` → `autodev-in-progress`
10. JUNIOR implements: code changes + tests + evidence
11. ATLAS opens PR: `work-with-pr` skill, pushes to GitHub
12. ATLAS updates issue label: `autodev-in-progress` → `autodev-review`
13. CI runs automatically (GitHub Actions: lint, test, build)
14. If CI fails → JUNIOR fixes → push → CI reruns (loop)
15. If CI green → label: `autodev-ci-running` → `autodev-ready`
16. Human reviews (optional, async, not required for forward progress)
17. ATLAS merges PR (after grace period if no human review)
18. ATLAS updates issue label: `autodev-ready` → `autodev-merged`
19. ATLAS triggers deployment skill
20. ATLAS notifies liaison via GitHub comment or webhook
21. LIAISON receives completion signal → notifies Traderbot agent
```

### Merge policy

- **Default:** Auto-merge after CI green + review-clean + 2-hour grace period
- **Critical changes** (security, auth, money handling): Require human `approve` review before merge. Label `autodev-blocked` until approved.
- **Human override:** Any human comment with `@autodev hold` on a PR prevents auto-merge until explicitly released with `@autodev proceed`

---

## Webhook Protocol

### Liaison → AutoDev (wake signal)

Liaison POSTs to OmO's configured gateway endpoint:

```json
{
  "event": "autodev:wake",
  "instruction": "New autodev-request issue: #42 - Fix P&L settlement rounding",
  "text": "Issue #42 requests a fix for P&L settlement rounding errors on Kalshi fill reporting. Priority: high. Type: bug.",
  "timestamp": "2026-06-15T10:30:00Z",
  "context": {
    "issueNumber": "42",
    "priority": "high",
    "type": "bug",
    "source": "traderbot:pricing-agent"
  }
}
```

OmO's gateway dispatcher receives this, resolves the matching hook, and injects the instruction into the active AutoDev session. The hook is configured in OmO's `oh-my-openagent.jsonc`:

```jsonc
{
  "openclaw": {
    "enabled": true,
    "gateways": {
      "autodev-liaison": {
        "type": "http",
        "url": "http://localhost:9900/autodev-wake"  // OpenCode API server endpoint
      }
    },
    "hooks": {
      "autodev:wake": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "A Traderbot agent has filed an autodev-request. Triage and begin work."
      }
    }
  }
}
```

### AutoDev → Liaison (completion signal)

AutoDev POSTs to the OpenClaw gateway webhook endpoint:

```json
{
  "event": "autodev:completed",
  "instruction": "PR #43 merged: Fix P&L settlement rounding",
  "text": "Issue #42 resolved. PR #43 merged to main. Deployment triggered.",
  "timestamp": "2026-06-15T14:00:00Z",
  "context": {
    "issueNumber": "42",
    "prNumber": "43",
    "branch": "fix/pnl-settlement-rounding",
    "status": "merged"
  }
}
```

The OpenClaw gateway receives this as a webhook, and the liaison agent picks it up from its event stream.

---

## Custom Skills

### `autodev-triage`

Triggered when Sisyphus receives an `autodev:wake` event. Reads the GitHub issue, classifies it, and routes to Prometheus for planning.

### `autodev-implement`

Extends OmO's `work-with-pr` skill with Traderbot-specific validation:
- Runs Traderbot's test suite as the CI gate
- Validates against Kalshi API contract (no breaking changes)
- Checks OpenClaw compatibility (no gateway-breaking config changes)

### `autodev-deploy`

Post-merge deployment skill. Triggers the Traderbot deployment pipeline and verifies the deployment is healthy before signaling completion.

### `autodev-review`

Automated PR review skill. Runs Oracle (architecture review), security checks, and code review before human review. Posts findings as PR comments.

---

## State Management

All AutoDev state lives in the repo under `.autodev/`:

```
.autodev/
├── ARCHITECTURE.md          # This document
├── plans/                   # Prometheus plans (markdown)
│   └── <slug>.md
├── evidence/                # QA evidence per change
│   └── <YYYYMMDD>-<slug>/
│       ├── red-<test>.txt
│       ├── green-<test>.txt
│       └── ci-output.txt
├── memory/                  # Session-to-session context
│   ├── projectbrief.md
│   ├── techContext.md
│   └── activeContext.md
├── skills/                  # Custom skill definitions
│   ├── autodev-triage/
│   ├── autodev-implement/
│   ├── autodev-deploy/
│   └── autodev-review/
└── config/                  # Team and agent configuration
    ├── team-spec.json
    └── standing-orders.md
```

`.omo/` holds OmO runtime state (boulder, session data, notepads). `.autodev/` holds project-level AutoDev state that gets committed to git.

---

## Failure Modes and Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| OpenCode process dies | Heartbeat timeout in tmux | systemd restart, `/start-work` resumes from boulder state |
| Liaison goes down | No new `autodev-request` issues appearing | AutoDev heartbeat polls GitHub directly as fallback |
| CI is down | `autodev-ci-running` label stuck > 30 min | AutoDev comments on PR, labels `autodev-blocked` |
| Human rejects PR | `autodev-rejected` label or review comment | Prometheus re-plans, Atlas re-implements |
| Model API outage | Agent session error, fallback triggers | OmO's model fallback chains (per-agent) |
| Merge conflict | `gh pr view` shows mergeable: false | Atlas rebases, re-pushes, re-enters verification loop |
| Deployment fails | Health check fails post-deploy | AutoDev rolls back, labels issue `autodev-blocked` |
