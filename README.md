# BetBot

Autonomous prediction market investment toolkit for [OpenClaw](https://github.com/openclaw/openclaw) agents.

BetBot provides the data pipeline, statistical analysis, risk enforcement, simulation, and execution layer that an AI agent needs to trade prediction markets — starting with [Kalshi](https://kalshi.com), expanding to stocks and other instruments.

## Core Principle

**Dumb pipe with smart guards.** The toolkit handles the *how* (API calls, data normalization, risk limits, execution) but never the *why* (what to trade, when, how much). The agent decides strategy; the toolkit ensures execution is safe, correct, and auditable.

This separation is deliberate: it eliminates emotional bias from the execution layer. Even if the agent's LLM "decides" to go all-in on a hunch, hard-coded risk guards reject the order before it reaches the exchange.

## Architecture at a Glance

BetBot runs three autonomous loops via OpenClaw:

| Loop | Frequency | Purpose |
|---|---|---|
| **Decision Loop** | Continuous (market hours) | Analyze → signal → risk-check → execute |
| **Heartbeat Loop** | Every 6 hours | Performance review → adapt parameters → log learnings |
| **News/Sentiment Loop** | Event-driven | Process news → classify → update market outlook |

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Project Structure

```
betbot/
├── src/betbot/
│   ├── kalshi/              # Kalshi exchange adapter
│   ├── analysis/            # Statistical computation engine
│   ├── risk/                 # Immutable risk enforcement
│   ├── simulation/          # Backtesting & paper trading
│   ├── news/                # News & social media pipeline
│   ├── db/                  # State persistence (SQLite)
│   └── cli.py               # CLI entry point
├── skills/betbot/
│   └── SKILL.md             # OpenClaw skill definition
├── .openclaw/workspace/     # Agent workspace files
│   ├── AGENTS.md
│   ├── SESSION-STATE.md
│   ├── HEARTBEAT.md
│   └── .learnings/
├── docs/                    # Full documentation
├── tests/
├── AGENTS.md                # AI-assisted development conventions
└── pyproject.toml
```

## Documentation

| Document | Scope |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Three-loop system, components, data flow, toolkit vs. agent boundary |
| [docs/kalshi.md](docs/kalshi.md) | Kalshi API reference: endpoints, auth, SDK, historical data, rate limits |
| [docs/openclaw-integration.md](docs/openclaw-integration.md) | Skill system, workspace files, cron architectures, proactive patterns |
| [docs/risk.md](docs/risk.md) | Hard risk guards, circuit breakers, position sizing, audit trail, anti-bias design |
| [docs/simulation.md](docs/simulation.md) | Backtest engine, data loading, paper trading, performance metrics |
| [docs/news-sentiment.md](docs/news-sentiment.md) | Pipeline architecture, sources, classifiers, impact assessment |
| [docs/self-learning.md](docs/self-learning.md) | Bayesian adaptation, learning logs, heartbeat, WAL protocol |
| [docs/product-roadmap.md](docs/product-roadmap.md) | Implementation phases, dependencies, future expansion |
| [docs/research.md](docs/research.md) | External references, existing projects, ecosystem analysis |

## Quick Start

*Not yet implemented. See [docs/product-roadmap.md](docs/product-roadmap.md) for implementation timeline.*

```bash
# Install (future)
pip install betbot

# Configure
export KALSHI_API_KEY=your_key_id
export KALSHI_PRIVATE_KEY=path/to/private_key.pem

# Scan markets
betbot scan

# Deep analysis
betbot analyze KXBTCD-26MAR31-T55000

# Paper trade a strategy
betbot paper momentum

# Run heartbeat (self-review)
betbot heartbeat
```

## License

MIT