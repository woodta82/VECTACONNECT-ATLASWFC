# ATLAS — Operations Guide

**Scope:** running ATLAS in production. Written for the person who has to
fix it at 7am, which is the same person who built it.

The V1.0 exit review scored operational maturity **3/10** — the weakest
area, and the one requiring procedure rather than engineering. This guide
closes most of that gap. What it cannot close is the fact that these
procedures have been **written, not rehearsed**. A restore procedure that
has never been executed is a hypothesis about a restore procedure.

---

## 1. Architecture in one page

```
  Browser ──HTTPS──▶ Railway: Frontend (Next.js 14)
                          │
                          │ fetch, session cookie + CSRF header
                          ▼
                     Railway: Backend (FastAPI)
                          │
                          ├──▶ Railway Postgres      (all application data)
                          ├──▶ Supabase Storage      (uploaded files)
                          └──▶ Anthropic API         (manual scans only)
```

**Single instance by design.** Sessions and lockout counters are held in
the application process. Scaling to multiple replicas requires moving both
to the database first — see §9.

**Cost profile.** The only variable cost is the Anthropic API, and it is
incurred **only** when a scan or contact discovery is manually triggered.
The daily briefing, all seven intelligence models, and the advisor are
computed from stored data and cost nothing. This is deliberate and should
not be relaxed without a decision.

---

## 2. Configuration

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✓ | Railway provides. Postgres in production |
| `LOGIN_USERNAME` | ✓ | Single authorised login |
| `LOGIN_PASSWORD` | Bootstrap only | **Delete after first login and password change** |
| `ANTHROPIC_API_KEY` | ✓ | Scanning fails gracefully without it |
| `ANTHROPIC_MODEL` | ✓ | Watch for trailing newlines — a known Railway pitfall |
| `FRONTEND_ORIGIN` | ✓ | CORS fails **closed**. Case-sensitive, no trailing slash |
| `ENVIRONMENT` | ✓ | `production` enables Secure cookies |
| `NEXT_PUBLIC_API_URL` | ✓ | Frontend → backend |

**Two configuration failures have bitten this project before:**
- A trailing newline in `ANTHROPIC_MODEL` breaks the API call with an
  opaque error.
- `FRONTEND_ORIGIN` mismatched by case or a trailing slash produces CORS
  failures that look like authentication failures.

Check both first when something inexplicable happens.

---

## 3. Deployment

**Backend start command** — the `&&` is load-bearing:

```
alembic upgrade head && sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

If the migration fails the container exits rather than serving requests
against a schema that does not match the models. One clear failure at
deploy time beats confusing 500s at runtime.

**First deploy against an existing database**, once only:

```bash
alembic stamp 0001_baseline
```

This adopts the schema `create_all()` already built. Without it, `0002`
attempts to add columns that exist and fails.

**Order:** stamp → deploy backend (watch logs for the migration report) →
deploy frontend → log in → change password → **delete `LOGIN_PASSWORD`**.

---

## 4. Monitoring

**Health:** `GET /health` — returns 200 when the app is serving. It does
**not** check the database; a 200 with a broken database is possible.

**What to watch, in priority order:**

| Signal | Where | Threshold | Meaning |
|---|---|---|---|
| Briefing generation time | `generation_ms` in the response | > 1500ms | Budget exceeded; check §8 |
| Briefing section failures | Log: `Briefing section '<name>' failed` | Any | A section degraded; page still served |
| Slow sections | Log: `Briefing section '<name>' took Nms` | > 300ms | Emerging performance issue |
| Failed logins | `security_events` table | > 10/hour | Possible attack |
| Scan failures | `scan_runs.error` | Any | Usually Anthropic credit, not code |
| AI parse failures | `ai_parse_failures` count | Growing | Prompt/schema drift |

**Log aggregation is not configured.** Railway retains recent logs only.
For a pilot this is tolerable; for sustained production it is not.

---

## 5. Backup

**Nothing is currently scheduled. This is the most serious operational
gap.**

**Minimum viable, before the pilot:**

```bash
# Daily, retained 30 days
pg_dump "$DATABASE_URL" --format=custom --file="atlas-$(date +%F).dump"
```

Railway offers managed Postgres backups — enable them and confirm the
retention period. Do not rely on them without testing a restore.

**What loss actually costs.** Opportunity data can be re-scanned at a cost
of a few dollars. **The Decision Journal cannot be reconstructed.** It
holds the reasoning behind every decision, frozen at the time it was made
— that is the organisational memory the platform exists to build, and it
exists nowhere else.

Back up accordingly.

---

## 6. Recovery

**Untested. Rehearse before relying on it.**

```bash
# 1. Provision a fresh database
# 2. Restore
pg_restore --dbname="$NEW_DATABASE_URL" --clean --if-exists atlas-YYYY-MM-DD.dump

