"""Capability-area API (directive §9), economics (§11) and prioritisation
definitions. Behind the shared session like every business route."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..domain import prioritisation as pr
from ..services import economics_service as eco
from ..services import modules_service as mod
from ..services.audit import audit
from .common import db_of, exact, meta_of, not_found

router = APIRouter()


def _raise(exc: Exception) -> None:
    raise HTTPException(getattr(exc, "status", 400), getattr(exc, "detail", str(exc))) from exc


@router.get("/modules/summary", tags=["Capability Areas"])
@exact
def summary(request: Request):
    """Status of all nine areas, so the briefing can say which have data."""
    db = db_of(request)
    today = date.today()
    first = today.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    out = {
        "airline_representation": {"status": "ok", "opportunities": db.scalar("module_opportunity_count", module="airline_representation")},
        "account_growth": {"status": mod.account_growth(db)["status"]},
        "forwarder_sales": {"status": mod.forwarder_sales(db)["status"]},
        "capacity_lanes": {"status": mod.capacity_lanes(db, prev, first - timedelta(days=1))["status"]},
        "service_operations": {"status": "ok" if db.scalar("dataset_freshness", name="Import: exceptions") is not None else "not_connected"},
        "trucking_gateways": {"status": mod.trucking_gateways(db, today)["status"]},
        "outsourcing_training": {"status": mod.outsourcing_training(db)["status"]},
        "technology_solutions": {"status": mod.technology_solutions(db, prev, first - timedelta(days=1))["status"]},
        "network_development": {"status": mod.network_development(db)["status"], "items": db.scalar("network_count")},
    }
    return {"areas": out}


@router.get("/modules/account-growth", tags=["Capability Areas"])
@exact
def account_growth(request: Request, on: date | None = None):
    return mod.account_growth(db_of(request), on)


class KeyIn(BaseModel):
    key: str = Field(min_length=3, max_length=400)


@router.post("/modules/account-growth/opportunity", tags=["Capability Areas"])
@exact
def account_growth_opp(request: Request, body: KeyIn):
    try:
        return mod.opportunity_from_account_growth(db_of(request), body.key, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


@router.get("/modules/forwarder-sales", tags=["Capability Areas"])
@exact
def forwarder_sales(request: Request, as_of: date | None = None, dormant_days: int = Query(90, ge=14, le=730)):
    return mod.forwarder_sales(db_of(request), as_of, dormant_days)


@router.post("/modules/forwarder-sales/opportunity", tags=["Capability Areas"])
@exact
def forwarder_opp(request: Request, body: KeyIn):
    try:
        return mod.opportunity_from_forwarder(db_of(request), body.key, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


@router.get("/modules/capacity-lanes", tags=["Capability Areas"])
@exact
def capacity_lanes(request: Request, start: date, end: date):
    if end < start:
        raise HTTPException(422, "end is before start")
    return mod.capacity_lanes(db_of(request), start, end)


@router.get("/modules/trucking", tags=["Capability Areas"])
@exact
def trucking(request: Request, ship_date: date | None = None):
    return mod.trucking_gateways(db_of(request), ship_date or date.today())


@router.get("/modules/outsourcing-training", tags=["Capability Areas"])
@exact
def outsourcing(request: Request, on: date | None = None):
    return mod.outsourcing_training(db_of(request), on)


@router.get("/modules/technology", tags=["Capability Areas"])
@exact
def technology(request: Request, start: date, end: date):
    return mod.technology_solutions(db_of(request), start, end)


class PeriodKeyIn(BaseModel):
    key: str = Field(min_length=3, max_length=400)
    start: date
    end: date


class ShipKeyIn(BaseModel):
    key: str = Field(min_length=3, max_length=400)
    ship_date: date


@router.post("/modules/capacity-lanes/opportunity", tags=["Capability Areas"])
@exact
def capacity_opp(request: Request, body: PeriodKeyIn):
    try:
        return mod.opportunity_from_capacity(db_of(request), body.key, body.start, body.end, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


@router.post("/modules/trucking/opportunity", tags=["Capability Areas"])
@exact
def trucking_opp(request: Request, body: ShipKeyIn):
    try:
        return mod.opportunity_from_trucking(db_of(request), body.key, body.ship_date, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


@router.post("/modules/technology/opportunity", tags=["Capability Areas"])
@exact
def technology_opp(request: Request, body: PeriodKeyIn):
    try:
        return mod.opportunity_from_solution(db_of(request), body.key, body.start, body.end, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


@router.get("/modules/network-development", tags=["Capability Areas"])
@exact
def network_development(request: Request, on: date | None = None):
    return mod.network_development(db_of(request), on)


@router.post("/modules/network-development/gap", tags=["Capability Areas"])
@exact
def network_gap(request: Request, body: KeyIn):
    try:
        return mod.network_gap_candidate(db_of(request), body.key, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)


class OwnerIn(BaseModel):
    person_id: str | None


@router.post("/service/exceptions/{exc_id}/owner", tags=["Service Intelligence"])
@exact
def exception_owner(request: Request, exc_id: str, body: OwnerIn):
    try:
        mod.assign_exception_owner(db_of(request), exc_id, body.person_id, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)
    return {"ok": True}


class AckIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


@router.post("/service/exceptions/{exc_id}/acknowledge", tags=["Service Intelligence"])
@exact
def exception_ack(request: Request, exc_id: str, body: AckIn):
    try:
        mod.acknowledge_exception(db_of(request), exc_id, body.note, meta_of(request))
    except mod.ModuleRejected as exc:
        _raise(exc)
    return {"ok": True}


# ------------------------------------------------------------------ economics
class AssumptionIn(BaseModel):
    text: str = Field(min_length=3, max_length=500)
    source: str = Field(min_length=2, max_length=200)
    source_date: date


class ValueIn(BaseModel):
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    airline_revenue: Decimal | None = None
    wfc_remuneration: Decimal | None = None
    incremental_costs: Decimal | None = None
    guarantee_exposure: Decimal | None = None
    duration_months: int | None = Field(None, ge=0, le=240)
    basis: Literal["contract", "scenario", "unknown"] = "unknown"
    assumptions: list[AssumptionIn] = Field(default_factory=list)
    value_kind: Literal["potential", "won", "realised"] = "potential"


@router.post("/opportunities/{opp_id}/value", tags=["Opportunities"])
@exact
def set_value(request: Request, opp_id: str, body: ValueIn):
    try:
        return eco.set_value(db_of(request), opp_id, body.model_dump(), meta_of(request))
    except eco.EconomicsRejected as exc:
        _raise(exc)


class GroupIn(BaseModel):
    with_opportunity_id: str | None = None


@router.post("/opportunities/{opp_id}/competition", tags=["Opportunities"])
@exact
def competition(request: Request, opp_id: str, body: GroupIn):
    try:
        return eco.set_competition(db_of(request), opp_id, body.with_opportunity_id, meta_of(request))
    except eco.EconomicsRejected as exc:
        _raise(exc)


class ReferralIn(BaseModel):
    opportunity_id: str
    from_company: str
    to_company: str


@router.post("/referrals", tags=["Network Development"])
@exact
def add_referral(request: Request, body: ReferralIn):
    db = db_of(request)
    if body.from_company == body.to_company:
        raise HTTPException(422, "a referral is between two different operating companies")
    rid = db.scalar("referral_insert", opp=body.opportunity_id, src=body.from_company, dst=body.to_company)
    if rid is None:
        raise HTTPException(409, "this opportunity is already referred to that company")
    audit(db, "referral_created", meta_of(request), entity_type="referral", entity_id=str(rid))
    return {"id": rid}


class ReferralStatus(BaseModel):
    status: Literal["accepted", "declined", "closed"]


@router.post("/referrals/{ref_id}/status", tags=["Network Development"])
@exact
def referral_status(request: Request, ref_id: str, body: ReferralStatus):
    db = db_of(request)
    if db.scalar("referral_set_status", id=ref_id, status=body.status) is None:
        cur = db.one("referral_get", id=ref_id)
        if cur is not None:
            raise HTTPException(409, f"a {cur['status']} referral cannot become {body.status} "
                                     "(allowed: proposed → accepted or declined; accepted → closed)")
        raise not_found("Referral")
    audit(db, "referral_status", meta_of(request), entity_type="referral", entity_id=ref_id, detail={"status": body.status})
    return {"ok": True}


@router.get("/referrals", tags=["Network Development"])
@exact
def referrals(request: Request):
    return {"items": db_of(request).all("referrals_list")}


class LinkSignalIn(BaseModel):
    signal_id: str


@router.post("/network/{cand_id}/evidence", tags=["Network Development"])
@exact
def link_network_evidence(request: Request, cand_id: str, body: LinkSignalIn):
    """Attach a discovered signal (e.g. a supported partnership claim) as
    supporting evidence for a network candidate."""
    db = db_of(request)
    if db.scalar("network_link_signal", id=cand_id, signal=body.signal_id) is None:
        raise not_found("Network item or signal")
    audit(db, "network_evidence_linked", meta_of(request), entity_type="network_candidate", entity_id=cand_id)
    return {"ok": True}


@router.get("/settings/prioritisation", tags=["Settings"])
@exact
def prioritisation_definitions(request: Request):
    return {"models": pr.definitions(),
            "note": "Weights are provisional until evaluated against recorded outcomes. Scores are not probabilities of winning. "
                    "Attractiveness, evidence confidence, readiness and risk are kept separate. Rankings compare within a module only."}
