# Phase 2 — Development Status (working branch)

**This is not a Phase 2 completion claim.** Per the completion standard
in the spec, Phase 2 cannot be labelled complete until the database
persists the model, data migrates, the scanner produces the new schema,
the frontend displays it and automated tests pass. Several of those
layers are not built. What follows is split strictly on that basis.

**Package name:** `atlas-vecta-phase2-dev` — deliberately not a release
label, per the instruction to keep this in the development branch until
the completion conditions are met.

---

## THIS ITERATION — blocking import bug fixed

### Item 1 — service-layer ImportError: FIXED

`app/services/opportunity_service.py` used single-dot relative imports.
The module sits one level below `app/`, so `from . import evidence`
resolved to `app.services.evidence` — which does not exist. All seven
imports corrected to `..`.

**Why my previous verification missed it, and what changed:** I grepped
for the import strings and confirmed the target names existed somewhere
in the package. A grep cannot see package depth, so it confirmed the
wrong thing entirely. Replaced with `backend/tools/verify_imports.py`,
which computes the actual target module path for every relative import
the way Python does (`.` = own package, `..` = parent) and checks the
module exists and exports the name.

*Verified by reintroducing the bug:* the resolver reports
`app/services/opportunity_service.py:31: '.evidence' -> app.services.evidence does not exist`
— the same failure, caught statically. With it restored: 40 modules
checked, all imports resolve. The resolver runs as a committed test, so
this class of bug now fails the suite.

### Items 2 and 6 — committed tests: ADDED
`backend/tests/test_phase2_service.py`, **18 tests**, all real imports
and real database writes:

- `test_opportunity_service_imports` — the direct regression test
- `test_service_actually_bound_to_the_engines` — asserts the service
  holds references to the real engine modules and their functions are
  callable, rather than that a module name appears in the file
- `test_all_backend_relative_imports_resolve` — runs the resolver
- `test_phase2_models_registered_on_metadata` — all 17 tables present in
  `Base.metadata` (defining models in a separate file does not register
  them; the import has to happen)
- `test_phase2_columns_on_opportunity` — all 9 columns registered
- Persistence: evidence + claims, claim-less evidence rejected, scores +
  factor rows, risk-not-established stored, qualification with checklist
  and typed blockers, remediable blocker → conditional, pursuit priority
  with restriction recorded
- Enforcement: Confirmed downgraded without evidence and allowed with
  it, pipeline blocked until qualified, pipeline blocked by passed
  deadline, override requires a reason and preserves the AI score,
  parse failure persisted with no partial opportunity created

## PREVIOUS ITERATION — integration spine

### Item 4 — strict AI contract: BUILT (`app/ai_schema.py`)
Replaces the bracket-slicing extraction, which could not tell "returned
nothing useful" from "returned six good records and one malformed one",
and silently produced half-populated opportunities from partial JSON.

- Versioned (`2.0`), `extra="forbid"` throughout — unknown fields are an
  error, because a response carrying fields we don't recognise means the
  model drifted from the contract
- Every Phase 2 field declared with type and constraints: classification,
  verticals, commercial types, routes, evidence with claims, fact
  candidates, interpretation, assumptions, gaps, verification actions,
  values, four factor-level score dimensions, qualification checklist
- **Per-record validation** — one malformed record is isolated rather
  than poisoning the batch; the outcome carries valid records *and* the
  errors for the invalid ones
- Cross-field rules the type system can't express: a fact candidate
  referencing an evidence URL not present in the payload is rejected (the
  AI inventing a source); `estimated_range` requires both bounds *and* a
  stated methodology; a published status requires its published figure;
  primary vertical cannot also be a contributing vertical
- Factor and qualification keys are **imported from the engines**, not
  duplicated — rename a factor in `scoring_v2.py` and a stale AI response
  fails validation instead of silently dropping

*Verified statically:* all four `Literal` enums match the taxonomy
exactly; `_CLAIM_TYPES` matches `evidence.ClaimType` exactly; all 39
factor keys and 16 qualification keys resolve against the live engines.

### Item 6 — service layer: BUILT (`app/services/opportunity_service.py`)
**This is what makes the engines live.** Every write path — scanner, API,
manual editing — goes through here, so the rules cannot be bypassed by
writing to the ORM directly from a router.

