"""Relationship intelligence and the light commercial workspace (28 Oct 2026 refocus and its continuation).

Research itself (what is read, in which order, and how completeness is reported) is in services/relationship_research.py.
This module holds the people records: confirming identity, LinkedIn profiles, evidence, opportunity links, existing
relationships, introduction routes, engagements, possible duplicates and reversible merges, and the opportunity's
relationship view. Every candidate keeps its evidence and the reason it appears relevant. Nobody becomes a decision maker,
a confirmed identity, an existing relationship or an available introduction without a person recording it with a basis.
Nothing is sent to anyone.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any, Callable

from ..ai import extraction as ai_extraction
from ..config import Settings
from ..domain import retrieval
from ..domain import relationships as rel
from ..domain.attribution import AFFILIATION_LABELS
from ..domain.involvement import LABELS as INVOLVEMENT_LABELS
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit

RELATIONSHIP_NATURES = ("works_with", "former_colleague", "client", "supplier", "partner", "personal", "other")
ROUTE_STATUSES = ("possible", "available", "requested", "made", "declined")


class RelationshipRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _require(row: Any, what: str) -> Any:
    if row is None:
        raise RelationshipRejected(404, f"{what} not found")
    return row


def _active(db: Database, person_id: str) -> Any:
    """A person record that can be changed: it exists and has not been merged into another record."""
    p = _require(db.one("rel_person_get", id=person_id), "Person")
    if p.get("merged_into_id"):
        raise RelationshipRejected(409, "this record was merged into another person: change that record, or undo the merge")
    return p


def _country_name(code: str | None) -> str | None:
    return COUNTRIES.get(code, (None,))[0] if code else None


# ===================================================================== research
def research(db: Database, settings: Settings, opp_id: str, meta: RequestMeta, *,
             fetch: Callable[[str], retrieval.FetchResult] | None = None,
             transport: ai_extraction.Transport | None = None, search_transport: Any = None, mode: str = "start") -> dict[str, Any]:
    """Opportunity-led relationship research: see services/relationship_research.py."""
    from . import relationship_research as rr
    if mode not in ("start", "continue"):
        raise RelationshipRejected(422, "mode must be start or continue")
    try:
        return rr.research(db, settings, opp_id, meta, fetch=fetch, transport=transport, search_transport=search_transport, mode=mode)
    except rr.ResearchRejected as exc:
        raise RelationshipRejected(exc.status, exc.detail) from exc


def add_research_source(db: Database, opp_id: str, *, url: str | None, title: str | None, text: str | None, meta: RequestMeta,
                        organisation_id: str | None = None) -> str:
    from . import relationship_research as rr
    try:
        return rr.add_user_source(db, opp_id, url=url, title=title, text=text, meta=meta, organisation_id=organisation_id)
    except rr.ResearchRejected as exc:
        raise RelationshipRejected(exc.status, exc.detail) from exc


def set_research_pages(db: Database, org_id: str, *, website: str | None, newsroom: str | None, leadership: str | None,
                       meta: RequestMeta) -> None:
    for u in (website, newsroom, leadership):
        if u and not u.startswith(("http://", "https://")):
            raise RelationshipRejected(422, "addresses must start with http:// or https://")
    with db.transaction() as tx:
        _require(tx.scalar("org_research_pages_set", id=org_id, website=website, newsroom=newsroom, leadership=leadership), "Organisation")
        audit(tx, "organisation_research_pages", meta, entity_type="organisation", entity_id=org_id)


def search_suggestions(module: str, orgs: list[dict[str, Any]], countries: list[str]) -> list[dict[str, str]]:
    """Targeted LinkedIn people searches: organisation x role (x country). Labelled as searches, never as contacts."""
    country = _country_name(countries[0]) if countries else None
    out = []
    for o in orgs[:2]:
        for r in rel.target_roles(module):
            terms = r.search_terms[0]
            out.append({"organisation": o["name"], "role": r.label, "country": country or "",
                        "url": rel.linkedin_search_url(o["name"], terms, country), "kind": "linkedin_search"})
    return out


# ===================================================================== people
def person_detail(db: Database, person_id: str) -> dict[str, Any]:
    p = _require(db.one("rel_person_get", id=person_id), "Person")
    country = _country_name(p.get("organisation_country"))
    p["state_label"] = rel.STATE_LABELS.get(p["state"], p["state"])
    p["linkedin_search_url"] = rel.linkedin_search_url(p["full_name"], p.get("organisation"))
    p["linkedin_role_search_url"] = rel.linkedin_search_url(p.get("organisation"), p.get("role_title"), country) if p.get("organisation") else None
    gaps: list[str] = []
    if p["state"] == "research_candidate":
        gaps.append("Identity and role not yet confirmed by a person")
    if not p.get("linkedin_profile_url"):
        gaps.append("No confirmed LinkedIn profile (use the search, then save the correct profile)")
    if not p.get("relationship_owner"):
        gaps.append("No relationship owner recorded")
    if not p.get("remit_text"):
        gaps.append("Geographic remit not established")
    if p["state"] in ("research_candidate", "identity_confirmed") and not p.get("possible_routes"):
        gaps.append("No introduction route recorded")
    roles = db.all("rel_roles_for", id=person_id)
    for r in roles:
        r["affiliation_label"] = AFFILIATION_LABELS.get(r["affiliation"], r["affiliation"])
    current = {(r["role_title"] or "").lower() for r in roles if r["role_status"] == "current" and r["role_title"]}
    if len(current) > 1:
        gaps.append("Sources state different current titles: confirm which is correct")
    if not any(r["organisation"] and r["role_status"] == "current" for r in roles) and not p.get("organisation"):
        gaps.append("Organisation not established by any source: record it when confirmed")
    dups = [d for d in db.all("dup_list", status="open", person=person_id)]
    from . import relationship_intelligence as ri
    intelligence = ri.person_health(db, person_id)
    if intelligence["stakeholder"]["type"] == "unknown":
        gaps.append("Stakeholder type, decision authority and posture not yet judged by a person")
    return {"person": p, "evidence": db.all("rel_evidence_for", id=person_id), "opportunities": db.all("rel_person_opportunities", id=person_id),
            "relationships": db.all("rel_relationships_for", id=person_id), "routes": db.all("rel_routes_for", id=person_id),
            "engagements": db.all("rel_engagements_for", id=person_id), "roles": roles, "duplicates": dups,
            "merges": db.all("merges_for", id=person_id), "gaps": gaps, "intelligence": intelligence,
            "outreach": db.all("outreach_for", id=person_id)}


def create_person(db: Database, data: dict[str, Any], meta: RequestMeta) -> str:
    with db.transaction() as tx:
        pid = str(tx.scalar("rel_person_insert", name=" ".join(data["full_name"].split()), role=data.get("role_title"),
                            org=data.get("organisation_id"), org_label=data.get("organisation_label"), origin="manual",
                            remit=data.get("remit_text"), remit_countries=data.get("remit_countries"), notes=data.get("notes")))
        if data.get("source_url") or data.get("source_note"):
            tx.run("rel_evidence_add", person=pid, supports="identity", kind="public_page" if data.get("source_url") else "note",
                   doc=None, url=data.get("source_url"), quote=None, note=data.get("source_note") or "added by a reviewer",
                   session_ref=meta.session_ref)
        if data.get("opportunity_id"):
            tx.run("rel_link_upsert", opp=data["opportunity_id"], person=pid, role=data.get("role_on_opportunity") or "unknown",
                   basis=data.get("relevance_basis") or "added by a reviewer", status="candidate")
        audit(tx, "person_created", meta, entity_type="person", entity_id=pid)
    return pid


def update_person(db: Database, person_id: str, data: dict[str, Any], meta: RequestMeta) -> None:
    cur = _active(db, person_id)
    merged = {k: data.get(k, cur.get(k)) for k in ("role_title", "organisation_id", "remit_text", "remit_basis", "relationship_owner",
                                                    "notes", "next_action", "next_action_due")}
    with db.transaction() as tx:
        tx.run("rel_person_update", id=person_id, role=merged["role_title"], org=merged["organisation_id"],
               org_label=data.get("organisation_label", None if merged["organisation_id"] else cur.get("organisation")),
               remit=merged["remit_text"], remit_basis=merged["remit_basis"], owner=merged["relationship_owner"], notes=merged["notes"],
               next_action=merged["next_action"], next_action_due=merged["next_action_due"])
        audit(tx, "person_updated", meta, entity_type="person", entity_id=person_id, detail={"fields": sorted(data)})


def confirm_identity(db: Database, person_id: str, basis: str, source_url: str | None, meta: RequestMeta) -> None:
    _active(db, person_id)
    with db.transaction() as tx:
        tx.run("rel_person_confirm", id=person_id, basis=basis)
        tx.run("rel_evidence_add", person=person_id, supports="identity", kind="public_page" if source_url else "note", doc=None,
               url=source_url, quote=None, note=f"identity and role confirmed: {basis}", session_ref=meta.session_ref)
        audit(tx, "person_identity_confirmed", meta, entity_type="person", entity_id=person_id)


def set_linkedin_profile(db: Database, person_id: str, url: str | None, meta: RequestMeta) -> str | None:
    """Save the profile a person has checked is the right one. Only a member-profile URL is accepted."""
    p = _active(db, person_id)
    clean = None
    if url:
        try:
            clean = rel.normalise_profile_url(url)
        except ValueError as exc:
            raise RelationshipRejected(422, str(exc)) from exc
    with db.transaction() as tx:
        tx.run("rel_person_linkedin", id=person_id, url=clean)
        if clean:
            tx.run("rel_evidence_add", person=person_id, supports="identity", kind="public_page", doc=None, url=clean, quote=None,
                   note="LinkedIn profile checked and confirmed by a reviewer", session_ref=meta.session_ref)
            if p["state"] == "research_candidate":
                tx.run("rel_person_confirm", id=person_id, basis=f"LinkedIn profile checked and confirmed by a reviewer: {clean}")
        audit(tx, "person_linkedin_set", meta, entity_type="person", entity_id=person_id, detail={"cleared": clean is None})
    return clean


def add_evidence(db: Database, person_id: str, supports: str, url: str | None, note: str, meta: RequestMeta) -> None:
    _active(db, person_id)
    with db.transaction() as tx:
        tx.run("rel_evidence_add", person=person_id, supports=supports, kind="public_page" if url else "note", doc=None, url=url, quote=None,
               note=note, session_ref=meta.session_ref)
        tx.run("rel_person_verified", id=person_id)
        audit(tx, "person_evidence_added", meta, entity_type="person", entity_id=person_id, detail={"supports": supports})


def link_person(db: Database, opp_id: str, person_id: str, role: str | None, status: str | None, basis: str | None,
                meta: RequestMeta) -> None:
    _require(db.one("opportunity_get2", id=opp_id), "Opportunity")
    _active(db, person_id)
    with db.transaction() as tx:
        if not tx.run("rel_link_set", opp=opp_id, person=person_id, role=role, status=status, basis=basis):
            tx.run("rel_link_upsert", opp=opp_id, person=person_id, role=role or "unknown", basis=basis or "linked by a reviewer",
                   status=status or "relevant")
        audit(tx, "opportunity_person_linked", meta, entity_type="opportunity", entity_id=opp_id,
              detail={"person": person_id, "role": role, "status": status})


def record_relationship(db: Database, person_id: str, holder: str, nature: str, basis: str, meta: RequestMeta) -> str:
    """An existing relationship someone at WFC holds. Knowing the person also confirms who they are."""
    p = _active(db, person_id)
    if nature not in RELATIONSHIP_NATURES:
        raise RelationshipRejected(422, f"nature must be one of {', '.join(RELATIONSHIP_NATURES)}")
    with db.transaction() as tx:
        rid = str(tx.scalar("rel_relationship_add", person=person_id, holder=holder.strip(), nature=nature, basis=basis.strip(),
                            session_ref=meta.session_ref))
        if p["state"] == "research_candidate":
            tx.run("rel_person_confirm", id=person_id, basis=f"Known to {holder.strip()} ({nature.replace('_', ' ')}): {basis.strip()}")
        tx.run("rel_person_owner_if_empty", id=person_id, owner=holder.strip())       # the holder owns it unless an owner is set
        tx.run("rel_evidence_add", person=person_id, supports="relationship", kind="note", doc=None, url=None, quote=None,
               note=f"relationship recorded: {holder.strip()} — {basis.strip()}", session_ref=meta.session_ref)
        audit(tx, "relationship_recorded", meta, entity_type="person", entity_id=person_id, detail={"nature": nature})
    return rid


def set_relationship_status(db: Database, relationship_id: str, status: str, meta: RequestMeta) -> None:
    if status not in ("current", "lapsed"):
        raise RelationshipRejected(422, "status must be current or lapsed")
    with db.transaction() as tx:
        pid = _require(tx.scalar("rel_relationship_status", id=relationship_id, status=status), "Relationship")
        audit(tx, "relationship_status", meta, entity_type="person", entity_id=str(pid), detail={"status": status})


def add_route(db: Database, target_id: str, data: dict[str, Any], meta: RequestMeta) -> str:
    """A POSSIBLE introduction route. It becomes available only through confirm_route."""
    _active(db, target_id)
    if not data.get("introducer_person_id") and not data.get("introducer_label"):
        raise RelationshipRejected(422, "name the introducer (a person record or a description)")
    if data.get("introducer_person_id") == target_id:
        raise RelationshipRejected(422, "a person cannot introduce themselves")
    with db.transaction() as tx:
        iid = str(tx.scalar("rel_route_add", target=target_id, opp=data.get("opportunity_id"), introducer=data.get("introducer_person_id"),
                            introducer_label=data.get("introducer_label"), holder=data.get("wfc_holder_label"),
                            basis=data["connection_basis"].strip(), url=data.get("evidence_url"), notes=data.get("notes"),
                            session_ref=meta.session_ref))
        audit(tx, "introduction_route_added", meta, entity_type="person", entity_id=target_id)
    return iid


def update_route(db: Database, route_id: str, status: str, willingness_basis: str | None, notes: str | None, meta: RequestMeta) -> None:
    r = _require(db.one("rel_route_get", id=route_id), "Introduction route")
    if status not in ROUTE_STATUSES:
        raise RelationshipRejected(422, f"status must be one of {', '.join(ROUTE_STATUSES)}")
    willing = bool(r["willingness_confirmed"])
    basis = r["willingness_basis"]
    if status in ("available", "requested", "made") and not willing:
        if not willingness_basis or len(willingness_basis.strip()) < 10:
            raise RelationshipRejected(422, "an introduction is available only when the introducer's relationship with the target and "
                                            "their willingness to introduce are confirmed: record how this was confirmed")
        willing, basis = True, willingness_basis.strip()
    with db.transaction() as tx:
        tx.run("rel_route_update", id=route_id, status=status, willing=willing, willing_basis=basis, notes=notes)
        audit(tx, "introduction_route_status", meta, entity_type="person", entity_id=str(r["target_person_id"]), detail={"status": status})


def add_engagement(db: Database, person_id: str, data: dict[str, Any], meta: RequestMeta) -> str:
    _active(db, person_id)
    with db.transaction() as tx:
        eid = str(tx.scalar("rel_engagement_add", person=person_id, opp=data.get("opportunity_id"),
                            occurred_at=data.get("occurred_at") or datetime.now(timezone.utc), kind=data["kind"], summary=data["summary"],
                            owner=data.get("owner_label"), outcome=data.get("outcome"), next_step=data.get("next_step"),
                            direction=data.get("direction") or "outbound", session_ref=meta.session_ref))
        tx.run("rel_person_verified", id=person_id)
        audit(tx, "engagement_recorded", meta, entity_type="person", entity_id=person_id)
    return eid


# ===================================================================== opportunity relationship view
def opportunity_relationships(db: Database, opp_id: str) -> dict[str, Any]:
    opp = _require(db.one("opportunity_get2", id=opp_id), "Opportunity")
    orgs = db.all("opportunity_organisations", id=opp_id)
    countries = [g["country_code"] for g in db.all("opportunity_geo", id=opp_id)]
    linked = db.all("rel_opportunity_people", id=opp_id)
    for p in linked:
        p["state_label"] = rel.STATE_LABELS[p["state"]]
        p["linkedin_search_url"] = rel.linkedin_search_url(p["full_name"], p.get("organisation"))
        p["involvement_label"] = INVOLVEMENT_LABELS.get(p.get("involvement") or "unresolved")
    # press contacts and external advisers: kept with their actual role, never counted as commercial contacts (coverage, gaps, ranking)
    external = [p for p in linked if p.get("link_status") == "external_contact" or p.get("involvement") in ("press_contact", "external_adviser")]
    people = [p for p in linked if p not in external]
    at_org = db.all("rel_org_people_not_linked", id=opp_id)
    for p in at_org:
        p["state_label"] = rel.STATE_LABELS[p["state"]]
    roles: dict[str, list[dict[str, Any]]] = {}
    for r in db.all("rel_roles_for_opp", id=opp_id):
        r["affiliation_label"] = AFFILIATION_LABELS.get(r["affiliation"], r["affiliation"])
        roles.setdefault(str(r["person_id"]), []).append(r)
    for p in people:
        p["roles"] = roles.get(str(p["id"]), [])
    latest = db.one("rel_research_latest", id=opp_id)
    gaps, actions = rel.gaps_and_actions(opp["module"], [o["name"] for o in orgs], people + [dict(p, link_status="relevant") for p in at_org],
                                         researched=latest is not None)
    if latest and latest.get("outcome") == "incomplete":
        gaps.insert(0, "Relationship research is incomplete: see what remains under Research coverage")
        actions.insert(0, "Continue research")
    unresolved = [p for p in people if p.get("link_status") != "not_relevant" and not p.get("organisation")
                  and not any(r.get("organisation") and r["role_status"] != "former" for r in p["roles"])]
    if unresolved:
        gaps.append(f"{len(unresolved)} person(s) whose organisation no source establishes")
    open_dups = [d for d in db.all("dup_list", status="open", person=None)
                 if {str((d["a"] or {}).get("id")), str((d["b"] or {}).get("id"))} & {str(p["id"]) for p in people}]
    if open_dups:
        actions.append(f"Review {len(open_dups)} possible duplicate person record(s)")
    cov = rel.coverage(people + [dict(p, link_status="relevant") for p in at_org])
    routes = db.all("rel_routes_for_opp", id=opp_id)
    return {"organisations": orgs, "people": people, "external_contacts": external, "people_at_organisation": at_org, "coverage": cov.level,
            "coverage_label": rel.COVERAGE_LABELS[cov.level], "searches": search_suggestions(opp["module"], orgs, countries),
            "target_roles": [{"key": r.key, "label": r.label} for r in rel.target_roles(opp["module"])],
            "latest_research": latest, "gaps": gaps, "actions": actions,
            "documents": db.all("rdoc_for_opp", id=opp_id, disc=None, org=None),
            "relationships": db.all("rel_relationships_for_opp", id=opp_id),
            "routes_available": [r for r in routes if r["status"] in ("available", "requested", "made")],
            "routes_possible": [r for r in routes if r["status"] == "possible"],
            "duplicates": open_dups,
            "engagements": db.all("rel_engagements_for_opportunity", id=opp_id),
            "linkedin_integration": "Not connected: search links only"}


# ===================================================================== possible duplicates and reversible merges
def duplicates(db: Database, status: str | None = "open") -> list[dict[str, Any]]:
    return db.all("dup_list", status=status, person=None)


def dismiss_duplicate(db: Database, dup_id: str, note: str | None, meta: RequestMeta) -> None:
    d = _require(db.one("dup_get", id=dup_id), "Possible duplicate")
    if d["status"] == "merged":
        raise RelationshipRejected(409, "this pair was merged: undo the merge first")
    with db.transaction() as tx:
        tx.run("dup_decide", id=dup_id, status="dismissed", note=(note or "").strip() or "different people")
        audit(tx, "person_duplicate_dismissed", meta, entity_type="person", entity_id=str(d["person_a"]), detail={"duplicate": dup_id})


def merge_people(db: Database, keep_id: str, merge_id: str, note: str | None, meta: RequestMeta, *, duplicate_id: str | None = None) -> str:
    """Merge `merge_id` into `keep_id`. Every moved row is listed in person_merges.moved and the kept record's previous
    fields are kept, so the merge can be undone exactly. Evidence is retained, never deleted."""
    if keep_id == merge_id:
        raise RelationshipRejected(422, "choose two different people")
    keep = _require(db.one("rel_person_get", id=keep_id), "Person")
    other = _require(db.one("rel_person_get", id=merge_id), "Person")
    if keep.get("merged_into_id") or other.get("merged_into_id"):
        raise RelationshipRejected(409, "one of these records is already merged")
    with db.transaction() as tx:
        snap = tx.one("merge_snapshot", k=keep_id, m=merge_id)
        tx.scalar("merge_move", k=keep_id, m=merge_id)
        tx.run("merge_fill_kept", k=keep_id, m=merge_id)
        _require(tx.scalar("merge_mark", k=keep_id, m=merge_id), "Person")
        mid = str(tx.scalar("merge_insert", k=keep_id, m=merge_id, dup=duplicate_id, moved=json.dumps(snap["moved"]),
                            kept_before=json.dumps(snap["kept_before"]), note=(note or "").strip() or None, session_ref=meta.session_ref))
        if duplicate_id:
            tx.run("dup_decide", id=duplicate_id, status="merged", note=(note or "").strip() or "same person")
        audit(tx, "people_merged", meta, entity_type="person", entity_id=keep_id, detail={"merged": merge_id, "merge": mid})
    return mid


def merge_duplicate(db: Database, dup_id: str, keep_id: str, note: str | None, meta: RequestMeta) -> str:
    d = _require(db.one("dup_get", id=dup_id), "Possible duplicate")
    if d["status"] != "open":
        raise RelationshipRejected(409, f"this pair is already {d['status']}")
    pair = {str(d["person_a"]), str(d["person_b"])}
    if keep_id not in pair:
        raise RelationshipRejected(422, "keep one of the two records in this pair")
    (other,) = pair - {keep_id}
    return merge_people(db, keep_id, other, note, meta, duplicate_id=dup_id)


def undo_merge(db: Database, merge_id: str, meta: RequestMeta) -> None:
    m = _require(db.one("merge_get", id=merge_id), "Merge")
    if m["undone_at"]:
        raise RelationshipRejected(409, "this merge was already undone")
    moved = m["moved"] if isinstance(m["moved"], dict) else json.loads(m["moved"])
    k, x = str(m["kept_person_id"]), str(m["merged_person_id"])
    with db.transaction() as tx:
        tx.scalar("unmerge_rows", k=k, m=x, ev=json.dumps(moved.get("evidence", [])), ro=json.dumps(moved.get("roles", [])),
                  re=json.dumps(moved.get("relationships", [])), rt=json.dumps(moved.get("routes_target", [])),
                  ri=json.dumps(moved.get("routes_introducer", [])), en=json.dumps(moved.get("engagements", [])))
        for link in moved.get("links", []):
            if not link.get("kept_had_link"):
                tx.run("unmerge_link_remove_kept", opp=link["opportunity_id"], k=k)
            tx.run("unmerge_link_restore", opp=link["opportunity_id"], m=x, role=link["role"], basis=link["basis"], status=link["status"],
                   added_at=link["added_at"])
        before = m["kept_before"] if isinstance(m["kept_before"], dict) else json.loads(m["kept_before"])
        tx.run("unmerge_restore_kept", k=k, b=json.dumps(before))
        _require(tx.scalar("unmerge_mark", k=k, m=x), "Merged person")
        tx.run("merge_undone", id=merge_id)
        if m.get("duplicate_id"):
            tx.run("dup_decide", id=str(m["duplicate_id"]), status="open", note=None)
        audit(tx, "people_merge_undone", meta, entity_type="person", entity_id=k, detail={"restored": x, "merge": merge_id})


# ===================================================================== light workspace
def set_progress(db: Database, opp_id: str, to: str, reason: str | None, closed_reason: str | None, meta: RequestMeta) -> None:
    from ..domain.overview import PROGRESS
    if to not in PROGRESS:
        raise RelationshipRejected(422, f"progress must be one of {', '.join(PROGRESS)}")
    cur = _require(db.one("opportunity_get2", id=opp_id), "Opportunity")
    if cur["progress"] == to:
        return
    with db.transaction() as tx:
        tx.run("ws_progress_set", id=opp_id, to=to, closed_reason=closed_reason)
        tx.run("opportunity_history_add", id=opp_id, field="progress", **{"from": cur["progress"]}, to=to, reason=reason or closed_reason,
               session_ref=meta.session_ref)
        audit(tx, "opportunity_progress", meta, entity_type="opportunity", entity_id=opp_id, detail={"to": to})


def set_saved(db: Database, opp_id: str, saved: bool, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        _require(tx.scalar("ws_saved_set", id=opp_id, saved=saved), "Opportunity")
        tx.run("opportunity_history_add", id=opp_id, field="saved", **{"from": None}, to="saved" if saved else "unsaved", reason=None,
               session_ref=meta.session_ref)


def set_owner(db: Database, opp_id: str, owner: str | None, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        _require(tx.scalar("ws_owner_set", id=opp_id, owner=(owner or "").strip() or None), "Opportunity")
        tx.run("opportunity_history_add", id=opp_id, field="owner", **{"from": None}, to=(owner or "").strip() or "(none)", reason=None,
               session_ref=meta.session_ref)


def set_next_action(db: Database, opp_id: str, action: str | None, due: date | None, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        _require(tx.scalar("ws_next_action_set", id=opp_id, action=(action or "").strip() or None, due=due), "Opportunity")
        tx.run("opportunity_history_add", id=opp_id, field="next_action", **{"from": None}, to=(action or "").strip() or "(cleared)",
               reason=str(due) if due else None, session_ref=meta.session_ref)


def add_note(db: Database, opp_id: str, body: str, author: str | None, meta: RequestMeta) -> str:
    _require(db.one("opportunity_get2", id=opp_id), "Opportunity")
    with db.transaction() as tx:
        nid = str(tx.scalar("ws_note_add", id=opp_id, body=body.strip(), author=(author or "").strip() or None, session_ref=meta.session_ref))
        audit(tx, "opportunity_note", meta, entity_type="opportunity", entity_id=opp_id)
    return nid


def track_signal(db: Database, signal_id: str, meta: RequestMeta) -> str:
    """A market signal the team decides to pursue becomes a commercial opportunity. The signal's evidence stays attached and
    what is still unconfirmed stays visible; nothing about it becomes a tender."""
    sig = _require(db.one("record_signal_get", id=signal_id), "Signal")
    if sig["opportunity_id"]:
        return str(sig["opportunity_id"])
    if sig["record_type"] == "excluded":
        raise RelationshipRejected(409, "this record is outside the freight scope; review its scope before tracking it")
    with db.transaction() as tx:
        oid = str(tx.scalar("ws_track_signal", signal=signal_id))
        tx.run("ws_track_geo", opp=oid, signal=signal_id)
        tx.run("opportunity_history_add", id=oid, field="record_type", **{"from": sig["record_type"]}, to="commercial",
               reason="market signal tracked as a commercial opportunity", session_ref=meta.session_ref)
        audit(tx, "signal_tracked", meta, entity_type="opportunity", entity_id=oid, detail={"signal": signal_id})
    return oid


def set_involvement(db: Database, person_id: str, involvement: str, basis: str, meta: RequestMeta) -> dict[str, Any]:
    """A person's correction of someone's involvement (employee, appointed representative, external adviser, press contact, unresolved).
    It is never changed by later research; the person's opportunity links follow (external contact or candidate), except where a person
    already marked the link relevant or not relevant."""
    from ..domain import involvement as inv
    if involvement not in inv.INVOLVEMENTS:
        raise RelationshipRejected(422, f"involvement must be one of {', '.join(inv.INVOLVEMENTS)}")
    if not basis or len(basis.strip()) < 10:
        raise RelationshipRejected(422, "say what was checked and where (at least 10 characters)")
    with db.transaction() as tx:
        if not tx.scalar("person_involvement_by_person", id=person_id, inv=involvement, basis=f"set by a person: {basis.strip()}"):
            raise RelationshipRejected(404, "Person not found")
        moved = tx.all("opp_links_external_sync", id=person_id)
        tx.scalar("rel_evidence_add2", person=person_id, supports="relevance", kind="note", doc=None, rdoc=None, url=None, quote=None,
                  note=f"involvement set by a person: {inv.LABELS[involvement]} — {basis.strip()}", session_ref=meta.session_ref)
    audit(db, "person_involvement_set", meta, entity_type="person", entity_id=person_id, detail={"involvement": involvement, "links": len(moved)})
    return {"involvement": involvement, "involvement_label": inv.LABELS[involvement], "opportunity_links_updated": len(moved)}
