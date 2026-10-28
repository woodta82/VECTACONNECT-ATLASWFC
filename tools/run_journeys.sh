#!/usr/bin/env bash
# Start a clean local stack, run the browser journeys, keep artifacts and logs, stop the stack.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/e2e-artifacts}"
PY="${PYTHON:-python}"
mkdir -p "$OUT"
STACK_PYTHON="$PY" "$PY" "$ROOT/tools/local_stack.py" up --logs "$OUT/stack-logs" > "$OUT/stack-up.json" || { echo "stack failed to start"; exit 2; }
E2E_RESTART_WORKER_CMD="STACK_PYTHON=$PY $PY $ROOT/tools/local_stack.py restart --service worker --logs $OUT/stack-logs" \
E2E_ARTIFACTS="$OUT" "$PY" -m pytest "$ROOT/e2e" -q -p no:cacheprovider --junitxml="$OUT/journeys.xml" 2>&1 | tee "$OUT/journeys.log"
rc=${PIPESTATUS[0]}
"$PY" "$ROOT/tools/local_stack.py" down --logs "$OUT/stack-logs"
exit "$rc"
