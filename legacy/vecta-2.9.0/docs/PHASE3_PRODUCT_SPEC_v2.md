# ATLAS Phase 3 — Product Specification v2

**Status: DESIGN AUTHORITY.** Supersedes `PHASE3_PRODUCT_SPEC.md` (v1).
Every Phase 3 design and engineering decision is measured against this
document.

**Companion:** `PHASE3_ARCHITECTURE.md` — data model, migrations,
services, security. Not repeated here.

---

## 1. Product vision

> **ATLAS is an Executive Commercial Intelligence Platform. Its purpose
> is to help VECTA Sports make better strategic decisions faster than
> anyone else.**

It is not a CRM, an opportunity tracker or a reporting platform. Those
describe *what data it holds*. This describes *what it is for*.

The operational test remains: **does it become the first application
opened each morning?** That is falsifiable, and §11 makes it an
acceptance criterion.

---

## 2. The seven Executive Outcomes

Every capability must contribute to at least one. These are referenced by
code throughout this document.

| Code | Outcome |
|---|---|
| **EO1** | Identify commercial opportunities earlier |
| **EO2** | Increase win probability |
| **EO3** | Improve executive prioritisation |
| **EO4** | Strengthen strategic relationships |
| **EO5** | Reduce pursuit risk |
| **EO6** | Improve allocation of time, people and capital |
| **EO7** | Surface decisions before they become problems |

---

## 3. Decision-first design

Every screen is named for the question it answers, not the object it
holds. This is not cosmetic: a screen called "Opportunities" invites a
list, and a list makes you do the prioritisation ATLAS should be doing.

| Was | Becomes | Question answered |
|---|---|---|
| Dashboard | **Briefing** | What changed since yesterday, and what should we do about it? |
| Opportunities | **What deserves attention** | Which opportunities deserve executive attention today? |
| Relationships | **Who should we reach** | Which relationship would most improve our probability of winning? |
| Reports | **Board decisions** | What decisions should the Board make this week? |
| Organisations | *(removed — see §6)* | — |
| Regional Search | *(folded into scanning)* | — |

### 3.1 Information hierarchy — enforced, not aspirational

Every screen, card and panel presents in this order:

```
1. DECISION            what to do
2. WHY IT MATTERS      one paragraph, plain language
3. EVIDENCE            what supports it, with tier and source
4. RISKS               what could go wrong, including the cost of waiting
5. RECOMMENDED ACTION  specific, owned, dated
6. SUPPORTING DETAIL   collapsed by default
```

**Rule:** nothing above level 5 may require scrolling on a 1440×900
screen. If a card cannot state its decision, reasoning, evidence, risk and
action in one view, the card is doing too much.

This inverts the v2.9 opportunity detail page, which currently presents
overview → evidence → facts → scores → qualification, and reaches the
recommendation last. That ordering asks you to derive the decision
yourself.

---

## 4. Traceability matrix

The instruction was: *if a feature cannot be linked to a meaningful
executive outcome, remove it or redesign it.* Applied honestly, that
means the matrix must cut things — otherwise it is decoration.

### 4.1 Retained — clear outcome linkage

