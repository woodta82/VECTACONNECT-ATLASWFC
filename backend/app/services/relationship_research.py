"""Opportunity-led relationship research (instruction of 28 Oct 2026, second continuation, items 1–4).

What a research run reads, in order, recording each document and what happened to it (`research_documents`):
1. the opportunity's own source documents (text retained only where the source permits);
2. URLs and documents a person added for this opportunity;
3. pages of the organisations involved: the website, newsroom and leadership pages recorded for them, and the links on
   those pages that lead to leadership, management, team and board pages, the newsroom and relevant news items (same site).
   Fixed addresses are tried only when a site offers no such links, and are labelled as guessed;
4. results of the configured, authorised web search (queries built from the opportunity, its organisations, geography and
   target roles). When no search connector is configured, nothing is searched: the queries are listed as not run, with
   links a person can open.

Each document is read in sections. The rules read every section once the document is fetched. The configured AI
extractor, when connected, reads sections under the budget controls; reading stops at the per-run or budget limit and
resumes on the next run. Fetching is limited per run as well. Everything not yet done is shown as remaining work, and a
run with remaining work, failed fetches or unread sections is reported as INCOMPLETE — never as "no people found".

People are recorded only with a passage that binds them to a role and/or an organisation (`domain/attribution.py`).
Identity: the same passage (also the identical statement republished in another document of the same opportunity), or the
same name at the same KNOWN organisation, is the same person. A name alone never merges records when the organisation is
unknown: a new record is created and the pair is queued for duplicate review.
Nothing is sent to anyone; robots.txt is respected for every page fetched for research.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlsplit

from ..ai import extraction as ai_extraction
from ..ai import people as ai_people
from ..config import Settings
from ..connectors import search as web_search
from ..domain import attribution as attr
from ..domain import content, retrieval
from ..domain import relationships as rel
from ..domain import research_plan as plan
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit

MAX_FETCHES_PER_RUN = 15
MAX_AI_SECTIONS_PER_RUN = 6
MAX_BODY_CHARS = 400_000
ROBOTS_UA = "VECTA-Connect-ATLAS"

Fetch = Callable[[str], retrieval.FetchResult]


class ResearchRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class _Run:
    opp_id: str | None                      # opportunity-led research, or
    meta: RequestMeta
    org_names: list[str]
    subject: list[str]
    orgs: list[dict[str, Any]]
    disc_id: str | None = None              # an open-market contact discovery (29 Oct 2026)
    fetches: int = 0
    ai_sections: int = 0
    cost: Decimal = Decimal("0")
    found: list[dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0
    unavailable: list[dict[str, str]] = field(default_factory=list)
    limits_hit: list[str] = field(default_factory=list)
    robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)
    ai_rejected: list[str] = field(default_factory=list)


def _country_name(code: str | None) -> str | None:
    return COUNTRIES.get(code, (None,))[0] if code else None


def _scope(run: _Run) -> dict[str, Any]:
    """Query parameters selecting this run's research documents: the opportunity's or the discovery's."""
    return {"id": run.opp_id, "disc": run.disc_id}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _same_site(url: str, site: str | None) -> bool:
    if not site:
        return False
    a, b = (urlsplit(url).hostname or "").lower(), (urlsplit(site).hostname or "").lower()
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return bool(a) and strip(a) == strip(b)


def _org_resolve(db: Database, run: _Run, name: str | None) -> tuple[str | None, str | None]:
    """(organisation id, label) for an organisation named in the text: an involved organisation or a known record by name or
    alias; otherwise the name as written (a label), never guessed."""
    if not name:
        return None, None
    for o in run.orgs:
        if o["name"] and o["name"].lower() == name.lower():
            return str(o["id"]), None
    oid = db.scalar("org_find_for_person", name=name, norm=re.sub(r"[^a-z0-9]", "", name.lower()))
    return (str(oid), None) if oid else (None, name)


