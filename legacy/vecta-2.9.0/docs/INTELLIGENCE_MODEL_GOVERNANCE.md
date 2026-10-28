# ATLAS Intelligence Models — Governance Specification

**Purpose:** these seven models are the platform's intellectual property.
This document is the specification a reviewer, auditor or future engineer
reads to understand what each model claims, how it computes it, and where
it can be wrong.

**Governance rule:** no model ships without every section below completed.
A model whose calculation cannot be explained is not IP — it is a liability
that will eventually produce a confident recommendation nobody can defend.

---

## Model register

| Code | Model | Question answered | Version | Module |
|---|---|---|---|---|
| **EFS** | Executive Focus Score | Where should executive time be invested today? | 1.0 | `app/focus_score.py` |
| **RCI** | Relationship Coverage Index | Do we know the right people? | 1.0 | `app/coverage_index.py` |
| **CRI** | Commercial Readiness Index | Are we genuinely ready to pursue this? | 1.0 | `app/readiness_index.py` |
| **RMI** | Relationship Momentum Index | Are relationships improving or deteriorating? | 1.0 | `app/relationship_health.py` |
| **DCS** | Decision Confidence Score | How confident should we be in this recommendation? | 1.0 | `app/readiness_index.py` |
| **SCE** | Scenario Engine | What are the alternatives and their consequences? | 1.0 | `app/scenario_engine.py` |
| **RHS** | Relationship Health Score | How strong is this relationship now? | 1.0 | `app/relationship_health.py` |

---

## EFS — Executive Focus Score

**Purpose.** Rank opportunities by where an hour of executive attention
changes the outcome. Explicitly **not** a measure of opportunity quality —
Pursuit Priority already does that.

**Inputs and weights** (sum = 1.000)

| Input | Weight | Source |
|---|---|---|
| Urgency | 0.20 | Deadline proximity, lifecycle stage |
| Strategic alignment | 0.16 | `ScoreAssessment` |
| Relationship readiness | 0.16 | Contact/stakeholder gaps |
| Commercial value | 0.14 | `CommercialValue` vs profile thresholds |
| Win probability | 0.12 | `ScoreAssessment` |
| Qualification | 0.10 | `QualificationAssessment` |
| Evidence quality | 0.07 | Evidence tiers |
| Delivery capacity | 0.05 | Commercial Profile |

**Calculation.** Weighted sum, then an **actionability gate**: if executive
action cannot change the outcome (submitted, evaluated, disqualified,
deadline passed, non-actionable classification), the score collapses to 0
with a stated reason.

**Deliberate inversions** — these look wrong and are not:
- *Weak evidence scores HIGH.* Verification is an action worth taking.
- *`verification_required` scores 90; `qualified` scores 15.* Blocked-but-
  resolvable is where attention pays; qualified work needs nothing.
- *`disqualified` scores 0.* Not because it doesn't matter — because
  attention cannot change it.

**Non-linearity.** Urgency is stepped, not linear: 90 vs 60 days barely
affects today's decision; 10 vs 5 is decisive. A linear scale would spread
attention evenly across a quarter.

**Known limitations.** Relationship readiness currently infers seniority
from contact role text where no stakeholder is mapped. Capped and labelled
inferred. `competing_pursuits` is hardcoded to 0 pending capability
mapping.

**Test coverage.** `TestExecutiveFocusScore` — 6 tests. Critical:
`test_focus_differs_from_opportunity_quality`.

---

## RCI — Relationship Coverage Index

**Purpose.** Assess whether VECTA has meaningful coverage across the buying
ecosystem, and name **which kind** of gap exists.

**Inputs and weights** (sum = 1.000)

| Role | Weight | Critical |
|---|---|---|
| Executive sponsor / economic buyer | 0.26 | ✓ |
| Decision maker (budget holder) | 0.20 | ✓ |
| Procurement contact | 0.16 | ✓ |
| Technical evaluator | 0.14 | |
| Operational champion | 0.14 | |
| Political sponsor | 0.10 | |

**Role states.** unknown (0) → identified (35) → contacted (60) → engaged
(85) → advocating (100). Identification alone is not coverage.

**The defining feature — three gap types:**

| Gap | Meaning | Verb |
|---|---|---|
| **Intelligence** | We do not know who holds this role | Identify |
| **Execution** | We know them, never engaged | Contact |
| **Relationship** | Engaged, but weak or declining | Repair |

A single percentage conflates all three; the actions differ completely.

**Modifiers** capped at ±12: warm introduction (+6), recent engagement
(+4), healthy relationships (+4), declining relationships (−4 each).

**Unsupplied roles count as unknown.** A role absent from the input is
treated as `unknown`, not omitted. An earlier version excluded them from
the gap list, producing *"Weak coverage (36). All roles covered and
healthy."* — found by calibration.

**Critical-role cap.** One unmapped critical role caps the score at 55;
two or more at 35. A weighted average would flatter a pursuit that has no
route to a decision.

**Test coverage.** `TestRelationshipCoverageIndex` — 7 tests. Critical:
`test_distinguishes_three_gap_types`, `test_unmapped_critical_role_caps_the_score`.

