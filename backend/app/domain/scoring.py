"""Versioned, deterministic scoring (build spec §7).

Four separate assessments: attractiveness, evidence_confidence, readiness
and risk. They are never combined into one number and never presented as
a probability of winning.

Factor values are anchors 0..4 or None (unknown). Unknown is NOT zero: it
reduces coverage. Below `min_coverage`, the assessment is
`insufficient_evidence` and carries no score. Gate factors block the
dimension when they fail.

Weights are PROVISIONAL until evaluated against recorded outcomes. Changing
any weight or anchor requires a new version string; the definition's hash
is stored so an edited-in-place model is detectable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Mapping

Dimension = Literal["attractiveness", "evidence_confidence", "readiness", "risk"]
DIMENSIONS: tuple[Dimension, ...] = ("attractiveness", "evidence_confidence", "readiness", "risk")


@dataclass(frozen=True)
class Factor:
    code: str
    dimension: Dimension
    weight: Decimal
    anchors: tuple[str, str, str, str, str]
    gate: bool = False  # anchor 0 on a gate factor => dimension blocked


@dataclass(frozen=True)
class ModelVersion:
    module: str
    version: str
    factors: tuple[Factor, ...]
    min_coverage: Decimal = Decimal("0.60")
    provisional: bool = True

    def definition(self) -> dict:
        return {
            "module": self.module, "version": self.version, "min_coverage": str(self.min_coverage),
            "provisional": self.provisional,
            "factors": [{"code": f.code, "dimension": f.dimension, "weight": str(f.weight), "anchors": list(f.anchors), "gate": f.gate}
                        for f in self.factors],
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.definition(), sort_keys=True).encode()).hexdigest()


@dataclass
class Assessment:
    dimension: Dimension
    status: Literal["scored", "insufficient_evidence", "blocked"]
    score: Decimal | None  # 0..100, None unless scored
    coverage: Decimal
    factors: list[dict] = field(default_factory=list)
    model_version: str = ""


def assess(model: ModelVersion, values: Mapping[str, int | None], rationales: Mapping[str, str] | None = None,
           evidence: Mapping[str, list[str]] | None = None) -> dict[Dimension, Assessment]:
    rationales = rationales or {}
    evidence = evidence or {}
    unknown_codes = set(values) - {f.code for f in model.factors}
    if unknown_codes:
        raise ValueError(f"values for factors not in model {model.version}: {sorted(unknown_codes)}")
    out: dict[Dimension, Assessment] = {}
    for dim in DIMENSIONS:
        factors = [f for f in model.factors if f.dimension == dim]
        if not factors:
            continue
        total_w = sum((f.weight for f in factors), Decimal("0"))
        known_w = Decimal("0")
        weighted = Decimal("0")
        blocked = False
        detail = []
        for f in factors:
            v = values.get(f.code)
            if v is not None and not (0 <= v <= 4):
                raise ValueError(f"factor {f.code} anchor {v} outside 0..4")
            detail.append({"code": f.code, "value": v, "anchor": None if v is None else f.anchors[v],
                           "weight": str(f.weight), "gate": f.gate, "rationale": rationales.get(f.code),
                           "evidence": evidence.get(f.code, [])})
            if v is None:
                continue
            known_w += f.weight
            weighted += f.weight * Decimal(v) / Decimal(4)
            if f.gate and v == 0:
                blocked = True
        coverage = (known_w / total_w).quantize(Decimal("0.0001"), ROUND_HALF_UP) if total_w else Decimal("0")
        if blocked:
            out[dim] = Assessment(dim, "blocked", None, coverage, detail, model.version)
        elif coverage < model.min_coverage or known_w == 0:
            out[dim] = Assessment(dim, "insufficient_evidence", None, coverage, detail, model.version)
        else:
            score = (weighted / known_w * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
            out[dim] = Assessment(dim, "scored", score, coverage, detail, model.version)
    return out


def family_count_anchor(independent_families: int, has_authoritative: bool) -> int:
    """Evidence-confidence anchor from INDEPENDENT announcement families.
    Assumptions never feed this value."""
    if independent_families <= 0:
        return 0
    anchor = min(independent_families, 4)
    if not has_authoritative:
        anchor = min(anchor, 2)
    return anchor


def _f(code, dim, w, anchors, gate=False) -> Factor:
    return Factor(code, dim, Decimal(w), tuple(anchors), gate)  # type: ignore[arg-type]


AIRLINE_REPRESENTATION_V0_1 = ModelVersion(
    module="airline_representation",
    version="wfc-score-0.1",
    factors=(
        _f("territory_fit", "attractiveness", "0.30",
           ["no WFC presence nearby", "contiguous to WFC territory", "same region as WFC territory", "WFC station in territory", "WFC station + same airline elsewhere"]),
        _f("contribution_band", "attractiveness", "0.30",
           ["below WFC floor", "low band", "mid band", "high band", "strategic band"]),
        _f("airline_relationship", "attractiveness", "0.20",
           ["none", "contact known", "active engagement", "agreement elsewhere", "multi-territory agreement"]),
        _f("duration", "attractiveness", "0.20",
           ["< 6 months", "6-12 months", "1-2 years", "2-3 years", "> 3 years / renewable"]),
        _f("independent_families", "evidence_confidence", "0.50",
           ["none", "1 family", "2 families", "3 families", "4+ families incl. official"]),
        _f("best_authority", "evidence_confidence", "0.30",
           ["unverified", "trade press", "trade press (corroborated)", "company release", "official tender portal"]),
        _f("recency", "evidence_confidence", "0.20",
           ["> 180 days", "90-180 days", "30-90 days", "7-30 days", "< 7 days"]),
        _f("capability_verified", "readiness", "0.50",
           ["expired / unverified", "partial", "verified, validity unknown", "verified", "verified + credentials current"], gate=True),
        _f("eligibility", "readiness", "0.30",
           ["fails", "mostly fails", "partial", "mostly meets", "meets all stated criteria"]),
        _f("owner_and_time", "readiness", "0.20",
           ["no owner, deadline too close", "no owner", "owner, tight deadline", "owner, workable deadline", "owner, ample time"]),
        _f("territory_conflict", "risk", "0.40",
           ["exclusive appointment held elsewhere", "conflict likely", "unclear", "minor", "no conflict"], gate=True),
        _f("contradicting_evidence", "risk", "0.35",
           ["material contradiction", "several", "one minor", "stale only", "none"]),
        _f("exposure", "risk", "0.25",
           ["uncapped guarantee", "large guarantee", "moderate", "small", "none"]),
    ),
)
# NB: on the risk dimension a HIGHER score means LOWER risk (anchor 4 = no risk found).

MODELS: dict[str, ModelVersion] = {AIRLINE_REPRESENTATION_V0_1.module: AIRLINE_REPRESENTATION_V0_1}
