#!/usr/bin/env python3
"""Pre-commit hook to prevent runtime data from polluting .openclaw/workspace/ templates.

Template files should only contain placeholder content (e.g., "*(pending)*", "*(none)*").
Any real data (timestamps, status entries, learning entries, heartbeat metrics)
indicates test/runtime leakage that should stay in deployed workspaces.
"""

import sys
from pathlib import Path

WORKSPACE = Path(".openclaw/workspace")

FORBIDDEN_PATTERNS = {
    "SESSION-STATE.md": ["Status: CANCELLED", "Status: COMPLETED", "Status: PENDING"],
    "HEARTBEAT_DATA.md": ["### Performance", "### Circuit Breaker", "### System Health", "## Last Heartbeat:"],
    ".learnings/LEARNINGS.md": ["## Entry:", "**Logged**:", "**Pattern-Key**:"],
    ".learnings/FEATURE_REQUESTS.md": ["## Entry: FEAT-"],
}


def check_workspace_templates() -> list[str]:
    errors = []
    for rel_path, patterns in FORBIDDEN_PATTERNS.items():
        filepath = WORKSPACE / rel_path
        if not filepath.exists():
            continue
        content = filepath.read_text()
        for pattern in patterns:
            if pattern in content:
                errors.append(f"{filepath}: contains runtime data '{pattern}' — template should be clean")
    return errors


if __name__ == "__main__":
    errors = check_workspace_templates()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("\nWorkspace templates must contain only placeholder content.", file=sys.stderr)
        print("Run: git checkout -- .openclaw/workspace/ to restore templates", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)