"""Four-dimension scoring and Pursuit Priority (rebuild spec §1–§2).

Replaces the single VECTA Alignment Score. Four independent dimensions,
each 0–100, each with named factors that are stored and displayed — no
score is ever presented without its breakdown (§1, and the Phase 2
completion check "No AI score is displayed without an explanation").

Direction matters: Strategic, Commercial and Win Probability are all
"higher is better". **Risk is inverted — higher means MORE risk** — so it
is folded into Pursuit Priority as (100 - risk).
"""
from __future__ import annotations

from .taxonomy import ACTIVE_PIPELINE_STATES, QualificationState

SCORING_MODEL_VERSION = "2.0"


# ------------------------------------------------------------ factor definitions
#
# DIRECTION RULE (spec §1 correction): within Strategic, Commercial and Win
# Probability, EVERY factor is phrased so 100 is always the better outcome.
# Negatively-phrased factors were renamed to their positive form —
# "Mobilisation requirement" -> "Mobilisation efficiency", "Cost to pursue"
# -> "Pursuit-cost efficiency", "Partner revenue share" -> "Retained
# revenue potential", "Procurement complexity" -> "Procurement
# accessibility" — so a high score can never be misread as a bad thing.
#
# Risk is the deliberate exception and is inverted as a whole dimension:
# every risk factor is phrased so 100 = MOST risk. It enters Pursuit
# Priority as (100 - risk).
#
# Every factor carries anchors describing what 0, 50 and 100 mean. These
# are the single source of truth: they are rendered in the UI and injected
# into the AI prompt, so the scale cannot drift between them.

STRATEGIC_FACTORS: list[dict] = [
    {"key": "primary_vertical_fit", "label": "Primary VECTA vertical fit", "weight": 0.18,
     "anchors": {"0": "No fit with any VECTA vertical.",
                 "50": "Partial fit; adjacent to a vertical but not core.",
                 "100": "Squarely core to one VECTA vertical."}},
    {"key": "contributing_vertical_fit", "label": "Contributing vertical fit", "weight": 0.08,
     "anchors": {"0": "Single-vertical only, no secondary relevance.",
                 "50": "One credible contributing vertical.",
                 "100": "Multiple contributing verticals with real delivery roles."}},
    {"key": "geographic_priority", "label": "Geographic priority", "weight": 0.14,
     "anchors": {"0": "Outside all priority regions.",
                 "50": "Secondary region.",
                 "100": "Primary priority market (per Commercial Profile)."}},
    {"key": "government_federation_relevance", "label": "Government/federation relevance", "weight": 0.12,
     "anchors": {"0": "No public-sector or federation dimension.",
                 "50": "Indirect federation or public-body involvement.",
                 "100": "Direct government or federation counterparty."}},
    {"key": "long_term_ecosystem_value", "label": "Long-term ecosystem value", "weight": 0.12,
     "anchors": {"0": "One-off with no follow-on value.",
                 "50": "Some durable positioning.",
                 "100": "Builds lasting ecosystem position and future access."}},
    {"key": "cross_vertical_value", "label": "Cross-vertical value", "weight": 0.10,
     "anchors": {"0": "No pull-through to other verticals.",
                 "50": "Plausible pull-through to one other vertical.",
                 "100": "Strong pull-through across several verticals."}},
    {"key": "brand_positioning_value", "label": "Brand and positioning value", "weight": 0.10,
     "anchors": {"0": "No brand benefit, or brand-negative.",
                 "50": "Modest credibility benefit.",
                 "100": "Flagship reference that materially lifts positioning."}},
    {"key": "strategic_account_value", "label": "Strategic-account value", "weight": 0.10,
     "anchors": {"0": "Counterparty of no ongoing interest.",
                 "50": "Useful account, not strategic.",
                 "100": "Target strategic account with long-term potential."}},
    {"key": "current_priority_alignment", "label": "Alignment with current VECTA priorities", "weight": 0.06,
     "anchors": {"0": "Conflicts with stated current priorities.",
                 "50": "Neutral against current priorities.",
                 "100": "Directly serves a stated current priority."}},
]

