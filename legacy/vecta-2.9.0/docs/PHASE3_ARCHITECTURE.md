# ATLAS Phase 3 — Architecture & Implementation Design

**Foundation:** v2.9 (validated, frozen)
**Status:** Design document — no implementation until approved
**Supersedes:** `PHASE3_OVERVIEW_v1.md` (earlier summary, retained)

---

## 1. Executive summary

Phase 2 made ATLAS trustworthy. Every opportunity carries its sources,
reasoning is separated from evidence, and nothing enters the pipeline
without passing a formal gate. That was necessary but not sufficient:
ATLAS currently tells you *what is true*, not *what to do*.

Phase 3 closes that gap with four additions:

1. **A definition of VECTA** — the Commercial Profile. Today, scores are
   computed against assumptions baked into a prompt. "Geographic
   priority" means whatever the model imagined. Until VECTA's actual
   strategy, thresholds and capacity are first-class data, every score is
   a well-structured guess.
2. **A map of influence** — Relationship Intelligence. Win Probability
   already weights `relationship_strength` (13%) and
   `decision_maker_access` (12%). The AI currently guesses both. This
   does not add a score; it makes a quarter of an existing one honest.
3. **A forward view** — Predictive Engine and Opportunity Timeline.
   Published tenders are usually too late to influence. The commercial
   advantage sits eighteen months earlier, in the strategy document and
   the budget line.
4. **A recommendation** — Commercial Strategy and Executive Decision
   engines, combining the above into a defensible "do this, because of
   this, by this date".

The organising discipline is unchanged and applies to everything new:
**a claim is not a fact**. Phase 3 adds two categories to that spectrum —
*predictions* and *recommendations* — and both must be as visibly
labelled, sourced and challengeable as an AI interpretation is today.

**One design position stated plainly.** The Predictive Engine is the
highest-value and highest-risk item here. Predictions are by construction
claims no Tier 1 source can support — they concern things that have not
happened. Designed carelessly it would fill ATLAS with confident-looking
records the platform is built to distrust, eroding the credibility Phase
2 earned. The design below therefore keeps predictions in a **separate
table with a separate lifecycle**, never in `opportunities`, and requires
every prediction to reach a recorded outcome. That last part matters
most: a prediction engine never scored against reality is a horoscope.
Section 10 specifies the calibration loop that prevents this.

---

## 2. Phase 3 objectives

| # | Objective | Measured by |
|---|---|---|
| 1 | Scores reflect VECTA's strategy, not generic assumptions | Every recommendation cites a Commercial Profile version |
| 2 | Home screen answers "what do I do this week" | Every dashboard block links to a resolving action |
| 3 | Relationship factors become evidence-backed | % of priority opportunities with a mapped decision-maker |
| 4 | Opportunities identified before publication | Median lead time from first signal to tender publication |
| 5 | Every meaningful opportunity has a recommended posture | % of qualified opportunities with a current recommendation |
| 6 | Recommendations auditable and reversible | 100% carry rationale, assumptions, confidence, profile version |
| 7 | Predictions never masquerade as facts | Zero predictions written to `opportunities` |
| 8 | Predictions calibrated against outcomes | Accuracy tracked and reported per signal type |

---

## 3. Proposed architecture

### 3.1 Layering

Phase 3 sits **above** Phase 2 and reads through it. Nothing in Phase 3
writes a Phase 2 table directly.

