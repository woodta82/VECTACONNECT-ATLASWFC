# Phase 3.1 — Design Consistency Review

**Purpose:** audit the proposed and implemented Phase 3.1 surface against
the executive design standard, before further implementation.

**Method:** checked against the actual code, not the documents. Every
finding below is reproducible with a command in the appendix.

**Summary: seven inconsistencies found.** Two are material and would have
produced a confusing product; three are terminology; two are gaps against
the newly-specified Decision Card standard.

---

## Part 1 — Screen-by-screen executive purpose

Each screen restated against the required five-part definition.

### Briefing (home)

| | |
|---|---|
| **Primary decision** | Where do I spend today? |
| **Supporting decisions** | What can I ignore? What needs a decision this week? |
| **Evidence required** | Focus scores, material changes, deadlines, capacity |
| **Recommended action** | Open the top Decision Card, or close the laptop |
| **Success measure** | Understood in under 2 minutes; ≤3 items require action |

### Decisions (queue)

| | |
|---|---|
| **Primary decision** | Which of these do I decide now? |
| **Supporting decisions** | Which can I defer, and until when? |
| **Evidence required** | Decision Card set, decide-by dates |
| **Recommended action** | Accept, edit, defer or decline each card |
| **Success measure** | Queue reaches zero weekly; no card ages past its decide-by date |

### Decision Card

| | |
|---|---|
| **Primary decision** | Pursue, partner, influence, monitor, defer or decline? |
| **Supporting decisions** | Who owns it? By when? What must be verified first? |
| **Evidence required** | All 13 standard fields |
| **Recommended action** | Record the decision |
| **Success measure** | Decidable without opening the opportunity detail |

*That last measure is the real test of the card. If a card routinely
requires opening the detail page, the card has failed.*

### Opportunity detail

| | |
|---|---|
| **Primary decision** | Do I trust this recommendation? |
| **Supporting decisions** | What is the evidence? What is assumed? What is missing? |
| **Evidence required** | Full Phase 2 model |
| **Recommended action** | Confirm, override with a reason, or request verification |
| **Success measure** | Every score traceable to a factor and a source |

### Commercial Profile

| | |
|---|---|
| **Primary decision** | Is ATLAS evaluating opportunities the way VECTA actually thinks? |
| **Supporting decisions** | Which sections are still generic? |
| **Evidence required** | Completeness, named fallbacks, version history |
| **Recommended action** | Complete the highest-impact missing section |
| **Success measure** | Completeness rises; recommendations cite a real version |

### Advisor

| | |
|---|---|
| **Primary decision** | Answer a question no screen anticipated |
| **Supporting decisions** | Is the answer trustworthy? |
| **Evidence required** | Claim classification and sources on every response |
| **Recommended action** | Act, or open the referenced card |
| **Success measure** | Answers in the 6-part structure; no response exceeds ~150 words |

---

## Part 2 — Inconsistencies found

### FINDING 1 — Two competing prioritisation scores (MATERIAL)

`PursuitPriority.final_score` and `ExecutiveFocus.score` are both 0–100,
both banded, and both sort opportunities. An executive seeing "Priority
92 / Focus 12" on the same card will reasonably ask which is right.

They answer different questions and both are needed — but nothing in the
current design says so at the point of use.

**Refinement.** Establish a single vocabulary and enforce it:

| Score | Question | Where it appears |
|---|---|---|
| **Pursuit Priority** | *How good is this opportunity?* | Opportunity detail only |
| **Executive Focus** | *Where should I spend today?* | Briefing, Decisions, cards — the default sort everywhere |

Rules:
- Focus is the **only** score that sorts a list an executive sees daily.
- Where both appear, Focus is primary and Priority is secondary detail.
- The card must carry a one-line reconciliation whenever they diverge by
  more than 30 points — e.g. *"High-value opportunity, but nothing you do
  this week changes the outcome."* Divergence is the interesting case,
  and currently it is silent.

### FINDING 2 — Relationship status is inferred from role text (MATERIAL)

`_relationship_status()` decides seniority by keyword-matching the role
string against `director, minister, head, chief, secretary general`. A
"Head of Facilities" scores as senior access; a "Directeur Général" does
not. It is presented with the same visual weight as an evidence-backed
score.

This breaks the platform's central discipline: **AI interpretation
presented as verified fact.**

**Refinement.** Until 3.2 supplies the stakeholder model:
- Label it `"Inferred"` explicitly in the payload and the UI.
- Add `basis: "Inferred from contact role text — not verified"`.
- Cap the level at `moderate`; **`strong` must never be inferred**, since
  a false "strong" is the one that would actually mislead a decision.

### FINDING 3 — Decision Card missing 2 of 13 standard fields

Verified against the code: `required_relationships` and
`supporting_evidence` are absent from `todays_priorities()`.

`supporting_evidence` is the more serious omission — the card asks for a
decision while the evidence sits one click away, which contradicts
"recommendations are always supported by evidence."

**Refinement.** Add both. Evidence as a compact summary (tier counts,
strongest source, validation status) with a link to the full set.

### FINDING 4 — Navigation does not match the stated workflow

The workflow is 8 steps ending in **"leave the platform"**. The proposed
navigation has 4 destinations, one of which — `INTELLIGENCE` — bundles
opportunities, predictions, signals and relationships.

Two problems:
- Step 5 ("review relationship actions") has no home. It is buried inside
  a bundle.