COMMERCIAL_FACTORS: list[dict] = [
    {"key": "potential_revenue", "label": "Potential VECTA revenue", "weight": 0.20,
     "anchors": {"0": "Below the minimum contract value threshold.",
                 "50": "At around the target contract value.",
                 "100": "Materially above the target contract value."}},
    {"key": "expected_gross_margin", "label": "Expected gross margin", "weight": 0.15,
     "anchors": {"0": "Below the minimum acceptable margin.",
                 "50": "At the target margin.",
                 "100": "Well above the target margin."}},
    {"key": "contract_duration", "label": "Contract duration", "weight": 0.10,
     "anchors": {"0": "Single short engagement.",
                 "50": "Around one year.",
                 "100": "Multi-year committed term."}},
    {"key": "recurring_revenue_potential", "label": "Recurring-revenue potential", "weight": 0.12,
     "anchors": {"0": "Strictly one-off.",
                 "50": "Possible repeat, not contracted.",
                 "100": "Contracted or highly likely recurring revenue."}},
    {"key": "payment_profile", "label": "Payment profile", "weight": 0.08,
     "anchors": {"0": "Fully in arrears with long payment terms.",
                 "50": "Standard staged payments.",
                 "100": "Favourable — advance or milestone-front-loaded."}},
    # RENAMED (was "Mobilisation requirement" — negative phrasing in a
    # higher-is-better dimension). 100 now means LOW mobilisation burden.
    {"key": "mobilisation_efficiency", "label": "Mobilisation efficiency", "weight": 0.08,
     "anchors": {"0": "Very heavy mobilisation — major upfront cost or standing capability required.",
                 "50": "Moderate, manageable mobilisation.",
                 "100": "Minimal mobilisation — deliverable with existing capability."}},
    # RENAMED (was "Cost to pursue"). 100 now means CHEAP to pursue.
    {"key": "pursuit_cost_efficiency", "label": "Pursuit-cost efficiency", "weight": 0.09,
     "anchors": {"0": "Very expensive to pursue relative to the prize.",
                 "50": "Proportionate pursuit cost.",
                 "100": "Very low pursuit cost relative to the prize."}},
    {"key": "scalability", "label": "Scalability", "weight": 0.08,
     "anchors": {"0": "Cannot scale beyond this instance.",
                 "50": "Some scope to scale.",
                 "100": "Highly replicable across markets or clients."}},
    {"key": "upsell_expansion_potential", "label": "Upsell or expansion potential", "weight": 0.06,
     "anchors": {"0": "Closed scope, no expansion path.",
                 "50": "Plausible adjacent expansion.",
                 "100": "Clear, sizeable expansion path."}},
    # RENAMED (was "Potential partner revenue share" — a HIGH partner share
    # is bad for VECTA). 100 now means VECTA retains most of the revenue.
    {"key": "retained_revenue_potential", "label": "Retained revenue potential", "weight": 0.04,
     "anchors": {"0": "Most revenue passes to partners; VECTA retains little.",
                 "50": "Roughly balanced partner split.",
                 "100": "VECTA retains substantially all revenue."}},
]

