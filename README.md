# TraderBot

[![PyPI version](https://img.shields.io/pypi/v/traderbot)](https://pypi.org/project/traderbot/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

Autonomous prediction market investment toolkit for [Kalshi](https://kalshi.com).

TraderBot provides the data pipeline, statistical analysis, risk enforcement, simulation, and execution layer that an AI agent needs to trade prediction markets.

## Core Principle

**Dumb pipe with smart guards.** The toolkit handles the *how* (API calls, data normalization, risk limits, execution) but never the *why* (what to trade, when, how much). The agent decides strategy; the toolkit ensures execution is safe, correct, and auditable.

This separation is deliberate: it eliminates emotional bias from the execution layer. Even if the agent's LLM "decides" to go all-in on a hunch, hard-coded risk guards reject the order before it reaches the exchange.

## Install

### From PyPI (recommended)

```bash
pip install traderbot
```

### From source

```bash
git clone https://github.com/JsonDaRula69/TraderBot.git
cd TraderBot
uv sync  # or: pip install -e .
```

### One-Liner Install (Linux/macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh | bash
```

### One-Liner Install (Linux/macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh | bash
```

Or install directly from PyPI on any platform:

```bash
pip install traderbot
```

Requires **Python 3.12** and Kalshi API credentials (sign up at [kalshi.com](https://kalshi.com) and generate an API key + RSA key pair).

## Quick Start

```bash
# Store Kalshi credentials in your OS keyring
traderbot auth set-kalshi

# Scan available weather markets
traderbot scan --category weather

# Analyze a specific market
traderbot analyze KXHIGHNY-26JUN02-T72

# Paper trade with a strategy
traderbot paper momentum

# View your positions
traderbot positions

# Check for updates
traderbot update --check
```

### Using with OpenClaw AI Agents

TraderBot integrates with [OpenClaw](https://github.com/openclaw/openclaw) for autonomous agent operation:

```bash
# Create a profile for your agent
traderbot profile create --name weather-agent --category weather

# Assign the profile token
traderbot profile assign --agent weather-agent --token $(traderbot profile token weather-agent)
```

The agent runs three autonomous loops: decision (every 5 min), heartbeat (every 30 min), and news/sentiment (event-driven). See [docs/architecture.md](docs/architecture.md) for details.

## CLI Overview

| Command | Description |
|---|---|---|
| `traderbot scan` | List open markets across categories |
| `traderbot analyze TICKER` | Orderbook depth + implied probability |
| `traderbot signals` | Active trading signals |
| `traderbot trade` | Place an order through risk checks |
| `traderbot positions` | View open positions |
| `traderbot audit` | Decision history with filters |
| `traderbot performance` | P&L and win-rate metrics |
| `traderbot paper` | Run a paper trading session |
| `traderbot backtest` | Run backtests against historical data |
| `traderbot compare` | Compare profiles across strategies |
| `traderbot halt` | Circuit breaker status check |
| `traderbot resume` | Clear circuit breaker halt state |
| `traderbot heartbeat` | Self-review cycle |
| `traderbot learnings` | List and promote learned patterns |
| `traderbot check-settlements` | Check for recently settled markets |
| `traderbot reconcile` | Sync local positions with Kalshi API |
| `traderbot cache warm` | Pre-populate event category cache |
| `traderbot data forecasts` | Weather forecasts with NWS + GFS/ECMWF/GEM ensemble |
| `traderbot data signals` | Trading signals by category |
| `traderbot data bias CITY` | Historical forecast bias for a city |
| `traderbot news-context` | News context for a category |
| `traderbot news-ingest` | Fetch, classify, embed news to ChromaDB |
| `traderbot data-points` | Query ChromaDB for structured data readings |
| `traderbot backfill` | One-time or recurring historical data backfill |
| `traderbot sentiment TICKER` | Analyze market sentiment from news |
| `traderbot auth` | Credential management (set-kalshi, check, migrate, rotate) |
| `traderbot profile` | Multi-agent profile management (create, list, assign, revoke) |
| `traderbot cron` | Register heartbeat cron jobs with OpenClaw |
| `traderbot bootstrap` | One-time environment setup wizard |
| `traderbot experiment` | A/B test harness (populate, verify, run, results) |
| `traderbot update` | Check for and apply updates |
| `traderbot uninstall` | Remove TraderBot and all artifacts |

## Project Structure

```
src/traderbot/
├── kalshi/           # Kalshi exchange adapter (client, models, signing, trading, websocket)
├── analysis/         # Statistical computation (indicators, odds, signals, registry)
├── risk/             # Immutable risk enforcement (limits, sizing, circuit breaker)
├── simulation/       # Backtesting engine & paper trading
├── news/             # News & sentiment pipeline (sources, classifier, embeddings, impact)
├── data/             # Data providers (weather NWS/Open-Meteo, base provider/signal ABCs)
├── db/               # SQLite persistence (positions, decisions, learnings, vectors, WAL)
├── profiles/         # Multi-agent profile system (models, runtime, injection, token)
├── cli/              # Typer CLI entry point and sub-commands (9 modules)
├── experiment/       # Experiment design, harness, and evaluation (treatments, results, registry)
├── sandbox.py        # Application-level filesystem sandbox (macOS sandbox-exec + chmod)
├── auth.py           # Credential management (keyring, .env, master password)
├── paper.py          # Paper balance computation
├── learning.py       # Learning log manager
├── heartbeat.py      # Self-review cycle
├── updater.py        # Version management (check, install mode detection, auto-update)
├── wal.py            # Write-ahead log for crash-safe trade execution
└── paths.py          # Data directory resolution
```

## Documentation

| Document | Scope |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Three-loop system, components, data flow |
| [docs/kalshi.md](docs/kalshi.md) | Kalshi API reference |
| [docs/risk.md](docs/risk.md) | Risk guards, circuit breakers, position sizing |
| [docs/simulation.md](docs/simulation.md) | Backtest engine, paper trading |
| [docs/profiles.md](docs/profiles.md) | Profile system, tokens, multi-agent |
| [docs/deployment.md](docs/deployment.md) | Production deployment |
| [docs/api.md](docs/api.md) | Full CLI reference |

## License

MIT