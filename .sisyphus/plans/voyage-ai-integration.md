# Voyage AI Integration Documentation Update

## TL;DR

> **Quick Summary**: Update TraderBot's `docs/` files to incorporate Voyage AI as a planned enhancement across the news/sentiment pipeline (Phase 7), decision logging (Phase 6), heartbeat pattern clustering, and market chart analysis. This is documentation-only — no code implementation.
>
> **Deliverables**:
> - Updated `docs/news-sentiment.md` — Voyage-enhanced pipeline architecture, model selection, thresholds
> - Updated `docs/architecture.md` — ChromaDB component, embedding data flows, updated dependency rules
> - Updated `docs/self-learning.md` — Semantic decision search, heartbeat clustering with embeddings
> - Updated `docs/product-roadmap.md` — Phase 6/7 component additions, new Phase 7 sub-components
> - Updated `docs/research.md` — Voyage AI research findings, comparison to alternatives
> - New `docs/decisions/voyage-ai-adoption.md` — ADR for Voyage AI model selection and integration approach
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: T1 (ADR) → T2-T5 (docs updates) → T6 (roadmap) → Final verification

---

## Context

### Original Request
User asked to research Voyage AI (https://docs.voyageai.com/docs/introduction) and consider where it could enhance the TraderBot roadmap. After discussion, the scope clarified to: **update docs/ files only** to prepare for future implementation. No code changes.

### Interview Summary
**Key Discussions**:
- Voyage integration approach: Enhance Phase 7 directly — Voyage is a core component, not a later add-on
- Vector storage: ChromaDB for embedding persistence and similarity search
- Model selection: Best quality regardless of cost — `voyage-4-large` for general text, `voyage-finance-2` for financial text, `rerank-2.5` (not lite) for classification fallback, `voyage-multimodal-3.5` for charts
- Scope: All viable Voyage applications — classifier, impact assessor, sentiment uplift, decision log search, heartbeat clustering, chart embedding
- This is docs-only: updating documentation to prepare for future implementation, not implementing code
- Update all relevant docs/ files

**Research Findings**:
- `voyage-4-large` — best general-purpose embedding (32K context, 1024/256/512/2048 dims, $0.12/M tokens)
- `voyage-finance-2` — domain-optimized for financial text (32K context, 1024 dims, $0.12/M tokens)
- `rerank-2.5` — highest-quality reranker with instruction-following (32K context, $0.05/M tokens)
- `voyage-multimodal-3.5` — text+image embeddings for chart processing ($0.12/M text tokens + $0.60/B pixels)
- ChromaDB — Python-native vector DB with metadata filtering, persistent collections, async support
- Architecture principle preserved: "dumb pipe with smart guards" — Voyage computes similarity, agent decides strategy
- Batch API: 33% discount for deferred operations, 12h completion window — safe for heartbeat clustering, initial ChromaDB population, re-embedding; NOT for real-time operations

### Metis Review
**Identified Gaps** (addressed):
- **Phase 6 doesn't exist yet**: Docs should describe Voyage enhancements as part of Phase 6/7 specs, not as modifications to existing code
- **Voyage API fallback needed**: Docs must describe graceful degradation to VADER/TextBlob-only mode
- **ChromaDB + SQLite consistency**: Docs must specify SQLite is authoritative; ChromaDB is search index
- **Reranking threshold**: Docs must set explicit 0.5–0.7 confidence range
- **Sentiment uplift trigger**: Docs must set explicit VADER compound -0.3 to +0.3 range
- **Decision log scope**: Last 90 days, max 1000 results
- **Chart embedding trigger**: Agent request OR `image_url` field in news item only
- **No unbounded growth**: ChromaDB TTL or max entries policy

---

## Work Objectives

### Core Objective
Update TraderBot's documentation to fully specify Voyage AI integration across the news/sentiment pipeline, decision logging, heartbeat clustering, and chart analysis — so that when Phases 6-7 are implemented, the specs already describe the Voyage-enhanced architecture.

### Concrete Deliverables
- `docs/news-sentiment.md` — Updated pipeline architecture with Voyage layers, model selection, threshold definitions, fallback behaviors, latency budgets
- `docs/architecture.md` — ChromaDB component in component map, embedding data flows, updated module dependencies, updated toolkit-vs-agent boundary table
- `docs/self-learning.md` — Semantic decision search section, heartbeat clustering with embeddings section, ChromaDB integration for learnings
- `docs/product-roadmap.md` — Updated Phase 6/7 component tables with Voyage sub-components, new success criteria, updated Advanced Capabilities table
- `docs/research.md` — Voyage AI research findings, comparison table vs alternatives, ChromaDB evaluation
- `docs/decisions/voyage-ai-adoption.md` — ADR documenting model selection rationale, integration approach decision, vector store decision

### Definition of Done
- [ ] All 5 existing docs files reflect Voyage AI integration in their respective domains
- [ ] New ADR exists with model selection rationale
- [ ] Phase 7 pipeline architecture shows Voyage enhancement layers with explicit thresholds
- [ ] Component map includes ChromaDB and embedding modules
- [ ] No code files are modified
- [ ] All docs changes are committed with version tag

### Must Have
- Explicit threshold numbers for every Voyage invocation (not "when ambiguous")
- Fallback behavior documented for each Voyage-dependent component
- Latency budgets documented for each pipeline stage (fast path vs slow path)
- Model selection rationale with "why this model for this use case"
- ChromaDB schema description (collections, metadata fields, TTL policy)
- Architecture principle reaffirmed: Voyage computes, agent decides
- All docs maintain existing formatting conventions (tables, code blocks, ASCII diagrams)

### Must NOT Have (Guardrails)
- **No code changes** — this is docs-only
- **No version bumps** — documentation updates don't change VERSION file
- **No strategy logic in docs** — Voyage computes similarity and relevance; docs must not prescribe what the agent does with those scores
- **No replacing existing specs** — enhance what's there, don't delete the VADER/TextBlob/keyword documentation
- **No AI slop in docs** — no obvious comments, no filler paragraphs, no restating the obvious
- **No changing the risk module description** — risk module is immutable, even in docs
- **Scope creep prevention**: Heartbeat clustering scoped to "decision outcome sequences grouped by market semantic similarity". Decision log search scoped to "last 90 days, max 1000". Chart embedding triggered by "agent request OR image_url field" only.

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: N/A (docs-only, no code tests)
- **Automated tests**: None (docs-only)
- **Framework**: N/A
- **Agent-Executed QA**: ALWAYS (mandatory for all tasks)

### QA Policy
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Docs**: Use Bash (`grep`, `wc -l`) — verify key terms present, verify file structure
- **Cross-references**: Use Bash (`grep`) — verify docs reference each other correctly
- **ADR**: Use Bash — verify ADR follows project's decision record format

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — ADR first, then parallel doc updates):
├── Task 1: Write ADR for Voyage AI adoption [COMPLETED]
├── Task 2: Update docs/news-sentiment.md [writing]
├── Task 3: Update docs/architecture.md [writing]
└── Task 4: Update docs/research.md [writing]

