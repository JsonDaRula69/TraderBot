# AutoDev Knowledge Architecture

How the AutoDev team stores, retrieves, and guards the Traderbot knowledge base. Design decisions here are ratified — do not modify without human approval.

---

## The Problem

Traderbot has extensive documentation: design decisions, system architecture, dependency contracts, API specifications, operational runbooks, and incident history. This body of knowledge cannot fit in a single agent context window (or even a large one). It must be:

1. **Preloadable** — existing Traderbot knowledge must be seeded into the system before any agent session runs
2. **Accessible on demand** — agents query for what they need, not load everything
3. **Trust-ranked** — ratified decisions are treated as truth; agent guesses are clearly labeled
4. **Modification-guarded** — agents cannot silently change ratified decisions
5. **Conflict-aware** — when implementation contradicts a ratified decision, the conflict surfaces

No single existing tool solves all five. The architecture below combines three systems, each covering the dimension it handles best.

---

## Architecture: Five Tiers, Three Systems

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Bootstrap (always in context)                        │
│ AGENTS.md, projectbrief.md, activeContext.md                 │
│ ~2-4KB total. Identity and standing orders.                  │
├─────────────────────────────────────────────────────────────┤
│ Tier 1.5: Working Memory (Magic Context)                    │
│ Auto-captured session knowledge, dreamer-consolidated,       │
│ semantically recalled. Persists across sessions.             │
│ Grows organically from active work.                          │
├─────────────────────────────────────────────────────────────┤
│ Tier 2: Ratified Decisions (Loreguard)                       │
│ Design decisions, ADRs, deprecation notices, incident        │
│ lessons, architectural constraints.                         │
│ Human-approved. Agents READ freely, CANNOT modify.          │
├─────────────────────────────────────────────────────────────┤
│ Tier 3: Technical Reference (filesystem + Context7)          │
│ API contracts, system architecture, Kalshi/OpenClaw specs.   │
│ Read on demand. Not loaded unless queried.                   │
├─────────────────────────────────────────────────────────────┤
│ Tier 4: Code-level Knowledge (AST grep + LSP)                │
│ Live queries against the actual codebase.                    │
│ Never stored — always derived from current code.             │
└─────────────────────────────────────────────────────────────┘
```

### Why three systems instead of one

| Dimension | Magic Context | Loreguard | Files + Context7 |
|-----------|--------------|-----------|-------------------|
| **Preloading** | No mechanism — memories only come from session work or agent `ctx_memory write` | `loreguard sync import` from `.loreguard/` markdown | Files are preloaded by definition — they exist in the repo |
| **Session continuity** | Excellent — compartments, historian, dreamer keep long sessions coherent | None — each query is stateless | None — stateless reads |
| **Automatic capture** | Excellent — historian extracts knowledge from sessions automatically | Agents can `suggest_lore` (draft) but not auto-capture | None — manual authoring |
| **Trust/provenance** | None — agents can `ctx_memory write` directly, no approval gate | Core strength — draft/approve lifecycle, confidence clamping, source requirements | None — any file edit changes the reference |
| **Modification guardrails** | None — agents can update/archive/merge without approval | Agents cannot approve/deprecate/supersede. CLI-only. | Git permissions only |
| **Conflict detection** | None — if code contradicts a memory, nothing surfaces | `report_conflict` creates a draft counter-record, never mutates original | None |
| **Selective retrieval** | Yes — semantic search across memories + session history | Yes — FTS5 keyword search, compact summaries | Yes — read specific files on demand |
| **Semantic search** | Yes — local embeddings + cosine similarity | No — FTS5 keyword only | N/A — direct file reads |
| **Cross-session persistence** | Yes — SQLite store survives sessions | Yes — SQLite + git-synced `.loreguard/` | Yes — files in repo |

None of these three systems subsumes the others. They solve orthogonal problems. The architecture uses each for what it does best and bridges the gaps explicitly.

---

## Tier 1: Bootstrap Context

**What:** Essential identity and standing orders that every agent needs every session.

**Storage:** Plain markdown files in the repo. Loaded by OpenCode's workspace bootstrap system.

**Size budget:** ~2-4KB total. These files are paid for on every prompt.

| File | Content |
|------|---------|
| `AGENTS.md` | Team structure, standing orders, label protocol |
| `.autodev/memory/projectbrief.md` | What Traderbot is, critical subsystems, constraints |
| `.autodev/memory/activeContext.md` | Current work focus, open questions |
| `.autodev/memory/techContext.md` | Key technologies, APIs, dev setup |

---

## Tier 1.5: Working Memory (Magic Context)

**What:** Knowledge that emerges organically from active work sessions. The agent's "working memory" — what it learned this week, patterns it noticed, gotchas it hit.

**Storage:** Magic Context's SQLite database. Automatically captured by the historian during sessions. Consolidated by the dreamer overnight.

**How it grows:**
1. Agent works on a task, hits a gotcha, discovers a pattern
2. Historian compresses the session, promotes durable observations to memories
3. Dreamer consolidates overnight: merges duplicates, verifies against codebase, retires stale
4. Memories are auto-injected into `<project-memory>` block at session start (within token budget)
5. Agent can also explicitly `ctx_memory write` to record something immediately

**The preloading gap.** Magic Context has NO mechanism to preload existing knowledge. Memories only come from:
- Historian promotion from session facts (`auto_promote`)
- Agent `ctx_memory write` during sessions
- Dreamer consolidation

There is no import API, no bulk insert, no pre-seeding tool. You cannot say "here's 50 existing Traderbot design decisions, ingest these." This is the gap that Loreguard fills.

**What belongs here vs. Loreguard:**

| Knowledge type | Magic Context | Loreguard |
|---------------|--------------|-----------|
| "I noticed the pricing agent uses REST polling, not WebSocket" | Yes — organic observation from working in the codebase | No — this is derivable from code |
| "Kalshi rate limit is 10 req/s (from the API docs)" | Maybe — if the agent hit the rate limit and learned it | Yes — if this is a ratified constraint the team decided on |
| "Always use Decimal for P&L, never float — INC-7" | No — this needs trust and provenance | Yes — incident lesson, human-approved |
| "The settlement module was refactored in PR #42" | Yes — working context, useful for continuity | No — this is session history, not a decision |

**Rule of thumb:** If wrong knowledge would cause real damage (financial, security, operational), it belongs in Loreguard. If it's useful context that helps the agent work faster, it belongs in Magic Context.

---

## Tier 2: Ratified Decisions (Loreguard)

**What:** Decisions the team has reviewed and approved. Treated as truth by all agents.

**Storage:** Loreguard SQLite database. Synced to `.loreguard/` in the repo for git-based sharing.

**Retrieval:** Agents call `search_lore` when their task touches a domain with ratified decisions. Results are compact, trust-ranked summaries.

**The preloading solution.** Loreguard solves the preloading problem through its sync pipeline:

1. **Write decisions as markdown ADRs** in `.autodev/decisions/`
2. **Import into Loreguard** via `loreguard sync import .loreguard/`
3. **Human ratifies** via `loreguard review`
4. **Agents query on demand** via `search_lore` MCP tool

This is the primary path for seeding existing Traderbot knowledge into the AutoDev system.

### The trust model (non-negotiable)

| Principle | Enforcement |
|-----------|-------------|
| Agents can READ ratified decisions freely | `search_lore` and `get_lore` always work |
| Agents can SUGGEST new decisions | `suggest_lore` creates a **draft** — hidden from default search |
| Agents CANNOT approve, deprecate, or supersede | No approval tool in MCP server. CLI-only. |
| Agent suggestions cannot claim high confidence | Drafts clamp to `medium` even if agent asks for `high` |
| No high confidence without a source | Sourceless records clamped to `medium` |
| Agents can CHALLENGE ratified decisions | `report_conflict` creates draft counter-record. Original never mutated. |
| Credential-shaped content is refused | Write path detects and rejects secrets. No override. |

### What belongs in Loreguard

**IN scope — what the code cannot tell you:**

- **Why** a decision was made (the code shows the choice, not the reasoning)
- **What NOT to do** that the code may still contain (deprecated patterns being migrated)
- **Incident lessons** (post-mortem knowledge that prevents recurrence)
- **Cross-module policy** ("risk manager must approve trades > $500")
- **Constraints and invariants** ("settlement must be idempotent")
- **Deprecation notices** ("bcrypt deprecated, use Argon2id")
- **Staleness signals** ("this rule was true as of v2.1")

**OUT of scope — what the agent can derive from code:**

- Function signatures, type annotations, import graphs (Tier 4)
- Current conventions visible in the codebase (just read the code)
- Generic programming knowledge the model already has
- Obvious facts from a nearby README

### Traderbot-specific lore tags

| Tag | Domain |
|-----|--------|
| `kalshi` | Kalshi API integration decisions |
| `trading` | Trade execution, order flow |
| `risk` | Risk management, position limits |
| `pnl` | P&L calculation, settlement |
| `openclaw` | OpenClaw gateway, agents, config |
| `architecture` | System structure, module boundaries |
| `security` | Auth, secrets, API keys |
| `deployment` | Deploy, rollback, health checks |

### ADR + Loreguard dual storage

Every ratified decision exists in two places:

1. **Loreguard SQLite** — for agent queries during work (fast, trust-ranked, selective)
2. **`.autodev/decisions/ADR-NNN.md`** — git-committed ADRs for human review, audit trail, offline reference

Loreguard sync keeps them in sync:
- `loreguard sync export .loreguard` — dumps active lore to markdown
- `loreguard sync import .loreguard` — loads lore from markdown into SQLite

---

## Tier 3: Technical Reference

**What:** Detailed technical documentation that agents need on demand but should not carry in every session.

**Storage:** Markdown files in `.autodev/reference/` plus Context7 MCP for third-party library docs.

**Preloading:** These files ARE the preload. They exist in the repo before any agent runs. Agents read them on demand when their task touches the relevant domain.

```
.autodev/reference/
├── system-architecture.md
├── kalshi/
│   ├── rest-api.md
│   ├── websocket-api.md
│   └── order-types.md
├── openclaw/
│   ├── agent-config.md
│   ├── cron-scheduling.md
│   └── channel-routing.md
├── dependencies/
│   └── ...
└── operations/
    ├── deployment.md
    ├── rollback.md
    └── health-checks.md
