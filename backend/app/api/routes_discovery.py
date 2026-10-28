"""Discovery, sources, schedules, jobs, review and reference-data API.

Every route sits behind AuthGateMiddleware (shared session + CSRF on
mutations). Errors are explicit HTTP errors with a reason; nothing fails
silently.
"""
from __future__ import annotations

import re

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..ai import extraction as ai
from ..domain import exports as ex
from ..reference.geography import COUNTRIES
from ..services import discovery as dsc
from ..services import review_service as rev
from ..services import sources_service as srcs
from ..services.audit import audit
from .common import db_of, exact, meta_of, not_found

router = APIRouter()
ModuleName = Literal["airline_representation", "account_growth", "forwarder_sales", "capacity_lanes", "service_operations",
                     "trucking_gateways", "outsourcing_training", "technology_solutions", "network_development"]


def _settings(request: Request):
    return request.app.state.settings


def _raise(exc: Exception) -> None:
    status = getattr(exc, "status", 400)
    raise HTTPException(status, getattr(exc, "detail", str(exc))) from exc


# ------------------------------------------------------------------ reference data
@router.get("/reference/geography", tags=["Discovery"])
@exact
def geography(request: Request):
    db = db_of(request)
    return {"countries": db.all("countries_list"), "regions": db.all("regions_list"), "members": db.all("region_members")}


class RegionIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,40}$")
    name: str = Field(min_length=2, max_length=120)
    countries: list[str] = Field(min_length=1, max_length=250)


@router.post("/reference/regions", tags=["Discovery"])
@exact
def add_region(request: Request, body: RegionIn):
    db = db_of(request)
    bad = [c for c in body.countries if c.upper() not in COUNTRIES]
    if bad:
        raise HTTPException(422, f"unknown country code(s): {', '.join(bad)}")
    with db.transaction() as tx:
        if tx.scalar("region_insert", code=body.code, name=body.name) is None:
            raise HTTPException(409, "region exists")
        for c in sorted({c.upper() for c in body.countries}):
            tx.run("region_add_country", region=body.code, country=c)
        audit(tx, "region_created", meta_of(request), entity_type="region", entity_id=body.code)
    return {"code": body.code}


@router.get("/reference/lookups", tags=["Discovery"])
@exact
def lookups(request: Request):
    db = db_of(request)
    return {"companies": db.all("operating_companies"), "services": db.all("services_list"), "airports": db.all("airports_brief"),
            "people": db.all("people_list", q=None, limit=500, offset=0)}


# ------------------------------------------------------------------ discovery
class SearchIn(BaseModel):
    geo_mode: Literal["country", "countries", "region", "worldwide"]
    countries: list[str] = Field(default_factory=list, max_length=250)
    regions: list[str] = Field(default_factory=list, max_length=50)
    modules: list[ModuleName] = Field(default_factory=list)
    organisation: str | None = Field(None, max_length=200)
    airline: str | None = Field(None, max_length=200)
    keywords: str | None = Field(None, max_length=300)
    date_from: date | None = None
    date_to: date | None = None
    # How a date-filtered search treats documents whose publication date is unknown (review §2).
    date_filter: Literal["include_unknown", "strict"] = "include_unknown"
    name: str | None = Field(None, max_length=200)
    save: bool = False
    run_now: bool = True


@router.get("/discovery/options", tags=["Discovery"])
@exact
def discovery_options(request: Request):
    db = db_of(request)
    s = _settings(request)
    per_doc = ai.estimate_per_document(s)
    return {"countries": db.all("countries_list"), "regions": db.all("regions_list"),
            "sources": [{"id": r["id"], "name": r["name"], "type": r["source_type"], "global": r["global_coverage"],
                         "countries": r["country_coverage"], "modules": r["modules"], "enabled": r["enabled"]}
                        for r in db.all("sources_list", kind="web")],
            "ai": {"connected": per_doc is not None, "detail": ai.available(s) or "connected",
                   "estimate_per_document_usd": per_doc, "kill_switch": db.scalar("flag_get", key="ai_kill_switch"),
                   "budget": db.one("budget_current")},
            "saved": db.all("searches_saved")}


