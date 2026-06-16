#!/usr/bin/env bash
# Seed Loreguard with existing Traderbot design decisions.
# This is the preloading pipeline from Tier 2 of the knowledge architecture.
# Run: bash .autodev/scripts/seed-loreguard.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DECISIONS_DIR="$REPO_ROOT/.autodev/decisions"
LOREGUARD_SYNC="$REPO_ROOT/.loreguard"

echo "=== Loreguard Preloading Pipeline ==="
echo ""

# 1. Check for ADRs to import
if [ ! -d "$DECISIONS_DIR" ] || [ -z "$(ls -A "$DECISIONS_DIR" 2>/dev/null)" ]; then
  echo "No ADRs found in .autodev/decisions/."
  echo "Create ADRs first (see template below), then re-run this script."
  echo ""
  echo "ADR template:"
  echo "---"
  cat << 'ADR_TEMPLATE'
# ADR-NNN: Title

**Status:** Proposed
**Date:** YYYY-MM-DD
**Source:** <URL or document reference>
**Tags:** kalshi, trading, architecture

## Context
<!-- What is the issue that motivates this decision? -->

## Decision
<!-- What is the change that we're proposing/making? -->

## Consequences
<!-- What becomes easier or harder to do because of this change? -->
ADR_TEMPLATE
  exit 0
fi

# 2. Import each ADR into Loreguard as a draft
echo "Importing ADRs into Loreguard..."
for adr in "$DECISIONS_DIR"/ADR-*.md; do
  [ -f "$adr" ] || continue
  basename=$(basename "$adr")
  title=$(head -1 "$adr" | sed 's/^# //')
  summary=$(grep -A2 "## Decision" "$adr" 2>/dev/null | tail -1 | head -c 800 || echo "See $basename")
  tags=$(grep -oP '(?<=\*\*Tags:\*\*).*' "$adr" 2>/dev/null | tr -d ' ' | tr ',' ' ' || echo "")
  source=$(grep -oP '(?<=\*\*Source:\*\*).*' "$adr" 2>/dev/null | tr -d ' ' || echo "")

  # Convert ADR to Loreguard sync format
  slug=$(echo "$basename" | sed 's/\.md$//')
  lore_file="$LOREGUARD_SYNC/${slug}.md"
  
  cat > "$lore_file" << EOF
# ${title}

status: draft
confidence: medium
source: ${source:-ADR}
tags: ${tags}

${summary}

---

$(cat "$adr")
EOF

  echo "  Imported: $basename → .loreguard/${slug}.md"
done

# 3. Sync into Loreguard DB
echo ""
echo "Syncing into Loreguard database..."
cd "$REPO_ROOT"
loreguard sync import .loreguard/
echo "Done."

# 4. Remind about ratification
echo ""
echo "=== Next Step: Ratification ==="
echo "All imported records are DRAFTS — hidden from agent search until approved."
echo "Run: loreguard review"
echo "Approve each record to make it visible to AutoDev agents."
