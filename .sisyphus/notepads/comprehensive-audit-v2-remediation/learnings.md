
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

## Task 2: V1 API Fallback Removal (2026-05-05)

- `portfolio.py:get_settlements()` had 4 V1 fallback blocks (price, settlement_price, pnl, count). Removed all `else` branches, simplified to V2-only: `_to_cents(raw.get("price_dollars") or raw.get("price_fp") or 0)` pattern.
- `_normalize.py:_normalize_trade()` had 2 V1 fallback blocks (price, count). Same simplification.
- Preserved `except Exception: continue` defensive handler in `get_settlements()`.
- The `from __future__ import annotations` and `TYPE_CHECKING` guard for `KalshiClient` import must be preserved in `portfolio.py` — removing it causes circular import via `kalshi/__init__.py`.
- Pre-existing RUF046 ruff warning in `_to_cents()` (not modified by this task).

## Issues

- Pre-existing circular import if `TYPE_CHECKING` guard is removed from portfolio.py (kalshi/__init__.py imports TradingService which imports models).
- Pre-existing `onnxruntime` wheel incompatibility on macOS x86_64 — need `.venv-test` with Python 3.12 for testing.
