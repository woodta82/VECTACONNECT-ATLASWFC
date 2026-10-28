# ATLAS Phase 3 — Executive Product Specification (v1, SUPERSEDED)

> **Superseded by `PHASE3_PRODUCT_SPEC_v2.md`**, which is the design
> authority. Retained for the wireframes in §4, which v2 references
> rather than repeats.

**Foundation:** v2.9 (frozen)
**Companion:** `PHASE3_ARCHITECTURE.md` — technical design, data model,
migrations. This document is product-led and does not repeat it.

---

## 0. The standard we are designing to

> *"Whether ATLAS becomes the first application I open each morning
> because it tells me what I need to know and what I should do next."*

That is a better specification than any feature list, because it is
falsifiable. Every design decision below is tested against it.

Three consequences follow immediately, and they shape everything:

**It must be fast.** If the morning brief takes eleven seconds to load,
it will lose to email. Target: **under 1.5 seconds** for the full
briefing. This forces a specific architecture — see §6.

**It must be fresh without being expensive.** Here is a real tension in
the brief, worth naming before it becomes a defect:

> A daily brief implies daily intelligence. But Phase 2's cost discipline
> is manual-only AI — no background API calls. Those look contradictory.

They are not, because **most of what changes overnight is not new
intelligence — it is the passage of time acting on existing data.** A
deadline moved from 31 days away to 30. An opportunity crossed 14 days
without movement. A qualification item has been unanswered for a week. A
prediction's horizon opened. None of that needs an AI call; all of it is
computed from data ATLAS already holds.

**Design rule:** the morning brief is *always* free and instant. AI
scanning remains manual, and the brief tells you when a scan would be
worth running — it never runs one for you. This preserves cost discipline
while still giving you something genuinely new every morning.

**It must never require searching.** If the answer is one click away, it
is one click too many. The brief pushes; you do not pull.

---

## 1. Executive Product Specification

### 1.1 What ATLAS becomes

| Today (v2.9) | Phase 3 |
|---|---|
| A place to look up opportunities | A daily briefing that finds you |
| Scores an opportunity | Recommends a decision on it |
| Tells you what is true | Tells you what to do about it |
| You search | It surfaces |
| Answers "is this real?" | Answers "what should VECTA do?" |

### 1.2 The three questions

Everything in Phase 3 serves three outputs, in this order:

1. **What should VECTA do?**
2. **Why?**
3. **What next?**

If a screen, panel or field does not contribute to one of those, it is
cut. This is applied literally in §2 and §3.

### 1.3 The nine morning questions

| Question | Answered by | Needs AI? |
|---|---|---|
| What changed overnight? | Change feed (diff since last visit) | No |
| Three things to focus on today? | Top 3 Decision Cards by urgency × value | No |
| Which organisations became more attractive? | Signal accumulation, profile match | No |
| Which probabilities moved? | Score deltas since last visit | No |
| What requires immediate action? | Deadlines, expiring windows, stalled gates | No |
| Which relationships need attention? | Engagement recency vs decision authority | No |
| Which risks appeared? | Risk deltas, coverage drops, evidence decay | No |
| What is being lost through inactivity? | Stale detection — **the quiet killer** | No |
| What decisions are waiting? | Unanswered Decision Cards | No |

**All nine are computable without a single API call.** That is what makes
a daily brief viable under manual-only cost discipline.

### 1.4 What we are deliberately not building

| Not building | Why |
|---|---|
| Notification/email digests | Push notifications train you to ignore them. The brief is the notification |
| Configurable dashboard widgets | Configuration is a way of avoiding the decision about what matters. We decide, you tell us if we are wrong |
| Kanban board as the primary view | A board shows state, not decisions. Available, not default |
| Bulk editing | Executive decisions are made one at a time. Bulk operations optimise for admin, which is the thing we are removing |
| Activity feed of everything | Noise. The change feed shows *material* changes only |

---

## 2. Complete information architecture

### 2.1 Navigation — four destinations, not eight

```
ATLAS
├── ▸ BRIEFING          (home — the morning read)
├── ▸ DECISIONS         (cards awaiting your response)
├── ▸ INTELLIGENCE      (opportunities · predictions · signals · relationships)
└── ▸ SETTINGS          (commercial profile · security · costs)
```

