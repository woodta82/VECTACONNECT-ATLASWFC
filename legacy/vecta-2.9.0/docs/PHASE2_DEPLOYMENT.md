# ATLAS Phase 2 — Deployment, Verification and Rollback

**Status: NOT READY TO DEPLOY.** The frontend still renders the legacy
model, so deploying this would put Phase 2 data behind a UI that cannot
display it. Run the verification below in the Codespace, then wait for
the frontend before deploying to Railway.

---

## 1. Verification (run these first, in this order)

Order matters: imports before tests, tests before migrations, migrations
before anything touches production.

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt

# (a) every relative import resolves — catches wrong-package-root errors
python3 tools/verify_imports.py

# (b) full backend suite (88 tests)
pytest tests/ -v

# (c) clean-database migration, all three revisions
rm -f clean.db
DATABASE_URL=sqlite:///./clean.db alembic upgrade head
DATABASE_URL=sqlite:///./clean.db alembic current      # expect 0003_legacy_backfill

# (d) downgrade path
DATABASE_URL=sqlite:///./clean.db alembic downgrade base
```

### Migration against a v2.8-shaped database

The backfill only demonstrates anything against real legacy rows, so seed
some first:

```bash
rm -f v28.db
DATABASE_URL=sqlite:///./v28.db python3 -c "
from app.database import Base, engine, SessionLocal
import app.models as m
Base.metadata.create_all(bind=engine)
db = SessionLocal()
db.add(m.Opportunity(title='Legacy Test Opportunity', vertical=m.Vertical.PATHWAYS,
                     alignment_score=72, score_breakdown={'vertical_fit': 80},
                     value_estimate=3000000.0, currency='USD',
                     source_urls=['https://example.gov/tender/1']))
db.commit(); db.close()
print('v2.8-shaped database seeded')
"

DATABASE_URL=sqlite:///./v28.db alembic stamp 0001_baseline   # adopt the existing schema
DATABASE_URL=sqlite:///./v28.db alembic upgrade head          # prints the migration report
```

The upgrade prints the **migration report** — records examined, migrated,
verticals mapped, verticals requiring review, evidence records created,
legacy values preserved, and any errors.

Confirm preservation:

```bash
DATABASE_URL=sqlite:///./v28.db python3 -c "
from app.database import SessionLocal
import app.models as m
from app.models_phase2 import LegacyOpportunityData, OpportunityEvidence, QualificationAssessment
db = SessionLocal()
opp = db.query(m.Opportunity).first()
legacy = db.query(LegacyOpportunityData).filter_by(opportunity_id=opp.id).first()
qual = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
print('legacy score preserved :', legacy.legacy_alignment_score)
print('legacy value preserved :', legacy.legacy_value_estimate)
print('mapped vertical        :', opp.primary_vertical)
print('classification         :', opp.classification, '(must be unverified_lead)')
print('qualification          :', qual.state, '(must be verification_required)')
print('evidence created       :', db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).count())
"
```

### Frontend

```bash
cd ../frontend
npm install
npm run lint
npx tsc --noEmit
npm run build
```

These check the **current** frontend. They cannot demonstrate Phase 2
rendering, because no component reads a Phase 2 field yet.

---

## 2. Deployment (once the frontend exists)

Alembic is authoritative. The app must not start against a database
behind the migrations.

**Railway backend — set the start command to migrate first:**

```
alembic upgrade head && sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

`&&` is doing real work here: if the migration fails the container exits
instead of serving requests against a schema that doesn't match the
models. Silently continuing would produce confusing 500s at runtime
rather than one clear failure at deploy time.

**First deploy on the existing production database**, run once before
switching the start command:

```
alembic stamp 0001_baseline
```

This adopts the schema `create_all()` already built. Without it, 0002
tries to add columns that exist and fails.

**Order:**
1. `alembic stamp 0001_baseline` (once, existing DB only)
2. Deploy backend with the migrating start command — watch the logs for
   the migration report
3. Deploy frontend
4. Confirm both Active, then log in and check an opportunity detail page

---

## 3. Rollback

**Application only** (schema stays): redeploy the previous zip over both
folders. The Phase 2 tables persist harmlessly; the legacy scanner ignores
them.

**Application and schema:**

```
alembic downgrade 0002_phase2_model   # undo the backfill only
alembic downgrade 0001_baseline       # also drop the Phase 2 tables
```

`downgrade 0002` removes only the rows the backfill inserted and clears
the classification columns it set. Legacy scores, values and source URLs
are untouched throughout — the backfill copies rather than moves, so the
original data survives every rollback path.

**Take a Railway Postgres snapshot before the first production upgrade.**
Alembic downgrade is tested on SQLite here, not against production
Postgres with real data, and a snapshot is the difference between an
inconvenience and a bad afternoon.

---

## 4. Known limitations

- **Frontend does not render Phase 2.** Blocking for deployment.
- The `alembic upgrade` runs are verified by me only as syntax and column
  correspondence; they have not been executed. Run section 1 first.
- Downgrade is tested on SQLite, not Postgres.
- Legacy `alignment_score` / `value_estimate` columns still exist on
  `opportunities`, populated for pre-Phase-2 rows. Dropping them is a
  later cleanup once nothing reads them.
- The scan cost profile changed: Regional Search now makes **one** AI
  call for the whole scope instead of one per vertical, because Phase 2
  classifies verticals per opportunity. Fewer calls, larger responses.

---

## 5. Pipeline-entry rule hierarchy (v2.9)

An opportunity may enter the active commercial pipeline only when **all**
of the following hold. The gate reports **every** failing rule at once
rather than the first — a user who fixes one blocker only to be shown the
next is being drip-fed, and order-dependent errors make tests brittle.

Ordered by how fundamental the objection is
(`PIPELINE_RULE_ORDER` in `app/qualification.py`):

| # | Rule | Blocks when | Resolution |
|---|---|---|---|
| 1 | **Classification** | `market_signal`, `intelligence_watch` or `unverified_lead` | Reclassify once evidence supports it |
| 2 | **Disqualified** | Qualification state is `disqualified` | Resolve the absolute bar, or override with a documented reason |
| 3 | **Deadline** | Deadline is in the past | None — the opportunity has expired |
| 4 | **Qualification** | State is `not_assessed` or `verification_required` | Complete the checklist in the UI |

Permitted states: `qualified` and `conditionally_qualified`. A conditional
state deliberately still progresses — a remediable blocker (local entity
not yet secured, partner not yet appointed) is a task to complete during
pursuit, not a reason to abandon the opportunity.

Enforced in `opportunity_service.assert_can_enter_active_pipeline()`,
which raises rather than returning a flag, because a caller who forgets to
check a boolean is exactly how such a rule gets bypassed.

## 6. Timestamp convention

- **Timezone-aware** (`utcnow()`): auth and Phase 2 tables, whose columns
  are `DateTime(timezone=True)`.
- **Naive UTC** (`utcnow_naive()`): pre-Phase-2 business tables
  (opportunities, interactions, scan_runs), whose columns are naive
  `DateTime` holding existing production data.

`utcnow_naive()` is semantically identical to the deprecated
`datetime.utcnow()` without the warning. Writing an aware datetime to
those naive columns would be silently truncated by Postgres and would
reintroduce the naive/aware comparison bug `as_aware()` exists to prevent.
Converting them requires an `ALTER COLUMN TYPE TIMESTAMPTZ` migration —
listed under known limitations rather than done silently.
