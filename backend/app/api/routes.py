"""Business API, one router per navigation section.

Every route here sits behind AuthGateMiddleware (session + CSRF). Company,
region and service parameters are FILTERS that organise data; they never
restrict access. The shared login sees every record in this instance.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..domain import economics as ec
from ..domain import exports as ex
from ..domain import import_docs
from ..domain import recommendations as rec
from ..domain import imports as im
from ..domain import metrics as mt
from ..domain.channels import ChannelEvent, booking_funnel
from ..domain.coverage import Agreement, ThirdPartyAppointment, coverage_matrix
from ..services import economics_service, fit_service, imports_service, ops_service, opportunity_service
from ..services.audit import audit
from .common import Paging, db_of, exact, insight, meta_of, not_found, page

router = APIRouter()
MODULES = Literal["airline_representation", "account_growth", "forwarder_sales", "capacity_lanes", "service_operations",
                  "trucking_gateways", "outsourcing_training", "technology_solutions", "network_development"]


# ------------------------------------------------------------------ Executive Briefing
@router.get("/briefing", tags=["Executive Briefing"])
@exact
def briefing(request: Request, days: int = Query(14, ge=1, le=90), countries: str | None = None, region: str | None = None):
    """Geography is a reporting filter applied consistently: deadlines, signals
    and pipeline counts are restricted to opportunities/signals whose scope
    includes a selected country."""
    db = db_of(request)
    geo = _geo(db, countries, region)
    scope = "All operating companies" + (f"; countries {', '.join(geo)}" if geo else "")
    return {
        "pipeline": db.all("briefing_pipeline_geo", geo=geo),
        "deadlines": db.all("briefing_deadlines_geo", days=days, geo=geo),
        "signals": db.all("briefing_signals_geo", limit=20, geo=geo),
        "exceptions": db.all("briefing_exceptions"),
        "sources": db.all("source_health"),
        "review": db.one("review_counts"),
        "runs": db.all("runs_list", search=None, source=None, limit=5),
        "geography": geo,
        "insight": insight(db, scope=scope, period=f"Next {days} days (deadlines)",
                           datasets=["bookings", "quotes", "exceptions", "capacity"]),
    }


def _dl_label(info: dict | None) -> str | None:
    """The deadline exactly as the source stated it (date only / local time / instant); None when unknown."""
    from ..domain.deadlines import StatedDeadline
    d = StatedDeadline.from_json(info)
    return d.label() if d else None


def _uuid_or_422(value: str | None, name: str) -> str | None:
    """Filters that name a record by id: a malformed id is the caller's error (422), not a server error."""
    if value in (None, ""):
        return None
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise HTTPException(422, f"{name} must be a record id") from None


def _geo(db, countries: str | None, region: str | None) -> list[str] | None:
    """Country filter from a comma list and/or a region code; None = no filter."""
    from ..reference.geography import COUNTRIES

    out: set[str] = set()
    if countries:
        bad = [c for c in (x.strip().upper() for x in countries.split(",")) if c and c not in COUNTRIES]
        if bad:
            raise HTTPException(422, f"unknown country code(s): {', '.join(bad)}")
        out |= {x.strip().upper() for x in countries.split(",") if x.strip()}
    if region:
        members = [r["country_code"] for r in db.all("region_members") if r["region_code"] == region.upper()]
        if not members:
            raise HTTPException(422, f"unknown region {region}")
        out |= set(members)
    return sorted(out) if out else None


# ------------------------------------------------------------------ Opportunities
@router.get("/opportunities", tags=["Opportunities"])
@exact
def list_opportunities(request: Request, paging: Paging = Depends(), module: MODULES | None = None, stage: str | None = None,
                       qualification: str | None = None, company: str | None = None, q: str | None = None,
                       countries: str | None = None, region: str | None = None):
    db = db_of(request)
    geo = _geo(db, countries, region)
    rows = db.all("opportunity_list2", module=module, stage=stage, qual=qualification, company=_uuid_or_422(company, "company"), q=q, geo=geo,
                  limit=paging.limit, offset=paging.offset)
    return page(rows, paging, insight(db, scope=(company or "All operating companies") + (f"; countries {', '.join(geo)}" if geo else ""),
                                      period=None, datasets=[]))