```
┌────────────────────────────────────────────────────────────┐
│  PHASE 3 — DECISION LAYER                                  │
│                                                            │
│  Executive Decision Engine                                 │
│      ↑ reads all below, writes decision_record             │
│  Commercial Strategy Engine      Executive Reporting       │
│      ↑                                ↑                    │
│  Relationship   Predictive     Opportunity   Commercial    │
│  Intelligence   Engine         Timeline      Profile       │
│      │              │              │             │         │
├──────┼──────────────┼──────────────┼─────────────┼─────────┤
│      ↓              ↓              ↓             ↓         │
│  PHASE 2 — INTELLIGENCE LAYER (frozen)                     │
│  opportunity_service  ← the only write path                │
│  scoring_v2 · qualification · evidence · taxonomy          │
│  17 normalised tables                                      │
├────────────────────────────────────────────────────────────┤
│  PHASE 1 — SECURITY (frozen)                               │
│  single login · PBKDF2 · DB sessions · CSRF · lockout      │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Integration rules

1. **Service layer remains the only write path.** New services call
   `opportunity_service`; they never touch Phase 2 tables directly. The
   existing static AST guard extends to every new module, so a bypass
   fails the build rather than silently skipping evidence enforcement.
2. **Additive schema only.** New tables and nullable columns. No Phase 2
   table restructured. Every change is an Alembic migration with a tested
   downgrade.
3. **Security inherited, not extended.** New endpoints sit behind the
   existing `SessionAuthMiddleware`. No new auth path, no service
   account, no public endpoint.
4. **Evidence discipline extends to every new claim.** A relationship
   strength, a prediction and a recommendation are all claims: sourced,
   confidence-rated, with fact separated from inference.
5. **Manual-only AI cost.** No Phase 3 feature introduces background API
   calls. Anything schedulable defaults off and states its cost first.

### 3.3 Profile versioning — the load-bearing decision

The Commercial Profile changes what every score *means*. If a profile
edit silently rewrote existing scores, past decisions would become
unreconstructable — you could not answer "why did we decline that?"
because the criteria would have moved underneath the record.

**Rule:** a profile change never mutates an existing score,
recommendation or decision. It marks affected records **stale** and
queues them for rescoring. Every score, recommendation and decision
stores `profile_version`. Historical records remain readable against the
profile that produced them.

This costs some complexity and buys the ability to defend a past
decision — the right trade for a platform whose purpose is executive
judgement.

---

## 4. Data-model additions

All new tables. No Phase 2 table altered except by nullable additive
columns where noted.

### 4.1 Commercial Profile

```
commercial_profile
  id, version (int, monotonic), is_active
  strategic_objectives, revenue_objective, growth_priorities
  risk_appetite (conservative|balanced|aggressive)
  min_viable_contract_value, target_contract_value
  max_mobilisation_exposure
  target_gross_margin, min_gross_margin
  delivery_capacity_fte, current_workload_pct
  created_at, created_reason, superseded_at

profile_priority_region       region, market, tier(1-3), rationale
profile_priority_account      organisation_name, account_type
                              (government|federation|club|brand), tier
profile_target_type           commercial_type, priority_weight
profile_sector                sector, is_target
profile_delivery_model        model, is_preferred
profile_route_preference      route_to_market, preference (1-5)
profile_capability            capability, strength(0-100),
                              specialist_count, is_specialist_scarce
profile_partner               partner_name, capability,
                              relationship_strength, regions, is_active
profile_required_capability   capability, why_needed,
                              acquisition_route (build|partner|acquire)
profile_geographic_limit      region, market, limitation, reason
profile_exclusion             exclusion_type (sector|commercial_type|
                              region|counterparty), value, reason
profile_strategic_account     organisation_id, objective, owner_name
profile_weighting             dimension, weight
                              -- overrides DEFAULT_PRIORITY_WEIGHTS
profile_factor_anchor         factor_key, anchor_0, anchor_50, anchor_100
                              -- VECTA-specific restatement
profile_change_log            field_path, previous_value, new_value,
                              reason, changed_at
```

**Single active row**, mirroring the single-login model. Editing creates
a new version and supersedes the previous; nothing is destroyed.

### 4.2 Relationship Intelligence

```
stakeholder                   -- extends Contact, does not replace it
  id, contact_id (nullable FK), organisation_id, full_name, role_title
  stakeholder_type (economic_buyer|programme_sponsor|budget_holder|
    procurement_authority|technical_evaluator|technical_influencer|
    political_sponsor|gatekeeper|potential_blocker|adviser|consultant|
    delivery_partner|local_partner|competitor|introducer)
  decision_authority (final|significant|advisory|none|unknown)
  seniority, region, market
  source_evidence_id (FK opportunity_evidence)
  confidence, is_verified, created_at, last_reviewed_at

relationship_edge
  id, from_type (vecta|stakeholder|organisation|partner), from_id
  to_type, to_id
  edge_type (employs|reports_to|advises|partners_with|competes_with|
             knows|introduced_by|former_colleague|board_member)
  strength (0-100), strength_basis, confidence
  is_vecta_relationship, is_partner_held
  owner_name  -- informational text, not an account
  last_engagement_at, next_action, next_action_due
  evidence_id, risk_note, conflict_note
  created_at, last_reviewed_at

introduction_path             -- derived, cached
  id, opportunity_id, target_stakeholder_id
  path_json (ordered hops), hop_count, weakest_link_strength
  is_viable, computed_at, profile_version

opportunity_stakeholder       -- per-opportunity context
  opportunity_id, stakeholder_id, relevance
  engagement_status (not_engaged|contacted|meeting_held|advocating|blocking)
  last_engagement_at, next_action, owner_name

