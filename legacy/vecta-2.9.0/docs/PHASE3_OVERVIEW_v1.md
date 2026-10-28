# ATLAS Phase 3 — Architecture

**Foundation:** v2.9 (validated, frozen)
**Principle:** every capability must improve executive decision-making,
increase win probability, strengthen strategic positioning, or reduce
pursuit risk. If it does not help VECTA decide what to do next, it is not
built.

---

## 1. The integration contract

Phase 3 builds **on** v2.9, not into it. Four things stay untouched:

**Security.** Single login, PBKDF2 hash, DB-backed sessions, CSRF,
lockout. Every new endpoint sits behind the existing middleware and
inherits it. No Phase 3 feature introduces a second authentication path,
a service account, or a public endpoint.

**The service layer as the only write path.** New modules call
`opportunity_service`. Nothing writes Phase 2 tables directly — the eight
business rules live there, and a module that bypassed them would bypass
evidence enforcement and the qualification gate with it. The static AST
guard in the test suite already fails the build if the scanner does this;
the same guard extends to new modules.

**The evidence framework.** Any Phase 3 claim about an opportunity, an
organisation or a person is subject to the same discipline: tiered
sources, claim-level linkage, fact separated from interpretation from
assumption. This is the constraint that most shapes Phase 3, and it is
the one most likely to feel inconvenient. It should not be relaxed.

**Additive schema only.** New tables and new nullable columns. No Phase 2
table is restructured. Alembic remains authoritative; every change is a
migration with a tested downgrade.

### Extension points already built

| Point | What it enables |
|---|---|
| `DEFAULT_PRIORITY_WEIGHTS` in `scoring_v2.py` | Commercial Profile overrides the 35/30/25/10 weighting |
| Factor `anchors` | Profile can restate what 0/50/100 mean for VECTA specifically |
| `Contact` model + `relationship_strength` / `decision_maker_access` factors | Relationship Intelligence feeds Win Probability |
| `OverrideAudit`, `OpportunityActivity` | Timeline reads existing history; nothing new to capture |
| `serialise_opportunity()` | One place to extend the API/frontend contract |
| `outcome_reason`, Won/Lost stages | Win/loss analysis has data to work from |

---

## 2. Workstreams

### 2.1 VECTA Commercial Profile — **first, and a prerequisite**

Everything else depends on it. Right now "geographic priority" and
"target contract value" are scored against assumptions baked into a
prompt. Until those are *yours*, every score is a well-structured guess.

New tables: `commercial_profile` (single row, mirroring the single-login
model), `profile_capability`, `profile_priority`, `profile_partner`,
`profile_credential`, `profile_exclusion`, `profile_history`.

Integration: `scoring_v2.compute_pursuit_priority()` already accepts a
`weights` argument. The profile supplies it. Factor anchors gain optional
profile-specific text injected into the AI prompt, which is generated
from the engines rather than hand-maintained — so the prompt follows
automatically.

**Decision value:** changes what surfaces at the top of the list. Direct.

**Design note:** profile changes must not silently rewrite historical
scores. Scores are versioned (`model_version`, `last_scored_at`); a
profile change marks affected opportunities as due for rescoring rather
than mutating them. Otherwise last month's decisions become
unreconstructable.

### 2.2 Relationship Intelligence

Win Probability already has `relationship_strength` and
`decision_maker_access` as weighted factors. Today the AI guesses them.
This makes them real.

New tables: `stakeholder` (extends `Contact` with role classification —
economic buyer, technical evaluator, gatekeeper, blocker),
`relationship_edge` (person↔organisation, person↔person, with strength
and provenance), `interaction_log` (extends existing `Interaction`).

Integration: a scoring input, not a parallel system. Where a stakeholder
map exists, those two factors are scored from data and marked
evidence-backed; where it does not, they fall back to AI assessment and
say so.

**Constraints carried forward:** public and compliant sources only. No
LinkedIn scraping, no automated connection requests. Relationship
strength is a claim like any other and needs evidence.

**Decision value:** makes an existing score honest. High.

### 2.3 Executive Intelligence Dashboard

Replaces the Control Panel. The test is whether it answers "what do I do
this week" — the current panel reports status instead.

Content, all derived from existing tables:
- Top 5 actions this week (Pursuit Priority + deadline urgency + open
  verification actions)
- Awaiting review (`requires_human_review`)
- Deadlines within 30 days
- Qualification bottlenecks (stuck at Verification Required, with the
  specific unanswered items)
- Stale opportunities needing revalidation
- Risk exposure, including *unestablished* risk
- AI spend