@router.get("/opportunities/{opp_id}", tags=["Opportunities"])
@exact
def get_opportunity(request: Request, opp_id: str):
    db = db_of(request)
    o = db.one("opportunity_get2", id=opp_id)
    if o is None:
        raise not_found("Opportunity")
    value = db.one("opportunity_value", id=opp_id)
    contribution = None
    if value:
        cv = ec.CommercialValue(opp_id, value["currency"], value["airline_revenue"], value["wfc_remuneration"],
                                value["incremental_costs"], value["guarantee_exposure"], value["basis"],
                                tuple(ec.Assumption(a["text"], a["source"], date.fromisoformat(a["source_date"]))
                                      for a in (value["assumptions"] or [])))
        r = ec.retained_contribution(cv)
        contribution = {"status": r.status, "retained_contribution": r.retained_contribution, "currency": r.currency, "reasons": r.reasons}
    signal_id = o.get("signal_id")
    return {"opportunity": o, "checks": db.all("opportunity_checks", id=opp_id), "overrides": db.all("opportunity_overrides", id=opp_id),
            "history": db.all("opportunity_history", id=opp_id),
            "evidence": db.all("signal_evidence_view", signal=signal_id) if signal_id else [],
            "geography": db.all("opportunity_geo", id=opp_id), "assessments": db.all("opportunity_assessments", id=opp_id),
            "value": value, "contribution": contribution, "referrals": db.all("referrals_for", id=opp_id),
            "competing": db.all("opportunity_competitors", id=opp_id)}


class StageChange(BaseModel):
    to: str
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/opportunities/{opp_id}/stage", tags=["Opportunities"])
@exact
def change_stage(request: Request, opp_id: str, body: StageChange):
    try:
        return {"commercial_stage": opportunity_service.change_stage(db_of(request), opp_id, body.to, body.reason, meta_of(request))}
    except opportunity_service.ActionRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