# ===================================================================== recording one mention
def record_mention(tx: Database, run: _Run, m: attr.Mention, *, kind: str, document_id: str | None, rdoc_id: str | None,
                   url: str | None, method: str, source: str = "rules", extra_note: str | None = None) -> tuple[str, bool]:
    name = " ".join(m.name.split())
    org_id, org_label = _org_resolve(tx, run, m.organisation)
    # identity: the same passage first, then the same name at the same KNOWN organisation; never the name alone
    pid = tx.scalar("rel_person_by_passage", name=name, kind=kind, doc=document_id, rdoc=rdoc_id, url=url, quote=m.quote)
    if pid is None and run.opp_id:
        pid = tx.scalar("rel_person_by_statement_on_opp", name=name, opp=run.opp_id, quote=m.quote)
    if pid is None and (org_id or org_label):
        pid = tx.scalar("rel_person_by_name_org", name=name, org=org_id, org_label=org_label)
    created = pid is None
    if created:
        current = m.role_status == "current"
        pid = tx.scalar("rel_person_insert", name=name, role=m.role if current else None, org=org_id if current else None,
                        org_label=org_label if current else None,
                        origin="discovery" if run.disc_id else ("document" if kind == "source_document" else "research"),
                        remit=None, remit_countries=None, notes=None)
        for other in tx.all("rel_people_same_name", id=str(pid), name=name):
            known_both = bool((org_id or org_label) and (other["organisation_id"] or other["organisation_label"]))
            reason = ("same name; different organisations recorded" if known_both else
                      "same name; organisation not established for one or both records")
            if tx.scalar("dup_add", a=str(other["id"]), b=str(pid), reason=reason, session_ref=run.meta.session_ref):
                run.duplicates += 1
    pid = str(pid)
    if m.role_status == "current":
        tx.run("rel_person_role_if_empty", id=pid, role=m.role)
        if org_id or org_label:
            tx.run("rel_person_org_if_empty", id=pid, org=org_id, org_label=org_label)
    note = f"found by {method}" + (f"; {extra_note}" if extra_note else "")
    ev_kind = {"rules": "", "ai": " (configured AI extractor; binding confirmed by the rules)"}.get(source, "")
    rel_ev = tx.scalar("rel_evidence_add2", person=pid, supports="relevance", kind=kind, doc=document_id, rdoc=rdoc_id, url=url,
                       quote=m.quote, note=note + ev_kind, session_ref=run.meta.session_ref)
    role_ev = None
    if m.role:
        role_ev = tx.scalar("rel_evidence_add2", person=pid, supports="role", kind=kind, doc=document_id, rdoc=rdoc_id, url=url,
                            quote=m.quote, note=f"{m.binding}{ev_kind}", session_ref=run.meta.session_ref)
    if m.organisation:
        tx.scalar("rel_evidence_add2", person=pid, supports="organisation", kind=kind, doc=document_id, rdoc=rdoc_id, url=url,
                  quote=m.org_quote or m.quote, note=f"{attr.AFFILIATION_LABELS[m.affiliation]}: {m.organisation} — {m.binding}{ev_kind}",
                  session_ref=run.meta.session_ref)
    if m.role or m.organisation:
        tx.scalar("rel_role_add", person=pid, role=m.role, org=org_id, org_label=org_label, status=m.role_status,
                  affiliation=m.affiliation, binding=m.binding, evidence=str(role_ev or rel_ev), source=source)
    if m.role_status != "former" and run.opp_id:
        tx.run("rel_link_upsert", opp=run.opp_id, person=pid, role=m.role_on_opportunity, basis=m.relevance_basis, status="candidate")
    if run.disc_id:
        tx.run("disc_person_link", disc=run.disc_id, person=pid, new=created)
    run.found.append({"person_id": pid, "name": name, "role": m.role, "role_status": m.role_status, "organisation": m.organisation,
                      "affiliation": m.affiliation, "affiliation_label": attr.AFFILIATION_LABELS[m.affiliation], "binding": m.binding,
                      "new": created, "method": method, "source": url})
    return pid, created


