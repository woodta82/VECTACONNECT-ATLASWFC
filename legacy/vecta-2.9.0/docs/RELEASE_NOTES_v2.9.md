# ATLAS v2.9 — Release Notes

**Version:** 2.9.0
**Status:** Validated baseline release
**Supersedes:** v2.7 (last deployed), v2.8 (Phase 1 security, not deployed)

---

## What this release is

v2.9 closes Phases 1 and 2. It turns ATLAS from an opportunity list into
an evidence-led commercial intelligence platform: every opportunity now
carries its sources, its reasoning, four independent scores with visible
factor breakdowns, and a formal qualification gate that controls whether
it can be pursued at all.

The change that matters most is not a feature. It is that ATLAS no longer
presents an unverified guess and a checked fact in the same typeface. An
AI estimate is labelled an estimate, a wider-programme figure can never
be read as money available to VECTA, and a risk score built from thin
data refuses to display as a reassuring number.

---

## Phase 1 — Security foundation

- **Password stored only as a PBKDF2-HMAC-SHA256 hash** (600k iterations,
  per-hash salt). No plaintext password exists anywhere in the repository,
  environment files, logs or frontend build.
- **Server-side sessions** in an HttpOnly, Secure, SameSite=None cookie —
  unreadable by page JavaScript. 24h absolute plus 60min idle expiry.
- **CSRF protection** on every state-changing endpoint.
- **Login lockout** (5 failures per IP in 15 minutes) plus an
  account-level escalating delay that slows distributed attacks without
  ever locking the owner out permanently.
- **Security event log** recording every login, failure, lockout, logout
  and password change.
- **Static frontend API key removed entirely.** A key shipped in the
  browser build is readable by anyone who can load the page; it was never
  a private security layer. The database-backed session is now the sole
  authentication mechanism.
- **Single login enforced.** No registration, invitations, roles or
  additional accounts. The legacy `users` table is retained inert, for
  foreign-key integrity only.

## Phase 2 — Intelligence model

**Four independent scores** replace the single alignment score: Strategic
Alignment, Commercial Attractiveness, Win Probability and Risk. Risk is
inverted (100 = most risk) and enters Pursuit Priority as (100 − Risk).
All 39 factors carry explicit 0/50/100 anchors, and every factor score
requires a rationale.

**Coverage governance.** A partially assessed score is never presented as
complete. Below 80% coverage, Pursuit Priority is capped at "Review". For
Risk specifically, insufficient coverage displays **"Risk not
established"** rather than a low number — a reassuring figure built from
thin data is worse than no figure.

**Evidence model.** Source tiers 1–4, with claim-level linkage: each
evidence record declares which specific claims it supports. A Tier 1
tender notice proving an opportunity exists does **not** validate an AI's
guess at its value. ATLAS validates URLs itself; the AI does not certify
its own sources.

**Confirmed Opportunity enforcement** in the service layer, not the
prompt or frontend: Tier 1 (or definitive Tier 2) evidence, live-status
evidence, a validated URL, a publication date or documented reason, a
verification timestamp and a confidence assessment. Unsupported claims
downgrade to Unverified Lead with the reason recorded, rather than being
discarded.

**Qualification gate** — 16 checks with typed failures. Absolute
disqualifiers bar permanently; remediable blockers (local entity not yet
secured, partner not yet appointed) produce Conditionally Qualified so a
recoverable obstacle is not buried as a permanent one. Pipeline entry
reports **every** blocking reason at once.

**Strict AI contract.** Bracket-slicing extraction is gone. A versioned
Pydantic schema validates per-record, so one malformed record is isolated
as a parse failure — with the raw response preserved for retry — while
the good records in the same batch still persist.

**Commercial value** separates published contract value, published
programme value and estimated ranges. An estimated range requires both
bounds and a stated methodology.

### Also in this release
- Manual-only AI costs: no automatic scanning, saved-search refresh or
  contact discovery. Charges occur only from actions you take.
- Alembic as the authoritative migration system, with a non-destructive
  legacy backfill.
- Currency displayed in USD throughout.
- Qualification workflow UI, so the gate has a route through it.

---

## Validation status

| Check | Result |
|---|---|
| Backend tests | **103 passed, 0 failed, 0 errors** |
| Import resolution | 44 modules, all resolve |
| Deprecated APIs | 0 (`datetime.utcnow`, `declarative_base`, legacy `Query.get`, `class Config`) |
| Plaintext secrets | 0 occurrences repo-wide |
| Browser-exposed auth secrets | 0 |

Remaining warnings are SQLite/Python third-party deprecations, accepted
as non-blocking.

---

## Known limitations

1. **Frontend runtime validation is the operator's step.** Type-check,
   lint and production build must be run in the deployment environment
   (`npm run validate`). They have not been executed by the build author.
2. **Alembic downgrade is tested on SQLite, not Postgres.** Take a
   database snapshot before the first production upgrade.
3. **Legacy business-table timestamps remain naive.** Converting
   `opportunities`, `interactions` and `scan_runs` to `TIMESTAMPTZ`
   requires an `ALTER COLUMN TYPE` migration, deliberately deferred
   rather than done silently.
4. **Migrated legacy records are deliberately conservative.** Every
   pre-Phase-2 opportunity lands as `unverified_lead` /
   `verification_required` and is flagged for review. Old data has no
   evidence tiers, so it cannot satisfy the Phase 2 bar. Expect to
   review them.
5. **Legacy `alignment_score` / `value_estimate` columns still exist** on
   `opportunities`, populated for pre-Phase-2 rows and preserved in
   `legacy_opportunity_data`. Dropping them is a later cleanup.
6. **Failed-login counters are in-memory** and reset on restart. The
   durable record is `security_events`.
7. **Single backend instance assumed.** Sessions and lockout counters do
   not synchronise across replicas.
8. **No Commercial Profile yet.** Scoring weights use documented defaults
   rather than VECTA's configured priorities — the first Phase 3
   workstream.

---

## Upgrade summary

1. Set `LOGIN_PASSWORD` and `FRONTEND_ORIGIN` in Railway **before**
   deploying (CORS fails closed without the latter).
2. `alembic stamp 0001_baseline` once, on the existing production
   database.
3. Deploy backend with `alembic upgrade head && uvicorn ...` so the app
   refuses to start against a stale schema.
4. Deploy frontend.
5. Log in, change the password in Settings, then **delete
   `LOGIN_PASSWORD` from Railway**.

Full detail in `docs/PHASE2_DEPLOYMENT.md`.
