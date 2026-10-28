"""Prioritisation for all nine capability areas (directive §11).

Two methods, chosen per module and documented in each definition:
- SCORED (versioned weighted factors, `domain.scoring`): used where several
  independent, comparable facts bear on priority. Four SEPARATE dimensions:
  commercial attractiveness, evidence confidence, pursuit readiness and risk.
  They are never combined into one number and never presented as a
  probability of winning. Unknown factors reduce coverage; below the
  model's minimum coverage the dimension is `insufficient_evidence`.
- RULES (transparent ordering): used where a numerical score adds nothing,
  e.g. operational exceptions (severity, then deadline) or network fit
  (assessed fit, then evidence).

All weights are PROVISIONAL until evaluated against recorded outcomes;
every definition says so. Rankings are only meaningful within a module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .scoring import AIRLINE_REPRESENTATION_V0_1, ModelVersion, _f

ACCOUNT_GROWTH_V0_1 = ModelVersion(
    module="account_growth", version="wfc-ag-0.1",
    factors=(
        _f("airline_volume", "attractiveness", "0.40", ["no bookings", "low", "medium", "high", "top decile"]),
        _f("service_breadth", "attractiveness", "0.30", ["new service, no adjacency", "adjacent service", "same service, new territory",
                                                          "same service, neighbouring territory", "extension of an existing mandate"]),
        _f("contribution_band", "attractiveness", "0.30", ["below WFC floor", "low band", "mid band", "high band", "strategic band"]),
        _f("record_basis", "evidence_confidence", "1.00", ["none", "partial records", "agreement only", "agreement + capability",
                                                          "agreement + capability + bookings"]),
        _f("appointment_rights", "readiness", "0.50", ["prohibited", "consent refused", "consent required", "unknown→consent likely",
                                                       "may extend"], gate=True),
        _f("capability_verified", "readiness", "0.50", ["expired / unverified", "partial", "verified, validity unknown", "verified",
                                                        "verified + credentials current"], gate=True),
        _f("territory_conflict", "risk", "1.00", ["exclusive appointment held elsewhere", "conflict likely", "unclear", "minor",
                                                  "no conflict"], gate=True),
    ),
)

FORWARDER_SALES_V0_1 = ModelVersion(
    module="forwarder_sales", version="wfc-fs-0.1",
    factors=(
        _f("historical_volume", "attractiveness", "0.60", ["none", "low", "medium", "high", "top decile"]),
        _f("volume_change", "attractiveness", "0.40", ["growing > 15%", "stable", "down 15-30%", "down 30-60%", "down > 60% / dormant"]),
        _f("data_currency", "evidence_confidence", "1.00", ["no data", "stale > 3 SLA", "stale", "within SLA, gaps", "within SLA"]),
        _f("quote_conversion", "readiness", "0.50", ["no quotes", "< 10%", "10-25%", "25-50%", "> 50%"]),
        _f("owner_assigned", "readiness", "0.50", ["no owner", "owner, no contact", "owner + contact", "owner, recent engagement",
                                                   "owner, engagement this month"]),
        _f("lost_to_price", "risk", "1.00", ["> 75% lost on price", "50-75%", "25-50%", "< 25%", "no losses"]),
    ),
)

OUTSOURCING_TRAINING_V0_1 = ModelVersion(
    module="outsourcing_training", version="wfc-ot-0.1",
    factors=(
        _f("contribution_band", "attractiveness", "1.00", ["below WFC floor", "low band", "mid band", "high band", "strategic band"]),
        _f("independent_families", "evidence_confidence", "0.60", ["none", "1 family", "2 families", "3 families", "4+ families incl. official"]),
        _f("best_authority", "evidence_confidence", "0.40", ["unverified", "trade press", "trade press (corroborated)", "company release",
                                                             "official tender portal"]),
        _f("capability_verified", "readiness", "0.60", ["expired / unverified", "partial", "verified, validity unknown", "verified",
                                                        "verified + credentials current"], gate=True),
        _f("owner_and_time", "readiness", "0.40", ["no owner, deadline too close", "no owner", "owner, tight deadline",
                                                   "owner, workable deadline", "owner, ample time"]),
        _f("contradicting_evidence", "risk", "1.00", ["material contradiction", "several", "one minor", "stale only", "none"]),
    ),
)

# Trucking, technology and capacity tenders discovered from public sources use
# the same evidence-and-readiness factors as outsourcing tenders.
TRUCKING_GATEWAYS_V0_1 = ModelVersion(module="trucking_gateways", version="wfc-tg-0.1", factors=OUTSOURCING_TRAINING_V0_1.factors)
TECHNOLOGY_SOLUTIONS_V0_1 = ModelVersion(module="technology_solutions", version="wfc-ts-0.1", factors=OUTSOURCING_TRAINING_V0_1.factors)
CAPACITY_LANES_V0_1 = ModelVersion(
    module="capacity_lanes", version="wfc-cl-0.1",
    factors=(
        _f("spare_capacity", "attractiveness", "0.60", ["none / overbooked", "< 5%", "5-15%", "15-30%", "> 30% unsold"]),
        _f("booking_trend", "attractiveness", "0.40", ["down > 30%", "down 10-30%", "stable", "up 10-30%", "up > 30%"]),
        _f("capacity_data", "evidence_confidence", "1.00", ["none", "one snapshot", "two snapshots", "monthly series", "weekly series"]),
        _f("owner_and_time", "readiness", "1.00", ["no owner, deadline too close", "no owner", "owner, tight deadline",
                                                   "owner, workable deadline", "owner, ample time"]),
        _f("yield_comparability", "risk", "1.00", ["mixed currencies, no FX", "partial revenue", "revenue on some bookings",
                                                   "revenue on most bookings", "full revenue, one currency"]),
    ),
)

SCORED: dict[str, ModelVersion] = {m.module: m for m in (
    AIRLINE_REPRESENTATION_V0_1, ACCOUNT_GROWTH_V0_1, FORWARDER_SALES_V0_1, OUTSOURCING_TRAINING_V0_1, TRUCKING_GATEWAYS_V0_1,
    TECHNOLOGY_SOLUTIONS_V0_1, CAPACITY_LANES_V0_1)}

RULES: dict[str, dict[str, Any]] = {
    "service_operations": {
        "version": "wfc-so-rules-0.1", "provisional": True,
        "order": ["severity: critical, high, medium, low", "deadline: earliest first; unknown deadline after known",
                  "age: oldest open first"],
        "why_no_score": "Operational exceptions are handled in severity and deadline order; a weighted score would hide that order.",
        "missing_data": "Unknown deadline sorts after known deadlines; unknown severity is not accepted on import.",
    },
    "network_development": {
        "version": "wfc-nd-rules-0.1", "provisional": True,
        "order": ["fit: strong, partial, weak, insufficient evidence, not assessed",
                  "evidence: number of supported partner claims", "status: open, assessing, parked, closed"],
        "why_no_score": "Network fit is assessed against stated coverage gaps from supported claims; acquisition research is never "
                        "scored, valued or counted in pipeline totals.",
        "missing_data": "No supported claims means 'insufficient evidence', never a weak fit.",
    },
}


def definitions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in SCORED.values():
        d = m.definition()
        d["method"] = "scored"
        d["dimensions_kept_separate"] = ["attractiveness", "evidence_confidence", "readiness", "risk"]
        d["note"] = ("Provisional weights. Not a probability of winning. Unknown factors reduce coverage; below "
                     f"{m.min_coverage} coverage a dimension shows 'insufficient evidence'. Risk: a higher score means LOWER risk. "
                     f"Money bands are defined in {BAND_CURRENCY}; amounts in other currencies are treated as unknown.")
        out.append(d)
    for module, r in RULES.items():
        out.append({"module": module, "method": "rules", **r})
    return out


# --------------------------------------------------------------------- factor anchors from facts


def authority_anchor(best: str | None, families: int) -> int | None:
    if best is None:
        return None
    return {"unverified": 0, "trade_press": 2 if families > 1 else 1, "company_release": 3, "official_portal": 4,
            "internal_record": 4}.get(best, 0)


def recency_anchor(days: int | None) -> int | None:
    if days is None:
        return None
    return 4 if days < 7 else 3 if days < 30 else 2 if days < 90 else 1 if days < 180 else 0


def owner_time_anchor(has_owner: bool, days_to_deadline: int | None) -> int | None:
    if days_to_deadline is None:
        return 1 if not has_owner else None
    if not has_owner:
        return 0 if days_to_deadline < 7 else 1
    return 2 if days_to_deadline < 7 else 3 if days_to_deadline < 30 else 4


def check_anchor(result: str | None, *, pass_value: int = 4) -> int | None:
    return {"pass": pass_value, "fail": 0}.get(result or "", None)


def capability_anchor(result: str | None, credentials_required: bool) -> int | None:
    if result == "pass":
        return 4 if credentials_required else 3
    if result == "fail":
        return 0
    return None


# Money bands are defined in this currency. An amount in any other currency gets NO band (unknown),
# because no conversion basis is applied inside scoring (directive §11: no currency mixing).
BAND_CURRENCY = "USD"


def contribution_anchor(value: Decimal | None) -> int | None:
    """Band of a retained contribution in BAND_CURRENCY (callers pass None for
    any other currency). Only set when a contract or scenario value exists.
    Thresholds are provisional."""
    return None if value is None else (0 if value <= 0 else 1 if value < 50_000 else 2 if value < 250_000 else 3 if value < 1_000_000 else 4)


@dataclass
class Facts:
    module: str
    checks: dict[str, str]
    families: int
    best_authority: str | None
    recency_days: int | None
    has_owner: bool
    days_to_deadline: int | None
    contradicted: int
    credentials_required: bool
    contribution: Decimal | None
    exposure: Decimal | None
    agreements_elsewhere: int
    has_contact: bool
    has_engagement: bool
    duration_months: int | None
    value_currency: str | None = None


def factor_values(f: Facts) -> tuple[dict[str, int | None], dict[str, str]]:
    """Anchor values (0..4 or None = unknown) and a one-line rationale each."""
    v: dict[str, int | None] = {}
    why: dict[str, str] = {}

    def put(code: str, value: int | None, reason: str) -> None:
        v[code] = value
        why[code] = reason if value is not None else f"unknown: {reason}"

    put("independent_families", min(f.families, 4) if f.families else (0 if f.best_authority is None else None),
        f"{f.families} independent announcement family(ies)")
    put("best_authority", authority_anchor(f.best_authority, f.families), f"best supporting source: {f.best_authority or 'none'}")
    put("recency", recency_anchor(f.recency_days), f"first published {f.recency_days} day(s) ago" if f.recency_days is not None else "publication date unknown")
    put("capability_verified", capability_anchor(f.checks.get("capability"), f.credentials_required),
        f"capability check: {f.checks.get('capability', 'not evaluated')}")
    put("eligibility", check_anchor(f.checks.get("eligibility")), f"eligibility check: {f.checks.get('eligibility', 'not evaluated')}")
    put("owner_and_time", owner_time_anchor(f.has_owner, f.days_to_deadline),
        ("owner assigned" if f.has_owner else "no owner") + (f", {f.days_to_deadline} day(s) to deadline" if f.days_to_deadline is not None else ", deadline unknown"))
    tc = f.checks.get("territory_conflict")
    put("territory_conflict", {"pass": 4, "fail": 0, "unknown": 2}.get(tc or "", None), f"territory check: {tc or 'not applicable'}")
    put("contradicting_evidence", 0 if f.contradicted > 1 else 2 if f.contradicted == 1 else 4, f"{f.contradicted} contradicted claim(s)")
    other_ccy = f.value_currency is not None and f.value_currency != BAND_CURRENCY
    ccy_note = f"amounts are in {f.value_currency}; bands are defined in {BAND_CURRENCY} and no conversion basis is applied"
    put("exposure", None if f.exposure is None or other_ccy else (4 if f.exposure == 0 else 3 if f.exposure < 50_000 else 2 if f.exposure < 250_000 else 1),
        ccy_note if other_ccy and f.exposure is not None else
        "guarantee exposure from commercial terms" if f.exposure is not None else "no commercial terms recorded")
    put("contribution_band", None if other_ccy else contribution_anchor(f.contribution),
        ccy_note if other_ccy and f.contribution is not None else
        "retained contribution (contract or labelled scenario)" if f.contribution is not None else "remuneration or costs unknown: unqualified")
    rel = 3 if f.agreements_elsewhere else 2 if f.has_engagement else 1 if f.has_contact else None
    put("airline_relationship", rel, f"{f.agreements_elsewhere} agreement(s) elsewhere" if f.agreements_elsewhere else
        ("engagement recorded" if f.has_engagement else "contact recorded" if f.has_contact else "no recorded relationship"))
    put("duration", None if f.duration_months is None else (0 if f.duration_months < 6 else 1 if f.duration_months < 12 else
                                                            2 if f.duration_months < 24 else 3 if f.duration_months <= 36 else 4),
        f"{f.duration_months} month(s)" if f.duration_months is not None else "duration not recorded")
    put("territory_fit", None, "WFC footprint distance is not computed from records yet")
    put("appointment_rights", {"pass": 4, "fail": 0, "unknown": None}.get(f.checks.get("appointment_rights", ""), None),
        f"appointment rights check: {f.checks.get('appointment_rights', 'not evaluated')}")
    return v, why