# ===================================================================== queueing
def _queue(db: Database, run: _Run, *, origin: str, url: str | None = None, source_doc: str | None = None, org_id: str | None = None,
           title: str | None = None, page_kind: str = "other", found_via: str | None = None, body: str | None = None,
           status: str = "queued", reason: str | None = None) -> str | None:
    if url and not urlsplit(url).path:
        url = url + "/"                                   # https://example.com and https://example.com/ are the same page
    rid = db.scalar("rdoc_add", opp=run.opp_id, disc=run.disc_id, org=org_id, origin=origin, url=url, source_doc=source_doc, title=title,
                    page_kind=page_kind, found_via=found_via, status=status, reason=reason, body=body[:MAX_BODY_CHARS] if body else None,
                    sha=_sha(body) if body else None, session_ref=run.meta.session_ref)
    return str(rid) if rid else None


def add_user_source(db: Database, opp_id: str, *, url: str | None, title: str | None, text: str | None, meta: RequestMeta,
                    organisation_id: str | None = None) -> str:
    """A person adds a relevant URL or document for research. A URL is fetched at the next run (robots.txt respected); a
    document's text is read as supplied."""
    if not db.one("opportunity_get2", id=opp_id):
        raise ResearchRejected(404, "Opportunity not found")
    if not url and not (text and text.strip()):
        raise ResearchRejected(422, "give a URL or a document")
    if url and not re.match(r"^https?://[^\s]+$", url):
        raise ResearchRejected(422, "the URL must start with http:// or https://")
    run = _Run(opp_id, meta, [], [], [])
    if url:
        rid = _queue(db, run, origin="user_url", url=url.strip(), org_id=organisation_id, title=title, page_kind=attr.page_kind(url, title),
                     found_via="added by a reviewer")
    else:
        body = (text or "").strip()
        rid = _queue(db, run, origin="user_document", org_id=organisation_id, title=title or "Document added by a reviewer",
                     page_kind="document", found_via="added by a reviewer", body=body)
    if rid is None:
        raise ResearchRejected(409, "this URL or document is already part of this opportunity's research")
    audit(db, "research_source_added", meta, entity_type="opportunity", entity_id=opp_id, detail={"url": url, "document": url is None})
    return rid


def _enqueue_start(db: Database, settings: Settings, run: _Run, opp: dict[str, Any], countries: list[str],
                   search_transport: web_search.Transport | None) -> list[dict[str, Any]]:
    # 1. the opportunity's own documents
    docs = db.all("opportunity_documents", id=run.opp_id)
    for d in docs:
        if d.get("body_text"):
            _queue(db, run, origin="opportunity_source", source_doc=str(d["id"]), url=None, title=d["title"] or d["canonical_url"],
                   page_kind="document", found_via="source of this opportunity", body=d["body_text"])
        else:
            _queue(db, run, origin="opportunity_source", source_doc=str(d["id"]), title=d["title"] or d["canonical_url"],
                   page_kind="document", found_via="source of this opportunity", status="skipped",
                   reason="the source does not permit retaining its text, so it cannot be re-read for people")
    # 3. organisation pages recorded on the organisation profile
    _queue_org_pages(db, run)
    # 4. authorised web search
    queries = plan.build_queries(module=opp["module"], title=opp["title"], reference=opp.get("tender_ref"), organisations=run.org_names,
                                 countries=[c for c in (_country_name(c) for c in countries) if c], limit=max(settings.search_max_queries, 1))
    return _run_searches(db, settings, run, queries, countries, search_transport)


def _queue_org_pages(db: Database, run: _Run) -> None:
    """The website, newsroom and leadership pages recorded for the run's organisations (their links are followed when read)."""
    for o in run.orgs:
        for url, kind, via in ((o.get("leadership_url"), "leadership", "leadership page recorded for the organisation"),
                               (o.get("newsroom_url"), "news", "newsroom recorded for the organisation"),
                               (o.get("website"), "other", "website recorded for the organisation")):
            if url and str(url).startswith(("http://", "https://")):
                _queue(db, run, origin="organisation_page", url=str(url), org_id=str(o["id"]), page_kind=kind, found_via=via)
        if not o.get("website") and not o.get("newsroom_url") and not o.get("leadership_url"):
            run.unavailable.append({"method": "organisation_website",
                                    "reason": f"no website, newsroom or leadership page recorded for {o['name']}: record one to include "
                                              "its public pages"})