- Nothing supports step 8. Every screen invites further browsing.

**Refinement.**
- Promote relationship actions to a **Briefing section with a direct
  route**, rather than requiring navigation into `INTELLIGENCE`.
- Add an explicit end state: when the queue is clear and nothing is in
  the act-now band, the Briefing says so plainly — *"Nothing further
  requires your attention today."* A product optimised for short sessions
  should be willing to say it is finished.

### FINDING 5 — Terminology drift

Code check found: `priority_band` (4 uses) vs `focus_band` (2);
"Focus Score" (5) vs "Executive Focus" (4); band labels differ between
the two scores (`Immediate Priority` vs `Act now`).

**Refinement.** Fix the vocabulary now, before the UI is built:

| Concept | Canonical term | Never |
|---|---|---|
| Where to spend time | **Executive Focus** | Focus Score, focus rating |
| Focus bands | **Act now · This week · This month · Monitor · No action** | (unchanged) |
| Opportunity quality | **Pursuit Priority** | Priority Score, opportunity score |
| Recommendation | **Recommended decision** | posture, recommendation, advice |
| Evidence quality | **Evidence status** | evidence quality, source strength |
| Relationship level | **Relationship position** | status, strength, readiness |

### FINDING 6 — Advisor has prompts but no response structure

`advisor_prompts()` returns questions and availability flags. There is no
response builder, so the mandated 6-part structure (Recommendation · Why
· Evidence · Risks · Assumptions · Next actions) is not yet enforced
anywhere.

**Refinement.** Build the response as a **typed structure, not prose** —
six named fields the frontend renders in fixed order. This makes the
"no long conversational responses" requirement structural rather than a
prompt instruction the model may ignore. Suggested cap: 40 words per
field.

### FINDING 7 — Focus Score explanation can run long

`explain()` concatenates every note from the top two components. In the
verified example it produced a 6-clause sentence: *"9 days remaining; No
decision-maker contact; No procurement contact; Introduction path
available and unused; Existing relationships weak; No engagement for 45
days."*

Accurate, but not executive.

**Refinement.** Cap at the two strongest drivers and one clause each:
*"9 days remaining; no decision-maker contact."* Full breakdown stays
available in the card's detail.

---

## Part 3 — What is consistent

Confirmed by code audit, so the review is not only negative:

| Check | Status |
|---|---|
| Recommendation appears before metrics in the card payload | ✓ field order enforced |
| Every score carries coverage | ✓ |
| Risk suppression honoured end to end | ✓ `display_label` never resurrects a suppressed number |
| Estimated value never presented as published | ✓ `is_estimate` flag |
| Briefing makes zero AI calls | ✓ verified: 0 occurrences in the path |
| Every recommendation carries a `basis` | ✓ |
| Profile version stamped on scores and priorities | ✓ |
| Suppressed opportunities excluded from priorities | ✓ |

---

## Part 4 — Resolution status

All seven findings resolved. Verified against the code:

| # | Finding | Resolution |
|---|---|---|
| 1 | Two competing scores | `_reconcile()` emits a plain-language line when Focus and Priority diverge by 30+; Focus is the sole daily sort |
| 2 | Inferred relationship status | `is_inferred` + `basis` on every response; **`strong` unreachable by inference** |
| 3 | Card missing 2 of 13 fields | `required_relationships` and `supporting_evidence` added — 13/13 |
| 4 | No end state | `is_complete` + `completion_message` — the briefing says when you are finished |
| 5 | Terminology drift | `app/vocabulary.py` — single source for every executive-facing term |
| 6 | Advisor had no response structure | Typed six-section shape, 40-word cap enforced by `_clip()`, not by prompt |
| 7 | Focus explanation too long | Capped at two clauses — verified output: 9 words |

## Part 5 — Original refinement plan (retained for the record)

Ordered by cost of deferring.

| # | Refinement | Why now |
|---|---|---|
| 1 | Add `supporting_evidence` + `required_relationships` to the card | The card is being built next; adding fields after is rework |
| 2 | Label inferred relationship status; cap at `moderate` | Shipping an unlabelled inference contradicts the core discipline |
| 3 | Fix terminology across code and UI | Cheap now, expensive once components exist |
| 4 | Add Focus/Priority reconciliation line | Divergence is the interesting case and is currently silent |
| 5 | Shorten `explain()` to two clauses | One-line change |
| 6 | Define advisor response as a typed 6-field structure | Before the advisor is built |
| 7 | Add the "nothing further requires attention" end state | Supports step 8 of the workflow |

**Not proposed:** no new screens, no new data model, no change to the
Phase 2 foundation. All seven are refinements to what exists.

---

## Appendix — reproducing the audit

```bash
cd backend

# Finding 3 — card field coverage
python3 - <<'PY'
import re, pathlib
c = pathlib.Path('app/services/briefing_service.py').read_text()
block = c.split('def todays_priorities')[1].split('def _provisional_decision')[0]
print(sorted(set(re.findall(r'"(\w+)":', block))))
PY

# Finding 5 — terminology drift
grep -rc "priority_band\|focus_band" app/

# Finding 2 — inferred relationship logic
grep -A 6 "_relationship_status" app/services/briefing_service.py

# Part 3 — zero AI calls in the briefing path
grep -c "anthropic\|run_phase2_scan" app/services/briefing_service.py
```
