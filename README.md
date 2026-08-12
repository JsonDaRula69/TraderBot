# TraderBot

Autonomous prediction-market trading toolkit for OpenClaw agents. v2 is
MCP-based (DD-015): TraderBot registers as an MCP server with OpenClaw, and
agents drive it through typed MCP tools (`traderbot__*`). The CLI is retired
from containers.

> **Status**: v2 Phase 2 (issue #166) is implemented. TraderBot now runs as an
> always-on daemon: the Kalshi WebSocket stream, the scheduled data pipeline
> (weather 1h, news stub 30m, settlement 1h), and the MCP server all run in one
> process, serving MCP over streamable-http on loopback (`127.0.0.1:8765/mcp`).
> The MCP layer exposes 5 tools (`health`, `auth_check`, `profile_list`,
> `market_edge`, `market_prices`) with WS-first market data, profile-token
> resolution, tool-permission checks, and DD-011 category enforcement. On-target
> macpro-linux QA (24h uptime, WS reconnect, live E2E) was in progress; Phase 3
> items (ChromaDB, GRIB2 multi-day forecasts, crypto/sports workers, three-mode
> trading engine) remain on the roadmap.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pipx).

```bash
git clone git@github.com:JsonDaRula69/TraderBot.git
cd TraderBot
uv sync                      # install deps + project (editable)
uv run traderbot daemon      # start the always-on daemon (WS + workers + MCP)
```

The daemon serves MCP over streamable-http at `http://127.0.0.1:8765/mcp`
(loopback only). OpenClaw connects with `transport: "streamable-http"`; the
legacy stdio entry point (`uv run traderbot-mcp-server`) remains available as a
development fallback. For an installed background service on Linux/macOS/Windows
use the `traderbot` CLI:

```bash
traderbot service install   # write the unit + enable + start (sudo on systemd)
traderbot service status
traderbot service uninstall
```

`auth_check` validates the supplied profile token and reports the resolved
profile, agent, mode, enabled categories, and permissions. It does not inspect
Kalshi or other external provider credentials; those checks are deferred to
the secrets/provider/deploy phases.

For real auth, set `TRADERBOT_USE_HARDCODED_AUTH=0`. The deploy wizard and
daemon use the unified `SecretsStore` facade: Infisical is primary and the
machine-bound encrypted local store is the fallback. `LocalTokenStore` remains
a compatibility/test seam, not the deploy persistence path. The Phase 0
hardcoded development mapping remains active unless the environment variable
is exactly `0`.

`traderbot deploy` runs all eight wizard steps. It inventories all
OpenClaw workspace ownership before mutation, adopts existing selected paths,
and requires explicit paths and approval flags for missing selected agents.
Approved dormant heartbeat state is written as `0m` through OpenClaw config;
bootstrap automation is requested from Gateway only after selected state is
verified. It then reuses or securely collects only the canonical Kalshi secret
pair, falling back to machine-bound encrypted storage when local Infisical is
unusable, and provisions selected category databases plus a lazy embedded
Chroma root in daemon ownership order. Step 6 reuses the standalone typed
backfill runtime, Step 7 is an intentional read-only Phase 5 sandbox stub, and
Step 8 reuses the verification graph. No simulation, trading, or scheduling
mutation occurs in Step 7.

Historical data can be populated independently with `traderbot backfill --months 6`.
Use `--collector-db PATH` to import an explicit legacy collector and `--json` for
one machine-readable result line. The command imports weather data read-only and
fetches both current and archived Kalshi weather history; the deploy wizard
composes the same request and dependency boundary.

Per-agent configuration lives under `configs/openclaw/` with restrictive
per-agent `allow`/`deny` policies. Secure per-agent profile-token delivery is
handled by the `traderbot-token-injector` plugin (a `before_tool_call` hook,
transport-agnostic) resolving Infisical-stored tokens; the MCP server fails
closed when a call has no valid token. With Phase 2, OpenClaw connects to the
daemon over streamable-http at `http://127.0.0.1:8765/mcp` (see
`main/configs/openclaw/with-plugin.json`).

## Architecture

| Doc | Purpose |
|---|---|
| `v2roadmap.md` | Design decisions (DD-001..DD-038) and phase tracking |
| `v2docs/00-10*.md` | Derived design docs (architecture, security, MCP tools, ...) |

Key decisions: DD-011 (category enforcement), DD-015 (MCP server), DD-016
(always-on service), and DD-025 (explicit profile-token authentication).

## Development

```bash
uv run pytest tests/                           # test suite
uvx --with ruff ruff check src/ tests/         # lint
uvx --with ruff ruff format src/traderbot      # format
uv build                                       # build wheel
```

## License

MIT
MIT