class Approval(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/opportunities/{opp_id}/approve", tags=["Opportunities"])
@exact
def approve(request: Request, opp_id: str, body: Approval):
    try:
        return {"qualification_status": opportunity_service.approve(db_of(request), opp_id, body.reason, meta_of(request))}
    except opportunity_service.ActionRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


class OverrideIn(BaseModel):
    check_code: str
    result: Literal["pass", "fail", "review_required"]
    reason: str = Field(min_length=10, max_length=2000)
    expires_at: datetime | None = None


@router.post("/opportunities/{opp_id}/overrides", tags=["Opportunities"])
@exact
def add_override(request: Request, opp_id: str, body: OverrideIn):
    try:
        return {"override_id": opportunity_service.add_override(db_of(request), opp_id, body.check_code, body.result, body.reason,
                                                                body.expires_at, meta_of(request))}
    except opportunity_service.ActionRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


class ScopeIn(BaseModel):
    operating_company_id: str | None = None
    service_id: str | None = None
    station_code: str | None = Field(None, pattern=r"^[A-Za-z]{3}$")
    delivery_start: date | None = None
    required_credentials: list[str] = Field(default_factory=list, max_length=20)


@router.post("/opportunities/{opp_id}/scope", tags=["Opportunities"])
@exact
def set_scope(request: Request, opp_id: str, body: ScopeIn):
    """Assign the delivering operating company, service, station, delivery date
    and required credentials; capability is then resolved from the register
    (it cannot be overridden to pass) and qualification is recomputed."""
    try:
        return {"qualification_status": opportunity_service.set_scope(
            db_of(request), opp_id, body.operating_company_id, body.service_id, meta_of(request), station_code=body.station_code,
            delivery_start=body.delivery_start, required_credentials=body.required_credentials)}
    except opportunity_service.ActionRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


class OwnerIn(BaseModel):
    person_id: str | None


@router.post("/opportunities/{opp_id}/owner", tags=["Opportunities"])
@exact
def assign_owner(request: Request, opp_id: str, body: OwnerIn):
    try:
        return {"qualification_status": opportunity_service.assign_owner(db_of(request), opp_id, body.person_id, meta_of(request))}
    except opportunity_service.ActionRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


# ------------------------------------------------------------------ Airlines and Forwarders
@router.get("/organisations", tags=["Airlines and Forwarders"])
@exact
def list_organisations(request: Request, paging: Paging = Depends(), kind: str | None = None, q: str | None = None):
    db = db_of(request)
    return page(db.all("organisation_list", kind=kind, q=q, limit=paging.limit, offset=paging.offset), paging)


@router.get("/organisations/{org_id}", tags=["Airlines and Forwarders"])
@exact
def get_organisation(request: Request, org_id: str):
    db = db_of(request)
    o = db.one("organisation_get", id=org_id)
    if o is None:
        raise not_found("Organisation")
    out: dict[str, Any] = {"organisation": o, "engagements": db.all("engagements_for_org", org=org_id)}
    if o["kind"] == "airline":
        out["agreements"] = db.all("agreements_for_airline", airline=org_id)
        out["third_party_appointments"] = db.all("third_party_for_airline", airline=org_id)
    if o["kind"] == "forwarder":
        out["monthly"] = db.all("forwarder_monthly", forwarder=org_id)
        out["insight"] = insight(db, scope=o["canonical_name"], period="All loaded months", datasets=["bookings", "quotes"])
    return out


@router.get("/organisations/{airline_id}/coverage", tags=["Airlines and Forwarders"])
@exact
def airline_coverage(request: Request, airline_id: str, territories: str = Query(..., description="Comma-separated codes"),
                     services: str = Query(..., description="Comma-separated service codes"), on: date | None = None):
    db = db_of(request)
    on = on or date.today()
    ags = [Agreement(airline_id, a["operating_company"], frozenset(a["territories"]), frozenset(a["services"]), a["effective_from"],
                     a["effective_to"], a["exclusivity"], a["appointment_rights"], a["status"])
           for a in db.all("agreements_for_airline", airline=airline_id)]
    tps = [ThirdPartyAppointment(airline_id, t["territory"], t["service"], t["holder"] or "unknown holder", t["exclusivity"], t["valid_to"])
           for t in db.all("third_party_for_airline", airline=airline_id)]
    cells = coverage_matrix(airline_id, [t.strip() for t in territories.split(",") if t.strip()],
                            [s.strip() for s in services.split(",") if s.strip()], ags, tps, on)
    return {"cells": [c.__dict__ for c in cells],
            "insight": insight(db, scope="All operating companies", period=f"As at {on.isoformat()}", datasets=["agreements"])}


@router.get("/forwarders/{forwarder_id}/review", tags=["Airlines and Forwarders"])
@exact
def forwarder_review(request: Request, forwarder_id: str, month: date = Query(..., description="First day of the month")):
    db = db_of(request)
    start = month.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    pts = [(r["day"], r["kg"]) for r in db.all("forwarder_daily_weight", forwarder=forwarder_id)]
    first = pts[0][0] if pts else None
    cmp_ = mt.compare_periods(pts, start, end, as_of=date.today(), data_start=first)
    lost = {r["reason"]: int(r["n"]) for r in db.all("forwarder_lost_reasons", forwarder=forwarder_id,
                                                        since=datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))}
    item = mt.declining_account_review(forwarder_id, cmp_, lost_reasons=lost)
    return {"comparison": cmp_.__dict__, "review_item": item.__dict__ if item else None,
            "insight": insight(db, scope="Forwarder account", period=f"{start.isoformat()} to {end.isoformat()}",
                               datasets=["bookings", "quotes"], gaps=cmp_.notes)}


# ------------------------------------------------------------------ Trade Lanes and Capacity
@router.get("/lanes", tags=["Trade Lanes and Capacity"])
@exact
def lanes(request: Request, start: date, end: date):
    db = db_of(request)
    return {"items": db.all("lane_summary", start=start, end=end),
            "insight": insight(db, scope="All lanes (directional)", period=f"{start} to {end}", datasets=["bookings", "capacity"])}


