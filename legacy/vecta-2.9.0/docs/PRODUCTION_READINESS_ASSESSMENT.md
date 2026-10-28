# ATLAS — Production Readiness Assessment

**Prepared for:** Sprint 5 Release Candidate review
**Assessment date:** 28 July 2026
**Assessed by:** Head of Product Engineering

---

## Verdict

# NOT READY FOR RELEASE CANDIDATE

This is not a close call, and the reason is singular:

> **No part of Phase 3 has ever been executed.** 235 tests written, zero
> run. 64 backend modules, ~7,000 lines of Phase 3 code, six frontend
> components — none compiled, none executed, no migration applied, no
> endpoint called.

A Release Candidate is a build believed to be shippable pending final
validation. This build has had **no** validation beyond static analysis.
Labelling it RC would misrepresent its state to anyone who later relies
on that label.

**This assessment recommends against the RC designation and sets out
exactly what would earn it.**

---

## Why static verification is not enough

The static toolchain has been genuinely productive. It has caught, in
sequence:

| Sprint | Bug caught statically | Would have failed at |
|---|---|---|
| 2.9 | `.models` vs `..models` import | Import time — total outage |
| 3.1 | `CommercialValue` used, never imported | Runtime, on a specific path |
| 3.1 | Backend/frontend contract drift | Silent `undefined` in the UI |
| 2 | Influence offsetting decay, not amplifying | Never — wrong advice, looked fine |
| 4 | Scenario engine: only 2 of 5 options reachable | Never — plausible but useless |
| 4 | "Strengthen relationships" with 18 days left | Never — impossible recommendation |

**The last three matter most.** They would never have thrown an error.
They would have produced confident, well-formatted, wrong advice. That is
precisely the failure mode this platform exists to prevent, and static
analysis found them only because I went looking.

What static analysis **cannot** find:
- Whether the 235 tests pass
- Whether SQLAlchemy relationships resolve at runtime
- Whether the migrations apply in sequence
- Whether TypeScript compiles
- Whether the briefing meets its 1.5s budget
- Whether any of it works

---

## Findings by area

### 1. Testing — **BLOCKING**

| | |
|---|---|
| Tests written | 250 |
| Tests executed | **0** |
| Coverage measured | Not possible |

Every calibration claim in `INTELLIGENCE_MODEL_GOVERNANCE.md` rests on
static analysis and hand-traced examples.

### 2. Frontend — **BLOCKING**

Six components (~1,900 lines) never compiled. `npm install` has never
run, so there is **no lockfile** — dependencies are non-deterministic.
`tsc`, `eslint` and `next build` have never executed.

New code of this size reliably produces type errors. The API contract
checker reduces the risk of *shape* mismatches but says nothing about
syntax, generics, or React-specific typing.

### 3. Database — **BLOCKING**

Seven migrations (`0001`–`0007`), none applied. Generated from the models
with verified zero drift and complete downgrade paths — but a migration
that has not run is a hypothesis.

The v2.8 upgrade path has never been exercised against a seeded dataset.

### 4. Performance — **HIGH RISK, partially mitigated**

Fixed this sprint: `_momentum_batch()` collapses ~6 queries per
stakeholder into 4 total. At 200 stakeholders that is ~1,200 queries
reduced to 4.

**Remaining:**
- `who_matters_most`, `compute_coverage_index`, `influence_graph` still
  query per entity
- The 1.5s briefing budget is instrumented but never measured
- No caching layer; every request recomputes
- No index review against real query plans

### 5. Error handling — **PARTIALLY RESOLVED (RC1)**

**Closed in RC1:** `relationships_v2` now has **12 of 12** endpoints
protected. Query failures degrade to an empty result with the cause
logged; the two compute-heavy endpoints surface a 500 with a clear message
rather than a stack trace. This matters because relationship intelligence
renders inside the executive briefing — an unhandled exception there took
down the landing page.

**Remaining:** roughly 43 of 52 other endpoints still lack explicit
handling. Lower risk, since they are not on the daily path.

Mitigating: the briefing has section-level isolation, so the landing page
degrades rather than failing entirely. That protects the most important
surface but not the others.

### 6. Security — **ACCEPTABLE**

| Control | Status |
|---|---|
| Authentication | PBKDF2-HMAC-SHA256, 600k iterations |
| Sessions | DB-backed, HttpOnly, Secure, SameSite |
| CSRF | Enforced, only `/auth/login` exempt |
| Lockout | 5 attempts per IP + escalating delay |
| Audit logging | `security_events` table |
| Middleware coverage | Global — all Sprint 2–4 endpoints inherit it |
| Secrets in repo | Zero occurrences |
| Browser-exposed secrets | Zero |
| Dependencies | 9 direct, all mainstream |

