# ADR-001: Voyage AI Model Selection and Integration Approach

**Date**: 2026-04-21
**Status**: Accepted
**Deciders**: TraderBot team

---

## Context

As part of Phase 7, TraderBot requires AI-powered semantic analysis capabilities for the news/sentiment pipeline, decision logging, heartbeat pattern clustering, and market chart analysis. Current implementation uses VADER/TextBlob for fast-path sentiment and keyword-based classification, which lacks domain-specific financial understanding and semantic relevance scoring.

We need to select embedding, reranking, and multimodal models that provide best-in-class financial text understanding while respecting latency constraints (fast path <10ms, slow path can tolerate 200-500ms) and cost constraints (single-user bot, generous free tiers available).

---

## Decision

We adopt **Voyage AI** as the sole AI model provider for semantic analysis, using four models across three use-case categories:

### Model Selection

| Use Case | Model | Rationale |
|----------|-------|-----------|
| News classification, sentiment scoring, market relevance | `voyage-finance-2` | Domain-optimized for financial text; understands FOMC, quantitative easing, CPI, federal funds rate jargon that generic models miss |
| Decision log search, heartbeat pattern clustering | `voyage-4-large` | Best general-purpose quality for non-financial text with variable context; supports configurable dimensions (256/512/1024/2048) |
| Ambiguous classification fallback | `rerank-2.5` | Highest-quality reranker with instruction-following and multilingual support; invoked when classifier confidence is 0.5–0.7 |
| Market chart / image analysis | `voyage-multimodal-3.5` | Text+image embeddings for processing chart screenshots when `image_url` field is present or agent requests visual analysis |

### Vector Store: ChromaDB

**ChromaDB** is adopted as the vector storage layer (not sqlite-vss):

- Purpose-built vector DB with native metadata filtering — essential for filtering embeddings by ticker, category, date range
- Python-native async support — aligns with existing async/await patterns in TraderBot
- Persistent collections with TTL policy support — enables bounded storage growth
- Tradeoff vs sqlite-vss: adds a new dependency but provides significantly richer feature set; sqlite-vss is extension-based, less mature, and lacks native metadata filtering
- Architecture constraint: **SQLite remains the authoritative write store** for all trading data; ChromaDB is a **search-optimized index only**

### Integration Approach

Enhance Phase 7 **directly** with Voyage AI as a core component rather than building a keyword-first pipeline and upgrading later:

- Rationale: Higher quality from day one; avoids rewriting the classification/sentiment pipeline twice
- Tradeoff: Larger initial Phase 7 scope but eliminates a future migration
- Constraint: Every Voyage invocation must have an explicit trigger condition, timeout, and fallback behavior

### Slow-Path Constraint

Voyage API calls are ~200-500ms and must **never block the hot path**:

- Sentiment scoring must return within 100ms total → VADER/TextBlob fast path (<10ms) always executes first; Voyage is invoked **only** on the slow path for ambiguous cases
- Classification: keyword matching executes first; Voyage semantic classification is the slow path
- **No Voyage calls on the hot path** — this is a hard architectural constraint

### Agent-Decides Principle

Voyage computes **similarity scores and relevance metrics**. The **agent decides** strategy:

- Voyage produces: embedding vectors, cosine similarities, reranked relevance scores
- Agent consumes: scores and decides action (buy/sell/hold/ignore)
- **No strategy logic in the toolkit** — toolkit is a "dumb pipe with smart guards"

### Batch API Strategy

Voyage Batch API (33% discount, 12-hour completion window) is used **only for deferred operations**:

- ✅ Safe for batch: heartbeat clustering runs every 6 hours, initial ChromaDB population, re-embedding on model upgrade, pre-computing market condition embeddings for known events
- ❌ NOT for real-time: news classification, sentiment scoring, impact assessment, decision log search queries — all require sub-second response for prediction market timing

---

## Alternatives Considered

### OpenAI `text-embedding-3-large`
- Good general quality but not domain-optimized for finance
- Higher latency (~75ms vs Voyage ~150ms for finance text)
- No instruction-following reranker in the same family
- **Rejected**: Weaker on financial jargon without domain fine-tuning

### Cohere `embed-v3`
- Good multilingual support but historically weaker on financial domain
- Proprietary model with less transparency on training data
- **Rejected**: Inferior financial domain performance vs voyage-finance-2

### Local `sentence-transformers` (all-MiniLM-L6-v2)
- Zero API latency, free
- Significantly worse quality on financial text (generic training corpus)
- No reranker available
- **Rejected**: Quality gap unacceptable for financial classification; no reranker support

### sqlite-vss
- Leverages existing SQLite infrastructure
- Extension-based (not a standalone DB), less mature
- No native metadata filtering
- **Rejected**: ChromaDB's feature set (async, metadata filtering, persistent collections) justifies the new dependency

---

## Consequences

### Positive
- Best-in-class financial text understanding via domain-optimized embeddings
- Consistent model family (Voyage) across all semantic tasks
- Reranker improves classification accuracy on ambiguous news items
- Multimodal support enables chart analysis without separate provider
- Generous free tiers (50M–200M tokens per model) — estimated **FREE for single-user bot for ~1 year**

### Negative
- **New dependencies**: `voyageai` SDK + `chromadb` Python packages
- **API dependency**: Requires `VOYAGE_API_KEY` environment variable; graceful degradation to VADER/TextBlob/keywords when unavailable or rate-limited
- **Latency on slow path**: 200-500ms added to deferred operations (acceptable since slow path only)
- **Cost at scale**: If user base grows significantly, per-token pricing applies (but free tiers are generous for individual use)

### Tradeoffs
- Adding ChromaDB vs leveraging existing SQLite: ChromaDB provides rich features at cost of new dependency
- Best quality models vs cost optimization: User prefers quality; free tiers are sufficient
- Batch vs real-time: 12h batch latency unsuitable for real-time but perfect for overnight analytics

---

## Implementation Notes

- All Pydantic models must use `ConfigDict(strict=True, extra="forbid")`
- All monetary values remain `int` cents (Voyage API costs are tracked separately, not as domain monetary values)
- Fast path (VADER/TextBlob) must **always** work without `VOYAGE_API_KEY`
- ChromaDB TTL policy required to prevent unbounded growth
- Rate limiting: Max 60 Voyage API calls/minute; queue overflow falls back to fast path