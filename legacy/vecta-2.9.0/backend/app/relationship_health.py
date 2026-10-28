"""Relationship Health Score — Sprint 2.

Answers: **is this relationship getting stronger or weaker, and does it
matter commercially?**

Two design decisions worth stating, because both are easy to get wrong:

**1. Health decays.** A relationship is not a stored value; it is a
perishable asset. A strong relationship untouched for six months is not
strong any more, and a model that reports it as strong will let it die
quietly. Recency therefore carries the heaviest weight, and the decay is
non-linear — the difference between 10 and 30 days barely matters, the
difference between 90 and 180 is severe.

**2. Health is weighted by influence.** A warm relationship with someone
who cannot affect a decision is pleasant but not commercially useful. A
cold one with an economic buyer is a live problem. The score reflects
*commercial* health, not personal rapport — which is why
`strategic_value` and `influence` are inputs rather than separate
metrics.

Every factor produces a rationale. A score an executive cannot explain to
a colleague is not usable, and one they cannot challenge is not
trustworthy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

HEALTH_MODEL_VERSION = "1.0"

# Recency dominates because it is the factor that silently erodes.
HEALTH_WEIGHTS: dict[str, float] = {
    "recency": 0.24,
    "frequency": 0.16,
    "responsiveness": 0.14,
    "meeting_outcomes": 0.14,
    "influence": 0.14,
    "opportunity_alignment": 0.10,
    "strategic_value": 0.08,
}

HEALTH_BANDS = [
    {"min": 75, "max": 100, "key": "strong", "label": "Strong"},
    {"min": 55, "max": 74, "key": "healthy", "label": "Healthy"},
    {"min": 35, "max": 54, "key": "cooling", "label": "Cooling"},
    {"min": 15, "max": 34, "key": "weak", "label": "Weak"},
    {"min": 0, "max": 14, "key": "dormant", "label": "Dormant"},
]

# Influence tiers. `unknown` is deliberately mid-range rather than zero:
# an unmapped stakeholder is a gap to close, not a person who does not
# matter, and scoring them zero would hide them.
INFLUENCE_SCORES = {
    "economic_buyer": 100,
    "budget_holder": 95,
    "programme_sponsor": 85,
    "procurement_authority": 80,
    "political_sponsor": 75,
    "technical_evaluator": 65,
    "technical_influencer": 60,
    "adviser": 50,
    "gatekeeper": 45,
    "introducer": 40,
    "delivery_partner": 35,
    "consultant": 30,
    "unknown": 45,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ------------------------------------------------------------- factors

def recency_component(last_engagement: date | datetime | None,
                      today: date | None = None) -> dict:
    """How long since anyone spoke to them.

    Non-linear on purpose. Ten days versus thirty barely changes what an
    executive should do this week; ninety versus a hundred and eighty is
    the difference between a relationship and a memory.
    """
    today = today or date.today()
    if last_engagement is None:
        return {"score": 0.0, "note": "No engagement ever recorded"}

    if isinstance(last_engagement, datetime):
        last_engagement = last_engagement.date()
    days = (today - last_engagement).days

    if days < 0:
        return {"score": 100.0, "note": "Engagement scheduled"}
    if days <= 14:
        score, note = 100.0, f"Engaged {days} days ago"
    elif days <= 30:
        score, note = 85.0, f"Engaged {days} days ago"
    elif days <= 60:
        score, note = 65.0, f"{days} days since contact"
    elif days <= 90:
        score, note = 45.0, f"{days} days since contact"
    elif days <= 180:
        score, note = 22.0, f"{days} days since contact — cooling"
    else:
        score, note = 5.0, f"{days} days since contact — effectively dormant"
    return {"score": score, "note": note, "days_since": days}


def frequency_component(engagements_12m: int, months_known: int | None = None) -> dict:
    """Sustained contact, not a single meeting.

    One conversation a year is an acquaintance. The scale rewards rhythm
    over volume — twelve touches spread across a year beats twelve in one
    week, though this cannot yet distinguish them; noted as a limitation
    rather than pretended away.
    """
    if engagements_12m == 0:
        return {"score": 0.0, "note": "No engagements in the last 12 months"}
    if engagements_12m >= 12:
        score = 100.0
    elif engagements_12m >= 6:
        score = 80.0
    elif engagements_12m >= 3:
        score = 60.0
    elif engagements_12m >= 2:
        score = 40.0
    else:
        score = 25.0
    note = f"{engagements_12m} engagement(s) in 12 months"
    if months_known is not None and months_known < 3:
        note += " (new relationship)"
    return {"score": score, "note": note}


def responsiveness_component(sent: int, replied: int) -> dict:
    """Do they answer? The most honest signal of whether a relationship is
    real, and the one people most often flatter themselves about."""
    if sent == 0:
        return {"score": 50.0, "note": "No outbound contact to measure"}
    rate = replied / sent
    score = _clamp(rate * 100)
    if rate >= 0.7:
        note = f"Responds reliably ({replied}/{sent})"
    elif rate >= 0.4:
        note = f"Responds sometimes ({replied}/{sent})"
    elif rate > 0:
        note = f"Rarely responds ({replied}/{sent})"
    else:
        note = f"Never responded ({sent} attempts)"
    return {"score": score, "note": note}


def meeting_outcome_component(positive: int, neutral: int, negative: int) -> dict:
    """Whether meetings advance anything.

    A negative outcome is weighted more heavily than a positive one.
    Meetings that go badly are more informative than meetings that go
    pleasantly, and a model that averages them symmetrically will read a
    stalling relationship as merely mixed.
    """
    total = positive + neutral + negative
    if total == 0:
        return {"score": 50.0, "note": "No meeting outcomes recorded"}
    raw = (positive * 100 + neutral * 50 + negative * 0) / total
    penalty = min(20, negative * 10)
    score = _clamp(raw - penalty)
    return {
        "score": score,
        "note": f"{positive} positive, {neutral} neutral, {negative} negative",
    }


def influence_component(stakeholder_type: str | None,
                        decision_authority: str | None = None) -> dict:
    """How much this person can actually affect an outcome."""
    base = INFLUENCE_SCORES.get(stakeholder_type or "unknown", 45)
    if decision_authority == "final":
        base = max(base, 90)
    elif decision_authority == "none":
        base = min(base, 35)
    label = (stakeholder_type or "unknown").replace("_", " ")
    note = f"{label}"
    if decision_authority and decision_authority != "unknown":
        note += f", {decision_authority} authority"
    return {"score": float(base), "note": note}


def opportunity_alignment_component(linked_opportunities: int,
                                    highest_focus: int | None = None) -> dict:
    """Is this relationship attached to anything commercially live?

    A well-maintained relationship with no live opportunity is an
    investment, not an asset. Scored accordingly rather than dismissed.
    """
    if linked_opportunities == 0:
        return {"score": 20.0, "note": "Not linked to any live opportunity"}
    base = min(100.0, 45.0 + linked_opportunities * 15)
    if highest_focus is not None:
        base = max(base, float(highest_focus))
    return {
        "score": _clamp(base),
        "note": f"Linked to {linked_opportunities} opportunit"
                f"{'y' if linked_opportunities == 1 else 'ies'}"
                + (f", highest Executive Focus {highest_focus}" if highest_focus else ""),
    }


def strategic_value_component(is_strategic_account: bool, region_tier: int | None,
                              organisation_type: str | None = None) -> dict:
    """Does this relationship sit in a market VECTA has chosen to be in?"""
    score = 40.0
    notes: list[str] = []
    if is_strategic_account:
        score += 35
        notes.append("Strategic account")
    if region_tier == 1:
        score += 25
        notes.append("Tier 1 market")
    elif region_tier == 2:
        score += 10
        notes.append("Tier 2 market")
    elif region_tier is None:
        notes.append("Market not a stated profile priority")
    if organisation_type in ("government", "federation"):
        score += 10
        notes.append(f"{organisation_type.title()} counterparty")
    return {"score": _clamp(score), "note": "; ".join(notes) or "No strategic weighting"}


# ------------------------------------------------------------- compose

def band_for(score: float) -> dict:
    for band in HEALTH_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return HEALTH_BANDS[-1]


# A high-influence relationship that has gone quiet is the worst case, not
# a middling one. Below these thresholds the weighted average is overridden
# and the relationship is flagged at risk.
AT_RISK_INFLUENCE_FLOOR = 70   # economic buyer, budget holder, sponsor
AT_RISK_RECENCY_CEILING = 45   # roughly 90+ days since contact


def compute_health(components: dict[str, dict]) -> dict:
    """Weighted composition with a full, inspectable breakdown.

    CALIBRATION NOTE. An earlier version averaged influence and recency
    symmetrically, which produced a genuinely wrong answer: an economic
    buyer not contacted for 150 days scored 70 — "Healthy" — because high
    influence offset poor recency.

    That is backwards. Influence should *amplify* the urgency of decay,
    not offset it. A dormant relationship with someone who cannot affect
    the decision is a low priority; a dormant relationship with the person
    who signs is the most pressing item on the list. The override below
    enforces that.
    """
    contributions = []
    total = 0.0
    for key, weight in HEALTH_WEIGHTS.items():
        component = components.get(key) or {"score": 0.0, "note": "Not assessed"}
        value = _clamp(float(component.get("score", 0.0)))
        contribution = value * weight
        total += contribution
        contributions.append(
            {
                "factor": key,
                "label": key.replace("_", " ").title(),
                "score": round(value),
                "weight": weight,
                "contribution": round(contribution, 2),
                "note": component.get("note"),
            }
        )

    score = round(total)

    # --- at-risk override -------------------------------------------------
    influence_score = _clamp(float((components.get("influence") or {}).get("score", 0)))
    recency_score = _clamp(float((components.get("recency") or {}).get("score", 0)))
    at_risk = (
        influence_score >= AT_RISK_INFLUENCE_FLOOR
        and recency_score <= AT_RISK_RECENCY_CEILING
    )
    at_risk_reason = None
    if at_risk:
        # Capped rather than zeroed: the relationship still exists and its
        # other strengths are real. It is the *band* that must not read as
        # healthy.
        score = min(score, 40)
        at_risk_reason = (
            "High-influence relationship has gone quiet — "
            f"{(components.get('recency') or {}).get('note', 'no recent contact')}."
        )

    band = band_for(score)

    # Ordered by contribution so "why is this weak" is answered by the
    # bottom of the list, and "what is holding it up" by the top.
    contributions.sort(key=lambda c: c["contribution"], reverse=True)
    weakest = sorted(contributions, key=lambda c: c["score"])[:2]

    return {
        "score": score,
        "band": band["key"],
        "band_label": band["label"],
        "at_risk": at_risk,
        "at_risk_reason": at_risk_reason,
        "contributions": contributions,
        "strongest_factors": [c["label"] for c in contributions[:2]],
        "weakest_factors": [c["label"] for c in weakest],
        "improvement_levers": [
            {
                "factor": c["label"],
                "current": c["score"],
                "potential_gain": round((100 - c["score"]) * c["weight"]),
                "note": c["note"],
            }
            for c in weakest
            if c["score"] < 60
        ],
        "model_version": HEALTH_MODEL_VERSION,
    }


def explain(result: dict) -> str:
    """One short sentence. A score that cannot be explained in a line
    will not be trusted or challenged."""
    if result.get("at_risk"):
        return f"At risk — {result['at_risk_reason']}"
    weakest = result["weakest_factors"]
    if result["score"] >= 75:
        return f"{result['band_label']} — {result['contributions'][0]['note']}."
    if weakest:
        note = next(
            (c["note"] for c in result["contributions"] if c["label"] == weakest[0]),
            weakest[0],
        )
        return f"{result['band_label']} — {note}."
    return result["band_label"]


def trend(current: int, previous: int | None) -> dict:
    """Direction matters more than level.

    A relationship at 60 and falling needs attention; one at 45 and rising
    does not. Reporting only the current score hides that entirely.
    """
    if previous is None:
        return {"direction": "new", "delta": None, "label": "No previous score"}
    delta = current - previous
    if abs(delta) < 5:
        return {"direction": "stable", "delta": delta, "label": "Stable"}
    if delta > 0:
        return {"direction": "strengthening", "delta": delta,
                "label": f"Strengthening (+{delta})"}
    return {"direction": "weakening", "delta": delta, "label": f"Weakening ({delta})"}


# ══════════════════════════════ MOMENTUM ══════════════════════════════
#
# Momentum is not the delta between two readings. `80 → 70 → 60` and
# `50 → 70 → 60` both show "down 10" from the last reading, but they are
# opposite stories: one is a sustained decline, the other a correction
# after a spike. A single delta cannot tell them apart, and an executive
# acting on "down 10" would treat them identically.
#
# So momentum is computed from a SERIES, and combines three signals:
#
#   1. Trajectory  — the slope across recent readings
#   2. Acceleration— whether the slope itself is steepening
#   3. Leading     — signals that precede a score change: response-rate
#      indicators   shifts, overdue follow-ups, a scheduled next meeting
#
# Leading indicators matter most. Health is a lagging measure — by the
# time it falls, the relationship has already cooled. Momentum should
# reach the executive before that.

MOMENTUM_STATES = {
    "improving": {"label": "Improving", "priority": 4},
    "stable": {"label": "Stable", "priority": 3},
    "declining": {"label": "Declining", "priority": 2},
    "critical": {"label": "Critical", "priority": 1},
}

MIN_READINGS_FOR_TRAJECTORY = 3


def _slope(scores: list[int]) -> float:
    """Least-squares slope over evenly spaced readings, in points per
    reading. Simple by design — a heavier statistical model on five data
    points would imply precision that is not there."""
    n = len(scores)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(scores) / n
    numerator = sum((i - mean_x) * (s - mean_y) for i, s in enumerate(scores))
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def compute_momentum(
    score_series: list[int],
    *,
    at_risk: bool = False,
    influence_score: float = 50.0,
    days_since_engagement: int | None = None,
    overdue_followups: int = 0,
    has_scheduled_engagement: bool = False,
    response_rate_change: float | None = None,
) -> dict:
    """Direction of travel, with the reasoning stated.

    `score_series` is oldest-first. Leading indicators are applied on top
    of the trajectory, because they move before the score does.
    """
    signals: list[str] = []

    # --- trajectory -------------------------------------------------------
    if len(score_series) < 2:
        slope = 0.0
        trajectory = "unknown"
        signals.append("Insufficient history to establish a trajectory")
    else:
        recent = score_series[-5:]
        slope = _slope(recent)
        if len(recent) < MIN_READINGS_FOR_TRAJECTORY:
            signals.append(f"Provisional trajectory from {len(recent)} readings")
        if slope >= 3:
            trajectory = "improving"
            signals.append(f"Health rising ~{slope:.0f} points per review")
        elif slope <= -3:
            trajectory = "declining"
            signals.append(f"Health falling ~{abs(slope):.0f} points per review")
        else:
            trajectory = "stable"
            signals.append("Health broadly flat")

    # --- acceleration -----------------------------------------------------
    accelerating = False
    if len(score_series) >= 4:
        first_half = _slope(score_series[-4:-2])
        second_half = _slope(score_series[-2:])
        if second_half < first_half - 2:
            accelerating = True
            signals.append("Decline is steepening")
        elif second_half > first_half + 2:
            signals.append("Improvement is accelerating")

    # --- leading indicators ----------------------------------------------
    # These move before the score does, which is the point of tracking them.
    leading_penalty = 0
    if days_since_engagement is not None and days_since_engagement > 60:
        leading_penalty += 1
        signals.append(f"No contact for {days_since_engagement} days")
    if overdue_followups > 0:
        leading_penalty += 1
        signals.append(
            f"{overdue_followups} follow-up commitment(s) overdue"
        )
    if response_rate_change is not None and response_rate_change < -0.2:
        leading_penalty += 1
        signals.append("Responsiveness has dropped materially")

    leading_credit = 0
    if has_scheduled_engagement:
        leading_credit += 1
        signals.append("Engagement already scheduled")

    # --- resolve ----------------------------------------------------------
    state = trajectory if trajectory != "unknown" else "stable"

    if leading_penalty >= 2 and state != "improving":
        state = "declining"
    elif leading_penalty >= 1 and state == "stable":
        state = "declining"
    if leading_credit and state == "declining" and leading_penalty <= 1:
        state = "stable"
        signals.append("Scheduled contact may arrest the decline")

    # Critical is reserved for the case that actually warrants the word:
    # a relationship that matters commercially and is failing.
    is_critical = (
        (at_risk and influence_score >= 70)
        or (state == "declining" and accelerating and influence_score >= 70)
        or (state == "declining" and leading_penalty >= 3)
    )
    if is_critical:
        state = "critical"
        signals.insert(0, "High-influence relationship failing")

    # The explanation must name the signal that actually DROVE the state,
    # not merely the first one recorded. An earlier version produced
    # "Declining — health broadly flat", which contradicts itself and
    # would rightly make an executive distrust the label.
    decisive = _decisive_signal(state, trajectory, signals, leading_penalty)

    return {
        "state": state,
        "label": MOMENTUM_STATES[state]["label"],
        "priority": MOMENTUM_STATES[state]["priority"],
        "slope": round(slope, 2),
        "accelerating": accelerating,
        "readings_used": len(score_series),
        "is_provisional": len(score_series) < MIN_READINGS_FOR_TRAJECTORY,
        "leading_penalty": leading_penalty,
        "leading_drove_state": leading_penalty > 0 and trajectory != state,
        "signals": signals,
        "decisive_signal": decisive,
        "explanation": f"{MOMENTUM_STATES[state]['label']} — {decisive.lower()}.",
    }


def _decisive_signal(state: str, trajectory: str, signals: list[str],
                     leading_penalty: int) -> str:
    """Which signal explains the state.

    When leading indicators overrode the trajectory, the trajectory signal
    is the wrong thing to show — it is precisely what the override
    disagreed with.
    """
    if not signals:
        return MOMENTUM_STATES[state]["label"]

    leading_phrases = ("No contact for", "follow-up commitment", "Responsiveness has dropped")
    trajectory_phrases = ("Health rising", "Health falling", "Health broadly flat",
                          "Insufficient history")

    if state == "critical":
        return next((s for s in signals if "failing" in s), signals[0])

    if leading_penalty > 0 and trajectory != state:
        lead = next((s for s in signals if s.startswith(leading_phrases)), None)
        if lead:
            return lead

    non_trajectory = [s for s in signals if not s.startswith(trajectory_phrases)]
    if state in ("declining", "critical") and non_trajectory:
        return non_trajectory[0]

    return signals[0]


def combined_priority(health_score: int, momentum: dict, influence_score: float) -> int:
    """Ranks relationships for executive attention.

    Deliberately NOT the health score. A strong relationship needs nothing
    done to it; a declining high-influence one needs a call today. This
    ranks by *where attention changes the outcome*, which is the same
    logic as Executive Focus applied to people.
    """
    # Weakness creates the opportunity to act.
    headroom = 100 - health_score

    momentum_multiplier = {
        "critical": 2.0,
        "declining": 1.5,
        "stable": 1.0,
        "improving": 0.6,   # working — leave it alone
    }[momentum["state"]]

    influence_weight = 0.5 + (influence_score / 100)

    return round(min(100, headroom * momentum_multiplier * influence_weight * 0.6))
