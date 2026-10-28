"""Canonical executive vocabulary — Phase 3.1.

One place defines every executive-facing term. The design review found the
same concept named three ways across code, API and documentation
(`focus_band` / `priority_band`, "Focus Score" / "Executive Focus",
"relationship status" / "readiness" / "position"). That is cheap to fix
now and expensive once components render it.

**Rule:** no user-facing string is written inline. Anything an executive
reads comes from here, so a rename happens once.

The distinction that matters most is between the two scores. They answer
different questions and both are needed, but presented without a clear
vocabulary they invite the reasonable question "which number is right?".
"""
from __future__ import annotations

# ---------------------------------------------------------- the two scores

SCORE_TERMS = {
    "executive_focus": {
        "canonical": "Executive Focus",
        "question": "Where should I spend my time today?",
        "short": "Focus",
        "never": ["Focus Score", "focus rating", "attention score"],
        "primary_use": "Sorts every list an executive sees daily",
    },
    "pursuit_priority": {
        "canonical": "Pursuit Priority",
        "question": "How good is this opportunity?",
        "short": "Priority",
        "never": ["Priority Score", "opportunity score", "pursuit score"],
        "primary_use": "Opportunity detail only — never the default sort",
    },
}

# Executive Focus bands — the only bands shown on daily surfaces.
FOCUS_BAND_LABELS = {
    "act_now": "Act now",
    "this_week": "This week",
    "this_month": "This month",
    "monitor": "Monitor",
    "no_action": "No action needed",
}

# Pursuit Priority bands — opportunity detail only.
PRIORITY_BAND_LABELS = {
    "immediate": "Immediate Priority",
    "high": "High Priority",
    "review": "Review",
    "monitor": "Monitor",
    "low": "Low Priority",
}


# ------------------------------------------------------------ field terms

FIELD_LABELS = {
    # decision
    "recommended_decision": "Recommended decision",
    "why_this_matters": "Why",
    "confidence": "Confidence",
    # scores
    "focus_score": "Executive Focus",
    "pursuit_priority": "Pursuit Priority",
    "strategic_alignment": "Strategic Alignment",
    "commercial_attractiveness": "Commercial Attractiveness",
    "commercial_value": "Commercial Value",
    "win_probability": "Win Probability",
    "risk": "Risk",
    # position
    "relationship_position": "Relationship Position",
    "qualification_state": "Qualification",
    "evidence_status": "Evidence Status",
    "coverage": "Assessment Coverage",
    # action
    "opportunity_cost_of_waiting": "Cost of Waiting",
    "recommended_next_action": "Next Action",
    "target_date": "Target Date",
    "required_relationships": "Required Relationships",
    "supporting_evidence": "Supporting Evidence",
    "owner": "Owner",
}


# --------------------------------------------------------- state labels

RELATIONSHIP_POSITION_LABELS = {
    "strong": "Strong",
    "moderate": "Moderate",
    "weak": "Weak",
    "unknown": "Unknown",
}

CONFIDENCE_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}

SEVERITY_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}

# Claim classification — the vocabulary that keeps AI output distinguishable
# from verified fact. Used identically in cards, the advisor and reports.
CLAIM_KIND_LABELS = {
    "verified_fact": "Verified",
    "ai_interpretation": "AI interpretation",
    "assumption": "Assumption",
    "prediction": "Prediction",
    "recommendation": "Recommendation",
}

CLAIM_KIND_ORDER = [
    "verified_fact",
    "ai_interpretation",
    "assumption",
    "prediction",
    "recommendation",
]


# ------------------------------------------------- advisor response shape

ADVISOR_SECTIONS = [
    ("recommendation", "Recommendation"),
    ("key_reasons", "Key reasons"),
    ("supporting_evidence", "Supporting evidence"),
    ("risks", "Risks"),
    ("assumptions", "Assumptions"),
    ("suggested_actions", "Suggested actions"),
]

# Word budget per advisor section. Enforced structurally rather than by
# prompt instruction, because a prompt asking for brevity is a request and
# a truncation is a guarantee.
ADVISOR_SECTION_WORD_LIMIT = 40


def label(key: str, fallback: str | None = None) -> str:
    """Executive-facing label for a field key."""
    return FIELD_LABELS.get(key, fallback or key.replace("_", " ").title())


def focus_band_label(band: str) -> str:
    return FOCUS_BAND_LABELS.get(band, band.replace("_", " ").title())


def priority_band_label(band: str) -> str:
    return PRIORITY_BAND_LABELS.get(band, band.replace("_", " ").title())


def claim_label(kind: str) -> str:
    return CLAIM_KIND_LABELS.get(kind, kind.replace("_", " ").title())
