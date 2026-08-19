# TraderBot

Autonomous prediction-market trading toolkit for OpenClaw agents. v2 is
MCP-based (DD-015): TraderBot registers as an MCP server with OpenClaw, and
agents drive it through typed MCP tools (`traderbot__*`). The CLI is retired
from containers.

> **Status**: v2 Phase 4 implementation Todos 1-13 for issue #168 are locally
> complete at `2.0.0a98`, subject to Atlas acceptance and Final Wave F1-F4.
> Todo 12 landed in local commit `498ddc1` at `2.0.0a97`: 917 full tests and
> 192 targeted deploy/backfill/verify tests passed, including isolated config-mode
> CLI and malformed-JSON coverage with no live service or default-state mutation.
> F3 on-target macpro-linux QA remains pending, so Phase 4 and issue #168 remain
> open. The branch is local-only and unpushed; no remote CI or publication is
> claimed.

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
OpenClaw workspace ownership before mutation and requires the pre-existing
`main` agent; deploy never creates `main`. Existing selected category paths are
adopted unchanged. A missing selected category agent may be created only with
an explicitly approved absolute workspace path. The stricter existing-agents-only
contract and per-agent paper/live, channel, and same-name Telegram requirements
are deferred to Phase 4b.
Approved dormant heartbeat state is written as `0m` through OpenClaw config;
bootstrap automation is requested from OpenClaw Gateway only after selected
state is verified. Gateway owns agent cron and heartbeat; the TraderBot daemon
owns provider and token schedules; MCP owns neither. Deploy then reuses or
securely collects only `kalshi_api_key` and `kalshi_private_key_pem`, using
Infisical as primary and machine-bound encrypted local storage as fallback.
One explicit data root and `production`/`demo` Kalshi environment propagate
through database creation, backfill, verification, and deploy state. Selected
category databases use `{mode}-{name}/db/decisions.db`; SysAdmin receives
read-only enumeration and no decisions database. Chroma collection creation is
lazy. Step 7 is a read-only Phase 5 sandbox stub: Phase 4 starts no Docker,
simulation, backtest, trading lifecycle, or scheduling mutation.

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
