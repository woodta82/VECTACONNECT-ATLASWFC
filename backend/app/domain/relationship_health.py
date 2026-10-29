"""Relationship health, momentum and attention (29 Oct 2026: the ATLAS v1.0 relationship parameters). Framework-free.

Answers: is this relationship getting stronger or weaker, and does it matter commercially? Two decisions carried over from
ATLAS v1.0, because both are easy to get wrong:

1. Health decays. A strong relationship untouched for six months is not strong any more. Recency carries the heaviest
   weight and the decay is non-linear: 10 versus 30 days barely matters; 90 versus 180 is severe.
2. Health is weighted by influence. A warm relationship with someone who cannot affect a decision is pleasant; a cold one
   with the economic buyer is a live problem. So influence and strategic value are inputs, not separate metrics, and a
   high-influence relationship that has gone quiet is capped at 40 ("at risk") however good its other factors.

Every factor produces a note, and the result lists the weakest factors with the points each could recover. Health is a
measure of a relationship's upkeep from facts the team recorded (engagements, outcomes, their own stakeholder judgements);
it is NOT a probability of winning, it never changes a person's derived research state, and it is "not assessed" until at
least one engagement or judgement is recorded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HEALTH_MODEL_VERSION = "1.0-wfc"

WEIGHTS: dict[str, float] = {"recency": 0.24, "frequency": 0.16, "responsiveness": 0.14, "meeting_outcomes": 0.14, "influence": 0.14,
                             "opportunity_alignment": 0.10, "strategic_value": 0.08}
LABELS = {"recency": "Recency", "frequency": "Frequency", "responsiveness": "Responsiveness", "meeting_outcomes": "Meeting outcomes",
          "influence": "Influence", "opportunity_alignment": "Opportunity alignment", "strategic_value": "Strategic value"}
BANDS = (("strong", "Strong", 75, 100), ("healthy", "Healthy", 55, 74), ("cooling", "Cooling", 35, 54), ("weak", "Weak", 15, 34),
         ("dormant", "Dormant", 0, 14))

STAKEHOLDER_TYPES = {"economic_buyer": "Economic buyer", "budget_holder": "Budget holder", "programme_sponsor": "Programme sponsor",
                     "procurement_authority": "Procurement authority", "political_sponsor": "Political sponsor",
                     "technical_evaluator": "Technical evaluator", "technical_influencer": "Technical influencer", "adviser": "Adviser",
                     "gatekeeper": "Gatekeeper", "introducer": "Introducer", "delivery_partner": "Delivery partner",
                     "consultant": "Consultant", "unknown": "Not yet judged"}
DECISION_AUTHORITY = {"final": "Final say", "shared": "Shared decision", "influence": "Influences the decision", "none": "No authority",
                      "unknown": "Not established"}
POSTURES = {"champion": "Champion", "supportive": "Supportive", "neutral": "Neutral", "sceptical": "Sceptical", "blocker": "Blocker",
            "unknown": "Not yet judged"}
# "unknown" sits mid-range on purpose: an unjudged stakeholder is a gap to close, not a person who does not matter.
INFLUENCE_SCORES = {"economic_buyer": 100, "budget_holder": 95, "programme_sponsor": 85, "procurement_authority": 80, "political_sponsor": 75,
                    "technical_evaluator": 65, "technical_influencer": 60, "adviser": 50, "gatekeeper": 45, "introducer": 40,
                    "delivery_partner": 35, "consultant": 30, "unknown": 45}
CRITICAL_ROLES = ("economic_buyer", "budget_holder", "procurement_authority")

AT_RISK_INFLUENCE_FLOOR = 70     # economic buyer, budget holder, sponsor, procurement authority
AT_RISK_RECENCY_CEILING = 45     # roughly 90+ days since contact


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ------------------------------------------------------------------ factors
def recency(last_engagement: Any, now: datetime) -> dict[str, Any]:
    last = _dt(last_engagement)
    if last is None:
        return {"score": 0.0, "note": "No engagement recorded"}
    days = int((now - last).total_seconds() // 86400)
    if days < 0:
        return {"score": 100.0, "note": "Engagement scheduled", "days_since": days}
    if days <= 14:
        s, n = 100.0, f"Engaged {days} day(s) ago"
    elif days <= 30:
        s, n = 85.0, f"Engaged {days} days ago"
    elif days <= 60:
        s, n = 65.0, f"{days} days since contact"
    elif days <= 90:
        s, n = 45.0, f"{days} days since contact"
    elif days <= 180:
        s, n = 22.0, f"{days} days since contact: cooling"
    else:
        s, n = 5.0, f"{days} days since contact: effectively dormant"
    return {"score": s, "note": n, "days_since": days}


def frequency(engagements_12m: int, months_known: int | None = None) -> dict[str, Any]:
    if engagements_12m == 0:
        return {"score": 0.0, "note": "No engagements in the last 12 months"}
    s = 100.0 if engagements_12m >= 12 else 80.0 if engagements_12m >= 6 else 60.0 if engagements_12m >= 3 else 40.0 if engagements_12m >= 2 else 25.0
    n = f"{engagements_12m} engagement(s) in 12 months" + (" (new relationship)" if months_known is not None and months_known < 3 else "")
    return {"score": s, "note": n}


def responsiveness(outbound: int, answered: int) -> dict[str, Any]:
    """Outbound approaches that got an answer (any outcome but no_response or pending). The most honest signal."""
    if outbound == 0:
        return {"score": 50.0, "note": "No outbound contact to measure"}
    rate = answered / outbound
    s = _clamp(rate * 100)
    n = (f"Responds reliably ({answered}/{outbound})" if rate >= 0.7 else f"Responds sometimes ({answered}/{outbound})" if rate >= 0.4
         else f"Rarely responds ({answered}/{outbound})" if rate > 0 else f"Never responded ({outbound} approach(es))")
    return {"score": s, "note": n}


def meeting_outcomes(positive: int, neutral: int, negative: int) -> dict[str, Any]:
    """A negative outcome weighs more than a positive one: meetings that go badly are the more informative."""
    total = positive + neutral + negative
    if total == 0:
        return {"score": 50.0, "note": "No engagement outcomes recorded"}
    raw = (positive * 100 + neutral * 50) / total
    return {"score": _clamp(raw - min(20, negative * 10)), "note": f"{positive} positive, {neutral} neutral, {negative} negative"}


def influence(stakeholder_type: str | None, decision_authority: str | None = None) -> dict[str, Any]:
    base = INFLUENCE_SCORES.get(stakeholder_type or "unknown", 45)
    if decision_authority == "final":
        base = max(base, 90)
    elif decision_authority == "none":
        base = min(base, 35)
    n = STAKEHOLDER_TYPES.get(stakeholder_type or "unknown", "Not yet judged")
    if decision_authority and decision_authority != "unknown":
        n += f", {DECISION_AUTHORITY[decision_authority].lower()}"
    return {"score": float(base), "note": n}


def opportunity_alignment(linked_live: int, best_opportunity_score: int | None = None) -> dict[str, Any]:
    if linked_live == 0:
        return {"score": 20.0, "note": "Not linked to any live opportunity"}
    base = min(100.0, 45.0 + linked_live * 15)
    if best_opportunity_score is not None:
        base = max(base, float(best_opportunity_score))
    return {"score": _clamp(base), "note": f"Linked to {linked_live} live opportunit{'y' if linked_live == 1 else 'ies'}"
            + (f"; best opportunity score {best_opportunity_score}" if best_opportunity_score is not None else "")}


def strategic_value(strategic_account: bool, in_saved_search_scope: bool, organisation_kind: str | None) -> dict[str, Any]:
    s, notes = 40.0, []
    if strategic_account:
        s += 35
        notes.append("Strategic account (marked by the team)")
    if in_saved_search_scope:
        s += 15
        notes.append("In a market the team searches")
    if organisation_kind in ("airline", "airport_operator"):
        s += 10
        notes.append({"airline": "Airline", "airport_operator": "Airport operator"}[organisation_kind] + " counterparty")
    return {"score": _clamp(s), "note": "; ".join(notes) or "No strategic weighting recorded"}


# ------------------------------------------------------------------ compose
def band(score: int) -> tuple[str, str]:
    for key, label, lo, hi in BANDS:
        if lo <= score <= hi:
            return key, label
    return "dormant", "Dormant"


def compute(components: dict[str, dict[str, Any]], *, assessed: bool = True) -> dict[str, Any]:
    """Weighted composition with the full breakdown and the at-risk override (influence amplifies decay, never offsets it)."""
    if not assessed:
        return {"assessed": False, "score": None, "band": None, "band_label": "Not assessed", "at_risk": False, "at_risk_reason": None,
                "contributions": [], "strongest_factors": [], "weakest_factors": [], "improvement_levers": [],
                "model_version": HEALTH_MODEL_VERSION, "note": "No engagement or stakeholder judgement recorded yet"}
    contributions, total = [], 0.0
    for key, w in WEIGHTS.items():
        c = components.get(key) or {"score": 0.0, "note": "Not assessed"}
        v = _clamp(float(c.get("score", 0.0)))
        contributions.append({"factor": key, "label": LABELS[key], "score": round(v), "weight": w, "contribution": round(v * w, 2),
                              "note": c.get("note")})
        total += v * w
    score = round(total)
    inf = _clamp(float((components.get("influence") or {}).get("score", 0)))
    rec = _clamp(float((components.get("recency") or {}).get("score", 0)))
    at_risk = inf >= AT_RISK_INFLUENCE_FLOOR and rec <= AT_RISK_RECENCY_CEILING
    reason = None
    if at_risk:
        score = min(score, 40)                # capped, not zeroed: the relationship exists; it must not read as healthy
        reason = f"High-influence relationship has gone quiet: {(components.get('recency') or {}).get('note', 'no recent contact')}"
    key, label = band(score)
    contributions.sort(key=lambda c: c["contribution"], reverse=True)
    weakest = sorted(contributions, key=lambda c: c["score"])[:2]
    return {"assessed": True, "score": score, "band": key, "band_label": label, "at_risk": at_risk, "at_risk_reason": reason,
            "contributions": contributions, "strongest_factors": [c["label"] for c in contributions[:2]],
            "weakest_factors": [c["label"] for c in weakest],
            "improvement_levers": [{"factor": c["label"], "current": c["score"], "potential_gain": round((100 - c["score"]) * c["weight"]),
                                    "note": c["note"]} for c in weakest if c["score"] < 60],
            "model_version": HEALTH_MODEL_VERSION}


def explain(h: dict[str, Any]) -> str:
    if not h.get("assessed"):
        return "Not assessed: no engagement or stakeholder judgement recorded yet"
    if h["at_risk"]:
        return f"{h['band_label']} ({h['score']}): {h['at_risk_reason']}"
    strong = " and ".join(h["strongest_factors"][:2]).lower()
    weak = " and ".join(h["weakest_factors"][:2]).lower()
    return f"{h['band_label']} ({h['score']}): held up by {strong}; weakest on {weak}"


# ------------------------------------------------------------------ momentum (from the engagement record, no stored history needed)
def momentum(engagements: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Compares the last 90 days with the 90 before: count and outcome quality. States: new, improving, stable, declining, dormant."""
    recent, prior = [], []
    for e in engagements:
        at = _dt(e.get("occurred_at"))
        if at is None:
            continue
        days = (now - at).total_seconds() / 86400
        if 0 <= days <= 90:
            recent.append(e)
        elif 90 < days <= 180:
            prior.append(e)
    if not engagements:
        return {"state": "new", "label": "No history", "explanation": "No engagement recorded yet", "recent": 0, "prior": 0}

    def quality(es: list[dict[str, Any]]) -> float:
        vals = [{"positive": 1.0, "neutral": 0.5, "pending": 0.5, "negative": 0.0, "no_response": 0.0}.get(e.get("outcome") or "pending", 0.5) for e in es]
        return sum(vals) / len(vals) if vals else 0.5
    if not recent and not prior:
        return {"state": "dormant", "label": "Dormant", "explanation": "Nothing recorded in the last 180 days", "recent": 0, "prior": 0}
    if recent and not prior:
        older = len(engagements) - len(recent)
        return {"state": "new" if not older else "improving", "label": "New" if not older else "Improving",
                "explanation": f"{len(recent)} engagement(s) in the last 90 days" + ("" if not older else ", none in the 90 before"),
                "recent": len(recent), "prior": 0}
    if prior and not recent:
        return {"state": "declining", "label": "Declining", "explanation": f"No engagement in the last 90 days after {len(prior)} in the 90 before",
                "recent": 0, "prior": len(prior)}
    qr, qp = quality(recent), quality(prior)
    delta = (len(recent) - len(prior)) / max(len(prior), 1)
    # outcome quality first: more meetings that go badly is not improvement
    if qp - qr >= 0.25:
        state, label = "declining", "Declining"
    elif qr - qp >= 0.25:
        state, label = "improving", "Improving"
    elif delta >= 0.5:
        state, label = "improving", "Improving"
    elif delta <= -0.5:
        state, label = "declining", "Declining"
    else:
        state, label = "stable", "Stable"
    return {"state": state, "label": label, "recent": len(recent), "prior": len(prior),
            "explanation": f"{len(recent)} engagement(s) in the last 90 days against {len(prior)} before; outcome quality {qr:.0%} against {qp:.0%}"}