*Verified:* `scoring_v2` (3 call sites), `qualification` (3),
`evidence` (2) all imported and executed; 9 taxonomy symbols referenced;
10 Phase 2 models instantiated; all 18 model imports and 5 taxonomy
imports resolve.

Enforcement implemented: Confirmed-without-evidence downgrades to
Unverified Lead with the reason recorded and human review flagged;
pipeline entry raises rather than returning a flag (a caller who forgets
to check a boolean is exactly how such a rule gets bypassed); expired
deadline blocks entry; coverage and risk-established restrictions applied
where the priority number is produced, not at display time; value display
metadata travels with the figure so no layer decides for itself whether
it's a published fact; overrides require a reason and write the AI value
to `ai_score` before the manual value lands.



### Item 11 — deprecation warnings in tests: FIXED
The four `datetime.utcnow()` calls in `tests/test_auth_phase1.py` now use
the timezone-aware `utcnow()` helper. Zero `datetime.utcnow()` remain in
the test suite.

### Item 1 — Alembic established as authoritative: DONE
- `alembic.ini` — URL read from `DATABASE_URL` via `env.py`, never
  committed
- `alembic/env.py` — `render_as_batch` enabled for SQLite so the
  migration **tests exercise the same files that run against production
  Postgres**, rather than a different code path
- `alembic/versions/0001_baseline.py` — deliberate no-op. Production
  already holds the v2.8/RC1 schema from `create_all()`, so it is adopted
  with `alembic stamp 0001_baseline` rather than recreated
- `alembic/versions/0002_phase2_model.py` — the full Phase 2 schema,
  additive only, with a complete `downgrade()`
- `alembic>=1.13` added to requirements

**Baseline strategy** (documented in the migration itself):
- *Existing DB:* `alembic stamp 0001_baseline` → `alembic upgrade head`
- *Clean DB:* `create_all()` → `alembic stamp head`

### Item 2 — persistent Phase 2 model: DONE
**17 normalised tables**, plus 9 classification columns on `opportunities`:

*Evidence* — `opportunity_evidence`, `evidence_claims`
*Analysis* — `opportunity_analysis_items` (facts / interpretation /
assumptions / gaps / verification actions, type-discriminated)
*Scoring* — `score_assessments`, `score_factors`, `pursuit_priorities`
*Qualification* — `qualification_assessments`,
`qualification_checklist_items`, `qualification_blockers`,
`qualification_overrides`
*Value* — `commercial_values` (programme and contract value as separate
columns, so a national strategy figure can never be read as money
available to VECTA)
*AI* — `ai_parse_failures`
*Legacy* — `legacy_opportunity_data`
*Audit* — `override_audits`
*Multi-valued* — `opportunity_contributing_verticals`,
`opportunity_secondary_commercial_types`, `opportunity_routes_to_market`

**JSON audit — 3 columns, all legitimate:** `weights_used` (weighting
snapshot at calculation time), `validation_errors` (diagnostic payload),
`legacy_score_breakdown` (frozen historical snapshot). Every material,
filterable field is a real indexed column.

*Verified:* migration creates exactly the 17 tables the models declare —
no drift in either direction — and `downgrade()` drops all 17 plus the 9
added columns and 4 indexes.

---

## PREVIOUS ITERATION

### 1. Failing authentication test — FIXED

`test_password_change_uses_fresh_salt_and_revokes_all_sessions` returned
403. **The test was wrong; the implementation was right.**

Cause: the test called `login()` twice on the *same* `TestClient`. A
TestClient holds one cookie jar, so the second login overwrote the first
session's cookie — while the test still sent the *first* session's CSRF
token. The 403 was correct: a CSRF token only validates against the
session that issued it. The test was simulating something that cannot
happen in a real browser, where a second session means a second cookie
jar.

Fixed by using an independent `TestClient` for the second session, plus
three new tests making the intended semantics explicit:

- `test_concurrent_sessions_are_independent` — the single authorised
  account may hold several concurrent sessions; logging in from a second
  browser does **not** invalidate the first, and each session gets its
  own CSRF token