---

## CRI — Commercial Readiness Index

**Purpose.** Whether VECTA is genuinely ready to pursue. Readiness is not
attractiveness — an opportunity can be highly attractive and completely
unready, which is the most expensive combination in pursuit management.

**Inputs and weights** (sum = 1.000)

| Dimension | Weight | Why it matters |
|---|---|---|
| Qualification completeness | 0.22 | An unqualified pursuit may be ineligible or already lost |
| Relationship maturity | 0.20 | Bidding without access means writing to an unverified brief |
| Evidence quality | 0.18 | Weak evidence means the opportunity may not be as described |
| Delivery capability | 0.16 | Winning work VECTA cannot deliver is worse than losing it |
| Resource availability | 0.14 | Bid effort competes with committed pursuits |
| Strategic alignment | 0.10 | Off-strategy wins consume on-strategy capacity |

**Blocking cap.** Any dimension below 40 is blocking. One blocker caps the
score at 59, two or more at 39. Fixes a real contradiction: an earlier
version reported *"Mostly ready. Blocked by relationship maturity"*, which
would let an executive commit resources to a pursuit that cannot proceed.

**Test coverage.** `TestCommercialReadinessIndex` — 5 tests. Critical:
`test_blocking_dimension_caps_the_band`.

---

## RMI — Relationship Momentum Index

**Purpose.** Direction of travel. Momentum predicts future outcomes better
than current strength — a relationship at 40 and rising is better news
than one at 70 and falling.

**Inputs.** A **series** of health readings (not a delta), plus leading
indicators: days since engagement, overdue follow-ups, responsiveness
change, scheduled engagement.

**Calculation.**
1. **Trajectory** — least-squares slope over the last five readings.
2. **Acceleration** — whether the slope itself is steepening.
3. **Leading indicators** — applied on top; these move *before* the score.

**States.** improving · stable · declining · **critical**.

`critical` requires a relationship that both **matters commercially**
(influence ≥ 70) **and is failing**. The word keeps its meaning.

**Why a series.** `80→70→60` and `50→70→60` both show "down 10" from the
previous reading but are opposite stories. A single `previous_score`
cannot distinguish them — this was a real model limitation found and fixed
in Sprint 2.

**Test coverage.** `TestRelationshipMomentumIndex` — 8 tests. Critical:
`test_trajectory_distinguishes_what_a_delta_cannot`,
`test_leading_indicators_move_before_the_score`.

---

## RHS — Relationship Health Score

**Purpose.** Current commercial strength of a relationship — not personal
rapport.

**Inputs and weights** (sum = 1.000)

| Factor | Weight | Note |
|---|---|---|
| Recency | 0.24 | Heaviest, because it erodes silently |
| Frequency | 0.16 | Sustained contact, not a single meeting |
| Responsiveness | 0.14 | The most honest signal |
| Meeting outcomes | 0.14 | Negatives weighted harder than positives |
| Influence | 0.14 | |
| Opportunity alignment | 0.10 | |
| Strategic value | 0.08 | |

**Decay.** Non-linear: ≤14 days = 100, 90 days = 45, 180+ = 5.

**At-risk override.** Influence ≥ 70 **and** recency ≤ 45 caps the score at
40 and flags at-risk. Fixes a real calibration bug: an economic buyer
untouched for 150 days scored 70 "Healthy" because high influence
*offset* poor recency. Influence must **amplify** the urgency of decay, not
offset it.

**Asymmetric outcomes.** Three positive meetings = 100; two positive and
one negative = 57. A meeting that goes badly is more informative than one
that goes pleasantly, and symmetric averaging reads a stalling
relationship as merely mixed.

---

## DCS — Decision Confidence Score

**Purpose.** Whether a recommendation should be believed. The model that
governs the others — without it, every recommendation carries identical
authority and the confidently wrong one is indistinguishable from the
well-evidenced one.

**Inputs and weights** (sum = 1.000)

| Factor | Weight | Source |
|---|---|---|
| Evidence quality | 0.28 | Tier and validation status |
| Data completeness | 0.24 | Score coverage, qualification, stakeholders |
| **Historical accuracy** | 0.22 | **Decision Journal outcomes** |
| Assumption load | 0.16 | Assumption ledger |
| Model certainty | 0.10 | Models available and agreeing |

**Advisory floor.** Below **40** (raised from 30 after RC2 calibration —
a single Tier 3 source with four assumptions scored 31 and was permitted to
advise), `should_advise = False` and the consuming
surface must state that ATLAS does not know enough — rather than present a
recommendation with false authority.

**Historical accuracy methodology.** Requires ≥10 scored outcomes.
Below that it returns a **neutral 50**, never a flattering default.
Claiming confidence because there is no contrary evidence *yet* is exactly
the failure this model prevents.

**Deliberate inversion vs EFS.** Weak evidence scores **low** here and
**high** in EFS. Different questions: "should you believe this" versus "is
there work to do". Conflating them would be a real bug, and there is a
test asserting both directions.

