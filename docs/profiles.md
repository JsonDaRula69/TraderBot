# Profile System

The profile system enables multi-agent deployment where each OpenClaw agent runs with isolated data, risk parameters, market category filters, and API credentials. Traders configure profiles; agents receive tokens; the toolkit enforces boundaries.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Profile Registry (.env file)                        │
│                    traderbot.profiles.<name> → JSON profile           │
└──────────┬───────────────────┬──────────────────────┬────────────────┘
           │                   │                      │
    ┌──────▼──────┐    ┌───────▼──────┐      ┌──────▼──────┐
    │   Profile   │    │    Token     │      │    Auth     │
    │   Models    │    │   Module     │      │   Store     │
    │ TradingProf │    │ assign/      │      │ ProfileAuth │
    │             │    │ resolve/     │      │ Manager     │
    └─────────────┘    │ revoke       │      └──────┬──────┘
                       └──────┬───────┘             │
                              │               ┌─────▼─────┐
                       ┌──────▼──────┐       │  .env     │
                       │  Injection  │       │  Shared   │
                       │ into TOOLS  │       │  API Keys │
                       └─────────────┘       └───────────┘
```

## TradingProfile Model

Every profile is a `TradingProfile` stored in the `.env` file under `traderbot.profiles.<name>`.

```python
class TradingProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str                                          # Unique identifier
    mode: Literal["paper", "live"]                     # Trading mode
    description: str                                   # Human-readable description
    enabled_categories: list[MarketCategory]          # Empty = all permitted
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0)]
    max_position_per_market_pct: Annotated[float, Field(gt=0)]
    max_daily_loss_pct: Annotated[float, Field(gt=0)]
    max_drawdown_pct: Annotated[float, Field(gt=0)]
    max_open_positions: Annotated[int, Field(gt=0)]
    min_liquidity_threshold: Annotated[int, Field(gt=0)]
    min_edge_pct: Annotated[float, Field(gt=0)]
```

### Computed Properties

```python
profile.base_dir      # ".traderbot-paper" or ".traderbot-live"
profile.env_file      # ".env.paper" or ".env.live"
```

### HARD_LIMITS Ceiling

All risk parameters are validated against `HARD_LIMITS` at creation time. A profile cannot exceed these ceilings:

| Parameter | Ceiling | Floor |
|---|---|---|
| `max_position_per_market_pct` | 5% | N/A |
| `max_daily_loss_pct` | 2% | N/A |
| `max_drawdown_pct` | 10% | N/A |
| `max_open_positions` | 20 | N/A |
| `min_liquidity_threshold` | N/A | 1000 |
| `min_edge_pct` | N/A | 3% |

Attempting to create a profile with stricter-than-ceiling parameters raises `ValueError`.

### Category Filtering

```python
profile.is_category_enabled(category: MarketCategory) -> bool
```

An empty `enabled_categories` list means all categories are permitted. If a list is provided, only those categories are allowed.

## Profile Registry

`ProfileRegistry` manages CRUD operations for profiles. It stores profiles in a `.env`-based configuration by default, with automatic fallback to an AES-256 encrypted file when needed (e.g., headless Linux).

```python
registry = ProfileRegistry()

registry.create_profile(profile)           # Store in .env or encrypted file
profile = registry.get_profile(name)       # Retrieve by name, None if missing
names = registry.list_profiles()          # All profile names (sorted)
registry.profile_exists(name)             # Boolean check
registry.delete_profile(name, keep_data)  # Remove + optionally purge data dirs
```

Storage namespace: `traderbot.profiles.<name>` (`.env` file) or `~/.traderbot/profiles.enc` (file fallback)

## Headless Linux / File Storage

On headless Linux servers (no desktop environment, no D-Bus session), the `.env` file is the primary storage. `ProfileRegistry` falls back to an AES-256 encrypted file when `.env` is unavailable.

### Fallback Path

```
~/.traderbot/profiles.enc    # AES-256 encrypted JSON blob (mode 0600)
```

The file stores all profiles as a single JSON dictionary, encrypted via `cryptography.fernet` (Fernet, AES-128-CBC with HMAC-SHA256).

### Encryption Key

The AES-256 key is derived as follows:

1. **Key file available**: A 32-byte random key is stored in `~/.traderbot/.profile_key` (mode 0600).
2. **Key file missing**: A 32-byte key is generated and stored in `~/.traderbot/.profile_key`.

The `_derive_or_create_key()` function creates the key on first access and caches it.

### Migration from Legacy

If a plaintext `~/.traderbot/profiles.json` exists alongside `profiles.enc`, the registry imports and encrypts it, then deletes the legacy file.

## Token Handshake

Agents are bound to profiles via opaque tokens. The flow:

1. **Generate**: `generate_token()` → 12-char URL-safe string (~72 bits entropy)
2. **Assign**: `assign_token(profile_name, agent_id, token)` → stored in `.env` as `traderbot.tokens.<token>`
3. **Resolve**: `resolve_token(token)` → `(profile_name, agent_id)` or `None` if invalid/revoked
4. **Revoke**: `revoke_token(token)` → deletes from `.env`

### One-to-One Binding

A profile can have only one active token. Attempting to assign a second token to a profile that already has one raises `ValueError`.

### Token Injection

`inject_token(agent_path, token)` writes the token into the agent's `TOOLS.md`:

```markdown
## Environment Variables

