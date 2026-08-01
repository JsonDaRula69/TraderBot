# Problems — News Data Sources

## F4: Scope Fidelity Check Findings

### CRITICAL: mentions-test.txt contains secrets

- **File**: `mentions-test.txt` (untracked, in repo root)
- **Contents**: Contains a Kalshi API key and an RSA private key in plaintext
- **Risk**: If committed, this leaks credentials. Per AGENTS.md: "Never commit .env, credentials, or API keys"
- **Action needed**: Delete this file immediately and rotate the exposed Kalshi API key + RSA key
- **Status**: UNRESOLVED

### MINOR: test_cli.py changes are consequential, not in plan spec

- The plan (T12) specifies changes to `src/traderbot/cli.py` but doesn't explicitly call out `tests/test_cli.py`
- The changes are legitimate: the `news` command behavior changed (no-key sources return empty instead of error), so the existing tests needed adaptation
- **Verdict**: Acceptable consequential change, not scope creep

### INFO: uv.lock updated (80 lines)

- `pyproject.toml` added `[news-extras]` optional dep group with `pytrends>=4.9.2`
- `uv.lock` auto-updated to reflect this new dependency
- **Verdict**: Expected; lockfile updates are a natural consequence of pyproject.toml changes