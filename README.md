# TraderBot

Autonomous prediction market investment toolkit for [OpenClaw](https://github.com/openclaw/openclaw) agents.

TraderBot provides the data pipeline, statistical analysis, risk enforcement, simulation, and execution layer that an AI agent needs to trade prediction markets — starting with [Kalshi](https://kalshi.com), expanding to stocks and other instruments.

## Core Principle

**Dumb pipe with smart guards.** The toolkit handles the *how* (API calls, data normalization, risk limits, execution) but never the *why* (what to trade, when, how much). The agent decides strategy; the toolkit ensures execution is safe, correct, and auditable.

This separation is deliberate: it eliminates emotional bias from the execution layer. Even if the agent's LLM "decides" to go all-in on a hunch, hard-coded risk guards reject the order before it reaches the exchange.

## Prerequisites

- **OpenClaw** — TraderBot is designed to be operated by OpenClaw AI agents. [Install OpenClaw first](https://github.com/openclaw/openclaw#installation).
- **Python 3.12** — required (chroma-hnswlib has no wheels for 3.13+)
- **Kalshi API credentials** — sign up at [kalshi.com](https://kalshi.com) and generate an API key + RSA key pair

## One-Liner Install

```bash
curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh -o /tmp/traderbot-installer.sh && bash /tmp/traderbot-installer.sh
```

The installer auto-detects your OS (Ubuntu/Debian or macOS), installs dependencies, clones the repo, and runs the interactive config wizard — covering API keys, profile creation, and OpenClaw agent assignment.

### Installer Options

| Flag | Description |
|------|-------------|
| *(none)* | Interactive install with config wizard |
| `--update` | Pull latest from GitHub and restart services |
| `--uninstall` | Remove all TraderBot services and files |
| `--help` | Show full usage |

### Manual Install

```bash
# Clone the repo
git clone https://github.com/JsonDaRula69/TraderBot.git ~/traderbot
cd ~/traderbot

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Quick Start

```bash
# 1. Configure your Kalshi credentials
#    Create ~/.traderbot/.env with:
export KALSHI_API_KEY=your_key_id
export KALSHI_PRIVATE_KEY_PEM="$(cat /path/to/private_key.pem)"

# 2. Scan available markets
traderbot scan

# 3. Deep analysis on a specific market
traderbot analyze KXBTCD-26MAR31-T55000

# 4. Paper trade a strategy
traderbot paper momentum

# 5. Run a heartbeat (self-review cycle)
traderbot heartbeat
```

### OpenClaw Agent Setup

After installing TraderBot, configure your OpenClaw agents to use it:

1. **Assign a profile token** to your agent:
   ```bash
   traderbot profile create --name weather-agent --category weather
   traderbot profile assign --agent weather-agent --token $(traderbot profile token weather-agent)
   ```

2. **Set `TRADERBOT_PROFILE_TOKEN`** in your agent's environment (OpenClaw `.env` or agent config)

3. The agent can now run all TraderBot commands autonomously. See [TOOLS.md](.openclaw/workspace/TOOLS.md) for the agent command reference.

See [docs/deployment.md](docs/deployment.md) for full deployment instructions including systemd/launchd service setup.

## Architecture

TraderBot runs three autonomous loops via OpenClaw:

| Loop | Frequency | Purpose |
|---|---|---|
| **Decision Loop** | Continuous (market hours) | Analyze → signal → risk-check → execute |
| **Heartbeat Loop** | Every 6 hours | Performance review → adapt parameters → log learnings |
| **News/Sentiment Loop** | Event-driven | Process news → classify → update market outlook |

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Project Structure

```
traderbot/
├── src/traderbot/
│   ├── kalshi/              # Kalshi exchange adapter
│   ├── analysis/            # Statistical computation engine
│   ├── risk/                # Immutable risk enforcement
│   ├── simulation/          # Backtesting & paper trading
│   ├── news/                # News & social media pipeline
│   ├── profiles/            # Multi-agent profile system
│   │   ├── models.py        # TradingProfile model
│   │   ├── registry.py      # ProfileRegistry (.env CRUD)
│   │   ├── tokens.py        # Token generation/resolution
│   │   ├── config.py        # Profile-aware credential resolution
│   │   ├── isolation.py     # Per-profile data isolation
│   │   └── runtime.py       # Runtime context resolution
│   ├── db/                  # State persistence (SQLite)
│   └── cli.py               # CLI entry point
├── install/
│   ├── traderbot-installer.sh  # OS detection, deps, config flow
│   └── services/              # Systemd templates
├── skills/traderbot/
│   └── SKILL.md             # OpenClaw skill definition
├── .openclaw/workspace/     # Agent workspace files
│   ├── AGENTS.md
│   ├── TOOLS.md             # Agent CLI reference
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
| [docs/risk.md](docs/risk.md) | Hard risk guards, AgentRiskLimits, circuit breakers, position sizing, audit trail, anti-bias design |
| [docs/simulation.md](docs/simulation.md) | Backtest engine, data loading, paper trading, performance metrics |
| [docs/news-sentiment.md](docs/news-sentiment.md) | Pipeline architecture, sources, classifiers, impact assessment |
| [docs/self-learning.md](docs/self-learning.md) | Bayesian adaptation, learning logs, heartbeat, WAL protocol |
| [docs/product-roadmap.md](docs/product-roadmap.md) | Implementation phases, dependencies, future expansion |
| [docs/research.md](docs/research.md) | External references, existing projects, ecosystem analysis |
| [docs/profiles.md](docs/profiles.md) | Profile system architecture, TradingProfile model, registry, token handshake |
| [docs/deployment.md](docs/deployment.md) | Ubuntu (Debian-based Linux) installation, persistence setup, profile-agent flow |
| [docs/security.md](docs/security.md) | Threat model, token handshake security, .env-based encryption, enforcement layers |
| [docs/api.md](docs/api.md) | CLI command reference including profile commands |

## CLI Overview

| Command | Description |
|---|---|
| `traderbot scan` | List open markets across categories |
| `traderbot analyze TICKER` | Orderbook depth + implied probability |
| `traderbot signals` | Active trading signals |
| `traderbot news` | Fetch news from all active sources |
| `traderbot sentiment TICKER` | Aggregate sentiment analysis |
| `traderbot paper` | Paper trade (no real money) |
| `traderbot trade` | Place a real order (human-only) |
| `traderbot positions` | View open positions |
| `traderbot performance` | P&L and metrics |
| `traderbot heartbeat` | Self-review: performance, adaptation, risk state |
| `traderbot profile` | Profile management (create, list, assign tokens) |
| `traderbot auth check` | Verify credential configuration |
| `traderbot resume` | Clear circuit breaker halt state |

Full reference in [TOOLS.md](.openclaw/workspace/TOOLS.md) and [docs/api.md](docs/api.md).

## License

MIT