@router.get("/lanes/{lane_id}", tags=["Trade Lanes and Capacity"])
@exact
def lane_detail(request: Request, lane_id: str, start: date, end: date, basis: Literal["weight_kg", "volume_m3"] = "weight_kg",
                capacity_type: Literal["offered", "bookable", "allotted"] = "bookable", reporting_currency: str | None = None):
    db = db_of(request)
    lane_row = db.one("lane_get", lane=lane_id)
    if lane_row is None:
        raise not_found("Lane")
    lane = mt.Lane(lane_row["origin"], lane_row["destination"])
    rows = [mt.BookingRow(b["external_id"], lane, b["flight_date"], b["status"], b["actual_weight_kg"], b["chargeable_weight_kg"],
                          b["volume_m3"], b["revenue"], b["currency"], None, b["fx_rate_to_reporting"], b["fx_source"], b["fx_date"])
            for b in db.all("lane_bookings", lane=lane_id, start=start, end=end)]
    caps = [mt.CapacityRow(lane, c["period_start"], c["period_end"], c["basis"], c["capacity_type"], c["amount"])
            for c in db.all("lane_capacity", lane=lane_id, start=start, end=end)]
    util = mt.utilisation(rows, caps, lane, start, end, basis, capacity_type)
    money = mt.revenue_totals(rows, reporting_currency)
    return {"lane": lane_row, "chargeable": mt.booked_quantity(rows, lane, start, end, basis).__dict__,
            "actual_weight": mt.booked_quantity(rows, lane, start, end, "weight_kg", "actual").__dict__ if basis == "weight_kg" else None,
            "utilisation": util.__dict__, "revenue": money.__dict__, "capacity": [c.__dict__ | {"lane": lane.key} for c in caps],
            "insight": insight(db, scope=lane.key, period=f"{start} to {end}", datasets=["bookings", "capacity"],
                               gaps=[util.reason] if util.reason else [])}


# ------------------------------------------------------------------ Service Intelligence
@router.get("/service/exceptions", tags=["Service Intelligence"])
@exact
def exceptions(request: Request, paging: Paging = Depends(), status: str | None = "active"):
    db = db_of(request)
    rows = db.all("exceptions_list", status=status, limit=paging.limit, offset=paging.offset)
    rows = rec.explain_ranks("service_operations", rows,
                             lambda e: f"severity {e['severity']}; deadline {e['deadline_utc'].isoformat() if e['deadline_utc'] else 'not stated'}",
                             lambda e: [None if e["owner_person_id"] else "owner not assigned", None if e["deadline_utc"] else "deadline"])
    for i, r in enumerate(rows, start=1):
        r["rank"] = paging.offset + i
    return page(rows, paging, insight(db, scope="All operating companies", period="Current", datasets=["exceptions"]))


class ResolveIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


@router.post("/service/exceptions/{exc_id}/resolve", tags=["Service Intelligence"])
@exact
def resolve_exception(request: Request, exc_id: str, body: ResolveIn):
    if not ops_service.resolve(db_of(request), exc_id, body.note, meta_of(request)):
        raise HTTPException(409, "Exception not found or already resolved")
    return {"ok": True}


@router.get("/service/exceptions/{exc_id}/history", tags=["Service Intelligence"])
@exact
def exception_history(request: Request, exc_id: str):
    return {"items": db_of(request).all("exception_history", id=exc_id)}


# ------------------------------------------------------------------ Group Capabilities (incl. outsourcing, training, trucking)
@router.get("/capabilities", tags=["Group Capabilities"])
@exact
def capabilities(request: Request, company: str | None = None):
    db = db_of(request)
    return {"capabilities": db.all("capabilities_all", company=_uuid_or_422(company, "company")), "credentials": db.all("credentials_all"),
            "feeders": db.all("feeders_list"), "companies": db.all("operating_companies"), "services": db.all("services_list"),
            "insight": insight(db, scope=company or "All operating companies", period="Current", datasets=["capabilities", "trucking"])}


# ------------------------------------------------------------------ Technology and solutions (module 8)
@router.get("/technology/funnel", tags=["Reports"])
@exact
def channel_funnel(request: Request, start: date, end: date, channel: str | None = None):
    db = db_of(request)
    channels = db.all("channel_list")
    out: dict[str, Any] = {"channels": channels, "funnel": None,
                           "integration_failures": db.all("integration_failures", start=start, end=end + timedelta(days=1))}
    if channel:
        lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        evs = [ChannelEvent(e["event_type"], e["session_key"], e["booking_external_id"], e["occurred_at"], e["channel"])
               for e in db.all("channel_events_period", start=lo, end=hi, channel=channel)]
        f = booking_funnel(evs, lo, hi, channel)
        out["funnel"] = {"status": f.status, "stages": f.stages, "conversion": f.conversion, "limitations": f.limitations}
    out["insight"] = insight(db, scope=channel or "All channels", period=f"{start} to {end}", datasets=["channel_events"])
    return out