- `test_csrf_token_is_bound_to_its_own_session` — session B's cookie with
  session A's CSRF is rejected; with its own CSRF, accepted
- `test_logout_of_one_session_leaves_the_other_active`

Password change still revokes **every** session, verified from both the
changing session and the bystander session.

### 2. Static API-key remnants — REMOVED REPOSITORY-WIDE

`frontend/Dockerfile` (3 occurrences) and `docker-compose.yml` (2) still
carried the build arg and env var; documentation in `SECURITY.md`,
`ENVIRONMENT.md`, `DEPLOYMENT.md` and `README.md` still described it as a
security layer.

**Verified sweep — zero active occurrences repository-wide:**

| Term | Occurrences |
|---|---|
| `NEXT_PUBLIC_ATLAS_API_KEY` | 0 |
| `ATLAS_API_KEY` | 0 |
| `X-API-Key` | 0 (one changelog line recording the removal) |
| `ApiKeyMiddleware` | 0 |

The database-backed session is now the sole authentication mechanism, in
code and in documentation.

### 3. Deprecation warnings — ADDRESSED (with one documented boundary)

- Pydantic `class Config` → `SettingsConfigDict`
- New `app/timeutils.py`: `utcnow()` (aware) and `as_aware()` coercion
- Auth/security tables now use `DateTime(timezone=True)`; all
  `datetime.utcnow()` removed from `models.py`, `security.py`,
  `qualification.py`, `evidence.py`
- Expiry comparisons coerce before comparing

**Why the coercion is load-bearing, not cosmetic:** SQLite (the test
database) drops tzinfo on round-trip and returns naive datetimes, while
Postgres `TIMESTAMPTZ` returns aware ones. Comparing the two raises
`TypeError` — verified. Without coercion the auth path would crash on
every request under SQLite. Four regression tests added covering aware
`utcnow()`, coercion behaviour, the raising comparison, and both absolute
and idle expiry after the change.

**Documented boundary:** business-table timestamps (opportunities,
interactions, scan_runs) remain naive. Their columns are naive `DateTime`
holding existing production data; converting them requires a real
`ALTER COLUMN TYPE TIMESTAMPTZ` migration, which is Alembic work in item
4. Making the Python side aware while the columns stay naive would create
exactly the mixed-comparison bug this change set out to remove, so they
are deliberately left until the migration exists.

Test count: **40** (was 32 + 1 failing).

---

## COMPLETE AND VERIFIED IN EARLIER PACKAGES

### Design corrections (spec items 1–5) — all four addressed

**1. Factor direction corrected**
Four factors sat in higher-is-better dimensions while being negatively
phrased, so a high score was ambiguous. Renamed to their positive form:

| Was | Now | 100 now means |
|---|---|---|
| Mobilisation requirement | **Mobilisation efficiency** | minimal mobilisation burden |
| Cost to pursue | **Pursuit-cost efficiency** | very low pursuit cost |
| Potential partner revenue share | **Retained revenue potential** | VECTA retains substantially all revenue |
| Procurement complexity | **Procurement accessibility** | simple, open process |

Every one of the 39 factors now carries explicit **0 / 50 / 100 anchors**
describing what each level means. These live in `scoring_v2.py` as the
single source of truth, so the UI and the AI prompt cannot drift apart.
Risk remains the deliberate exception — inverted as a whole dimension,
every factor phrased so 100 = most risk.

*Verified:* weights still sum to exactly 1.0 in all four dimensions; all
39 factors have complete anchors; zero occurrences of the four old keys.

**2. Incomplete assessments governed**
- Coverage bands: <50% "Provisional — insufficient assessment",
  50–79% "Provisional", 80–100% "Assessed"
- `coverage_percent` returned on every dimension for display beside the
  headline score
- Below 80% coverage in any dimension caps Pursuit Priority at "Review" —
  no unrestricted Immediate/High Priority on partial data
- **Risk gets a stricter rule:** where material risk factors are
  unassessed, the score is suppressed entirely and replaced with
  **"Risk not established"** plus an uncertainty note. A partially
  assessed risk score would render as a reassuringly low number, which is
  worse than showing nothing.

