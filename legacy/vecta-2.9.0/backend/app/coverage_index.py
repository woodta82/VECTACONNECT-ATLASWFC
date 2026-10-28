"""Relationship Coverage Index — Sprint 2.1.

Answers: **are we covered across the buying ecosystem, or exposed?**

THE DESIGN DECISION THAT MATTERS
================================
A naive coverage score counts roles filled and reports a percentage. That
conflates three genuinely different failures, each needing a different
response:

  UNKNOWN     — we do not know who the decision-maker is.
                → an INTELLIGENCE gap. Research, ask, map.

  UNENGAGED   — we know exactly who they are and have never spoken.
                → an EXECUTION gap. Make contact this week.

  DETERIORATING — we know them, we have engaged, and it is going backwards.
                → a RELATIONSHIP gap. Repair, or route around them.

"60% coverage" tells an executive nothing about which of these they have.
Every RCI output therefore names the gap type, because the action differs
completely and the cost of confusing them is wasted weeks.

A second consequence: an opportunity can score *worse* after mapping
stakeholders, because discovering an unengaged economic buyer is worse
news than not knowing whether one exists. That is correct. The score
should track reality, not reward data entry.
"""
from __future__ import annotations

from datetime import date, datetime

COVERAGE_MODEL_VERSION = "1.0"

# The buying ecosystem. Weights reflect what actually decides a pursuit:
# an unmapped economic buyer sinks a bid regardless of how well the
# technical evaluator likes you.
COVERAGE_ROLES = [
    {
        "key": "economic_buyer",
        "label": "Executive sponsor / economic buyer",
        "weight": 0.26,
        "critical": True,
        "why": "Signs the contract. Without them a pursuit has no route to a decision.",
    },
    {
        "key": "budget_holder",
        "label": "Decision maker",
        "weight": 0.20,
        "critical": True,
        "why": "Controls whether funding is released.",
    },
    {
        "key": "procurement_authority",
        "label": "Procurement contact",
        "weight": 0.16,
        "critical": True,
        "why": "Controls process, timing and compliance. Often decides who is even eligible.",
    },
    {
        "key": "technical_evaluator",
        "label": "Technical evaluator",
        "weight": 0.14,
        "critical": False,
        "why": "Scores the submission against requirements.",
    },
    {
        "key": "operational_champion",
        "label": "Operational champion",
        "weight": 0.14,
        "critical": False,
        "why": "Advocates internally when VECTA is not in the room.",
    },
    {
        "key": "political_sponsor",
        "label": "Political / institutional sponsor",
        "weight": 0.10,
        "critical": False,
        "why": "Provides cover and continuity across leadership change.",
    },
]

# Role-quality bands. Identification alone is worth little — a mapped
# contact nobody has spoken to does not improve win probability.
ROLE_STATE_SCORES = {
    "unknown": 0,
    "identified": 35,        # we know who, no contact
    "contacted": 60,         # engaged at least once
    "engaged": 85,           # active, healthy relationship
    "advocating": 100,       # actively supporting VECTA
}

GAP_TYPES = {
    "intelligence": {
        "label": "Intelligence gap",
        "meaning": "We do not know who holds this role.",
        "action_verb": "Identify",
    },
    "execution": {
        "label": "Execution gap",
        "meaning": "We know who they are but have not engaged them.",
        "action_verb": "Contact",
    },
    "relationship": {
        "label": "Relationship gap",
        "meaning": "We have engaged, but the relationship is weak or declining.",
        "action_verb": "Repair",
    },
    "none": {"label": "Covered", "meaning": "", "action_verb": ""},
}

COVERAGE_BANDS = [
    {"min": 80, "max": 100, "key": "strong", "label": "Strong coverage"},
    {"min": 60, "max": 79, "key": "adequate", "label": "Adequate coverage"},
    {"min": 40, "max": 59, "key": "partial", "label": "Partial coverage"},
    {"min": 20, "max": 39, "key": "weak", "label": "Weak coverage"},
    {"min": 0, "max": 19, "key": "exposed", "label": "Exposed"},
]

# Modifiers applied after role coverage. Deliberately capped so they can
# adjust a score but never manufacture coverage that does not exist.
MAX_MODIFIER = 12


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def classify_gap(state: str, health_score: int | None,
                 momentum_state: str | None) -> str:
    """Which of the three gap types this role represents."""
    if state == "unknown":
        return "intelligence"
    if state == "identified":
        return "execution"
    if momentum_state in ("declining", "critical"):
        return "relationship"
    if health_score is not None and health_score < 40:
        return "relationship"
    return "none"