def _run_searches(db: Database, settings: Settings, run: _Run, queries: list[plan.Query], countries: list[str],
                  search_transport: web_search.Transport | None) -> list[dict[str, Any]]:
    """Runs the queries through the authorised search connector and queues every hit; without a connector, lists them as not run."""
    searches: list[dict[str, Any]] = []
    reason = web_search.available(settings)
    if reason:
        run.unavailable.append({"method": "web_search", "reason": reason})
        for q in queries:
            searches.append({"purpose": q.purpose, "query": q.text, "status": "not_run", "results": 0,
                             "link": web_search.web_search_link(q.text), "reason": reason})
        return searches
    country = countries[0] if countries else None
    for q in queries[: settings.search_max_queries]:
        try:
            hits = web_search.search(settings, q.text, country=country, transport=search_transport)
        except web_search.SearchFailed as exc:
            searches.append({"purpose": q.purpose, "query": q.text, "status": "failed", "results": 0, "reason": str(exc)[:200],
                             "link": web_search.web_search_link(q.text)})
            continue
        for h in hits:
            org = next((o for o in run.orgs if _same_site(h.url, o.get("website"))), None)
            _queue(db, run, origin="search_result", url=h.url, org_id=str(org["id"]) if org else None, title=h.title,
                   page_kind=attr.page_kind(h.url, h.title), found_via=f"search: {q.text}")
        searches.append({"purpose": q.purpose, "query": q.text, "status": "run", "results": len(hits),
                         "link": web_search.web_search_link(q.text)})
    return searches


# ===================================================================== fetching and reading
def _robots_allows(run: _Run, fetch: Fetch, url: str) -> bool:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in run.robots:
        rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        try:
            res = fetch(base + "/robots.txt")
            if "text" in (res.content_type or ""):
                rp.parse(res.body.decode("utf-8", "replace").splitlines())      # type: ignore[union-attr]
            else:
                rp = None
        except Exception:  # noqa: BLE001 - no robots.txt (404) or unreachable: no restriction recorded
            rp = None
        run.robots[base] = rp
    rp = run.robots[base]
    return True if rp is None else rp.can_fetch(ROBOTS_UA, url)


@dataclass
class _Page:
    text: str
    links: list[tuple[str, str]]
    final_url: str
    title: str | None


def _fetch_into(db: Database, run: _Run, fetch: Fetch, d: dict[str, Any]) -> _Page | None:
    """Fetch a queued page; on failure, record why on the research document and return None."""
    url = d["url"]
    if not _robots_allows(run, fetch, url):
        db.run("rdoc_read", id=str(d["id"]), status="skipped", reason="robots.txt does not allow automated reading of this page",
               title=None, page_kind=None, body=None, sha=None, final_url=None, sections_total=0, sections_read=0, fetched=None)
        return None
    run.fetches += 1
    try:
        res = fetch(url)
    except (retrieval.RetrievalBlocked, retrieval.RetrievalFailed) as exc:
        msg = str(exc)[:200]
        not_found = bool(re.search(r"HTTP 40[0-9]|HTTP 410", msg))
        blocked = isinstance(exc, retrieval.RetrievalBlocked)
        status = "skipped" if (not_found or blocked) else "failed"
        label = "guessed address not found" if d["origin"] == "guessed_page" and not_found else msg
        db.run("rdoc_read", id=str(d["id"]), status=status, reason=label, title=None, page_kind=None, body=None, sha=None, final_url=None,
               sections_total=0, sections_read=0, fetched=datetime.now(timezone.utc))
        return None
    except Exception as exc:  # noqa: BLE001 - network errors are recorded, never fatal
        db.run("rdoc_read", id=str(d["id"]), status="failed", reason=f"could not fetch: {exc.__class__.__name__}", title=None, page_kind=None,
               body=None, sha=None, final_url=None, sections_total=0, sections_read=0, fetched=datetime.now(timezone.utc))
        return None
    try:
        ex = content.extract(res.body, res.content_type, res.final_url)
    except Exception as exc:  # noqa: BLE001
        db.run("rdoc_read", id=str(d["id"]), status="skipped", reason=f"content could not be read: {str(exc)[:120]}", title=None,
               page_kind=None, body=None, sha=None, final_url=res.final_url, sections_total=0, sections_read=0,
               fetched=datetime.now(timezone.utc))
        return None
    return _Page(ex.text[:MAX_BODY_CHARS], ex.links + ex.nav_links, res.final_url, ex.title)


