"""Commercial Readiness Index and Decision Confidence Score — Sprint 2.2.

Two models completing the ATLAS intelligence framework.

**CRI answers**: are we genuinely ready to pursue this?
**DCS answers**: how much should you trust what ATLAS just told you?

DCS is the more important of the two, and the more unusual. Most systems
present every recommendation with identical authority — the confidently
wrong one looks exactly like the well-evidenced one. DCS is the model
that governs the others: it measures the reliability of a recommendation
and, below a threshold, requires ATLAS to say plainly that it does not
know enough.

Its most distinctive input is **historical accuracy**, drawn from the
Decision Journal. A system that has been wrong about this kind of
recommendation before should say so. That closes the loop between
recommending and learning, and it is the part a competitor cannot copy
by adding a field.
"""
from __future__ import annotations

from datetime import date

CRI_MODEL_VERSION = "1.0"
DCS_MODEL_VERSION = "1.0"


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ══════════════════ Commercial Readiness Index (CRI) ══════════════════
#
# Readiness is not attractiveness. An opportunity can be highly
# attractive and completely unready — that combination is the most
# expensive mistake in pursuit management, because it converts enthusiasm
# into wasted bid cost.

CRI_DIMENSIONS = {
    "qualification": {
        "weight": 0.22,
        "label": "Qualification completeness",
        "why": "An unqualified pursuit may be ineligible, mis-scoped or already lost.",
    },
    "relationship_maturity": {
        "weight": 0.20,
        "label": "Relationship maturity",
        "why": "Bidding without access means writing to a brief you cannot verify.",
    },
    "evidence_quality": {
        "weight": 0.18,
        "label": "Evidence quality",
        "why": "Weak evidence means the opportunity itself may not be as described.",
    },
    "delivery_capability": {
        "weight": 0.16,
        "label": "Delivery capability",
        "why": "Winning work VECTA cannot deliver is worse than losing it.",
    },
    "resource_availability": {
        "weight": 0.14,
        "label": "Resource availability",
        "why": "Bid effort and mobilisation compete with committed pursuits.",
    },
    "strategic_alignment": {
        "weight": 0.10,
        "label": "Strategic alignment",
        "why": "Off-strategy wins consume capacity that on-strategy pursuits need.",
    },
}

CRI_BANDS = [
    {"min": 80, "max": 100, "key": "ready", "label": "Ready to pursue"},
    {"min": 60, "max": 79, "key": "mostly_ready", "label": "Mostly ready"},
    {"min": 40, "max": 59, "key": "gaps", "label": "Material gaps"},
    {"min": 20, "max": 39, "key": "not_ready", "label": "Not ready"},
    {"min": 0, "max": 19, "key": "unprepared", "label": "Unprepared"},
]


def cri_band(score: float) -> dict:
    for band in CRI_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return CRI_BANDS[-1]


