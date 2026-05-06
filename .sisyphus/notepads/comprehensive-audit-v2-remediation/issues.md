# Issues — Comprehensive Audit V2 Remediation

## FIXED
- [x] All previous issues resolved
- [x] NewsAPI compliance: added country="us" to top-headlines, removed incorrect sources/language exclusion, documented rate-limit headers, fixed env var naming
- [x] docs/kalshi.md: rate limit tiers, V2 endpoint paths, V2 order body example

## KALSHI V2 API AUDIT FINDINGS (2026-05-06)

### Critical — to be fixed

1. **OrderRequest.to_v2_body() field names wrong**: sends `count_fp`/`price_dollars` but CreateOrderV2Request uses `count`/`price`
2. **Missing required V2 fields**: `time_in_force` (fill_or_kill|good_till_canceled|immediate_or_cancel) and `self_trade_prevention_type` (taker_at_cross|maker)
3. **place_order can't parse real V2 response**: CreateOrderV2Response has {order_id, fill_count, remaining_count, ts_ms} — no ticker, side, price, status, created_time
4. **cancel_order parses nonexistent status field**: CancelOrderV2Response has no `status`
5. **get_order/list_orders use undocumented paths**: /portfolio/events/orders (GET) not in spec; should be /portfolio/orders
6. **_parse_order mismaps legacy fields**: expects price_dollars but legacy Order uses yes_price_dollars/no_price_dollars

### Test impact
- tests/test_trading.py mocks fake responses that don't match real V2 API
- tests/test_client.py tests legacy /portfolio/orders endpoint

## PRE-EXISTING (not in scope)
- Ruff warnings (RUF046, F841, TC001, TC003) — pre-existing style issues
- test_cron_setup_no_openclaw_shows_fallback — OpenClaw CLI not in PATH
- simulation engine ↔ profiles circular import
- paper_trader unrealized vs realized loss