WIN_PROBABILITY_FACTORS: list[dict] = [
    {"key": "eligibility", "label": "Eligibility", "weight": 0.16,
     "anchors": {"0": "Fails a mandatory eligibility requirement.",
                 "50": "Eligible with conditions or unconfirmed points.",
                 "100": "Fully and demonstrably eligible."}},
    {"key": "relevant_credentials", "label": "Relevant VECTA credentials", "weight": 0.13,
     "anchors": {"0": "No relevant track record.",
                 "50": "Adjacent credentials.",
                 "100": "Directly comparable, referenceable delivery."}},
    {"key": "relationship_strength", "label": "Existing relationship strength", "weight": 0.13,
     "anchors": {"0": "No relationship — entirely cold.",
                 "50": "Known but not close.",
                 "100": "Strong, trusted, active relationship."}},
    {"key": "decision_maker_access", "label": "Decision-maker access", "weight": 0.12,
     "anchors": {"0": "No identified route to the decision-maker.",
                 "50": "Indirect or introduced access.",
                 "100": "Direct access to the economic buyer."}},
    {"key": "competitive_position", "label": "Competitive position", "weight": 0.11,
     "anchors": {"0": "Crowded field, incumbent strongly favoured.",
                 "50": "Competitive but winnable.",
                 "100": "Few credible competitors or clear differentiation."}},
    {"key": "delivery_readiness", "label": "Delivery readiness", "weight": 0.10,
     "anchors": {"0": "Could not deliver without major new capability.",
                 "50": "Deliverable with some build-out.",
                 "100": "Ready to deliver today."}},
    {"key": "partner_availability", "label": "Availability of required partners", "weight": 0.07,
     "anchors": {"0": "Required partner needed and none identified.",
                 "50": "Candidate partners identified, not committed.",
                 "100": "No partner needed, or partner already secured."}},
    {"key": "time_remaining", "label": "Time remaining before deadline", "weight": 0.07,
     "anchors": {"0": "Insufficient time to prepare a credible response.",
                 "50": "Tight but workable.",
                 "100": "Ample time to prepare well."}},
    {"key": "local_market_capability", "label": "Local-market capability", "weight": 0.06,
     "anchors": {"0": "No presence or capability in the market.",
                 "50": "Some local capability or partner coverage.",
                 "100": "Established local presence and capability."}},
    # RENAMED (was "Procurement complexity"). 100 now means EASY to navigate.
    {"key": "procurement_accessibility", "label": "Procurement accessibility", "weight": 0.05,
     "anchors": {"0": "Highly complex or closed procurement process.",
                 "50": "Standard procurement complexity.",
                 "100": "Simple, open and accessible process."}},
]

# RISK — inverted dimension: 100 = MOST risk throughout.
RISK_FACTORS: list[dict] = [
    {"key": "financial_exposure", "label": "Financial exposure", "weight": 0.13,
     "anchors": {"0": "No capital or balance-sheet exposure.",
                 "50": "Moderate, bounded exposure.",
                 "100": "Severe exposure relative to VECTA's capacity."}},
    {"key": "delivery_complexity", "label": "Delivery complexity", "weight": 0.12,
     "anchors": {"0": "Simple, well-understood delivery.",
                 "50": "Moderately complex.",
                 "100": "Highly complex, multi-party, unproven delivery."}},
    {"key": "legal_risk", "label": "Legal risk", "weight": 0.11,
     "anchors": {"0": "Standard, low-risk contracting.",
                 "50": "Some unusual terms requiring review.",
                 "100": "Onerous liability, unresolved legal exposure."}},
    {"key": "regulatory_risk", "label": "Regulatory risk", "weight": 0.10,
     "anchors": {"0": "No material regulatory constraint.",
                 "50": "Manageable regulatory requirements.",
                 "100": "Severe or uncertain regulatory barriers."}},
    {"key": "reputational_risk", "label": "Reputational risk", "weight": 0.12,
     "anchors": {"0": "No reputational concern.",
                 "50": "Some sensitivity requiring care.",
                 "100": "Serious reputational hazard."}},
    {"key": "payment_risk", "label": "Payment risk", "weight": 0.10,
     "anchors": {"0": "Counterparty of unquestioned financial standing.",
                 "50": "Some payment uncertainty.",
                 "100": "Material doubt about being paid."}},
    {"key": "partner_dependency", "label": "Partner dependency", "weight": 0.09,
     "anchors": {"0": "No partner dependency.",
                 "50": "Partner needed but substitutable.",
                 "100": "Wholly dependent on a single unsecured partner."}},
    {"key": "political_sensitivity", "label": "Political or stakeholder sensitivity", "weight": 0.08,
     "anchors": {"0": "Politically neutral.",
                 "50": "Some stakeholder sensitivity.",
                 "100": "Highly politically exposed."}},
    {"key": "evidence_uncertainty", "label": "Evidence uncertainty", "weight": 0.09,
     "anchors": {"0": "Fully evidenced by Tier 1 sources.",
                 "50": "Partly evidenced; some claims unverified.",
                 "100": "Largely unverified — key facts unconfirmed."}},
    {"key": "deadline_mobilisation_risk", "label": "Deadline or mobilisation risk", "weight": 0.06,
     "anchors": {"0": "Comfortable timeline.",
                 "50": "Tight but achievable.",
                 "100": "Timeline not credibly achievable."}},
]