@router.post("/discovery/searches", tags=["Discovery"])
@exact
def create_search(request: Request, body: SearchIn):
    db = db_of(request)
    try:
        sid = dsc.create_search(db, dsc.SearchSpec(body.geo_mode, body.countries, body.regions, list(body.modules), body.organisation,
                                                   body.airline, body.keywords, body.date_from, body.date_to, body.name, body.save,
                                                   date_filter=body.date_filter))
        run = dsc.start_run(db, _settings(request), search_id=sid) if body.run_now else None
    except dsc.DiscoveryRejected as exc:
        _raise(exc)
    audit(db, "discovery_search", meta_of(request), entity_type="discovery_search", entity_id=sid,
          detail={"geo_mode": body.geo_mode, "countries": body.countries, "regions": body.regions, "saved": body.save})
    return {"search_id": sid, "run": run}


@router.get("/discovery/searches", tags=["Discovery"])
@exact
def saved_searches(request: Request):
    return {"items": db_of(request).all("searches_saved")}


@router.post("/discovery/searches/{search_id}/run", tags=["Discovery"])
@exact
def run_search(request: Request, search_id: str):
    try:
        return dsc.start_run(db_of(request), _settings(request), search_id=search_id)
    except dsc.DiscoveryRejected as exc:
        _raise(exc)


class SaveIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


@router.post("/discovery/searches/{search_id}/save", tags=["Discovery"])
@exact
def save_search(request: Request, search_id: str, body: SaveIn):
    db = db_of(request)
    if db.scalar("search_save", id=search_id, name=body.name) is None:
        raise not_found("Search")
    audit(db, "discovery_search_saved", meta_of(request), entity_type="discovery_search", entity_id=search_id)
    return {"ok": True}


@router.delete("/discovery/searches/{search_id}", tags=["Discovery"])
@exact
def delete_search(request: Request, search_id: str):
    db = db_of(request)
    with db.transaction() as tx:
        if tx.scalar("search_delete", id=search_id) is None:
            raise not_found("Search")
        for s in tx.all("schedules_for_search", search=search_id):
            tx.run("schedule_set_enabled", id=str(s["id"]), enabled=False)
        audit(tx, "discovery_search_deleted", meta_of(request), entity_type="discovery_search", entity_id=search_id)
    return {"ok": True}


class ScheduleIn(BaseModel):
    interval_minutes: int = Field(ge=15, le=60 * 24 * 31)
    timezone: str = "Asia/Dubai"
    enabled: bool = True
    name: str | None = Field(None, max_length=200)


@router.post("/discovery/searches/{search_id}/schedule", tags=["Discovery"])
@exact
def schedule_search(request: Request, search_id: str, body: ScheduleIn):
    try:
        sid = srcs.create_schedule(db_of(request), search_id=search_id, source_id=None, interval_minutes=body.interval_minutes,
                                   timezone=body.timezone, enabled=body.enabled, name=body.name, meta=meta_of(request))
    except srcs.SourceRejected as exc:
        _raise(exc)
    return {"schedule_id": sid}


@router.get("/discovery/runs", tags=["Discovery"])
@exact
def runs(request: Request, search_id: str | None = None, source_id: str | None = None, limit: int = Query(30, ge=1, le=200)):
    return {"items": db_of(request).all("runs_list", search=search_id, source=source_id, limit=limit)}


@router.get("/discovery/runs/{run_id}", tags=["Discovery"])
@exact
def run_detail(request: Request, run_id: str):
    db = db_of(request)
    run = db.one("run_get", id=run_id)
    if run is None:
        raise not_found("Run")
    search = db.one("search_get", id=str(run["search_id"])) if run["search_id"] else None
    return {"run": run, "search": search, "sources": db.all("run_sources", run=run_id), "results": db.all("run_results", run=run_id),
            "job": db.one("job_get", id=str(run["job_id"])) if run["job_id"] else None}


def _dl_label(info: dict | None) -> str | None:
    from ..domain.deadlines import StatedDeadline
    d = StatedDeadline.from_json(info)
    return d.label() if d else None