# ------------------------------------------------------------------ Relationships
@router.get("/relationships/people", tags=["Relationships"])
@exact
def people(request: Request, paging: Paging = Depends(), q: str | None = None):
    return page(db_of(request).all("people_list", q=q, limit=paging.limit, offset=paging.offset), paging)


class PersonIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    role_title: str | None = None
    organisation_id: str | None = None
    operating_company_id: str | None = None
    email: str | None = None
    is_internal: bool = False


@router.post("/relationships/people", tags=["Relationships"])
@exact
def add_person(request: Request, body: PersonIn):
    db = db_of(request)
    pid = db.scalar("person_insert", full_name=body.full_name, role_title=body.role_title, organisation_id=body.organisation_id,
                    company_id=body.operating_company_id, email=body.email, is_internal=body.is_internal)
    audit(db, "person_added", meta_of(request), entity_type="person", entity_id=str(pid))
    return {"id": pid}


class EngagementIn(BaseModel):
    organisation_id: str
    person_id: str | None = None
    opportunity_id: str | None = None
    occurred_at: datetime
    kind: Literal["meeting", "call", "email", "proposal", "visit", "other"]
    summary: str = Field(min_length=3, max_length=4000)


@router.post("/relationships/engagements", tags=["Relationships"])
@exact
def add_engagement(request: Request, body: EngagementIn):
    return {"id": db_of(request).scalar("engagement_insert", org=body.organisation_id, person=body.person_id, opp=body.opportunity_id,
                                        at=body.occurred_at, kind=body.kind, summary=body.summary)}


@router.get("/tasks", tags=["Relationships"])
@exact
def tasks(request: Request, status: str | None = None, limit: int = Query(100, ge=1, le=200)):
    return {"items": db_of(request).all("tasks_list", status=status, limit=limit)}


class TaskStatusIn(BaseModel):
    status: Literal["open", "in_progress", "done", "cancelled"]


@router.post("/tasks/{task_id}/status", tags=["Relationships"])
@exact
def task_status(request: Request, task_id: str, body: TaskStatusIn):
    if db_of(request).scalar("task_set_status", id=task_id, status=body.status) is None:
        raise not_found("Task")
    return {"ok": True}


# ------------------------------------------------------------------ Network Development
@router.get("/network", tags=["Network Development"])
@exact
def network(request: Request, kind: Literal["coverage_gap", "partner", "referral", "acquisition_research"] | None = None):
    db = db_of(request)
    items = db.all("network_list", kind=kind)
    for it in items:
        if it.get("latest_fit"):
            cur = fit_service.current(db, str(it["id"]))
            it["latest_fit"] = (it["latest_fit"] | {"valid": cur["valid"], "changes": cur["changes"]}) if cur else it["latest_fit"]
    return {"items": items,
            "note": "Acquisition research is kept separate from the sales pipeline and is visible to the shared login. No valuations are generated. "
                    "A partner fit is invalidated when the partner evidence or WFC's own agreements change, and is then reassessed."}


class NetworkIn(BaseModel):
    kind: Literal["coverage_gap", "partner", "referral", "acquisition_research"]
    title: str = Field(min_length=3, max_length=300)
    organisation_id: str | None = None
    territory_id: str | None = None
    service_id: str | None = None


@router.post("/network", tags=["Network Development"])
@exact
def add_network(request: Request, body: NetworkIn):
    db = db_of(request)
    nid = db.scalar("network_insert", kind=body.kind, org=body.organisation_id, territory=body.territory_id, service=body.service_id,
                    title=body.title)
    audit(db, "network_candidate_added", meta_of(request), entity_type="network_candidate", entity_id=str(nid))
    return {"id": nid}


class FitIn(BaseModel):
    organisation_id: str
    gaps: list[tuple[str, str]] = Field(max_length=200)


