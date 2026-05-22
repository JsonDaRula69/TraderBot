# Security

This document covers the threat model for multi-agent deployment, the security properties of the token handshake system, encryption mechanisms, and the enforcement layers that prevent agents from exceeding their granted capabilities.

## Threat Model

Multi-agent deployment introduces new attack surfaces that do not exist in single-agent setups:

| Threat | Description | Mitigation |
|---|---|---|
| **Token theft** | Malicious actor reads token from TOOLS.md or environment | Token is 72-bit entropy, keyring-first storage (OS-encrypted) |
| **Token guessing** | Offline brute force of token values | `secrets.token_urlsafe(9)` provides ~72 bits of entropy |
| **Profile hijacking** | Agent attempts to modify its own profile | Profile stored in `.env` file agent cannot modify at runtime |
| **Risk limit override** | Agent attempts to set aggressive risk parameters | HARD_LIMITS ceiling enforcement at profile creation + at runtime |
| **Credential theft** | Agent reads another profile's API keys | Keyring namespace isolation; profiles scoped to `traderbot.profiles.{name}.*` |
| **Data isolation breach** | Agent reads another agent's SQLite/ChromaDB | Separate base directories per profile (`~/.traderbot/{mode}-{name}/`) |
| **Token re-use** | Revoked token still resolves | `revoke_token()` removes token from registry; resolution fails immediately |
| **Category filter bypass** | Agent attempts to trade disabled market categories | Category check in `evaluate_trade()` before any sizing |

## Token Handshake Security

### Entropy

Tokens are generated with:

```python
secrets.token_urlsafe(9)[:12]
```

This provides approximately 72 bits of entropy (9 bytes × 8/6 URL-safe encoding ≈ 72 bits). At 1 million guesses per second, brute-forcing takes roughly 300,000 years.

### Storage

Tokens are stored in the `.env` file alongside other configuration. The agent process receives the token via the `TRADERBOT_PROFILE_TOKEN` environment variable at startup and cannot modify the file at runtime.

### Resolution

`resolve_token(token)` returns `(profile_name, agent_id)` or `None`. Revocation is immediate — the token entry is removed from the registry and subsequent resolution attempts return `None`.

### One-to-One Binding

Each profile can have only one active token. Attempting to assign a second token raises `ValueError`. This prevents a scenario where an agent is assigned a profile that already has a token from a previous agent.

## Credential Storage

TraderBot uses OS-native keyring as the primary credential store, with `.env` file fallback when keyring is unavailable.

### OS Keyring (Primary)

When `keyring` is installed and a backend is available, credentials are stored in OS-encrypted storage:

| OS | Backend | Storage Location |
|---|---|---|
| **macOS** | Keychain | `login` keychain, encrypted with user password |
| **Windows** | Credential Locker | Windows Credential Manager |
| **Linux** | Secret Service | GNOME Keyring / KDE Wallet (requires D-Bus) |

The `keyring` Python package (`>=25.0`) auto-detects the OS backend. If no backend is available (headless Linux without D-Bus, CI environments), TraderBot falls back to `.env`.

### .env File (Fallback)

When keyring is unavailable, credentials fall back to the `.env` file:

- **Location**: `~/.traderbot/.env` with mode 0600 (owner read/write only)
- **API keys**: `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PEM` stored as plain text
- **Profile tokens**: `TRADERBOT_PROFILE_TOKEN` injected at agent startup

The `.env` file serves as the fallback when keyring is unavailable. All profiles share the same API keys when using `.env` — per-profile credential isolation requires keyring.

### .env File Format

```bash
KALSHI_API_KEY=your_key_id
KALSHI_PRIVATE_KEY_PEM=-----BEGIN RSA PRIVATE KEY-----
KALSHI_RATE_LIMIT_RPS=20
TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4
```

### Resolution Order

`AuthManager.get_credential()` resolves credentials in this order:

1. **OS keyring** — `traderbot.{service}` namespace (e.g., `traderbot.kalshi` → username `api_key`)
2. **Environment variables** — process environment (`KALSHI_API_KEY`, etc.)
3. **.env file** — `~/.traderbot/.env`

`ProfileAuthStore.get_credentials()` resolves per-profile credentials:

1. **Profile keyring** — `traderbot.profiles.{name}.{service}` namespace
2. **Profile env vars** — `KALSHI_API_KEY_PROFILE_{NAME}`, etc.
3. **Profile .env entries** — same keys in `~/.traderbot/.env`

