
## 2026-05-05: V2 Endpoint Path Remediation — Task Complete

### Changes Made
- `src/traderbot/kalshi/trading.py:30`: `/portfolio/orders` → `/portfolio/events/orders` (place_order)
- `src/traderbot/kalshi/trading.py:38`: `/portfolio/orders/{order_id}` → `/portfolio/events/orders/{order_id}` (cancel_order)
- `src/traderbot/kalshi/websocket.py:14-21`: Removed inaccurate `# V1 channels` / `# V2 channels` grouping; all channels are V2-compatible on the wss:// v2 endpoint
- `tests/test_trading.py`: Updated mock URL expectations to match new V2 paths

### Verification
- All 38 targeted tests pass (17 trading + 21 websocket)
- Zero occurrences of `/portfolio/orders` without `/events/` in trading.py
- `get_order()` (line 48) and `list_orders()` (line 60) already used correct V2 paths — untouched per instructions

### Pre-existing Issue Noted
- `models.py` has staged changes that include a refactored `OrderRequest` class (count/price as str, count_fp/price_dollars in to_v2_body). This was already in the working tree before this task and is compatible with the updated endpoint paths.

### Ruff
- One pre-existing RUF046 on `int(round(...))` in trading.py — not introduced by this change.

## 2026-05-05: V1 API Fallback Removal — Task Complete

### Changes Made
- `src/traderbot/kalshi/trading.py:_parse_order()`: Removed V1 `yes_price`/`price` fallback for price resolution — now uses only `price_dollars`/`price_fp`. Removed V1 `count`/`quantity` fallback for quantity — now uses only `count_fp`. Fixed RUF046 ruff warning by removing redundant `int()` cast on `round()`.
- `src/traderbot/kalshi/models.py:OrderSide`: Simplified docstring from V1/V2 mapping reference to `"Internal yes/no side representation."`
- `src/traderbot/kalshi/models.py:OrderRequest`: Removed `no_price: str | None = None` field (V1 remnant not in V2 API)
- `src/traderbot/kalshi/models.py:OrderRequest.to_v2_body()`: Removed `no_price` conditional inclusion in body dict
- `tests/test_trading.py`: Updated `SAMPLE_ORDER_RAW` to use V2-only fields (removed `quantity` and `price` V1 fields). Updated `order_raw_2` test fixture to use V2 fields (`price_dollars`, `count_fp`, `side: "ask"` instead of V1 `no`). Added `assert "no_price" not in body` to `test_to_v2_body_maps_fields`.

### Verification
- All 17 trading tests pass
- Ruff check passes on all 3 changed files
- LSP diagnostics: 0 errors on all files
- `OrderType.market` kept — valid V2 value
- `OrderStatus.matched` kept — valid V2 value (docstring notes it maps to `filled`)
- Pre-existing: `test_models.py::TestMarket::test_valid` fails due to `CRYPTO` category removal (separate task)

## Task 2: V1 API Fallback Removal (2026-05-05)

- `portfolio.py:get_settlements()` had 4 V1 fallback blocks (price, settlement_price, pnl, count). Removed all `else` branches, simplified to V2-only: `_to_cents(raw.get("price_dollars") or raw.get("price_fp") or 0)` pattern.
- `_normalize.py:_normalize_trade()` had 2 V1 fallback blocks (price, count). Same simplification.
- Preserved `except Exception: continue` defensive handler in `get_settlements()`.
- The `from __future__ import annotations` and `TYPE_CHECKING` guard for `KalshiClient` import must be preserved in `portfolio.py` — removing it causes circular import via `kalshi/__init__.py`.
- Pre-existing RUF046 ruff warning in `_to_cents()` (not modified by this task).

## Issues

- Pre-existing circular import if `TYPE_CHECKING` guard is removed from portfolio.py (kalshi/__init__.py imports TradingService which imports models).
- Pre-existing `onnxruntime` wheel incompatibility on macOS x86_64 — need `.venv-test` with Python 3.12 for testing.
## Wave 2 — NewsAPI Security Fix (2026-05-05)

### Pattern: Migrating API key from query params to headers
- Use `headers={"X-Api-Key": key}` on `httpx.AsyncClient.get()` and move non-auth params to separate `params` dict
- Must update ALL `_client.get` calls — there were two in `get_everything` that matched the old pattern
- The existing `self.rate_limit_remaining` check (server-reported) is separate from the new `_daily_request_count` (client-side counter); the former is opportunistic, the latter is guaranteed enforcement

### Pattern: Permanent auth error handling
- 401 must short-circuit BEFORE the generic `status_code != 200` check — otherwise it falls through to the catch-all `NewsAPIError`
- 401 should NOT retry (unlike 429 and httpx.HTTPError) — just raise immediately with a distinct exception type

### Gotcha: Multiple matches in edit tool
- `edit` finds ALL occurrences of oldString; when `_client.get` appears in multiple methods, must include surrounding context (the 429 check block) to disambiguate