**Test coverage.** `TestDecisionConfidenceScore` — 8 tests. Critical:
`test_refuses_to_advise_below_the_floor`,
`test_no_history_returns_neutral_not_flattering`.

---

## SCE — Scenario Engine

**Purpose.** Model five commercial postures and their consequences, so an
executive can compare futures rather than accept a verdict.

**Scenarios.** pursue now · delay engagement · strengthen relationships
first · partner with another organisation · withdraw.

**Per scenario:** expected value, commercial impact, resource impact,
strategic impact, confidence, principal risks, rationale.

**Composite ranking.** `commercial × 22 + strategic × 10 + resource × 8 −
high_risks × 12 − other_risks × 4`, scaled by confidence.

**The governing principle.** Scenario analysis is theatre if one option
always wins. `test_engine_differentiates_across_situations` fails if the
engine stops producing at least three distinct recommendations across
realistic inputs.

**Value floor applies to every posture.** An earlier version applied the
minimum viable contract value only to `withdraw`'s scoring, so a £1.2m
opportunity against a £2m floor still returned "pursue immediately" — the
model knew the rule and did not apply it where it mattered. Found by
calibration.

**Two real bugs found by the differentiation test:**
1. *Withdrawal was structurally unreachable* — permanently negative
   commercial impact. But withdrawing from an unwinnable pursuit converts
   sunk effort into capacity for winnable ones.
2. *Time gated value but not feasibility* — the engine recommended
   "strengthen relationships first" with 18 days remaining. Feasibility now
   scales with the size of the gap: `30 + coverage_headroom × 0.6 +
   missing_critical_roles × 30` days.

**Partner modelling.** Margin share fixed at 0.65 (a joint bid typically
returns 60–70%). Partnering scores highest when access is missing **and**
time is short — you cannot build a relationship in 40 days but you can
borrow one.

**Test coverage.** `TestScenarioEngine` — 13 tests.

---

## Evidence weighting (cross-model)

Applied by `app/intelligence_pipeline.py`. Deliberately steep.

| Class | Weight | Tier |
|---|---|---|
| Signed document | 1.00 | High |
| Official announcement | 0.95 | High |
| Verified meeting / Tier 1 source | 0.90 | High |
| Confirmed stakeholder | 0.85 | High |
| Confirmed conversation | 0.60 | Medium |
| Tier 2 source | 0.55 | Medium |
| Internal note | 0.50 | Medium |
| Partner report | 0.45 | Medium |
| Tier 3 source | 0.25 | Low |
| AI observation | 0.15 | Low |
| Inferred relationship | 0.12 | Low |
| Assumption / Tier 4 | 0.10 | Low |

**Why steep.** One signed document (1.00) outweighs six AI observations
(0.90). An AI observation is a hypothesis; a signed document is a fact.
Gentle averaging would let volume of speculation outweigh a single hard
source.

**Unverified downgrade.** High-tier evidence not yet verified is
multiplied by 0.7 — a Tier 1 URL nobody has opened is a claim *about* a
source, not a source.

**Minimum to recommend:** 0.8 weighted total. Below that, `should_advise`
is false.

---

## Confidence methodology (cross-model)

Every model exposes:
- per-factor **contributions** with weight and note
- **weakest factors**, so "why is this low" is answerable
- **improvement levers**, so "what would raise it" is answerable

**No model returns a bare number.** `test_no_model_is_a_black_box` asserts
this for all five core models.

---

## Test coverage summary

| Model | Test class | Tests |
|---|---|---|
| EFS | `TestExecutiveFocusScore` | 6 |
| RCI | `TestRelationshipCoverageIndex` | 7 |
| CRI | `TestCommercialReadinessIndex` | 5 |
| RMI + RHS | `TestRelationshipMomentumIndex` | 8 |
| DCS | `TestDecisionConfidenceScore` | 8 |
| SCE | `TestScenarioEngine` | 13 |
| Pipeline | `TestIntelligencePipeline` | 8 |
| Framework | `TestIntelligenceFramework` | 5 |
| **Total** | | **60** |

Plus 175 tests across auth, Phase 2, migrations and executive intelligence.
**235 committed tests total.**

---

## Governance limitations — stated honestly

1. **No model has been executed.** All 235 tests are written and
   statically cross-verified; none has run. Every calibration claim in
   this document rests on static analysis and hand-traced examples.
2. **No model is calibrated against real outcomes.** DCS's historical
   accuracy input requires ≥10 scored decisions in the Decision Journal;
   there are none. Until then it returns neutral, which is honest but
   means the learning loop is inert.
3. **Weights are reasoned, not fitted.** They reflect commercial judgement
   about what matters, not regression against outcomes. That is the
   correct starting position, but they should be revisited once outcome
   data exists.
4. **RHS frequency cannot distinguish rhythm from clustering.** Twelve
   engagements across a year and twelve in one week score identically.
5. **Model interactions are not modelled.** Each model is independently
   computed; correlated errors (e.g. thin evidence depressing both DCS and
   CRI) are not adjusted for.

---

## Change control

- Every model carries `model_version`.
- Every score persists the version that produced it.
- Weight changes require a version increment and a test update.
- A model must not be modified without updating this document.