```

**Third-party docs:** Context7 MCP (`mcp__context7`) for Pydantic, httpx, OpenClaw SDK, etc. Not for Traderbot-specific APIs.

---

## Tier 4: Code-level Knowledge

**What:** The actual state of the codebase — function signatures, type contracts, call graphs.

**Storage:** None. Always derived from live code.

**Retrieval:** AST grep, LSP tools, ripgrep, Explore agent.

**Principle:** "Lore is for what the agent CAN'T derive from code." Don't duplicate what tools can discover.

---

## The Preloading Pipeline

This is the critical path for seeding existing Traderbot knowledge into the AutoDev system. No single tool handles it end-to-end. The pipeline combines all three systems.

### Phase 1: Inventory existing knowledge

Audit what Traderbot documentation already exists:

- Design docs, ADRs, READMEs
- API specifications (Kalshi, OpenClaw)
- Operational runbooks
- Incident post-mortems
- Config documentation
- Architecture diagrams (convert to prose)

### Phase 2: Route each document to the right tier

| Document type | Destination | Why |
|---------------|-------------|-----|
| Design decisions with reasoning | Loreguard (Tier 2) | Needs trust, provenance, approval gates |
| Incident post-mortems | Loreguard (Tier 2) | Prevents recurrence, needs ratification |
| Deprecation notices | Loreguard (Tier 2) | "What NOT to do" is the core use case |
| API specifications | `.autodev/reference/` (Tier 3) | Reference material, read on demand |
| Architecture overviews | `.autodev/reference/` (Tier 3) | Too large for Tier 1, not a decision |
| Dev setup instructions | `.autodev/reference/` (Tier 3) | Operational reference |
| Project identity/constraints | `.autodev/memory/projectbrief.md` (Tier 1) | Essential, small, always needed |
| Key technical constraints | `.autodev/memory/techContext.md` (Tier 1) | Summary only — details in Tier 3 |

### Phase 3: Seed Loreguard

For each decision/rule/constraint:

1. Write it as a draft ADR in `.autodev/decisions/ADR-NNN-slug.md`
2. Add it to the `.loreguard/` sync directory with proper metadata:
   - `status: draft` (until human ratifies)
   - `confidence: medium` (agent-suggested can't be high)
   - `source: ADR-NNN` or `source: <original-doc-url>`
   - `tags: [kalshi, trading, ...]`
3. Import: `loreguard sync import .loreguard/`
4. Human reviews: `loreguard review` — approve, edit, or reject each record

### Phase 4: Seed Tier 3 reference files

Copy existing API specs, architecture docs, and operational runbooks into `.autodev/reference/`. These are just files — no special ingestion needed. The agent reads them when the task calls for it.

### Phase 5: Update Tier 1 bootstrap

Summarize the most critical constraints into the bootstrap files. Keep these under 4KB total. Every byte here is paid for on every prompt, so be selective.

### Phase 6: Let Magic Context fill in organically

As agents work on Traderbot tasks, Magic Context's historian will:
- Notice patterns the agent encounters
- Promote useful observations to project memories
- Build semantic index for future recall

This layer doesn't need preloading — it grows from actual work. But it does need the preloaded layers (Loreguard + reference files) to prevent the agent from re-deriving things that are already decided.

---

## Behavioral Guardrails

### Guardrail 1: Search before you assume

Before implementing anything in these domains, agents MUST call `search_lore`:

- `kalshi`, `trading`, `risk`, `pnl`, `security`, `architecture`, `deployment`

This rule is embedded in AGENTS.md so it's loaded every session.

### Guardrail 2: Ratified decisions are truth

When `search_lore` returns an `active` record with `high` confidence and a `source`:
- Agent MUST follow that decision
- Agent CANNOT silently contradict or work around it
- If the agent believes the decision is wrong, it MUST use `report_conflict`

When lore returns `draft` or `low` confidence:
- Treat as a CLUE, not authority
- Verify against actual code before relying on it

### Guardrail 3: Stale lore is demoted, not deleted

When `search_lore` returns a record with `stale: true`:
- Treat as POTENTIALLY OUTDATED
- Verify the decision still holds before relying on it
- Do not silently ignore it

### Guardrail 4: Uncertainties are escalated, not assumed

When an agent encounters a situation not covered by any lore:

1. Search lore — check for ratified decisions
2. Search Magic Context — check for working memories from past sessions
3. Search reference docs — check Tier 3 files
4. Search the code — check if derivable from live code (Tier 4)
5. If still uncertain: label `autodev-blocked`, comment with the question, present to human

Agent MUST NOT:
- Make up a decision and implement it
- Assume "the old way is fine" without checking
- Choose between approaches without escalating
- Contradict existing lore without reporting the conflict

### Guardrail 5: New knowledge flows through ratification

When an agent discovers something worth recording as a decision:

1. Use `suggest_lore` — creates a **draft**, hidden from search
2. Human reviews via `loreguard review`
3. Only after approval does it become `active` and visible to all agents

For working context (not decisions), use `ctx_memory write` in Magic Context. This records the observation but without the trust guarantees of Loreguard.

### Guardrail 6: Conflicts are surfaced, not buried

When code contradicts ratified lore:

1. Use `report_conflict` — creates draft counter-record
2. Original is NEVER mutated
3. Human decides: update lore, fix code, or reject conflict

Agent MUST NOT silently "fix" code to match lore, or update lore to match code.

### Guardrail 7: Magic Context memories are clues, not truth

Magic Context has no trust model. Agents can write memories directly. Therefore:

- Magic Context memories are treated as **working context**, not **ratified decisions**
- If a Magic Context memory contradicts a Loreguard record, Loreguard wins
- If a Magic Context memory seems wrong, the agent should verify against code and lore
- Do not archive or update Magic Context memories just because they disagree with your current approach — they may be correct

---

## MCP Configuration

### Loreguard (Tier 2)

```jsonc
{
  "loreguard": {
    "command": "npx",
    "args": ["-y", "loreguard-mcp"],
    "env": {
      "LOREGUARD_DB_PATH": "<project>/.loreguard/lore.db",
      "LOREGUARD_ALLOW_MCP_ABSENCE": "1"
    }
  }
}
```

### Magic Context (Tier 1.5)

Installed as an OpenCode plugin via `npx @cortexkit/magic-context@latest setup`. Provides:
- `ctx_memory` tool — write/update/archive/merge memories
- `ctx_search` tool — search memories, session history, git commits
- `ctx_reduce` tool — manage context window
- Auto-injected `<project-memory>` block at session start
- Historian + dreamer agents (hidden subagents)

No MCP configuration needed — it's a plugin, not an MCP server.

### Context7 (Tier 3 — third-party docs)

Already available as `mcp__context7`. Use for Pydantic, httpx, OpenClaw SDK, etc.

### AST Grep (Tier 4)

Already available as `mcp__ast_grep`. Use for structural code search.

---

## Cold Start: Seeding the Knowledge Base

When AutoDev first connects to a Traderbot repo, all tiers are empty. The cold start procedure:

### Step 1: Inventory existing docs

Agent reads the repo and catalogs:
- README, existing docs, ADRs
- Config files (openclaw.json, environment configs)
- Recent commits (patterns, deprecations)
- Incident history (if documented)
- API documentation (Kalshi, OpenClaw)

### Step 2: Route to tiers

Classify each document per the routing table in Phase 2 above.

### Step 3: Seed Loreguard

For each decision/rule/constraint, use `suggest_lore` with:
- `source` pointing to the original document
- `tags` from the Traderbot-specific tag set
- `confidence: "medium"` (agent-suggested, can't be high)

Human ratifies via `loreguard review`.

### Step 4: Seed reference files

Copy detailed specs into `.autodev/reference/`.

### Step 5: Update bootstrap

Summarize critical constraints into Tier 1 files. Keep under 4KB.

### Step 6: Let Magic Context learn organically

As work happens, Magic Context captures what the agent actually learns. No preloading needed for this tier — it grows from use.

---

## Quality Gates for the Knowledge Base

| Gate | Check | Frequency |
|------|-------|-----------|
| Lore freshness | `loreguard doctor` — check for stale records | Every dream run |
| Reference accuracy | Agent flags code/reference conflicts via `report_conflict` | During implementation |
| Bootstrap size | `wc -c AGENTS.md .autodev/memory/*.md` — must stay under 4KB | Before every commit that touches these files |
| Magic Context health | Magic Context doctor — check DB integrity, embedding status | Weekly |
| Draft queue depth | `loreguard review --list` — unreviewed drafts should not accumulate | Daily (heartbeat) |
| Conflict queue | `loreguard search --include-drafts tag:conflict-report` | During any PR review |