| Feature | Outcome | Decision supported | Business value |
|---|---|---|---|
| **Briefing** | EO3, EO7 | What do I do today? | Replaces 20 min of searching with a 2 min read; surfaces problems while they are still cheap |
| **Change feed** ("what changed") | EO3, EO7 | What is different, and does it matter? | Movement is the signal; static state is not |
| **Staleness detection** | EO7 | What am I losing by not acting? | Opportunities die quietly. This is the only mechanism that catches it |
| **Decision Cards** | EO2, EO3, EO5 | Pursue, partner, influence, monitor, defer, decline? | Converts analysis into a decision with an owner and a date |
| **Commercial Profile** | EO3, EO6 | Is this right *for VECTA*? | Without it every score is generic. This is what makes scoring specific |
| **Opportunity cost model** | EO5, EO6 | What does pursuing cost us elsewhere? | Prevents pursuing everything at once — the commonest failure of pipeline tools |
| **Relationship gaps + paths** | EO2, EO4 | Who should we reach, and how? | 25% of Win Probability is relationship-derived and currently guessed |
| **Win-probability levers** | EO2 | What would actually improve our odds? | Turns a score into an action |
| **Lifecycle timeline** | EO1, EO2 | Where is this, and is influence still possible? | Stages 1–6 are pre-publication — the only window where scope can be shaped |
| **Predictive engine** | EO1 | What is coming before it is published? | Published tenders are usually too late to influence |
| **Prediction calibration** | EO1, EO5 | Should we trust these predictions? | Without it the engine is unfalsifiable |
| **Strategic Memory** | EO3, EO5, EO7 | Why did we conclude that, and what changed? | Makes past decisions defensible and assumptions reviewable |
| **AI Advisor** | EO3, EO6 | Ad-hoc executive questions | Answers questions not anticipated by a screen |
| **Capacity view** | EO6 | Can we actually deliver what we are pursuing? | Prevents winning work VECTA cannot staff |
| **Weekly Executive Brief** | EO3, EO7 | What should the Board decide? | Board-ready without preparation time |
| **Relationship Gap Report** | EO2, EO4 | Where is our access weakest? | Directly actionable |
| **Predictive Report** | EO1 | What is emerging, and is the engine accurate? | Includes its own accuracy — rare and important |

### 4.2 Removed — failed the test

| Feature | Why it fails | Disposition |
|---|---|---|
| **Organisations screen** | Answers "who exists", which is not a decision. Every genuine use is reached via an opportunity or a stakeholder | **Removed.** Organisation data remains; the browsing screen does not |
| **Regional Search as a destination** | It is an *action* (run a scan), not a place. Having it as a nav item invites aimless scanning, which costs money | **Removed as a screen.** Becomes a scan action from the Briefing, cost stated |
| **Kanban pipeline board** | Shows state, not decisions. Attractive, rarely acted on | **Removed as default.** Available as a view within "What deserves attention" |
| **Intelligence Feed (raw)** | An undifferentiated feed is noise. The change feed already carries material changes | **Removed.** Merged into the change feed with a materiality threshold |
| **Markets to Watch (as proposed)** | "Saudi Arabia is active" supports no decision on its own | **Redesigned** → "Markets where we are under-invested relative to activity" (EO6). Now actionable |
| **9 of 12 report types** | Most reports are opened once; several are slices of the same data | **Deferred** until requested twice |
| **Visual relationship graph** | A picture of a network is impressive and rarely decisive | **Deferred.** The seven answers change behaviour; the graph does not |
| **Configurable dashboard widgets** | Configuration is a way of avoiding the decision about what matters | **Removed** |
| **Notification/email digests** | Trains you to ignore them. The Briefing is the notification | **Removed** |
| **Bulk editing** | Optimises for administration, which is the thing being removed | **Removed** |

### 4.3 Redesigned — outcome present but weakly served

| Feature | Problem | Redesign |
|---|---|---|
| **Opportunity detail** | Reaches the recommendation last | Reordered to the §3.1 hierarchy: decision first, supporting detail collapsed |
| **Reports** | Static exports | Board-level decision papers with claim-level evidence classification |
| **Score display** | Shows a number | Shows the number, its coverage, and the levers that would move it |
| **Qualification checklist** | A form | A gate that states what is blocking and what resolves it |

---

## 5. Strategic Memory

Executives care about **movement**, not state. "Win probability is 65" is
inert. "Win probability fell 12 points because a competitor secured the
local partner we were pursuing" is a decision trigger.

### 5.1 What is remembered

| Remembered | Already stored in v2.9? | Gap |
|---|---|---|
| Previous scores | ✓ `ScoreAssessment` (current only) | Need history rows |
| Previous recommendations | — | New: `strategy_recommendation` supersession |
| Previous decisions | — | New: `decision_record` append-only |
| Previous assumptions | ✓ `OpportunityAnalysisItem` (current) | Need validity tracking |
| Previous forecasts | — | New: `predicted_opportunity.outcome` |
| Relationship changes | — | New: `relationship_edge` history |
| Manual overrides | ✓ `OverrideAudit` | Complete |
| Stage transitions | — | New: `lifecycle_transition` |

### 5.2 Additional schema

