"""Signal identity, module routing and merge-review similarity (directive §6).

Separate tenders must remain separate opportunities:
- With a stable tender reference, identity is (subject, reference): every
  amendment, deadline revision or cancellation that cites the reference is
  applied to that tender and no other.
- With a procurement cycle but no reference: (subject, delivery countries,
  cycle).
- With neither, each announcement family is its own tender candidate. A
  similar existing tender (same subject, overlapping countries) becomes a
  MERGE-REVIEW candidate. Nothing without a reliable identifier is merged
  automatically.
- Route and capacity announcements live in their own key space, so they
  are never merged with tenders.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SERVICE_MODULE = {
    "GSSA": "airline_representation", "TCM": "airline_representation",
    "HANDLING": "outsourcing_training", "DATA_PROCESSING": "outsourcing_training", "ACCOUNTING": "outsourcing_training",
    "INVOICING": "outsourcing_training", "COLLECTIONS": "outsourcing_training", "TRAINING": "outsourcing_training",
    "TRUCKING": "trucking_gateways", "TECHNOLOGY": "technology_solutions",
}
TENDER_ANCHORS = {"gssa_tender", "service_tender"}
# tender_context (fifth instruction of 27 Oct 2026, item 5): supporting information about an established tender (a contact
# update, a clarification) that announces nothing; attached to the tender, never a status, deadline or freshness statement.
TENDER_FOLLOWERS = {"tender_deadline", "tender_status", "tender_scope", "eligibility", "tender_context"}
ROUTE_TYPES = {"route_launch", "route_suspension"}


@dataclass(frozen=True)
class Identity:
    key: str
    basis: str            # tender_ref | procurement_cycle | announcement | route | subject
    module: str
    related_modules: tuple[str, ...] = ()


def norm_ref(ref: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", ref.upper())


_norm_ref = norm_ref


def module_for(claim_type: str, service_code: str | None) -> tuple[str, tuple[str, ...]]:
    # Road-feeder services: an airline's RFS launch or its appointment of RFS providers belongs to trucking and gateways.
    if claim_type in ("representation_change", "route_launch", "route_suspension") and (service_code or "").upper() == "TRUCKING":
        return "trucking_gateways", ("airline_representation", "capacity_lanes") if claim_type != "representation_change" else ("airline_representation",)
    if claim_type in ("gssa_tender", "tcm_signal", "representation_change") or claim_type in TENDER_FOLLOWERS:
        return "airline_representation", ()
    if claim_type == "service_tender":
        return SERVICE_MODULE.get(service_code or "", "outsourcing_training"), ()
    if claim_type in ROUTE_TYPES:
        # A route launch or suspension without stated trucking scope is a capacity and trade-lane event (fourth instruction of
        # 27 Oct, item 4), never airline representation by default.
        return "capacity_lanes", ("airline_representation", "trucking_gateways")
    if claim_type == "capacity_statement":
        return "capacity_lanes", ("airline_representation",)
    if claim_type == "partnership":
        return "network_development", ()
    return "network_development", ()


def signal_identity(claim_type: str, *, subject: str | None, countries: list[str], lane: str | None,
                    tender_ref: str | None, procurement_cycle: str | None, family_key: str,
                    service_code: str | None = None, tender_module: str | None = None) -> Identity:
    module, related = module_for(claim_type, service_code)
    if claim_type in TENDER_FOLLOWERS and tender_module:
        module = tender_module
    subj = subject or "unknown-subject"
    where = ",".join(sorted(countries)) or "-"
    if claim_type in TENDER_ANCHORS | TENDER_FOLLOWERS:
        if tender_ref:
            return Identity(f"tender|{subj}|ref:{_norm_ref(tender_ref)}", "tender_ref", module, related)
        if procurement_cycle:
            return Identity(f"tender|{subj}|{where}|cycle:{_norm_ref(procurement_cycle)}", "procurement_cycle", module, related)
        # Without a reference or cycle, two notices of one family for DIFFERENT services (a listing's handling row and its IT row)
        # are different tenders; the service is part of the identity.
        svc = f"|svc:{service_code.upper()}" if service_code else ""
        return Identity(f"tender|{subj}|{where}|ann:{family_key}{svc}", "announcement", module, related)
    if claim_type in ROUTE_TYPES or claim_type == "capacity_statement":
        return Identity(f"route|{subj}|{lane or where}", "route", module, related)
    if claim_type in ("representation_change", "tcm_signal"):
        return Identity(f"rep|{claim_type}|{subj}|{where}", "subject", module, related)
    if claim_type == "partnership":
        return Identity(f"partner|{subj}|{where}", "subject", module, related)
    return Identity(f"other|{family_key}", "announcement", module, related)


def tender_similarity(a_countries: set[str], b_countries: set[str], a_text: str, b_text: str) -> float:
    """Score for a merge-review candidate between two tender signals of the
    same subject with no shared reliable identifier. Country overlap and
    wording overlap; never used to merge automatically."""
    if not a_countries or not b_countries:
        geo = 0.5
    else:
        geo = len(a_countries & b_countries) / len(a_countries | b_countries)
    ta = set(re.findall(r"[a-z0-9]+", a_text.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b_text.lower()))
    words = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return round(0.6 * geo + 0.4 * words, 4)


def name_similarity(a: str, b: str) -> float:
    stop = {"the", "ltd", "limited", "llc", "plc", "inc", "co", "company", "airlines", "airline", "airways", "cargo", "group"}
    ta = {t for t in re.findall(r"[a-z0-9]+", a.lower()) if t not in stop}
    tb = {t for t in re.findall(r"[a-z0-9]+", b.lower()) if t not in stop}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
