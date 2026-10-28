"""ATLAS Intelligence Pipeline — Sprint 3.

Every recommendation in ATLAS follows the same seven stages:

    1. Collect evidence
    2. Assess data quality
    3. Calculate intelligence models
    4. Identify risks
    5. Generate recommendations
    6. Calculate confidence
    7. Explain reasoning

Consistency here is not tidiness. Before this module, each surface
assembled recommendations its own way — the briefing computed confidence
one way, the advisor another, the coverage index a third. Three
implementations of "how sure are we" produce three different answers to
the same question, and an executive who notices that stops trusting all
three.

THE EVIDENCE WEIGHTING DECISION
================================
Not all evidence is equal, and treating it as though it were is how a
platform ends up confidently wrong. A signed contract and an AI-inferred
relationship should not carry the same weight in a recommendation.

The weights below are deliberately steep: a Tier 1 verified document is
worth roughly ten AI observations. That is not a modelling convenience —
it reflects that an AI observation is a hypothesis and a signed document
is a fact, and averaging them gently would let volume of speculation
outweigh a single hard source.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("atlas.intelligence")

PIPELINE_VERSION = "1.0"


# ═══════════════════════ 1. EVIDENCE FRAMEWORK ═══════════════════════

EVIDENCE_CLASSES = {
    # High confidence — a fact, independently checkable.
    "signed_document": {"weight": 1.00, "tier": "high", "label": "Signed document"},
    "official_announcement": {"weight": 0.95, "tier": "high", "label": "Official announcement"},
    "verified_meeting": {"weight": 0.90, "tier": "high", "label": "Verified meeting"},
    "confirmed_stakeholder": {"weight": 0.85, "tier": "high", "label": "Confirmed stakeholder"},
    "tier_1_source": {"weight": 0.90, "tier": "high", "label": "Tier 1 source"},

    # Medium confidence — real, but single-sourced or unverifiable.
    "confirmed_conversation": {"weight": 0.60, "tier": "medium", "label": "Confirmed conversation"},
    "internal_note": {"weight": 0.50, "tier": "medium", "label": "Internal note"},
    "tier_2_source": {"weight": 0.55, "tier": "medium", "label": "Tier 2 source"},
    "partner_report": {"weight": 0.45, "tier": "medium", "label": "Partner report"},

    # Low confidence — a hypothesis, not a fact.
    "ai_observation": {"weight": 0.15, "tier": "low", "label": "AI observation"},
    "inferred_relationship": {"weight": 0.12, "tier": "low", "label": "Inferred relationship"},
    "assumption": {"weight": 0.10, "tier": "low", "label": "Assumption"},
    "tier_3_source": {"weight": 0.25, "tier": "low", "label": "Tier 3 source"},
    "tier_4_source": {"weight": 0.10, "tier": "low", "label": "Tier 4 source"},
}

# Below this weighted total, a recommendation has no real basis.
MIN_EVIDENCE_WEIGHT_TO_RECOMMEND = 0.8

# Maps Phase 2 source tiers onto evidence classes, so the existing
# evidence model feeds the pipeline without a parallel taxonomy.
_TIER_TO_CLASS = {
    "tier_1": "tier_1_source",
    "tier_2": "tier_2_source",
    "tier_3": "tier_3_source",
    "tier_4": "tier_4_source",
}


def classify_evidence(kind: str, *, is_verified: bool = False) -> dict:
    """Weight and tier for one piece of evidence."""
    entry = EVIDENCE_CLASSES.get(kind)
    if entry is None:
        entry = EVIDENCE_CLASSES["ai_observation"]
        kind = "ai_observation"
    weight = entry["weight"]
    # Unverified high-tier evidence is downgraded, not accepted on trust.
    # A Tier 1 URL nobody has opened is a claim about a source, not a source.
    if entry["tier"] == "high" and not is_verified:
        weight *= 0.7
    return {
        "kind": kind,
        "label": entry["label"],
        "tier": entry["tier"],
        "weight": round(weight, 3),
        "is_verified": is_verified,
    }


def weigh_evidence(items: list[dict]) -> dict:
    """Stage 1. Total weighted evidence supporting a recommendation.

    Returns the composition as well as the total, because "we have six
    sources" and "we have six AI guesses" are different situations that a
    single number would hide.
    """
    classified = []
    for item in items:
        kind = item.get("kind") or _TIER_TO_CLASS.get(item.get("source_tier", ""), "ai_observation")
        classified.append(
            {
                **classify_evidence(kind, is_verified=bool(item.get("is_verified"))),
                "description": item.get("description"),
                "url": item.get("url"),
            }
        )

    total = sum(c["weight"] for c in classified)
    by_tier = {"high": 0, "medium": 0, "low": 0}
    for c in classified:
        by_tier[c["tier"]] += 1

    strongest = max(classified, key=lambda c: c["weight"]) if classified else None

    return {
        "items": sorted(classified, key=lambda c: -c["weight"]),
        "total_weight": round(total, 2),
        "count": len(classified),
        "by_tier": by_tier,
        "strongest": strongest,
        "is_sufficient": total >= MIN_EVIDENCE_WEIGHT_TO_RECOMMEND,
        "summary": _evidence_summary(by_tier, total),
    }


def _evidence_summary(by_tier: dict, total: float) -> str:
    if by_tier["high"]:
        base = f"{by_tier['high']} high-confidence source(s)"
    elif by_tier["medium"]:
        base = f"{by_tier['medium']} medium-confidence source(s)"
    elif by_tier["low"]:
        base = f"{by_tier['low']} low-confidence observation(s) only"
    else:
        return "No supporting evidence"
    extra = []
    if by_tier["high"] and by_tier["medium"]:
        extra.append(f"{by_tier['medium']} medium")
    if by_tier["low"] and (by_tier["high"] or by_tier["medium"]):
        extra.append(f"{by_tier['low']} low")
    return base + (f", plus {', '.join(extra)}" if extra else "")


# ═══════════════════════ 5. RECOMMENDATION ═══════════════════════

EFFORT_LEVELS = {
    "trivial": {"label": "Under an hour", "rank": 1},
    "low": {"label": "A few hours", "rank": 2},
    "medium": {"label": "A day or two", "rank": 3},
    "high": {"label": "A week or more", "rank": 4},
    "major": {"label": "Sustained programme", "rank": 5},
}

IMPACT_LEVELS = {
    "transformational": {"label": "Transformational", "rank": 5},
    "high": {"label": "High", "rank": 4},
    "moderate": {"label": "Moderate", "rank": 3},
    "low": {"label": "Low", "rank": 2},
    "marginal": {"label": "Marginal", "rank": 1},
}


def build_recommendation(
    *,
    action: str,
    because: str,
    impact: str,
    effort: str,
    evidence: dict,
    confidence: dict,
    risks: list[dict] | None = None,
    models: list[str] | None = None,
    next_action: str | None = None,
    owner: str | None = None,
    due: date | None = None,
    subject_id: str | None = None,
    subject_title: str | None = None,
) -> dict:
    """Stages 5–7. One recommendation in the standard shape.

    `because` is a required argument rather than optional metadata. A
    recommendation without a reason is an instruction, and an executive
    cannot evaluate an instruction — only obey or ignore it.

    Priority is impact-over-effort rather than impact alone: a moderate
    gain available in an hour usually beats a high gain needing a week,
    and ranking on impact alone systematically buries the quick wins.
    """
    from .readiness_index import cite

    impact_rank = IMPACT_LEVELS.get(impact, IMPACT_LEVELS["moderate"])["rank"]
    effort_rank = EFFORT_LEVELS.get(effort, EFFORT_LEVELS["medium"])["rank"]

    # Confidence gates priority: a high-impact recommendation ATLAS is not
    # sure about should not outrank a moderate one it is sure about.
    confidence_factor = (confidence.get("score", 50)) / 100
    priority = round((impact_rank / effort_rank) * 20 * (0.5 + confidence_factor))

    should_advise = confidence.get("should_advise", True) and evidence["is_sufficient"]

    return {
        "action": action,
        "because": because,
        "priority": min(100, priority),
        "expected_impact": impact,
        "expected_impact_label": IMPACT_LEVELS.get(impact, {}).get("label", impact),
        "implementation_effort": effort,
        "implementation_effort_label": EFFORT_LEVELS.get(effort, {}).get("label", effort),
        "confidence_score": confidence.get("score"),
        "confidence_band": confidence.get("band_label"),
        "should_advise": should_advise,
        "caveat": (
            confidence.get("caveat")
            or (
                "Evidence is too thin to support this recommendation — "
                f"{evidence['summary'].lower()}."
                if not evidence["is_sufficient"] else None
            )
        ),
        "supporting_evidence": {
            "summary": evidence["summary"],
            "total_weight": evidence["total_weight"],
            "by_tier": evidence["by_tier"],
            "strongest": evidence["strongest"],
            "items": evidence["items"][:5],
        },
        "risks": risks or [],
        "intelligence_models": cite(*(models or [])),
        "next_action": next_action or action,
        "owner": owner,
        "due": due.isoformat() if due else None,
        "subject_id": subject_id,
        "subject_title": subject_title,
        "pipeline_version": PIPELINE_VERSION,
    }


def rank_recommendations(recommendations: list[dict], limit: int | None = None) -> list[dict]:
    """Highest priority first, with un-advisable ones demoted.

    A recommendation ATLAS is not confident enough to make still appears —
    suppressing it entirely would hide a real situation — but it ranks
    below everything actionable and carries its caveat.
    """
    advisable = [r for r in recommendations if r["should_advise"]]
    withheld = [r for r in recommendations if not r["should_advise"]]
    advisable.sort(key=lambda r: -r["priority"])
    withheld.sort(key=lambda r: -r["priority"])
    ordered = advisable + withheld
    return ordered[:limit] if limit else ordered


# ═══════════════════════ full pipeline ═══════════════════════

def run_pipeline(
    *,
    subject_id: str,
    subject_title: str,
    evidence_items: list[dict],
    model_results: dict[str, dict],
    risk_items: list[dict],
    recommendation_specs: list[dict],
    data_quality: dict,
    confidence_inputs: dict,
) -> dict:
    """All seven stages, in order, with each stage's output retained.

    Retaining intermediate stages is what makes the pipeline auditable:
    an executive who distrusts a recommendation can see the evidence it
    weighed, the models that ran, and the confidence that gated it —
    rather than being told to trust the output.
    """
    from .readiness_index import compute_confidence

    # 1. collect evidence
    evidence = weigh_evidence(evidence_items)

    # 2. assess data quality — supplied by the caller, which knows what
    #    "complete" means for its own domain
    quality = data_quality

    # 3. models already calculated by the caller; recorded for audit
    models_run = list(model_results.keys())

    # 4. risks
    risks = sorted(
        risk_items,
        key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.get("severity", "low"), 3),
    )

    # 6. confidence (computed before 5 so it can gate the recommendations)
    confidence = compute_confidence(confidence_inputs)

    # 5. recommendations
    recommendations = [
        build_recommendation(
            evidence=evidence,
            confidence=confidence,
            risks=[r for r in risks if r.get("relates_to") in (None, spec.get("action"))],
            subject_id=subject_id,
            subject_title=subject_title,
            **spec,
        )
        for spec in recommendation_specs
    ]
    recommendations = rank_recommendations(recommendations)

    # 7. explanation
    explanation = _pipeline_explanation(evidence, confidence, recommendations, risks)

    return {
        "subject_id": subject_id,
        "subject_title": subject_title,
        "stages": {
            "1_evidence": evidence,
            "2_data_quality": quality,
            "3_models_run": models_run,
            "4_risks": risks,
            "5_recommendations": recommendations,
            "6_confidence": confidence,
            "7_explanation": explanation,
        },
        "headline_recommendation": recommendations[0] if recommendations else None,
        "pipeline_version": PIPELINE_VERSION,
        "ai_calls_used": 0,
    }


def _pipeline_explanation(evidence: dict, confidence: dict,
                          recommendations: list[dict], risks: list[dict]) -> dict:
    """Stage 7. Answers the three questions every score must answer."""
    top = recommendations[0] if recommendations else None
    return {
        "why": top["because"] if top else "No recommendation could be generated.",
        "biggest_contributing_factors": [
            f["label"] for f in confidence.get("factors", [])[:3]
        ],
        "what_would_improve_this": [
            item["action"] for item in confidence.get("what_would_raise_confidence", [])
        ],
        "evidence_basis": evidence["summary"],
        "material_risks": [r["summary"] for r in risks if r.get("severity") == "high"][:3],
        "confidence_statement": confidence.get("explanation"),
    }


# ═══════════════════ recommendation quality (Sprint 5) ═══════════════════
#
# A recommendation can be well-formed and still useless: correctly
# structured, properly cited, and about something no executive would act
# on. Quality scoring catches that class of failure, which none of the
# other models can see.

QUALITY_DIMENSIONS = {
    "evidence_quality": {
        "weight": 0.28,
        "label": "Evidence quality",
        "why": "A recommendation is only as sound as what supports it.",
    },
    "confidence": {
        "weight": 0.24,
        "label": "Confidence",
        "why": "Low-confidence advice presented as certain is worse than none.",
    },
    "completeness": {
        "weight": 0.20,
        "label": "Completeness",
        "why": "Missing owner, date or reason makes a recommendation unactionable.",
    },
    "commercial_relevance": {
        "weight": 0.16,
        "label": "Commercial relevance",
        "why": "Advice about something with no commercial consequence wastes attention.",
    },
    "executive_usefulness": {
        "weight": 0.12,
        "label": "Executive usefulness",
        "why": "An executive should be able to act on it without further work.",
    },
}

QUALITY_THRESHOLD = 55


def score_recommendation_quality(recommendation: dict, *,
                                 subject_focus_score: int | None = None,
                                 subject_value: float | None = None) -> dict:
    """Whether this recommendation is worth an executive's attention.

    Below `QUALITY_THRESHOLD` the recommendation is marked
    `below_threshold` with the reason stated, rather than quietly shown
    alongside good ones.
    """
    evidence = recommendation.get("supporting_evidence", {})
    by_tier = evidence.get("by_tier", {})

    # evidence
    if by_tier.get("high"):
        ev_score, ev_note = 90, f"{by_tier['high']} high-confidence source(s)"
    elif by_tier.get("medium"):
        ev_score, ev_note = 60, f"{by_tier['medium']} medium-confidence source(s)"
    elif by_tier.get("low"):
        ev_score, ev_note = 25, "Low-confidence observations only"
    else:
        ev_score, ev_note = 0, "No supporting evidence"

    # confidence
    conf_score = recommendation.get("confidence_score") or 0
    conf_note = recommendation.get("confidence_band") or "Not assessed"

    # completeness — the fields that make advice actionable
    required = {
        "action": recommendation.get("action"),
        "reason": recommendation.get("because"),
        "next action": recommendation.get("next_action"),
        "owner": recommendation.get("owner"),
        "due date": recommendation.get("due"),
    }
    present = [k for k, v in required.items() if v]
    missing = [k for k, v in required.items() if not v]
    completeness = round(len(present) / len(required) * 100)
    comp_note = f"Missing: {', '.join(missing)}" if missing else "All fields present"

    # commercial relevance
    if subject_value is not None and subject_value > 0:
        rel_score = 85
        rel_note = f"Attached to an opportunity worth {round(subject_value):,}"
    elif subject_focus_score is not None:
        rel_score = min(90, 30 + subject_focus_score)
        rel_note = f"Executive Focus {subject_focus_score}"
    else:
        rel_score = 35
        rel_note = "No commercial consequence established"

    # executive usefulness — can it be acted on as written?
    impact_rank = IMPACT_LEVELS.get(
        recommendation.get("expected_impact", "moderate"), {"rank": 3}
    )["rank"]
    effort_rank = EFFORT_LEVELS.get(
        recommendation.get("implementation_effort", "medium"), {"rank": 3}
    )["rank"]
    useful = round(min(100, (impact_rank / effort_rank) * 35))
    use_note = (
        f"{recommendation.get('expected_impact_label', 'Moderate')} impact for "
        f"{recommendation.get('implementation_effort_label', 'moderate')} effort"
    )

    values = {
        "evidence_quality": (ev_score, ev_note),
        "confidence": (conf_score, conf_note),
        "completeness": (completeness, comp_note),
        "commercial_relevance": (rel_score, rel_note),
        "executive_usefulness": (useful, use_note),
    }

    contributions = []
    total = 0.0
    for key, meta in QUALITY_DIMENSIONS.items():
        score, note = values[key]
        contribution = score * meta["weight"]
        total += contribution
        contributions.append(
            {
                "dimension": key,
                "label": meta["label"],
                "why_it_matters": meta["why"],
                "score": round(score),
                "weight": meta["weight"],
                "contribution": round(contribution, 2),
                "note": note,
            }
        )

    score = round(_clamp_quality(total))
    weakest = sorted(contributions, key=lambda c: c["score"])[:2]
    below = score < QUALITY_THRESHOLD

    return {
        "score": score,
        "below_threshold": below,
        "threshold": QUALITY_THRESHOLD,
        "dimensions": sorted(contributions, key=lambda c: -c["contribution"]),
        "weakest": [c["label"] for c in weakest],
        "reason_below_threshold": (
            "; ".join(f"{c['label']}: {c['note']}" for c in weakest) if below else None
        ),
        "how_to_improve": [
            {"dimension": c["label"], "current": c["score"], "note": c["note"]}
            for c in weakest
            if c["score"] < 70
        ],
    }


def _clamp_quality(v: float) -> float:
    return max(0.0, min(100.0, v))