```
score_history                 -- snapshot on every material change
  id, opportunity_id, dimension, score, coverage, profile_version
  changed_at, change_reason (rescore|profile_change|manual_override|
                             evidence_added)
  delta_from_previous

assumption_ledger             -- assumptions with a lifecycle
  id, opportunity_id, assumption_text, basis
  status (active|validated|invalidated|expired)
  validated_at, validated_by_evidence_id, invalidated_reason
  review_due_at                -- assumptions decay
  affects_recommendation_ids

change_event                  -- the unified feed powering "what changed"
  id, subject_type, subject_id, event_type
  materiality (high|medium|low)
  summary, previous_value, new_value, occurred_at
  triggered_by (scan|profile_change|manual|time_elapsed)
```

**`change_event` is the load-bearing table.** Everything in the Briefing's
"what changed" comes from it, materiality-filtered, and it is written by
the computed layer — no AI call.

### 5.3 The question Strategic Memory answers

> *"Why did we decline the Qatar opportunity in March?"*

Answerable because: `decision_record` holds the recommendation and your
response, `inputs_snapshot_json` holds the values it reasoned from,
`profile_version` identifies the criteria in force, and
`assumption_ledger` shows which assumptions were active and whether they
have since been invalidated.

**That last part is the highest-value piece.** An assumption that has been
invalidated since a decision was made is a reason to revisit it — and
nothing in ATLAS currently surfaces that.

---

## 6. Commercial opportunity cost

Scores tell you how attractive something is. They do not tell you what
pursuing it costs, and that is what makes prioritisation real: VECTA
cannot pursue everything, so the relevant question is not "is this good?"
but "is this better than what it displaces?"

### 6.1 Four costs, on every priority opportunity

| Cost | Composed from | Expressed as |
|---|---|---|
| **Cost of pursuing** | Bid effort + mobilisation + specialist time + travel + partner fees | Currency + specialist-days |
| **Cost of delaying** | Stage window closing + competitor positioning + requirement lock-in | Win-probability points lost per week |
| **Cost of not pursuing** | Strategic account impact + market position + precedent value + capability signal | Qualitative + strategic-objective impact |
| **Strategic objective impact** | Mapped to profile objectives | Which objectives advance, by how much |

### 6.2 Schema

```
opportunity_cost
  id, opportunity_id
  pursuit_cost_currency, pursuit_cost_specialist_days
  pursuit_cost_basis
  delay_cost_win_prob_per_week, delay_cost_window_closes_at
  delay_cost_basis
  non_pursuit_strategic_impact, non_pursuit_basis
  displaced_opportunity_ids     -- what this pursuit would crowd out
  profile_version, computed_at, confidence
```

### 6.3 Why `displaced_opportunity_ids` matters

Given delivery capacity in the profile and specialist requirements per
pursuit, ATLAS can identify **which pursuits compete for the same
people**. That converts "we are at 82% capacity" — a statistic — into
"pursuing Saudi means deferring Kenya, because both need the same two
coach-education specialists in September" — a decision.

This is EO6 in its most concrete form, and it is the piece most pipeline
tools lack entirely.

---

## 7. Executive AI Advisor

An adviser, not a chatbot. The distinction is real: a chatbot answers
whatever is asked, from whatever it can retrieve. An adviser answers from
a known evidence base and tells you how confident it is.

### 7.1 Design constraints

1. **Grounded only in ATLAS data.** It does not browse or speculate
   beyond stored evidence. If the answer is not in the data, it says so.
2. **Every response classifies its claims** — verified fact · AI
   interpretation · assumption · prediction · recommendation — using the
   same visual language as the rest of the platform.
3. **Every response cites sources**, linked and tier-labelled.
4. **Cost stated before answering.** Consistent with manual-only.
5. **Answers are not authoritative.** The advisor surfaces and reasons; it
   does not decide.

### 7.2 The questions it must answer well

