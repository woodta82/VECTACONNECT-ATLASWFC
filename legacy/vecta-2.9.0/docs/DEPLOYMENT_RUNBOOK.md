# ATLAS — Production Deployment Runbook

**Purpose:** take ATLAS from its current state — comprehensively built,
never executed — to running in production with a measurable pilot.

**Time:** roughly two working days, most of it waiting for things to run.

**The one thing to understand before starting.** ATLAS has never been
executed. Not "lightly tested" — never run. 250 tests written and zero
executed, 23 components never compiled, 8 migrations never applied.

The one tool that *has* run — the calibration harness — found two real bugs
in ninety seconds on its first execution. **Expect failures at Stage 1.**
They are not a setback; they are the point of the exercise, and finding
them here costs an afternoon rather than a commercial decision.

---

## Stage 1 — Execute (half a day)

**Gate: nothing proceeds until this passes.**

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
bash tools/validate_release.sh
```

This runs, in order: import resolution → unbound-name check → API contract
check → 250 tests → clean migration up and down → v2.8 migration with
report → end-to-end demo → `npm install` → typecheck → lint → build.
It writes `VALIDATION_REPORT.txt`.

**What to expect:**

| Area | Likelihood of failure | Typical cause |
|---|---|---|
| Import gates | Low | Already verified statically |
| Backend tests | **Medium-high** | Fixture mismatches, SQLAlchemy relationship resolution |
| Migrations | Medium | Column type or constraint issues under real Postgres/SQLite |
| TypeScript | **High** | 23 components never compiled |
| Lint | Medium | Unused imports, hook dependencies |
| Build | Medium | Follows from typecheck |

**How to work through it:** fix in the order the report lists. Backend
failures first — the frontend consumes their output, so a shape change
there invalidates frontend fixes.

Send me the report and I will work through the failures. That is faster
than either of us guessing.

**GO/NO-GO:** every gate green. Not "mostly".

---

## Stage 2 — Commit the lockfile (10 minutes)

```bash
cd frontend
git add package-lock.json
git commit -m "Add frontend lockfile for deterministic builds"
```

Without this, every deploy resolves dependencies differently. In a platform
producing commercial recommendations, non-deterministic builds are not
acceptable.

**GO/NO-GO:** `package-lock.json` in the repository.

---

## Stage 3 — Enable CI (30 minutes)

Push to a branch. Confirm `.github/workflows/validate.yml` runs and passes.

The three static gates have each caught a defect that shipped. Running them
manually makes them optional; CI makes them mandatory. This is the single
highest-leverage half hour in the runbook.

**GO/NO-GO:** green build on GitHub.

---

## Stage 4 — Database (half a day)

**Before anything else — snapshot.**

```bash
pg_dump "$DATABASE_URL" --format=custom --file="pre-v1-$(date +%F).dump"
```

Then rehearse the restore into a scratch database. The Operations Guide
documents the procedure; **it has never been executed**. Rehearse it now,
not during an incident.

```bash
# apply migrations to a copy first, never to production first
pg_dump "$DATABASE_URL" | psql "$STAGING_DATABASE_URL"
DATABASE_URL="$STAGING_DATABASE_URL" alembic stamp 0001_baseline
DATABASE_URL="$STAGING_DATABASE_URL" alembic upgrade head
```

Read the migration report. Verify:
- opportunity count unchanged
- legacy scores preserved in `legacy_opportunity_data`
- every migrated record is `unverified_lead` / `verification_required`
- no record wrongly marked Confirmed or Qualified

**GO/NO-GO:** staging migration clean, restore rehearsed, snapshot held.

---

## Stage 5 — Deploy (2 hours)

Backend start command:
```
alembic upgrade head && sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

Order: stamp production once → deploy backend, watch for the migration
report → deploy frontend → log in → change password → **delete
`LOGIN_PASSWORD` from Railway**.

**GO/NO-GO:** briefing loads. Check `generation_ms` against the 1.5s budget.

---