@router.get("/discovery/runs/{run_id}/results.csv", tags=["Reports"])
@exact
def run_results_csv(request: Request, run_id: str):
    db = db_of(request)
    run = db.one("run_get", id=run_id)
    if run is None:
        raise not_found("Run")
    rows = db.all("run_results", run=run_id)
    headers = ["title", "classification", "freight_scope", "capability_area", "match", "geography_basis", "countries", "deadline_as_stated", "deadline_utc",
               "deadline_source_tz", "tender_status", "qualification_status", "best_authority", "independent_families", "gaps", "recommended_next_action", "is_new"]
    out = []
    for r in rows:
        m = r["match"]
        # A match withdrawn after a re-check stays on the run with its reason; its former geography is not shown as a current match.
        withdrawn = bool(m.get("withdrawn"))
        geography = [] if withdrawn else m.get("geography", [])
        out.append([r["title"], r["classification"], r.get("freight_scope") or "unclear", m.get("capability_area"),
                    f"withdrawn: {m.get('withdrawn_reason')}" if withdrawn else "current", m.get("geography_basis"),
                    "; ".join(f"{g['country']} ({g['role']})" for g in geography), _dl_label(m.get("deadline")), m.get("deadline_utc"),
                    m.get("deadline_source_tz"), r.get("tender_status") or m.get("tender_status") or "unknown", r["qualification_status"],
                    (m.get("confidence") or {}).get("best_authority"), (m.get("confidence") or {}).get("independent_families"),
                    "; ".join(m.get("gaps", [])), m.get("recommended_next_action"), r["is_new"]])
    plan = run["plan"] or {}
    note = (f"Discovery run {run_id}; countries={plan.get('countries')}; capability areas={plan.get('modules')}; "
            f"outcome={run['outcome']}; {plan.get('coverage_note', '')}")
    body = ex.to_csv(headers, out, scope_note=note, generated_at=str(run["finished_at"] or run["created_at"]))
    audit(db, "export", meta_of(request), entity_type="report", entity_id=f"discovery-run-{run_id}.csv", detail={"rows": len(out)})
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="atlas-discovery-{run_id[:8]}.csv"'})


@router.post("/discovery/runs/{run_id}/cancel", tags=["Discovery"])
@exact
def cancel_run(request: Request, run_id: str):
    db = db_of(request)
    if not dsc.cancel_run(db, run_id):
        raise HTTPException(409, "run not found or already finished")
    audit(db, "discovery_run_cancelled", meta_of(request), entity_type="discovery_run", entity_id=run_id)
    return {"ok": True}


@router.post("/discovery/runs/{run_id}/retry", tags=["Discovery"])
@exact
def retry_run(request: Request, run_id: str):
    try:
        return dsc.retry_run(db_of(request), _settings(request), run_id)
    except dsc.DiscoveryRejected as exc:
        _raise(exc)


@router.get("/discovery/searches/{search_id}/queue", tags=["Discovery"])
@exact
def search_queue(request: Request, search_id: str):
    """Relevant links this search has found but not yet read (queued), or given up after repeated failures."""
    db = db_of(request)
    if db.one("search_get", id=search_id) is None:
        raise not_found("Search")
    scope = f"search:{search_id}"
    return {"items": db.all("queue_list", scope=scope), "counts": db.one("queue_remaining", scope=scope)}


@router.post("/discovery/searches/{search_id}/queue/retry", tags=["Discovery"])
@exact
def retry_given_up_links(request: Request, search_id: str):
    db = db_of(request)
    if db.one("search_get", id=search_id) is None:
        raise not_found("Search")
    urls = [r["url"] for r in db.all("queue_retry_given_up", scope=f"search:{search_id}")]
    db.run("documents_reset_failures", urls=urls)     # a document whose section kept failing is tried again too
    audit(db, "discovery_queue_retry", meta_of(request), entity_type="discovery_search", entity_id=search_id, detail={"links": len(urls)})
    return {"requeued": len(urls)}


