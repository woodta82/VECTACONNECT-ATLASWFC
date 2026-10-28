#!/usr/bin/env bash
# Run ALL authenticated browser journeys (e2e/) against the container stack (substitute images + compose.e2e.yml):
# PostgreSQL, migrate, API, worker and web containers, with the synthetic fixture site and SIMULATED AI provider.
#   tools/docker_substitute/run_e2e.sh OUT_DIR [PYTHON]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:?output dir}"; PY="${2:-python3}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"; cd "$HERE"
export LOGIN_BOOTSTRAP_PASSWORD="Local-Verify-Pass-2026!"     # the journeys' shared login (verification only)
C="docker compose -f compose.yml -f compose.e2e.yml"
$C down -v >/dev/null 2>&1
$C build --progress plain > "$OUT/build.log" 2>&1; b=$?; echo "build exit $b" | tee "$OUT/report.txt"
# Never fall back to images left over from an earlier build.
[ "$b" -eq 0 ] || { tail -5 "$OUT/build.log" | tee -a "$OUT/report.txt"; exit 3; }
timeout 300 $C up -d --wait > "$OUT/up.log" 2>&1; echo "up --wait exit $?" | tee -a "$OUT/report.txt"
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:3000/api/health/live && break; sleep 1; done
{ echo "== services"; $C ps -a --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
  echo "== ready"; curl -s -w " [%{http_code}]\n" http://127.0.0.1:3000/api/health/ready; } >> "$OUT/report.txt" 2>&1
( cd "$ROOT" && PGPASSWORD=dev-only WFC_STACK_PG="host=127.0.0.1 port=5434 user=atlas" E2E_STACK_DB=atlas_wfc \
  E2E_FIXTURE_SITE=http://fixture:8089 E2E_ARTIFACTS="$OUT" E2E_RESTART_WORKER_CMD="cd $HERE && $C restart worker" \
  "$PY" -m pytest e2e -q -p no:cacheprovider --junitxml="$OUT/journeys.xml" > "$OUT/journeys.log" 2>&1 )
rc=$?; echo "journeys exit $rc" | tee -a "$OUT/report.txt"; tail -3 "$OUT/journeys.log" >> "$OUT/report.txt"
for s in db migrate api worker web fixture ai_stub; do $C logs --no-color "$s" > "$OUT/$s.log" 2>&1; done
if grep -l "$LOGIN_BOOTSTRAP_PASSWORD" "$OUT"/*.log; then echo "LOGIN PASSWORD FOUND IN CONTAINER LOGS" | tee -a "$OUT/report.txt"; fi
$C down -v >> "$OUT/down.log" 2>&1
exit "$rc"
