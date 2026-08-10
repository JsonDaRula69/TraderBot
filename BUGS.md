# BUGS

Known bugs and pre-existing failures, documented as discovered. Each entry
records the symptom, the root cause, and whether it is fixed or still open.

## Open

### QA test failures when `TRADERBOT_USE_HARDCODED_AUTH=0` (macpro-linux)

**Status**: Pre-existing, environment-dependent. Not caused by Phase 3.

**Symptom**: 7 tests fail on macpro-linux (where
`TRADERBOT_USE_HARDCODED_AUTH=0` is set) but pass locally:

- `tests/test_market_prices_tool.py` (4): `test_market_prices_returns_cached_ticker`,
  `test_market_prices_uncached_ticker_returns_error`,
  `test_market_prices_no_daemon_returns_error`,
  `test_market_prices_missing_ticker_rejected`
- `tests/test_daemon_status.py` (2): `test_health_reports_component_status[daemon]`,
  `test_health_reports_component_status[stdio-degraded]`
- `tests/test_daemon_mcp_integration.py` (1): `test_daemon_serves_mcp_over_streamable_http`

**Root cause**: These tests call MCP tools with the Phase 0 hardcoded tokens
(`weather-test-token`, `sysadmin-test-token`). When
`TRADERBOT_USE_HARDCODED_AUTH=0`, `resolve_token_adapter()` in
`src/traderbot/mcp/resolver.py` switches to real auth, which cannot resolve the
hardcoded tokens. `_check_permissions()` in `src/traderbot/mcp/tools.py` then
returns `{"error": "Invalid or expired profile token"}` — a dict with no
`status` key. The tests assert `result["status"] == "ok"` / `"error"` and raise
`KeyError: 'status'`.

**Why pre-existing**: The identical resolver/tools behavior exists at the
pre-Phase-3 commit `2496aa4` (verified via `git show`). The tests were added in
Phase 2 (`88cc3f8`) and never guarded against the real-auth environment. The
failures are a test/environment mismatch, not a Phase 3 regression.

**Reproduction**:
```bash
TRADERBOT_USE_HARDCODED_AUTH=0 uv run pytest \
  tests/test_market_prices_tool.py tests/test_daemon_status.py \
  tests/test_daemon_mcp_integration.py -q
```

**Fix options** (not applied here — out of scope for the QA gate fix):
1. Set `TRADERBOT_USE_HARDCODED_AUTH=1` (or unset) when running the suite on
   macpro-linux, matching the local default.
2. Add a fixture that pins the hardcoded-auth env for these tests.
3. Make `_check_permissions` return a consistent error shape including a
   `status` key, and update the tests to assert on it.
