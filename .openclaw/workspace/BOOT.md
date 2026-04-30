# BOOT.md

Run on every Gateway restart. Keep checks short and actionable.

1. Verify Kalshi API connection: `traderbot scan --json` — confirm response is valid.
2. Check for missed heartbeat runs: read `HEARTBEAT_DATA.md` timestamp. If stale (>6h old), flag it.
3. Reconcile open positions: `traderbot positions --json` — confirm no orphaned positions from downtime.
4. Check circuit breaker state: `traderbot halt` — if SLOW or worse, alert the human immediately.
5. Confirm update check: if auto-updates are enabled, verify `~/.traderbot/update_config.json` exists and is valid.

If any check fails or needs human attention, send an alert via the configured notification channel. If all checks pass, reply with `NO_REPLY`.