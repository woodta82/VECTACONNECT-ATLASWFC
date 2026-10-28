"""Executive Focus Score — Phase 3.1.

**This is not another opportunity score.** Pursuit Priority already
answers "how good is this opportunity". Focus answers a different and
more useful question:

> *Where does an hour of executive attention change the outcome most?*

The distinction matters, and getting it wrong would make this redundant.
Consider two opportunities:

- **A**: Priority 92. Submitted last week, now in evaluation. Nothing
  VECTA does this month changes the result.
- **B**: Priority 68. Consultation closes in nine days, no decision-maker
  contact, and a local entity is mandatory but unsecured.

Pursuit Priority correctly ranks A above B. **Focus must rank B above A**,
because B is where attention still changes something and A is not. An
executive who spends the morning on A has wasted it, however attractive A
is.

So Focus = *value at stake* × *how much attention can still change it*.
The eight inputs the specification lists resolve into those two halves:

    VALUE AT STAKE          ATTENTION CHANGES THE OUTCOME
    strategic alignment     urgency (closing window)
    commercial value        relationship readiness (gap to close)
    win probability         qualification (blocked, resolvable)
                            evidence quality (verifiable)
                            delivery capacity (conflict to resolve)

An opportunity with high value and no open lever scores low. One with
moderate value and several open levers scores high. That is the whole
idea.
"""
from __future__ import annotations

from datetime import date
from typing import Any

FOCUS_MODEL_VERSION = "1.0"

# Weighting across the eight inputs. Urgency and relationship readiness
# carry the most because they are the two things that most often decay
# irreversibly while an executive is looking elsewhere.
FOCUS_WEIGHTS: dict[str, float] = {
    "strategic_alignment": 0.16,
    "commercial_value": 0.14,
    "win_probability": 0.12,
    "urgency": 0.20,
    "relationship_readiness": 0.16,
    "qualification": 0.10,
    "evidence_quality": 0.07,
    "delivery_capacity": 0.05,
}

FOCUS_BANDS = [
    {"min": 80, "max": 100, "key": "act_now", "label": "Act now"},
    {"min": 60, "max": 79, "key": "this_week", "label": "This week"},
    {"min": 40, "max": 59, "key": "this_month", "label": "This month"},
    {"min": 20, "max": 39, "key": "monitor", "label": "Monitor"},
    {"min": 0, "max": 19, "key": "no_action", "label": "No action needed"},
]


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


# ------------------------------------------------------------ components

def urgency_component(deadline: date | None, lifecycle_stage: str | None = None,
                      today: date | None = None) -> dict:
    """How fast the window is closing.

    Deliberately non-linear. The difference between 90 and 60 days out is
    almost irrelevant to today's decision; the difference between 10 and 5
    is decisive. A linear scale would spread attention evenly across a
    quarter, which is precisely the failure mode.
    """
    today = today or date.today()

    if deadline is None:
        # No deadline is not "no urgency" — a pre-publication window can
        # close without one. Treat as mild, not zero.
        base, note = 35.0, "No deadline recorded"
    else:
        days = (deadline - today).days
        if days < 0:
            base, note = 0.0, f"Deadline passed {abs(days)} days ago"
        elif days <= 7:
            base, note = 100.0, f"{days} days remaining"
        elif days <= 14:
            base, note = 85.0, f"{days} days remaining"
        elif days <= 30:
            base, note = 65.0, f"{days} days remaining"
        elif days <= 60:
            base, note = 40.0, f"{days} days remaining"
        elif days <= 90:
            base, note = 25.0, f"{days} days remaining"
        else:
            base, note = 12.0, f"{days} days remaining"

    # Pre-publication stages carry their own urgency: influence is
    # possible now and will not be later, regardless of deadline.
    if lifecycle_stage in ("stakeholder_consultation", "market_engagement"):
        base = max(base, 75.0)
        note += " · pre-publication window open"

    return {"score": _clamp(base), "note": note}


def relationship_readiness_component(has_decision_maker: bool, has_procurement: bool,
                                     strongest_relationship: int | None,
                                     introduction_available: bool,
                                     days_since_engagement: int | None) -> dict:
    """How much relationship work remains, and whether it is doable.

    Scores HIGH when there is a gap that could be closed — because that is
    where attention pays. A fully-mapped opportunity with warm access
    scores LOW here: nothing left to do.
    """
    notes: list[str] = []
    score = 0.0

    if not has_decision_maker:
        score += 45
        notes.append("No decision-maker contact")
    if not has_procurement:
        score += 20
        notes.append("No procurement contact")

    if introduction_available and not has_decision_maker:
        # An introduction that exists but is unused is the highest-value,
        # lowest-cost action available.
        score += 20
        notes.append("Introduction path available and unused")

    if strongest_relationship is not None and strongest_relationship < 40:
        score += 10
        notes.append("Existing relationships weak")

    if days_since_engagement is not None and days_since_engagement > 30:
        score += 15
        notes.append(f"No engagement for {days_since_engagement} days")

    if not notes:
        notes.append("Relationship position adequate — no action needed")

    return {"score": _clamp(score), "note": "; ".join(notes)}


