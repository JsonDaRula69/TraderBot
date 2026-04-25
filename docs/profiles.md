# Profile System

The profile system enables multi-agent deployment where each OpenClaw agent runs with isolated data, risk parameters, market category filters, and API credentials. Traders configure profiles; agents receive tokens; the toolkit enforces boundaries.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Profile Registry (Keyring)                        │
│              traderbot.profiles.<name> → JSON profile                │
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
                       ┌──────▼──────┐       │  Keyring  │
                       │  Injection  │       │ Namespace │
                       │ into TOOLS  │       │ profiles. │
                       └─────────────┘       │ <name>    │
                                            └───────────┘
```

## TradingProfile Model

Every profile is a `TradingProfile` stored in the OS keyring under `traderbot.profiles.<name>`.

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
profile.demo_mode     # True if mode == "paper"
profile.base_dir      # ".traderbot-paper" or ".traderbot-live"
profile.keyring_prefix  # "traderbot-paper-<name>" or "traderbot-live-<name>"
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

`ProfileRegistry` manages CRUD operations for profiles in the OS keyring.

```python
registry = ProfileRegistry()

registry.create_profile(profile)           # Store in keyring
profile = registry.get_profile(name)       # Retrieve by name, None if missing
names = registry.list_profiles()          # All profile names (sorted)
registry.profile_exists(name)             # Boolean check
registry.delete_profile(name, keep_data)  # Remove + optionally purge data dirs
```

Storage namespace: `traderbot.profiles.<name>`

## Token Handshake

Agents are bound to profiles via opaque tokens. The flow:

1. **Generate**: `generate_token()` → 12-char URL-safe string (~72 bits entropy)
2. **Assign**: `assign_token(profile_name, agent_id, token)` → stored in keyring as `traderbot.tokens.<token>`
3. **Resolve**: `resolve_token(token)` → `(profile_name, agent_id)` or `None` if invalid/revoked
4. **Revoke**: `revoke_token(token)` → deletes from keyring

### One-to-One Binding

A profile can have only one active token. Attempting to assign a second token to a profile that already has one raises `ValueError`.

### Token Injection

`inject_token_into_tools(agent_path, token)` writes the token into the agent's `TOOLS.md`:

```markdown
## Environment Variables

The following environment variables are available:
- `TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4`: Your assigned profile token (do not modify)
```

If a token already exists, it is replaced. New sections are created if `## Environment Variables` does not exist. Write is atomic via temp file.

## Per-Profile Auth Store

`ProfileAuthManager` provides isolated credential storage per profile:

```python
auth = ProfileAuthManager(profile)

auth.set_credentials("kalshi", api_key, api_secret)    # Store
key, secret = auth.get_credentials("kalshi")            # Retrieve
auth.delete_credentials("kalshi")                       # Remove
auth.has_credentials("kalshi")                          # Boolean check
auth.list_services()                                    # All configured services
```

Keyring namespace: `traderbot.profiles.<profile_name>.<service>`

### Credential Resolution Chain

When resolving API credentials:

1. Profile-specific keyring (`traderbot.profiles.<name>.<service>`)
2. Global keyring (`traderbot.<service>`)
3. Environment variable

The resolution chain in `resolve_kalshi_credentials()` checks profile credentials first, then falls back to global AuthManager.

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
#   - demo_mode: bool
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
traderbot profile discover-agents [--json]           # Scan .openclaw/workspace/
```

## OpenClaw Agent Discovery

`discover_agents()` scans `~/.openclaw/workspace/` for agent directories and reads `IDENTITY.md` to extract agent metadata:

```python
agents = discover_agents()
# Returns: [{"agent_id": "...", "name": "...", "path": "..."}]
```

Supported IDENTITY.md fields: `**Agent ID**:` and `**Name**:`