DIMENSIONS: dict[str, dict] = {
    "strategic_alignment": {
        "label": "Strategic Alignment",
        "factors": STRATEGIC_FACTORS,
        "higher_is_better": True,
    },
    "commercial_attractiveness": {
        "label": "Commercial Attractiveness",
        "factors": COMMERCIAL_FACTORS,
        "higher_is_better": True,
    },
    "win_probability": {
        "label": "Win Probability",
        "factors": WIN_PROBABILITY_FACTORS,
        "higher_is_better": True,
    },
    "risk": {
        "label": "Risk",
        "factors": RISK_FACTORS,
        "higher_is_better": False,  # higher score = higher risk
    },
}



# ------------------------------------------------------------ coverage (§2)

COVERAGE_ASSESSED_MIN = 0.80      # >= 80% -> "Assessed"
COVERAGE_PROVISIONAL_MIN = 0.50   # 50-79% -> "Provisional"

# Below this, a dimension cannot support an unrestricted high priority.
COVERAGE_REQUIRED_FOR_HIGH_PRIORITY = 0.80


def coverage_status(coverage: float) -> dict:
    """Coverage banding. An incomplete assessment must never be presented
    as equivalent to a complete one."""
    if coverage >= COVERAGE_ASSESSED_MIN:
        return {"key": "assessed", "label": "Assessed", "sufficient": True}
    if coverage >= COVERAGE_PROVISIONAL_MIN:
        return {"key": "provisional", "label": "Provisional", "sufficient": False}
    return {
        "key": "insufficient",
        "label": "Provisional — insufficient assessment",
        "sufficient": False,
    }


