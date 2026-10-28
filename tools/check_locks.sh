#!/usr/bin/env bash
# Release gate (26 Oct 2026, evening, item 6): the committed dependency locks must be present and consistent.
# Every build, audit, browser and container job installs from exactly these files; none generates its own.
#   tools/check_locks.sh            -> exit 0 when all locks are committed, 1 otherwise (with the list)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
missing=0
for f in backend/requirements.lock backend/requirements-dev.lock frontend/package-lock.json; do
  if [ ! -s "$ROOT/$f" ]; then echo "MISSING: $f"; missing=1; else echo "present: $f ($(wc -l < "$ROOT/$f") lines)"; fi
done
if [ -s "$ROOT/backend/requirements.lock" ] && ! grep -q -- '--hash=sha256:' "$ROOT/backend/requirements.lock"; then
  echo "INVALID: backend/requirements.lock has no --hash entries (must be generated with --generate-hashes)"; missing=1
fi
if [ -s "$ROOT/backend/requirements-dev.lock" ] && ! grep -q -- '--hash=sha256:' "$ROOT/backend/requirements-dev.lock"; then
  echo "INVALID: backend/requirements-dev.lock has no --hash entries"; missing=1
fi
if [ -s "$ROOT/frontend/package-lock.json" ] && ! grep -q '"lockfileVersion"' "$ROOT/frontend/package-lock.json"; then
  echo "INVALID: frontend/package-lock.json is not an npm lockfile"; missing=1
fi
if [ "$missing" -ne 0 ]; then
  echo "Release checks cannot run without the committed locks. Generate them with the 'commit-locks' workflow (Run workflow),"
  echo "review and merge its pull request, then re-run."
  exit 1
fi
echo "locks OK"
