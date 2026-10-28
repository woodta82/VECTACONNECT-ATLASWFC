#!/usr/bin/env bash
#
# ATLAS v2.9 — release validation runner
#
# Runs every validation step and writes one report. Designed so the whole
# suite is a single command rather than twelve, and so the output is
# reproducible by anyone.
#
#   cd backend && bash tools/validate_release.sh
#
# Exit code 0 = everything passed. Non-zero = at least one failure; the
# report says which.
#
# Nothing here is destructive: it uses throwaway SQLite databases in a
# temp directory and never touches a configured DATABASE_URL.

set -uo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
WORK="$(mktemp -d)"
REPORT="$ROOT_DIR/VALIDATION_REPORT.txt"

FAILURES=0
SECTION=""

log()  { echo "$*" | tee -a "$REPORT"; }
head2() { SECTION="$1"; log ""; log "=================================================================="; log "$1"; log "=================================================================="; }
ok()   { log "  [PASS] $1"; }
bad()  { log "  [FAIL] $1"; FAILURES=$((FAILURES+1)); }
skip() { log "  [SKIP] $1"; }

: > "$REPORT"
log "ATLAS v2.9 RELEASE VALIDATION"
log "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
log "Host python: $(python3 --version 2>&1)"
log "Host node:   $(node --version 2>&1 || echo 'not installed')"
log "Working dir: $WORK"

# ---------------------------------------------------------------- 0. imports
head2 "0. STATIC VERIFICATION"
cd "$BACKEND_DIR"
if python3 tools/verify_imports.py 2>&1 | tee -a "$REPORT" | grep -q "All relative imports resolve"; then
  ok "imports resolve and all names are bound"
else
  bad "import resolution failed — fix before anything else"
fi

if python3 tools/verify_contract.py 2>&1 | tee -a "$REPORT" | grep -q "All contracts agree"; then
  ok "API contracts agree between backend and frontend types"
else
  bad "API contract mismatch — the frontend would read undefined at runtime"
fi

# ---------------------------------------------------------------- 1. backend
head2 "1. BACKEND TEST SUITE"
if ! python3 -c "import pytest" 2>/dev/null; then
  bad "pytest not installed — run: pip install -r requirements.txt -r requirements-dev.txt"
else
  export DATABASE_URL="sqlite:///$WORK/test.db"
  export ENVIRONMENT=development
  export LOGIN_USERNAME="tom@vectasports"
  export LOGIN_PASSWORD="TestBootstrap-Pw-1!"
  export ANTHROPIC_API_KEY=""

  PYTEST_OUT="$WORK/pytest.txt"
  python3 -m pytest tests/ -v --tb=short --durations=10 > "$PYTEST_OUT" 2>&1
  PYTEST_RC=$?
  tail -40 "$PYTEST_OUT" | tee -a "$REPORT"

  SUMMARY="$(grep -E '^=+ .*(passed|failed|error).* =+$' "$PYTEST_OUT" | tail -1)"
  log ""
  log "  Summary line: ${SUMMARY:-<none found>}"
  log "  Collected : $(grep -cE '^tests/.*::' "$PYTEST_OUT" 2>/dev/null || echo '?')"
  log "  Passed    : $(grep -oE '[0-9]+ passed' "$PYTEST_OUT" | tail -1 || echo 0)"
  log "  Failed    : $(grep -oE '[0-9]+ failed' "$PYTEST_OUT" | tail -1 || echo 0)"
  log "  Errors    : $(grep -oE '[0-9]+ error' "$PYTEST_OUT" | tail -1 || echo 0)"
  log "  Skipped   : $(grep -oE '[0-9]+ skipped' "$PYTEST_OUT" | tail -1 || echo 0)"
  log "  Warnings  : $(grep -oE '[0-9]+ warning' "$PYTEST_OUT" | tail -1 || echo 0)"
  log "  Full log  : $PYTEST_OUT"

  if [ $PYTEST_RC -eq 0 ]; then ok "backend suite passed"; else bad "backend suite failed (rc=$PYTEST_RC)"; fi

  log ""
  log "  --- failing tests (if any) ---"
  grep -E '^FAILED|^ERROR' "$PYTEST_OUT" | tee -a "$REPORT" || log "  none"
fi

# ------------------------------------------------------- 2. clean migration
head2 "2. DATABASE — CLEAN INSTALL MIGRATION"
if ! python3 -c "import alembic" 2>/dev/null; then
  bad "alembic not installed"
