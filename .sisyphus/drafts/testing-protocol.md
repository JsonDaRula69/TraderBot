# Draft: Comprehensive E2E Testing Protocol

## Requirements (confirmed)
- User wants to update tests/TESTING_PROMPT.md with a comprehensive end-to-end test framework
- Must test every module and every function line by line
- Must test installation flow, dependency checks, configuration (API keys, OpenClaw)
- Must verify secret storage security
- Must verify agent tool calls and decision-making analysis
- Must continuously reference docs/ as source of truth
- Must verify integrations are used to specification (Kalshi API, OpenClaw, security)
- Must verify OpenClaw agent files (Identity.md, Soul.md, Heartbeat.md, Agent.md) are correct
- Must verify no secrets are ever exposed in plain text
- Must verify highest security against hacking/jailbreaking
- Must test real-world context that the package and agent operate in
- Must be designed to be run repeatedly as development continues
- This is a documentation update plan ONLY

## Technical Decisions
- Current TESTING_PROMPT.md is already quite comprehensive (1156 lines)
- It covers Phases 0-5 of static analysis + unit tests + integration + property-based + execution
- It has §2.11-§2.14 for simulation, self-learning, news/sentiment, and adaptation tests
- It is missing: installation/config flow tests, OpenClaw integration verification, security/encryption deep audit, Kalshi API spec compliance, agent decision-making E2E, real-world context tests
- Version is now 0.08.01 (docs say Roadmap stops at Phase 6 complete, Phase 7/8 not started)
- All 8 phases need testing coverage regardless of implementation status

1. Kalshi demo API: **Real demo API calls** against demo-api.kalshi.co with real credentials for true E2E verification
2. OpenClaw integration: **Full gateway integration** — actually connect to OpenClaw gateway, test cron, heartbeat, session injection, skill execution
3. Telegram: **Full Telegram integration test** — end-to-end from Gateway → Telegram → Agent → TraderBot skill call → response
4. SecretStr: **P1 bug — must fix** — all credential fields must use `SecretStr` instead of plain `str`
5. Docs divergence: **Update TESTING_PROMPT to match code** — all built phases should be fully testable

## Research Findings

### Kalshi API Verification (from bg_215f0b3c)
- Authentication: RSA-PSS JWT signing required for all authenticated requests
  - Headers: `Authorization: Bearer <JWT>`, `X-Kalshi-Timestamp` (UTC nanoseconds), `X-Kalshi-Signature` (base64)
  - JWT contains `iss` (API key ID), `exp` (10-minute max TTL), body hash
  - Tokens are per-request, not session-based; no refresh mechanism needed
- All API endpoints should be validated against OpenAPI spec at docs.kalshi.com/openapi.yaml
- WebSocket: wss://api.kalshi.com/v2 with REST auth headers during handshake
  - Subscription channels: market-ticker, orderbook-updates, user-orders
  - Keep-alive: ping/pong every 30s
- Historical data: MUST fetch cutoff timestamps first via GET /historical/cutoffs
- Demo vs production: demo-api.kalshi.co vs api.kalshi.com; some endpoints restricted in demo
- Rate limits: ~10 req/sec; must handle 429 with backoff + retry (max 3x)
- Error body format: `{"error": "code", "message": "details"}`
- SDK: kalshi_python_async (async) and kalshi_python_sync; handles auth signing automatically

### Security Audit (from bg_6140d67a)
- Hardcoded API key in kalshi/client.py (TEST_API_KEY) — needs verification if test-only or risk
- SQLite DB files opened with `open(db_path, "w")` without permission constraints — world-readable
- os.getenv calls for secrets without keyring fallback in some paths
- No evidence of SecretStr usage for credential fields in Pydantic models — all use plain `str`
- Demo vs production endpoint selection needs proper isolation verification
- Audit trail: JSONL append-only but no tamper-evidence mechanism
- Input validation: need to verify SQL queries use parameterized statements
- .env.example present but need to verify .env is gitignored
- auth.py uses keyring but need to verify fallback paths are secure

### OpenClaw Agent Framework (from bg_6ff713fa)
- Agent workspace files are: AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, BOOTSTRAP.md, HEARTBEAT.md
  - TraderBot also has HEARTBEAT_DATA.md (data output, not instructions)
  - HEARTBEAT.md = agent instructions (checklist with tasks: blocks)
  - HEARTBEAT_DATA.md = data output from `traderbot heartbeat`
  - KEY DISTINCTION that must be tested
- Gateway injects workspace files into every session context
- Two cron architectures: `isolated agentTurn` (background autonomous) vs `systemEvent` (surfaces to main session)
- Heartbeat config: every: "30m", target: "last" | "none" | "<channel-id>"
- Skill system: SKILL.md with YAML frontmatter (name, description, metadata with env/bins/primaryEnv)
- Skills installed via `openclaw skills install <slug>` or manual clone to ~/.openclaw/skills/
- Session management: per-channel-peer DM scoping, idle resets, daily resets
- Telegram integration: channels.telegram config, acts as gateway mediator
- Cron payload format: `{sessionTarget: "isolated"|"main", payload: {kind: "agentTurn"|"systemEvent", message: "..."}}m`

## Open Questions
1. Should we test against the actual Kalshi demo API or mock everything?
2. How deep should OpenClaw integration testing go? (agent file format validation vs actual gateway connection)
3. What Telegram-specific testing should be included?
4. Should we add load/performance testing alongside E2E?
5. How should we handle testing Phase 7/8 components that aren't implemented yet?
6. The existing TESTING_PROMPT.md references "Phase 5 (not yet built)" and "Phase 7 (not yet built)" for simulation and news — but those ARE now built. How should we handle this doc-code divergence?
7. Security audit found plain `str` for credential fields instead of `SecretStr`. Is this an intentional design choice or a bug to fix?
8. The OpenClaw docs say workspace files include IDENTITY.md, SOUL.md, etc. — should our testing verify that our workspace files match the exact format OpenClaw expects?

## Scope Boundaries
- INCLUDE: All modules in src/traderbot/, all docs in docs/, all workspace files, all tests, all integrations
- INCLUDE: Installation flow, configuration, security, API compliance, agent behavior
- EXCLUDE: Actual live trading with real money (demo API only)
- EXCLUDE: Modifications to docs/ files (need explicit approval per AGENTS.md)