# Research & External References

Findings from our investigation of existing prediction market tools, trading agent frameworks, and the Kalshi ecosystem. This document preserves what we learned so we don't reinvent the wheel.

## Existing Prediction Market Projects

### ryanfrigo/kalshi-ai-trading-bot

**What it does**: Full-stack Kalshi trading framework — Python client with auth, DB-backed position management, AI-driven strategy, risk checks, performance analysis.

**Key patterns we adopt**:
- Layered client/strategy/DB/analysis separation
- Database-backed position tracking (not in-memory) for restart resilience
- `is_tradeable_market()` liquidity/volume checks before entering positions
- Pandas DataFrames as universal cross-exchange data format

**Key differences from TraderBot**:
- Monolithic — not designed as an agent toolkit/skill
- No OpenClaw integration
- Risk limits are configurable (agent could override) — ours are immutable
- No self-learning or adaptation mechanism

**Repo**: https://github.com/ryanfrigo/kalshi-ai-trading-bot

### BigBodyCobain/Shadowbroker

**What it does**: Cross-exchange data aggregator (Kalshi + Polymarket) — merges market data, calculates consensus odds, classifies by category.

**Key patterns we adopt**:
- Consensus oracle pattern — comparing odds across exchanges for arbitrage signals
- Category classification for market grouping
- Cross-exchange data normalization into unified DataFrames

**Key differences**:
- Read-only — no trading execution
- No risk management
- No agent framework integration

**Repo**: https://github.com/BigBodyCobain/Shadowbroker

### Jon-Becker/prediction-market-analysis

**What it does**: Statistical analysis tools — win rate by price, Kalshi/Polymarket comparison, synthetic data generators.

**Key patterns we adopt**:
- Pandas-based performance metrics
- Statistical testing with minimum sample thresholds (avoids drawing conclusions from tiny samples)
- Synthetic data generation for testing strategies without real market data

**Key differences**:
- Analysis only — no trading, no real-time data
- No risk management
- No agent integration

**Repo**: https://github.com/Jon-Becker/prediction-market-analysis

## OpenClaw Ecosystem

### Proactive Agent (halthelobster/proactive-agent)

**Version**: 3.1.0

**What we adopt**:
- **WAL Protocol**: Write critical details to SESSION-STATE.md BEFORE responding/executing — prevents context loss
- **Working Buffer**: At 60% context, start logging every exchange for crash recovery
- **Heartbeat System**: Periodic self-improvement check-ins with structured checklist
- **Two cron architectures**: `isolated agentTurn` for autonomous background work; `systemEvent` for surfacing actionable insights
- **File-based memory**: SESSION-STATE.md, HEARTBEAT.md, MEMORY.md, USER.md, SOUL.md

**What we don't adopt**:
- Reverse prompting (asking "what would delight my human") — not appropriate for a trading bot
- SOUL.md (identity definition) — trading agents should be strategy-driven, not personality-driven
- Self-improving guardrails from ADL/VFM — our adaptation engine has different guardrail design

**Repo**: https://github.com/openclaw/skills/tree/main/skills/halthelobster/proactive-agent

### Self-Improving Agent (peterskoett/self-improving-agent)

**What we adopt**:
- `.learnings/` directory structure with LEARNINGS.md, ERRORS.md, FEATURE_REQUESTS.md
- Structured entry format with Pattern-Key and Recurrence-Count metadata
- Pattern promotion: Recurrence-Count >= 3 across 2+ tasks within 30 days → promote to AGENTS.md
- Gitignore strategy: `.learnings/` local by default to avoid committing noisy logs

**What we don't adopt**:
- GitHub Copilot/Claude Code hook integrations — we're OpenClaw-only for now
- The entire "skill extraction" workflow — our learnings are strategy-specific, not generalizable to other skills

**Repo**: https://github.com/peterskoett/self-improving-agent

### ClawHub (clawhub.ai)

OpenClaw's skill marketplace. We searched for existing finance/trading/investment skills — **none found** as of April 2026. TraderBot would be the first.

