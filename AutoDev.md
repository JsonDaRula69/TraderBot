# AutoDev — Coding Agent Knowledge Architecture Research

> Living document cataloguing external solutions for coding agent memory and knowledge systems. This is a research reference, not an implementation decision. See `v2roadmap.md` DD-024 and pending discussion items for the Coding Agent design decisions.

---

## Category 1: Markdown Memory Banks (Cline Memory Bank Pattern)

### Overview

The Cline Memory Bank pattern is the most widely-adopted approach to coding agent memory. The agent maintains a structured set of markdown files in a `memory-bank/` directory. These files are read in full at the start of every session and updated during work. The pattern originated as custom instructions for the Cline VS Code extension and has since been ported to MCP servers and other agent runtimes.

The core idea is that the agent has "amnesia" between sessions — it starts fresh each time — and relies entirely on the memory bank files to reconstruct context. The files form a hierarchy: `projectbrief.md` is the foundation, feeding into `productContext.md`, `systemPatterns.md`, and `techContext.md`, which all converge into `activeContext.md` and `progress.md`.

### Key Projects

| Project | Stars | URL |
|---|---|---|
| Cline Memory Bank (original pattern) | — | [docs.cline.bot/cline-memory-bank](https://docs.cline.bot/improving-your-prompting-skills/cline-memory-bank) |
| alioshr/memory-bank-mcp | 911 | [github.com/alioshr/memory-bank-mcp](https://github.com/alioshr/memory-bank-mcp) |
| hudrazine/claude-code-memory-bank | 40 | [github.com/hudrazine/claude-code-memory-bank](https://github.com/hudrazine/claude-code-memory-bank) |
| Shivansh12t/claude-code-memory-bank | 6 | [github.com/Shivansh12t/claude-code-memory-bank](https://github.com/Shivansh12t/claude-code-memory-bank) |

### How It Works

The agent reads all memory bank files at the start of every session. No selective retrieval — everything is loaded into context. The files are plain markdown, organized into a fixed hierarchy:

1. **`projectbrief.md`** — Foundation document defining core requirements and goals
2. **`productContext.md`** — Why the project exists, problems it solves, user experience goals
3. **`systemPatterns.md`** — System architecture, key technical decisions, design patterns
4. **`techContext.md`** — Technologies, development setup, technical constraints, dependencies
5. **`activeContext.md`** — Current work focus, recent changes, next steps, active decisions
6. **`progress.md`** — What works, what's left to build, current status, known issues

The `memory-bank-mcp` variant adds MCP tool access (`memory_bank_read`, `memory_bank_write`, `memory_bank_update`, `list_projects`, `list_project_files`) so other agents and external tools can read/write the files. It supports multi-project isolation with project-specific directories.

The Claude Code variant adds a skill-based workflow with `/memory-bank` slash command, automatic updates triggered by significant changes, and a `.clinerules` learning journal for project-specific patterns.

### Strengths

- **Zero infrastructure** — plain markdown files, no database, no embedding model, no server
- **Human-readable and auditable** — anyone can open and read the files
- **Self-maintaining** — the agent updates the files as it works
- **Version-controllable** — markdown files can be committed to git
- **Portable** — no lock-in to any specific tool or platform
- **MCP access** — the MCP variant makes memory bank files accessible to other agents

### Weaknesses

- **No selective retrieval** — the agent reads all files at session start or nothing. There's no "give me the P&L settlement formula" without also loading the deployment pipeline steps and the risk module architecture. This creates a hard context budget ceiling.
- **No semantic search** — finding information requires reading entire files. There's no vector similarity or keyword search across the memory bank.
- **Flat structure** — six fixed files don't scale well to large codebases. A project like TraderBot has 16+ docs files, hundreds of source modules, and thousands of functions. Six markdown files can't capture that depth without becoming unwieldy.
- **Session persistence, not reference retrieval** — the pattern is designed to solve "the agent forgets everything between sessions," not "the agent needs to quickly find a specific API contract." The memory bank is always in context; it can't be queried on demand.
- **No code-level indexing** — the files contain prose descriptions, not function signatures, type annotations, or import graphs.
- **No version awareness** — files don't track which version of the codebase they describe. Stale information isn't detected automatically.
- **No trust or provenance layer** — the agent writes whatever it wants. There's no human approval gate or confidence scoring.

### Relevant Patterns for TraderBot

- The fixed hierarchy of context files (brief → patterns → active context) is a useful mental model for the Coding Agent's bootstrap files
- The `.clinerules` learning journal maps to what OpenClaw already provides via `MEMORY.md` and `memory/YYYY-MM-DD.md`
- The MCP variant's project isolation model is relevant for multi-agent setups where different agents need different knowledge scopes

---

## Category 2: Agent Operational Layers (AgentOps Pattern)

### Overview

AgentOps is an operational layer that sits on top of existing coding agents (Claude Code, Codex, Cursor, OpenCode). It adds bookkeeping, validation gates, and a compounding knowledge corpus. Rather than replacing the agent, it wraps it with structured workflows: discovery, build, validation, and learning phases, each leaving evidence in a `.agents/` directory.

The key innovation is the "knowledge flywheel" — as agents work, they generate learnings that are mined (`/forge`), reconciled (`/evolve`), and stored as a corpus of markdown wiki pages. This corpus compounds over time without manual curation, since agents read and write to it natively during their work.

### Key Projects

| Project | Stars | URL |
|---|---|---|
| boshu2/agentops | 392 | [github.com/boshu2/agentops](https://github.com/boshu2/agentops) |

### How It Works

AgentOps stores everything in a `.agents/` directory next to the code, in plain markdown:

- **Bookkeeping layer** — Captures runs, decisions, findings, citations, verdicts, and retros in `.agents/`
- **Context compiler** — `ao context assemble` builds phase-scoped context packets; `ao lookup` retrieves decay-ranked knowledge
- **Validation gates** — `/pre-mortem`, `/vibe`, `/council` run multi-model consensus on plans and code. Gates block rather than advise.
- **Knowledge flywheel** — `/forge` mines learnings from past runs; `/evolve` reconciles contradictions; the corpus compounds as a side effect of use.

The context compiler is the key retrieval mechanism. Rather than loading everything, `ao context assemble` builds a targeted context packet for the current phase (discovery, build, validation, etc.). `ao lookup` retrieves curated learnings with decay ranking — recent learnings rank higher than older ones.

The `/council` command is particularly relevant: it spawns independent judges (optionally across different models like Claude and Codex) to evaluate a plan or code change, producing a consolidated verdict with evidence.

### Strengths

- **Self-maintaining corpus** — the knowledge base grows as a side effect of normal work, not through manual curation
- **Phase-scoped context** — instead of loading everything, the context compiler builds targeted packets for the current phase
- **Decay ranking** — recent knowledge ranks higher than older knowledge, reflecting that codebases change
- **Multi-model validation** — the `/council` pattern of independent judges is directly applicable to the agent-debate framework (DD-018)
- **Plain markdown, portable** — `.agents/` is git-committable, forkable, and survives tool changes
- **Works with any agent** — wraps Claude Code, Codex, Cursor, OpenCode

### Weaknesses

- **Session-level knowledge, not reference knowledge** — the corpus captures "what we tried, what failed, what we learned" — operational knowledge from coding sessions. It doesn't contain API contracts, data model specifications, or architectural reference material.
- **Decay ranking assumes knowledge loses value over time** — this is true for session-level operational knowledge ("we tried X pattern and it didn't work") but false for reference documentation ("the risk module enforces position limits via `max_position_per_market_pct`"). Reference knowledge should be stable, not decaying.
- **No semantic search** — `ao lookup` retrieves from markdown files, not from a vector index. It's text-based retrieval, not embedding-based.
- **No code-level indexing** — the corpus is markdown prose, not parsed source code. It can describe what code does, but can't retrieve function signatures or type annotations directly.
- **Plugin ecosystem lock-in** — AgentOps is designed for Claude Code, Codex, Cursor, and OpenCode. Adapting it to OpenClaw would require building a skill or plugin wrapper.
- **No external dependency documentation** — the corpus only covers the project's own code and decisions, not third-party libraries or APIs.

### Relevant Patterns for TraderBot

- The phase-scoped context compiler (`ao context assemble`) is a useful pattern for building targeted context packets before specific tasks (test authoring vs. error diagnosis vs. update verification)
- The `/council` multi-model consensus pattern maps directly to the agent-debate framework (DD-018 Round 2)
- The `.agents/` directory as git-committable, portable knowledge is similar to what OpenClaw already provides via workspace files and the memory-wiki plugin
- The `/forge` → `/evolve` learning loop maps to the improvement framework's "identify suboptimal outcomes → white paper → validation" cycle

---

## Category 3: Team-Ratified Knowledge Bases (Loreguard Pattern)

### Overview

Loreguard is a SQLite-backed MCP server that stores team-ratified knowledge — conventions, architectural decisions, deprecated patterns, gotchas, and incident lessons. The key philosophical distinction from memory banks and agent memory is that loreguard stores *what the team has reviewed and approved*, not what one session inferred.

Agents can search, read, suggest new entries, challenge existing ones, flag gaps, and map boundaries — but they cannot approve, deprecate, or supersede entries. Those operations are CLI-only, gated by human review. This poisoning-prevention guardrail ensures the knowledge base remains trustworthy even when agents propose incorrect information.

### Key Projects

| Project | Stars | URL |
|---|---|---|
| tmj-90/loreguard-mcp | 2 | [github.com/tmj-90/loreguard-mcp](https://github.com/tmj-90/loreguard-mcp) |

### How It Works

Loreguard exposes seven MCP tools with a deliberate separation between agent-accessible and human-only operations:

| Tool | Who uses it | What it does |
|---|---|---|
| `search_lore` | Agent | Retrieve brief, trust-ranked summaries |
| `get_lore` | Agent | Fetch the full body of one record |
| `suggest_lore` | Agent | Propose a new record — lands as a **draft** |
| `report_conflict` | Agent | Challenge an active record — drafts a counter, never mutates the original |
| `record_absence` | Agent | Mark a confirmed gap so it isn't re-discovered |
| `find_dependents` | Agent | Cross-repo blast radius + the rules that govern a contract |
| `declare_boundary` | Agent | Record a provides/consumes edge — lands as a **draft** |

Approval, deprecation, and supersession are CLI-only (`loreguard review`, `loreguard approve`, `loreguard deprecate`). The server exposes no approval tool. Agents can propose, but humans ratify.

Each record has:
- **Status**: `draft`, `active`, `deprecated`, `superseded`
- **Confidence**: `low`, `medium`, `high`
- **Source**: reference to the ADR, incident, or convention that established it
- **Tags**: scoped to repo, team, or tag for targeted retrieval

Retrieval is via SQLite full-text search (FTS5), not vector embeddings. The `search_lore` tool returns compact summaries, not entire documents. Agents call `get_lore` only when they need the full body.

The retrieval rule for agents is explicit and scoped: "Search when the task touches auth/security, dates/timezones, migrations/schema, payments/billing, API contracts, deployment/infra, cross-repo conventions, or unfamiliar services."

### Strengths

- **Trust hierarchy** — distinguishes between "one session believed it" (memory), "always-on instructions" (CLAUDE.md), and "the team ratified it" (loreguard). This three-tier model maps well to the distinction between bootstrap files, accumulated knowledge, and reference documentation.
- **On-demand retrieval** — agents get compact summaries, not whole files. Only `get_lore` returns full records, and only when needed.
- **Poisoning prevention** — agents can propose but not approve. This prevents hallucinated knowledge from polluting the knowledge base.
- **Conflict detection** — `report_conflict` lets agents flag contradictions between what loreguard says and what the code says, creating a path to resolution.
- **Absence tracking** — `record_absence` prevents re-discovery of known gaps.
- **Dependency mapping** — `find_dependents` shows blast radius and governing rules, directly useful for understanding change impact.
- **Narrow tool surface** — seven tools, clear semantics, no ambiguity about what each does.

### Weaknesses

- **Very early stage** — 2 stars, single author, limited real-world testing
- **SQLite FTS5 only** — no semantic/vector search. Keyword-based retrieval works for conventions ("use Argon2id for passwords") but struggles with conceptual queries ("how does settlement logic work?")
- **No code-level indexing** — loreguard stores prose decisions, not function signatures, type annotations, or source code. It can tell you "use Argon2id" but can't show you the actual `hashPassword()` implementation.
- **No embedding model** — retrieval is exact-match and FTS5, not semantic similarity. "Password hashing" and "credential encryption" won't match unless they share keywords.
- **Human approval bottleneck** — for an autonomous TradingBot agent, requiring human approval for every knowledge base update may be too slow. The SysAdmin agent could serve as the approver, but that adds latency.
- **Not OpenClaw-native** — it's a standalone MCP server, not integrated with OpenClaw's memory system or workspace files.

### Relevant Patterns for TraderBot

- The three-tier trust model (always-on instructions / agent memory / team-ratified knowledge) is directly applicable to the Coding Agent's knowledge architecture
- The narrow tool surface with clear semantics (`search`, `get`, `suggest`, `report_conflict`, `find_dependents`) is a good design reference for `traderbot__reference`
- The `suggest` → `review` → `approve` flow for knowledge base updates maps to the SysAdmin approval pattern in DD-023
- The `find_dependents` blast-radius query is valuable for the Coding Agent when writing treatments that affect shared modules

---

## Category 4: Semantic Code Search MCP Servers (Codesearch / Code-Context-v2 Pattern)

### Overview

These tools index source code using AST-aware chunking (tree-sitter parsing that aligns chunks to functions, classes, and methods rather than arbitrary line ranges), embed the chunks with vector models, and serve semantic search via MCP protocol. They're designed to answer the question "where is this implemented?" — the single most important query for a coding agent that needs to understand a codebase.

The category includes a range of implementations from lightweight local tools to full-featured multi-repo servers, but they share the same core architecture: parse → chunk → embed → index → search.

### Key Projects

| Project | Stars | Language | URL |
|---|---|---|---|
| flupkede/codesearch | 44 | Rust | [github.com/flupkede/codesearch](https://github.com/flupkede/codesearch) |
| enzodevs/code-context-v2 | 1 | Python | [github.com/enzodevs/code-context-v2](https://github.com/enzodevs/code-context-v2) |
| elastic/semantic-code-search-mcp-server | 13 | TypeScript | [github.com/elastic/semantic-code-search-mcp-server](https://github.com/elastic/semantic-code-search-mcp-server) |
| DeDeveloper23/codebase-mcp | 80 | TypeScript | [github.com/DeDeveloper23/codebase-mcp](https://github.com/DeDeveloper23/codebase-mcp) |

### How Codesearch Works (Rust, most feature-complete)

**Indexing:**
1. Walk the repository file tree, respect `.gitignore`
2. Parse each file with tree-sitter (supports 16 languages)
3. Chunk at AST boundaries — functions, classes, methods (not arbitrary line ranges)
4. Embed chunks with a local embedding model (no GPU required, runs on CPU)
5. Store vectors in arroy (ANN index backed by LMDB), full-text in Tantivy (BM25)

**Search:**
- **Semantic mode** (`search` tool): Vector ANN + BM25 + Reciprocal Rank Fusion (RRF)
- **Literal mode** (`search` tool with `mode=literal`): Tantivy FTS / regex
- **Symbol navigation** (`find` tool): Jump to definitions, find usages, trace imports and dependents
- **Exploration** (`explore` tool): AST outlines, similar code discovery
- **On-demand retrieval** (`get_chunk` tool): Returns metadata by default; agents fetch full code only when needed
- **Impact analysis** (`find_impact` tool): Trace blast radius for C# symbols (extensible)

**Multi-repo serve mode:** Fan-out queries across repository groups with cross-repo RRF ranking. Index once, search across multiple repositories simultaneously.

**Key design choices:**
- Token-efficient: returns metadata by default, full code on demand
- Lightweight: hundreds of MB, CPU-only, no Docker
- Zero-config for single repos: `codesearch index && codesearch mcp`
- Incremental updates: re-index only changed files

### How Code-Context-v2 Works (Python, Voyage AI embeddings)

**Indexing:**
1. Parse with tree-sitter (AST-aware chunking)
2. Embed with `voyage-4-large` (documents) and `voyage-4-lite` (queries) — same embedding space, asymmetric retrieval
3. Store in PostgreSQL/pgvector + pgvectorscale (recommended), LanceDB (embedded), or SQLite + FTS5 + sqlite-vec (experimental)
4. Rerank with `rerank-2.5` for precision
5. Dedup with overlap/containment + Jaccard similarity filtering

**Search:**
- Intent resolution: converts natural language queries to targeted search terms
- Result controls: limit, offset, score thresholds, file type filtering
- Cross-file context: includes related files that reference or are referenced by the result
- Quality logging: tracks retrieval metrics for tuning

**Architecture:** RetrievalPipeline facade → Voyage AI (query embed + rerank) → vector store (pgvector/LanceDB/SQLite) → Markdown-formatted results with file paths, line numbers, relevance scores.

### Strengths

- **AST-aware chunking** — chunks align to functions, classes, and methods, not arbitrary line ranges. When the agent asks for "the TreatmentInterface contract," it gets the whole ABC, not a fragment.
- **Hybrid retrieval** — vector similarity for semantic queries ("how does settlement work?") combined with BM25 for exact-match queries (`ValidatedDecision`). RRF fusion produces better results than either alone.
- **On-demand retrieval** — metadata first, full code only when needed. This is the key insight: the agent gets "I found 3 relevant chunks at `shared.py:84`, `harness.py:156`, `results.py:42`" and then decides which to fetch in full.
- **Multi-repo support** — codesearch can index and search across multiple repositories simultaneously, relevant for TraderBot + OpenClaw + agent-debate
- **Local/offline** — no cloud API required for the embedding model (codesearch). Code-context-v2 requires a Voyage AI API key for embeddings.
- **Voyage AI integration** — code-context-v2 uses the same `voyage-4-large` model that TraderBot already uses for news embeddings, and `voyage-4-lite` for queries, with the same vector space. This is a direct compatibility point.

### Weaknesses

- **Source code only** — none of these tools index documentation files (`docs/`, `README.md`, `CHANGELOG.md`, design decisions, ADRs). They can't answer "what does DD-015 say about MCP server architecture?" or "what's the deployment bar for paper-to-live transitions?"
- **No external dependency documentation** — they index your own code, not third-party library docs. For "how does the Kalshi WebSocket client work?", they find your code that uses it, but not the API documentation.
- **No trust/provenance layer** — results are ranked by relevance, not by trustworthiness. There's no distinction between "the team reviewed and approved this" and "an AI generated this."
- **No version awareness** — the index reflects the current state of the code. If you re-index after a deploy, old knowledge is gone. There's no way to query "what did this function look like in v0.15.42?"
- **No claim/conflict model** — there's no mechanism for flagging contradictions or recording that a search result conflicts with documentation.

### Relevant Patterns for TraderBot

- AST-aware chunking is essential — the Coding Agent needs whole function definitions, not line fragments
- Hybrid retrieval (vector + BM25 + RRF) should be the retrieval strategy for `traderbot__reference`
- The metadata-first, full-code-on-demand pattern is exactly how `traderbot__reference` should work
- The `voyage-4-large` / `voyage-4-lite` asymmetric embedding pattern is worth adopting since TraderBot already uses `voyage-4-large`
- The multi-repo serve pattern is relevant for future indexing of OpenClaw docs alongside TraderBot

---

## Category 5: Documentation-as-Context Services (Context7 Pattern)

### Overview

Context7 is an MCP server that fetches up-to-date, version-specific documentation for third-party libraries and frameworks. Instead of relying on the LLM's training data (which may be months or years old), the agent calls Context7 to pull the latest docs for React, Next.js, Supabase, Pydantic, or any of thousands of indexed libraries directly into its context.

It solves the specific problem of "LLMs hallucinate outdated APIs" by providing a live documentation retrieval layer. The agent says "use context7" in its prompt, and Context7 fetches the correct, version-specific documentation for the libraries mentioned.

### Key Projects

| Project | Stars | URL |
|---|---|---|
| upstash/context7 | 57,431 | [github.com/upstash/context7](https://github.com/upstash/context7) |

### How It Works

**Two modes:**

1. **CLI + Skills mode** — installs a skill that guides the agent to fetch docs using `ctx7` CLI commands. No MCP required.
2. **MCP mode** — registers a Context7 MCP server so the agent can call documentation tools natively via `resolve-library-id` and `get-library-docs`.

**MCP tools:**

| Tool | What it does |
|---|---|
| `resolve-library-id` | Takes a library name and returns the Context7 ID and matching libraries |
| `get-library-docs` | Takes a Context7 ID (and optional topic/version) and returns up-to-date documentation |

**Key design choices:**
- Documentation is fetched from the source (GitHub repos, official docs sites) on demand
- Version-specific: you can request docs for a specific library version
- Topic-scoped: you can narrow the retrieval to a specific API or feature
- Token-budgeted: you can set `tokens` limits to control how much documentation is returned
- No API key required for basic use (rate-limited), API key for higher limits
- 57K+ stars, widely adopted across Claude Code, Cursor, Windsurf, Continue, and other coding agents

### Strengths

- **Eliminates API hallucination** — the agent gets the actual, current documentation for the library it's working with, not what the LLM's training data remembers
- **Version-specific** — request docs for the exact version of the library you're using
- **Topic-scoped** — narrow retrieval to "Pydantic validators" or "Pydantic BaseSettings" instead of loading all of Pydantic
- **Zero indexing effort** — Context7 maintains the documentation index. You don't need to pre-index or embed anything for third-party libraries.
- **MCP-native** — works as a standard MCP server, directly compatible with OpenClaw's MCP integration (DD-015)
- **Free tier available** — no cost for basic use

### Weaknesses

- **Third-party libraries only** — Context7 covers public libraries and frameworks on its index. It cannot provide documentation for TraderBot's own code, architecture, design decisions, or internal APIs.
- **No code-level detail** — Context7 returns documentation (prose, examples, API references), not source code. For "show me the `ValidatedDecision` class implementation," you need a code search tool, not a documentation service.
- **No architectural knowledge** — it doesn't know about design decisions, ADRs, or the reasoning behind why things are built a certain way.
- **Rate limits** — the free tier has rate limits. For an autonomous agent making frequent queries, these could be a constraint.
- **Dependency on external service** — Context7 is a hosted service. If it's down, the agent loses access to third-party documentation. No offline fallback.

### Relevant Patterns for TraderBot

- Context7 is directly usable via the `mcp__context7` tool that's already configured in this environment
- It eliminates the need to pre-index Dep_Docs/ for libraries that Context7 already covers (Pydantic, httpx, typer, ChromaDB, SQLite, etc.)
- For TraderBot-specific APIs (Kalshi, OpenClaw, Open-Meteo, FRED, NewsAPI, Voyage AI), Dep_Docs/ indexing is still needed since Context7 won't have these
- The topic-scoped, token-budgeted retrieval pattern (get docs for a specific API, with a token limit) is a good design reference for `traderbot__reference`

---

## Cross-Category Comparison

| Dimension | Memory Banks | AgentOps | Loreguard | Code Search MCP | Context7 |
|---|---|---|---|---|---|
| **Knowledge type** | Session context | Operational learnings | Team-ratified decisions | Source code contracts | Third-party library docs |
| **Retrieval method** | Full file read | Markdown lookup with decay | FTS5 keyword search | Vector + BM25 hybrid (RRF) | On-demand API fetch |
| **Selective retrieval** | No — all files loaded | Partial — phase-scoped packets | Yes — compact summaries | Yes — metadata first, code on demand | Yes — topic-scoped, token-budgeted |
| **Code awareness** | No — prose only | No — prose only | No — prose only | Yes — AST-aware chunking | No — docs only |
| **Semantic search** | No | No | No (FTS5 only) | Yes (vector embeddings) | N/A (live fetch) |
| **Trust/provenance** | None | Session-level | Team-ratified with approval gates | None (relevance-ranked) | Source = official docs |
| **Conflict detection** | None | `/evolve` reconciliation | `report_conflict` tool | None | N/A |
| **Version awareness** | Manual | Decay-ranked (recent > old) | Manual status fields | Current state only | Yes — version-specific |
| **External deps** | No | No | No | No | Yes — thousands of libraries |
| **Infrastructure** | None (markdown files) | `.agents/` directory + `ao` CLI | SQLite MCP server | Rust/Python MCP server + embedding model | Hosted MCP service |
| **OpenClaw compatible** | Partially (workspace files) | Needs adaptation (skill/plugin) | MCP server (compatible) | MCP server (compatible) | MCP server (compatible) |

---

## References

- [Cline Memory Bank documentation](https://docs.cline.bot/improving-your-prompting-skills/cline-memory-bank)
- [memory-bank-mcp](https://github.com/alioshr/memory-bank-mcp) — MCP server for Cline Memory Bank pattern
- [claude-code-memory-bank](https://github.com/hudrazine/claude-code-memory-bank) — Memory management for Claude Code
- [AgentOps](https://github.com/boshu2/agentops) — Operational layer for coding agents with knowledge flywheel
- [Loreguard](https://github.com/tmj-90/loreguard-mcp) — Team-ratified knowledge MCP server
- [Codesearch](https://github.com/flupkede/codesearch) — Multi-repo semantic code search MCP server (Rust)
- [Code-Context-v2](https://github.com/enzodevs/code-context-v2) — Semantic code search with Voyage AI embeddings (Python)
- [Elastic Semantic Code Search MCP](https://github.com/elastic/semantic-code-search-mcp-server) — Elastic's semantic code search
- [Context7](https://github.com/upstash/context7) — Up-to-date library documentation for LLMs (57K★)
- [Repomix](https://github.com/yamadashy/repomix) — Packs entire repositories into AI-friendly files (26K★)
- [RepoMemory](https://github.com/patchhive/repomemory) — Durable repo memory from merged PRs, reviews, and issues
- [Consolidation Memory](https://github.com/InitialDBklyn/consolidation-memory) — FAISS + SQLite memory for AI agents
- [OpenClaw Memory System](https://docs.openclaw.ai/concepts/memory) — OpenClaw's built-in memory, search, and dreaming
- [OpenClaw Memory Wiki](https://docs.openclaw.ai/plugins/memory-wiki) — Compiled knowledge vault plugin
- [OpenClaw Memory Search](https://docs.openclaw.ai/concepts/memory-search) — Hybrid vector + keyword memory search
