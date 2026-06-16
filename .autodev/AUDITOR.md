# AutoDev Auditor

Knowledge integrity checks that run automatically to keep the knowledge base trustworthy.

## Run Schedule

These checks run as part of the AutoDev heartbeat (every 5-10 minutes) and as a deeper sweep during the dream cycle (overnight).

## Checks

### 1. Bootstrap Size Gate

```bash
total=$(cat AGENTS.md .autodev/memory/projectbrief.md .autodev/memory/activeContext.md .autodev/memory/techContext.md 2>/dev/null | wc -c)
if [ "$total" -gt 4096 ]; then
  echo "FAIL: Bootstrap files total ${total} bytes (max 4096). Trim before committing."
fi
```

### 2. Lore Draft Queue Depth

```bash
drafts=$(loreguard review --list 2>/dev/null | grep -c "draft" || echo 0)
if [ "$drafts" -gt 20 ]; then
  echo "WARN: ${drafts} unreviewed lore drafts. Review queue is backing up."
fi
```

### 3. Stale Lore Detection

```bash
stale=$(loreguard search --include-stale tag:kalshi tag:trading tag:risk tag:pnl 2>/dev/null | grep -c "stale.*true" || echo 0)
if [ "$stale" -gt 0 ]; then
  echo "WARN: ${stale} stale lore records need verification."
fi
```

### 4. Conflict Queue

```bash
conflicts=$(loreguard search --include-drafts tag:conflict-report 2>/dev/null | wc -l || echo 0)
if [ "$conflicts" -gt 0 ]; then
  echo "ACTION: ${conflicts} unresolved lore conflicts need human review."
fi
```

### 5. Reference File Existence

```bash
for f in .autodev/reference/system-architecture.md .autodev/reference/kalshi/rest-api.md; do
  if [ ! -f "$f" ]; then
    echo "WARN: Missing reference file: ${f}"
  fi
done
```

### 6. Magic Context DB Health

```bash
npx @cortexkit/magic-context@latest doctor --harness opencode 2>&1 | grep -E "FAIL|WARN" || echo "OK"
```

### 7. AGENTS.md Contains Retrieval Rule

```bash
if ! grep -q "search_lore" AGENTS.md; then
  echo "FAIL: AGENTS.md missing the search_lore retrieval rule. Agents won't query lore."
fi
```