else
  export DATABASE_URL="sqlite:///$WORK/clean.db"
  if python3 -m alembic upgrade head > "$WORK/clean_up.txt" 2>&1; then
    ok "alembic upgrade head (clean database)"
    log "  revision: $(python3 -m alembic current 2>&1 | tail -1)"
    python3 - <<'PY' 2>&1 | tee -a "$REPORT"
import os, sqlite3
db = os.environ["DATABASE_URL"].replace("sqlite:///", "")
conn = sqlite3.connect(db)
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
expected = {
 "opportunity_evidence","evidence_claims","opportunity_analysis_items","score_assessments",
 "score_factors","pursuit_priorities","qualification_assessments","qualification_checklist_items",
 "qualification_blockers","qualification_overrides","commercial_values","ai_parse_failures",
 "legacy_opportunity_data","override_audits","opportunity_contributing_verticals",
 "opportunity_secondary_commercial_types","opportunity_routes_to_market"}
missing = expected - tables
print(f"  Phase 2 tables present: {len(expected & tables)}/{len(expected)}")
print(f"  Missing: {sorted(missing) if missing else 'none'}")
PY
  else
    bad "clean migration failed"
    tail -25 "$WORK/clean_up.txt" | tee -a "$REPORT"
  fi

  log ""
  log "  --- downgrade path ---"
  if python3 -m alembic downgrade base > "$WORK/clean_down.txt" 2>&1; then
    ok "alembic downgrade base"
  else
    bad "downgrade failed"
    tail -20 "$WORK/clean_down.txt" | tee -a "$REPORT"
  fi
fi

# ------------------------------------------------------- 3. v2.8 migration
head2 "3. DATABASE — MIGRATION FROM v2.8 DATASET"
if python3 -c "import alembic" 2>/dev/null; then
  export DATABASE_URL="sqlite:///$WORK/v28.db"
  python3 - <<'PY' 2>&1 | tee -a "$REPORT"
# Build a v2.8-shaped database: legacy schema via create_all, legacy rows,
# no Phase 2 data. This is what production looks like before upgrading.
from app.database import Base, engine, SessionLocal
import app.models as m
Base.metadata.create_all(bind=engine)
db = SessionLocal()
rows = [
    m.Opportunity(title="FIFA Youth Development Programme 2027",
                  summary="Youth pathway delivery partner across five federations.",
                  vertical=m.Vertical.PATHWAYS, region=m.Region.EUROPE,
                  alignment_score=78, score_breakdown={"vertical_fit": 85},
                  value_estimate=4500000.0, currency="USD",
                  source_urls=["https://fifa.example/tender/youth-2027",
                               "https://news.example/fifa-youth"]),
    m.Opportunity(title="Qatar Stadium Hospitality Partner",
                  summary="Hospitality delivery partner for stadium operations.",
                  vertical=m.Vertical.EXPERIENCES, region=m.Region.MENA,
                  alignment_score=64, score_breakdown={"vertical_fit": 70},
                  value_estimate=1200000.0, currency="USD",
                  source_urls=["https://qatar.example/hospitality"]),
    m.Opportunity(title="Legacy Record With No Sources",
                  summary="", vertical=m.Vertical.MEDIA, region=m.Region.AFRICA,
                  alignment_score=41, score_breakdown={}, source_urls=[]),
]
db.add_all(rows); db.commit()
print(f"  Seeded v2.8 dataset: {db.query(m.Opportunity).count()} opportunities")
db.close()
PY

  log ""
  log "  --- stamp baseline, then upgrade ---"
  python3 -m alembic stamp 0001_baseline > "$WORK/v28_stamp.txt" 2>&1
  if python3 -m alembic upgrade head > "$WORK/v28_up.txt" 2>&1; then
    ok "alembic upgrade head (v2.8 dataset)"
    log ""
    log "  --- MIGRATION REPORT ---"
    grep -A 20 "LEGACY MIGRATION REPORT" "$WORK/v28_up.txt" | tee -a "$REPORT" || cat "$WORK/v28_up.txt" | tail -25 | tee -a "$REPORT"

    log ""
    log "  --- data preservation ---"
    python3 - <<'PY' 2>&1 | tee -a "$REPORT"
from app.database import SessionLocal
import app.models as m
from app.models_phase2 import (LegacyOpportunityData, OpportunityEvidence,
                               QualificationAssessment, CommercialValue)