Wave 2 (Dependent docs — after Wave 1 establishes shared vocabulary):
├── Task 5: Update docs/self-learning.md [writing]
├── Task 6: Update docs/product-roadmap.md [deep]

Wave FINAL (After ALL tasks — verification):
├── Task F1: Cross-reference consistency audit (oracle)
├── Task F2: Content quality review (unspecified-high)
├── Task F3: Scope fidelity check (deep)
└── Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| T1   | None      | T2, T5, T6 |
| T2   | T1        | F1-F3 |
| T3   | T1        | T5, F1-F3 |
| T4   | None      | T2, F1-F3 |
| T5   | T1, T3    | F1-F3 |
| T6   | T1, T2, T3| F1-F3 |
| F1-F3| All tasks | — |

---

## TODOs

- [x] 1. Write ADR: Voyage AI Model Selection & Integration Approach

  **Status**: COMPLETED — `docs/decisions/voyage-ai-adoption.md` created (128 lines)

  **What was done**:
  - Created ADR with Context, Decision, Alternatives Considered, Consequences sections
  - Documented 4 model selections with rationale
  - Documented ChromaDB decision over sqlite-vss
  - Documented slow-path constraint, agent-decides principle, batch API strategy

- [x] 2. Update docs/news-sentiment.md with Voyage AI integration

  **What to do**:
  - Add a new section "Semantic Enhancement Layer (Voyage AI)" after the existing pipeline architecture
  - Update the Pipeline Architecture diagram to show Voyage enhancement layers alongside VADER/TextBlob
  - Update the Classifier section: add Voyage semantic classification as primary path for financial text, keyword matching as fallback, reranker for 0.5–0.7 confidence range
  - Update the Sentiment Scorer section: add Voyage uplift path for VADER compound between -0.3 and +0.3
  - Update the Impact Assessor section: add Voyage semantic relevance (embed news + market resolution condition → cosine similarity) as the "direct relevance" criterion
  - Add explicit threshold table: every Voyage invocation has a defined trigger condition, fallback, and timeout
  - Add latency budget table: fast path (<10ms VADER) vs slow path (~200-500ms Voyage API call)
  - Add ChromaDB section: collection schema (news_embeddings, market_conditions), metadata fields (ticker, category, date), TTL policy
  - Add fallback/degraded mode section: what happens when VOYAGE_API_KEY is unset or API is down
  - Add model selection table: `voyage-finance-2` for news/market text, `rerank-2.5` for ambiguous classification
  - Update the Future Enhancements section to remove "Transformer-based classification" (now planned as Voyage)

  **Must NOT do**:
  - Don't delete the existing VADER/TextBlob/source documentation
  - Don't remove the keyword-based classifier description
  - Don't prescribe when the agent should trade based on sentiment scores

  **Acceptance Criteria**:
  - [ ] Voyage AI section exists in `docs/news-sentiment.md`
  - [ ] Pipeline architecture diagram updated to show Voyage layer
  - [ ] Classifier section mentions `voyage-finance-2` and `rerank-2.5`
  - [ ] Sentiment scorer section mentions Voyage uplift with -0.3/+0.3 threshold
  - [ ] Impact assessor section mentions semantic relevance via embeddings
  - [ ] Explicit threshold table exists with trigger conditions
  - [ ] Latency budget table exists (fast path vs slow path)
  - [ ] ChromaDB collection schema documented
  - [ ] Fallback/degraded mode section exists
  - [ ] VADER/TextBlob/keyword documentation still intact