**Skill format**: SKILL.md with YAML frontmatter (name, version, description, author)
**Installation**: `openclaw skills install <slug>` or manual clone to `~/.openclaw/skills/`

## Kalshi API Research

### Authentication

- **Method**: RSA-PSS signed JWT headers
- **SDK**: `kalshi_python_async` (async) and `kalshi_python_sync` (sync)
- **Key requirement**: API key ID (public) + PEM private key (secret)
- **Important**: Always use the official SDK for auth — signing protocol is subtle and subject to change

### Historical Data

Kalshi partitions data into live and historical tiers:
- **Cutoff**: `GET /historical/cutoff` returns timestamps separating live from historical
- **Historical markets**: `GET /historical/markets` — settled markets before cutoff
- **Historical trades**: `GET /historical/trades` — trades before cutoff, paginated (1000/page)
- **No candlestick endpoint**: Must reconstruct OHLCV from trade data
- **Rate limit**: ~10 req/sec, 1000 results per page for trades

### Market Characteristics

- Binary outcomes: contracts settle at $1 (correct) or $0 (incorrect)
- Fixed expiry: every market has a defined settlement date
- No shorting: buy Yes or No contracts only
- Categories: Economics, Politics, Weather, Culture, Technology, Science

## Voyage AI Research
> Model selection rationale and constraints: [ADR-001](decisions/voyage-ai-adoption.md)

### Voyage AI Embedding Models

| Model | Dimensions | Context | Best For | Pricing |
|-------|-----------|---------|----------|---------|
| `voyage-finance-2` | 1024 | 32K tokens | Financial text (FOMC, CPI, earnings) | $0.12/M tokens |
| `voyage-4-large` | 256/512/1024/2048 (configurable) | 32K tokens | General text, decision logs, heartbeat patterns | $0.12/M tokens |
| `voyage-multimodal-3.5` | 1024 (256/512/2048 configurable) | 32K tokens | Text+image embeddings (chart screenshots) | $0.12/M tokens + $0.60/B pixels |

### Voyage AI Reranker

| Model | Context | Best For | Pricing |
|-------|---------|----------|---------|
| `rerank-2.5` | 32K tokens | Ambiguous classification fallback, instruction-following reranking | $0.05/M tokens |

### ChromaDB (Vector Store)

- Purpose-built vector DB with native metadata filtering
- Python-native async support
- Persistent collections with TTL policy
- vs sqlite-vss: ChromaDB has richer features (metadata filtering, async, TTL); sqlite-vss is extension-based, less mature
- Architecture: search-optimized index only, SQLite remains authoritative write store

### Batch API

- 33% discount on all models
- 12-hour completion window
- Safe uses: heartbeat clustering (6h cycle), initial ChromaDB population, model upgrade re-embedding
- NOT for real-time: news classification, sentiment scoring, impact assessment

### Free Tier Analysis

- Voyage-finance-2: 200M tokens free tier
- Voyage-4-large: 200M tokens free tier
- Estimated FREE for single-user bot for ~1 year

### Key Findings

1. Voyage-finance-2 significantly outperforms generic embeddings (OpenAI, Cohere, sentence-transformers) on financial domain text — understands FOMC, quantitative easing, federal funds rate jargon
2. Rerank-2.5 provides instruction-following reranking — perfect for 0.5–0.7 confidence range where classifier is uncertain
3. Configurable dimensions on voyage-4-large allow storage/cost/quality tradeoff
4. Multimodal support eliminates need for separate vision provider
5. Generous free tiers make this viable for single-user deployment

## News & Sentiment Research

### Available Sources

| Source | Speed | Cost | Best For |
|---|---|---|---|
| **NewsAPI** | Near real-time (minutes) | Free tier: 100 req/day | Political/economic headlines |
| **X/Twitter API** | Streaming (seconds) | Basic: $100/mo | Breaking news, pundit reactions |
| **Reddit RSS** | Polling (5-15 min) | Free | Community consensus, narrative shifts |

### Sentiment Tools

