# Learnings — prod-data-local-sim

## 2025-05-13: provider.py foundation (T5)

- Project uses `uv run python -m pytest` for running tests (not bare `python` or `python3`)
- `from __future__ import annotations` throughout — enables PEP 563 deferred evaluation, so `datetime` can go in TYPE_CHECKING
- Existing models use Pydantic `BaseModel` with `ConfigDict(strict=True, extra="forbid")`; new snapshot types use `@dataclass(frozen=True)` instead (lightweight, no validation needed)
- `pytest-asyncio` in AUTO mode — async test methods just work with `async def test_...`
- All monetary values in cents as `int`, never `float` (project-wide constraint)
- `OrderBookLevel` in models.py uses `price`/`size` int fields; snapshot mirrors this as `price_cents`/`size`
- Test files use `from __future__ import annotations` and import from `traderbot.kalshi.*`
- Ruff enforced: TC003 (move stdlib type imports to TYPE_CHECKING), W292 (missing newline at EOF)