- [x] 3. Update docs/architecture.md with ChromaDB and embedding components

  **What to do**:
  - Update the Component Map diagram: add `embeddings` and `vectors` under `news` box, add `vectors` under `db` box
  - Update `news/` module description to include `embeddings` (Voyage AI client)
  - Update `db/` module description to include `vectors` (ChromaDB interface)
  - Add new data flow section "Embedding Flow" showing: news item → Voyage embed → ChromaDB store → similarity search → relevance score
  - Update the Module Dependencies section: `news/` depends on `kalshi/models` (existing) + `voyageai` (new) + `chromadb` (new); `db/` depends on `kalshi/models` (existing) + `chromadb` (new)
  - Update the Toolkit vs. Agent Boundary table: add row for "Embedding computation & similarity scoring" → Toolkit Owns; add row for "Which similar decisions to review" → Agent Owns
  - Add constraint note: embedding API calls are on the slow path only; fast-path operations never block on Voyage API calls

  **Must NOT do**:
  - Don't modify the risk module description
  - Don't change existing data flow descriptions (Trade Execution, Analysis, Heartbeat)
  - Don't add code snippets

  **Acceptance Criteria**:
  - [ ] Component map includes `embeddings` under `news` and `vectors` under `db`
  - [ ] New "Embedding Flow" data flow section exists
  - [ ] Module Dependencies updated with `voyageai` and `chromadb`
  - [ ] Toolkit vs Agent Boundary has embedding row
  - [ ] Slow-path constraint noted for embedding calls
  - [ ] Risk module description unchanged

- [x] 4. Update docs/research.md with Voyage AI findings

  **What to do**:
  - Add new section "## Voyage AI" under the existing research document
  - Document Voyage AI's capabilities: embedding models, rerankers, multimodal embeddings
  - Add comparison table: Voyage AI vs OpenAI embeddings vs Cohere vs local sentence-transformers
  - Document model selection rationale: why `voyage-finance-2` for financial text, why `voyage-4-large` for general
  - Document ChromaDB evaluation: why chosen over sqlite-vss, Pinecone, Weaviate, Milvus
  - Add to "Reuse Directly" table: `voyageai` Python SDK for embedding/reranking, `chromadb` for vector storage
  - Update "Explicitly NOT Building" table: remove "Transformer-based sentiment (for now)" since Voyage is now planned; clarify that we're not building local transformer models (Voyage is API-based)
  - Add key insight: Voyage's finance-specific embeddings understand financial jargon that generic models miss (FOMC, quantitative easing, CPI, etc.)
  - Document Voyage Batch API: 33% discount for deferred operations, 12h completion window

  **Must NOT do**:
  - Don't remove existing research content
  - Don't add code implementation details (this is research, not spec)

  **Acceptance Criteria**:
  - [ ] Voyage AI section exists in `docs/research.md`
  - [ ] Comparison table exists (Voyage vs at least 2 alternatives)
  - [ ] ChromaDB evaluation documented
  - [ ] `voyageai` added to "Reuse Directly" table
  - [ ] `chromadb` added to "Reuse Directly" table
  - [ ] "Transformer-based sentiment" in "NOT Building" updated or removed
  - [ ] Existing research content preserved

