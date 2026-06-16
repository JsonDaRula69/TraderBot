#!/usr/bin/env bash
# End-to-end test: verify the full AutoDev pipeline works.
# Creates a test issue, expects AutoDev to pick it up, implement, and open a PR.
# Run: bash .autodev/scripts/test-e2e.sh
set -euo pipefail

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || "")
if [ -z "$REPO" ]; then
  echo "ERROR: Not in a GitHub repo. Run this from the Traderbot repo root."
  exit 1
fi

echo "=== AutoDev End-to-End Test ==="
echo ""

# 1. Create a test issue
echo "1. Creating test issue..."
ISSUE_URL=$(gh issue create \
  --title "autodev-test: Add a hello endpoint to the health check" \
  --body '## Autodev Request

**Source:** e2e-test
**Priority:** low
**Type:** feature

### Description
Add a simple `/hello` endpoint to the health check module that returns `{"status": "ok"}`. This is a test issue to verify the AutoDev pipeline works end-to-end.

### Acceptance Criteria
- [ ] A `/hello` endpoint exists
- [ ] It returns `{"status": "ok"}`
- [ ] A test verifies the endpoint works

### Constraints
This is a test issue. Do not modify any existing endpoints.' \
  --label "autodev-request" \
  --label "priority:low" \
  --label "type:feature" \
  2>&1)
ISSUE_NUMBER=$(echo "$ISSUE_URL" | grep -oE '[0-9]+$')
echo "   Created issue #$ISSUE_NUMBER"
echo "   URL: $ISSUE_URL"

# 2. Verify labels were applied
echo "2. Verifying labels..."
LABELS=$(gh issue view "$ISSUE_NUMBER" --json labels -q '.labels[].name' 2>/dev/null)
if echo "$LABELS" | grep -q "autodev-request"; then
  echo "   Labels OK: autodev-request present"
else
  echo "   WARNING: autodev-request label not found"
fi

# 3. Wait for AutoDev to pick it up
echo "3. Waiting for AutoDev to triage..."
echo "   AutoDev should pick this up within the next heartbeat cycle (5-10 min)"
echo "   or immediately if the liaison sends a webhook wake signal."
echo ""
echo "   Monitor with:"
echo "     gh issue view $ISSUE_NUMBER"
echo "     gh pr list --label autodev-review"
echo ""
echo "   Expected flow:"
echo "     autodev-request → autodev-planned → autodev-in-progress → autodev-review → autodev-ready → autodev-merged"
echo ""
echo "4. Cleanup after test:"
echo "   gh issue close $ISSUE_NUMBER --reason 'not planned' --comment 'E2E test complete'"