**Design note:** every component links to the action that resolves it.
A dashboard that reports a problem without a route to fixing it is the
same dead-end the qualification gate had before v2.9.

**New schema:** none. This is a query and presentation layer.

### 2.4 Commercial Strategy Engine

Given the profile, the pipeline and win/loss history: where should VECTA
concentrate? Vertical and geographic concentration, capability gaps
blocking otherwise-attractive opportunities, partner dependencies,
whitespace.

Integration: reads Phase 2 data plus the profile. Writes
`strategy_insight` records with the evidence they rest on — a strategic
recommendation is a claim and gets the same treatment as any other.

**Decision value:** shapes where effort goes. Real, provided
recommendations cite their basis rather than asserting.

### 2.5 Executive Reporting

Deliberately **narrow**. Twelve report types were specified; most would be
opened once. Two change behaviour:

- **Win/loss analysis** — recalibrates scoring weights against actual
  outcomes. This is how the four dimensions stop being estimates.
- **Opportunity ageing** — stops valuable work dying quietly.

A weekly briefing is worth building if it is genuinely a decision digest.
The remaining nine are deferred until someone asks for one twice.

### 2.6 Opportunity Timeline

Chronological view per opportunity: discovery, evidence added, score
changes, qualification transitions, overrides, stage moves, interactions.

**New schema:** none. `OverrideAudit`, `OpportunityActivity`,
`QualificationOverride`, `ScoreAssessment.last_scored_at` and
`Interaction` already hold it. This is a read model.

**Decision value:** moderate — mainly "why did we conclude that?" during
review. Cheap because the data exists.

### 2.7 Predictive Opportunity Engine — **deferred, and here is why**

This is the one workstream I would not build now.

ATLAS's entire Phase 2 design exists because *published* opportunities
are hard to verify. Predicting unannounced ones means generating claims
with no possible Tier 1 source. The evidence model would correctly
classify every output as `unverified_lead` — so the feature would produce
confident-looking records the platform is designed to distrust.

It becomes sound when there is **Won/Lost history to calibrate against**.
At that point it is forecasting from VECTA's own outcomes — evidenced,
falsifiable, and genuinely predictive — rather than speculation dressed
as intelligence.

**Recommendation:** revisit after 2.5 has accumulated outcome data.
Building it earlier risks undermining the trust the evidence model exists
to create.

---

## 3. Sequencing

| Order | Workstream | Depends on |
|---|---|---|
| 1 | Commercial Profile | v2.9 |
| 2 | Executive Dashboard | v2.9 (profile improves it) |
| 3 | Relationship Intelligence | v2.9 |
| 4 | Opportunity Timeline | v2.9 |
| 5 | Win/loss + ageing reports | Outcome data |
| 6 | Commercial Strategy Engine | 1, 5 |
| 7 | Strategic recommendations | 1, 6 |
| — | Predictive Engine | 5 (deferred) |

Profile first because it changes what every other module sees. Dashboard
second because it delivers visible value quickly and exercises the
profile. Predictive last, if at all.

---

## 4. Non-negotiables

Carried from v2.9 and not open for renegotiation in Phase 3:

1. **Single login.** No accounts, roles, registration or invitations.
2. **No browser-exposed secrets.**
3. **Manual-only AI cost.** New features must not introduce background
   API calls. Any scheduled capability defaults off and states its cost.
4. **Evidence discipline.** Strategic recommendations and relationship
   claims are claims: sourced, tiered, with fact separated from
   inference.
5. **No estimate presented as fact.** The `is_published_fact` /
   `is_estimate` distinction extends to every new numeric output.
6. **Service layer is the only write path.**
7. **Additive migrations only**, each with a tested downgrade.
8. **No score without an explanation.**

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Profile changes silently rewriting history | Version scores; flag for rescoring rather than mutating |
| Relationship data drifting into non-compliant collection | Public sources only; no scraping; evidence rules apply |
| Dashboard becoming a status display | Every component must link to a resolving action |
| Strategy engine asserting without basis | `strategy_insight` records cite evidence, same as opportunities |
| Report sprawl | Build two; defer the rest until asked twice |
| Predictive engine undermining evidence trust | Deferred until outcome data exists |

---

## 6. Definition of done

A Phase 3 workstream is complete when:

- schema changes are Alembic migrations with tested downgrades
- all writes route through the service layer
- committed tests cover the behaviour, running without a live AI key
- the frontend renders it with written labels, not colour alone
- documentation states what it does and what it does not
- **it demonstrably changes a decision** — the standard set at the outset,
  and the one worth holding hardest when a feature is technically
  interesting but operationally inert