- [x] 5. Update docs/self-learning.md with semantic enhancements

  **What to do**:
  - Add new section "## Semantic Decision Search" after the Learning Logs section
  - Describe: embed each decision's market context using `voyage-4-large`, store in ChromaDB, query with natural language ("what happened last time the Fed raised rates?") instead of SQL filters
  - Specify scope: last 90 days, max 1000 results, embed on write (not on read)
  - Specify the linkage: ChromaDB stores embedding + decision_id (FK to SQLite); SQLite is authoritative; ChromaDB is search index
  - Add new section "## Heartbeat Pattern Clustering" after the Semantic Decision Search section
  - Describe: during heartbeat cycle, group closed-market decisions by semantic similarity of market conditions using `voyage-4-large` embeddings
  - Specify: clustering input = decision outcome sequences grouped by market semantic similarity; clustering output = grouping labels + similarity scores; logging only — agent reviews, no automatic action
  - Specify: cluster analysis runs every 6 hours during heartbeat, not on every decision
  - Handle empty clusters gracefully: log "no significant clusters found" and exit
  - Specify that `voyage-4-large` is used for these (general-purpose, not finance-specific) because decision context spans multiple categories
  - Add ChromaDB collection schema: `decision_embeddings` collection with metadata (decision_id, ticker, category, timestamp, outcome); `cluster_results` collection with metadata (cluster_id, decisions_count, pattern_key)

  **Must NOT do**:
  - Don't modify the existing Bayesian adaptation section
  - Don't remove the WAL protocol description
  - Don't prescribe that the agent should automatically change strategy based on clusters (agent reviews, decides)

  **Acceptance Criteria**:
  - [ ] "Semantic Decision Search" section exists
  - [ ] "Heartbeat Pattern Clustering" section exists
  - [ ] Both sections specify `voyage-4-large` model
  - [ ] Decision search scope (90 days, 1000 max) documented
  - [ ] SQLite-as-authoritative, ChromaDB-as-index specified
  - [ ] Clustering: input, output, and "agent reviews" constraint documented
  - [ ] Empty cluster handling documented
  - [ ] Bayesian adaptation section unchanged

- [x] 6. Update docs/product-roadmap.md with Voyage AI components

  **What to do**:
  - Update Phase 6 component table: add `db/vectors.py` (ChromaDB interface), `db/learnings.py` enhanced with semantic search and clustering
  - Update Phase 6 success criteria: add "Decision log supports semantic search via natural language queries" and "Heartbeat clusters semantically similar decision patterns"
  - Update Phase 7 component table: add `news/embeddings.py` (Voyage API client), update classifier/sentiment/impact descriptions to mention Voyage enhancement
  - Add new sub-rows to Phase 7 component table: "Embedding client", "ChromaDB integration", "Semantic classification", "Reranker fallback"
  - Update Phase 7 success criteria: update "News classified to correct Kalshi category >80%" → ">90% (with Voyage semantic classification)"; add "Voyage-enhanced classification degrades gracefully when API unavailable"
  - Update the Advanced Capabilities table: replace "Transformer sentiment" row with "Voyage AI semantic pipeline" (now in-scope for Phase 7, not Post-7); add "Market chart analysis" using `voyage-multimodal-3.5` (Phase 7); add "Decision log semantic search" (Phase 6)
  - Add a note to Phase 7: "Voyage AI integration requires `VOYAGE_API_KEY` environment variable. Pipeline degrades to VADER/TextBlob/keyword-only mode without it."

  **Must NOT do**:
  - Don't change phase dependencies (Phase 7 still depends on Phase 1)
  - Don't change the version targets
  - Don't change the Implementation Principles section
  - Don't add new phases — Voyage enhances existing phases

  **Acceptance Criteria**:
  - [ ] Phase 6 component table includes `db/vectors.py` and enhanced `db/learnings.py`
  - [ ] Phase 6 success criteria include semantic search and clustering
  - [ ] Phase 7 component table includes `news/embeddings.py` and Voyage sub-components
  - [ ] Phase 7 success criteria updated with Voyage-enhanced targets (>90% classification)
  - [ ] Advanced Capabilities table updated (Transformer sentiment → Voyage AI semantic pipeline)
  - [ ] Phase dependencies and version targets unchanged
  - [ ] Implementation Principles unchanged

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 3 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Cross-Reference Consistency Audit** — `oracle`
  Read all 6 modified/created docs files. Verify: (1) model names are consistent across all docs (`voyage-4-large`, `voyage-finance-2`, `rerank-2.5`, `voyage-multimodal-3.5` — same names everywhere), (2) ChromaDB described consistently (same schema, same role as search index), (3) thresholds are consistent (0.5-0.7 reranker, -0.3/+0.3 sentiment uplift, 90 days / 1000 max decision search), (4) fallback behavior described in every component that depends on Voyage, (5) ADR cross-references exist from each doc that uses Voyage.
  Output: `Model Names [CONSISTENT/INCONSISTENT at N locations] | ChromaDB [CONSISTENT/INCONSISTENT] | Thresholds [CONSISTENT/INCONSISTENT at N locations] | Fallbacks [N/N components covered] | VERDICT: APPROVE/REJECT`