## Stage 6 — Make it yours (2 hours, mostly yours not mine)

**This is the stage most likely to be skipped and least advisable to skip.**

Complete the Commercial Profile to **at least 60%**. Below that, ATLAS
scores against generic defaults, and a pilot would be testing the defaults
rather than ATLAS. The completeness meter names which sections fall back
and what they fall back to.

Priority order:
1. Commercial thresholds — minimum viable value drives decline recommendations
2. Priority markets — drives strategic alignment
3. Delivery capacity — drives capacity conflict detection
4. Scoring weights — or accept the documented 35/30/25/10

Then map stakeholders on your **three** most important live opportunities.
Not thirty. The relationship models need real data to say anything useful,
and three opportunities is enough to judge whether they do.

**GO/NO-GO:** profile ≥60%, three opportunities with mapped stakeholders.

---

## Stage 7 — Calibrate against your judgement (1 hour)

```bash
python3 tools/calibrate_models.py
```

Then **replace the six scenarios with real ones from your pipeline**. For
each, write what you would conclude *before* running the models.

Where you disagree, the model is probably wrong — you have run these
pursuits and it has not. The two divergences currently open are documented
in the exit review; one (the EFS meaning question) needs your decision.

**GO/NO-GO:** no divergence you disagree with remains unresolved.

---

## Stage 8 — Pilot (four weeks)

**Do this:** open the briefing each morning. Record every significant
decision through the cards — accept, edit, defer or decline. When
opportunities resolve, record the outcome.

**Do not do this:** feed it every opportunity in the pipeline. A pilot on
ten well-maintained opportunities produces better evidence than one on
ninety neglected ones.

**Measurement.** `GET /briefing/kpis` reports all six pilot objectives:

| Objective | Metric | Target |
|---|---|---|
| Executive adoption | `working_day_coverage_percent` | > 80% |
| Recommendation usefulness | `acceptance_rate_percent` | > 60% |
| Decision quality | `accuracy_percent` | measurable at 10 outcomes |
| Workflow efficiency | `mean_turnaround_hours` | < 48 |
| Relationship visibility | RCI across pipeline | > 70% on qualified |
| Commercial impact | `win_rate_percent` | baseline established |

**Adoption is the one that matters.** The other five can all be satisfied
by a platform nobody opens. If coverage is below 50% after two weeks, the
product has failed its central test and no amount of model refinement
fixes that.

**Weekly, free:**
```bash
POST /briefing/recompute-focus
POST /relationships/recompute
```

---

## Stage 9 — Version 1.1, from evidence

After four weeks you will have: adoption data, acceptance rates, at least
some outcomes, and your own accumulated irritations.

**Define 1.1 from that.** Not from this document, and not from ideas.

The likely candidates, in the order the evidence usually surfaces them:
1. Whatever friction you hit daily and worked around
2. Model recalibration against real outcomes — the first genuine
   calibration this platform will have had
3. Activating the learning loop once ≥10 outcomes exist
4. The Predictive Engine, if and only if outcome data supports forecasting

---

## Realistic timeline

| Stage | Effort |
|---|---|
| 1. Execute and fix | Half a day + fixes |
| 2. Lockfile | 10 min |
| 3. CI | 30 min |
| 4. Database | Half a day |
| 5. Deploy | 2 hours |
| 6. Profile and stakeholders | 2 hours (yours) |
| 7. Calibration | 1 hour (yours) |
| 8. Pilot | 4 weeks |

**Roughly two working days to running, four weeks to evidence.**

---

## The honest framing

Everything in Stages 1–7 is work that should have happened before now. It
did not, because this environment cannot execute code — so twelve sprints
of design, engineering and documentation accumulated without a single
execution.

That is not a small caveat. It is the dominant risk on the project, and
Stage 1 is the whole of the mitigation.

The platform is genuinely well-built: layered architecture, single write
path, seven documented and explainable intelligence models, evidence
discipline maintained throughout, and static gates that have caught real
defects repeatedly.

**It has also never been switched on.** Stage 1 is one command.