v2.9 has seven nav items — Control Panel, Opportunities, Regional Search,
Relationship Intelligence, Organisations, Reports, Settings. That is a
CRM's information architecture: organised by *object type*, which makes
you the router. You have to know that a decision lives inside an
opportunity which lives in a list.

Four destinations organised by *intent*: read the brief, make decisions,
investigate, configure. Reports move inside Briefing (a report is a
briefing over a longer period). Search becomes global rather than a
place.

### 2.2 Screen inventory

| # | Screen | Answers | Priority |
|---|---|---|---|
| 1 | **Briefing** | What changed, what matters today | P0 |
| 2 | **Decision queue** | What is waiting for me | P0 |
| 3 | **Decision card** | What should we do, why, what next | P0 |
| 4 | **Opportunity detail** | Everything behind the card | P0 (exists) |
| 5 | **Commercial Profile** | What is VECTA | P0 |
| 6 | Intelligence list | Investigate the pipeline | P1 (exists) |
| 7 | Relationship view | Who decides, who can introduce us | P1 |
| 8 | Prediction detail | What is coming, on what evidence | P1 |
| 9 | Timeline view | Where is this, what is next | P1 |
| 10 | Report viewer | Board-level decision paper | P2 |

### 2.3 Depth rule

Nothing important is more than **two clicks** from the Briefing.

```
Briefing → Decision Card → Opportunity Detail
   (0)          (1)               (2)
```

Everything else is investigation, reached from the card.

---

## 3. Executive Decision Cards

The centrepiece. A Decision Card is the atomic unit of Phase 3 — the
thing you read, decide on, and move past.

### 3.1 Design principles

**One card, one decision.** A card that asks two questions gets neither
answered.

**The recommendation leads.** Not the score. Scores are supporting
evidence for a recommendation, and putting them first makes you compute
the recommendation yourself — which is the work ATLAS should be doing.

**Always assign ownership and a date.** A recommendation with no owner
and no deadline is an observation. This is the single most common failure
of "insight" products.

**Always state the cost of inaction.** "What happens if nothing is done"
is the question that converts an interesting card into an acted-upon one.

**A card can be dismissed.** Rejecting a recommendation is a valid,
recorded decision — not a failure state to be nagged about.

### 3.2 Card anatomy

