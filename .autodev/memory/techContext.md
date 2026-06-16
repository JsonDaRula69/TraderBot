# TraderBot v2 — Technical Context

Full detail: `.autodev/reference/v2docs/`

## Module Map

`data/` (unified pipeline), `trading.py` (P&L, settlement, paper), `kalshi/` (WebSocket, REST, settlement), `mcp_server/` (auth, tools, routing), `analysis/` (portfolio, adaptation), `simulation/` (backtest engine), `secrets/` (Infisical, local), `cli/` (deploy, trade, profile).

## Key Patterns

- Per-agent per-mode SQLite, shared ChromaDB with category filtering
- WebSocket-first Kalshi (REST only for fallback/history)
- MCP tools route by profile token + mode on backend
- Docker sandbox mandatory for all category agents
- SysAdmin unsandboxed but denied trading tools (DD-036)

## AutoDev Stack

OpenCode + OmO (Team Mode), GLM 5.1 (orchestrator/planner/writer), Deepseek V4 Pro (reasoning/review), Deepseek V4 Flash (fast tasks).

## Model Routing

| Role | Model | Category |
|------|-------|----------|
| Triage/Orchestrate | GLM 5.1 | unspecified-high |
| Plan | GLM 5.1 | unspecified-high |
| Execute | Deepseek V4 Pro | deep |
| Review | Deepseek V4 Pro | ultrabrain |
| Deploy | GLM 5.1 | unspecified-high |