def risk_is_established(coverage: float, factor_breakdown: list[dict] | None = None) -> bool:
    """Risk needs its own rule: for the other three dimensions a missing
    factor merely widens uncertainty, but for Risk an unassessed factor
    could hide a serious hazard. A partially-assessed risk score would
    render as a reassuringly low number, which is worse than showing
    nothing — so below the threshold we refuse to state a risk figure at
    all and surface "Risk not established" instead."""
    if coverage < COVERAGE_ASSESSED_MIN:
        return False
    if factor_breakdown:
        # Any high-weight risk factor left unscored also blocks establishment.
        for f in factor_breakdown:
            if not f.get("scored") and f.get("weight", 0) >= 0.10:
                return False
    return True


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def compute_dimension(dimension: str, factor_scores: dict[str, float]) -> dict:
    """Weighted 0–100 headline score for one dimension, plus the full
    factor breakdown. Missing factors are treated as unscored and excluded
    from the weighting (rather than silently counted as zero, which would
    understate a partially-assessed opportunity); the coverage ratio is
    returned so the UI can show how complete the assessment is."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown scoring dimension: {dimension}")

    factors = DIMENSIONS[dimension]["factors"]
    breakdown: list[dict] = []
    weighted_total = 0.0
    weight_used = 0.0

    for f in factors:
        raw = factor_scores.get(f["key"])
        scored = raw is not None
        value = _clamp(float(raw)) if scored else None
        breakdown.append(
            {
                "key": f["key"],
                "label": f["label"],
                "weight": f["weight"],
                "score": value,
                "scored": scored,
            }
        )
        if scored:
            weighted_total += value * f["weight"]
            weight_used += f["weight"]

    headline = round(weighted_total / weight_used) if weight_used > 0 else 0
    coverage = round(weight_used, 4)
    status = coverage_status(coverage)
    is_risk = dimension == "risk"
    established = risk_is_established(coverage, breakdown) if is_risk else status["sufficient"]

    result = {
        "dimension": dimension,
        "label": DIMENSIONS[dimension]["label"],
        "score": int(headline),
        "higher_is_better": DIMENSIONS[dimension]["higher_is_better"],
        "factors": breakdown,
        "coverage": coverage,
        "coverage_percent": round(coverage * 100),
        "coverage_status": status["key"],
        "coverage_label": status["label"],
        "sufficient_for_high_priority": coverage >= COVERAGE_REQUIRED_FOR_HIGH_PRIORITY,
        "model_version": SCORING_MODEL_VERSION,
    }

    if is_risk:
        result["risk_established"] = established
        if not established:
            # Do NOT present a low-looking number built from partial data.
            result["display_score"] = None
            result["display_label"] = "Risk not established"
            result["uncertainty_note"] = (
                "Material risk factors are unassessed. The computed value is retained for "
                "audit but must not be read as a low risk score."
            )
        else:
            result["display_score"] = int(headline)
            result["display_label"] = str(int(headline))
    else:
        result["display_score"] = int(headline)
        result["display_label"] = str(int(headline))

    return result


# ------------------------------------------------------- pursuit priority (§2)

# Default weighting. Configurable via the Commercial Profile in Phase 3 —
# see docs/SCORING_MODEL.md.
DEFAULT_PRIORITY_WEIGHTS: dict[str, float] = {
    "strategic_alignment": 0.35,
    "commercial_attractiveness": 0.30,
    "win_probability": 0.25,
    "inverse_risk": 0.10,
}

PRIORITY_BANDS: list[dict] = [
    {"min": 85, "max": 100, "key": "immediate", "label": "Immediate Priority"},
    {"min": 70, "max": 84, "key": "high", "label": "High Priority"},
    {"min": 55, "max": 69, "key": "review", "label": "Review"},
    {"min": 40, "max": 54, "key": "monitor", "label": "Monitor"},
    {"min": 0, "max": 39, "key": "low", "label": "Low Priority"},
]

# An opportunity that has not cleared qualification can never present as a
# high-priority pursuit, however well it scores (§2, §10). Its computed
# score is preserved and shown; the BAND is capped and the restriction is
# stated explicitly so the cap is never silent.
UNQUALIFIED_BAND_CAP = 54  # cannot exceed "Monitor"

# An opportunity assessed on partial data cannot present as Immediate or
# High Priority either (§2). It is capped into "Review" — visible and
# actionable, but not presented as a confident top pursuit.
LOW_COVERAGE_BAND_CAP = 69  # cannot exceed "Review"
RISK_NOT_ESTABLISHED_BAND_CAP = 69


def band_for(score: float) -> dict:
    for band in PRIORITY_BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return PRIORITY_BANDS[-1]


def compute_pursuit_priority(
    strategic_alignment: float,
    commercial_attractiveness: float,
    win_probability: float,
    risk: float,
    qualification_state: str = QualificationState.NOT_ASSESSED.value,
    urgency_adjustment: float = 0.0,
    weights: dict[str, float] | None = None,
    coverage: dict[str, float] | None = None,
    risk_established: bool = True,
) -> dict:
    """Pursuit Priority with a fully transparent breakdown.

    Risk enters as (100 - risk) because higher risk must reduce priority.
    Urgency may modify the result but cannot lift an unqualified or
    disqualified opportunity into a pursuit band.
    """
    w = {**DEFAULT_PRIORITY_WEIGHTS, **(weights or {})}
    inverse_risk = _clamp(100 - _clamp(risk))

    contributions = [
        {
            "component": "strategic_alignment",
            "label": "Strategic Alignment",
            "value": round(_clamp(strategic_alignment), 2),
            "weight": w["strategic_alignment"],
            "contribution": round(_clamp(strategic_alignment) * w["strategic_alignment"], 2),
        },
        {
            "component": "commercial_attractiveness",
            "label": "Commercial Attractiveness",
            "value": round(_clamp(commercial_attractiveness), 2),
            "weight": w["commercial_attractiveness"],
            "contribution": round(_clamp(commercial_attractiveness) * w["commercial_attractiveness"], 2),
        },
        {
            "component": "win_probability",
            "label": "Win Probability",
            "value": round(_clamp(win_probability), 2),
            "weight": w["win_probability"],
            "contribution": round(_clamp(win_probability) * w["win_probability"], 2),
        },
        {
            "component": "inverse_risk",
            "label": "Inverse Risk (100 − Risk)",
            "value": round(inverse_risk, 2),
            "weight": w["inverse_risk"],
            "contribution": round(inverse_risk * w["inverse_risk"], 2),
        },
    ]

    base = sum(c["contribution"] for c in contributions)
    adjusted = _clamp(base + urgency_adjustment)

    restrictions: list[str] = []
    final = adjusted

    # --- coverage restriction (§2) ---
    low_coverage = [
        f"{DIMENSIONS[d]['label']} {round(v * 100)}%"
        for d, v in (coverage or {}).items()
        if d in DIMENSIONS and v < COVERAGE_REQUIRED_FOR_HIGH_PRIORITY
    ]
    if low_coverage:
        final = min(final, LOW_COVERAGE_BAND_CAP)
        restrictions.append(
            "Assessment incomplete (" + ", ".join(low_coverage) +
            f") — capped at 'Review'. Uncapped score: {round(adjusted)}."
        )
    if not risk_established:
        final = min(final, RISK_NOT_ESTABLISHED_BAND_CAP)
        restrictions.append(
            "Risk not established — material risk factors unassessed, so this cannot be "
            "presented as a high-confidence pursuit."
        )

    restricted = qualification_state not in ACTIVE_PIPELINE_STATES
    restriction_note = None
    if restricted:
        if qualification_state == QualificationState.DISQUALIFIED.value:
            restriction_note = (
                "Disqualified — excluded from active pursuits regardless of score."
            )
        else:
            restriction_note = (
                f"Qualification state is '{qualification_state}' — priority band capped at "
                f"'Monitor' until the opportunity is qualified. Uncapped score: {round(adjusted)}."
            )
        final = min(final, UNQUALIFIED_BAND_CAP)
        restrictions.append(restriction_note)

    band = band_for(final)
    return {
        "score": round(final),
        "uncapped_score": round(adjusted),
        "band": band["key"],
        "band_label": band["label"],
        "base_score": round(base, 2),
        "urgency_adjustment": round(urgency_adjustment, 2),
        "qualification_state": qualification_state,
        "qualification_restricted": restricted,
        "restriction_note": restriction_note,
        "restrictions": restrictions,
        "coverage_restricted": bool(low_coverage) or not risk_established,
        "risk_established": risk_established,
        "weights": w,
        "contributions": contributions,
        "model_version": SCORING_MODEL_VERSION,
    }


# --------------------------------------------------------- manual override (§16)

def build_score_override(
    dimension: str, ai_score: float, manual_score: float, reason: str, timestamp: str
) -> dict:
    """Records a manual score override without destroying the AI score
    (§16: "Do not delete the original AI score")."""
    if not reason or not reason.strip():
        raise ValueError("A manual score override requires a reason.")
    return {
        "dimension": dimension,
        "ai_score": round(_clamp(ai_score)),
        "manual_score": round(_clamp(manual_score)),
        "reason": reason.strip(),
        "overridden_at": timestamp,
        "model_version": SCORING_MODEL_VERSION,
    }