```
┌──────────────────────────────────────────────────────────────────┐
│ ⬤ IMMEDIATE PRIORITY          Confirmed opportunity · Tier 1 ✓   │
│                                                                   │
│ Saudi Ministry of Sport — National Coach Education Framework      │
│ VECTA Pathways · +2 contributing · MENA / Saudi Arabia            │
│                                                                   │
│ ▸ RECOMMENDED DECISION                                            │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │  PURSUE WITH PARTNER                    Confidence: MEDIUM │ │
│   └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ ▸ WHY                                                             │
│   Core Pathways work in a tier-1 priority market with a           │
│   government counterparty. Strategic fit is high (85) and the     │
│   deadline is achievable. A local entity is mandatory and VECTA   │
│   has none in Saudi Arabia, so a partner route is required        │
│   rather than optional.                          [3 sources ▸]   │
│                                                                   │
│ ▸ POSITION                                                        │
│   Strategic    85  ████████▌  Assessed 100%                       │
│   Commercial   70  ███████    Assessed 100%                       │
│   Win prob.    65  ██████▌    Assessed 100%                       │
│   Risk         35  ███▌       Assessed 100%                       │
│   Relationship  ◐ MODERATE — technical director known via         │
│                   partner; no economic buyer contact              │
│   Stage         6 · Market engagement  (pre-publication)          │
│                                                                   │
│ ▸ RISK OF WAITING                             ⚠ HIGH              │
│   Consultation closes in 18 days. After that, requirements are    │
│   fixed and VECTA's ability to shape scope drops to near zero.    │
│   Two competitors are already engaged.                            │
│                                                                   │
│ ▸ WHAT WOULD IMPROVE WIN PROBABILITY                              │
│   +12  Secure a local delivery entity        (largest single gain)│
│   +8   Reach the economic buyer before consultation closes        │
│   +5   Add a comparable national reference                        │
│                                                                   │
│ ▸ REQUIRED ACTIONS                                                │
│   1. Confirm eligibility from the full RFP pack        by 04 Aug  │
│   2. Approach [Partner] re local entity                by 08 Aug  │
│   3. Request introduction to the buyer via [Name]      by 11 Aug  │
│                                                                   │
│ ▸ OWNER   Tom Wood          ▸ DECIDE BY   11 August 2026          │
│                                                                   │
│ [ ACCEPT ]  [ EDIT ]  [ DEFER ]  [ DECLINE ]      [ Full detail ▸]│
│                                                                   │
│ Profile v4 · generated 28 Jul 06:00 · model 3.0                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 Field specification

| Field | Source | Rule |
|---|---|---|
| Priority band | `pursuit_priorities.band` | Restricted bands show the reason inline |
| Classification | `opportunities.classification` | With evidence status |
| Executive summary | AI, from structured data | One paragraph. Hard limit |
| Recommended decision | `strategy_recommendation.posture` | Rule-derived, never AI-chosen |
| Confidence | Computed | Mechanical, not self-assessed |
| Why | AI narrative over `recommendation_factor` | Every claim links to evidence |
| Four scores | `score_assessments` | Coverage always shown; Risk shows "Not established" where applicable |
| Relationship position | Computed from stakeholder map | Strong / Moderate / Weak / **Unknown** — unknown is honest and common |
| Stage | `opportunity_lifecycle` | Flags pre-publication, where influence is possible |
| Risk of waiting | Computed from stage + deadline + competitor signals | The field that drives action |
| Win-probability levers | Lowest-scoring factors with named actions | Quantified gain, ordered by size |
| Required actions | Ordered, each with a date | Maximum 3 on the card; rest in detail |
| Owner | Profile strategic-account owner, else opportunity owner | Never blank |
| Decide by | Computed from deadline, stage duration, action lead times | Never blank |
| Provenance | Profile version, timestamp, model version | Always visible, small |

### 3.4 Decision responses

| Response | Effect |
|---|---|
| **Accept** | Actions become tasks with dates and owner. Card leaves the queue |
| **Edit** | Owner amends posture or actions; original AI recommendation preserved |
| **Defer** | Card returns at a chosen date; recorded, not hidden |
| **Decline** | Recorded with reason. Opportunity remains searchable, exits active consideration |

Every response is appended to `decision_record`. Nothing is overwritten —
you can always reconstruct what was recommended, what you did, and why.

### 3.5 When a card is generated

Cards are generated for opportunities that are **qualified or
conditionally qualified**, and refreshed when:
- a score changes materially (>10 points on any dimension)
- qualification state changes
- lifecycle stage changes
- a relationship gap opens or closes
- the Commercial Profile version changes
- the decide-by date approaches (7 days out)

**Not** generated for unverified leads, market signals or intelligence
watch items. A decision card on an unverified lead would be asking you to
decide something ATLAS has not yet established is real.

---

## 4. Screen-by-screen wireframes

### 4.1 Briefing (home)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ATLAS                                    Tuesday 28 July · 06:14    │
│  ────────────────────────────────────────────────────────────────    │
│                                                                       │
│  GOOD MORNING. HERE IS WHAT CHANGED.                                 │
│                                                                       │
│  ▸ 3 opportunities moved stage    ▸ 2 probabilities changed          │
│  ▸ 1 new confirmed opportunity    ▸ 4 deadlines inside 30 days       │
│  ▸ 2 decisions awaiting you       ▸ 1 opportunity going stale        │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ① FOCUS TODAY                                                        │
│                                                                       │
│   1. Saudi Coach Education — consultation closes in 18 days           │
│      PURSUE WITH PARTNER · decide by 11 Aug        [ Open card ▸ ]   │
│                                                                       │
│   2. UEFA EURO 2028 Hospitality — win probability fell 12 pts         │
│      Competitor secured a local partner            [ Open card ▸ ]   │
│                                                                       │
│   3. ICC Women's T20 — no contact in 21 days, deadline 34 days        │
│      GOING STALE                                   [ Open card ▸ ]   │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│  ② DECISIONS WAITING (2)                                              │
│     Qatar Stadium Hospitality — DECLINE recommended    [ Review ▸ ]   │
│     Kenya Youth Pathways — INFLUENCE EARLY             [ Review ▸ ]   │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│  ③ WHAT CHANGED                                            [ all ▸ ] │
│     ↑ Saudi Arabia    3 new signals · 2 opportunities                 │
│     ↑ India           coach education strategy published (Tier 1)     │
│     ↓ Qatar           tender awarded to a competitor                  │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│  ④ RELATIONSHIPS NEEDING ATTENTION                                    │
│     ⚠ No economic buyer contact — Saudi Coach Education (18d window)  │
│     ⚠ 47 days since last engagement — Kenya federation                │
│     ○ Introduction available — UEFA via [Partner]      [ Details ▸ ]  │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│  ⑤ RISKS                                                              │
│     ⚠ Delivery capacity 82% — 3 pursuits assume the same specialists  │
│     ⚠ Risk not established on 4 opportunities (insufficient evidence) │
│     ⚠ 2 confirmed opportunities have unreviewed source URLs           │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│  ⑥ POSITION                    Pipeline    Weighted    Expected       │
│                                $22.8B      $2.3B       $4.1M          │
│                                                                       │
│     Last global scan: 6 days ago.   3 markets show new activity.      │
│     [ Run scan — est. $0.50 ]                                         │
└───────────────────────────────────────────────────────────────────────┘
```