The following environment variables are available:
- `TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4`: Your assigned profile token (do not modify)
```

If a token already exists, it is replaced. New sections are created if `## Environment Variables` does not exist. Write is atomic via temp file.

### Agent Path Resolution

The `_resolve_agent_path(agent_id)` function resolves agent paths in OpenClaw's multi-agent layout. Search order:

1. **Per-agent workspace**: `~/.openclaw/workspace-<agentId>/TOOLS.md`
2. **Subdirectory layout**: `~/.openclaw/workspace/<agentId>/TOOLS.md`
3. **Agent state dir**: `~/.openclaw/agents/<agentId>/TOOLS.md`

The first match wins. If none of these exist, `inject_token()` receives the raw path passed by the caller (from `discover_agents()`).

## Shared Credential Storage

All profiles share the same `.env` file for API credentials. There is no per-profile credential isolation.

```python
from traderbot.profiles import get_current_profile

profile = get_current_profile()  # Reads TRADERBOT_PROFILE_TOKEN env var
# API keys always come from ~/.traderbot/.env
```

API keys (`KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PEM`) are stored once in `~/.traderbot/.env` and shared by all agents regardless of profile.

### Credential Resolution Chain

When resolving API credentials:

1. `.env` file (`~/.traderbot/.env` with mode 0600)
2. Environment variable fallback

The resolution chain in `resolve_kalshi_credentials()` reads from `.env` first, then falls back to `KALSHI_API_KEY` / `KALSHI_PRIVATE_KEY_PEM` environment variables.

## Data Isolation

Each profile has isolated data directories:

| Path | Purpose |
|---|---|
| `~/.traderbot-paper/` | Paper trading data |
| `~/.traderbot-live/` | Live trading data |

### Isolated Paths

```python
get_profile_db_path(profile, "decisions.db")  # ~/.traderbot-paper/db/decisions.db
get_profile_chroma_path(profile)                 # ~/.traderbot-paper/chroma
get_profile_audit_path(profile)                 # ~/.traderbot-paper/audit
```

Directories are created on demand via `ensure_profile_dirs(profile)`.

## Runtime Resolution

At CLI startup, `get_current_profile()` reads the `TRADERBOT_PROFILE_TOKEN` environment variable, resolves it to a profile, and returns the `TradingProfile`. This profile is passed to `evaluate_trade()` for category filtering and risk ceiling enforcement.

```python
profile = get_current_profile()  # None if env var not set
```

The full config bundle:

```python
config = load_profile_config(profile)
# Returns:
#   - credentials: {"kalshi": (api_key, api_secret)}
#   - paths: {"db": Path, "chroma": Path, "audit": Path}
#   - limits: dict of effective risk limits
```

## CLI Commands

```bash
# Profile CRUD
traderbot profile create <name> --mode paper|live [--description TEXT] \
    [--categories Economics,Politics,...] [--risk-multiplier N] \
    [--max-position-pct N] [--max-daily-loss-pct N] [--max-drawdown-pct N] \
    [--max-open-positions N] [--min-liquidity N] [--min-edge-pct N]

traderbot profile list [--json]
traderbot profile show <name> [--json]
traderbot profile delete <name> [--keep-data]

# Agent assignment
traderbot profile assign <agent-id> <profile-name>   # Generate token, inject into TOOLS.md
traderbot profile revoke <profile-name>               # Revoke token, remove from TOOLS.md
traderbot profile assignments [--json]               # List all token assignments

# Credential management
traderbot profile set-auth <profile-name> <service> <key>
traderbot profile auth <profile-name> [--json]

# Discovery
traderbot profile discover-agents [--json]           # Scan OpenClaw agents (3-source)
```

## OpenClaw Agent Discovery

`discover_agents()` scans three sources in priority order. Agents found in higher-priority sources are deduplicated from later sources by `agent_id`:

| Priority | Source | Format |
|---|---|---|
| 1 (highest) | `~/.openclaw/openclaw.json` | `agents.list[].id`, `workspace`, `name` |
| 2 | `~/.openclaw/agents/<agentId>/IDENTITY.md` | Markdown fields per agent directory |
| 3 | Workspace directories | `IDENTITY.md` in CWD, `~/.openclaw/workspace/`, `~/traderbot/.openclaw/workspace/` |

```python
agents = discover_agents()
# Returns: [{"agent_id": "...", "name": "...", "path": "..."}]
```

### Source 1: openclaw.json

