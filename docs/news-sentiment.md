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
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│  sentiment_scorer.py — VADER + TextBlob scoring   │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────┐
│  impact_assessor.py — Does this news matter?      │
└──────────────────────┬────────────────────────────┘
                       │
                       ▼
             Agent receives structured news item
             (with category, sentiment, impact score)
```

## Sources

`news/sources.py` — unified interface for multiple data providers.

### NewsAPI

| Detail | Value |
|---|---|
| **Coverage** | 50,000+ sources worldwide |
| **Update frequency** | Near real-time (minutes) |
| **Rate limit** | 100 requests/day (free), 1000 (developer) |
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

The classifier uses lightweight keyword matching + category heuristics as a first pass, then the agent (LLM) handles ambiguous cases:

1. **Keyword filter**: Pre-built keyword lists per category ("Fed", "interest rate", "FOMC" → Economics)
2. **Entity extraction**: Named entities (people, places, organizations) mapped to categories
3. **Fallback to agent**: If confidence < 0.7, defer to the LLM for interpretation

This hybrid approach minimizes API calls while ensuring the agent sees relevant news.

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
        return vader_score(text)        # Fast, social-optimized
    else:
        return textblob_score(text)      # Better for articles
```

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

### Impact Assessment Criteria

| Criterion | Question | Weight |
|---|---|---|
| **Direct relevance** | Does this news directly relate to a market's resolution condition? | High |
| **Source authority** | Is this from an official source (Fed, CBO, NWS) or speculation? | High |
| **Recency** | How fresh is this news? (Breaking vs. hours old) | Medium |
| **Market sensitivity** | How much did similar news move this market historically? | Medium |
| **Volume** | Are multiple sources reporting the same thing? (Corroboration) | Low |

### Impact Score

The assessor outputs a single impact score (0-1):

- **>0.7**: High impact — emit `systemEvent` to alert the human
- **0.3-0.7**: Moderate — update internal market outlook, no alert
- **<0.3**: Low — log for completeness, no action

### Corroboration Boost

When multiple independent sources report the same event, confidence increases. If NewsAPI AND Twitter both report the same Fed statement, the impact score gets a 1.3× multiplier (capped at 1.0).

## Latency Considerations

| Operation | Target Latency | Actual (estimated) |
|---|---|---|
| Source polling | 30-60 seconds | Depends on API rate limits |
| Classification | <50ms | Local keyword matching |
| Sentiment scoring | <10ms | VADER (local, pure Python) |
| Impact assessment | <100ms | Local computation |
| Total end-to-end | <2 seconds | From news break to signal update |

The biggest bottleneck is source polling latency. NewsAPI and Reddit are polled, not streamed. Twitter offers streaming, but requires a more expensive API tier and careful filtering to avoid drowning in noise.

## Future Enhancements

- **WebSocket news feeds**: Some news APIs offer WebSocket streams for sub-second updates
- **Transformer-based classification**: For higher accuracy on ambiguous items (trade speed for precision)
- **Historical news correlation**: "What happened to market X the last time news type Y broke?"
- **Custom source integrations**: CFTC reports, Fed FOMC minutes, NOAA alerts