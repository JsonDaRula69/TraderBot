# T3 Learnings

## Patterns Followed
- `_fetch_coincap` modeled after `_fetch_coingecko` (lines ~840-980): same category filter pattern, same DataPoint construction with int cents
- Insertion point: right before `close()`, after the last existing `_fetch_*` method
- All monetary values as `int` cents via `int(round(float(val) * 100))`

## CoinCap API Details
- Base URL: `https://api.coincap.io/v2/assets`
- No API key required for free tier
- Response wraps data in `{"data": [...]}` 
- Field names: `priceUsd`, `marketCapUsd`, `volumeUsd24Hr`, `changePercent24Hr`, `vwap24Hr`
- No per-asset timestamp — used `datetime.now(tz=UTC)` instead

## Verification
- LSP diagnostics: clean (0 errors)
- Tests: 45 passed, 1 pre-existing failure (test_profile_assign_token — unrelated)
- Offline validation: signature correct, category filter short-circuit works
- Network test: DNS resolution failed for api.coincap.io from this environment — code correctly caught exception and returned []