def role_coverage(role_key: str, state: str, *, health_score: int | None = None,
                  momentum_state: str | None = None,
                  stakeholder_name: str | None = None) -> dict:
    """Coverage for one role, with its gap type and the action that closes it."""
    role = next((r for r in COVERAGE_ROLES if r["key"] == role_key), None)
    if role is None:
        role = {"key": role_key, "label": role_key.replace("_", " ").title(),
                "weight": 0.0, "critical": False, "why": ""}

    base = ROLE_STATE_SCORES.get(state, 0)

    # A known-but-deteriorating relationship scores below a healthy
    # contacted one. Presence is not coverage.
    if state in ("contacted", "engaged", "advocating"):
        if momentum_state == "critical":
            base = min(base, 45)
        elif momentum_state == "declining":
            base = min(base, 60)
        if health_score is not None:
            base = round(base * (0.5 + health_score / 200))

    gap = classify_gap(state, health_score, momentum_state)
    gap_info = GAP_TYPES[gap]

    action = None
    if gap != "none":
        who = stakeholder_name or f"the {role['label'].lower()}"
        action = f"{gap_info['action_verb']} {who}"

    return {
        "role": role["key"],
        "label": role["label"],
        "weight": role["weight"],
        "is_critical": role["critical"],
        "why_it_matters": role["why"],
        "state": state,
        "state_label": state.replace("_", " ").title(),
        "score": round(_clamp(base)),
        "stakeholder_name": stakeholder_name,
        "health_score": health_score,
        "momentum": momentum_state,
        "gap_type": gap,
        "gap_label": gap_info["label"],
        "gap_meaning": gap_info["meaning"],
        "recommended_action": action,
    }


def band_for(score: float) -> dict:
    for band in COVERAGE_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return COVERAGE_BANDS[-1]


def compute_coverage(role_states: list[dict], *,
                     warm_introduction_available: bool = False,
                     days_since_any_engagement: int | None = None,
                     mean_health: int | None = None,
                     declining_count: int = 0) -> dict:
    """The Relationship Coverage Index, with its reasoning.

    Role coverage is the substance; the modifiers adjust at the margin.
    They are capped so a warm introduction can improve a score but never
    disguise an unmapped economic buyer.
    """
    # Roles not supplied are UNKNOWN, not absent. An earlier version
    # excluded them from the gap list entirely, producing "Weak coverage
    # (36). All roles covered and healthy." — a score and an explanation
    # that contradicted each other. Silence about a role is the strongest
    # possible signal that nobody has looked for them.
    supplied = {e["role"] for e in role_states}
    role_states = list(role_states) + [
        {"role": r["key"], "state": "unknown"}
        for r in COVERAGE_ROLES
        if r["key"] not in supplied
    ]

    covered = []
    total = 0.0
    for entry in role_states:
        result = role_coverage(
            entry["role"],
            entry.get("state", "unknown"),
            health_score=entry.get("health_score"),
            momentum_state=entry.get("momentum_state"),
            stakeholder_name=entry.get("stakeholder_name"),
        )
        covered.append(result)
        total += result["score"] * result["weight"]

    base_score = _clamp(total)

    # --- modifiers ---------------------------------------------------------
    modifier = 0.0
    modifier_notes: list[str] = []

    if warm_introduction_available:
        modifier += 6
        modifier_notes.append("Warm introduction route available")
    if days_since_any_engagement is not None:
        if days_since_any_engagement <= 30:
            modifier += 4
            modifier_notes.append(f"Engaged within {days_since_any_engagement} days")
        elif days_since_any_engagement > 90:
            modifier -= 8
            modifier_notes.append(f"No engagement for {days_since_any_engagement} days")
    if mean_health is not None and mean_health >= 70:
        modifier += 4
        modifier_notes.append(f"Mapped relationships are healthy (mean {mean_health})")
    if declining_count:
        modifier -= min(8, declining_count * 4)
        modifier_notes.append(f"{declining_count} mapped relationship(s) declining")

    modifier = max(-MAX_MODIFIER, min(MAX_MODIFIER, modifier))
    score = round(_clamp(base_score + modifier))

    # --- critical-role cap -------------------------------------------------
    # An unmapped economic buyer means the pursuit has no route to a
    # decision, however well the rest is covered. Capping is honest where
    # a weighted average would flatter.
    missing_critical = [
        c for c in covered if c["is_critical"] and c["state"] == "unknown"
    ]
    cap_reason = None
    if missing_critical:
        cap = 55 if len(missing_critical) == 1 else 35
        if score > cap:
            score = cap
            cap_reason = (
                f"Capped at {cap}: "
                + ", ".join(c["label"].lower() for c in missing_critical)
                + " not identified."
            )

    band = band_for(score)

    gaps = [c for c in covered if c["gap_type"] != "none"]
    gaps.sort(key=lambda c: (-c["weight"], c["score"]))

    by_type: dict[str, int] = {}
    for c in gaps:
        by_type[c["gap_type"]] = by_type.get(c["gap_type"], 0) + 1

    return {
        "score": score,
        "base_score": round(base_score),
        "band": band["key"],
        "band_label": band["label"],
        "modifier": round(modifier),
        "modifier_notes": modifier_notes,
        "cap_reason": cap_reason,
        "roles": covered,
        "gaps": gaps,
        "gap_counts": by_type,
        "missing_critical": [c["label"] for c in missing_critical],
        "biggest_lever": _biggest_lever(gaps),
        "explanation": _explain(score, band, covered, gaps, cap_reason),
        "model_version": COVERAGE_MODEL_VERSION,
    }