def _read_rules(db: Database, run: _Run, d: dict[str, Any], text: str, *, page_url: str | None) -> int:
    org = next((o for o in run.orgs if d.get("organisation_id") and str(o["id"]) == str(d["organisation_id"])), None)
    on_own_site = bool(org and page_url and _same_site(page_url, org.get("website") or org.get("newsroom_url") or org.get("leadership_url")))
    kind = "source_document" if d["origin"] == "opportunity_source" else "research_document"
    found = 0
    for sec in plan.sections(text):
        ms = attr.mentions(sec, run.org_names, subject_orgs=run.subject, page_org=org["name"] if (org and on_own_site) else None,
                           page_kind=d.get("page_kind") if on_own_site else None, page_url=page_url)
        if not ms:
            continue
        with db.transaction() as tx:
            for m in ms:
                record_mention(tx, run, m, kind=kind,
                               document_id=str(d["source_document_id"]) if kind == "source_document" else None,
                               rdoc_id=str(d["id"]) if kind == "research_document" else None,
                               url=None if kind == "source_document" else (page_url or d.get("url")),
                               method=_method_label(d))
                found += 1
    return found


def _method_label(d: dict[str, Any]) -> str:
    return {"opportunity_source": "reading the opportunity's source document", "user_url": "reading a page added by a reviewer",
            "user_document": "reading a document added by a reviewer", "search_result": "reading a web search result",
            "organisation_page": "reading the organisation's own page", "followed_link": "reading a page linked from the organisation's site",
            "guessed_page": "reading a guessed address on the organisation's site"}.get(d["origin"], "research")


def _read_ai(db: Database, settings: Settings, run: _Run, d: dict[str, Any], text: str, transport: ai_extraction.Transport | None) -> None:
    secs = plan.sections(text)
    done = int(d.get("ai_sections_read") or 0)
    status = "partial" if done else "not_run"
    kind = "source_document" if d["origin"] == "opportunity_source" else "research_document"
    url = None if kind == "source_document" else d.get("url")
    while done < len(secs):
        if run.ai_sections >= MAX_AI_SECTIONS_PER_RUN:
            run.limits_hit.append("AI reading limit for one run reached")
            status = "partial"
            break
        out = ai_people.people_in_document(db, settings, secs[done], transport=transport)
        run.cost += out.cost_usd
        if out.status == "budget_refused":
            status = "budget_refused"
            run.limits_hit.append("AI budget refused further reading")
            break
        if out.status in ("failed", "not_connected"):
            status = "failed" if out.status == "failed" else "not_connected"
            run.unavailable.append({"method": "configured_extractor", "reason": out.detail or out.status})
            break
        run.ai_sections += 1
        run.ai_rejected.extend(out.rejected)
        with db.transaction() as tx:
            for ap in out.people:
                role_ok, org_ok = attr.binding_confirms(ap["quote"], ap["name"], ap.get("role"), ap.get("organisation"),
                                                         run.org_names + ([ap["organisation"]] if ap.get("organisation") else []))
                unconfirmed = []
                if ap.get("role") and not role_ok:
                    unconfirmed.append(f"title '{ap['role']}' proposed by the AI extractor, not bound to the person by the passage")
                if ap.get("organisation") and not org_ok:
                    unconfirmed.append(f"organisation '{ap['organisation']}' proposed by the AI extractor, not bound to the person by the passage")
                role = ap.get("role") if role_ok else None
                orgname = ap.get("organisation") if org_ok else None
                aff = attr._affiliation(orgname, attr._Orgs(run.subject), ap["quote"]) if orgname else "unknown"
                m = attr.Mention(ap["name"], role, ap.get("role_status") or "current", orgname, aff, ap["quote"],
                                 "stated in the passage (AI extractor; confirmed by the rules)" if (role or orgname) else
                                 "named in the passage (AI extractor); no title or organisation bound to them",
                                 "ai", None, rel.classify_role(role) if role else "named_in_source")
                m.relevance_basis = attr._basis(m)
                record_mention(tx, run, m, kind=kind, document_id=str(d["source_document_id"]) if kind == "source_document" else None,
                               rdoc_id=str(d["id"]) if kind == "research_document" else None, url=url,
                               method="the configured AI extractor", source="ai", extra_note="; ".join(unconfirmed + ap.get("notes", [])) or None)
        done += 1
        if out.partial:
            run.limits_hit.append("a section was longer than the extractor input; its end was not read by the extractor")
            status = "partial"
    else:
        status = "complete"
    db.run("rdoc_ai", id=str(d["id"]), ai_status=status, ai_read=done)


