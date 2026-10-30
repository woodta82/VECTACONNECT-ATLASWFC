"""One workspace (30 Oct 2026): the global airport directory, the Dashboard, staged research and the research file, company
duplicate review and merges. Behind the shared session like every business route."""
from __future__ import annotations

import functools
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from ..services import airport_directory as ad
from ..services import company_intelligence as cmp
from ..services import dashboard as dash
from ..services import deep_research as dr
from ..services.audit import audit
from .common import db_of, exact, meta_of

router = APIRouter()


def _translate(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except (ad.DirectoryRejected, cmp.CompanyRejected, dr.ResearchRejected) as exc:
            raise HTTPException(exc.status, exc.detail) from exc
    return wrapper


# ------------------------------------------------------------------ airport directory
@router.get("/airports", tags=["Reference"])
@exact
def airports(request: Request, q: str | None = None, country: str | None = None, include_closed: bool = False, limit: int = Query(20, ge=1, le=100)):
    """Search the global airport directory by name, IATA code, ICAO code, city or country (airports without an IATA code included)."""
    return {"items": ad.search(db_of(request), q, country=country, include_closed=include_closed, limit=limit)}


@router.get("/airports/status", tags=["Reference"])
@exact
def airports_status(request: Request):
    """Which dataset is loaded, its provenance and refresh date."""
    return ad.status(db_of(request))


@router.get("/airports/{code}", tags=["Reference"])
@exact
def airport(request: Request, code: str):
    a = ad.resolve(db_of(request), code)
    if a is None:
        raise HTTPException(404, f"{code.upper()} is not in the airport directory (kept as written where it was found)")
    return {**a, "label": ad.label(a)}


@router.post("/airports/load", tags=["Reference"])
@exact
async def airports_load(request: Request, file: UploadFile = File(...), version: str | None = Form(None), refreshed_at: str | None = Form(None),
                        notes: str | None = Form(None)):
    """Load or refresh the maintained dataset from OurAirports' airports.csv (upload, for servers without outbound access)."""
    data = await file.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(413, "File too large (64 MB at most)")
    when = None
    if refreshed_at:
        try:
            when = datetime.fromisoformat(refreshed_at)
        except ValueError as exc:
            raise HTTPException(422, "refreshed_at must be an ISO date") from exc
    try:
        out = ad.load_ourairports(db_of(request), data.decode("utf-8", "replace"), version=version, refreshed_at=when, notes=notes)
    except ad.DirectoryRejected as exc:
        ad.record_attempt(db_of(request), ok=False, source=f"upload ({file.filename})", detail=exc.detail)
        raise HTTPException(exc.status, exc.detail) from exc
    ad.record_attempt(db_of(request), ok=True, source=f"upload ({file.filename})", detail=f"{out['rows']} rows loaded")
    audit(db_of(request), "airport_directory_loaded", meta_of(request), entity_type="reference_dataset", entity_id=None,
          detail={"rows": out["rows"], "version": version, "filename": file.filename})
    return out


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard", tags=["Overview"])
@exact
def dashboard(request: Request, countries: str | None = None, region: str | None = None, airports: str | None = None, modules: str | None = None,
              org: str | None = None, tender: str | None = None, progress: str | None = None, coverage: str | None = None, types: str | None = None,
              deadline_days: int | None = Query(None, ge=1, le=730)):
    """The first screen: what deserves attention, what changed, who is relevant, what to do next. `airports`: comma-separated directory
    idents or codes; records are kept when the opportunity or one of its organisations names one of them."""
    from .routes_intel import _records, _scope
    db = db_of(request)
    ranked = _records(request, countries=countries, region=region, modules=modules, org=org, tender=tender, progress=progress, coverage=coverage, types=types,
                      deadline_days=deadline_days)
    chosen: list[dict] = []
    if airports:
        found, _missing = ad.resolve_many(db, [a for a in airports.split(",") if a.strip()])
        chosen = [{"ident": a["ident"], "label": ad.label(a)} for a in found]
        if found:
            keep = {str(r["opportunity_id"]) for r in db.all("opps_with_airports", idents=[a["ident"] for a in found])}
            ranked = [r for r in ranked if str(r["id"]) in keep]
    scope = _scope(countries, region) + (f" · airports {', '.join(a['label'] for a in chosen)}" if chosen else "")
    link_query = {"countries": countries or "", "region": region or "", "airports": airports or "", "modules": modules or "", "org": org or ""}
    return dash.build(db, ranked, scope=scope, airports=chosen, link_query=link_query)


# ------------------------------------------------------------------ staged research
class ResearchIn(BaseModel):
    stages: list[Literal["identify", "identity", "company", "people", "relationships", "relevance"]] | None = None
    brief: str | None = Field(None, max_length=600)


@router.post("/opportunities/{opp_id}/deep-research", tags=["Research"])
@exact
@_translate
def opportunity_deep_research(request: Request, opp_id: str, body: ResearchIn | None = None):
    """Staged, resumable research of an opportunity: identify → official identity → company → people → relationships → relevance.
    Enriches the opportunity's companies and people; resumes at the first stage not done."""
    st = request.app.state
    return dr.run(db_of(request), st.settings, "opportunity", opp_id, meta_of(request), stages=(body.stages if body else None),
                  fetch=getattr(st, "fetch", None), transport=getattr(st, "ai_transport", None), search_transport=getattr(st, "search_transport", None))


def _kw(request: Request) -> dict:
    st = request.app.state
    return {"fetch": getattr(st, "fetch", None), "transport": getattr(st, "ai_transport", None), "search_transport": getattr(st, "search_transport", None)}


@router.post("/opportunities/{opp_id}/deep-research/retry-failed", tags=["Research"])
@exact
@_translate
def opportunity_retry_failed(request: Request, opp_id: str):
    """Retry only the organisations whose research failed (and stages that failed outright). Completed work is not repeated."""
    return dr.retry_failed(db_of(request), request.app.state.settings, "opportunity", opp_id, meta_of(request), **_kw(request))


@router.post("/companies/{org_id}/deep-research/retry-failed", tags=["Research"])
@exact
@_translate
def company_retry_failed(request: Request, org_id: str):
    return dr.retry_failed(db_of(request), request.app.state.settings, "organisation", org_id, meta_of(request), **_kw(request))


@router.post("/companies/{org_id}/deep-research", tags=["Research"])
@exact
@_translate
def company_deep_research(request: Request, org_id: str, body: ResearchIn | None = None):
    """Staged research of a company: official identity (website, contact page), company pages, people, relationships."""
    st = request.app.state
    return dr.run(db_of(request), st.settings, "organisation", org_id, meta_of(request), stages=(body.stages if body else None),
                  fetch=getattr(st, "fetch", None), transport=getattr(st, "ai_transport", None), search_transport=getattr(st, "search_transport", None))


@router.get("/opportunities/{opp_id}/research-file", tags=["Research"])
@exact
@_translate
def research_file(request: Request, opp_id: str):
    """The complete research file of an opportunity: a concise summary first, supporting research below, every gap explicit."""
    return dr.research_file(db_of(request), opp_id)


@router.get("/research-stages/{entity_type}/{entity_id}", tags=["Research"])
@exact
def research_stages(request: Request, entity_type: Literal["opportunity", "organisation", "person"], entity_id: str):
    return {"stages": dr.stages(db_of(request), entity_type, entity_id), "queue": dr.queue_items(db_of(request), entity_type, entity_id),
            "progress": dr.progress(db_of(request), entity_type, entity_id)}


# ------------------------------------------------------------------ company duplicates and merges
@router.get("/companies/duplicates", tags=["Companies"])
@exact
def company_duplicates(request: Request, status: Literal["open", "dismissed", "merged"] | None = "open"):
    return {"items": cmp.duplicates(db_of(request), status)}


class DupNoteIn(BaseModel):
    note: str | None = Field(None, max_length=500)


@router.post("/companies/duplicates/{dup_id}/dismiss", tags=["Companies"])
@exact
@_translate
def company_duplicate_dismiss(request: Request, dup_id: str, body: DupNoteIn):
    cmp.dismiss_duplicate(db_of(request), dup_id, body.note, meta_of(request))
    return {"ok": True}


class MergeIn(BaseModel):
    keep_id: str
    merge_id: str
    note: str | None = Field(None, max_length=500)
    duplicate_id: str | None = None


@router.post("/companies/merge", tags=["Companies"])
@exact
@_translate
def company_merge(request: Request, body: MergeIn):
    """Merge two company records a person has judged to be the same: every piece of evidence, contact, relationship, person and
    opportunity is re-pointed to the kept record; reversible."""
    return {"merge_id": cmp.merge(db_of(request), body.keep_id, body.merge_id, body.note, meta_of(request), duplicate_id=body.duplicate_id)}


@router.post("/companies/merges/{merge_id}/undo", tags=["Companies"])
@exact
@_translate
def company_merge_undo(request: Request, merge_id: str):
    cmp.undo_merge(db_of(request), merge_id, meta_of(request))
    return {"ok": True}

