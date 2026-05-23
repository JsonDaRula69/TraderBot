#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building Docker image ==="
docker compose build

echo "=== Creating results directory ==="
mkdir -p ./results

echo "=== Starting all 4 methodology containers ==="
docker compose up --abort-on-container-exit

echo ""
echo "=== All containers finished ==="
echo "Results written to experiments/docker/results/:"
ls -la ./results/
echo ""
echo "Summary:"
for f in ./results/*.jsonl; do
    if [ -f "$f" ]; then
        count=$(wc -l < "$f" || echo "0")
        echo "  $(basename "$f"): ${count} lines"
    else
        echo "  $(basename "$f"): missing"
    fi
done
echo ""
echo "To clean up: docker compose down"