@router.post("/sources/{source_id}/queue/retry", tags=["Discovery"])
@exact
def retry_given_up_source_links(request: Request, source_id: str):
    """Single-source runs (no saved search) queue their links under the source."""
    db = db_of(request)
    urls = [r["url"] for r in db.all("queue_retry_given_up", scope=f"source:{source_id}")]
    db.run("documents_reset_failures", urls=urls)
    audit(db, "discovery_queue_retry", meta_of(request), entity_type="source", entity_id=source_id, detail={"links": len(urls)})
    return {"requeued": len(urls)}


@router.get("/signals/{signal_id}", tags=["Discovery"])
@exact
def signal_detail(request: Request, signal_id: str):
    db = db_of(request)
    s = db.one("signal_get", id=signal_id)
    if s is None:
        raise not_found("Signal")
    return {"signal": s, "geography": db.all("signal_geo", signal=signal_id), "evidence": db.all("signal_evidence_view", signal=signal_id),
            "opportunity_id": db.scalar("opportunity_by_signal", signal=signal_id)}


# ------------------------------------------------------------------ sources
class SourceIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    source_type: Literal["web_page", "listing", "rss", "search_template"]
    base_url: str = Field(min_length=8, max_length=2048)
    authority: Literal["unverified", "trade_press", "company_release", "official_portal"]
    family: str | None = Field(None, max_length=120)
    country_coverage: list[str] = Field(default_factory=list, max_length=250)
    global_coverage: bool = False
    language: str | None = Field(None, max_length=20)
    local_language_permitted: bool = True
    modules: list[ModuleName] = Field(default_factory=list)
    refresh_minutes: int | None = Field(None, ge=15, le=60 * 24 * 31)
    query_template: str | None = Field(None, max_length=2048)
    max_items: int = Field(20, ge=1, le=200)
    retention_permitted: bool = False
    authorisation_note: str | None = Field(None, max_length=1000)
    notes: str | None = Field(None, max_length=2000)
    enabled: bool = False

    def spec(self) -> srcs.SourceSpec:
        return srcs.SourceSpec(self.name, self.source_type, self.base_url, self.authority, self.family, self.country_coverage,
                               self.global_coverage, self.language, self.local_language_permitted, list(self.modules), self.refresh_minutes,
                               self.query_template, self.max_items, self.retention_permitted, self.authorisation_note, self.notes,
                               self.enabled)


@router.get("/sources", tags=["Data Sources and Imports"])
@exact
def list_sources(request: Request, kind: Literal["web", "import"] | None = None):
    return {"items": db_of(request).all("sources_list", kind=kind)}


@router.post("/sources", tags=["Data Sources and Imports"])
@exact
def create_source(request: Request, body: SourceIn):
    try:
        return {"id": srcs.create_source(db_of(request), body.spec(), meta_of(request))}
    except srcs.SourceRejected as exc:
        _raise(exc)


@router.get("/sources/{source_id}", tags=["Data Sources and Imports"])
@exact
def source_detail(request: Request, source_id: str):
    db = db_of(request)
    s = db.one("source_get", id=source_id)
    if s is None or s["deleted_at"] is not None:
        raise not_found("Source")
    s = dict(s)
    s["country_coverage"] = [c.strip() for c in (s.get("country_coverage") or [])]
    return {"source": s, "runs": db.all("source_runs", source=source_id, limit=30),
            "documents": db.all("source_documents_list", source=source_id, run=None, status=None, limit=100),
            "schedule": db.one("schedule_for_source", source=source_id)}


@router.put("/sources/{source_id}", tags=["Data Sources and Imports"])
@exact
def update_source(request: Request, source_id: str, body: SourceIn):
    try:
        srcs.update_source(db_of(request), source_id, body.spec(), meta_of(request))
    except srcs.SourceRejected as exc:
        _raise(exc)
    return {"ok": True}


class EnableIn(BaseModel):
    enabled: bool


