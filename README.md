# TraderBot

Autonomous prediction market investment toolkit for [OpenClaw](https://github.com/openclaw/openclaw) agents.

TraderBot provides the data pipeline, statistical analysis, risk enforcement, simulation, and execution layer that an AI agent needs to trade prediction markets — starting with [Kalshi](https://kalshi.com), expanding to stocks and other instruments.

## Core Principle

**Dumb pipe with smart guards.** The toolkit handles the *how* (API calls, data normalization, risk limits, execution) but never the *why* (what to trade, when, how much). The agent decides strategy; the toolkit ensures execution is safe, correct, and auditable.

This separation is deliberate: it eliminates emotional bias from the execution layer. Even if the agent's LLM "decides" to go all-in on a hunch, hard-coded risk guards reject the order before it reaches the exchange.

## Prerequisites

- **OpenClaw** (optional) — TraderBot can be operated by OpenClaw AI agents or used standalone. [Install OpenClaw](https://github.com/openclaw/openclaw#installation) if using agent integration.
- **Python 3.12** — required (chroma-hnswlib has no wheels for 3.13+)
- **Kalshi API credentials** — sign up at [kalshi.com](https://kalshi.com) and generate an API key + RSA key pair

## One-Liner Install

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh -o /tmp/traderbot-installer.sh && bash /tmp/traderbot-installer.sh
```

### Windows (PowerShell)

```powershell
.\install\Install-TraderBot.ps1
```

The installer auto-detects your OS (Ubuntu/Debian, macOS, or Windows), installs dependencies, clones the repo, and runs the interactive config wizard — covering API keys, profile creation, and OpenClaw agent assignment.

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

### Credential Setup (Recommended: OS Keyring)

```bash
# 1. Store Kalshi credentials securely in your OS keyring
#    (macOS Keychain, Windows Credential Locker, or Linux Secret Service)
traderbot auth set-kalshi
# Prompts for KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PEM

# Fallback: create ~/.traderbot/.env manually (not recommended for production)
# export KALSHI_API_KEY=your_key_id
# export KALSHI_PRIVATE_KEY_PEM="$(cat /path/to/private_key.pem)"
```

### Market Analysis

```bash
# 2. Scan available markets
traderbot scan

# 3. Deep analysis on a specific market
traderbot analyze KXBTCD-26MAR31-T55000

# 4. Paper trade a strategy (no authentication required)
traderbot paper momentum

# 5. Place a live trade (requires master password)
traderbot auth setup-master-password  # One-time setup
traderbot trade KXBTCD-26MAR31-T55000 --direction yes --quantity 10 --confirm

# 6. Run a heartbeat (self-review cycle)
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
|---|---|---|---|
| **Decision Loop** | Every 5 minutes (24/7) | Analyze → signal → risk-check → execute |
| **Heartbeat Loop** | Every 30 minutes | Performance review → adapt parameters → log learnings |
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
│   │   ├── runtime.py       # Runtime context resolution
│   │   ├── auth.py          # Credential management & AuthManager
│   │   ├── discovery.py     # OpenClaw agent discovery
│   │   ├── injection.py     # Token/agent file injection
│   │   └── injection_strategies.py  # File merge strategies
│   ├── db/                  # State persistence (SQLite)
│   ├── cli.py               # CLI entry point (Typer)
│   ├── cron_loops.py        # Three-loop cron models
│   ├── paths.py             # Data directory resolution
│   ├── wal.py               # Write-ahead log protocol
│   ├── heartbeat.py         # Self-review cycle logic
│   ├── learning.py          # Learning log manager
│   ├── auth.py              # AuthManager
│   └── updater.py           # Version management
├── install/
│   ├── traderbot-installer.sh  # OS detection, deps, config flow
│   └── services/              # Systemd/launchd templates
├── skills/traderbot/
│   └── SKILL.md             # OpenClaw skill definition
├── .openclaw/workspace/     # Agent workspace file templates
│   ├── AGENTS.md            # Agent operating rules
│   ├── SOUL.md              # Persona & behavioral principles
│   ├── IDENTITY.md          # Agent identity
│   ├── BOOT.md              # Startup checklist
│   ├── BOOTSTRAP.md         # One-time identity ritual
│   ├── TOOLS.md             # Agent CLI reference
│   ├── HEARTBEAT.md         # Heartbeat instructions
│   ├── HEARTBEAT_DATA.md    # Heartbeat output data
│   ├── SESSION-STATE.md     # WAL protocol target
│   ├── USER.md              # Human profile
│   ├── MEMORY.md            # Cross-session memory
│   └── .learnings/          # Self-improvement logs
├── docs/                    # Full documentation
├── tests/
├── AGENTS.md                # AI-assisted development conventions
├── ROADMAP_PROGRESS.md      # Phase progress tracking
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
| `traderbot trade` | Place a real order (human-only) |
| `traderbot positions` | View open positions |
| `traderbot audit` | Show decision history with filters |
| `traderbot performance` | P&L and metrics |
| `traderbot paper` | Paper trade (no real money) |
| `traderbot backtest` | Run backtests against historical data |
| `traderbot compare` | Compare strategy performance across profiles |
| `traderbot bootstrap` | One-time setup wizard |
| `traderbot heartbeat` | Self-review: performance, adaptation, risk state |
| `traderbot halt` | Check/set circuit breaker status |
| `traderbot resume` | Clear circuit breaker halt state |
| `traderbot learnings` | List learned patterns and trigger promotions |
| `traderbot cron setup` | Register cron loops with OpenClaw |
| `traderbot profile` | Profile management (create, list, assign, auth) |
| `traderbot auth` | Credential management (check, login, set-key) |

Full reference in [TOOLS.md](.openclaw/workspace/TOOLS.md) and [docs/api.md](docs/api.md).

## License

MIT