relationship_gap              -- computed
  id, opportunity_id, gap_type (no_decision_maker|no_procurement_contact|
    no_introduction_path|no_local_partner|single_point_dependency)
  severity, recommended_action, computed_at
```

**Additive to Phase 2:** none. `Contact` is referenced, not modified.

### 4.3 Predictive Opportunity Engine

```
market_signal                 -- raw observed signal, evidence-first
  id, signal_type (government_strategy|sector_plan|federation_restructure|
    funding_announcement|budget_approval|national_programme|
    coach_education_initiative|youth_strategy|infrastructure_plan|
    consultation|rfi|market_sounding|leadership_appointment|policy_change|
    event_award|partner_announcement|procurement_pattern)
  title, summary, organisation_name, region, market
  observed_at, source_tier, evidence_id (FK opportunity_evidence)
  confidence, is_verified, superseded_by_opportunity_id, created_at

predicted_opportunity         -- DELIBERATELY NOT in `opportunities`
  id, predicted_type (commercial_type), commissioning_organisation
  predicted_title, rationale
  time_horizon_months_min, time_horizon_months_max, horizon_basis
  confidence (high|medium|low), confidence_basis
  likely_route_to_market, likely_value_min, likely_value_max, value_basis
  primary_vertical (+ contributing verticals join table)
  recommended_early_action, required_relationships
  profile_version, model_version, generated_at
  status (active|superseded|expired|converted|rejected)
  converted_opportunity_id (nullable)
  outcome (correct|partially_correct|incorrect|too_early)
  outcome_recorded_at, outcome_note

prediction_signal             prediction_id, signal_id, contribution_note

prediction_calibration        -- the accountability loop
  id, period_start, period_end
  predictions_made, converted, expired_unconverted
  accuracy_rate, mean_horizon_error_months
  by_signal_type_json, computed_at
```

**Why a separate table, restated:** a prediction has no verified live
status, no confirmed deadline, no Tier 1-confirmed issuing organisation.
Placing it in `opportunities` would either force it through a
qualification gate it cannot pass, or require weakening that gate. The
separation is what allows predictions to be useful *and* honest.

### 4.4 Opportunity lifecycle

```
lifecycle_stage_definition    -- seeded reference data
  key, ordinal (1-17), label, description
  typical_duration_days, is_pre_publication
  recommended_actions, required_capabilities

opportunity_lifecycle
  id, opportunity_id (nullable), predicted_opportunity_id (nullable)
  current_stage, previous_stage, expected_next_stage
  estimated_next_stage_date, stage_confidence
  entered_current_stage_at, evidence_id, rationale
  recommended_action, relationship_actions_required
  documents_required, capabilities_required
  profile_version, updated_at

lifecycle_transition          -- append-only
  id, lifecycle_id, from_stage, to_stage, transitioned_at
  evidence_id, was_predicted, days_in_previous_stage, source, reason
```

Applies to both real and predicted opportunities — which is what makes
the seventeen-stage model useful, since stages 1–6 are pre-publication.

### 4.5 Strategy & decisions

```
strategy_recommendation
  id, opportunity_id (nullable), predicted_opportunity_id (nullable)
  posture (lead|pursue_directly|pursue_with_partner|build_consortium|
    secure_local_partner|influence_early|introduce_capability|monitor|
    defer|decline|invest_in_capability|acquire_capability|
    seek_strategic_introduction)
  rationale, key_assumptions, missing_information, major_risks
  next_decision_date, owner_name, confidence
  inputs_snapshot_json      -- immutable record of what it reasoned from
  profile_version, model_version, generated_at
  status (active|superseded|accepted|edited|rejected)
  superseded_by_id, reviewed_at, review_note

recommendation_factor         -- transparent reasoning
  recommendation_id, factor (profile_fit|score|qualification|evidence|
    win_probability|relationship|delivery_capability|resource_capacity|
    margin|mobilisation|geographic_risk|legal_risk|partner_requirement|
    strategic_value|timing)
  assessment, influence (supports|opposes|neutral), weight, note

decision_record
  id, subject_type (opportunity|predicted_opportunity|account|market)
  subject_id, question
  recommended_action, rationale, timing, owner_name
  must_verify_first, cost_of_waiting, risk_of_pursuing,
  risk_of_not_pursuing, win_probability_levers
  confidence, evidence_summary
  profile_version, model_version, generated_at
  owner_response (accepted|edited|rejected|deferred)
  owner_note, responded_at, superseded_by_id