| Question | Data | Outcome |
|---|---|---|
| What should I focus on this week? | Priority × urgency × decisions waiting | EO3 |
| Which five deserve executive attention? | Priority + stage window + cost of delay | EO3 |
| Why has win probability changed? | `score_history` + `change_event` | EO2 |
| Which relationships should we strengthen? | Gaps ranked by win-probability gain | EO4 |
| Where are we under-investing? | Profile priorities vs pipeline distribution | EO6 |
| Which markets are becoming important? | Signal accumulation vs profile priorities | EO1 |
| What assumptions are weakening our recommendations? | `assumption_ledger` where status = invalidated or review overdue | EO5 |

That last one is the most valuable and least common. It is the question
that catches a recommendation built on something no longer true.

### 7.3 Response format

```
┌──────────────────────────────────────────────────────────────────┐
│ Q: What assumptions are weakening our recommendations?            │
├──────────────────────────────────────────────────────────────────┤
│ Three active recommendations rest on assumptions that have        │
│ weakened since they were made.                                    │
│                                                                   │
│ ▪ VERIFIED   Saudi Coach Education — the assumed 3-year term is   │
│              contradicted by the RFP pack (2 years + option).     │
│              Commercial Attractiveness may be overstated.         │
│              [Etimad RFP · Tier 1 · 12 Jul ▸]                    │
│                                                                   │
│ ▫ ASSUMPTION Kenya Youth Pathways — assumes federation            │
│   (unvalidated) restructuring completes by Q4. No evidence since  │
│              May. Review overdue by 34 days.                      │
│                                                                   │
│ ◇ PREDICTION India coach education — horizon assumed 9–18 months. │
│              Now month 14 with no procurement signal.             │
│                                                                   │
│ → RECOMMENDED  Re-verify the Saudi contract term before the       │
│                11 Aug decision. It changes the value basis.       │
│                                                                   │
│ Profile v4 · 3 sources · generated 28 Jul 06:14 · est. $0.02      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Screens, restated as questions

| Screen | Question | Outcomes | Priority |
|---|---|---|---|
| **Briefing** | What changed, and what do I do today? | EO3, EO7 | P0 |
| **Decisions** | What is waiting for my judgement? | EO3, EO7 | P0 |
| **Decision Card** | Should we pursue this, and why? | EO2, EO3, EO5 | P0 |
| **What deserves attention** | Which opportunities warrant executive time? | EO3, EO6 | P0 |
| **Opportunity detail** | What is behind this recommendation? | EO5 | P0 |
| **Commercial Profile** | What is VECTA, and is it complete? | EO3, EO6 | P0 |
| **Who should we reach** | Which relationship most improves our odds? | EO2, EO4 | P1 |
| **What is coming** | What is emerging before publication? | EO1 | P1 |
| **Timeline** | Where is this, and can we still influence it? | EO1, EO2 | P1 |
| **Board decisions** | What should the Board decide this week? | EO3, EO7 | P2 |
| **Advisor** | Anything not anticipated by a screen | EO3, EO6 | P2 |

Eleven screens, each named for a question. No screen exists to display an
object type.

---

## 9. Updated roadmap

| # | Milestone | Outcomes | Why here |
|---|---|---|---|
| **3.1** | Commercial Profile | EO3, EO6 | Everything downstream is evaluated against it |
| **3.2** | Computed layer · change_event · Briefing | EO3, EO7 | The daily-open habit starts here |
| **3.3** | Decision Cards + opportunity cost | EO2, EO3, EO5, EO6 | Briefing without cards is half a product |
| **3.4** | Strategic Memory (history, assumptions) | EO3, EO5, EO7 | Cards need "what changed" to be useful |
| **3.5** | Relationship Intelligence | EO2, EO4 | Converts 25% of Win Probability to evidence |
| **3.6** | Timeline | EO1, EO2 | Pre-publication window becomes visible |
| **3.7** | Predictive + calibration | EO1 | Earliest identification |
| **3.8** | AI Advisor | EO3, EO6 | Needs the memory layer to answer well |
| **3.9** | Board decision papers | EO3, EO7 | Composes everything above |

**Changed from v1:** Strategic Memory moves to 3.4, ahead of
Relationships. Decision Cards depend on "what changed" to be worth
opening daily — a card that cannot say *why* the recommendation moved is
substantially less useful, and retro-fitting history is harder than
building it early.

---

## 10. Governance — unchanged from Phase 2

Every AI output carries: source evidence · timestamp · model identifier ·
confidence · **profile version** · owner review action.

Claim classification extends to every new surface — advisor responses,
decision cards, reports, predictions:

```
verified fact → evidence → AI interpretation → assumption
                              → prediction → recommendation
   (most grounded)                        (least grounded)