**Design notes.** The header is a *diff*, not a status — it answers "what
changed" before you read anything else. "Focus today" is capped at three;
a list of ten is a list, not a focus. Scan cost is stated at the point of
decision, and the brief tells you scanning would be *worth* it rather
than doing it for you.

### 4.2 Decision queue

```
┌──────────────────────────────────────────────────────────────────────┐
│  DECISIONS                                    2 waiting · 1 deferred │
│  ─────────────────────────────────────────────────────────────────   │
│  [ Waiting (2) ]  [ Deferred (1) ]  [ Decided (34) ]                 │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ⬤ DECIDE BY 04 AUG  ·  6 days                                       │
│  Qatar Stadium Hospitality Partner                                    │
│  DECLINE  ·  Confidence HIGH                                          │
│  Below minimum viable contract value ($1.2M vs $2M floor) and no      │
│  strategic-account rationale. Pursuit cost is disproportionate.       │
│                                              [ Review card ▸ ]        │
│                                                                       │
│  ⬤ DECIDE BY 11 AUG  ·  13 days                                      │
│  Kenya Youth Development Pathways                                     │
│  INFLUENCE EARLY  ·  Confidence MEDIUM                                │
│  Pre-publication (stage 3). Federation restructuring creates a        │
│  window to shape requirements. No VECTA relationship yet.             │
│                                              [ Review card ▸ ]        │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.3 Commercial Profile

```
┌──────────────────────────────────────────────────────────────────────┐
│  COMMERCIAL PROFILE                    Version 4 · active since 12 Jul│
│  ─────────────────────────────────────────────────────────────────    │
│  ⓘ This profile determines how ATLAS scores every opportunity.        │
│    34 opportunities were rescored when v4 was activated.              │
│                                              [ Version history ▸ ]    │
├───────────────────────────────────────────────────────────────────────┤
│  COMPLETENESS                                          ████████░░ 78% │
│  ⚠ 3 sections incomplete. Incomplete sections fall back to defaults,  │
│    which are documented but generic.                                  │
│    Missing: specialist availability · partner network · exclusions    │
├───────────────────────────────────────────────────────────────────────┤
│  ▸ STRATEGIC PRIORITIES                                    [ Edit ]   │
│    Objectives · growth priorities · revenue objective                 │
│                                                                       │
│  ▸ MARKETS                            7 regions · 4 tier-1  [ Edit ]  │
│    Tier 1: Saudi Arabia · UAE · India · UK                            │
│                                                                       │
│  ▸ COMMERCIAL THRESHOLDS                                   [ Edit ]   │
│    Min viable $2.0M · target $5.0M · margin 32% · max mobilisation... │
│                                                                       │
│  ▸ DELIVERY CAPACITY                  82% utilised    ⚠      [ Edit ] │
│  ▸ CAPABILITIES                       12 mapped              [ Edit ] │
│  ▸ PARTNERS                           ⚠ not yet completed    [ Add  ] │
│  ▸ EXCLUSIONS                         ⚠ not yet completed    [ Add  ] │
│  ▸ SCORING WEIGHTS                    Strategic 35% · ...    [ Edit ] │
├───────────────────────────────────────────────────────────────────────┤
│  Editing creates version 5. Existing scores are preserved and flagged  │
│  for rescoring — historical decisions remain readable against v4.      │
└───────────────────────────────────────────────────────────────────────┘
```

**The completeness meter is deliberate.** The main adoption risk in Phase
3 is a half-filled profile that looks authoritative while being
arbitrary. Making incompleteness visible — and naming which sections fall
back to defaults — is the mitigation.

### 4.4 Relationship view (per opportunity)

```
┌──────────────────────────────────────────────────────────────────────┐
│  RELATIONSHIPS — Saudi Coach Education Framework                      │
├───────────────────────────────────────────────────────────────────────┤
│  POSITION: ◐ MODERATE                                                 │
│  Technical influence established. No economic buyer contact.          │
├───────────────────────────────────────────────────────────────────────┤
│  WHO DECIDES                                                          │
│   ⬤ [Name] · Deputy Minister · Final authority          ✗ No contact  │
│     Introduction available: [Partner] → [Adviser] → target            │
│     3 hops · weakest link 60      [ Request introduction ▸ ]          │
│                                                                       │
│  WHO CONTROLS PROCUREMENT                                             │
│   ⬤ [Name] · Head of Procurement                        ✗ No contact  │
│                                                                       │
│  WHO INFLUENCES                                                       │
│   ⬤ [Name] · Technical Director            ✓ Known via [Partner]      │
│     Last engagement 34 days ago · strength 65                         │
│     Next: brief on comparable delivery      [ Log engagement ]        │
│                                                                       │
│  GAPS                                                                 │
│   ⚠ No economic buyer relationship — highest-value gap (+8 win prob.) │
│   ⚠ No local entity partner — mandatory requirement                   │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.5 Opportunity timeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  TIMELINE — Saudi Coach Education Framework                           │
│                                                                       │
│  ①──②──③──④──⑤──[⑥]──⑦──⑧──⑨──⑩──⑪──⑫──⑬──⑭──⑮──⑯──⑰            │
│                     ▲                                                 │
│                  YOU ARE HERE                                         │
│                                                                       │
│  CURRENT   6 · Market engagement          entered 12 days ago         │
│  PREVIOUS  5 · Stakeholder consultation   lasted 41 days              │
│  NEXT      7 · Partner formation          expected mid-Aug (medium)   │
│                                                                       │
│  ⓘ Stages 1–6 are pre-publication. This is the last stage at which    │
│    VECTA can influence requirements.                                  │
│                                                                       │
│  BEFORE THE NEXT STAGE                                                │
│   □ Local delivery entity secured            ⚠ mandatory, not started │
│   □ Consortium partner identified                                     │
│   □ Comparable national reference prepared                            │
│                                                                       │
│  RELATIONSHIPS REQUIRED                                               │
│   □ Economic buyer contact before consultation closes (18 days)       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 5. Dashboard layouts — density and hierarchy

