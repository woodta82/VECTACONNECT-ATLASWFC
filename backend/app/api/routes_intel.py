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
from ..domain import relationship_health as rh
from ..domain import relationships as rel
from ..reference.geography import COUNTRIES
from ..services import company_intelligence as cmp
from ..services import contact_discovery as cd
from ..services import relationship_intelligence as ri
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
        except (rs.RelationshipRejected, cd.DiscoveryRejected, ri.IntelligenceRejected, cmp.CompanyRejected) as exc:
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
            q: str | None = None, deadline_days: int | None = Query(None, ge=1, le=730), saved: bool | None = None, airports: str | None = None,
            live: bool | None = None, needs: Literal["attention"] | None = None,
            sort: Literal["priority", "deadline", "source_date"] = "priority", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """`live` and `needs=attention` apply the Dashboard's own rules (services/dashboard.py), so a summary's link opens exactly the records it counts."""
    rows = _records(request, countries=countries, region=region, modules=modules, org=org, tender=tender, progress=progress, coverage=coverage,
                    types=types, q=q, deadline_days=deadline_days, saved=saved, sort=sort)
    if live or needs:
        from ..services import dashboard as dash
        rows = [r for r in rows if dash.is_live(r)]
        if needs == "attention":
            research, now = dash.research_state(db_of(request)), datetime.now(timezone.utc)
            rows = [r for r in rows if r["record_type"] in ("tender", "commercial") and dash.attention(r, research, now)]
    if airports:
        from ..services import airport_directory as ad
        found, _missing = ad.resolve_many(db_of(request), [a for a in airports.split(",") if a.strip()])
        if found:
            keep = {str(r["opportunity_id"]) for r in db_of(request).all("opps_with_airports", idents=[a["ident"] for a in found])}
            rows = [r for r in rows if str(r["id"]) in keep]
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
           country: str | None = None, module: str | None = None, stakeholder_type: str | None = None,
           sort: Literal["status", "health", "attention", "name", "recent"] = "status", min_health: int | None = Query(None, ge=0, le=100),
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return _people(db_of(request), states=states, q=q, org=org, has_action=has_action, country=country, module=module,
                   stakeholder_type=stakeholder_type, sort=sort, min_health=min_health, limit=limit, offset=offset)


def _people(db, *, states, q, org, has_action, country, module, stakeholder_type, sort, min_health, limit, offset) -> dict[str, Any]:
    # health and attention are computed on read for everyone, so sorting by them needs the whole list first
    rows = db.all("rel_people_list", states=_csv_list(states), q=q or None, org=org or None, since=None, has_action=has_action,
                  country=(country or "").upper() or None, module=module or None, stakeholder_type=stakeholder_type or None,
                  limit=MAX_RECORDS, offset=0)
    health = ri.health_index(db)
    for r in rows:
        r.pop("total", None)
        r["state_label"] = rel.STATE_LABELS[r["state"]]
        r["linkedin_search_url"] = rel.linkedin_search_url(r["full_name"], r.get("organisation"))
        h = health.get(str(r["id"])) or {}
        for k in ("health_score", "health_band", "health_band_label", "at_risk", "momentum", "momentum_state", "attention", "recommended_action",
                  "stakeholder_label", "influence_score", "explanation"):
            r[k] = h.get(k)
        r["stakeholder_label"] = r["stakeholder_label"] or rh.STAKEHOLDER_TYPES.get(r.get("stakeholder_type") or "unknown")
        r["posture_label"] = rh.POSTURES.get(r.get("posture") or "unknown")
        r["capability_area_label"] = ov.CATEGORY_LABELS.get(r.get("capability_area") or "", None)
    if min_health is not None:
        rows = [r for r in rows if r["health_score"] is not None and r["health_score"] >= min_health]
    if sort == "health":
        rows.sort(key=lambda r: (r["health_score"] is None, -(r["health_score"] or 0), r["full_name"]))
    elif sort == "attention":
        rows.sort(key=lambda r: (-(r["attention"] or 0), r["full_name"]))
    elif sort == "name":
        rows.sort(key=lambda r: r["full_name"].lower())
    elif sort == "recent":
        rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    total = len(rows)
    return {"items": rows[offset: offset + limit], "total": total, "limit": limit, "offset": offset, "states": rel.STATE_LABELS,
            "stakeholder_types": rh.STAKEHOLDER_TYPES, "postures": rh.POSTURES, "decision_authority": rh.DECISION_AUTHORITY,
            "capability_areas": ov.CATEGORY_LABELS}