Keyring entries always take precedence. This ensures that when a profile has keyring-stored credentials, they cannot be overridden by environment variable injection.

### Migration

Use `AuthManager.migrate_to_keyring()` to move credentials from `.env` to OS keyring:

```python
mgr = AuthManager()
result = mgr.migrate_to_keyring()  # All services
result = mgr.migrate_to_keyring("kalshi")  # Single service
# Returns {"migrated": N, "skipped": M}
```

All credential fields in Pydantic models use `SecretStr` to prevent accidental logging of secrets.

## Enforcement Layers

### Layer 1: Profile Creation Validation

At `TradingProfile` creation, a model validator checks all risk parameters against `HARD_LIMITS` ceilings:

```python
if self.max_position_per_market_pct > HARD_LIMITS["max_position_per_market_pct"]:
    raise ValueError("max_position_per_market_pct exceeds HARD_LIMITS ceiling")
```

An agent cannot create a profile with parameters that exceed the hard limits.

### Layer 2: AgentRiskLimits Ceiling

At runtime, `AgentRiskLimits` enforces the ceiling again:

```python
max_position_pct = min(
    self._profile.max_position_per_market_pct,
    float(HARD_LIMITS["max_position_per_market_pct"]),
)
```

The profile parameter and the ceiling are compared, and the more restrictive value wins. This handles cases where a profile was created with parameters at the ceiling, then `HARD_LIMITS` was tightened by a human.

### Layer 3: Category Filter

In `evaluate_trade()`, before any risk math:

```python
if not profile.is_category_enabled(trade_request.market_category):
    return 0
```

If the market's category is not in `enabled_categories`, the trade is rejected. This filter is applied before position sizing, so no amount of position size adjustment can bypass it.

### Layer 4: Immutable Token Binding

Tokens are generated by the CLI and stored by TraderBot. The agent cannot:
- Generate its own token
- Modify an existing token
- Assign itself to a profile without CLI intervention

The agent receives a token via TOOLS.md injection. It cannot change the token value at runtime.

### Layer 5: Data Isolation

Each profile has isolated data directories under `~/.traderbot/{mode}-{name}/`:

- Paper agent: `~/.traderbot/paper-weather-agent/`
- Live agent: `~/.traderbot/live-portfolio/`

An agent running with one profile token cannot access another profile's SQLite database or ChromaDB vectors (different base directories). The isolation is at the filesystem level (enforced by the OS and file permissions).

## What Agents Cannot Do

These restrictions are enforced by the system and cannot be bypassed by the agent:

1. **Cannot modify profile parameters** — Profiles are stored via env and managed only via CLI
2. **Cannot exceed HARD_LIMITS** — Even with a custom profile, `AgentRiskLimits` ceiling enforcement prevents exceeding hard limits
3. **Cannot read another profile's credentials** — Keyring namespace isolation: profile credentials stored in `traderbot.profiles.{name}.*`, global credentials in `traderbot.{service}`
4. **Cannot use revoked tokens** — `revoke_token()` removes the token entry immediately
5. **Cannot bypass category filtering** — Category check is in the risk gate before sizing
6. **Cannot access another profile's data** — Separate SQLite and ChromaDB directories per profile (`~/.traderbot/{mode}-{name}/`)
7. **Cannot self-assign a token** — Token generation requires CLI invocation by a human
8. **Cannot increase position size beyond profile limits** — Sized position is capped by the effective limit

## Keyring Namespace Map

| Namespace | Access | Contents |
|---|---|---|
| `traderbot.{service}` | Agent-readable | Global service credentials (e.g., `traderbot.kalshi` → username `api_key`, `private_key_pem`) |
| `traderbot.profiles.{name}.{service}` | TraderBot-only | Per-profile credentials (e.g., `traderbot.profiles.weather-agent.kalshi`) |

All keyring entries use the key name as the username field (e.g., `api_key`, `private_key_pem`, `client_id`). The `keyring` package handles OS-specific encryption automatically.

The agent can read the `traderbot.*` namespace for credential lookup via `AuthManager`. Per-profile namespaces (`traderbot.profiles.*`) are resolved by `ProfileAuthStore` — the agent process does not directly access these, they are resolved by the TraderBot runtime.