def compute_readiness(dimensions: dict[str, dict]) -> dict:
    """Weighted readiness with the weakest dimensions named.

    Naming the weakest is the whole point. "You are 54% ready" is not
    actionable; "delivery capability is your weakest dimension because
    two specialists are already committed" is.
    """
    contributions = []
    total = 0.0
    for key, meta in CRI_DIMENSIONS.items():
        entry = dimensions.get(key) or {"score": 0, "note": "Not assessed"}
        value = _clamp(float(entry.get("score", 0)))
        contribution = value * meta["weight"]
        total += contribution
        contributions.append(
            {
                "dimension": key,
                "label": meta["label"],
                "why_it_matters": meta["why"],
                "score": round(value),
                "weight": meta["weight"],
                "contribution": round(contribution, 2),
                "note": entry.get("note"),
                "is_blocking": value < 40,
            }
        )

    score = round(_clamp(total))
    weakest = sorted(contributions, key=lambda c: c["score"])[:3]
    blocking = [c for c in contributions if c["is_blocking"]]

    # A blocking dimension caps the band. An earlier version reported
    # "Mostly ready (62). Blocked by relationship maturity" — which
    # contradicts itself, and an executive reading only the band would
    # commit resources to a pursuit that cannot proceed. Same logic as
    # the RCI critical-role cap: a weighted average flatters where a
    # single dimension is decisive.
    cap_reason = None
    if blocking:
        cap = 59 if len(blocking) == 1 else 39
        if score > cap:
            cap_reason = (
                f"Capped at {cap}: "
                + ", ".join(b["label"].lower() for b in blocking)
                + " below the viability threshold."
            )
            score = cap

    band = cri_band(score)

    # Weight x headroom: a heavily-weighted dimension at 30 matters more
    # than a light one at 10, which severity-sorting alone would miss.
    lever = None
    if weakest:
        best = max(contributions, key=lambda c: c["weight"] * (100 - c["score"]))
        lever = {
            "dimension": best["label"],
            "current": best["score"],
            "potential_gain": round(best["weight"] * (100 - best["score"])),
            "note": best["note"],
        }

    return {
        "score": score,
        "band": band["key"],
        "band_label": band["label"],
        "dimensions": sorted(contributions, key=lambda c: -c["contribution"]),
        "weakest_dimensions": [c["label"] for c in weakest],
        "blocking_dimensions": [c["label"] for c in blocking],
        "biggest_lever": lever,
        "cap_reason": cap_reason,
        "explanation": _cri_explain(score, band, weakest, blocking),
        "model_version": CRI_MODEL_VERSION,
    }


def _cri_explain(score: int, band: dict, weakest: list[dict],
                 blocking: list[dict]) -> str:
    if blocking:
        names = ", ".join(c["label"].lower() for c in blocking[:2])
        return f"{band['label']} ({score}). Blocked by {names}."
    if weakest and weakest[0]["score"] < 60:
        return f"{band['label']} ({score}). Weakest: {weakest[0]['label'].lower()}."
    return f"{band['label']} ({score}). No material readiness gaps."


# ══════════════════ Decision Confidence Score (DCS) ══════════════════
#
# The model that governs the others. Without it every recommendation
# carries identical authority, and the confidently wrong one is
# indistinguishable from the well-evidenced one.

DCS_FACTORS = {
    "evidence_quality": {
        "weight": 0.28,
        "label": "Evidence quality",
        "why": "A recommendation is only as sound as what it rests on.",
    },
    "data_completeness": {
        "weight": 0.24,
        "label": "Data completeness",
        "why": "Partial data produces confident conclusions from thin inputs.",
    },
    "historical_accuracy": {
        "weight": 0.22,
        "label": "Historical accuracy",
        "why": "Has ATLAS been right about this kind of recommendation before?",
    },
    "assumption_load": {
        "weight": 0.16,
        "label": "Assumption load",
        "why": "Every unverified assumption is a way the recommendation can be wrong.",
    },
    "model_certainty": {
        "weight": 0.10,
        "label": "Model certainty",
        "why": "Coverage and consistency across the contributing models.",
    },
}

DCS_BANDS = [
    {"min": 75, "max": 100, "key": "high", "label": "High confidence"},
    {"min": 50, "max": 74, "key": "moderate", "label": "Moderate confidence"},
    {"min": 30, "max": 49, "key": "low", "label": "Low confidence"},
    {"min": 0, "max": 29, "key": "insufficient", "label": "Insufficient basis"},
]

# Below this, ATLAS must state that it does not know enough rather than
# present a recommendation as though it did.
#
# Raised from 30 to 40 after calibration. A single Tier 3 article with four
# open assumptions scored 31 and was permitted to advise — one point of
# margin on the platform's most important safety gate is too fine. The
# asymmetry justifies it: withholding advice that would have been sound
# costs an executive nothing, while giving advice that should have been
# withheld costs the platform its credibility.
DCS_ADVISORY_FLOOR = 40


def dcs_band(score: float) -> dict:
    for band in DCS_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return DCS_BANDS[-1]