| Tool | Speed | Self-Hosted | Best For |
|---|---|---|---|
| **VADER** | <1ms | Yes (pure Python) | Social media short text |
| **TextBlob** | ~5ms | Yes | Longer articles, formal text |
| **spaCy + transformers** | ~100ms+ | Yes (GPU recommended) | Deep analysis, ambiguous text |
| **Voyage AI** | ~200-500ms | API (cloud) | Financial domain text, ambiguous classification |

For prediction market trading where latency matters, VADER is the practical choice for real-time scoring. Voyage AI is invoked on the slow path for ambiguous cases and domain-specific enrichment.

### Key Insight: News Moves Markets in Seconds

Prediction market prices can shift dramatically within seconds of a news event. The pipeline must be fast enough to detect, classify, and score news before the edge disappears. This is why we prioritize lightweight local scoring (VADER) over accurate but slow transformer models.

## Backtesting Research

### Why Stock Frameworks Don't Work

| Framework | Why It's Poor Fit |
|---|---|
| **backtrader** | Designed for continuous price series; binary settlement doesn't fit |
| **zipline** | Equity-focused; no concept of fixed-expiry binary contracts |
| **vectorbt** | Vectorized backtesting assumes continuous prices; doesn't handle settlement events |

All three assume the core trading unit is a stock with a continuous price curve. Prediction markets have discrete events, binary outcomes, and fixed settlement dates — fundamentally different.

**Decision**: Build a custom event-driven backtest engine optimized for binary outcome instruments.

### Self-Learning Approaches

| Approach | Pros | Cons | Our Decision |
|---|---|---|---|
| **Reinforcement learning** | Can discover novel strategies | Unstable, hard to debug, black box | ✗ Too risky for real money |
| **Bayesian updating** | Transparent, mathematically sound, stable | Conservative, slow to adapt | ✓ Adopted — conjugate priors for fast updates |
| **Evolutionary/genetic** | Can optimize multi-parameter strategies | Prone to over-fitting, computationally expensive | ✗ Over-fitting risk too high |
| **Manual parameter tuning** | Human understands the reasoning | Doesn't scale, human bias | Hybrid — human sets priors, Bayesian updates adjust |

## What We're Reusing vs. Building

### Reuse Directly

| Component | Use | Why |
|---|---|---|
| `kalshi_python_async` SDK | Kalshi API client | Official, handles auth/retry, stays current |
| pandas, numpy, scipy | Statistical analysis | Standard, fast, proven |
| VADER | Sentiment scoring | Lightweight, battle-tested for social text |
| TextBlob | Fallback sentiment | Better for formal text, also lightweight |
| OpenClaw proactive-agent patterns | WAL, heartbeat, cron | Already built, just need to apply |
| OpenClaw self-improving-agent patterns | Learning logs, pattern promotion | Already built, just need to apply |
| `voyageai` SDK | Embedding & reranking API | Official client, async support, stays current |
| `chromadb` | Vector store | Purpose-built, async, metadata filtering, TTL |

### Build Ourselves

| Component | Why |
|---|---|
| Kalshi data normalization (Pydantic models) | Our type system, our validation |
| Risk module with immutable hard limits | No existing solution has this right |
| Event-driven backtest engine for binary outcomes | Stock frameworks don't fit |
| News classification → Kalshi category mapping | No one has built this mapping |
| Bayesian adaptation engine | Needs to work with our strategy parameters |
| OpenClaw skill bridge (SKILL.md + CLI) | Novel — no existing finance skill on ClawHub |
| Embedding pipeline orchestration | Trigger conditions, fallback logic, rate limiting |
| ChromaDB collection management | TTL policy, metadata schema, index lifecycle |

### Explicitly NOT Building

| Component | Why Not |
|---|---|
| Custom HTTP client for Kalshi | Official SDK exists |
| Our own statistical libraries | scipy/statsmodels/pandas cover everything |
| Web UI | OpenClaw's Canvas handles display |
| Transformer-based sentiment (for now) | Too slow for real-time trading loop |
| Reinforcement learning agent | Too unstable for real money |
| Custom embedding model | Voyage provides best-in-class |
| Custom vector DB | ChromaDB is purpose-built |