def _follow(db: Database, run: _Run, d: dict[str, Any], links: list[tuple[str, str]], page_url: str, text: str) -> None:
    """Queue leadership, newsroom and relevant news links found on an organisation's own page (same site)."""
    org = next((o for o in run.orgs if d.get("organisation_id") and str(o["id"]) == str(d["organisation_id"])), None)
    if not org:
        return
    # depth: from the organisation's recorded pages and from its newsroom listing only
    if not (d["origin"] in ("organisation_page", "user_url") or (d["origin"] == "followed_link" and d.get("page_kind") == "news")):
        return
    keywords = [org["name"]] + [w for w in re.findall(r"[A-Za-z]{4,}", run.subject[0] if run.subject else "")]
    picks = plan.links_to_follow(links, page_url, keywords)
    for url, anchor, kind in picks:
        _queue(db, run, origin="followed_link", url=url, org_id=str(org["id"]), title=anchor or None,
               page_kind={"leadership": "leadership", "news": "news"}.get(kind, "other"),   # a news item is read, not followed further
               found_via=f"link '{anchor[:80]}' on {page_url}" if anchor else f"linked from {page_url}")
    if not picks and d["origin"] == "organisation_page" and d.get("page_kind") == "other":
        base = f"{urlsplit(page_url).scheme}://{urlsplit(page_url).netloc}/"
        for path in plan.FALLBACK_PATHS:
            _queue(db, run, origin="guessed_page", url=base + path, org_id=str(org["id"]), page_kind=attr.page_kind(base + path, None),
                   found_via=f"guessed address: {org['name']}'s site offered no leadership or news links")


# ===================================================================== the run
def research(db: Database, settings: Settings, opp_id: str, meta: RequestMeta, *, fetch: Fetch | None = None,
             transport: ai_extraction.Transport | None = None, search_transport: web_search.Transport | None = None,
             mode: str = "start") -> dict[str, Any]:
    opp = db.one("opportunity_get2", id=opp_id)
    if opp is None:
        raise ResearchRejected(404, "Opportunity not found")
    orgs = db.all("opportunity_organisations", id=opp_id)
    org_names = [o["name"] for o in orgs if o["name"]]
    subject = [o["name"] for o in orgs if o["name"] and o["involvement"] in ("issuer", "named in the evidence")] or org_names[:1]
    countries = [g["country_code"] for g in db.all("opportunity_geo", id=opp_id)]
    run = _Run(opp_id, meta, org_names, subject, orgs)
    fetch = fetch or (lambda url: retrieval.fetch(url, allow_private_hosts=frozenset(settings.retrieval_allow_private_hosts)))
    searches: list[dict[str, Any]] = []
    if mode == "start":
        searches = _enqueue_start(db, settings, run, opp, countries, search_transport)
    else:
        latest = db.one("rel_research_latest", id=opp_id)
        searches = list((latest or {}).get("searches") or [])
        db.all("rdoc_requeue_failed", id=opp_id, disc=None)
    ai_reason = ai_extraction.available(settings)
    if ai_reason:
        run.unavailable.append({"method": "configured_extractor", "reason": ai_reason})
    _read_everything(db, settings, run, fetch, transport, ai_reason)
    run.unavailable.append({"method": "linkedin_profiles",
                            "reason": "no authorised LinkedIn integration is connected: targeted LinkedIn searches are provided instead, "
                                      "and a profile is saved only when a person confirms it"})
    return _finish(db, settings, run, opp, countries, searches, ai_connected=ai_reason is None)