```

### 4.6 Executive Reporting

```
executive_report
  id, report_type, period_start, period_end
  title, executive_summary
  content_json              -- structured sections, not rendered HTML
  key_changes, implications, decisions_required,
  recommended_actions, risks
  profile_version, model_version, generated_at
  generated_by (manual|scheduled), ai_cost_estimate, status

report_evidence_link
  report_id, claim_text
  claim_kind (verified_fact|ai_interpretation|assumption|prediction|
              recommendation)
  evidence_id (nullable), opportunity_id (nullable)
```

`report_evidence_link` is what makes a report a decision paper rather
than a summary: every claim is traceable to its kind and source.

### 4.7 Additive columns on Phase 2 tables (nullable only)

| Table | Column | Purpose |
|---|---|---|
| `opportunities` | `lifecycle_stage` | denormalised for list filtering |
| `opportunities` | `originating_prediction_id` | links a materialised prediction |
| `score_assessments` | `profile_version` | which profile produced this score |
| `score_assessments` | `is_stale` | flagged after a profile change |
| `pursuit_priorities` | `profile_version` | which weighting was applied |

---

## 5. New services

Modules under `app/services/`, following the v2.9 pattern.

| Service | Responsibility |
|---|---|
| `profile_service` | Versioned CRUD; supplies weights and anchors to scoring; flags stale scores |
| `relationship_service` | Stakeholders, edges, introduction paths, gaps; feeds Win Probability |
| `prediction_service` | Signal ingestion, prediction synthesis, conversion detection, calibration |
| `lifecycle_service` | Stage inference, transitions, next-stage estimation |
| `strategy_service` | Rule-driven posture with factor-level reasoning |
| `decision_service` | Composes decision records |
| `report_service` | Report composition with claim-level evidence links |
| `dashboard_service` | Read-only aggregation for the briefing |

**Boundary:** `opportunity_service` remains the only writer of Phase 2
tables. Where a Phase 3 service needs a Phase 2 change — relationship
data improving a Win Probability factor, for instance — it calls
`opportunity_service.override_score()` or the rescoring path, so evidence
rules, coverage governance and the override audit all still apply.

---

## 6. API additions

All behind the existing session middleware; mutations require CSRF.

```
# Commercial Profile
GET    /profile                        active profile, expanded
GET    /profile/versions               version history
GET    /profile/versions/{version}     a historical profile
POST   /profile                        new version (reason required)
PATCH  /profile/{section}              section edit -> new version
GET    /profile/impact                 what a pending change would restale

# Dashboard
GET    /dashboard/executive            full briefing
GET    /dashboard/actions              priority actions only
GET    /dashboard/changes?since=       what changed

# Relationships
GET    /relationships/stakeholders
POST   /relationships/stakeholders
PATCH  /relationships/stakeholders/{id}
GET    /relationships/edges
POST   /relationships/edges
GET    /opportunities/{id}/relationships        the seven answers
GET    /opportunities/{id}/introduction-paths
GET    /relationships/gaps

# Predictions
GET    /predictions
GET    /predictions/{id}
POST   /predictions/generate                    manual, cost-estimated
PATCH  /predictions/{id}                        review/accept/reject
POST   /predictions/{id}/convert                link to a real opportunity
GET    /predictions/calibration                 accuracy over time
GET    /signals
POST   /signals                                 manual signal entry

# Lifecycle
GET    /opportunities/{id}/lifecycle
PATCH  /opportunities/{id}/lifecycle            manual correction
GET    /lifecycle/stages                        reference data

# Strategy & decisions
GET    /opportunities/{id}/recommendation
POST   /opportunities/{id}/recommendation/generate
PATCH  /recommendations/{id}                    accept|edit|reject
GET    /decisions
GET    /decisions/{id}
POST   /decisions/generate
PATCH  /decisions/{id}/respond

# Reporting
GET    /reports
POST   /reports/generate                        type + period, cost-estimated
GET    /reports/{id}
GET    /reports/{id}/export?format=pdf|csv
```

---

## 7. AI pipeline design

Three new pipelines, all following the v2.9 pattern: strict versioned
Pydantic schema, per-record validation, parse failures preserved with the
raw response, no bracket-slicing, manual trigger only.

### 7.1 Signal detection → prediction

```
manual trigger (cost shown)
  → scoped search prompt, generated from taxonomy + profile
  → strict schema validation (PredictionResponse v3.0)
  → per-record isolation of failures
  → evidence persistence (same tiering, same URL validation)
  → signal deduplication against existing market_signal
  → prediction synthesis: 1..n signals → 1 prediction
  → confidence from signal tier + corroboration + horizon distance
  → persist to predicted_opportunity (never to opportunities)
