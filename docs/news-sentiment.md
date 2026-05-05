# News & Sentiment Pipeline

How TraderBot ingests real-world events and converts them into actionable market signals.

## Why This Matters

Prediction markets are **event-driven**. Prices move when news breaks — not from technical patterns or momentum. A Fed rate decision, a Supreme Court ruling, or a celebrity announcement can shift a market's probability by 20+ points in seconds.

The toolkit doesn't interpret news (that's the agent's job). It **collects, classifies, and scores** news so the agent can reason about it efficiently.

## Pipeline Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  NewsAPI    │  │  X/Twitter  │  │  Reddit RSS │  ← Sources
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────────────────────────────────────────┐
│              sources.py (unified interface)       │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│  classifier.py — Map news to Kalshi market categories │
│  ┌─────────────────┐    ┌─────────────────────┐   │
│  │ Keyword matching │───▶│ Voyage semantic (opt-in)│  ← [NEW]
│  └─────────────────┘    └─────────────────────┘   │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│  sentiment_scorer.py — VADER + TextBlob scoring   │
│  ┌─────────┐    ┌─────────────┐                    │
│  │  VADER  │───▶│ Voyage uplift │  ← [NEW]        │
│  └─────────┘    └─────────────┘                    │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│  impact_assessor.py — Does this news matter?      │
│  ┌──────────────────┐    ┌────────────────────┐   │
│  │ Heuristic rules  │───▶│ Voyage relevance    │  ← [NEW]
│  └──────────────────┘    └────────────────────┘   │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
              Agent receives structured news item
              (with category, sentiment, impact score)
```

## Semantic Enhancement Layer (Voyage AI)
> Model selection rationale and constraints: [ADR-001](decisions/voyage-ai-adoption.md)

`news/voyage_client.py` — domain-optimized semantic analysis for financial text.

### Why Semantic Enhancement?

Keyword matching catches obvious signals ("Fed raises rates") but misses subtle ones ("officials signal caution on inflation"). Voyage AI provides the semantic layer to catch nuance that keywords miss.

### Models

| Model | Use Case | Latency |
|---|---|---|
| `voyage-finance-2` | News articles, market descriptions, financial text | ~200-500ms |
| `rerank-2.5` | Ambiguous classification (0.5–0.7 confidence range) | ~100-300ms |

### Invocation Triggers

| Component | Trigger Condition | Fallback | Timeout |
|---|---|---|---|
| Classifier | Keyword confidence <0.7 | Return to agent for LLM interpretation | 500ms |
| Sentiment Scorer | VADER compound between -0.3 and +0.3 | Use VADER score as-is | 300ms |
| Impact Assessor | Direct relevance unclear from heuristics | Skip Voyage, use heuristic score | 300ms |

### Fallback / Degraded Mode

When `VOYAGE_API_KEY` is unset or the API is unreachable:

1. **Classifier**: Falls back to keyword matching; low-confidence items go to agent LLM
2. **Sentiment Scorer**: Returns VADER/TextBlob score without uplift
3. **Impact Assessor**: Uses heuristic rules only, no semantic relevance check

The pipeline continues with degraded capability rather than failing. All degraded-mode decisions are logged with `"voyage_status": "unavailable"` for later review.

## Sources

`news/sources.py` — unified interface for multiple data providers.

### NewsAPI

| Detail | Value |
|---|---|
| **Coverage** | 50,000+ sources worldwide |
| **Update frequency** | Near real-time (minutes) |
| **Rate limit** | 100/day (free), 1000/day (developer) |
| **Strength** | Broad coverage, structured data, good for political/economic news |
| **Weakness** | Paid tier needed for high-frequency queries; no social media |

Use for: Political events, economic indicators, general news that maps to Kalshi categories like economics, politics, weather.

### X/Twitter API

| Detail | Value |
|---|---|
| **Coverage** | Real-time social — often first to break news |
| **Update frequency** | Streaming (real-time) |
| **Rate limit** | Varies by tier (basic: 10,000 tweets/month read) |
| **Strength** | Speed — news breaks here first; sentiment from replies/likes |
| **Weakness** | Noisy, requires filtering; API access increasingly restricted |

Use for: Breaking news detection, real-time sentiment shifts, journalist/pundit reactions that signal market movement.

### Reddit RSS

| Detail | Value |
|---|---|
| **Coverage** | Discussion-oriented; slower but deeper analysis |
| **Update frequency** | Polling every 5-15 minutes |
| **Rate limit** | 60 requests/minute (RSS), 100/min (API) |
| **Strength** | Community analysis, early indicators of narrative shifts |
| **Weakness** | Slow, not a breaking news source; requires subreddit curation |

Use for: Subreddit-specific monitoring (r/politics, r/economics, r/weather) for narrative shifts and community consensus signals.

### Source Priority for Speed

For latency-sensitive prediction market trading:

1. **X/Twitter** — fastest to break news, but noisiest
2. **NewsAPI** — structured, reliable, minutes behind Twitter
3. **Reddit** — slowest but provides depth and community consensus

## Classifier

`news/classifier.py` — maps raw news items to Kalshi market categories.

### MarketCategory Enum

The `MarketCategory` enum defines the supported news classification categories, mapping directly to Kalshi's market categories:

```python
class MarketCategory(str, Enum):
    ECONOMICS = "economics"
    POLITICS = "politics"
    WEATHER = "weather"
    SPORTS = "sports"
    CULTURE = "culture"
    TECHNOLOGY = "technology"
    SCIENCE = "science"
