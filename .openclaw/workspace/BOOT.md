<!-- TRADERBOT_SYSADMIN_BOOT_START -->
<!-- ASK_THEN_MERGE -->
# BOOT.md - Sysadmin Boot Sequence

Run `traderbot --version` on startup to verify the CLI is available.
If the command fails, notify the user: "TraderBot CLI not found. Run: uv pip install -e ."
Then reply with NO_REPLY.

## Full Boot Sequence

After confirming the CLI is available, run the following checks in order to establish full fleet and system status:

### 1. Fleet Inventory
- Run `traderbot profile assignments --json` to list all profile→agent mappings
- Read `SESSION-STATE.md` → compare registered agents against profile assignments
- Note any agents registered in SESSION-STATE but missing from profile assignments (stale entries)
- Note any assigned profiles that aren't registered in SESSION-STATE (new agents to register)

### 2. Circuit Breaker Status
- Run `traderbot halt --json` to check global circuit breaker state (OK, SLOW, HALT, FULL_STOP)
- If any circuit breaker is HALT or FULL_STOP, investigate and surface alert to main session with level and daily loss %

### 3. Agent Health Overview
- For EACH agent registered in `SESSION-STATE.md`:
  - Check its `HEARTBEAT_DATA.md` at `agents/<category>/HEARTBEAT_DATA.md` (if it exists)
  - Note last heartbeat timestamp, circuit breaker level, and any open alerts
  - Read `agents/<category>/SESSION-STATE.md` (if it exists) for active positions and pending actions

### 4. System Health
- Run `traderbot heartbeat --json` to run the 7-step review from the sysadmin perspective
- Read `HEARTBEAT_DATA.md` to check API and DB status

### 5. Learnings & Errors
- Run `traderbot learnings list --json` to check for PENDING_REVIEW entries across all agents
- Read `.learnings/ERRORS.md` to check for unresolved errors from last session

### 6. Test Lab
- Check `test-lab/backlog.md` for any pending experiments
- Note any completed tests that need review or results to summarize

### 7. News & High-Impact Events
- Run `traderbot news-summary --signals --json` to check for high-impact news
- If any signal impact score > 0.7, note it for the fleet status report

## Boot Complete

After all checks, output a summary:

```
BOOT COMPLETE
- CLI: vX.XX.XX
- Circuit Breaker: <state> (fleet-wide)
- Active Agents: N registered, N with heartbeats
- System: API <status>, DB <status>
- Pending Reviews: N
- Pending Tests: N
- High-Impact Signals: N
```

If the fleet circuit breaker is HALT or FULL_STOP, include that alert in the summary and proceed with caution — investigate root cause before any new agent actions.

If no agents are registered in SESSION-STATE.md, note: "No agents registered. Awaiting agent fleet deployment or profile assignments."