def _read_everything(db: Database, settings: Settings, run: _Run, fetch: Fetch, transport: ai_extraction.Transport | None,
                     ai_reason: str | None) -> None:
    """Reads everything queued for the run within the per-run fetch limit, then the AI extractor section by section."""
    # read everything queued, within the per-run fetch limit
    while True:
        pending = db.all("rdoc_pending", **_scope(run))
        if not pending:
            break
        progressed = False
        for d in pending:
            if d["url"] and not d.get("body_text"):
                if run.fetches >= MAX_FETCHES_PER_RUN:
                    run.limits_hit.append(f"fetch limit for one run reached ({MAX_FETCHES_PER_RUN} pages)")
                    break
                page = _fetch_into(db, run, fetch, d)
                if page is None:
                    progressed = True
                    continue
                text, links, final_url, title = page.text, page.links, page.final_url, page.title
                kind = d["page_kind"] if d["page_kind"] != "other" else attr.page_kind(final_url or d["url"], title)
                secs = plan.sections(text)
                db.run("rdoc_read", id=str(d["id"]), status="read", reason=None, title=title, page_kind=kind, body=text, sha=_sha(text),
                       final_url=final_url, sections_total=len(secs), sections_read=0, fetched=datetime.now(timezone.utc))
                d = dict(d, page_kind=kind, body_text=text, title=title or d.get("title"))
                _read_rules(db, run, d, text, page_url=final_url or d["url"])
                db.run("rdoc_read", id=str(d["id"]), status="read", reason=None, title=None, page_kind=None, body=None, sha=None,
                       final_url=None, sections_total=len(secs), sections_read=len(secs), fetched=None)
                _follow(db, run, d, links, final_url or d["url"], text)
            else:
                text = d.get("body_text") or ""
                secs = plan.sections(text)
                _read_rules(db, run, d, text, page_url=d.get("url"))
                db.run("rdoc_read", id=str(d["id"]), status="read", reason=None, title=None, page_kind=None, body=None, sha=None,
                       final_url=None, sections_total=len(secs), sections_read=len(secs), fetched=None)
            db.run("rdoc_people", id=str(d["id"]))
            progressed = True
        if not progressed or run.limits_hit:
            break
    # the configured AI extractor, section by section, under the budget controls
    if not ai_reason:
        for d in db.all("rdoc_ai_pending", **_scope(run)):
            if run.ai_sections >= MAX_AI_SECTIONS_PER_RUN:
                run.limits_hit.append("AI reading limit for one run reached")
                break
            _read_ai(db, settings, run, d, d.get("body_text") or "", transport)
            db.run("rdoc_people", id=str(d["id"]))
            if "AI budget refused further reading" in run.limits_hit:
                break
    else:
        for d in db.all("rdoc_ai_pending", **_scope(run)):
            if d["ai_status"] == "not_run":
                db.run("rdoc_ai", id=str(d["id"]), ai_status="not_connected", ai_read=0)


def coverage(db: Database, opp_id: str | None, *, ai_connected: bool, searches: list[dict[str, Any]], disc_id: str | None = None) -> dict[str, Any]:
    docs = db.all("rdoc_for_opp", id=opp_id, disc=disc_id)
    by = lambda st: [d for d in docs if d["status"] == st]  # noqa: E731
    sections_total = sum(int(d["sections_total"]) for d in docs)
    sections_read = sum(int(d["sections_read"]) for d in docs)
    ai_read = sum(int(d["ai_sections_read"]) for d in docs)
    remaining: list[str] = []
    if by("queued"):
        remaining.append(f"{len(by('queued'))} document(s) or page(s) still to read")
    if ai_connected:
        ai_left = sum(int(d["sections_total"]) - int(d["ai_sections_read"]) for d in docs if d["status"] in ("read", "partial"))
        if ai_left:
            remaining.append(f"{ai_left} section(s) still to be read by the configured AI extractor")
    if by("failed"):
        remaining.append(f"{len(by('failed'))} page(s) could not be fetched (retried on the next run)")
    not_searched: list[str] = []
    if not ai_connected:
        not_searched.append("The configured AI extractor did not read anything: it is not connected; only the rules read the documents")
    nr = [s for s in searches if s["status"] == "not_run"]
    if nr:
        not_searched.append(f"{len(nr)} web search(es) not run: no authorised search connector is configured")
    fs = [s for s in searches if s["status"] == "failed"]
    if fs:
        not_searched.append(f"{len(fs)} web search(es) failed")
    not_searched.append("LinkedIn was not searched (no authorised integration); use the search links")
    not_searched.append("Only the documents and pages listed were read: this is not a complete search of public information")
    return {"documents": len(docs), "read": len(by("read")), "partial": len(by("partial")), "queued": len(by("queued")),
            "failed": len(by("failed")), "skipped": len(by("skipped")), "sections_total": sections_total, "sections_read": sections_read,
            "ai_sections_read": ai_read, "ai_connected": ai_connected, "remaining": remaining, "not_searched": not_searched,
            "searches_run": len([s for s in searches if s["status"] == "run"]), "searches_not_run": len(nr), "searches_failed": len(fs)}