@router.get("/people/export.csv", tags=["Relationships"])
def people_export(request: Request, states: str | None = None, q: str | None = None, org: str | None = None, country: str | None = None,
                  module: str | None = None, stakeholder_type: str | None = None,
                  sort: Literal["status", "health", "attention", "name", "recent"] = "status"):
    data = _people(db_of(request), states=states, q=q, org=org, has_action=None, country=country, module=module, stakeholder_type=stakeholder_type,
                   sort=sort, min_health=None, limit=MAX_RECORDS, offset=0)
    out = []
    for r in data["items"]:
        out.append([r["full_name"], r.get("role_title") or "", r.get("organisation") or "", r["state_label"], r["stakeholder_label"],
                    rh.DECISION_AUTHORITY.get(r.get("decision_authority") or "unknown"), r["posture_label"], r.get("capability_area_label") or "",
                    "" if r["health_score"] is None else r["health_score"], r.get("health_band_label") or "Not assessed", r.get("momentum") or "",
                    r.get("relationship_owner") or "", r.get("next_action") or "", r.get("linkedin_profile_url") or r["linkedin_search_url"],
                    r.get("recommended_action") or ""])
    csv = ex.to_csv(["Name", "Title", "Organisation", "Research status", "Stakeholder type", "Decision authority", "Posture", "Capability area",
                     "Health (0-100)", "Health band", "Momentum", "Relationship owner", "Next action", "LinkedIn (profile or search)",
                     "Recommended action"], out, scope_note="Health is a measure of a relationship's upkeep from recorded engagements; not a probability of winning",
                    generated_at=datetime.now(timezone.utc).isoformat())
    return Response(csv, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="atlas-contacts.csv"'})


# ------------------------------------------------------------------ Relationship intelligence (ATLAS v1.0 parameters, 29 Oct 2026)
@router.get("/relationships/questions", tags=["Relationships"])
@exact
def relationship_questions(request: Request, limit: int = Query(8, ge=1, le=30)):
    """Who matters most, who are we missing, what is improving, what is at risk, where to invest time: computed on read from
    recorded engagements, the team's stakeholder judgements and live opportunity links."""
    return ri.questions(db_of(request), limit=limit)


@router.get("/relationships/impact/{opp_id}", tags=["Relationships"])
@exact
@_translate
def relationship_impact(request: Request, opp_id: str):
    return ri.impact(db_of(request), opp_id)


@router.get("/people/{person_id}/health", tags=["Relationships"])
@exact
@_translate
def person_health(request: Request, person_id: str):
    return ri.person_health(db_of(request), person_id)


class JudgementIn(BaseModel):
    stakeholder_type: str = "unknown"
    decision_authority: str = "unknown"
    posture: str = "unknown"
    basis: str | None = Field(None, max_length=2000)
    by_label: str | None = Field(None, max_length=200)
    key_interests: str | None = Field(None, max_length=2000)
    strategic_account: bool = False


@router.post("/people/{person_id}/judgement", tags=["Relationships"])
@exact
@_translate
def person_judgement(request: Request, person_id: str, body: JudgementIn):
    ri.set_judgement(db_of(request), person_id, body.model_dump(), meta_of(request))
    return {"ok": True}


class InvolvementIn(BaseModel):
    involvement: Literal["employee", "appointed_representative", "external_adviser", "press_contact", "unresolved"]
    basis: str = Field(min_length=10, max_length=500)


@router.post("/people/{person_id}/involvement", tags=["Relationships"])
@exact
@_translate
def person_involvement(request: Request, person_id: str, body: InvolvementIn):
    """A person's correction of someone's involvement; later research never changes it."""
    return rs.set_involvement(db_of(request), person_id, body.involvement, body.basis, meta_of(request))


class OutreachIn(BaseModel):
    channel: Literal["email", "linkedin_message", "call_notes"] = "email"
    opportunity_id: str | None = None
    sender_label: str | None = Field(None, max_length=200)
    use_ai: bool = True


@router.post("/people/{person_id}/outreach-drafts", tags=["Relationships"])
@exact
@_translate
def outreach_draft(request: Request, person_id: str, body: OutreachIn):
    return ri.draft_outreach(db_of(request), request.app.state.settings, person_id, body.model_dump(), meta_of(request))


@router.get("/people/{person_id}/outreach-drafts", tags=["Relationships"])
@exact
def outreach_list(request: Request, person_id: str):
    return {"items": db_of(request).all("outreach_for", id=person_id)}


class OutreachEditIn(BaseModel):
    subject: str | None = Field(None, max_length=300)
    body: str | None = Field(None, min_length=10, max_length=8000)


@router.post("/outreach-drafts/{draft_id}", tags=["Relationships"])
@exact
@_translate
def outreach_edit(request: Request, draft_id: str, body: OutreachEditIn):
    ri.update_draft(db_of(request), draft_id, body.subject, body.body, meta_of(request))
    return {"ok": True}


class OutreachStatusIn(BaseModel):
    status: Literal["sent", "discarded"]
    by_label: str | None = Field(None, max_length=200)
    note: str | None = Field(None, max_length=1000)


@router.post("/outreach-drafts/{draft_id}/status", tags=["Relationships"])
@exact
@_translate
def outreach_status(request: Request, draft_id: str, body: OutreachStatusIn):
    ri.set_draft_status(db_of(request), draft_id, body.status, body.by_label, body.note, meta_of(request))
    return {"ok": True}


# ------------------------------------------------------------------ Open-market contact discovery
class DiscoveryIn(BaseModel):
    purpose: Literal["people", "companies"] = "people"                 # 29 Oct 2026: research purposes
    brief: str | None = Field(None, max_length=600)                    # plain-language research request
    organisation_name: str | None = Field(None, max_length=200)
    countries: list[str] = Field(default_factory=list, max_length=5)
    region: str | None = Field(None, max_length=40)
    airport_iata: str | None = Field(None, min_length=3, max_length=3)
    airports: list[str] = Field(default_factory=list, max_length=20)        # directory idents or IATA/ICAO codes (30 Oct 2026)
    capability_area: str | None = None
    organisation_kinds: list[str] = Field(default_factory=list, max_length=12)
    role_focus: str | None = Field(None, max_length=120)
    requested_by_label: str | None = Field(None, max_length=200)


@router.post("/contacts/discover", tags=["Relationships"])
@exact
@_translate
def discover_contacts(request: Request, body: DiscoveryIn):
    """A standalone search for contacts in the open market, by organisation, country or region, WFC capability area and role
    focus. Reads the organisation's own pages and the authorised web search's results under the evidence rules."""
    st = request.app.state
    return cd.start(db_of(request), st.settings, body.model_dump(), meta_of(request), fetch=getattr(st, "fetch", None),
                    transport=getattr(st, "ai_transport", None), search_transport=getattr(st, "search_transport", None))


@router.post("/contacts/discoveries/{disc_id}/continue", tags=["Relationships"])
@exact
@_translate
def discovery_continue(request: Request, disc_id: str):
    st = request.app.state
    return cd.continue_(db_of(request), st.settings, disc_id, meta_of(request), fetch=getattr(st, "fetch", None),
                        transport=getattr(st, "ai_transport", None), search_transport=getattr(st, "search_transport", None))


@router.get("/contacts/discoveries", tags=["Relationships"])
@exact
def discoveries(request: Request, limit: int = Query(20, ge=1, le=100), purpose: Literal["people", "companies"] | None = None):
    return {"items": cd.list_discoveries(db_of(request), limit=limit, purpose=purpose)}


# ------------------------------------------------------------------ Companies (29 Oct 2026: company intelligence; supplied data)
@router.get("/companies", tags=["Companies"])
@exact
def companies(request: Request, kind: str | None = None, country: str | None = None, airport: str | None = None, origin: str | None = None,
              carrier_type: str | None = None, state: Literal["verified", "awaiting_verification", "researched", "unverified"] | None = None,
              discovery: str | None = None, q: str | None = None, sort: Literal["name", "relevance", "recent"] = "name",
              scope: Literal["all", "cargo", "freighter", "belly", "mixed", "cargo_services", "passenger_only", "unresolved"] | None = None,
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """The companies ATLAS knows: discovered from public pages, supplied by a dataset (awaiting verification), or from WFC data.
    `airport`: an IATA/ICAO code or directory ident (office, station or served); `scope`: freight scope ('cargo' = anything but passenger-only)."""
    out = cmp.list_companies(db_of(request), kind=kind or None, country=(country or "").upper() or None, airport=(airport or "").upper() or None,
                             origin=origin or None, carrier_type=carrier_type or None, state=state, discovery=discovery or None, q=q or None,
                             sort=sort, scope=None if scope == "all" else scope, limit=limit, offset=offset)
    from ..domain import company_intel as ci
    return {**out, "limit": limit, "offset": offset, "kinds": ci.KIND_LABELS, "carrier_types": ci.CARRIER_LABELS, "states": cmp.STATE_LABELS}


@router.get("/companies/{org_id}", tags=["Companies"])
@exact
@_translate
def company(request: Request, org_id: str):
    return cmp.profile(db_of(request), org_id)


class CompanyEditIn(BaseModel):
    website: str | None = Field(None, max_length=300, pattern=r"^https?://[^\s]+$")
    kind: str | None = None
    country: str | None = Field(None, min_length=2, max_length=2)
    airport_iata: str | None = Field(None, min_length=3, max_length=3)
    carrier_type: str | None = None
    description: str | None = Field(None, max_length=1000)
    services_text: str | None = Field(None, max_length=1000)
    locations_text: str | None = Field(None, max_length=600)
    parent_group: str | None = Field(None, max_length=200)
    basis: str | None = Field(None, max_length=500)
    source_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")


@router.post("/companies/{org_id}/edit", tags=["Companies"])
@exact
@_translate
def company_edit(request: Request, org_id: str, body: CompanyEditIn):
    cmp.edit(db_of(request), org_id, body.model_dump(), meta_of(request))
    return {"ok": True}


class VerifyIn(BaseModel):
    basis: str = Field(min_length=10, max_length=1000)
    source_url: str | None = Field(None, max_length=1000, pattern=r"^https?://")


@router.post("/companies/{org_id}/verify", tags=["Companies"])
@exact
@_translate
def company_verify(request: Request, org_id: str, body: VerifyIn):
    """A person records that the company's identity, website and kind were checked against current sources."""
    cmp.verify(db_of(request), org_id, body.basis, body.source_url, meta_of(request))
    return {"ok": True}


class ContactStatusIn(BaseModel):
    status: Literal["verified", "lapsed"]
    note: str | None = Field(None, max_length=500)


@router.post("/companies/{org_id}/contacts/{contact_id}/status", tags=["Companies"])
@exact
@_translate
def company_contact_status(request: Request, org_id: str, contact_id: str, body: ContactStatusIn):
    cmp.set_contact_status(db_of(request), org_id, contact_id, body.status, body.note, meta_of(request))
    return {"ok": True}


class RelStatusIn(BaseModel):
    status: Literal["confirmed", "lapsed", "not_established"]
    basis: str = Field(min_length=10, max_length=1000)
    by_label: str | None = Field(None, max_length=200)


@router.post("/companies/{org_id}/relationships/{rel_id}/status", tags=["Companies"])
@exact
@_translate
def company_relationship_status(request: Request, org_id: str, rel_id: str, body: RelStatusIn):
    """Confirm, mark as lapsed or mark as not established a representation or business relationship, with the basis."""
    cmp.set_relationship_status(db_of(request), org_id, rel_id, body.status, body.basis, body.by_label, meta_of(request))
    return {"ok": True}


class CompanyOpportunityIn(BaseModel):
    module: str
    interpretation: str = Field(min_length=20, max_length=2000)
    title: str | None = Field(None, max_length=200)
    country: str | None = Field(None, min_length=2, max_length=2)
    by_label: str | None = Field(None, max_length=200)


@router.post("/companies/{org_id}/opportunities", tags=["Companies"])
@exact
@_translate
def company_opportunity(request: Request, org_id: str, body: CompanyOpportunityIn):
    """A potential commercial opportunity from a researched company, recorded by a person with the interpretation. Never automatic."""
    return cmp.create_opportunity(db_of(request), org_id, body.model_dump(), meta_of(request))


@router.post("/supplied-data", tags=["Companies"])
@exact
async def supplied_upload(request: Request, file: UploadFile = File(...), name: str | None = Form(None), notes: str | None = Form(None),
                          by_label: str | None = Form(None)):
    """A supplied dataset (an .xlsx station list such as a GSA list) preserved row by row; everything from it is marked supplied —
    awaiting verification. It seeds research; it is not treated as a current database."""
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (5 MB at most)")
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(415, "Only Excel workbooks (.xlsx) are read as supplied datasets")
    try:
        return cmp.import_supplied(db_of(request), request.app.state.settings, data=data, filename=file.filename or "workbook.xlsx", name=name,
                                   notes=notes, meta=meta_of(request), by=by_label)
    except cmp.CompanyRejected as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.get("/supplied-data", tags=["Companies"])
@exact
def supplied_list(request: Request):
    return {"items": cmp.supplied_imports(db_of(request))}


@router.get("/supplied-data/{import_id}", tags=["Companies"])
@exact
@_translate
def supplied_detail(request: Request, import_id: str):
    return cmp.supplied_import_detail(db_of(request), import_id)


@router.get("/control-panel/summaries", tags=["Overview"])
@exact
def control_panel_summaries(request: Request):
    """Clearly separated summaries of the full system, each with the link that opens the filtered records: commercial opportunities,
    companies researched, relevant people identified, relationship gaps and next actions, important market developments, tender
    deadlines. Counts only; the analytics stay on the Control panel below them."""
    db = db_of(request)
    ranked = _records(request)
    now = datetime.now(timezone.utc)
    opps = [r for r in ranked if r["record_type"] in ("tender", "commercial")]
    commercial = [r for r in opps if r["record_type"] == "commercial"]
    tenders = [r for r in opps if r["record_type"] == "tender"]
    live_tenders = [r for r in tenders if (r.get("tender_status") or "") in ov.LIVE]
    def at(v: Any) -> datetime:
        return ov._as_dt(v) or datetime.min.replace(tzinfo=timezone.utc)
    live = [r for r in opps if r.get("progress") != "closed" and (r.get("tender_status") or "") not in ov.TERMINAL]
    soon = [r for r in tenders if r.get("deadline_at") and now <= at(r["deadline_at"]) <= now + timedelta(days=30)]
    gaps = [r for r in live if r.get("coverage") in ("none", "candidates_only")]
    def due(v: Any) -> date | None:
        if v is None:
            return None
        return v if isinstance(v, date) and not isinstance(v, datetime) else (at(v).date() if at(v) else None)
    actions_due = [r for r in live if r.get("next_action") and due(r.get("next_action_due")) and due(r["next_action_due"]) <= (now + timedelta(days=14)).date()]
    cs = db.one("cp_company_summary") or {}
    mc = db.one("cp_market_counts") or {}
    signals = db.all("cp_market_signals", limit=5)
    for sg in signals:
        sg["category"] = ov.CATEGORY_LABELS.get(sg["module"], sg["module"])
        sg["country_name"] = COUNTRIES.get(sg.get("country") or "", (None,))[0]
    return {
        "generated_at": now,
        "summaries": [
            {"key": "opportunities", "title": "Commercial opportunities", "count": len([r for r in commercial if r in live]),
             "detail": f"{len(live)} live opportunity records: {len(commercial)} commercial, {len(tenders)} tenders", "link": "/opportunities?types=commercial",
             "items": [{"id": r["id"], "title": r["title"], "detail": ", ".join(r["countries_named"]) or None} for r in commercial[:5]]},
            {"key": "companies", "title": "Companies researched", "count": int(cs.get("researched") or 0),
             "detail": f"{int(cs.get('verified') or 0)} verified; {int(cs.get('awaiting_verification') or 0)} supplied awaiting verification; "
                       f"{int(cs.get('representation_sourced') or 0)} representation relationships sourced, {int(cs.get('representation_supplied') or 0)} supplied",
             "link": "/companies?state=researched", "secondary": [{"label": "Awaiting verification", "link": "/companies?state=awaiting_verification",
                                                                   "count": int(cs.get("awaiting_verification") or 0)}],
             "items": [{"id": r["country"], "title": COUNTRIES.get(r["country"], (r["country"],))[0], "detail": f"{r['companies']} companies, {r['verified']} verified",
                        "link": f"/companies?country={r['country']}"} for r in db.all("cp_companies_by_country")[:5]]},
            {"key": "people", "title": "Relevant people identified", "count": int(cs.get("people_identified") or 0),
             "detail": f"{int(cs.get('people_confirmed') or 0)} confirmed by a person; {int(cs.get('people_candidates') or 0)} research candidates; "
                       f"{int(cs.get('discoveries_30d') or 0)} discoveries in 30 days", "link": "/relationships?state=research_candidate",
             "items": []},
            {"key": "gaps", "title": "Relationship gaps and next actions", "count": len(gaps),
             "detail": f"{len(gaps)} live opportunities without a usable relationship; {len(actions_due)} next actions due within 14 days",
             "link": "/opportunities?coverage=none,candidates_only",
             "items": [{"id": r["id"], "title": r["title"], "detail": r.get("next_action") or "no relationship recorded"} for r in (actions_due + gaps)[:5]]},
            {"key": "market", "title": "Important market developments", "count": int(mc.get("market_signals") or 0),
             "detail": f"{int(mc.get('market_signals_30d') or 0)} in the last 30 days; {int(mc.get('freight_candidates') or 0)} freight candidates to review",
             "link": "/opportunities?types=market_signal",
             "items": [{"id": sg["id"], "title": sg["title"], "detail": ", ".join(x for x in (sg.get("country_name"), sg.get("category")) if x), "link": f"/signals/{sg['id']}"}
                       for sg in signals]},
            {"key": "deadlines", "title": "Tender deadlines", "count": len(soon),
             "detail": f"{len(live_tenders)} open or revised tenders; {len(soon)} deadlines within 30 days", "link": "/opportunities?types=tender&deadline_days=30",
             "items": [{"id": r["id"], "title": r["title"], "detail": at(r["deadline_at"]).strftime("%d %b %Y")} for r in sorted(soon, key=lambda r: at(r["deadline_at"]))[:5]]},
        ],
    }


@router.get("/contacts/discoveries/{disc_id}", tags=["Relationships"])
@exact
@_translate
def discovery(request: Request, disc_id: str):
    return cd.detail(db_of(request), disc_id)


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
    kind: Literal["meeting", "call", "email", "proposal", "visit", "introduction", "event", "message", "note", "other"]
    summary: str = Field(min_length=3, max_length=2000)
    occurred_at: datetime | None = None
    opportunity_id: str | None = None
    owner_label: str | None = Field(None, max_length=200)
    outcome: Literal["positive", "neutral", "negative", "no_response", "pending"] | None = None
    next_step: str | None = Field(None, max_length=500)
    direction: Literal["outbound", "inbound", "mutual"] = "outbound"


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