The reference points named are Bloomberg and Foundry. What those actually
share is not aesthetics — it is **information density with strict
hierarchy**. A lot on screen, but never ambiguous about what matters.

### 5.1 Rules

| Rule | Rationale |
|---|---|
| One primary action per block | Two actions means neither is primary |
| Numbers before prose | An executive scans figures, then reads for why |
| Deltas beside values | $22.8B means little; "$22.8B, ↑$1.2B this week" means something |
| Never colour alone | Carried from v2.9 accessibility; also survives a bad screen |
| Empty states carry meaning | "No decisions waiting" is good news and should read as such |
| Provenance always visible, always small | Trust needs it present, not prominent |

### 5.2 Typographic hierarchy

```
LEVEL 1  Decision / recommendation      20px semibold
LEVEL 2  Opportunity title              15px medium
LEVEL 3  Scores, figures                14px tabular
LEVEL 4  Reasoning, evidence            13px regular
LEVEL 5  Provenance, timestamps         11px muted
```

Five levels, no more. The current UI uses roughly three, which is why
everything reads as equally important.

### 5.3 Colour

Retain the v2.9 dark navy. Colour carries **state**, never decoration:

| State | Use |
|---|---|
| Accent blue | Recommended action, primary route |
| Green | Verified, qualified, on track |
| Amber | Provisional, conditional, attention |
| Red | Disqualified, expired, absolute blocker |
| Muted | Unknown, not established, not assessed |

