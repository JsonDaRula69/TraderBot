# TraderBot

Autonomous prediction-market trading toolkit for OpenClaw agents. v2 is
MCP-based (DD-015): TraderBot registers as an MCP server with OpenClaw, and
agents drive it through typed MCP tools (`traderbot__*`). The CLI is retired
from containers.

> **Status**: v2 in development — Phase 0 (MCP server skeleton + hardcoded
> auth) is on `v2-main`. Phase 0 hardcoded tokens are for development only —
> **never run Phase 0 against live data** (see issue #163).

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pipx).

```bash
git clone git@github.com:JsonDaRula69/TraderBot.git
cd TraderBot
uv sync                      # install deps + project (editable)
uv run traderbot-mcp-server  # start the MCP server (stdio)
```

Register with OpenClaw:

```bash
openclaw mcp add traderbot -- uv run traderbot-mcp-server
```

The server exposes 4 tools (Phase 0): `health`, `auth_check`,
`profile_list`, `market_edge` — OpenClaw namespaces them as
`traderbot__health`, `traderbot__auth_check`, etc.

## Architecture

| Doc | Purpose |
|---|---|
| `v2roadmap.md` | Design decisions (DD-001..DD-038) and phase tracking |
| `v2docs/00-10*.md` | Derived design docs (architecture, security, MCP tools, ...) |

Key decisions: DD-015 (MCP server), DD-016 (always-on service), DD-025
(profile-based auth with the hardcoded Phase 0 swap).

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