def _biggest_lever(gaps: list[dict]) -> dict | None:
    """The single action that would most improve coverage.

    Weight times headroom — a heavily-weighted role at zero beats a light
    one at sixty, which is not obvious from a list sorted by severity.
    """
    if not gaps:
        return None
    best = max(gaps, key=lambda c: c["weight"] * (100 - c["score"]))
    return {
        "role": best["role"],
        "label": best["label"],
        "gap_type": best["gap_type"],
        "gap_label": best["gap_label"],
        "action": best["recommended_action"],
        "potential_gain": round(best["weight"] * (100 - best["score"])),
        "why_it_matters": best["why_it_matters"],
    }


def _explain(score: int, band: dict, covered: list[dict], gaps: list[dict],
             cap_reason: str | None) -> str:
    """Why the score is what it is — in one sentence.

    Names the gap TYPE, because "we don't know who they are" and "we know
    but haven't called" require completely different responses.
    """
    if cap_reason:
        return f"{band['label']} ({score}). {cap_reason}"
    if not gaps:
        return f"{band['label']} ({score}). All roles covered and healthy."

    intelligence = [g for g in gaps if g["gap_type"] == "intelligence"]
    execution = [g for g in gaps if g["gap_type"] == "execution"]
    relationship = [g for g in gaps if g["gap_type"] == "relationship"]

    parts: list[str] = []
    if intelligence:
        parts.append(f"{len(intelligence)} role(s) unidentified")
    if execution:
        parts.append(f"{len(execution)} identified but never contacted")
    if relationship:
        parts.append(f"{len(relationship)} relationship(s) weak or declining")

    return f"{band['label']} ({score}). " + "; ".join(parts) + "."


def pursuit_recommendation(coverage: dict, days_to_deadline: int | None = None) -> dict:
    """Whether coverage supports pursuing now.

    This is the recommendation the spec asks for — "delay pursuit until
    stakeholder coverage improves" — expressed as a rule rather than a
    judgement, so it is reproducible and challengeable.
    """
    score = coverage["score"]
    missing_critical = coverage["missing_critical"]

    if missing_critical and (days_to_deadline is not None and days_to_deadline < 21):
        return {
            "posture": "high_risk_pursuit",
            "label": "Pursue at risk",
            "rationale": (
                f"{', '.join(missing_critical)} unmapped with {days_to_deadline} days remaining. "
                "There is not enough time to build coverage before submission."
            ),
        }
    if missing_critical:
        return {
            "posture": "close_coverage_first",
            "label": "Close coverage before committing",
            "rationale": (
                f"{', '.join(missing_critical)} not identified. "
                "Committing bid resources before finding them risks writing to the wrong brief."
            ),
        }
    if score >= 70:
        return {
            "posture": "pursue",
            "label": "Coverage supports pursuit",
            "rationale": f"Coverage {score} with all critical roles mapped.",
        }
    if score >= 45:
        return {
            "posture": "pursue_with_engagement",
            "label": "Pursue alongside engagement",
            "rationale": (
                f"Coverage {score}. Viable, but engagement gaps should be closed in parallel."
            ),
        }
    return {
        "posture": "improve_coverage",
        "label": "Improve coverage before pursuing",
        "rationale": f"Coverage {score} — too thin to bid competitively.",
    }