@router.post("/sources/{source_id}/enabled", tags=["Data Sources and Imports"])
@exact
def enable_source(request: Request, source_id: str, body: EnableIn):
    try:
        srcs.set_enabled(db_of(request), source_id, body.enabled, meta_of(request))
    except srcs.SourceRejected as exc:
        _raise(exc)
    return {"ok": True}


@router.delete("/sources/{source_id}", tags=["Data Sources and Imports"])
@exact
def retire_source(request: Request, source_id: str):
    try:
        srcs.retire_source(db_of(request), source_id, meta_of(request))
    except srcs.SourceRejected as exc:
        _raise(exc)
    return {"ok": True}


@router.post("/sources/{source_id}/run", tags=["Data Sources and Imports"])
@exact
def run_source(request: Request, source_id: str):
    db = db_of(request)
    try:
        r = dsc.start_run(db, _settings(request), source_id=source_id)
    except dsc.DiscoveryRejected as exc:
        _raise(exc)
    audit(db, "source_run_requested", meta_of(request), entity_type="source", entity_id=source_id)
    return r


# ------------------------------------------------------------------ schedules and jobs
class ScheduleCreate(ScheduleIn):
    search_id: str | None = None
    source_id: str | None = None


@router.get("/schedules", tags=["Settings"])
@exact
def schedules(request: Request):
    return {"items": db_of(request).all("schedules_list")}


@router.post("/schedules", tags=["Settings"])
@exact
def create_schedule(request: Request, body: ScheduleCreate):
    try:
        return {"id": srcs.create_schedule(db_of(request), search_id=body.search_id, source_id=body.source_id,
                                           interval_minutes=body.interval_minutes, timezone=body.timezone, enabled=body.enabled,
                                           name=body.name, meta=meta_of(request))}
    except srcs.SourceRejected as exc:
        _raise(exc)


@router.put("/schedules/{schedule_id}", tags=["Settings"])
@exact
def update_schedule(request: Request, schedule_id: str, body: ScheduleIn):
    try:
        srcs.update_schedule(db_of(request), schedule_id, interval_minutes=body.interval_minutes, timezone=body.timezone,
                             enabled=body.enabled, name=body.name, meta=meta_of(request))
    except srcs.SourceRejected as exc:
        _raise(exc)
    return {"ok": True}


@router.get("/jobs", tags=["Settings"])
@exact
def jobs(request: Request, status: str | None = None, limit: int = Query(50, ge=1, le=200)):
    db = db_of(request)
    return {"items": db.all("jobs_list2", status=status, limit=limit), "queue": db.all("queue_stats")}


