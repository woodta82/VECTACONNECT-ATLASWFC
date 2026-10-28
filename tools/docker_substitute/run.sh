#!/usr/bin/env bash
# Build the SUBSTITUTE base images (if missing), build and start the compose stack, check health and
# readiness through the web container, restart the worker, collect logs, and stop everything.
#   tools/docker_substitute/run.sh OUT_DIR [PYTHON]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:?output dir}"; PY="${2:-python3}"
mkdir -p "$OUT"; cd "$HERE"
export LOGIN_BOOTSTRAP_PASSWORD="${LOGIN_BOOTSTRAP_PASSWORD:-Docker-Verify-Pass-2026!}"
C="docker compose -f compose.yml"
docker image inspect atlas-substitute/python-runtime:local >/dev/null 2>&1 || "$PY" build_bases.py --python "$PY" | tee "$OUT/bases.log"
$C down -v >/dev/null 2>&1
$C build --progress plain > "$OUT/build.log" 2>&1; b=$?; echo "build exit $b" | tee "$OUT/report.txt"
# Never fall back to images left over from an earlier build.
[ "$b" -eq 0 ] || { tail -5 "$OUT/build.log" | tee -a "$OUT/report.txt"; exit 3; }
timeout 300 $C up -d --wait > "$OUT/up.log" 2>&1; echo "up --wait exit $?" | tee -a "$OUT/report.txt"
# The web container has no health check of its own: wait until it answers through the published port.
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:3300/api/health/live && break; sleep 1; done
echo "web answered after ${i}s" >> "$OUT/report.txt"
{
  echo "== services"; $C ps -a --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
  echo "== live";  curl -s -w " [%{http_code}]\n" http://127.0.0.1:3300/api/health/live
  echo "== ready"; curl -s -w " [%{http_code}]\n" http://127.0.0.1:3300/api/health/ready
  echo "== unauthenticated /api/briefing"; curl -s -o /dev/null -w "[%{http_code}]\n" http://127.0.0.1:3300/api/briefing
  echo "== login"; curl -s -c "$OUT/.cj" -H 'content-type: application/json' \
       -d "{\"username\":\"ops@wfc.local\",\"password\":\"$LOGIN_BOOTSTRAP_PASSWORD\"}" -o /dev/null -w "[%{http_code}]\n" http://127.0.0.1:3300/api/auth/login
  echo "== /api/briefing signed in"; curl -s -b "$OUT/.cj" -o /dev/null -w "[%{http_code}]\n" http://127.0.0.1:3300/api/briefing
  echo "== page title"; curl -s http://127.0.0.1:3300/ | grep -o "<title>[^<]*</title>"
  echo "== security headers"; curl -sI http://127.0.0.1:3300/ | grep -iE "x-frame|nosniff|referrer"
  echo "== worker restart"; $C restart worker; sleep 4
  echo "== jobs"; $C exec -T db sh -c 'PGPASSWORD=dev-only /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U atlas -d atlas_wfc -Atc "select job_type, status, attempts from jobs order by created_at"'
} >> "$OUT/report.txt" 2>&1
rm -f "$OUT/.cj"
for s in db migrate api worker web; do $C logs --no-color "$s" > "$OUT/$s.log" 2>&1; done
if grep -l "$LOGIN_BOOTSTRAP_PASSWORD" "$OUT"/*.log; then echo "SECRET FOUND IN LOGS" | tee -a "$OUT/report.txt"; fi
$C down -v >> "$OUT/report.txt" 2>&1
cat "$OUT/report.txt"