def evidence_quality_factor(tier_1_count: int, validated_count: int,
                            total_evidence: int) -> dict:
    """Note the inversion from Executive Focus.

    In EFS, weak evidence scores HIGH — verification is an action worth
    taking. Here it scores LOW, because the question is different: not
    "is there work to do" but "should you believe this". Same input,
    opposite meaning, and conflating them would be a real bug.
    """
    if total_evidence == 0:
        return {"score": 0, "note": "No evidence — nothing supports this"}
    if tier_1_count and validated_count:
        return {"score": 95, "note": f"{tier_1_count} validated Tier 1 source(s)"}
    if tier_1_count:
        return {"score": 65, "note": f"{tier_1_count} Tier 1 source(s), URLs unverified"}
    if validated_count:
        return {"score": 45, "note": "Validated sources, none authoritative"}
    return {"score": 25, "note": f"{total_evidence} unverified source(s)"}


def data_completeness_factor(score_coverage_percent: float,
                             qualification_answered: int, qualification_total: int,
                             stakeholders_mapped: int) -> dict:
    """How much of what should be known, is known."""
    parts = [score_coverage_percent]
    if qualification_total:
        parts.append(qualification_answered / qualification_total * 100)
    parts.append(min(100, stakeholders_mapped * 25))
    value = sum(parts) / len(parts)
    gaps = []
    if score_coverage_percent < 80:
        gaps.append(f"score coverage {round(score_coverage_percent)}%")
    if qualification_total and qualification_answered < qualification_total:
        gaps.append(f"{qualification_total - qualification_answered} qualification item(s) open")
    if stakeholders_mapped == 0:
        gaps.append("no stakeholders mapped")
    return {
        "score": round(_clamp(value)),
        "note": "; ".join(gaps) if gaps else "Data substantially complete",
    }


def historical_accuracy_factor(accuracy_rate: float | None,
                               sample_size: int,
                               min_sample: int = 10) -> dict:
    """Has ATLAS been right before?

    Below the sample floor this returns a NEUTRAL 50 rather than a
    flattering default. Claiming high confidence because there is no
    contrary evidence yet is exactly the failure mode this model exists
    to prevent.
    """
    if accuracy_rate is None or sample_size == 0:
        return {
            "score": 50,
            "note": "No outcome history yet — confidence is unproven, not high",
        }
    if sample_size < min_sample:
        return {
            "score": 50,
            "note": (
                f"Only {sample_size} scored outcome(s) — too few to adjust confidence "
                f"({min_sample} needed)"
            ),
        }
    return {
        "score": round(_clamp(accuracy_rate * 100)),
        "note": f"{round(accuracy_rate * 100)}% accurate across {sample_size} decisions",
    }


def assumption_load_factor(active_assumptions: int, invalidated: int = 0,
                           overdue_review: int = 0) -> dict:
    """Every unverified assumption is a way to be wrong.

    An invalidated assumption still attached to a live recommendation is
    weighted hardest — it is not a risk, it is a known error.
    """
    if invalidated:
        return {
            "score": 10,
            "note": f"{invalidated} assumption(s) already invalidated but still relied upon",
        }
    penalty = active_assumptions * 12 + overdue_review * 15
    score = _clamp(100 - penalty)
    notes = []
    if active_assumptions:
        notes.append(f"{active_assumptions} active assumption(s)")
    if overdue_review:
        notes.append(f"{overdue_review} past review date")
    return {"score": round(score), "note": "; ".join(notes) or "No open assumptions"}


def model_certainty_factor(models_available: int, models_expected: int,
                           conflicting_signals: int = 0) -> dict:
    """Do the contributing models agree, and are they all present?"""
    if models_expected == 0:
        return {"score": 50, "note": "No models contributing"}
    availability = models_available / models_expected * 100
    score = _clamp(availability - conflicting_signals * 15)
    notes = [f"{models_available}/{models_expected} models available"]
    if conflicting_signals:
        notes.append(f"{conflicting_signals} conflicting signal(s)")
    return {"score": round(score), "note": "; ".join(notes)}