- [x] F2. **Content Quality Review** — `unspecified-high`
  Review all 6 files for: AI slop (obvious comments, filler paragraphs, restating the obvious), missing sections (any acceptance criteria item not represented), formatting consistency (tables, code blocks, headers match existing docs style), factual accuracy (Voyage model specs match official docs). Check that no code files were modified (`git diff --name-only` should only show .md files).
  Output: `AI Slop [N issues] | Missing Content [N items] | Formatting [CONSISTENT/INCONSISTENT] | Facts [ACCURATE/INACCURATE at N locations] | Code Changes [NONE/N files] | VERDICT`

- [x] F3. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was added, nothing beyond spec was added. Check "Must NOT do" compliance: no code changes, no risk module changes, no strategy prescriptions, no deleted existing docs content. Verify docs-only constraint: `git diff --name-only` returns only .md files.
  Output: `Tasks [N/N compliant] | Code Violations [NONE/N files] | Deleted Content [NONE/N sections] | Strategy Prescriptions [NONE/N found] | VERDICT`

---

## Commit Strategy

| Commit | Message | Files | Pre-commit |
|--------|---------|-------|------------|
| 1 | `docs: add ADR for Voyage AI model selection and integration approach` | `docs/decisions/voyage-ai-adoption.md` | — |
| 2 | `docs: add Voyage AI integration to news-sentiment pipeline documentation` | `docs/news-sentiment.md`, `docs/architecture.md`, `docs/research.md` | — |
| 3 | `docs: add Voyage AI semantic enhancements to self-learning and roadmap` | `docs/self-learning.md`, `docs/product-roadmap.md` | — |

---

## Success Criteria

### Verification Commands
```bash
# All docs files exist
test -f docs/decisions/voyage-ai-adoption.md && echo "ADR EXISTS" || echo "MISSING"
# Voyage model names consistent across all docs
grep -r "voyage-4-large\|voyage-finance-2\|rerank-2.5\|voyage-multimodal-3.5" docs/ | wc -l  # Expected: >= 10 total references
# No code files modified
git diff --name-only | grep -v "\.md$" | wc -l  # Expected: 0 non-.md files
# ChromaDB mentioned across docs
grep -rl "ChromaDB" docs/ | wc -l  # Expected: >= 3 docs files
# Fallback/degraded mode mentioned
grep -rl "degrad\|fallback" docs/news-sentiment.md docs/product-roadmap.md | wc -l  # Expected: >= 2
```

### Final Checklist
- [ ] All 6 docs files created/updated
- [ ] No code files modified
- [ ] Model names consistent across all docs
- [ ] Thresholds consistent across all docs
- [ ] ChromaDB described consistently as search index (not authoritative store)
- [ ] Fallback behavior documented for every Voyage-dependent component
- [ ] Existing docs content preserved (VADER, TextBlob, keywords, Bayesian, WAL, etc.)
- [ ] Version targets unchanged
- [ ] Risk module description untouched