def _finish(db: Database, settings: Settings, run: _Run, opp: dict[str, Any], countries: list[str], searches: list[dict[str, Any]], *,
            ai_connected: bool) -> dict[str, Any]:
    cov = coverage(db, run.opp_id, ai_connected=ai_connected, searches=searches)
    people_total = len({f["person_id"] for f in run.found})
    linked = db.all("rel_opportunity_people", id=run.opp_id)
    incomplete = bool(cov["remaining"]) or bool(run.limits_hit)
    outcome = "incomplete" if incomplete else ("people_found" if (people_total or linked) else "no_people_found")
    cov["limits_hit"] = sorted(set(run.limits_hit))
    cov["duplicates_flagged"] = run.duplicates
    cov["ai_rejected"] = run.ai_rejected[:20]
    gaps, actions = rel.gaps_and_actions(opp["module"], run.org_names, linked, researched=True)
    if outcome == "incomplete":
        actions.insert(0, "Continue research to read the remaining documents and sections")
    if run.duplicates:
        actions.append(f"Review {run.duplicates} possible duplicate person record(s)")
    if cov["searches_not_run"]:
        actions.append("Open the listed web searches yourself, and add any relevant page or document to the research")
    roles = [{"key": r.key, "label": r.label} for r in rel.target_roles(opp["module"])]
    docs = db.all("rdoc_for_opp", **_scope(run))
    read = {d["origin"] for d in docs if d["status"] in ("read", "partial")}
    methods = []
    if "opportunity_source" in read:
        methods.append("source_documents")
    if read & {"user_url", "user_document"}:
        methods.append("reviewer_sources")
    if read & {"organisation_page", "followed_link", "guessed_page"}:
        methods.append("organisation_pages")
    if "search_result" in read or any(s["status"] == "run" for s in searches):
        methods.append("web_search")
    methods.append("rules")
    if ai_connected and any(int(d["ai_sections_read"]) for d in docs):
        methods.append("configured_extractor")
    run_id = db.scalar("rel_research_insert2", opp=run.opp_id, methods=methods, unavailable=_dedupe(run.unavailable),
                       orgs=[{"id": str(o["id"]), "name": o["name"], "involvement": o["involvement"]} for o in run.orgs], roles=roles,
                       found=people_total, gaps=gaps, cost=str(run.cost), outcome=outcome, coverage=cov, searches=searches,
                       session_ref=run.meta.session_ref)
    audit(db, "relationship_research", run.meta, entity_type="opportunity", entity_id=run.opp_id,
          detail={"outcome": outcome, "people": people_total, "fetches": run.fetches, "ai_sections": run.ai_sections, "cost_usd": str(run.cost)})
    from .relationship_service import search_suggestions
    return {"run_id": str(run_id), "outcome": outcome, "methods": methods, "unavailable": _dedupe(run.unavailable),
            "organisations": run.orgs, "target_roles": roles, "found": run.found, "coverage": cov, "web_searches": searches,
            "searches": search_suggestions(opp["module"], run.orgs, countries), "gaps": gaps, "actions": actions,
            "cost_usd": str(run.cost), "documents": docs}


def _dedupe(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out = []
    for i in items:
        k = json.dumps(i, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out