@router.post("/network/{cand_id}/fit", tags=["Network Development"])
@exact
def assess_fit(request: Request, cand_id: str, body: FitIn):
    try:
        org = _uuid_or_422(body.organisation_id, "organisation_id")
        if org is None:
            raise HTTPException(422, "organisation_id is required")
        return fit_service.assess(db_of(request), cand_id, org, body.gaps, meta_of(request))
    except fit_service.FitRejected as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/network/{cand_id}/fit", tags=["Network Development"])
@exact
def current_fit(request: Request, cand_id: str):
    cur = fit_service.current(db_of(request), cand_id)
    if cur is None:
        raise not_found("Fit assessment")
    return cur


@router.post("/network/{cand_id}/fit/reassess", tags=["Network Development"])
@exact
def reassess_fit(request: Request, cand_id: str):
    try:
        return fit_service.reassess(db_of(request), cand_id, meta_of(request))
    except fit_service.FitRejected as exc:
        raise HTTPException(exc.status, exc.message) from exc


# ------------------------------------------------------------------ Reports
@router.get("/reports/pipeline", tags=["Reports"])
@exact
def pipeline_report(request: Request, company: str | None = None, module: MODULES | None = None,
                    kind: Literal["potential", "won", "realised"] = "potential", countries: str | None = None, region: str | None = None,
                    reporting_currency: str | None = Query(None, pattern=r"^[A-Z]{3}$"),
                    fx: str | None = Query(None, description="Explicit dated rates: CCY:rate:YYYY-MM-DD:source;... to the reporting currency")):
    db = db_of(request)
    geo = _geo(db, countries, region)
    rows = db.all("values_for_pipeline2", company=_uuid_or_422(company, "company"), module=module, geo=geo, kind=kind)
    vals = [ec.CommercialValue(r["opportunity_id"], r["currency"], r["airline_revenue"], r["wfc_remuneration"], r["incremental_costs"],
                               r["guarantee_exposure"], r["basis"],
                               tuple(ec.Assumption(a["text"], a["source"], date.fromisoformat(a["source_date"])) for a in (r["assumptions"] or [])),
                               r["value_kind"], r["competition_group"])
            for r in rows]
    t = ec.pipeline_totals(vals, kind)
    attribution = {r["opportunity_id"]: {"company": r["operating_company"], "referred_from": r["referred_from"]}
                   for r in rows if r["referred"]}
    conversion = None
    if reporting_currency:
        rates = []
        for part in (fx or "").split(";"):
            if not part.strip():
                continue
            bits = part.split(":")
            if len(bits) < 4:
                raise HTTPException(422, "fx entries must be CCY:rate:YYYY-MM-DD:source")
            try:
                rates.append({"currency": bits[0].upper(), "rate": Decimal(bits[1]), "date": date.fromisoformat(bits[2]).isoformat(),
                              "source": ":".join(bits[3:])})
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(422, f"invalid fx entry {part!r}") from exc
        conversion = economics_service.convert(t.by_currency, rates, reporting_currency)
    return {"by_currency": t.by_currency, "counted": t.counted, "excluded": t.excluded, "unqualified": t.unqualified,
            "conversion": conversion, "geography": geo, "referral_attribution": attribution,
            "note": "Retained contribution only; airline revenue is never shown as contribution. Currencies are not combined unless "
                    "you supply an explicit, dated conversion basis. Competing alternatives count once (largest). A referred opportunity "
                    "counts once, for the company that accepted the referral, not the one that referred it. Acquisition research is never in the pipeline. Rankings are within module only.",
            "insight": insight(db, scope=(company or "All operating companies") + (f"; countries {', '.join(geo)}" if geo else ""),
                               period=None, datasets=[])}