*Verified:* a risk assessment at 24% coverage computing to 8 displays as
"Risk not established", not 8. Low coverage caps a 95 to 69/"Review" with
the uncapped score preserved and the reason stated. Full coverage +
qualified still reaches 95/"Immediate Priority".

**3. Qualification outcomes refined into four failure types**
`absolute_disqualifier` / `remediable_blocker` /
`unresolved_mandatory_question` / `non_material_concern`.

Absolute bars (permanent Disqualified): not live, deadline passed with no
valid extension, no credible source, prohibited from participating,
legally or reputationally unacceptable, outside all verticals, impossible
route to market.

Remediable blockers (→ Conditionally Qualified, **not** permanent
disqualification): local entity not yet secured, delivery partner not yet
appointed, consortium required, accreditation/prequalification obtainable,
partner-dependent delivery.

*Verified:* eligibility failure → Disqualified; local entity not secured →
Conditionally Qualified with the blocker named; deadline passed with a
valid extension → Qualified; prohibited participation → Disqualified.

**4 & 5. Evidence rules enforced in the backend, with claim-level links**
New `backend/app/evidence.py`:
- Evidence declares **which specific claims** it supports (existence,
  live status, issuing organisation, deadline, published value,
  eligibility, geographic scope, procurement route, programme
  description). Evidence with no declared claims is rejected outright.
- `is_fact_verified(records, claim)` only returns true when *checked*
  evidence supports *that* claim — so an official tender notice proving
  an opportunity exists does **not** validate an AI's guess at its value.
- `validate_confirmed_opportunity()` enforces all six Confirmed
  requirements (Tier 1 or definitive Tier 2, live-status evidence,
  validated URL, publication date or documented reason, last-verified
  timestamp, confidence assessment) in the **service layer** — not the
  prompt, not the frontend.
- Unsupported Confirmed claims are **downgraded** to Unverified Lead with
  the reason recorded, rather than the finding being discarded.

*Verified:* Tier 1 notice supporting existence returns false for
published_value; a Tier 3-only record with an unreviewed URL produces all
five expected failures and downgrades correctly.

### Earlier (carried forward from v2.9-alpha, unchanged)
All five Phase 1 cleanup items — API-key feature removed repo-wide,
multi-user remnants cleared from schema.sql/seed.py with a safe
`owner_name` migration path, outdated auth docs replaced, security tests
decoupled from the AI stack, in-memory lockout limitation documented.

---

## NOT BUILT — do not treat as delivered

- **Item 6, database model** — the engines are complete and verified, but
  the normalised tables that persist them do not exist yet. This is the
  single biggest remaining piece and everything below depends on it.
- **Item 7, Alembic migrations** — no formal migration framework yet;
  the project still uses startup ALTER TABLE, which the spec correctly
  says is insufficient for the Phase 2 model.
- **Item 8, AI output contract** — strict versioned schema, validation
  before persistence, parse-failure preservation.
- **Item 9, scan pipeline** — the eleven-step flow.
- **Item 10, frontend** — cards, the sixteen detail sections, written
  labels for every state.
- **Item 11, manual editing UI.**
- **Item 12, committed automated tests** — the behavioural checks above
  were executed directly during this build and all passed, but they are
  **not yet committed as pytest tests**. That conversion is required
  before Phase 2 can close.
- **Item 13, documentation deliverables** — the factor anchors exist in
  code but the guides are not written.

**Item 14 completion standard: not met.** Four of its twelve conditions
currently hold (no estimated value shown as fact — enforced by
`ValueStatus.is_fact`; no Confirmed without evidence — enforced by
`evidence.py`; no high priority bypassing qualification or coverage —
enforced by `scoring_v2.py`; no risk score with insufficient evidence
reading low — enforced by the risk-not-established rule; and no
multi-user or static-key functionality has returned). The remaining
conditions depend on the unbuilt layers.

---

## Deployment

Safe to deploy or hold. The Phase 2 modules are pure additions that
nothing imports yet, so runtime behaviour is unchanged from v2.8 apart
from the Phase 1 cleanup. Both services must redeploy together (CORS
allowed-headers changed when X-API-Key was removed).

## Rollback

Redeploy `atlas-vecta-v2.8.zip` over both folders. The `owner_name`
columns persist harmlessly and are ignored by v2.8.