```

Recommendations and decisions are superseded, never overwritten.
Assumptions carry a review date and decay. Predictions retain their
outcome permanently, including when wrong.

---

## 11. Acceptance criteria

### Outcome coverage
1. Every shipped feature maps to ≥1 Executive Outcome in the §4 matrix
2. No screen exists that displays an object type rather than answering a
   question
3. Every screen presents in the §3.1 hierarchy: decision before detail

### Product
4. Briefing loads in **under 1.5 seconds**
5. Briefing requires **zero AI calls**
6. Every card carries owner, decide-by date, and cost of inaction
7. Every priority opportunity carries all four opportunity costs
8. Every recommendation states evidence, assumptions, confidence, risks,
   cost of waiting, and improvement actions
9. "What changed" answerable for any score, recommendation or decision
10. Invalidated assumptions surface against affected recommendations
11. Predictions structurally separated from verified opportunities

### Technical
12. No Phase 2 table restructured
13. Security model unchanged; single login preserved
14. All writes through the service layer
15. Full suite passes without a live AI key
16. Every recommendation and decision carries a profile version

### The real test
17. **ATLAS is opened before email for two consecutive weeks.**

If 1–16 pass and 17 does not, the product has failed and the design needs
revisiting — not more features.

---

## 12. Open questions — carried forward, still needing your call

1. **Decide-by dates** — computed with one-click override, or always
   owner-set? My inclination: computed, since friction at the point of
   decision is what stops decisions being made.
2. **Decision queue volume** — cap at 5, or show all ~20–30? My
   inclination: cap, because a queue of 30 is a backlog, not a briefing.
3. **Declined opportunities** — should they resurface once if
   circumstances materially change? My inclination: yes, once, with the
   change stated. Otherwise one early "no" becomes permanent.

New, arising from this revision:

4. **Opportunity cost precision.** Cost of pursuing needs bid effort and
   specialist-day estimates. Should ATLAS estimate these from comparable
   past pursuits, or should you supply defaults in the Commercial Profile?
   Estimated is faster and initially inaccurate; supplied is accurate and
   more setup.
5. **Advisor scope.** Restricted to the seven questions in §7.2, or open
   free-text? My inclination: start restricted. A known-good set of
   answers builds trust; an open box invites questions the data cannot
   support, and a confidently wrong answer early would undermine the
   platform's credibility more than a narrow one would limit it.

---

## Appendix A — features removed, with reasoning

Kept visible rather than quietly dropped, so the decisions can be
challenged:

| Removed | Reasoning | Reversible? |
|---|---|---|
| Organisations screen | Answers "who exists", not a decision | Yes — data retained |
| Regional Search as a destination | An action, not a place; invites costly aimless scanning | Yes — action retained |
| Kanban board as default | Shows state, not decisions | Yes — available as a view |
| Raw intelligence feed | Noise; change feed covers material movement | Yes |
| 9 of 12 reports | Opened once; overlapping data | Yes — on second request |
| Visual relationship graph | Impressive, rarely decisive | Yes — model supports it |
| Configurable widgets | Avoids the decision about what matters | Yes |
| Email/push digests | Trains you to ignore them | Yes |
| Bulk editing | Optimises for admin, the thing being removed | Yes |

## Appendix B — what changed from v1

| Change | Reason |
|---|---|
| Traceability matrix added, with genuine removals | A matrix where everything passes is not a test |
| Strategic Memory promoted to a first-class layer | Movement matters more than state |
| Opportunity cost model added | Scores say "attractive"; cost says "instead of what" |
| AI Advisor specified | Answers questions no screen anticipated |
| Screens renamed as questions | A screen named for an object invites a list |
| Information hierarchy made enforceable | "Decision first" needs a rule, not an intention |
| Strategic Memory moved ahead of Relationships | Cards need "what changed" to be worth a daily open |
| Assumption ledger added | An invalidated assumption is a reason to revisit a decision |