# 3. Confirm the schema is at head
DATABASE_URL="$NEW_DATABASE_URL" alembic current   # expect the latest revision

# 4. Verify the data that matters most
psql "$NEW_DATABASE_URL" -c "SELECT count(*) FROM decision_journal_entries;"
psql "$NEW_DATABASE_URL" -c "SELECT count(*) FROM opportunities;"

# 5. Repoint DATABASE_URL, redeploy
```

**Rollback of a bad deploy:**

```bash
# Application only — Phase 3 tables persist harmlessly
#   redeploy the previous package

# Application and schema
alembic downgrade 0006_decision_journal   # drop relationship intelligence
alembic downgrade 0003_legacy_backfill    # drop Phase 3 entirely
```

**Downgrades are tested on SQLite, never against Postgres with real data.**
Take a snapshot before the first production upgrade. This is the single
most important sentence in this guide.

**RPO/RTO:** undefined. With daily backups, RPO is up to 24 hours. RTO is
whatever a restore takes — unknown until one is rehearsed.

---

## 7. Incident response

| Symptom | Likely cause | First action |
|---|---|---|
| Login fails, correct password | Session table or `LOGIN_PASSWORD` removed before rotation | Check `auth_credentials` has a row |
| CORS errors after deploy | `FRONTEND_ORIGIN` case or trailing slash | Compare exactly |
| Briefing blank | Section isolation failed to catch something | Check logs for `Briefing section` |
| Briefing slow | Focus not recomputed; large pipeline | `POST /briefing/recompute-focus`, check §8 |
| All scans failing | Anthropic credit exhausted | Check billing before reading code |
| Scans return parse failures | Prompt/schema drift | `ai_parse_failures` holds the raw response |
| 500 on relationship endpoints | Should degrade, not 500 | Check logs — `_safe()` should have caught it |

**Diagnosis order that has proved correct repeatedly:** configuration →
credit → data → code. Code has rarely been the cause.

---

## 8. Performance

**Design budget:** briefing under 1.5 seconds, and it reports
`generation_ms` on every response.

**Known characteristics:**
- Decision cards are batched — query count is constant regardless of card
  count
- Relationship momentum is batched — 4 queries regardless of stakeholder
  count (previously ~6 per stakeholder)
- `who_matters_most`, `compute_coverage_index` and `influence_graph` still
  query per entity. Acceptable below ~200 stakeholders; revisit above that.

**If the briefing exceeds budget:**
1. Check `generation_ms` and the slow-section warnings to find the offender
2. Confirm focus scores are precomputed, not being computed on read
3. Add indexes on `executive_focus.score`, `change_events.occurred_at`
4. Only then consider caching

**No caching layer exists.** Every request recomputes. This is a deliberate
simplification, correct at current scale and wrong at ten times it.

---

## 9. Known operational limitations

1. **Single instance only.** Sessions and lockout counters are in-process.
   Two replicas would produce random logouts.
2. **Restore never rehearsed.**
3. **No log aggregation.** Railway retains recent logs only.
4. **No alerting.** Failures are discovered by looking.
5. **Postgres downgrade untested.**
6. **No rate limiting per endpoint** beyond the global middleware.
7. **RPO/RTO undefined.**

---

## 10. Routine operations

**Daily:** open the briefing. It reports its own generation time, profile
completeness and last scan age.

**Weekly:**
```bash
POST /briefing/recompute-focus        # refresh Executive Focus
POST /relationships/recompute         # refresh health and momentum
```
Both are free — no AI calls. Neither is scheduled; both should be, once a
scheduler is trusted.

**Monthly:**
- Review `ai_parse_failures` for prompt drift
- Review Commercial Profile completeness
- `python3 tools/calibrate_models.py` — check the models still agree with
  your judgement
- Verify a backup restores

**Per release:**
```bash
cd backend && bash tools/validate_release.sh
```

---

## 11. Support

Single-owner platform: the operator and the user are the same person, and
there is no escalation path. That is acceptable for a pilot and is the
main operational risk in sustained production — there is no second person
who understands the system.

**Mitigations that exist:** every model documented in
`INTELLIGENCE_MODEL_GOVERNANCE.md`; every architectural decision recorded
with its reasoning in the code comments; three static gates that fail
loudly.

**Mitigation that does not exist:** a second person.