```

**Confidence is mechanical, not self-assessed.** A model asked to rate
its own confidence tends to rate it well. See §10.2.

### 7.2 Strategy recommendation

Not primarily an AI pipeline. Posture is **rule-driven** from profile,
scores, qualification, relationships and capacity; the AI writes the
rationale and surfaces assumptions and risks.

This split matters. A recommendation to decline a $4m opportunity should
be reproducible and inspectable, not a model's mood on the day. **Rules
decide; AI explains.**

### 7.3 Report composition

Structured data → AI-authored narrative → claim-level evidence linking.
Every sentence is classified as verified fact, interpretation,
assumption, prediction or recommendation and stored in
`report_evidence_link`. A report that cannot show its working is not a
decision paper.

---

## 8. Dashboard information architecture

Eight blocks, priority-ordered. Every block links to the action that
resolves it.

```
1. WHAT REQUIRES A DECISION      decision_records awaiting response
2. PRIORITY ACTIONS THIS WEEK    top 5, each with a one-click route
3. WHAT CHANGED                  new confirmed, probability moves,
                                 stage transitions, new signals
4. WHERE TO FOCUS                profile-aligned concentration,
                                 emerging countries/sectors
5. WHAT IS BLOCKED               qualification bottlenecks with the
                                 specific unanswered items;
                                 relationship gaps
6. WHAT IS AT RISK               deadlines <30d, evidence-quality risks,
                                 delivery-capacity strain,
                                 unestablished risk scores
7. WHAT IS COMING                predictions by horizon; lifecycle stages
                                 approaching publication
8. COMMERCIAL POSITION           pipeline value, weighted value,
                                 expected revenue, resource demand
```

**Explicitly excluded:** activity counts, scan statistics, contact
totals, vanity charts. Anything that does not change a decision belongs
in a report, not on the home screen.

---

## 9. Relationship model

For every priority opportunity, ATLAS answers seven questions from one
query across `stakeholder`, `relationship_edge` and
`opportunity_stakeholder`:

| Question | Source |
|---|---|
| Who decides? | `stakeholder_type` ∈ {economic_buyer, budget_holder}, `decision_authority` = final |
| Who influences? | technical_influencer, political_sponsor, adviser |
| Who controls procurement? | procurement_authority |
| Who can introduce VECTA? | shortest viable `introduction_path` |
| What exists already? | edges where `is_vecta_relationship` |
| What is missing? | `relationship_gap` rows |
| What next? | `opportunity_stakeholder.next_action`, ordered by decision authority |

**Introduction paths:** breadth-first search over `relationship_edge`,
capped at 3 hops, scored by weakest link, cached and recomputed on edge
change. A graph database is not warranted at this scale; if edges ever
exceed ~10⁵ the algorithm is isolated enough to swap.

**Visual graph:** the data model supports it; it is not an early
priority. A picture of a network is impressive and rarely decisive. The
seven answers change behaviour.

**Compliance:** public and compliant sources only. No LinkedIn scraping,
no automated connection requests. Relationship strength is a claim and
needs evidence like any other. Stakeholder records must be individually
deletable on request.

**Feeds Phase 2:** where a stakeholder map exists,
`relationship_strength` and `decision_maker_access` are scored from data
and marked evidence-backed; otherwise they fall back to AI assessment and
say so. This is the highest-leverage Phase 3 integration — it converts
25% of Win Probability from guess to evidence.

---

## 10. Predictive-engine methodology

### 10.1 Signal → prediction

Signals are observed and evidenced individually; predictions are
synthesised from one or more. The link is recorded, so any prediction
traces to what prompted it.

```
Signal A (Tier 1): National sport strategy published, coach education
                   named as a pillar
Signal B (Tier 2): Ministry budget approval, line item for coach
                   development
Signal C (Tier 3): Federation appoints a technical director with a
                   coach-education background
        ↓
Prediction: coach_education tender, Ministry of Sport,
            horizon 9–18 months, confidence medium
            (two independent sources, one Tier 1)