db = SessionLocal()
opps = db.query(m.Opportunity).all()
print(f"  Opportunities after migration : {len(opps)} (expected 3 — none lost)")
print(f"  Legacy records created        : {db.query(LegacyOpportunityData).count()}")
print(f"  Evidence records created      : {db.query(OpportunityEvidence).count()}")
print(f"  Commercial values created     : {db.query(CommercialValue).count()}")
print(f"  Qualification records         : {db.query(QualificationAssessment).count()}")
print("")
bad = [o.title for o in opps if not (o.summary or "").strip()]
print(f"  Empty summaries               : {bad if bad else 'none'}")
confirmed = [o.title for o in opps if o.classification == "confirmed_opportunity"]
print(f"  Wrongly marked Confirmed      : {confirmed if confirmed else 'none'}")
quals = db.query(QualificationAssessment).all()
wrong = [q.opportunity_id for q in quals if q.state == "qualified"]
print(f"  Wrongly marked Qualified      : {wrong if wrong else 'none'}")
for lg in db.query(LegacyOpportunityData).all():
    print(f"    legacy score={lg.legacy_alignment_score} value={lg.legacy_value_estimate} "
          f"vertical={lg.legacy_vertical} review={lg.vertical_requires_review}")
db.close()
PY

    log ""
    log "  --- idempotency (re-running must not duplicate) ---"
    python3 -m alembic downgrade 0002_phase2_model > /dev/null 2>&1
    python3 -m alembic upgrade head > "$WORK/v28_again.txt" 2>&1
    python3 - <<'PY' 2>&1 | tee -a "$REPORT"
from app.database import SessionLocal
from app.models_phase2 import LegacyOpportunityData, OpportunityEvidence
db = SessionLocal()
print(f"  Legacy records after re-run   : {db.query(LegacyOpportunityData).count()} (expected 3)")
print(f"  Evidence after re-run         : {db.query(OpportunityEvidence).count()} (expected 3)")
db.close()
PY
  else
    bad "v2.8 migration failed"
    tail -30 "$WORK/v28_up.txt" | tee -a "$REPORT"
  fi
fi

# --------------------------------------------------- 4. end-to-end evidence
head2 "4. END-TO-END WORKFLOW DEMONSTRATION"
export DATABASE_URL="sqlite:///$WORK/e2e.db"
python3 tools/demo_end_to_end.py 2>&1 | tee -a "$REPORT"
if [ ${PIPESTATUS[0]} -eq 0 ]; then ok "end-to-end demonstration"; else bad "end-to-end demonstration failed"; fi

# ---------------------------------------------------------------- 5. frontend
head2 "5. FRONTEND VALIDATION"
if ! command -v npm >/dev/null 2>&1; then
  bad "npm not installed — cannot validate frontend"
else
  cd "$FRONTEND_DIR"
  log "  --- npm install ---"
  if npm install > "$WORK/npm_install.txt" 2>&1; then
    ok "npm install"
    tail -5 "$WORK/npm_install.txt" | tee -a "$REPORT"
    [ -f package-lock.json ] && ok "package-lock.json present (commit it)" || bad "no lockfile produced"
  else
    bad "npm install failed"; tail -25 "$WORK/npm_install.txt" | tee -a "$REPORT"
  fi

  log ""
  log "  --- typecheck (tsc --noEmit) ---"
  if npm run typecheck > "$WORK/tsc.txt" 2>&1; then
    ok "TypeScript type-check"
  else
    bad "TypeScript errors"
    cat "$WORK/tsc.txt" | tee -a "$REPORT"
  fi

  log ""
  log "  --- lint ---"
  if npm run lint > "$WORK/lint.txt" 2>&1; then
    ok "ESLint"
    tail -15 "$WORK/lint.txt" | tee -a "$REPORT"
  else
    bad "ESLint errors"
    cat "$WORK/lint.txt" | tee -a "$REPORT"
  fi

  log ""
  log "  --- production build ---"
  if npm run build > "$WORK/build.txt" 2>&1; then
    ok "next build"
    tail -25 "$WORK/build.txt" | tee -a "$REPORT"
  else
    bad "production build failed"
    tail -40 "$WORK/build.txt" | tee -a "$REPORT"
  fi
fi

# ---------------------------------------------------------------- verdict
head2 "VERDICT"
if [ $FAILURES -eq 0 ]; then
  log "  ALL VALIDATION PASSED — safe to package as ATLAS v2.9"
else
  log "  $FAILURES CHECK(S) FAILED — not ready to package"
  log "  Send this report back and the failures can be fixed."
fi
log ""
log "  Report written to: $REPORT"
log "  Raw logs retained in: $WORK"

exit $FAILURES