Every one also carries a text label.

---

## 6. AI orchestration design

### 6.1 The cost/freshness split — the central design decision

```
┌─────────────────────────────────────────────────────────────┐
│  COMPUTED LAYER — free, instant, runs on every page load    │
│                                                              │
│  • Change detection (diff since last visit)                 │
│  • Deadline and stage-window proximity                      │
│  • Staleness detection                                       │
│  • Score deltas                                              │
│  • Relationship recency vs decision authority                │
│  • Capacity vs committed pursuits                            │
│  • Qualification bottleneck detection                        │
│  • Priority ordering                                         │
│                                                              │
│  → Powers the ENTIRE morning briefing                       │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  AI LAYER — manual, cost-estimated, never automatic         │
│                                                              │
│  • Opportunity scanning        (existing)                    │
│  • Signal detection            → predictions                 │
│  • Executive summary narrative → decision cards              │
│  • Report authoring                                          │
│                                                              │
│  → Enriches. Never required for the briefing to work.       │
└─────────────────────────────────────────────────────────────┘
```

**This is what makes a daily executive brief compatible with manual-only
AI cost.** The brief is always available, always instant, always free.
The AI layer adds narrative and discovery when you choose to spend.

### 6.2 Card narrative generation

Decision cards need a written summary, which is an AI task. But
generating one per card on demand would be slow and costly.

**Approach:** the *recommendation* is rule-derived and instant. The
*narrative* is generated once when the card is created or materially
changes, then cached. A card whose narrative is stale shows the rule-based
reasoning — which is complete, just less readable — and offers to
regenerate.

Consequence: the card is never blocked on an API call.

### 6.3 Orchestration pattern

```
Trigger (manual) → cost estimate shown → confirm
  → scoped prompt built from taxonomy + profile
  → strict schema validation (v2.9 pattern)
  → per-record failure isolation
  → evidence persisted with URL validation
  → service layer writes (never direct ORM)
  → computed layer recalculates
  → briefing reflects it on next load
```

Unchanged from v2.9 in every respect that matters.

---

## 7. Relationship model

Fully specified in `PHASE3_ARCHITECTURE.md` §4.2 and §9. Product-level
summary:

**Relationships become first-class**, with their own screen, their own
gaps, and direct influence on Win Probability. Every relationship carries
confidence, influence, strength, last engagement, next engagement, and an
owner.

**Position** rolls up to one of four words — Strong / Moderate / Weak /
**Unknown**. Unknown is honest, will be the most common initially, and
should not be dressed up as Weak.

**The product question that matters** is not "who do we know" but "who do
we need to know, and how do we get there". That is why introduction paths
are computed and surfaced with the gap, rather than being a browsing
feature.

---

## 8. Decision engine specification

Specified in `PHASE3_ARCHITECTURE.md` §11 and §14. Product-level rules:

1. **Rules decide, AI explains.** Same inputs always produce the same
   posture. A recommendation to decline $4M must be reproducible.
2. **Every recommendation is challengeable.** Accept / edit / defer /
   decline, all recorded.
3. **No recommendation without an owner and a date.**
4. **No recommendation without the cost of inaction.**
5. **Confidence is mechanical**, from evidence quality and coverage — not
   the model's self-assessment.
6. **Superseded recommendations are retained**, so you can reconstruct
   what was advised and what you did.

---

## 9. Predictive intelligence methodology

Specified in `PHASE3_ARCHITECTURE.md` §10. Product-level rules:

- Predictions live in a **separate section**, labelled *"Predicted — not
  a verified opportunity"*
- **Never** counted in pipeline value, weighted value or forecast
- Never generate a Decision Card (they generate *watch* items with early
  actions)
- Every prediction reaches a recorded outcome; accuracy is reported
- A prediction converts by creating a **new** opportunity that passes the
  normal gate from scratch

The Briefing surfaces predictions under "what is coming", visually
separated from "what is real". That separation is the entire basis on
which predictions can be trusted enough to be useful.

---

## 10. Reporting framework

Board-level decision papers, not exports. Each answers: what changed ·
why · what decisions are required · what actions · what risks · what
assumptions · what evidence.

Every claim is classified — verified fact · AI interpretation ·
assumption · prediction · recommendation — and linked to its source.

