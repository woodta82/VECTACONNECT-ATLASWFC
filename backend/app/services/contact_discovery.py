"""Open-market contact discovery (29 Oct 2026: the ATLAS v1.0 "discover new contacts" parameters for WFC).

A standalone search for contacts, not tied to one tender: by organisation, country or region, WFC capability area (the
nine areas of the WFC brief) and a role focus. It reads, through the same evidence rules as opportunity research:
1. the organisation's own pages when it is a known record with a website, newsroom or leadership page recorded, and the
   leadership, team, board and newsroom links on them (same site, robots.txt respected);
2. the results of the authorised web search for the brief's queries (target roles of the capability area, appointment
   announcements, leadership pages; the country narrows them). Without a connector nothing is searched: the queries are
   listed as not run, with links a person can open.

Every person recorded carries the passage that names them and, when the passage binds it, their title and organisation
(`domain/attribution.py`); identity is never merged on a name alone. Each is scored for relevance to the brief
(`domain/contact_relevance.py`), with every point explained. ATLAS v1.0 asked an AI researcher with web search for named
people and a candid score; here the names come only from pages ATLAS fetched and read, never from the model's memory. A
contact's LinkedIn link is a search a person opens; no profile is fetched and nothing is sent to anyone.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..ai import extraction as ai_extraction
from ..config import Settings
from ..connectors import search as web_search
from ..domain import contact_relevance as cr
from ..domain import overview as ov
from ..domain import research_plan as plan
from ..domain import retrieval
from ..domain import company_intel as ci
from ..reference.airports import airport
from ..reference.geography import COUNTRIES, REGIONS
from ..repo.db import Database
from .audit import RequestMeta, audit
from . import company_intelligence as cmp
from . import relationship_research as rr

MAX_COUNTRIES = 5
PURPOSES = ("people", "companies")
PURPOSE_LABELS = {"people": "People", "companies": "Companies"}


class DiscoveryRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _brief_text(org: str | None, countries: list[str], region: str | None, module: str | None, role_focus: str | None,
                purpose: str = "people", brief: str | None = None, airport_iata: str | None = None, kinds: list[str] | None = None) -> str:
    parts = []
    if brief:
        parts.append(brief.strip())
    if purpose == "companies":
        parts.append("Purpose: companies" + (f" ({', '.join(ci.KIND_LABELS.get(k, k) for k in kinds)})" if kinds else ""))
    if airport_iata:
        ap = airport(airport_iata)
        parts.append(f"Airport: {ap[0]} ({airport_iata})" if ap else f"Airport: {airport_iata}")
    if org:
        parts.append(f"Organisation: {org}")
    if region:
        parts.append(f"Region: {REGIONS[region][0]}")
    elif countries:
        parts.append("Countries: " + ", ".join(COUNTRIES[c][0] for c in countries))
    if module:
        parts.append(f"WFC capability area: {ov.CATEGORY_LABELS.get(module, module)}")
    if role_focus:
        parts.append(f"Role focus: {role_focus}")
    return "; ".join(parts) or ("General search for cargo organisations" if purpose == "companies" else
                                "General search for senior cargo and commercial contacts")


def start(db: Database, settings: Settings, data: dict[str, Any], meta: RequestMeta, *, fetch: rr.Fetch | None = None,
          transport: ai_extraction.Transport | None = None, search_transport: web_search.Transport | None = None) -> dict[str, Any]:
    purpose = (data.get("purpose") or "people").strip().lower()
    if purpose not in PURPOSES:
        raise DiscoveryRejected(422, "purpose must be people or companies")
    brief_text = " ".join((data.get("brief") or "").split())[:600] or None
    airport_iata = (data.get("airport_iata") or "").strip().upper() or None
    if airport_iata and not airport(airport_iata):
        raise DiscoveryRejected(422, f"airport {airport_iata} is not in the reference list (use the IATA code of a major cargo airport)")
    kinds = [k for k in (data.get("organisation_kinds") or []) if k]
    if any(k not in ci.KIND_LABELS for k in kinds):
        raise DiscoveryRejected(422, "unknown organisation kind")
    org_label = (data.get("organisation_name") or "").strip() or None
    module = data.get("capability_area") or None
    role_focus = (data.get("role_focus") or "").strip() or None
    region = (data.get("region") or "").strip().upper() or None
    countries = [c.strip().upper() for c in (data.get("countries") or []) if c and c.strip()]
    if region and region not in REGIONS:
        raise DiscoveryRejected(422, f"unknown region code {region}")
    if any(c not in COUNTRIES for c in countries):
        raise DiscoveryRejected(422, "unknown country code")
    if region:
        countries = list(REGIONS[region][2])
    if airport_iata and not countries and not region:
        countries = [airport(airport_iata)[2]]
    if not (org_label or countries or role_focus or brief_text):
        raise DiscoveryRejected(422, "give a brief, an organisation, a country or region, or a role focus")
    if module and module not in ov.CATEGORY_LABELS:
        raise DiscoveryRejected(422, "unknown capability area")
    org_row = None
    if org_label:
        oid = db.scalar("org_find_for_person", name=org_label, norm=re.sub(r"[^a-z0-9]", "", org_label.lower()))
        org_row = db.one("org_get_for_research", id=str(oid)) if oid else None
    brief = _brief_text((org_row or {}).get("name") or org_label, countries[:MAX_COUNTRIES], region, module, role_focus, purpose, brief_text,
                        airport_iata, kinds)
    disc_id = str(db.scalar("disc_insert", org=str(org_row["id"]) if org_row else None, org_label=None if org_row else org_label,
                            countries=countries[:MAX_COUNTRIES], region=region, module=module, role_focus=role_focus, brief=brief,
                            by=data.get("requested_by_label"), session_ref=meta.session_ref, purpose=purpose, brief_text=brief_text,
                            airport=airport_iata, kinds=kinds))
    audit(db, "contact_discovery_started", meta, entity_type="discovery", entity_id=disc_id,
          detail={"brief": brief, "purpose": purpose, "organisation": bool(org_row), "countries": countries[:MAX_COUNTRIES]})
    return _run(db, settings, disc_id, meta, mode="start", fetch=fetch, transport=transport, search_transport=search_transport)


def continue_(db: Database, settings: Settings, disc_id: str, meta: RequestMeta, *, fetch: rr.Fetch | None = None,
              transport: ai_extraction.Transport | None = None, search_transport: web_search.Transport | None = None) -> dict[str, Any]:
    if not db.one("disc_get", id=disc_id):
        raise DiscoveryRejected(404, "Discovery not found")
    db.scalar("disc_reopen", id=disc_id)
    return _run(db, settings, disc_id, meta, mode="continue", fetch=fetch, transport=transport, search_transport=search_transport)


def _run(db: Database, settings: Settings, disc_id: str, meta: RequestMeta, *, mode: str, fetch: rr.Fetch | None,
         transport: ai_extraction.Transport | None, search_transport: web_search.Transport | None) -> dict[str, Any]:
    d = db.one("disc_get", id=disc_id)
    orgs = []
    if d["organisation_id"]:
        o = db.one("org_get_for_research", id=str(d["organisation_id"]))
        if o:
            orgs = [dict(o, involvement="named in the brief")]
    org_names = [o["name"] for o in orgs] or ([d["organisation"]] if d["organisation"] else [])
    run = rr._Run(None, meta, org_names, org_names[:1], orgs, disc_id=disc_id, company_mode=(d["purpose"] == "companies"))
    fetch = fetch or (lambda url: retrieval.fetch(url, allow_private_hosts=frozenset(settings.retrieval_allow_private_hosts)))
    countries = list(d["countries"] or [])
    if mode == "start":
        rr._queue_org_pages(db, run)
        if d["organisation"] and not orgs:
            run.unavailable.append({"method": "organisation_website",
                                    "reason": f"{d['organisation']} is not a known organisation record: its own pages were not read; "
                                              "the web search covers it when a connector is configured"})
        if d["purpose"] == "companies" or d.get("brief_text"):
            queries = ci.build_purpose_queries(purpose=d["purpose"], brief=d.get("brief_text"), countries=countries[:2] or [None],
                                               country_names={c: v[0] for c, v in COUNTRIES.items()},
                                               modules=[d["capability_area"]] if d["capability_area"] else [],
                                               kinds=ci.kinds_for([d["capability_area"]] if d["capability_area"] else [], list(d.get("organisation_kinds") or [])),
                                               airport_iata=d.get("airport_iata"), organisation=d["organisation"],
                                               max_per_country=max(settings.search_max_queries, 1))
            if d["purpose"] == "people" and d["role_focus"]:
                queries = plan.build_discovery_queries(module=d["capability_area"], organisation=d["organisation"],
                                                       countries=[c for c in (rr._country_name(c) for c in countries[:2]) if c],
                                                       role_focus=d["role_focus"], limit=max(settings.search_max_queries, 1))[:2] + queries
        else:
            queries = plan.build_discovery_queries(module=d["capability_area"], organisation=d["organisation"],
                                                   countries=[c for c in (rr._country_name(c) for c in countries[:2]) if c],
                                                   role_focus=d["role_focus"], limit=max(settings.search_max_queries, 1))
        searches = rr._run_searches(db, settings, run, queries, countries, search_transport)
    else:
        searches = list(d.get("searches") or [])
        db.all("rdoc_requeue_failed", id=None, disc=disc_id)
    ai_reason = ai_extraction.available(settings)
    if ai_reason:
        run.unavailable.append({"method": "configured_extractor", "reason": ai_reason})
    rr._read_everything(db, settings, run, fetch, transport, ai_reason)
    organisations: list[dict[str, Any]] = []
    if d["purpose"] == "companies":
        organisations = cmp.record_organisations(db, run, d)
        # the organisations just recorded become known to the run: their own sites are read (profile, airlines, leadership and
        # contact pages followed), then the pages are read again for organisations and for people bound to them
        new = [o for o in organisations if o["name"] not in run.org_names]
        if new:
            run.org_names = run.org_names + [o["name"] for o in new]
            added = [{"id": o["id"], "name": o["name"], "website": db.scalar("org_website", id=o["id"]), "newsroom_url": None, "leadership_url": None}
                     for o in new]
            run.orgs = run.orgs + added
            with_site = [o for o in added if o["website"]]
            if with_site and not run.limits_hit:
                saved = run.orgs
                run.orgs = with_site
                rr._queue_org_pages(db, run)
                run.orgs = saved
                rr._read_everything(db, settings, run, fetch, transport, ai_reason)
                organisations = cmp.record_organisations(db, run, d)
            for rd in db.all("rdoc_bodies", disc=disc_id):
                rr._read_rules(db, run, rd, rd.get("body_text") or "", page_url=rd.get("url"))
                db.run("rdoc_people", id=str(rd["id"]))
        cmp.score_organisations(db, d)
    run.unavailable.append({"method": "linkedin_profiles",
                            "reason": "no authorised LinkedIn integration is connected: a LinkedIn search link is offered per contact, "
                                      "and a profile is saved only when a person confirms it"})
    # relevance to the brief, for every person this discovery recorded
    for p in db.all("disc_people", id=disc_id):
        rel_countries = [c for c in ([p.get("organisation_country")] + list(p.get("remit_countries") or [])) if c]
        r = cr.score(role_title=p.get("role_title"), organisation=p.get("organisation"), organisation_kind=p.get("organisation_kind"),
                     countries=rel_countries, brief_module=d["capability_area"], brief_organisation=d["organisation"],
                     brief_countries=countries, brief_role_focus=d["role_focus"], binding=p.get("binding"), page_kind=p.get("page_kind"))
        db.run("disc_person_relevance", disc=disc_id, person=str(p["person_id"]), score=r["score"], relevance=r)
        if d["capability_area"]:
            db.run("person_set_capability_area", id=str(p["person_id"]), module=d["capability_area"])
    cov = rr.coverage(db, None, ai_connected=ai_reason is None, searches=searches, disc_id=disc_id)
    cov["limits_hit"] = sorted(set(run.limits_hit))
    cov["duplicates_flagged"] = run.duplicates
    people = db.all("disc_people", id=disc_id)
    docs = db.all("rdoc_for_opp", id=None, disc=disc_id)
    read_any = any(x["status"] in ("read", "partial") for x in docs)
    ran_any = any(s["status"] == "run" for s in searches)
    incomplete = bool(cov["remaining"]) or bool(run.limits_hit)
    found = bool(organisations or (d["purpose"] == "companies" and int(d.get("organisations_found") or 0))) if d["purpose"] == "companies" else bool(people)
    if not read_any and not ran_any and not docs:
        outcome = "not_run"
    elif d["purpose"] == "companies":
        outcome = "incomplete" if incomplete else ("companies_found" if found else "no_companies_found")
    else:
        outcome = "incomplete" if incomplete else ("people_found" if people else "no_people_found")
    methods = []
    read = {x["origin"] for x in docs if x["status"] in ("read", "partial")}
    if read & {"organisation_page", "followed_link", "guessed_page"}:
        methods.append("organisation_pages")
    if "search_result" in read or ran_any:
        methods.append("web_search")
    methods.append("rules")
    if ai_reason is None and any(int(x["ai_sections_read"]) for x in docs):
        methods.append("configured_extractor")
    db.run("disc_finish", id=disc_id, outcome=outcome, methods=methods, unavailable=rr._dedupe(run.unavailable), coverage=cov, searches=searches,
           cost=str(run.cost))
    audit(db, "contact_discovery_run", meta, entity_type="discovery", entity_id=disc_id,
          detail={"outcome": outcome, "purpose": d["purpose"], "people": len(people), "organisations": len(organisations), "fetches": run.fetches,
                  "cost_usd": str(run.cost)})
    return detail(db, disc_id)


def detail(db: Database, disc_id: str) -> dict[str, Any]:
    d = db.one("disc_get", id=disc_id)
    if d is None:
        raise DiscoveryRejected(404, "Discovery not found")
    people = db.all("disc_people", id=disc_id)
    from ..domain import relationships as rel
    for p in people:
        p["linkedin_search_url"] = rel.linkedin_search_url(p["full_name"], p.get("organisation"))
        p["state_label"] = rel.STATE_LABELS.get(p.get("state") or "research_candidate", "Research candidate")
    docs = db.all("rdoc_for_opp", id=None, disc=disc_id)
    _label(d)
    organisations = db.all("disc_orgs", id=disc_id) if d["purpose"] == "companies" else []
    for o in organisations:
        o["kind_label"] = ci.KIND_LABELS.get(o["kind"], o["kind"])
        o["carrier_type_label"] = ci.CARRIER_LABELS.get(o.get("carrier_type") or "", None)
        o["country_name"] = COUNTRIES.get(o.get("country") or "", (None,))[0]
        for r in o.get("relationships") or []:
            r["relationship_label"] = ci.RELATIONSHIP_LABELS.get(r["relationship"], r["relationship"])
    actions = []
    if d["outcome"] == "incomplete":
        actions.append("Continue the discovery to read the remaining pages")
    if d["outcome"] == "not_run":
        actions.append("Open the listed web searches yourself, or record the organisation's website so its pages can be read")
    if any(s["status"] == "not_run" for s in (d["searches"] or [])):
        actions.append("Configure the authorised search connector to run the listed searches")
    if people:
        actions.append("Confirm the identity and role of the contacts worth pursuing, then record who at WFC knows them")
    if organisations:
        actions.append("Open each company worth pursuing: check its website and published addresses, confirm or mark as lapsed any representation, "
                       "then record a potential opportunity only with your interpretation")
    rule = (cr.__doc__.split("\n\n")[1].strip().replace("\n", " ") if d["purpose"] == "people" else
            "Companies are recorded only from pages that were read, with the passage naming them; a relevant company is not an opportunity.")
    return {**d, "people": people, "organisations": organisations, "documents": docs, "actions": actions, "rule": rule}


def _label(d: dict[str, Any]) -> None:
    d["capability_area_label"] = ov.CATEGORY_LABELS.get(d["capability_area"] or "", None)
    d["countries_named"] = [COUNTRIES.get(c, (c,))[0] for c in (d["countries"] or [])]
    d["region_name"] = REGIONS[d["region_code"]][0] if d.get("region_code") in REGIONS else None
    d["purpose_label"] = PURPOSE_LABELS.get(d.get("purpose") or "people", "People")
    ap = airport(d.get("airport_iata"))
    d["airport_name"] = ap[0] if ap else None
    d["organisation_kind_labels"] = [ci.KIND_LABELS.get(k, k) for k in (d.get("organisation_kinds") or [])]


def list_discoveries(db: Database, limit: int = 20, purpose: str | None = None) -> list[dict[str, Any]]:
    out = db.all("disc_list", limit=limit, purpose=purpose)
    for d in out:
        _label(d)
        for k in ("unavailable", "coverage", "searches"):
            d.pop(k, None)
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)