The authoritative multi-agent config from `~/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "list": [
      {"id": "molty", "workspace": "~/.openclaw/workspace-molty", "name": "Molty"}
    ]
  }
}
```

Each entry provides `id`, `workspace`, and `name`. The `workspace` path, if present, is used as the agent's root path. If absent, defaults to `~/.openclaw/workspace/`.

### Source 2: Agent Directories

Each subdirectory of `~/.openclaw/agents/` is checked for an `IDENTITY.md` file. Supported fields:

```markdown
- **Agent ID**: molty
- **Name**: Molty the Trader
```

Both `Agent ID` and `Name` must be present. The regex is case-insensitive and flexible about whitespace.

### Source 3: Workspace Directories

Scans multiple workspace paths for `IDENTITY.md` files (direct agent dirs and their subdirectory children):

- Default workspace path (`.openclaw/workspace/`)
- `~/.openclaw/workspace/` (OpenClaw home)
- `~/traderbot/.openclaw/workspace/` (legacy installation path)

This source exists for backward compatibility with older installations that store IDENTITY.md directly in workspace directories.

## Multi-Agent Deployment

TraderBot integrates with OpenClaw's multi-agent architecture to run multiple autonomous agents, each with its own profile, workspace, and credential isolation.

### OpenClaw Multi-Agent Layout

OpenClaw (v0.7+) manages agents through `~/.openclaw/openclaw.json`. Each agent has:

| Path | Purpose |
|---|---|
| `~/.openclaw/openclaw.json` | Agent registry: `agents.list[].id`, `workspace`, `name` |
| `~/.openclaw/workspace-<agentId>/` | Per-agent workspace directory |
| `~/.openclaw/agents/<agentId>/` | Agent state directory (IDENTITY.md, sessions, auth) |
| `~/.openclaw/workspace/<agentId>/` | Subdirectory layout (legacy) |

Create new agents with:

```bash
openclaw agents add molty
# Creates: ~/.openclaw/workspace-molty/, ~/.openclaw/agents/molty/
```

### Profile-Agent Binding Flow

```
              ┌──────────────────┐
              │  openclaw.json   │
              │  agents.list[]   │
              └──────┬───────────┘
                     │
              ┌──────▼───────────┐
              │ discover_agents() │── 3-source scan (config, dirs, workspaces)
              └──────┬───────────┘
                     │
              ┌──────▼───────────┐
              │ assign_token()   │── Generate 12-char token, store mapping
              └──────┬───────────┘
                     │
              ┌──────▼───────────┐
              │ inject_token()   │── Write into agent's TOOLS.md
              └──────────────────┘
```

1. `discover_agents()` scans openclaw.json, agent directories, and workspace paths to find all available agents.
2. `traderbot profile assign <agent-id> <profile-name>` generates a token and binds the agent ID to the profile name in the `.env` file.
3. `inject_token()` writes `TRADERBOT_PROFILE_TOKEN` into the agent's `TOOLS.md` using path resolution (`workspace-<id>`, then `workspace/<id>`, then `agents/<id>`).
4. At runtime, the agent reads `TRADERBOT_PROFILE_TOKEN` from its environment (either from `TOOLS.md` or from a launchd/systemd service definition).

### Running Multiple Agents

Each agent runs independently with its own:

- **Profile**: Risk parameters, category filters, mode (paper/live)
- **Credentials**: Shared API keys in `.env` file under `traderbot.profiles.<name>.<service>`
- **Data**: SQLite DB, ChromaDB, audit logs in `~/.traderbot-<mode>/`
- **Token**: One-to-one binding — one profile per token, one token per agent

```bash
# Create two profiles
traderbot profile create aggro --mode paper --risk-multiplier 0.9
traderbot profile create conservative --mode paper --risk-multiplier 0.3

# Assign to different agents
traderbot profile assign molty aggro
traderbot profile assign alice conservative

# Each agent now has its own TRADERBOT_PROFILE_TOKEN in TOOLS.md
```

### Service Persistence

For persistent background operation, each agent gets its own systemd or launchd service instance with the token set in the environment:

**Linux (systemd)**:
```bash
bash install/services/install-service.sh molty <token>
# Creates: ~/.config/systemd/user/traderbot-agent@molty.service
# Token set as Environment=TRADERBOT_PROFILE_TOKEN=<token>
```

**macOS (launchd)**:
```bash
bash install/services/install-launchd.sh molty <token>
# Creates: ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
# Token set as EnvironmentVariables
```

See [deployment.md](deployment.md) for full service management details.

### Bindings

OpenClaw bindings map channel accounts (Discord, Slack, Telegram) to agents. This is configured in `~/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "list": [
      {"id": "molty", "workspace": "~/.openclaw/workspace-molty", "name": "Molty"}
    ]
  },
  "bindings": {
    "discord:123456789:general": "molty"
  }
}
```

The profile system is agent-agnostic at the toolkit level. Token resolution binds a profile to an `agent_id` string; the toolkit never concerns itself with which channel or platform the agent uses.