**Build three first:** Weekly Executive Brief · Predictive Opportunity
Report (with calibration accuracy) · Relationship Gap Report. The
remaining nine are deferred until one is requested twice; most reports in
most systems are opened once, and the maintenance cost is real.

---

## 11. API additions

Specified in `PHASE3_ARCHITECTURE.md` §6. Two additions arising from this
product spec:

```
GET  /briefing                  the full morning brief (computed, no AI)
GET  /briefing/changes?since=   diff since last visit
POST /decisions/{id}/respond    accept | edit | defer | decline
GET  /decisions/queue           waiting · deferred · decided
```

`/briefing` must return in **under 1.5 seconds**. If it cannot, the
computed layer needs materialised views — a performance requirement, not
an architectural change.

---

## 12. Implementation roadmap

| Milestone | Delivers | Executive value |
|---|---|---|
| **3.1 Commercial Profile** | Profile, versioning, scoring integration | Scores mean something specific to VECTA |
| **3.2 Computed layer + Briefing** | Change detection, staleness, the morning brief | **The daily-open habit starts here** |
| **3.3 Decision Cards** | Rule-driven postures, card UI, response capture | "What should we do" is answered |
| **3.4 Relationship Intelligence** | Stakeholders, paths, gaps, Win Probability | A quarter of Win Probability becomes evidence |
| **3.5 Timeline** | Lifecycle, stage inference, pre-publication window | Earlier engagement becomes visible |
| **3.6 Predictive** | Signals, predictions, calibration | Opportunities before publication |
| **3.7 Decision Engine** | Full nine-question composition | Complete decision support |
| **3.8 Reporting** | Three decision papers | Board-ready output |

**Sequencing changed from the architecture document.** That version put
the Dashboard second and Decision Cards later. On reflection that is
wrong: the Briefing without cards tells you what changed but not what to
do — which is half a product, and the half less likely to earn a daily
open. 3.2 and 3.3 should ship close together, and 3.3 should not slip.

---

## 13. Acceptance criteria

### Product
1. Briefing loads in **under 1.5 seconds**
2. Briefing requires **zero AI calls**
3. All nine morning questions answered without navigation
4. Every card carries owner, decide-by date and cost of inaction
5. Nothing important is more than two clicks from the Briefing
6. Every recommendation is accept/edit/defer/decline-able, and recorded
7. Predictions visually and structurally separated from verified
   opportunities
8. Profile completeness visible, with named fallbacks

### Technical
9. No Phase 2 table restructured
10. Security model unchanged; single login preserved
11. All writes through the service layer
12. Full suite passes without a live AI key
13. Guard tests prevent service bypass and prediction leakage
14. Every recommendation and decision carries a profile version

### The real test
15. **You open ATLAS before email for two consecutive weeks.**

If 1–14 pass and 15 does not, the product has failed and the design needs
revisiting — not more features. I would rather that be measured than
assumed.

---

## 14. Open questions for you

Three things I should not decide alone:

**1. Decide-by dates.** Should ATLAS compute them (from deadline, stage
duration and action lead times) or should you always set them? Computed
is faster and will sometimes be wrong; owner-set is always right and adds
friction. My inclination is computed with one-click override, but this
depends on how much you trust an automated deadline.

**2. Card volume.** With ~93 priority opportunities, generating cards for
all qualified ones could produce 20–30 at once. Options: cap the queue at
5 and hold the rest, or show all and rely on ordering. I lean toward
capping, since a queue of 30 decisions is a backlog, not a briefing — but
you may want visibility of everything.

**3. Declined opportunities.** Should a declined opportunity ever
resurface if circumstances change materially — a competitor withdraws, a
partner becomes available? My inclination is yes, once, with the change
stated explicitly. Otherwise a single early "no" becomes permanent.

---

## Appendix — what changed from the architecture document

| Change | Reason |
|---|---|
| Decision Cards elevated to centrepiece | They are the atomic unit; the architecture doc under-weighted them |
| Sequencing: Cards move from 3.5 to 3.3 | Briefing without cards is half a product |
| Navigation reduced from 7 items to 4 | Organised by intent, not object type |
| Computed/AI layer split made explicit | Resolves the daily-brief vs manual-cost tension |
| Profile completeness meter added | Mitigates the main adoption risk |
| "First app opened" added as acceptance criterion | The standard you set deserves to be measured |