```

### 10.2 Confidence — mechanical

| Confidence | Requires |
|---|---|
| High | ≥2 independent sources, ≥1 at Tier 1–2, horizon ≤12 months, procurement-pattern precedent |
| Medium | ≥2 independent sources OR 1 Tier 1, horizon ≤24 months |
| Low | Single source, or Tier 3–4 only, or horizon >24 months |

### 10.3 Separation from verified opportunities — enforced

- Stored in `predicted_opportunity`, never `opportunities`
- Never included in pipeline value, weighted pipeline or forecasts
- Rendered in a visually distinct section labelled **"Predicted — not a
  verified opportunity"**
- Carry no qualification state (there is nothing to qualify)
- Cannot enter the active pipeline; conversion creates a **new**
  opportunity that passes the normal gate from scratch

### 10.4 Calibration — what makes it honest

Every prediction reaches an outcome: `converted`,
`expired_unconverted`, or manually marked `incorrect`.
`prediction_calibration` computes accuracy by signal type and mean
horizon error, reported in the Predictive Opportunity Report.

**If accuracy for a signal type falls below threshold, that signal type
is demoted or retired.** Without this loop the engine is unfalsifiable,
and an unfalsifiable prediction engine is worse than none — it produces
confident noise that crowds out real work.

---

## 11. Commercial Strategy Engine methodology

### 11.1 Rules decide, AI explains

Posture is selected by deterministic rules over profile, scores,
qualification, relationships and capacity. Same inputs always produce the
same posture. The AI writes rationale, assumptions and risks.

### 11.2 Selection logic (illustrative)

```
IF profile_exclusion matches               → decline
IF qualification = disqualified            → decline
IF value < min_viable_contract_value       → decline (monitor if strategic account)
IF mobilisation > max_exposure             → pursue_with_partner | decline
IF capability gap AND no partner           → invest_in_capability | acquire_capability
IF local_entity_required AND none secured  → secure_local_partner
IF consortium_required                     → build_consortium
IF lifecycle stage ≤ 6 (pre-publication)   → influence_early
IF win_probability ≥ 70 AND capacity ok    → pursue_directly | lead
IF strategic_account AND value marginal    → influence_early | monitor
IF no decision-maker relationship          → seek_strategic_introduction
IF delivery capacity strained              → defer | pursue_with_partner
ELSE                                       → monitor
```

Every rule that fires is recorded in `recommendation_factor` with its
influence, so reasoning is inspectable rather than asserted.

### 11.3 Required output

Recommended action · rationale · key assumptions · missing information ·
major risks · next decision date · owner · confidence — plus
`inputs_snapshot_json`, so a past recommendation remains intelligible
after the underlying data moves.

---

## 12. Opportunity lifecycle model

Seventeen stages; **1–6 are pre-publication** — the window where
influence is possible and where predicted opportunities live.

| # | Stage | Pre-pub | Typical VECTA action |
|---|---|---|---|
| 1 | Strategic signal | ✓ | Monitor, map stakeholders |
| 2 | Policy/strategy announcement | ✓ | Position capability |
| 3 | Funding indication | ✓ | Build relationships |
| 4 | Budget confirmation | ✓ | Seek introduction |
| 5 | Stakeholder consultation | ✓ | Participate, shape requirements |
| 6 | Market engagement | ✓ | Respond to RFI, demonstrate capability |
| 7 | Partner formation | | Secure consortium / local entity |
| 8 | Prequalification | | Prepare and submit PQQ |
| 9 | Tender preparation | | Assemble bid team |
| 10 | Tender publication | | Confirm go/no-go |
| 11 | Submission | | Submit |
| 12 | Evaluation | | Clarifications, references |
| 13 | Negotiation | | Commercial terms |
| 14 | Award | | Contract execution |
| 15 | Mobilisation | | Resource and start |
| 16 | Delivery | | Deliver, log performance |
| 17 | Expansion/renewal | | Identify follow-on |

Stage changes require supporting evidence. Every transition records
`days_in_previous_stage`, which over time replaces the seeded duration
estimates with real data.

---

## 13. Executive-reporting framework

Twelve report types are specified. **I recommend building three first**
and deferring the rest until one is asked for twice. My honest assessment
is that most reports in most systems are opened once, and report sprawl
carries real maintenance cost against little decision value.

**Build first:**
1. **Weekly Executive Brief** — the decision digest
2. **Predictive Opportunity Report** — including calibration accuracy,
   without which the engine is unaccountable
3. **Relationship Gap Report** — directly actionable

**Then, once outcome data exists:**
4. Pipeline Health · 5. Qualification and Risk · 6. Revenue Forecast

**Defer:** Country Intelligence, Government Activity, Delivery Capacity,
Strategic Account, Priority Opportunity, Monthly Board. Several are
slices of the same data and may be better served by dashboard filters.

Every report contains: executive summary · key changes · evidence ·
implications · decisions required · recommended actions · risks · owners ·
deadlines — each claim classified and linked via `report_evidence_link`.

---

## 14. Decision-engine logic

Composes a `decision_record` answering nine questions:

| Question | Derived from |
|---|---|
| What should VECTA do? | `strategy_recommendation.posture` |
| Why? | rationale + `recommendation_factor` rows |
| When? | lifecycle stage, deadline, `next_decision_date` |
| Who owns it? | profile strategic-account owner, or opportunity `owner_name` |
| What must be verified first? | open qualification items + missing information |
| Cost of waiting? | lifecycle progression + competitor positioning + deadline proximity |
| Risk of pursuing? | Risk score + mobilisation exposure + capacity strain |
| Risk of not pursuing? | strategic-account impact + market position + precedent value |
| What raises win probability? | lowest-scoring Win Probability factors with improvement actions |

**Constraint:** the engine does not decide. It presents evidence-backed
options with transparent reasoning and explicit uncertainty. The owner
accepts, edits, rejects or defers, and that response is recorded.
`decision_record` is append-only; superseded decisions are linked, never
overwritten.

---

## 15. Governance and audit model

The Phase 2 separation extends to the two new claim types:

```
verified fact → evidence → AI interpretation → assumption
                              → prediction → recommendation
   (most grounded)                        (least grounded)
