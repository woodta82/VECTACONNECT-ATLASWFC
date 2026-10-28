"""The VECTA Alignment Score (spec Section 02): a weighted combination of
five sub-scores across vertical fit, commercial value, regional relevance,
deliverability and loop value. The AI provides each sub-score (0-100) as
part of scanning (see opportunity_scan.py); this module only does the fixed,
auditable weighting — kept deterministic and separate from the AI call so
the weights can be tuned without re-prompting the model, and so every score
is reproducible from its breakdown.
"""

WEIGHTS = {
    "vertical_fit": 0.30,
    "commercial_value": 0.25,
    "regional_relevance": 0.20,
    "deliverability": 0.15,
    "loop_value": 0.10,
}

PRIORITY_THRESHOLD = 70
STANDARD_THRESHOLD = 40  # below this, archived but searchable


def _clamp(value: object, default: int = 50) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, n))


def compute_alignment_score(raw_item: dict) -> tuple[int, dict]:
    """Returns (final 0-100 score, breakdown dict of the five clamped sub-scores)."""
    breakdown = {key: _clamp(raw_item.get(key)) for key in WEIGHTS}
    weighted = sum(breakdown[key] * weight for key, weight in WEIGHTS.items())
    final_score = round(weighted)
    return final_score, breakdown


def pipeline_bucket(score: int) -> str:
    if score >= PRIORITY_THRESHOLD:
        return "priority"
    if score >= STANDARD_THRESHOLD:
        return "standard"
    return "archived"
