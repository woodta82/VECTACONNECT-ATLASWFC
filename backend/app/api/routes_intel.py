"""Overview, opportunity records, relationship research and the light workspace (28 Oct 2026 refocus)."""
from __future__ import annotations

import functools
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..domain import control_panel as cp
from ..domain import exports as ex
from ..domain import overview as ov
from ..domain import relationships as rel
from ..reference.geography import COUNTRIES
from ..services import relationship_service as rs
from .common import db_of, exact, meta_of, not_found
from .routes import _geo

router = APIRouter()
MAX_RECORDS = 1000


def _translate(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except rs.RelationshipRejected as exc:
            raise HTTPException(exc.status, exc.detail) from exc
    return wrapper


def _csv_list(v: str | None) -> list[str] | None:
    items = [x.strip() for x in (v or "").split(",") if x.strip()]
    return items or None


def _records(request: Request, *, types=None, modules=None, countries=None, region=None, tender=None, progress=None, coverage=None,
             org=None, q=None, deadline_days=None, saved=None, since=None, sort="priority", limit=MAX_RECORDS, offset=0) -> list[dict[str, Any]]:
    db = db_of(request)
    geo = _geo(db, countries, region)
    rows = db.all("records_list", types=_csv_list(types), modules=_csv_list(modules), geo=geo, tender=_csv_list(tender),
                  progress=_csv_list(progress), coverage=_csv_list(coverage), org=org or None, q=q or None, deadline_days=deadline_days,
                  saved=saved, since=since, id=None, sort="created" if sort == "priority" else sort, limit=limit, offset=offset)
    for r in rows:
        r.pop("total", None)
        r["countries_named"] = [COUNTRIES.get(c, (c,))[0] for c in (r.get("countries") or [])]
        r["category"] = ov.CATEGORY_LABELS.get(r["module"], r["module"])
        r["record_type_label"] = ov.RECORD_TYPE_LABELS.get(r["record_type"], r["record_type"])
        r["tender_status_label"] = ov.TENDER_STATUS_LABELS.get(r.get("tender_status") or "", None)
        r["coverage_label"] = rel.COVERAGE_LABELS.get(r["coverage"], r["coverage"])
    if sort == "priority":
        rows = ov.rank(rows)
    else:
        for r in rows:
            r["priority_reason"] = ov.priority(r)[1]
            r["review_state"] = ov.review_state(r)
    return rows


def _scope(countries: str | None, region: str | None) -> str:
    if region:
        return f"Region {region.upper()}"
    if countries:
        return "Countries " + ", ".join(c.strip().upper() for c in countries.split(",") if c.strip())
    return "Worldwide"


# ------------------------------------------------------------------ Overview
@router.get("/overview", tags=["Overview"])
@exact
def overview(request: Request, countries: str | None = None, region: str | None = None, modules: str | None = None,
             org: str | None = None, tender: str | None = None, progress: str | None = None, coverage: str | None = None,
             types: str | None = None, deadline_days: int | None = Query(None, ge=1, le=730)):
    db = db_of(request)
    common = {"countries": countries, "region": region, "modules": modules, "org": org, "tender": tender, "progress": progress,
              "coverage": coverage, "types": types}
    ranked = _records(request, **common, deadline_days=deadline_days)
    now = datetime.now(timezone.utc)
    week = now - timedelta(days=14)
    # Live = still actionable: not historical or excluded, not closed by the team, and no terminal tender status (a cancelled,
    # awarded, closed or expired tender keeps its record and relationship history, but leaves the live lists).
    live = [r for r in ranked if r["record_type"] not in ("historical", "excluded") and r.get("progress") != "closed"
            and (r.get("tender_status") or "") not in ov.TERMINAL]
    def at(v: Any) -> datetime:
        return ov._as_dt(v) or datetime.min.replace(tzinfo=timezone.utc)
    recent = sorted([r for r in ranked if r["record_type"] != "excluded" and at(r["created_at"]) >= week],
                    key=lambda r: at(r["created_at"]), reverse=True)[:10]
    upcoming = sorted([r for r in live if r.get("deadline_at") and at(r["deadline_at"]) >= now], key=lambda r: at(r["deadline_at"]))[:10]
    needing = [r for r in live if r["kind"] == "opportunity" and r["coverage"] in ("none", "candidates_only")][:10]
    covered = [r for r in live if r["coverage"] in ("existing_relationship", "introduction_available")][:10]
    counts = {t: sum(1 for r in ranked if r["record_type"] == t) for t in ("tender", "commercial", "market_signal", "historical")}
    return {"scope": _scope(countries, region), "filters": {k: v for k, v in common.items() if v} | ({"deadline_days": deadline_days} if deadline_days else {}),
            "counts": counts, "priority": live[:10], "recent": recent, "upcoming_deadlines": upcoming, "needs_research": needing,
            "with_relationships": covered, "people_recent": [dict(p, state_label=rel.STATE_LABELS[p["state"]]) for p in db.all("overview_people_recent", limit=8)],
            "saved_searches": db.all("overview_saved_searches"), "recent_changes": db.all("overview_changes", limit=12),
            "rule": ov.RULE, "generated_at": now}


# ------------------------------------------------------------------ Control panel (29 Oct 2026)
@router.get("/control-panel", tags=["Overview"])
@exact
def control_panel(request: Request, countries: str | None = None, region: str | None = None, modules: str | None = None,
                  org: str | None = None, tender: str | None = None, progress: str | None = None, coverage: str | None = None,
                  types: str | None = None, deadline_days: int | None = Query(None, ge=1, le=730)):
    """Live opportunities per market (UN M49 region, sub-region and country) and per capability area, with the opportunity score
    out of 100 and its breakdown. The score is a provisional points score, not a probability of winning."""
    common = {"countries": countries, "region": region, "modules": modules, "org": org, "tender": tender, "progress": progress,
              "coverage": coverage, "types": types}
    ranked = _records(request, **common, deadline_days=deadline_days)
    now = datetime.now(timezone.utc)
    out = cp.build(ranked, COUNTRIES.get, now)
    return {"scope": _scope(countries, region),
            "filters": {k: v for k, v in common.items() if v} | ({"deadline_days": deadline_days} if deadline_days else {}),
            **out, "generated_at": now}


# ------------------------------------------------------------------ Opportunity records (all record types)
@router.get("/records", tags=["Opportunities"])
@exact
def records(request: Request, countries: str | None = None, region: str | None = None, modules: str | None = None, org: str | None = None,
            tender: str | None = None, progress: str | None = None, coverage: str | None = None, types: str | None = None,
            q: str | None = None, deadline_days: int | None = Query(None, ge=1, le=730), saved: bool | None = None,
            sort: Literal["priority", "deadline", "source_date"] = "priority", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = _records(request, countries=countries, region=region, modules=modules, org=org, tender=tender, progress=progress, coverage=coverage,
                    types=types, q=q, deadline_days=deadline_days, saved=saved, sort=sort)
    return {"items": rows[offset: offset + limit], "total": len(rows), "limit": limit, "offset": offset, "scope": _scope(countries, region),
            "rule": ov.RULE if sort == "priority" else None}


@router.get("/records/export.csv", tags=["Opportunities"])
def records_export(request: Request, countries: str | None = None, region: str | None = None, modules: str | None = None,
                   org: str | None = None, tender: str | None = None, progress: str | None = None, coverage: str | None = None,
                   types: str | None = None, q: str | None = None, saved: bool | None = None):
    db = db_of(request)
    rows = _records(request, countries=countries, region=region, modules=modules, org=org, tender=tender, progress=progress,
                    coverage=coverage, types=types, q=q, saved=saved)
    out = []
    for r in rows:
        gaps: list[str] = []
        people: list[str] = []
        if r["kind"] == "opportunity":
            rr = rs.opportunity_relationships(db, str(r["id"]))
            gaps = rr["gaps"]
            people = [f"{p['full_name']} ({p.get('role_title') or 'role not established'}, {p['state_label']})"
                      for p in rr["people"] if p.get("link_status") != "not_relevant"]
        out.append([r["priority_rank"] if "priority_rank" in r else "", r["record_type_label"], r["title"], r.get("organisation") or "",
                    ", ".join(r["countries_named"]), r["category"], r.get("source_date") or "", r.get("deadline_utc") or "",
                    r.get("tender_status_label") or "", ov.PROGRESS_LABELS.get(r.get("progress") or "", ""), r["priority_reason"],
                    r["coverage_label"], "; ".join(people), "; ".join(gaps), r.get("next_action") or "", r.get("owner_label") or ""])
    csv = ex.to_csv(["Priority", "Record type", "Title", "Organisation", "Countries", "Category", "Source date", "Stated deadline (UTC)",
                     "Tender status", "Progress", "Priority explanation", "Relationship coverage", "Relevant people", "Relationship gaps",
                     "Next action", "Owner"], out, scope_note=_scope(countries, region), generated_at=datetime.now(timezone.utc).isoformat())
    return Response(csv, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="atlas-opportunities.csv"'})


@router.get("/records/signals/{signal_id}", tags=["Opportunities"])
@exact
def signal_record(request: Request, signal_id: str):
    db = db_of(request)
    s = db.one("record_signal_get", id=signal_id)
    if s is None:
        raise not_found("Record")
    geo = db.all("record_signal_geo", id=signal_id)
    names = sorted({g["name"] for g in geo if g["support"] == "supported"})
    rec = dict(s, organisation=None, tender_status=(s.get("tender_state") or {}).get("status"))
    return {"record": s, "geography": geo, "evidence": db.all("signal_evidence_view", signal=signal_id),
            "interpretation": ov.interpretation(rec, names)}


@router.post("/records/signals/{signal_id}/track", tags=["Opportunities"])
@exact
@_translate
def track(request: Request, signal_id: str):
    return {"opportunity_id": rs.track_signal(db_of(request), signal_id, meta_of(request))}


# ------------------------------------------------------------------ Opportunity: understanding + relationships
def _intelligence(db, opp_id: str) -> dict[str, Any]:
    o = db.one("opportunity_get2", id=opp_id)
    if o is None:
        raise not_found("Opportunity")
    geo = db.all("opportunity_geo", id=opp_id)
    names = sorted({g["name"] for g in geo if g["support"] in ("supported", "internal_record")})
    rec = db.all("records_list", types='["tender","commercial"]', modules=None, geo=None, tender=None, progress=None, coverage=None, org=None,
                 q=None, deadline_days=None, saved=None, since=None, id=opp_id, sort="created", limit=1, offset=0)
    record = rec[0] if rec else dict(o, coverage="none", reviewed_claims=0)
    record["gaps"] = o.get("gaps") or []
    return {"opportunity": o, "interpretation": ov.interpretation(record, names), "priority_reason": ov.priority(record)[1],
            "review_state": ov.review_state(record), "relationships": rs.opportunity_relationships(db, opp_id),
            "notes": db.all("ws_notes", id=opp_id),
            "workspace": {"progress": o["progress"], "progress_label": ov.PROGRESS_LABELS[o["progress"]], "closed_reason": o.get("closed_reason"),
                          "saved": o.get("saved_at") is not None, "owner_label": o.get("owner_label"), "next_action": o.get("next_action"),
                          "next_action_due": o.get("next_action_due"), "record_type": o["record_type"],
                          "record_type_label": ov.RECORD_TYPE_LABELS[o["record_type"]],
                          "tender_status": o.get("tender_status"), "tender_status_label": ov.TENDER_STATUS_LABELS.get(o.get("tender_status") or "", None)}}


@router.get("/opportunities/{opp_id}/intelligence", tags=["Opportunities"])
@exact
@_translate
def opportunity_intelligence(request: Request, opp_id: str):
    out = _intelligence(db_of(request), opp_id)
    out.pop("opportunity")
    return out


class ResearchIn(BaseModel):
    mode: Literal["start", "continue"] = "start"


@router.post("/opportunities/{opp_id}/research", tags=["Relationships"])
@exact
@_translate
def research(request: Request, opp_id: str, body: ResearchIn | None = None):
    """Start relationship research (queue the opportunity's documents, organisation pages and authorised searches, then read),
    or continue it (read what remains). The result states whether research is complete or incomplete, and why."""
    return rs.research(db_of(request), request.app.state.settings, opp_id, meta_of(request), mode=(body.mode if body else "start"))


class ResearchSourceIn(BaseModel):
    url: str | None = Field(None, max_length=1000, pattern=r"^https?://[^\s]+$")
    title: str | None = Field(None, max_length=300)
    text: str | None = Field(None, max_length=400_000)
    organisation_id: str | None = None


@router.post("/opportunities/{opp_id}/research/sources", tags=["Relationships"])
@exact
@_translate
def research_source(request: Request, opp_id: str, body: ResearchSourceIn):
    """Add a relevant URL or the text of a document to this opportunity's research. It is read at the next research run."""
    rid = rs.add_research_source(db_of(request), opp_id, url=body.url, title=body.title, text=body.text, meta=meta_of(request),
                                 organisation_id=body.organisation_id)
    return {"id": rid}


@router.post("/opportunities/{opp_id}/research/documents", tags=["Relationships"])
@exact
async def research_document(request: Request, opp_id: str, file: UploadFile = File(...), title: str | None = Form(None)):
    """Add a document file (PDF, HTML or plain text) to this opportunity's research."""
    from ..domain import content as ct
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (5 MB at most)")
    name = (file.filename or "document").lower()
    ctype = ("application/pdf" if name.endswith(".pdf") else "text/html" if name.endswith((".html", ".htm"))
             else "text/plain" if name.endswith((".txt", ".md")) else None)
    if ctype is None:
        raise HTTPException(415, "Only PDF, HTML and plain-text documents can be read")
    try:
        text = ct.extract(data, ctype, "https://document.invalid/").text
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"The document could not be read: {str(exc)[:120]}") from exc
    if not text.strip():
        raise HTTPException(422, "The document has no readable text (a scanned image needs text recognition first)")
    try:
        rid = rs.add_research_source(db_of(request), opp_id, url=None, title=title or file.filename, text=text, meta=meta_of(request))
    except rs.RelationshipRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"id": rid, "characters": len(text)}


class ResearchPagesIn(BaseModel):
    website: str | None = Field(None, max_length=300, pattern=r"^https?://[^\s]+$")
    newsroom_url: str | None = Field(None, max_length=500, pattern=r"^https?://[^\s]+$")
    leadership_url: str | None = Field(None, max_length=500, pattern=r"^https?://[^\s]+$")


@router.post("/organisations/{org_id}/research-pages", tags=["Relationships"])
@exact
@_translate
def org_research_pages(request: Request, org_id: str, body: ResearchPagesIn):
    """The website, newsroom and leadership page research reads for this organisation (and follows links from)."""
    rs.set_research_pages(db_of(request), org_id, website=body.website, newsroom=body.newsroom_url, leadership=body.leadership_url,
                          meta=meta_of(request))
    return {"website": body.website, "newsroom_url": body.newsroom_url, "leadership_url": body.leadership_url}


@router.get("/people/duplicates", tags=["Relationships"])
@exact
def people_duplicates(request: Request, status: Literal["open", "merged", "dismissed", "all"] = "open"):
    return {"items": rs.duplicates(db_of(request), None if status == "all" else status)}


class MergeIn(BaseModel):
    keep_id: str
    note: str | None = Field(None, max_length=1000)


@router.post("/people/duplicates/{dup_id}/merge", tags=["Relationships"])
@exact
@_translate
def people_merge(request: Request, dup_id: str, body: MergeIn):
    """Merge a possible duplicate into the record kept. Reversible: POST /people/merges/{id}/undo."""
    return {"merge_id": rs.merge_duplicate(db_of(request), dup_id, body.keep_id, body.note, meta_of(request))}


class DismissIn(BaseModel):
    note: str | None = Field(None, max_length=1000)


@router.post("/people/duplicates/{dup_id}/dismiss", tags=["Relationships"])
@exact
@_translate
def people_dismiss(request: Request, dup_id: str, body: DismissIn):
    rs.dismiss_duplicate(db_of(request), dup_id, body.note, meta_of(request))
    return {"status": "dismissed"}


@router.post("/people/merges/{merge_id}/undo", tags=["Relationships"])
@exact
@_translate
def people_unmerge(request: Request, merge_id: str):
    rs.undo_merge(db_of(request), merge_id, meta_of(request))
    return {"status": "undone"}


class ProgressIn(BaseModel):
    to: Literal["new", "reviewing", "pursuing", "on_hold", "closed"]
    reason: str | None = Field(None, max_length=1000)
    closed_reason: str | None = Field(None, max_length=200)


@router.post("/opportunities/{opp_id}/progress", tags=["Opportunities"])
@exact
@_translate
def progress(request: Request, opp_id: str, body: ProgressIn):
    rs.set_progress(db_of(request), opp_id, body.to, body.reason, body.closed_reason, meta_of(request))
    return {"progress": body.to}


class SavedIn(BaseModel):
    saved: bool


@router.post("/opportunities/{opp_id}/saved", tags=["Opportunities"])
@exact
@_translate
def saved(request: Request, opp_id: str, body: SavedIn):
    rs.set_saved(db_of(request), opp_id, body.saved, meta_of(request))
    return {"saved": body.saved}


class OwnerIn(BaseModel):
    owner: str | None = Field(None, max_length=200)


@router.post("/opportunities/{opp_id}/owner-label", tags=["Opportunities"])
@exact
@_translate
def owner_label(request: Request, opp_id: str, body: OwnerIn):
    rs.set_owner(db_of(request), opp_id, body.owner, meta_of(request))
    return {"owner": body.owner}


class NextActionIn(BaseModel):
    action: str | None = Field(None, max_length=500)
    due: date | None = None


@router.post("/opportunities/{opp_id}/next-action", tags=["Opportunities"])
@exact
@_translate
def next_action(request: Request, opp_id: str, body: NextActionIn):
    rs.set_next_action(db_of(request), opp_id, body.action, body.due, meta_of(request))
    return {"next_action": body.action, "due": body.due}


class NoteIn(BaseModel):
    body: str = Field(min_length=2, max_length=5000)
    author: str | None = Field(None, max_length=200)


@router.post("/opportunities/{opp_id}/notes", tags=["Opportunities"])
@exact
@_translate
def add_note(request: Request, opp_id: str, body: NoteIn):
    return {"id": rs.add_note(db_of(request), opp_id, body.body, body.author, meta_of(request))}


ROLES = Literal["procurement_contact", "commercial_leader", "decision_maker", "department_lead", "regional_representative", "partner",
                "named_in_source", "unknown"]


class LinkIn(BaseModel):
    person_id: str | None = None
    full_name: str | None = Field(None, min_length=3, max_length=200)
    role_title: str | None = Field(None, max_length=200)
    organisation_id: str | None = None
    organisation_label: str | None = Field(None, max_length=200)
    role_on_opportunity: ROLES | None = None
    status: Literal["candidate", "relevant", "not_relevant"] | None = None
    relevance_basis: str | None = Field(None, max_length=1000)
    source_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")
    source_note: str | None = Field(None, max_length=1000)


@router.post("/opportunities/{opp_id}/people", tags=["Relationships"])
@exact
@_translate
def link_or_add_person(request: Request, opp_id: str, body: LinkIn):
    db, meta = db_of(request), meta_of(request)
    if db.one("opportunity_get2", id=opp_id) is None:
        raise not_found("Opportunity")
    if body.person_id:
        rs.link_person(db, opp_id, body.person_id, body.role_on_opportunity, body.status, body.relevance_basis, meta)
        return {"person_id": body.person_id}
    if not body.full_name:
        raise HTTPException(422, "give person_id, or full_name for a new person")
    pid = rs.create_person(db, body.model_dump() | {"opportunity_id": opp_id}, meta)
    return {"person_id": pid}


@router.get("/opportunities/{opp_id}/export.md", tags=["Opportunities"])
def opportunity_brief(request: Request, opp_id: str):
    db = db_of(request)
    intel = _intelligence(db, opp_id)
    o = intel["opportunity"]
    rr, ws, it = intel["relationships"], intel["workspace"], intel["interpretation"]
    ev = db.all("signal_evidence_view", signal=o["signal_id"] or o.get("tracked_from_signal_id")) if (o.get("signal_id") or o.get("tracked_from_signal_id")) else []
    geo = [g["name"] for g in db.all("opportunity_geo", id=opp_id)]
    lines = [f"# {o['title']}", "", f"_{ex.BRAND_HEADER} · exported {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", "",
             f"- **Record type:** {ws['record_type_label']}", f"- **Category:** {it['category']}",
             f"- **Organisation:** {o.get('organisation') or 'not established'}", f"- **Geography:** {', '.join(sorted(set(geo))) or 'not established'}",
             f"- **Tender status:** {ws['tender_status_label'] or 'n/a'}", f"- **Stated deadline:** {o.get('deadline_utc') or 'not stated'}",
             f"- **Progress:** {ws['progress_label']}" + (f" ({ws['closed_reason']})" if ws.get("closed_reason") else ""),
             f"- **Owner:** {ws['owner_label'] or 'not assigned'}", f"- **Next action:** {ws['next_action'] or 'none set'}"
             + (f" (due {ws['next_action_due']})" if ws.get("next_action_due") else ""), "",
             "## Source evidence", ""]
    for e in ev[:12]:
        lines.append(f"- {e.get('source_name') or 'source'}: \"{(e.get('quote') or '')[:300]}\" ({e.get('canonical_url') or e.get('original_url')}, "
                     f"published {e.get('published_at') or 'date not stated'})")
    if not ev:
        lines.append("- No source documents (record from WFC data or added by the team)")
    lines += ["", f"## {it['label']}", "", it["text"], ""]
    for u in it["unconfirmed"]:
        lines.append(f"- Unconfirmed: {u}")
    lines += ["", "## Organisations", ""] + [f"- {x['name']} ({x['involvement']})" for x in rr["organisations"]] + ["", "## Relevant people", ""]
    for p in rr["people"]:
        if p.get("link_status") == "not_relevant":
            continue
        lines.append(f"- {p['full_name']}, {p.get('role_title') or 'role not established'}, {p.get('organisation') or 'organisation not established'}: "
                     f"{p['state_label']}. Why relevant: {p['relevance_basis']}." + (f" Profile: {p['linkedin_profile_url']}" if p.get("linkedin_profile_url") else ""))
        for r in (p.get("roles") or [])[:3]:
            lines.append(f"  - Evidence: {r.get('role_title') or 'title not stated'} ({r['role_status']}), "
                         f"{r.get('organisation') or 'organisation not established'}"
                         + (f" ({r['affiliation_label'].lower()})" if r.get("organisation") else "") + f": {r['binding']}"
                         + (f" — \"{(r.get('quote') or '')[:200]}\"" if r.get("quote") else ""))
    if not rr["people"]:
        lines.append("- None recorded yet")
    lines += ["", "## Existing relationships and introductions", ""]
    lines += [f"- {r['person']}: relationship held by {r['holder_label']} ({r['nature'].replace('_', ' ')}, {r['status']}) — {r['basis']}"
              for r in rr.get("relationships", [])]
    lines += [f"- Introduction available to {r['target']} via {r['introducer']} — willingness confirmed: {r['willingness_basis']}"
              for r in rr.get("routes_available", [])]
    lines += [f"- Possible route to {r['target']} via {r['introducer']} (not confirmed) — {r['connection_basis']}" for r in rr.get("routes_possible", [])]
    if not (rr.get("relationships") or rr.get("routes_available") or rr.get("routes_possible")):
        lines.append("- None recorded")
    run = rr.get("latest_research") or {}
    cov = run.get("coverage") or {}
    if run:
        outcome = {"people_found": "people found in the sources read", "no_people_found": "no people found in the sources read",
                   "incomplete": "INCOMPLETE"}.get(run.get("outcome") or "", run.get("outcome") or "not recorded")
        lines += ["", "## Research coverage", "", f"- Last run: {run.get('started_at')} — {outcome}",
                  f"- Documents and pages: {cov.get('read', 0)} read of {cov.get('documents', 0)}; {cov.get('failed', 0)} could not be fetched; "
                  f"{cov.get('skipped', 0)} skipped; {cov.get('queued', 0)} still to read"]
        lines += [f"- Remaining: {x}" for x in cov.get("remaining", [])] + [f"- Not searched: {x}" for x in cov.get("not_searched", [])]
    lines += ["", f"**Relationship coverage:** {rr['coverage_label']}", "", "## Relationship gaps", ""] + [f"- {g}" for g in rr["gaps"]]
    lines += ["", "## Next actions", ""] + [f"- {a}" for a in rr["actions"]] + ([f"- {ws['next_action']}"] if ws.get("next_action") else [])
    lines += ["", "_Nothing in this brief has been sent to anyone. LinkedIn links are searches unless marked as a confirmed profile._", ""]
    body = "\n".join(ex.safe_cell(x) if x.startswith(("=", "+", "-@", "@")) else x for x in lines)
    return Response(body, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="atlas-opportunity-{opp_id[:8]}.md"'})


# ------------------------------------------------------------------ People
@router.get("/people", tags=["Relationships"])
@exact
def people(request: Request, states: str | None = None, q: str | None = None, org: str | None = None, has_action: bool | None = None,
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = db_of(request).all("rel_people_list", states=_csv_list(states), q=q or None, org=org or None, since=None, has_action=has_action,
                              limit=limit, offset=offset)
    total = int(rows[0]["total"]) if rows else 0
    for r in rows:
        r.pop("total", None)
        r["state_label"] = rel.STATE_LABELS[r["state"]]
        r["linkedin_search_url"] = rel.linkedin_search_url(r["full_name"], r.get("organisation"))
    return {"items": rows, "total": total, "limit": limit, "offset": offset, "states": rel.STATE_LABELS}


class PersonIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    role_title: str | None = Field(None, max_length=200)
    organisation_id: str | None = None
    organisation_label: str | None = Field(None, max_length=200)
    remit_text: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=5000)
    source_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")
    source_note: str | None = Field(None, max_length=1000)


@router.post("/people", tags=["Relationships"])
@exact
@_translate
def create_person(request: Request, body: PersonIn):
    return {"id": rs.create_person(db_of(request), body.model_dump(), meta_of(request))}


@router.get("/people/{person_id}", tags=["Relationships"])
@exact
@_translate
def person(request: Request, person_id: str):
    return rs.person_detail(db_of(request), person_id)


class PersonUpdate(BaseModel):
    role_title: str | None = Field(None, max_length=200)
    organisation_id: str | None = None
    organisation_label: str | None = Field(None, max_length=200)
    remit_text: str | None = Field(None, max_length=300)
    remit_basis: str | None = Field(None, max_length=1000)
    relationship_owner: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=5000)
    next_action: str | None = Field(None, max_length=500)
    next_action_due: date | None = None


@router.post("/people/{person_id}", tags=["Relationships"])
@exact
@_translate
def update_person(request: Request, person_id: str, body: PersonUpdate):
    rs.update_person(db_of(request), person_id, body.model_dump(exclude_unset=True), meta_of(request))
    return {"ok": True}


class ConfirmIn(BaseModel):
    basis: str = Field(min_length=10, max_length=1000)
    source_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")


@router.post("/people/{person_id}/confirm", tags=["Relationships"])
@exact
@_translate
def confirm(request: Request, person_id: str, body: ConfirmIn):
    rs.confirm_identity(db_of(request), person_id, body.basis, body.source_url, meta_of(request))
    return {"ok": True}


class LinkedInIn(BaseModel):
    url: str | None = Field(None, max_length=300)


@router.post("/people/{person_id}/linkedin", tags=["Relationships"])
@exact
@_translate
def linkedin(request: Request, person_id: str, body: LinkedInIn):
    return {"linkedin_profile_url": rs.set_linkedin_profile(db_of(request), person_id, body.url, meta_of(request))}


class EvidenceIn(BaseModel):
    supports: Literal["identity", "role", "remit", "relevance"]
    url: str | None = Field(None, max_length=1000, pattern=r"^https?://")
    note: str = Field(min_length=3, max_length=1000)


@router.post("/people/{person_id}/evidence", tags=["Relationships"])
@exact
@_translate
def evidence(request: Request, person_id: str, body: EvidenceIn):
    rs.add_evidence(db_of(request), person_id, body.supports, body.url, body.note, meta_of(request))
    return {"ok": True}


class RelationshipIn(BaseModel):
    holder: str = Field(min_length=2, max_length=200)
    nature: Literal["works_with", "former_colleague", "client", "supplier", "partner", "personal", "other"]
    basis: str = Field(min_length=10, max_length=1000)


@router.post("/people/{person_id}/relationships", tags=["Relationships"])
@exact
@_translate
def relationship(request: Request, person_id: str, body: RelationshipIn):
    return {"id": rs.record_relationship(db_of(request), person_id, body.holder, body.nature, body.basis, meta_of(request))}


class StatusIn(BaseModel):
    status: Literal["current", "lapsed"]


@router.post("/person-relationships/{rel_id}/status", tags=["Relationships"])
@exact
@_translate
def relationship_status(request: Request, rel_id: str, body: StatusIn):
    rs.set_relationship_status(db_of(request), rel_id, body.status, meta_of(request))
    return {"ok": True}


class RouteIn(BaseModel):
    introducer_person_id: str | None = None
    introducer_label: str | None = Field(None, max_length=200)
    wfc_holder_label: str | None = Field(None, max_length=200)
    connection_basis: str = Field(min_length=10, max_length=1000)
    evidence_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")
    opportunity_id: str | None = None
    notes: str | None = Field(None, max_length=2000)


@router.post("/people/{person_id}/routes", tags=["Relationships"])
@exact
@_translate
def add_route(request: Request, person_id: str, body: RouteIn):
    return {"id": rs.add_route(db_of(request), person_id, body.model_dump(), meta_of(request))}


class RouteStatusIn(BaseModel):
    status: Literal["possible", "available", "requested", "made", "declined"]
    willingness_basis: str | None = Field(None, max_length=1000)
    notes: str | None = Field(None, max_length=2000)


@router.post("/routes/{route_id}/status", tags=["Relationships"])
@exact
@_translate
def route_status(request: Request, route_id: str, body: RouteStatusIn):
    rs.update_route(db_of(request), route_id, body.status, body.willingness_basis, body.notes, meta_of(request))
    return {"ok": True}


class EngagementIn(BaseModel):
    kind: Literal["meeting", "call", "email", "proposal", "visit", "other"]
    summary: str = Field(min_length=3, max_length=2000)
    occurred_at: datetime | None = None
    opportunity_id: str | None = None
    owner_label: str | None = Field(None, max_length=200)
    outcome: Literal["positive", "neutral", "negative", "pending"] | None = None
    next_step: str | None = Field(None, max_length=500)


@router.post("/people/{person_id}/engagements", tags=["Relationships"])
@exact
@_translate
def engagement(request: Request, person_id: str, body: EngagementIn):
    return {"id": rs.add_engagement(db_of(request), person_id, body.model_dump(), meta_of(request))}


class WebsiteIn(BaseModel):
    website: str | None = Field(None, max_length=300, pattern=r"^https?://[^\s]+$")


@router.post("/organisations/{org_id}/website", tags=["Relationships"])
@exact
def org_website(request: Request, org_id: str, body: WebsiteIn):
    db = db_of(request)
    if not db.run("org_set_website", id=org_id, website=body.website):
        raise not_found("Organisation")
    from ..services.audit import audit
    audit(db, "organisation_website", meta_of(request), entity_type="organisation", entity_id=org_id)
    return {"website": body.website}
