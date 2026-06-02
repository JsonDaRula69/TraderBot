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
|---|---|
| `traderbot scan` | List open markets across categories |
| `traderbot analyze TICKER` | Orderbook depth + implied probability |
| `traderbot signals` | Active trading signals |
| `traderbot trade` | Place an order through risk checks |
| `traderbot positions` | View open positions with live pricing |
| `traderbot audit` | Decision history with filters |
| `traderbot performance` | P&L and win-rate metrics |
| `traderbot paper` | Run a paper trading session |
| `traderbot backtest` | Run backtests against historical data |
| `traderbot compare` | Compare profiles across strategies |
| `traderbot halt` | Check circuit breaker status |
| `traderbot resume` | Clear circuit breaker halt state |
| `traderbot heartbeat` | Self-review cycle |
| `traderbot learnings` | List and promote learned patterns |
| `traderbot data forecasts` | Weather forecasts with NWS + GFS/ECMWF/GEM ensemble |
| `traderbot data bias CITY` | Historical forecast bias for a city |
| `traderbot news-context` | News context for a category |
| `traderbot auth` | Credential management |
| `traderbot profile` | Multi-agent profile management |
| `traderbot cron` | Register heartbeat cron jobs with OpenClaw |
| `traderbot update` | Check for and apply updates |

## Project Structure

```
src/traderbot/
├── kalshi/           # Kalshi exchange adapter
├── analysis/         # Statistical computation engine
├── risk/             # Immutable risk enforcement
├── simulation/       # Backtesting & paper trading
├── news/             # News & sentiment pipeline
├── data/             # Weather & market data providers
├── db/               # SQLite persistence
├── profiles/         # Multi-agent profile system
├── cli/              # Typer CLI entry point and sub-commands
├── experiment/       # Experiment design and evaluation
├── heartbeat.py      # Self-review cycle
├── auth.py           # Credential management
├── learning.py       # Learning log manager
└── updater.py        # Version management
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