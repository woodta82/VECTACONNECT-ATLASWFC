"""Classification and qualification (build spec §6).

Classification, commercial stage and qualification are SEPARATE fields.
This module computes classification and qualification; commercial stage
moves only by authenticated human action (see `allowed_stage_transition`).

- Missing evidence gives `unknown` / `review_required`, never an automatic
  fail and never an automatic approval.
- Expired opportunities, known territory conflicts and verified capability
  failures BLOCK.
- `approved_for_pursuit` is never computed: it is recorded only by a human
  approval when status is `ready_for_review`.
- Overrides need a reason and may expire. They cannot override FACTUAL
  checks (existence, deadline, live status, territory conflict, capability)
  into a pass, because an override cannot fabricate evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from .evidence import AUTHORITY_RANK, AUTHORITATIVE_MIN, ClaimAssessment, TenderState

CheckValue = Literal["pass", "fail", "unknown", "review_required"]
Classification = Literal["market_signal", "unverified_lead", "qualified_opportunity", "risk_alert", "research_item", "excluded", "freight_candidate"]
QualStatus = Literal["incomplete", "blocked", "ready_for_review", "approved_for_pursuit"]

FACTUAL_CHECKS = {"existence", "not_expired", "live_status", "territory_conflict", "deadline_consistent", "capability",
                  "evidence_reviewed", "appointment_rights", "data_current", "freight_relevance", "geography_consistent",
                  "feasibility", "evidence_measured"}
# Checks a reviewer may settle by a recorded commercial judgement (with a reason, optionally expiring):
COMMERCIAL_CHECKS = {"eligibility", "scope", "owner_assigned", "commercial_terms"}


@dataclass
class Check:
    code: str
    result: CheckValue
    blocking: bool
    rationale: str
    overridden: bool = False


@dataclass(frozen=True)
class Override:
    check_code: str
    result: Literal["pass", "fail", "review_required"]
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    revoked: bool = False

    def active(self, now: datetime) -> bool:
        return not self.revoked and (self.expires_at is None or self.expires_at > now)


class OverrideRejected(ValueError):
    pass


def validate_override(o: Override) -> None:
    if len(o.reason.strip()) < 10:
        raise OverrideRejected("override reason must be at least 10 characters")
    if o.check_code in FACTUAL_CHECKS and o.result == "pass":
        raise OverrideRejected(f"{o.check_code} is a factual check; an override cannot create evidence")


def apply_overrides(checks: Sequence[Check], overrides: Sequence[Override], now: datetime) -> list[Check]:
    out = []
    for c in checks:
        o = next((o for o in reversed(overrides) if o.check_code == c.code and o.active(now)), None)
        if o is not None:
            validate_override(o)
            out.append(Check(c.code, o.result, c.blocking and o.result == "fail", f"OVERRIDE: {o.reason} (was {c.result}: {c.rationale})", True))
        else:
            out.append(c)
    return out


def qualification_status(checks: Sequence[Check]) -> QualStatus:
    if any(c.result == "fail" and c.blocking for c in checks):
        return "blocked"
    if any(c.result in ("unknown", "fail", "review_required") for c in checks):
        return "incomplete"
    return "ready_for_review"


# --------------------------------------------------------------------- airline representation


def classify_airline_signal(*, claim_types: set[str], tender_existence: ClaimAssessment | None) -> Classification:
    """A route launch is a market signal. Only a supported tender
    (authoritative family) is a qualified opportunity candidate; an
    unverified tender mention is an unverified lead."""
    if "gssa_tender" in claim_types and tender_existence is not None:
        if tender_existence.status == "supported" and AUTHORITY_RANK.get(tender_existence.best_supporting_authority or "", 0) >= AUTHORITATIVE_MIN:
            return "qualified_opportunity"
        if tender_existence.status == "contradicted":
            return "risk_alert"
        return "unverified_lead"
    if claim_types & {"route_launch", "route_suspension", "representation_change", "tcm_signal", "capacity_statement"}:
        return "market_signal"
    return "research_item"


def airline_representation_checks(
    *,
    existence: ClaimAssessment,
    tender: TenderState,
    territory_cell_state: Literal["covered", "gap", "blocked", "unknown"] | None,
    capability_readiness: Literal["ready", "blocked", "review_required"],
    eligibility_known: bool | None,
    eligibility_met: bool | None,
    eligibility_pending: int = 0,
    scope_known: bool,
    freight_scope: str | None = None,
    freight_reason: str | None = None,
    geography_conflict: str | None = None,
) -> list[Check]:
    checks: list[Check] = []
    # Freight relevance (item 1): passenger-only mandates never qualify; mixed or unclear ones wait for a person.
    if freight_scope == "cargo":
        checks.append(Check("freight_relevance", "pass", True, freight_reason or "cargo relevance stated by the notice"))
    elif freight_scope in ("passenger", "not_freight"):
        checks.append(Check("freight_relevance", "fail", True, "excluded from the freight pipeline: " + (freight_reason or "not a freight mandate")))
    else:
        checks.append(Check("freight_relevance", "review_required", True,
                            freight_reason or "freight relevance not established by the notice (generic representation wording); a reviewer must confirm"))
    if geography_conflict:
        checks.append(Check("geography_consistent", "review_required", True, geography_conflict))
    if existence.status == "supported" and AUTHORITY_RANK.get(existence.best_supporting_authority or "", 0) >= AUTHORITATIVE_MIN:
        checks.append(Check("existence", "pass", True, f"supported by {existence.supporting_families} independent family(ies)"))
    elif existence.status == "contradicted":
        checks.append(Check("existence", "review_required", True, "existence is contradicted; review the evidence"))
    else:
        checks.append(Check("existence", "unknown", True, "no authoritative supporting evidence yet"))

    # Live status and deadline are separate checks (directive §7: status is validated on its own).
    if tender.status in ("cancelled", "awarded", "closed"):
        checks.append(Check("live_status", "fail", True, f"tender is {tender.status}"))
    elif tender.status == "contradictory":
        checks.append(Check("live_status", "review_required", True,
                            next((r for r in tender.reasons if r.startswith("contradictory source")), "the source contradicts itself")))
    elif tender.status in ("unverified", "historical", "announced"):
        # Publication age is not a closing date: the record is held for review, never shown as open and never given a deadline.
        checks.append(Check("live_status", "review_required", True, tender.basis or f"status {tender.status}; confirm with the issuer"))
    elif tender.status == "unknown":
        checks.append(Check("live_status", "unknown", True, "tender status not established by an authoritative source"))
    if tender.status == "expired":
        checks.append(Check("not_expired", "fail", True, "deadline has passed"))
    elif tender.deadline_conflict:
        checks.append(Check("deadline_consistent", "review_required", True, "sources state conflicting deadlines"))
    elif tender.deadline is None:
        checks.append(Check("not_expired", "unknown", True, "deadline not established"))
    elif tender.status not in ("open", "revised"):
        checks.append(Check("not_expired", "unknown", True, f"deadline {tender.deadline.label()} but the tender is not live"))
    elif any(r.startswith("the deadline may already have passed") for r in tender.reasons):
        checks.append(Check("not_expired", "review_required", True,
                            f"the source states {tender.deadline.label()}; it may already have passed — confirm with the issuer"))
    else:
        checks.append(Check("not_expired", "pass", True, f"deadline {tender.deadline.label()}"))

    tc = {"covered": ("pass", "already covered by a WFC agreement"), "gap": ("pass", "no conflicting appointment known"),
          "blocked": ("fail", "an exclusive appointment is held elsewhere"), "unknown": ("unknown", "appointment exclusivity unknown")}
    if territory_cell_state is not None:  # representation mandates only
        r, why = tc[territory_cell_state]
        checks.append(Check("territory_conflict", r, True, why))  # type: ignore[arg-type]

    cr = {"ready": ("pass", "capability verified and current"), "blocked": ("fail", "capability or credential failure"),
          "review_required": ("unknown", "capability validity or credential expiry not recorded")}
    r, why = cr[capability_readiness]
    checks.append(Check("capability", r, True, why))  # type: ignore[arg-type]

    if eligibility_known is None or eligibility_known is False:
        checks.append(Check("eligibility", "unknown", False,
                            f"{eligibility_pending} eligibility criterion(s) await review (unsupported or not interpreted); none established"
                            if eligibility_pending else "eligibility criteria not yet established"))
    elif eligibility_met is None:
        checks.append(Check("eligibility", "unknown", False,
                            "eligibility criteria are stated in the evidence; record whether WFC meets them"))
    else:
        checks.append(Check("eligibility", "pass" if eligibility_met else "fail", True,
                            "meets stated criteria" if eligibility_met else "does not meet stated criteria"))
    checks.append(Check("scope", "pass" if scope_known else "unknown", False,
                        "scope established" if scope_known else "service scope not established"))
    return checks


# --------------------------------------------------------------------- commercial stage


STAGES = ("new", "reviewing", "qualified", "pursuing", "proposal", "negotiation", "won", "lost", "deferred", "expired")
_FORWARD = {
    "new": {"reviewing", "deferred", "lost", "expired"},
    "reviewing": {"qualified", "deferred", "lost", "expired"},
    "qualified": {"pursuing", "deferred", "lost", "expired"},
    "pursuing": {"proposal", "deferred", "lost", "expired"},
    "proposal": {"negotiation", "won", "lost", "deferred", "expired"},
    "negotiation": {"won", "lost", "deferred"},
    "deferred": {"reviewing"},
    "won": set(), "lost": set(), "expired": set(),
}


def allowed_stage_transition(current: str, target: str, qual: QualStatus) -> tuple[bool, str]:
    if target not in STAGES:
        return False, f"unknown stage {target}"
    if target not in _FORWARD.get(current, set()):
        return False, f"{current} -> {target} is not an allowed transition"
    if target in ("qualified", "pursuing", "proposal", "negotiation", "won") and qual != "approved_for_pursuit":
        if not (target == "qualified" and qual == "ready_for_review"):
            return False, f"moving to {target} requires qualification approved_for_pursuit (currently {qual})"
    return True, "ok"


def approve_for_pursuit(current: QualStatus) -> QualStatus:
    if current != "ready_for_review":
        raise ValueError(f"cannot approve from {current}: all blocking checks must pass first")
    return "approved_for_pursuit"