```

Every AI-generated output carries: source evidence · generation timestamp
· model/process identifier · confidence · **profile version** · owner
review action (accept / edit / reject).

**Immutability rules:**
- Recommendations and decisions superseded and linked, never overwritten
- `inputs_snapshot_json` preserves what was reasoned from
- Manual overrides retain the original AI value, reason and timestamp
  (existing `OverrideAudit` extends to Phase 3 entities)
- Profile changes create versions; `profile_change_log` records
  field-level history
- Predictions retain their outcome permanently, **including when wrong** —
  that is the calibration data

---

## 16. Migration impact

- **All additive.** New tables plus nullable columns; no Phase 2 table
  restructured.
- Alembic revisions `0004`–`0011`, one per workstream, each with a tested
  downgrade.
- `lifecycle_stage_definition` seeded as reference data.
- **Backfill:** existing opportunities get `lifecycle_stage` inferred
  conservatively from `stage` (e.g. `discovered` → stage 10 "Tender
  publication"), flagged for review rather than asserted.
- **Profile bootstrap:** version 1 created empty on first startup with
  documented defaults matching current `DEFAULT_PRIORITY_WEIGHTS`, so
  behaviour is unchanged until the owner fills it in.
- Existing scores are **not** retroactively stamped with a profile
  version; they carry `profile_version = NULL`, meaning "scored before
  the profile existed", which is honest.

---

## 17. Security impact

**No change to the security model.**

- Single login preserved. No registration, invitations, teams, RBAC or
  approval chains.
- All new endpoints behind `SessionAuthMiddleware`; mutations require
  CSRF.
- `owner_name` fields remain informational text, not accounts.
- No new browser-exposed secrets.
- **New consideration:** relationship data is personal data. Public,
  compliant sources only; no scraping; no automated outreach. Stakeholder
  records carry the same evidence discipline and must be individually
  deletable on request.

---

## 18. Testing strategy

Following the v2.9 pattern: committed tests, no live AI key, offline
fixtures, deterministic.

| Area | Coverage |
|---|---|
| Profile | Versioning; supersession; weight override reaches scoring; stale flagging; change log |
| Scoring integration | Profile weights alter Pursuit Priority; historical scores unaffected by a profile change |
| Relationships | Stakeholder persistence; edges; path finding including no-path; gap detection; Win Probability becomes evidence-backed |
| Predictions | Schema validation; parse-failure isolation; mechanical confidence; **never written to `opportunities`**; conversion creates a freshly-gated opportunity; calibration arithmetic |
| Lifecycle | Stage inference from evidence; transition history; duration accumulation |
| Strategy | Each posture rule fires correctly; determinism; factors recorded |
| Decisions | All nine questions populated; supersession preserves history; owner response recorded |
| Reports | Claim classification; evidence links; no unattributed claim |
| Governance | Profile version on every output; overrides preserve originals; append-only enforced |
| Security | New endpoints reject unauthenticated and missing-CSRF requests |

**Guard tests** (build-failing, in the v2.9 tradition):
- No Phase 3 module writes a Phase 2 table directly (static AST check)
- No prediction reaches `opportunities`
- Every recommendation and decision carries a `profile_version`

---

## 19. Implementation phases

| Milestone | Workstream | Depends on | Deliverable |
|---|---|---|---|
| **3.1** | Commercial Profile | v2.9 | Schema, service, API, admin UI, scoring integration |
| **3.2** | Executive Dashboard | 3.1 | Read-only briefing, eight blocks, actions linked |
| **3.3** | Relationship Intelligence | v2.9 | Stakeholders, edges, paths, gaps, Win Probability integration |
| **3.4** | Opportunity Timeline | v2.9 | Lifecycle model, inference, transition history |
| **3.5** | Commercial Strategy Engine | 3.1, 3.3, 3.4 | Rule-driven postures with reasoning |
| **3.6** | Predictive Engine | 3.1, 3.4 | Signals, predictions, calibration |
| **3.7** | Executive Decision Engine | 3.5, 3.6 | Decision records, owner response |
| **3.8** | Executive Reporting | all | Three reports, claim-level evidence |

Each milestone: schema → service → API → frontend → tests → docs, and is
independently deployable.

---

## 20. Risks and limitations

| Risk | Severity | Mitigation |
|---|---|---|
| Predictions treated as pipeline | High | Separate table; excluded from value figures; distinct UI; calibration reporting |
| Prediction engine unfalsifiable | High | Mandatory outcome recording; signal types demoted on poor accuracy |
| Profile change rewrites history | High | Versioning; stale-flagging not mutation; `profile_version` on every output |
| Relationship data non-compliant | High | Public sources only; no scraping; evidence discipline; deletion path |
| Recommendations become oracle | Medium | Rules decide and are inspectable; AI only explains; owner response required |
| Dashboard becomes a status board | Medium | Every block links to a resolving action; operational stats excluded |
| Report sprawl | Medium | Build 3, defer 9 until asked twice |
| AI cost growth | Medium | Manual trigger only; cost estimate before generation |
| Scope creep back into Phase 2 | Medium | Additive-only rule; static guard tests |
| Introduction-path performance | Low | 3-hop cap, cached; algorithm isolated for later replacement |

**Honest limitations:**
- Predictions will be wrong. The value is in the *rate*, tracked
  explicitly. Expect the first two quarters to be poorly calibrated.
- Relationship data is only as good as what is entered; ATLAS cannot
  discover private relationships.
- Lifecycle durations are seeded guesses until real transition data
  accumulates.
- **The Commercial Profile requires genuine effort to complete.** A
  half-filled profile will produce worse recommendations than today's
  documented defaults, because it will look authoritative while being
  arbitrary. This is the main adoption risk in Phase 3.

---

## 21. Phase 3 acceptance criteria

1. Commercial Profile versioned and auditable; every recommendation cites
   a version
2. Profile weights demonstrably alter Pursuit Priority; historical scores
   unaffected
3. Dashboard answers all eight questions; every block links to an action
4. Relationship model answers all seven questions for any priority
   opportunity
5. `relationship_strength` and `decision_maker_access` evidence-backed
   where a map exists
6. Predictions in a separate table, excluded from pipeline value, visibly
   labelled
7. Prediction calibration computed and reported
8. Every meaningful opportunity carries a current posture with factor
   reasoning
9. Decision records answer all nine questions; owner response recorded
10. Three reports generate with claim-level evidence links
11. No Phase 2 table restructured; all migrations additive with tested
    downgrades
12. Security model unchanged; single login preserved
13. Full test suite passes without a live AI key
14. Guard tests prevent service-layer bypass and prediction leakage

---

## 22. Recommended build sequence

**Start with the Commercial Profile (3.1).** Everything downstream is
evaluated against it; building recommendations before ATLAS knows what
VECTA wants would mean rebuilding them afterwards.

Then **Dashboard (3.2)** — visible value quickly, and it exercises the
profile in a way that surfaces gaps early.

Then **Relationship Intelligence (3.3)** — the highest-leverage
integration, converting a quarter of Win Probability from guess to
evidence.

Then **Timeline (3.4)**, which Strategy and Predictive both need for
stage awareness.

**Strategy (3.5)** before **Predictive (3.6)**: postures on real
opportunities are immediately useful, and the recommendation framework is
then already in place when predictions arrive.

**Decision Engine (3.7)** and **Reporting (3.8)** last, as they compose
everything above.

---

## Appendix — deliberately not being built

| Not building | Why |
|---|---|
| Visual relationship graph (initially) | The seven answers change behaviour; the picture rarely does. Model supports it later |
| Nine of twelve reports | Most reports are opened once; defer until asked twice |
| Automated outreach | Compliance risk; ATLAS recommends, the owner acts |
| Multi-user workflow, approvals | Explicitly out of scope, permanently |
| Background AI scanning | Phase 2 cost discipline stands |
| Graph database | Not warranted at this scale; algorithm isolated if it ever is |