@router.get("/reports/opportunities.csv", tags=["Reports"])
@exact
def export_opportunities(request: Request, module: MODULES | None = None, company: str | None = None, stage: str | None = None,
                         qualification: str | None = None, q: str | None = None, countries: str | None = None, region: str | None = None):
    db = db_of(request)
    geo = _geo(db, countries, region)
    rows = db.all("opportunity_list2", module=module, stage=stage, qual=qualification, company=_uuid_or_422(company, "company"), q=q, geo=geo, limit=10000, offset=0)
    tz = request.app.state.settings.reporting_timezone
    headers = ["id", "module", "title", "commercial_stage", "qualification_status", "classification", "tender_status", "tender_status_basis",
               "freight_scope", "evidence_published_at", "status_stated_at", "status_first_stated_at", "last_retrieved_at", "operating_company",
               "organisation", "countries", "deadline_as_stated", "deadline_precision", "deadline_utc", f"deadline_{tz}", "deadline_source_tz",
               "owner"]
    from zoneinfo import ZoneInfo

    def local(v):
        return v.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M") if v else None
    now = datetime.now(timezone.utc).isoformat()
    body = ex.to_csv(headers, ([r.get("id"), r.get("module"), r.get("title"), r.get("commercial_stage"), r.get("qualification_status"),
                                r.get("classification"), r.get("tender_status") or "unknown", r.get("tender_status_basis"),
                                r.get("freight_scope") or "unclear", r.get("evidence_published_at"),
                                r.get("status_stated_at") or ("unknown" if r.get("tender_status") in ("open", "revised", "unverified") else None),
                                r.get("status_first_stated_at"), r.get("last_retrieved_at"), r.get("operating_company"), r.get("organisation"),
                                "; ".join(r.get("countries") or []), _dl_label(r.get("deadline_info")),
                                (r.get("deadline_info") or {}).get("precision"), r.get("deadline_utc"), local(r.get("deadline_utc")),
                                r.get("deadline_source_tz"), r.get("owner")] for r in rows),
                     scope_note=(f"Opportunities; module={module or 'all'}; company={company or 'all'}; stage={stage or 'all'}; "
                                 f"qualification={qualification or 'all'}; countries={', '.join(geo) if geo else 'all'}; search={q or '-'}; "
                                 f"reporting time zone {tz}"), generated_at=now)
    audit(db, "export", meta_of(request), entity_type="report", entity_id="opportunities.csv",
          detail={"rows": len(rows), "module": module, "company": company, "countries": geo})
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="atlas-opportunities.csv"'})


@router.get("/audit", tags=["Reports"])
@exact
def audit_log(request: Request, paging: Paging = Depends()):
    return {"items": db_of(request).all("audit_list", limit=paging.limit, offset=paging.offset)}


# ------------------------------------------------------------------ Data Sources and Imports
@router.get("/data-sources", tags=["Data Sources and Imports"])
@exact
def data_sources(request: Request):
    db = db_of(request)
    return {"connectors": db.all("connectors_list"), "sources": db.all("source_health"),
            "imports": db.all("import_jobs_list", dataset=None, limit=50),
            "datasets": [{"dataset": c.dataset, "category": "master" if c.dataset in im.MASTER_DATA else "operational",
                          "source_of_truth": c.source_of_truth, "freshness_sla_hours": c.freshness_sla_hours,
                          "retention": c.retention, "fields": [f.__dict__ | {"why_required": import_docs.WHY_REQUIRED.get(f.name) if f.required else None} for f in c.fields],
                          "refresh": import_docs.refresh_requirement(c.dataset), "duplicate_key": import_docs.duplicate_key(c.dataset),
                          "correction": import_docs.correction_mode(c.dataset), "used_by": list(import_docs.USED_BY.get(c.dataset, ())),
                          "commit_supported": c.dataset in imports_service.COMMIT_SUPPORTED,
                          "reversible": c.dataset in imports_service.REVERSIBLE,
                          "freshness": db.one("dataset_freshness", name=f"Import: {c.dataset}")} for c in im.CONTRACTS.values()]}


@router.get("/imports/templates/{dataset}.csv", tags=["Data Sources and Imports"])
@exact
def template(dataset: str):
    if dataset not in im.CONTRACTS:
        raise not_found("Dataset")
    return Response(im.template_csv(dataset), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{dataset}-template.csv"'})


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(im.MAX_FILE_BYTES + 1)
    if len(data) > im.MAX_FILE_BYTES:
        raise HTTPException(413, "File too large")
    return data


@router.post("/imports/{dataset}/preview", tags=["Data Sources and Imports"])
@exact
async def import_preview(request: Request, dataset: str, file: UploadFile = File(...), mapping: str | None = Form(None),
                         timezone_name: str | None = Form(None, alias="timezone")):
    """Upload -> mapping -> validation -> preview. Nothing is written to the
    business tables; the file, mapping and planned effects are stored so the
    commit is bound to exactly what was reviewed."""
    import json

    data = await _read_upload(file)
    try:
        mp = json.loads(mapping) if mapping else None
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "mapping must be a JSON object of field -> column") from exc
    try:
        return imports_service.dry_run(db_of(request), dataset, file.filename or "upload", data, mp, meta_of(request),
                                       naive_tz=timezone_name)
    except imports_service.ImportRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.post("/imports/{job_id}/commit", tags=["Data Sources and Imports"])