def compute_confidence(factors: dict[str, dict]) -> dict:
    """Whether this recommendation should be believed.

    Below `DCS_ADVISORY_FLOOR` the output carries `should_advise=False`,
    and the consuming surface must say ATLAS does not know enough rather
    than presenting a recommendation with false authority.
    """
    contributions = []
    total = 0.0
    for key, meta in DCS_FACTORS.items():
        entry = factors.get(key) or {"score": 0, "note": "Not assessed"}
        value = _clamp(float(entry.get("score", 0)))
        contribution = value * meta["weight"]
        total += contribution
        contributions.append(
            {
                "factor": key,
                "label": meta["label"],
                "why_it_matters": meta["why"],
                "score": round(value),
                "weight": meta["weight"],
                "contribution": round(contribution, 2),
                "note": entry.get("note"),
            }
        )

    score = round(_clamp(total))
    band = dcs_band(score)
    weakest = sorted(contributions, key=lambda c: c["score"])[:2]

    should_advise = score >= DCS_ADVISORY_FLOOR
    caveat = None
    if not should_advise:
        caveat = (
            "ATLAS does not have enough reliable information to recommend a course of "
            "action here. "
            + "; ".join(f"{c['label']}: {c['note']}" for c in weakest if c["note"])
            + "."
        )

    return {
        "score": score,
        "band": band["key"],
        "band_label": band["label"],
        "should_advise": should_advise,
        "caveat": caveat,
        "factors": sorted(contributions, key=lambda c: -c["contribution"]),
        "weakest_factors": [c["label"] for c in weakest],
        "what_would_raise_confidence": [
            {
                "factor": c["label"],
                "current": c["score"],
                "potential_gain": round(c["weight"] * (100 - c["score"])),
                "action": _confidence_action(c["factor"]),
            }
            for c in weakest
            if c["score"] < 70
        ],
        "explanation": _dcs_explain(score, band, weakest, should_advise),
        "model_version": DCS_MODEL_VERSION,
    }


def _confidence_action(factor: str) -> str:
    return {
        "evidence_quality": "Validate sources or find a Tier 1 reference",
        "data_completeness": "Complete qualification and map stakeholders",
        "historical_accuracy": "Record outcomes on past decisions",
        "assumption_load": "Verify or retire open assumptions",
        "model_certainty": "Complete scoring so all models can contribute",
    }.get(factor, "Improve the underlying data")


def _dcs_explain(score: int, band: dict, weakest: list[dict], should_advise: bool) -> str:
    if not should_advise:
        return f"{band['label']} ({score}) — ATLAS should not advise on this yet."
    if weakest and weakest[0]["score"] < 50:
        return f"{band['label']} ({score}). Limited by {weakest[0]['label'].lower()}."
    return f"{band['label']} ({score})."


# ═══════════════════════ intelligence registry ═══════════════════════

INTELLIGENCE_MODELS = {
    "EFS": {
        "name": "Executive Focus Score",
        "question": "Where should executive time be invested today?",
        "module": "app.focus_score",
        "version": "1.0",
    },
    "RCI": {
        "name": "Relationship Coverage Index",
        "question": "Do we know the right people?",
        "module": "app.coverage_index",
        "version": CRI_MODEL_VERSION,
    },
    "CRI": {
        "name": "Commercial Readiness Index",
        "question": "Are we genuinely ready to pursue this?",
        "module": "app.readiness_index",
        "version": CRI_MODEL_VERSION,
    },
    "RMI": {
        "name": "Relationship Momentum Index",
        "question": "Are relationships improving or deteriorating?",
        "module": "app.relationship_health",
        "version": "1.0",
    },
    "DCS": {
        "name": "Decision Confidence Score",
        "question": "How confident should we be in this recommendation?",
        "module": "app.readiness_index",
        "version": DCS_MODEL_VERSION,
    },
}


def cite(*model_codes: str) -> list[dict]:
    """Model attribution for a recommendation.

    Every recommendation in ATLAS must reference the models behind it.
    Advice with no citation is opinion, and the platform's whole claim is
    that its advice is not opinion.
    """
    return [
        {
            "code": code,
            "name": INTELLIGENCE_MODELS[code]["name"],
            "question": INTELLIGENCE_MODELS[code]["question"],
            "version": INTELLIGENCE_MODELS[code]["version"],
        }
        for code in model_codes
        if code in INTELLIGENCE_MODELS
    ]