**Gaps:** no dependency vulnerability scan has been run; no rate limiting
on the new intelligence endpoints specifically (global limit applies); no
input validation beyond FastAPI type coercion on path parameters.

### 7. Backup and disaster recovery — **NOT ADDRESSED**

- No documented backup schedule
- No tested restore procedure
- Alembic downgrade tested on SQLite only, never Postgres
- No RPO/RTO defined

This is a genuine gap, not an oversight of documentation. Nothing exists.

### 8. Intelligence models — **DESIGN GOOD, VALIDATION ABSENT**

Seven models, all weights verified to 1.0, all documented, all
explainable, none executed.

**Structural limitation:** DCS's historical-accuracy input requires ≥10
scored decisions. There are none. The learning loop is inert and will
remain so until real decisions have real outcomes — likely months of
production use.

Weights are **reasoned, not fitted**. That is the correct starting
position but should not be mistaken for calibration.

---

## Remaining risks, ranked

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Nothing has been executed | **Critical** | Run `validate_release.sh` |
| 2 | No frontend lockfile | High | `npm install`, commit the lockfile |
| 3 | Migration chain unproven | High | Apply to clean + v2.8 DB |
| 4 | Briefing may exceed 1.5s | Medium | Measure; add caching if needed |
| 5 | 55 endpoints without error handling | Medium | Add handling to `relationships_v2` first |
| 6 | No backup/DR procedure | Medium | Document and test a restore |
| 7 | Models uncalibrated | Medium | Accumulate outcome data; revisit weights |
| 8 | No dependency vulnerability scan | Low | `pip-audit`, `npm audit` |
| 9 | Relationship inference from role text | Low | Labelled and capped; replaced by stakeholder data |

---

## Technical debt

**Introduced this sprint:** none — Sprint 5 removed debt (N+1 batching,
quality scoring, governance documentation).

**Carried:**

| Debt | Cost of leaving it |
|---|---|
| No frontend tests | UI regressions invisible |
| `_relationship_status` dual code path | Divergence risk between batched and single-item |
| `competing_pursuits` hardcoded to 0 | Capacity conflicts undetected |
| RHS cannot distinguish rhythm from clustering | 12 engagements in a week scores as 12 across a year |
| Legacy `alignment_score` columns retained | Schema confusion |
| Model interactions unmodelled | Correlated errors compound silently |

---

## The Executive Trust question

> *"Would an executive confidently base a multi-million-pound commercial
> decision on this recommendation?"*

**Today: no.** Not because the reasoning is poor — the models are
explainable, evidence-weighted and confidence-gated, and the design is
sound. But because **no recommendation has ever been produced by running
code**. Every example in this project has been traced by hand.

The honest position: ATLAS is a well-designed decision platform that has
never been switched on.

---

## Path to Release Candidate

Sequential. Each step gates the next.

**Step 1 — Execute (blocks everything)**
```bash
cd backend && bash tools/validate_release.sh
```
Runs three static gates, 235 tests, both migration paths, the end-to-end
demo, `npm install`, typecheck, lint and build. Writes
`VALIDATION_REPORT.txt`.

**Step 2 — Fix what it surfaces.** Expect failures. New code of this
volume always has them.

**Step 3 — Measure the briefing.** `generation_ms` is already returned.
If it exceeds 1.5s, add caching before RC.

**Step 4 — Close the error-handling gap** on `relationships_v2`.

**Step 5 — Document and test a restore** against Postgres.

**Step 6 — Run dependency scans.**

**Then, and only then, tag RC.**

---

## Recommended roadmap to Version 1.0

| Phase | Objective | Gate |
|---|---|---|
| **RC1** | Everything above | Full suite green |
| **RC2** | Two weeks of real use by one user | Briefing opened before email 10 of 10 working days |
| **RC3** | 10+ decisions recorded with outcomes | DCS learning loop becomes active |
| **1.0** | Weights revisited against outcome data | Models calibrated, not merely reasoned |

**1.0 should not be tagged on feature completeness.** It should be tagged
when the intelligence models have been checked against reality at least
once. Until then ATLAS is a well-reasoned hypothesis about what drives
commercial decisions — a good one, but untested.

---

## What Sprint 5 delivered

- **Recommendation quality scoring** — five dimensions, flags
  below-threshold recommendations with the reason rather than showing
  them alongside good ones
- **N+1 elimination** in `relationship_service` — ~1,200 queries to 4
- **Intelligence Model Governance** — seven models fully specified,
  22/22 documented values verified against code
- **Partner scenario** — fifth commercial posture, plus a fix to
  feasibility modelling that had recommended an impossible course of
  action
- **This assessment**

Sprint 5's objective was trust. The most trust-building thing available
was an honest assessment that the platform is not ready, and a specific
path that would make it so.