@exact
def import_commit(request: Request, job_id: str):
    """Commit a reviewed preview. Refused if the data changed since the preview."""
    try:
        return imports_service.commit(db_of(request), job_id, meta_of(request))
    except imports_service.ImportRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.get("/imports/{job_id}", tags=["Data Sources and Imports"])
@exact
def import_job(request: Request, job_id: str):
    db = db_of(request)
    job = db.one("import_job_get", id=job_id)
    if job is None:
        raise not_found("Import job")
    return {"job": job, "errors": db.all("import_errors", job=job_id), "effects": db.all("import_effects", job=job_id)[:500]}


@router.get("/imports/{job_id}/errors", tags=["Data Sources and Imports"])
@exact
def import_errors(request: Request, job_id: str):
    return {"items": db_of(request).all("import_errors", job=job_id)}


class ReverseIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/imports/{job_id}/reverse", tags=["Data Sources and Imports"])
@exact
def import_reverse(request: Request, job_id: str, body: ReverseIn):
    try:
        return imports_service.reverse(db_of(request), job_id, body.reason, meta_of(request))
    except imports_service.ImportRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


# ------------------------------------------------------------------ Settings
@router.get("/settings", tags=["Settings"])
@exact
def settings_view(request: Request):
    db = db_of(request)
    s = request.app.state.settings
    return {"release": request.app.state.release, "customer": s.customer_name, "reporting_timezone": s.reporting_timezone,
            "ai_kill_switch": db.scalar("flag_get", key="ai_kill_switch"), "budget": db.one("budget_current"),
            "schedules": db.all("schedules_list"), "queue": db.all("queue_stats"), "jobs": db.all("jobs_list2", status=None, limit=50),
            "models": db.all("model_versions"), "notifications": db.all("notifications_list", limit=20)}


class BudgetIn(BaseModel):
    cap_usd: Decimal = Field(ge=0)
    warn_at_usd: Decimal = Field(ge=0)
    per_run_cap_usd: Decimal = Field(ge=0)


@router.post("/settings/budget", tags=["Settings"])
@exact
def set_budget(request: Request, body: BudgetIn):
    db = db_of(request)
    db.run("budget_set", cap=body.cap_usd, warn=body.warn_at_usd, per_run=body.per_run_cap_usd)
    audit(db, "budget_changed", meta_of(request), detail={"cap_usd": str(body.cap_usd), "per_run_cap_usd": str(body.per_run_cap_usd)})
    return {"ok": True}


class KillIn(BaseModel):
    enabled: bool


@router.post("/settings/kill-switch", tags=["Settings"])
@exact
def kill_switch(request: Request, body: KillIn):
    db = db_of(request)
    db.run("flag_set", key="ai_kill_switch", value="true" if body.enabled else "false")  # JSON text, cast to jsonb
    audit(db, "kill_switch", meta_of(request), detail={"enabled": body.enabled})
    return {"ai_kill_switch": body.enabled}


class ScheduleIn(BaseModel):
    enabled: bool


@router.post("/settings/schedules/{sched_id}", tags=["Settings"])
@exact
def set_schedule(request: Request, sched_id: str, body: ScheduleIn):
    db = db_of(request)
    if db.scalar("schedule_set_enabled", id=sched_id, enabled=body.enabled) is None:
        raise not_found("Schedule")
    audit(db, "schedule_changed", meta_of(request), entity_type="schedule", entity_id=sched_id, detail={"enabled": body.enabled})
    return {"ok": True}


# /jobs/{job_id}/cancel lives in routes_discovery.py (it also cancels the job's discovery run).


# ------------------------------------------------------------------ Search
@router.get("/search", tags=["Search"])
@exact
def search(request: Request, q: str = Query(..., min_length=2, max_length=100)):
    return {"items": db_of(request).all("search", q=q)}