def qualification_component(state: str | None, unanswered_mandatory: int = 0,
                            remediable_blockers: int = 0) -> dict:
    """Blocked-but-resolvable scores highest.

    Disqualified scores zero — not because it does not matter, but because
    executive attention cannot change it. That is the consistent logic of
    this whole score.
    """
    if state == "disqualified":
        return {"score": 0.0, "note": "Disqualified — attention cannot change the outcome"}
    if state in (None, "not_assessed"):
        return {"score": 85.0, "note": "Not assessed — qualification needed to progress"}
    if state == "verification_required":
        return {
            "score": 90.0,
            "note": f"{unanswered_mandatory} mandatory question(s) blocking qualification",
        }
    if state == "conditionally_qualified":
        return {
            "score": 55.0,
            "note": f"{remediable_blockers} remediable blocker(s) to resolve",
        }
    return {"score": 15.0, "note": "Qualified — no qualification action outstanding"}


def evidence_quality_component(tier_1_count: int, validated_count: int,
                               total_evidence: int, requires_review: bool) -> dict:
    """Weak evidence scores HIGH — verification is an action worth taking.

    Inverted relative to intuition, and deliberately so: strong evidence
    means nothing left to verify, which means no call on executive time.
    """
    if total_evidence == 0:
        return {"score": 95.0, "note": "No evidence — verification required before any decision"}
    if requires_review:
        return {"score": 80.0, "note": "Flagged for human review"}
    if tier_1_count == 0:
        return {"score": 65.0, "note": "No Tier 1 source — verification would strengthen the case"}
    if validated_count == 0:
        return {"score": 50.0, "note": "Sources not yet validated"}
    return {"score": 10.0, "note": "Evidence sufficient — no verification outstanding"}


def delivery_capacity_component(capacity_strained: bool, uses_scarce_capability: bool,
                                competing_pursuits: int = 0) -> dict:
    """A capacity conflict is a decision only an executive can make.

    Two pursuits needing the same scarce specialists in the same month is
    not a scheduling problem; it is a choice about which one VECTA wants.
    """
    notes: list[str] = []
    score = 0.0
    if capacity_strained:
        score += 40
        notes.append("Delivery capacity strained")
    if uses_scarce_capability:
        score += 35
        notes.append("Requires a scarce specialist capability")
    if competing_pursuits > 0:
        score += min(25, competing_pursuits * 12)
        notes.append(f"Competes with {competing_pursuits} other pursuit(s) for the same people")
    if not notes:
        notes.append("No capacity conflict")
    return {"score": _clamp(score), "note": "; ".join(notes)}


def commercial_value_component(value: float | None, min_viable: float | None,
                               target: float | None) -> dict:
    """Value relative to VECTA's own thresholds, not absolute size.

    $3m is large or marginal depending on the Commercial Profile, which is
    exactly why the profile exists.
    """
    if value is None:
        return {"score": 40.0, "note": "Value not established"}
    if min_viable and value < min_viable:
        return {"score": 5.0, "note": f"Below minimum viable value ({value:,.0f})"}
    if target:
        ratio = value / target
        if ratio >= 2:
            return {"score": 100.0, "note": f"{value:,.0f} — well above target"}
        if ratio >= 1:
            return {"score": 80.0, "note": f"{value:,.0f} — at or above target"}
        return {"score": _clamp(30 + ratio * 50), "note": f"{value:,.0f} — below target"}
    return {"score": 60.0, "note": f"{value:,.0f} — no target set in profile"}


# -------------------------------------------------------------- compose

def band_for(score: float) -> dict:
    for band in FOCUS_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return FOCUS_BANDS[-1]


def compute_focus_score(components: dict[str, dict], *,
                        is_actionable: bool = True,
                        suppression_reason: str | None = None) -> dict:
    """Weighted composition with a full breakdown.

    `is_actionable=False` collapses the score to zero. That is the
    mechanism preventing the failure this score exists to avoid: an
    opportunity awaiting external evaluation, disqualified, or already
    decided must not occupy executive attention however attractive it is.
    """
    contributions = []
    total = 0.0
    for key, weight in FOCUS_WEIGHTS.items():
        component = components.get(key) or {"score": 0.0, "note": "Not assessed"}
        value = _clamp(float(component.get("score", 0.0)))
        contribution = value * weight
        total += contribution
        contributions.append(
            {
                "component": key,
                "label": key.replace("_", " ").title(),
                "score": round(value),
                "weight": weight,
                "contribution": round(contribution, 2),
                "note": component.get("note"),
            }
        )

    raw = round(total)
    if not is_actionable:
        final = 0
        note = suppression_reason or "No executive action would change the outcome"
    else:
        final = raw
        note = None

    band = band_for(final)
    contributions.sort(key=lambda c: c["contribution"], reverse=True)

    return {
        "score": final,
        "raw_score": raw,
        "band": band["key"],
        "band_label": band["label"],
        "is_actionable": is_actionable,
        "suppression_reason": note,
        "contributions": contributions,
        # The three biggest drivers, for the one-line explanation on a card.
        "primary_drivers": [c["label"] for c in contributions[:3]],
        "model_version": FOCUS_MODEL_VERSION,
    }


def explain(result: dict) -> str:
    """One short sentence naming why attention belongs here.

    Capped at the two strongest drivers, one clause each. An earlier
    version concatenated every note from the top components and produced
    six clauses — accurate, but not something an executive scans. The full
    breakdown remains available in `contributions`.
    """
    if not result["is_actionable"]:
        return result["suppression_reason"] or "No action required."

    clauses = []
    for contribution in result["contributions"][:2]:
        note = (contribution.get("note") or "").strip()
        if not note:
            continue
        # Take the first clause only — component notes may list several.
        clauses.append(note.split(";")[0].strip())

    if not clauses:
        return result["band_label"]
    return f"{result['band_label']} — " + "; ".join(clauses) + "."