@router.post("/jobs/{job_id}/cancel", tags=["Settings"])
@exact
def cancel_job(request: Request, job_id: str):
    """Cancel a queued or running job. A running worker sees the cancellation
    at its next checkpoint; a discovery run is cancelled with its job."""
    db = db_of(request)
    job = db.one("job_get", id=job_id)
    if job is None:
        raise not_found("Job")
    run = db.scalar("run_by_job", job=job_id)
    ok = dsc.cancel_run(db, str(run)) if run is not None else db.scalar("job_cancel", job=job_id) is not None
    if not ok:
        raise HTTPException(409, f"only queued or running jobs can be cancelled (job is {job['status']})")
    audit(db, "job_cancelled", meta_of(request), entity_type="job", entity_id=job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/retry", tags=["Settings"])
@exact
def retry_job(request: Request, job_id: str):
    db = db_of(request)
    job = db.one("job_get", id=job_id)
    if job is None:
        raise not_found("Job")
    if job["status"] not in ("dead", "failed", "cancelled"):
        raise HTTPException(409, f"only dead, failed or cancelled jobs can be retried (job is {job['status']})")
    run = db.scalar("run_by_job", job=job_id)
    if run is not None:
        try:
            return dsc.retry_run(db, _settings(request), str(run))
        except dsc.DiscoveryRejected as exc:
            _raise(exc)
    n = int(db.scalar("job_retry_count", id=job_id) or 0) + 1
    new = db.scalar("job_enqueue2", job_type=job["job_type"], key=f"retry:{job_id}:{n}", schedule=None, payload=job["payload"] or {},
                    retry_of=job_id)
    audit(db, "job_retried", meta_of(request), entity_type="job", entity_id=job_id)
    return {"job_id": str(new)}


# ------------------------------------------------------------------ review
@router.get("/review", tags=["Review"])
@exact
def review_queue(request: Request, limit: int = Query(100, ge=1, le=500)):
    db = db_of(request)
    return {"documents": db.all("review_documents", limit=limit), "claims": db.all("review_claims", limit=limit),
            "fields": db.all("review_fields", limit=limit),
            "rejections": db.all("review_rejections", limit=limit), "merges": db.all("review_merges", limit=limit),
            "conflicts": db.all("review_conflicts", limit=limit)}


@router.get("/documents/{doc_id}", tags=["Review"])
@exact
def document_detail(request: Request, doc_id: str):
    db = db_of(request)
    d = db.one("document_review_get", id=doc_id)
    if d is None:
        raise not_found("Document")
    text = d.pop("body_text", None) or d.get("excerpt") or ""
    d["text"] = text
    d["text_is_excerpt"] = not bool(db.scalar("document_has_body", id=doc_id))
    return {"document": d, "checks": db.all("document_checks", id=doc_id), "claims": db.all("document_claims", id=doc_id),
            "rejections": db.all("document_rejections", id=doc_id)}


@router.get("/documents/{doc_id}/passage", tags=["Review"])
@exact
def document_passage(request: Request, doc_id: str, quote: str | None = None, location: str | None = None, context: int = 400):
    """The evidence passage in the document's own text, for inspection: the quote located by its recorded position
    ("page p, chars a-b") or by searching the text, with the surrounding context. Reports when the text is not retained
    (only the stored excerpt remains) or when the quote cannot be found in the current text version."""
    from ..domain import sections as sec

    db = db_of(request)
    d = db.one("document_passage_source", id=doc_id)
    if d is None:
        raise not_found("Document")
    text = d.get("body_text") or ""
    retained = bool(text)
    if not retained:
        text = d.get("excerpt") or ""
    context = max(0, min(int(context), 4000))
    span: tuple[int, int] | None = None
    how = None
    m = re.search(r"chars (\d+)-(\d+)", location or "")
    if m and retained:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a < b <= len(text) and (not quote or re.sub(r"\s+", " ", text[a:b]).strip() == re.sub(r"\s+", " ", quote).strip()):
            span, how = (a, b), "recorded location"
    if span is None and quote:
        found = sec.locate_quote(text, quote)
        if found:
            span, how = found, "found in the text" + ("" if retained else " (stored excerpt only)")
    if span is None:
        return {"document_id": doc_id, "found": False, "text_retained": retained, "document_version": d.get("content_hash"),
                "retrieved_at": d.get("retrieved_at"), "canonical_url": d.get("canonical_url"),
                "detail": "the quote was not found in the retained text" if retained else "the full text is not retained for this source; only the stored excerpt is available"}
    a, b = span
    page = None
    starts = (d.get("read_progress") or {}).get("page_starts") or []
    if starts:
        page = sum(1 for st in starts if st <= a)
    return {"document_id": doc_id, "found": True, "how": how, "text_retained": retained, "document_version": d.get("content_hash"),
            "retrieved_at": d.get("retrieved_at"), "canonical_url": d.get("canonical_url"), "start": a, "end": b, "page": page,
            "before": text[max(0, a - context):a], "passage": text[a:b], "after": text[b:b + context]}


class FieldIn(BaseModel):
    value: str = Field(max_length=2000)
    quote: str | None = Field(None, max_length=2000)


class ClaimIn(BaseModel):
    claim_type: Literal["route_launch", "route_suspension", "gssa_tender", "tender_deadline", "tender_scope", "tender_status",
                        "representation_change", "tcm_signal", "capacity_statement", "partnership", "eligibility", "service_tender"]
    quote: str = Field(min_length=8, max_length=2000)
    stance: Literal["supports", "contradicts"] = "supports"
    deadline_timezone: str | None = Field(None, max_length=60)
    fields: dict[str, FieldIn] = Field(default_factory=dict)


@router.post("/documents/{doc_id}/claims", tags=["Review"])
@exact
def add_claim(request: Request, doc_id: str, body: ClaimIn):
    try:
        return rev.add_claim(db_of(request), doc_id, claim_type=body.claim_type, quote=body.quote,
                             fields={k: v.model_dump() for k, v in body.fields.items()}, stance=body.stance,
                             deadline_timezone=body.deadline_timezone, meta=meta_of(request), settings=_settings(request))
    except rev.ReviewRejected as exc:
        _raise(exc)


class ExtractIn(BaseModel):
    # Explicit renewed approval when the document's discovery run has reached its approved AI ceiling.
    approve_additional_usd: Decimal | None = Field(None, gt=0, le=100)


@router.post("/documents/{doc_id}/extract", tags=["Review"])
@exact
def extract_document(request: Request, doc_id: str, body: ExtractIn | None = None):
    try:
        return rev.extract_document(db_of(request), _settings(request), doc_id, meta_of(request),
                                    approve_additional_usd=body.approve_additional_usd if body else None)
    except rev.ReviewRejected as exc:
        _raise(exc)


class NoteIn(BaseModel):
    note: str = Field(min_length=0, max_length=2000, default="")


@router.post("/claims/{claim_id}/confirm", tags=["Review"])
@exact
def confirm_claim(request: Request, claim_id: str, body: NoteIn):
    try:
        return rev.confirm_claim(db_of(request), claim_id, body.note or None, meta_of(request))
    except rev.ReviewRejected as exc:
        _raise(exc)


@router.post("/claims/{claim_id}/reject", tags=["Review"])
@exact
def reject_claim(request: Request, claim_id: str, body: NoteIn):
    try:
        return rev.reject_claim(db_of(request), claim_id, body.note, meta_of(request))
    except rev.ReviewRejected as exc:
        _raise(exc)


class CorrectIn(BaseModel):
    document_id: str
    claim_type: str | None = None
    quote: str | None = Field(None, max_length=2000)
    fields: dict[str, FieldIn] = Field(default_factory=dict)
    note: str = Field(min_length=5, max_length=2000)


@router.post("/claims/{claim_id}/correct", tags=["Review"])
@exact
def correct_claim(request: Request, claim_id: str, body: CorrectIn):
    try:
        return rev.correct_claim(db_of(request), claim_id, document_id=body.document_id, claim_type=body.claim_type, quote=body.quote,
                                 fields={k: v.model_dump() for k, v in body.fields.items()}, note=body.note, meta=meta_of(request),
                                 settings=_settings(request))
    except rev.ReviewRejected as exc:
        _raise(exc)


class ResolveIn(BaseModel):
    status: Literal["resolved", "dismissed"]
    note: str = Field(min_length=3, max_length=1000)


@router.post("/rejections/{rejection_id}/resolve", tags=["Review"])
@exact
def resolve_rejection(request: Request, rejection_id: str, body: ResolveIn):
    try:
        rev.resolve_rejection(db_of(request), rejection_id, body.status, body.note, meta_of(request))
    except rev.ReviewRejected as exc:
        _raise(exc)
    return {"ok": True}


class ProposeMergeIn(BaseModel):
    opportunity_id: str
    other_opportunity_id: str
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/merge-candidates", tags=["Review"])
@exact
def propose_merge(request: Request, body: ProposeMergeIn):
    try:
        return rev.propose_merge(db_of(request), body.opportunity_id, body.other_opportunity_id, body.reason, meta_of(request))
    except rev.ReviewRejected as exc:
        _raise(exc)


class MergeIn(BaseModel):
    decision: Literal["merged", "kept_separate"]
    note: str = Field(min_length=5, max_length=1000)


@router.post("/merge-candidates/{candidate_id}/decide", tags=["Review"])
@exact
def decide_merge(request: Request, candidate_id: str, body: MergeIn):
    try:
        return rev.decide_merge(db_of(request), candidate_id, body.decision, body.note, meta_of(request))
    except rev.ReviewRejected as exc:
        _raise(exc)

