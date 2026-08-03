# TraderBot

Autonomous prediction-market trading toolkit for OpenClaw agents. v2 is
MCP-based (DD-015): TraderBot registers as an MCP server with OpenClaw, and
agents drive it through typed MCP tools (`traderbot__*`). The CLI is retired
from containers.

> **Status**: v2 Phase 1 is in development. Profile-token resolution,
> tool-permission checks, DD-011 category enforcement, hardened local token
> persistence, strict MCP input validation, and real-auth MCP transport tests
> are implemented and locally verified. This is not a deployable release:
> external provider credentials are not validated, secure per-agent token
> injection through OpenClaw is blocked, and macpro-linux testing is still
> pending. Issue #164 remains open.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pipx).

```bash
git clone git@github.com:JsonDaRula69/TraderBot.git
cd TraderBot
uv sync                      # install deps + project (editable)
uv run traderbot-mcp-server  # start the MCP server (stdio)
```

The server exposes 4 tools in the current Phase 1 development build: `health`,
`auth_check`, `profile_list`, and `market_edge`. OpenClaw namespaces them as
`traderbot__health`, `traderbot__auth_check`, etc.

`auth_check` validates the supplied profile token and reports the resolved
profile, agent, mode, enabled categories, and permissions. It does not inspect
Kalshi or other external provider credentials; those checks are deferred to
the secrets/provider/deploy phases.

For real auth, set `TRADERBOT_USE_HARDCODED_AUTH=0`. The current local backend
is `LocalTokenStore`, which can store generated 256-bit profile tokens in
`~/.traderbot/tokens.json` with mode `0600` on POSIX. The default remains the
Phase 0 hardcoded development mapping unless the environment variable is
exactly `0`.

The Phase 1 configuration remediation under `configs/openclaw/` registers TraderBot at root scope and applies restrictive per-agent `allow`/`deny` policies. The remediation fragments remove the legacy unsupported per-agent `env` and nested `mcp` fields but still cannot provide distinct per-agent profile tokens because root and MCP-server environment values are shared.
Secure token delivery therefore requires either an OpenClaw proxy/plugin that
injects caller identity or tokens, or isolated gateway/MCP instances per agent.
Do not treat the config state as deployable until that architecture is selected and tested on macpro-linux.

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