```

Each category has:
- Associated keyword lists for initial classification
- Category-specific risk parameters (e.g., sports markets have tighter spread thresholds)
- Priority mapping for the impact assessor

### CategoryAnalyzer Protocol

Each category has a specialized analyzer implementing the `CategoryAnalyzer` Protocol:

```python
class CategoryAnalyzer(Protocol):
    def analyze(self, text: str, source: SourceType) -> CategorySignals:
        """Analyze text for category-specific signals."""
        ...
```

`CategorySignals` model:

```python
class CategorySignals(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    confidence: float              # 0-1 confidence in classification
    subcategories: list[str]        # E.g., ["monetary_policy", "fed"] for ECONOMICS
    relevant_tickers: list[str]    # Kalshi tickers this may affect
    authority_score: float          # 0-1 domain authority of the source
    evidence_quality: float        # 0-1 quality of evidence for this category
```

### AnalysisRegistry

The `AnalysisRegistry` provides a central dispatch for category-specific analysis:

```python
class AnalysisRegistry:
    def register(self, category: MarketCategory, analyzer: CategoryAnalyzer) -> None:
        """Register an analyzer for a category."""
        ...

    def get(self, category: MarketCategory) -> CategoryAnalyzer | None:
        """Get the analyzer for a category. Returns None if unregistered."""
        ...

    def analyze(self, text: str, source: SourceType) -> CategorySignals:
        """Classify text, then dispatch to the appropriate category analyzer."""
        ...
```

The registry pattern allows:
- Adding new categories without modifying existing code
- Per-category analyzers with specialized logic
- Clean fallback: if no analyzer is registered for a category, keyword matching is used

### Kalshi Market Categories

Kalshi organizes markets into broad categories:

| Category | Example Markets |
|---|---|
| **Economics** | Fed rate decisions, GDP, unemployment, inflation |
| **Politics** | Elections, legislation, Supreme Court, appointments |
| **Weather** | Hurricane season, temperature records, snowfall |
| **Culture** | Box office, awards, sports championships |
| **Technology** | Crypto prices, tech earnings, product launches |
| **Science** | Space launches, disease outbreaks |

### Classification Approach

The classifier uses lightweight keyword matching + category heuristics as a first pass, then Voyage semantic classification for financial text, then the agent (LLM) handles remaining ambiguous cases:

1. **Keyword filter**: Pre-built keyword lists per category ("Fed", "interest rate", "FOMC" → Economics)
2. **Entity extraction**: Named entities (people, places, organizations) mapped to categories
3. **Voyage semantic classification**: For financial text, embed with `voyage-finance-2` → classify. If confidence 0.5–0.7, use `rerank-2.5` to refine
4. **Fallback to LLM**: If confidence <0.5 after reranking, defer to the agent for interpretation

This hybrid approach minimizes API calls while ensuring the agent sees relevant news. Voyage is the primary path for financial text; keyword matching catches obvious non-financial signals.

### Voyage Semantic Classification (Financial Text)

For text identified as potentially financial (via initial keyword filter), the pipeline:

1. Embeds the text with `voyage-finance-2` (optimized for financial domain)
2. Compares against known category embeddings in ChromaDB
3. Returns classification with confidence score

| Confidence Range | Action |
|---|---|
| >0.7 | Accept classification |
| 0.5–0.7 | Apply `rerank-2.5` to refine |
| <0.5 | Fall back to agent LLM |

The reranker is invoked only when classification confidence falls in the ambiguous range. This keeps rerank-2.5 usage targeted and avoids latency on clear-cut cases.

## Sentiment Scorer

`news/sentiment_scorer.py` — lightweight, fast sentiment analysis.

### Why Lightweight?

Prediction market opportunities have short windows. News breaks → market moves → edge disappears, often in seconds. We can't wait for a transformer model to process; we need sub-second scoring.

### VADER (Primary)

| Attribute | Value |
|---|---|
| **Speed** | <1ms per text |
| **Accuracy** | Good for social media (designed for it) |
| **Self-hosted** | Yes — pure Python, no API calls |
| **Output** | Compound score (-1 to +1), positive/negative/neutral breakdown |

VADER is the default scorer. It's fast, free, and designed for the kind of short, informal text found in tweets and headlines.

### TextBlob (Fallback)

| Attribute | Value |
|---|---|
| **Speed** | ~5ms per text |
| **Accuracy** | Better for formal/longer text (articles) |
| **Self-hosted** | Yes |
| **Output** | Polarity (-1 to +1) + subjectivity (0 to 1) |

TextBlob complements VADER by handling longer-form content like full articles where VADER's heuristic approach is less reliable.

### Scoring Pipeline

```python
def score(text: str, source: SourceType) -> SentimentResult:
    if source in (SourceType.TWITTER, SourceType.REDDIT):
        vader = vader_score(text)        # Fast, social-optimized
    else:
        vader = textblob_score(text)      # Better for articles

    # Voyage uplift: refine neutral-range VADER scores
    if -0.3 <= vader.compound <= 0.3:
        voyage = voyage_uplift(text, vader)   # Semantic refinement
        return SentimentResult(
            compound=voyage.refined_score,
            category=vader.category,
            confidence=voyage.confidence,
            relevant_tickers=vader.relevant_tickers
        )

    return SentimentResult(
        compound=vader.compound,
        category=vader.category,
        confidence=vader.confidence,
        relevant_tickers=vader.relevant_tickers
    )
```

### Voyage Uplift

When VADER returns a compound score in the neutral range (-0.3 to +0.3), the text may carry sentiment that VADER misses. The uplift path:

1. Embeds the text with `voyage-finance-2`
2. Compares against known sentiment-anchor embeddings
3. Returns a refined compound score that accounts for semantic nuance

This catches cases like "officials signal caution" which VADER reads as neutral but carries directional signal.

### Output Format

```python
class SentimentResult(BaseModel):
    compound: float              # -1 (very negative) to +1 (very positive)
    category: str                # Kalshi market category
    confidence: float            # How confident in the classification
    relevant_tickers: list[str] # Kalshi tickers this might affect
```

## Impact Assessor

`news/impact_assessor.py` — the critical filter that prevents noise from becoming signal.

### The Problem

Most news is irrelevant to any given prediction market. A celebrity divorce doesn't affect Fed rate probabilities. Without filtering, the agent gets overwhelmed with noise.

### Domain Authority Scoring

Each news source has a domain authority score per category. Higher authority means the source is more reliable for that category:

| Source | ECONOMICS | POLITICS | WEATHER | SPORTS | CULTURE | TECHNOLOGY | SCIENCE |
|---|---|---|---|---|---|---|---|
| **Federal Reserve** | 1.0 | 0.7 | 0.1 | 0.0 | 0.0 | 0.3 | 0.1 |
| **Reuters/Bloomberg** | 0.9 | 0.8 | 0.3 | 0.2 | 0.3 | 0.7 | 0.5 |
| **NWS/NOAA** | 0.1 | 0.0 | 1.0 | 0.1 | 0.0 | 0.1 | 0.7 |
| **ESPN** | 0.0 | 0.1 | 0.0 | 1.0 | 0.3 | 0.1 | 0.0 |
| **arXiv/Nature** | 0.3 | 0.1 | 0.2 | 0.0 | 0.1 | 0.6 | 1.0 |
| **General News (NewsAPI)** | 0.5 | 0.5 | 0.3 | 0.3 | 0.4 | 0.4 | 0.3 |
| **Twitter/X** | 0.3 | 0.6 | 0.2 | 0.5 | 0.5 | 0.4 | 0.1 |
| **Reddit** | 0.2 | 0.3 | 0.2 | 0.4 | 0.5 | 0.3 | 0.1 |

Domain authority is used as a multiplier in the impact score formula. A Fed statement scored at 0.8 impact with 1.0 economics authority gets 0.8 × 1.0 = 0.8 net impact. A random tweet scored at 0.8 impact with 0.3 economics authority gets 0.8 × 0.3 = 0.24 net impact.

### Evidence Quality Thresholds Per Category

Categories require different evidence quality levels to produce actionable signals:

| Category | Minimum Evidence Quality | Minimum Authority Score | Rationale |
|---|---|---|---|
| **ECONOMICS** | 0.7 | 0.5 | Economic decisions need strong evidence |
| **POLITICS** | 0.6 | 0.5 | Political news is noisy; requires corroboration |
| **WEATHER** | 0.5 | 0.3 | NWS forecasts are inherently reliable |
| **SPORTS** | 0.55 | 0.3 | Wide variance in sports predictions |
| **CULTURE** | 0.5 | 0.3 | Entertainment outcomes are hard to predict |
| **TECHNOLOGY** | 0.7 | 0.4 | Tech markets require strong signal-to-noise ratio |
| **SCIENCE** | 0.7 | 0.5 | Requires authoritative sources (peer-reviewed, institutional) |

Items below the threshold are still logged (for completeness) but their impact scores are reduced proportionally.

### Impact Assessment Criteria

| Criterion | Question | Weight |
|---|---|---|
| **Direct relevance** | Does this news directly relate to a market's resolution condition? | High |
| **Source authority** | Is this from an official source (Fed, CBO, NWS) or speculation? | High |
| **Recency** | How fresh is this news? (Breaking vs. hours old) | Medium |
| **Market sensitivity** | How much did similar news move this market historically? | Medium |
| **Volume** | Are multiple sources reporting the same thing? (Corroboration) | Low |

**Direct relevance via Voyage semantic similarity**: When heuristic rules cannot determine direct relevance, the assessor embeds the news text and the market's resolution condition text, then computes cosine similarity. A similarity above threshold (configurable, default 0.65) marks the item as directly relevant.

### Impact Score

The assessor outputs a single impact score (0-1):

- **>0.7**: High impact — emit `systemEvent` to alert the human
- **0.3-0.7**: Moderate — update internal market outlook, no alert
- **<0.3**: Low — log for completeness, no action

### Corroboration Boost

When multiple independent sources report the same event, confidence increases. If NewsAPI AND Twitter both report the same Fed statement, the impact score gets a 1.3× multiplier (capped at 1.0).

## Latency Considerations

### Fast Path (<10ms)

| Operation | Target Latency | Actual (estimated) |
|---|---|---|
| Source polling | 30-60 seconds | Depends on API rate limits |
| Classification (keyword) | <50ms | Local keyword matching |
| Sentiment scoring | <10ms | VADER (local, pure Python) |
| Impact assessment (heuristic) | <100ms | Local computation |
| Total end-to-end (fast path) | <2 seconds | From news break to signal update |

### Slow Path (~200-500ms)

When Voyage AI is invoked:

| Operation | Latency | Trigger |
|---|---|---|
| Voyage embedding | ~200-500ms | Configured per model |
| Rerank-2.5 | ~100-300ms | Confidence 0.5–0.7 |

Slow path is non-blocking: the fast path returns immediately with degraded confidence, and Voyage results update the assessment asynchronously when available.

### ChromaDB Vector Store

`news/chroma_store.py` — persistent vector store for semantic search.

#### Collections

| Collection | Purpose | Schema |
|---|---|---|
| `news_embeddings` | News articles and their embeddings | `id`, `embedding`, `text`, `source`, `ticker`, `category`, `date` |
| `market_conditions` | Market resolution conditions | `id`, `embedding`, `market_id`, `condition_text`, `expiry` |

#### Metadata Fields

| Field | Type | Indexed | Notes |
|---|---|---|---|
| `ticker` | string | Yes | Kalshi ticker (e.g., "KXBTCD-26MAR31") |
| `category` | string | Yes | Market category (e.g., "economics", "politics") |
| `date` | datetime | Yes | Publish date; used for TTL filtering |

#### TTL Policy

Vectors expire after 7 days by default. Configurable per collection via `TTL_DAYS` environment variable. Expired vectors are purged on startup.

The biggest bottleneck is source polling latency. NewsAPI and Reddit are polled, not streamed. Twitter offers streaming, but requires a more expensive API tier and careful filtering to avoid drowning in noise.

## Future Enhancements

- **WebSocket news feeds**: Some news APIs offer WebSocket streams for sub-second updates
- **Historical news correlation**: "What happened to market X the last time news type Y broke?"
- **Custom source integrations**: CFTC reports, Fed FOMC minutes, NOAA alerts
- **Voyage model upgrades**: As Voyage releases newer models (e.g., `voyage-4-large`), evaluate for potential accuracy gains