def attention(health: dict[str, Any], mom: dict[str, Any], influence_score: float) -> int:
    """Where an hour changes an outcome: high influence, low or falling health. Not a ranking by health."""
    if not health.get("assessed"):
        return round(influence_score * 0.6)
    gap = 100 - float(health["score"])
    trend = {"declining": 20, "dormant": 15, "new": 5, "stable": 0, "improving": -10}.get(mom.get("state", "stable"), 0)
    risk = 15 if health.get("at_risk") else 0
    return int(_clamp(influence_score * 0.45 + gap * 0.35 + trend + risk))


def recommended_action(person: dict[str, Any], health: dict[str, Any], mom: dict[str, Any]) -> str:
    name = person.get("full_name") or "this person"
    if not health.get("assessed"):
        return f"Record the stakeholder judgement for {name} and the first engagement"
    if health.get("at_risk"):
        return f"Contact {name} this week: a high-influence relationship has gone quiet"
    if mom.get("state") == "declining":
        return f"Re-engage {name} before the relationship cools further"
    if health["score"] < 35:
        return f"Rebuild contact with {name}: propose a meeting or an introduction"
    if person.get("posture") in ("sceptical", "blocker"):
        return f"Address {name}'s concerns: record what they object to and who can help"
    return f"Keep the rhythm with {name}; record the next engagement when it happens"
