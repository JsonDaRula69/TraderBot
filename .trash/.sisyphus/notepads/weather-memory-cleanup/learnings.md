## MEMORY.md cleanup (2026-05-12)

- Remote file: `/home/jsondarula/.openclaw/workspace/weather/MEMORY.md`
- Lines 41-42 were already in the expected cleaned state — no changes needed
- The "CLI Trade Blocker" bullet was already absent — no removal needed
- Line 45 (`- **Profile config**:...`) had a stale `**REGRESSION**: v0.10.178 raised floor back to 1000, blocking the profile update.` suffix — removed it via Python inline edit
- Remote host is Linux (Ubuntu 6.8 kernel, GNU sed) — use `sed -i` (no space) or Python for reliable edits
- Verification shows zero CLI Trade Blocker references, zero min_liquidity.*FR-001 matches, clean FR-004 and Profile config lines
