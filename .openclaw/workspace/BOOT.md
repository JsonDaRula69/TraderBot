# BOOT.md

Run `traderbot --version` on startup to verify the CLI is available.
If the command fails, notify the user: "TraderBot CLI not found. Run: uv pip install -e /path/to/TraderBot_BOB"
Then reply with NO_REPLY.

## Full Boot Sequence

After confirming the CLI is available, run the following checks in order to establish full market and portfolio status:

### 1. Profile & Configuration
- Run `traderbot profile assignments --json` to list all profile→agent mappings
- If a profile is assigned to this agent, run `traderbot profile show <profile_name> --json` to display current parameters (risk multiplier, max position %, categories)
- If no profile is assigned, note: "No profile assigned. Running with HARD_LIMITS defaults."

### 2. Circuit Breaker Status
- Run `traderbot halt --json` to check current circuit breaker state (OK, SLOW, HALT, FULL_STOP)
- If state is HALT or FULL_STOP, do NOT attempt new trades. Surface alert to user immediately.

### 3. Portfolio & Position Status
- Run `traderbot positions --json` to list all current positions (ticker, side, quantity, avg price, P&L)
- Run `traderbot performance --json` to get trade count, total P&L, and win rate

### 4. Available Markets
- Run `traderbot scan --limit 50 --json` to discover currently open markets
- Note the available market tickers and their categories
- Cross-reference with enabled categories in the active profile (if any)

### 5. Session State
- Read `SESSION-STATE.md` to check:
  - Active positions listed
  - Pending actions (must be reconciled if any exist from a crashed session)
  - Tracked markets list
  - Last heartbeat timestamp

### 6. Heartbeat Data
- Read `HEARTBEAT_DATA.md` (if exists) to get the latest 7-step review output
- Note any open alerts or required actions

### 7. Learnings & Errors
- Run `traderbot learnings --json` to check for PENDING_REVIEW entries
- Read `.learnings/ERRORS.md` to check for unresolved errors from last session

### 8. News & Sentiment (if markets are tracked)
- If SESSION-STATE.md lists tracked markets, run `traderbot news --json` to fetch latest news
- For each tracked ticker, run `traderbot sentiment <TICKER> --json` to get current sentiment

## Boot Complete

After all checks, output a summary:

```
BOOT COMPLETE
- CLI: vX.XX.XX
- Profile: <name> (or HARD_LIMITS)
- Circuit Breaker: <state>
- Positions: N (P&L: $X.XX)
- Tracked Markets: <list>
- Pending Actions: N
- Last Heartbeat: <timestamp or Never>
- Pending Reviews: N
```

If circuit breaker is HALT/FULL_STOP or there are pending actions from a crashed session, reply with the summary and highlight the issue. Otherwise, proceed normally.
