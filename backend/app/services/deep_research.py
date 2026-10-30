"""Staged, resumable research (30 Oct 2026, items 3–5): identify → resolve official identity → research company → research
relevant people → connect relationships → assess commercial relevance.

Every stage enriches the ONE canonical record of each company and person (never a parallel profile), through the same pipeline and
evidence rules as relationship research (`relationship_research`: organisation pages, authorised web search, robots.txt, per-run
limits) and company intelligence (`company_intelligence`). A stage ends `done`, `incomplete` (a limit was reached: continue later),
`failed` (the error is recorded), `not_run` (nothing could be searched: no connector, no pages) or `not_applicable`. Each profile field
carries its own status: found / not searched / not found after research / source inaccessible / research incomplete. When a website
or contact route is missing after the first pass, a targeted follow-up search runs before the field is called "not found".

The research file (`research_file`) presents the result: a concise summary first, the supporting research below, every gap explicit.
Nothing in it is a longer AI summary: it is the record.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timezone
from typing import Any

from ..ai import extraction as ai_extraction
from ..config import Settings
from ..connectors import search as web_search
from ..domain import assessment as asm
from ..domain import company_intel as ci
from ..domain import email_attribution as ea
from ..domain import overview as ov
from ..domain import research_plan as plan
from ..domain import retrieval
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from . import airport_directory as ad
from . import company_intelligence as cmp
from . import relationship_research as rr
from .audit import RequestMeta, audit

STAGES = asm.STAGES
STAGE_LABELS = asm.STAGE_LABELS
STATUS_LABELS = asm.STAGE_STATUS_LABELS
MAX_ORGS_PER_STAGE = 6
MAX_PEOPLE_QUERIES_PER_ORG = 2


class ResearchRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def stages(db: Database, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    return asm.stage_rows(db.all("stage_get_all", etype=entity_type, eid=entity_id))


def progress(db: Database, entity_type: str, entity_id: str) -> dict[str, Any]:
    """Completed / failed / pending organisation-stage items, and the overall state, the same everywhere (research file, company page,
    Dashboard): complete · complete with unresolved failures · incomplete with pending work · failed · not run. Pages queued for reading
    count as pending work."""
    t = {k: int(v or 0) for k, v in (db.one("stage_items_totals", etype=entity_type, eid=entity_id) or {}).items()}
    queued = db.scalar("rdoc_queued_count", opp=entity_id if entity_type == "opportunity" else None, org=entity_id if entity_type == "organisation" else None) or 0
    st = stages(db, entity_type, entity_id)
    out = {**t, "pages_queued": int(queued), **asm.overall(st, {**t, "pending": t.get("pending", 0) + int(queued)})}
    if queued:
        out["tally"] += f"; {queued} page(s) queued to read"
    return out


def retry_failed(db: Database, settings: Settings, entity_type: str, entity_id: str, meta: RequestMeta, **kw: Any) -> dict[str, Any]:
    """The explicit retry action: only the organisations whose stage failed are queued again (with the reason of the last failure kept),
    together with stages that failed outright; pages that failed to load are queued again for reading. Completed work is not repeated."""
    requeued = db.all("stage_items_retry_failed", etype=entity_type, eid=entity_id)
    failed_stages = [s["stage"] for s in stages(db, entity_type, entity_id) if s["status"] == "failed"]
    affected = sorted({r["stage"] for r in requeued} | set(failed_stages), key=STAGES.index)
    if not affected:
        raise ResearchRejected(409, "Nothing to retry: no organisation or stage has an unresolved failure")
    pages = db.all("rdoc_requeue_failed_explicit", id=entity_id if entity_type == "opportunity" else None, org=entity_id if entity_type == "organisation" else None)
    for st in affected:
        _set(db, entity_type, entity_id, st, "incomplete", "queued for retry", {}, meta)
    audit(db, "deep_research_retry", meta, entity_type=entity_type, entity_id=entity_id,
          detail={"stages": affected, "organisations": len(requeued), "pages": len(pages)})
    # the stages after the first failure that could not run because of it (e.g. no website to read) run again too; completed stages do not
    first = min(STAGES.index(a) for a in affected)
    current = {s["stage"]: s["status"] for s in stages(db, entity_type, entity_id)}
    downstream = [s for s in STAGES[first:] if current.get(s) in ("not_run", "incomplete") and s not in affected]
    out = run(db, settings, entity_type, entity_id, meta, stages=sorted({*affected, *downstream, "relevance"}, key=STAGES.index), **kw)
    out["retried"] = {"stages": affected, "organisations": len(requeued), "pages": len(pages)}
    return out


def queue_items(db: Database, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    """The persisted work queue: every organisation of every organisation-scoped stage with its status, so unfinished work is visible."""
    return [dict(r, status_label=QUEUE_STATUS_LABELS.get(r["status"], r["status"]), stage_label=STAGE_LABELS.get(r["stage"], r["stage"]))
            for r in db.all("stage_items_list", etype=entity_type, eid=entity_id)]


QUEUE_STATUS_LABELS = {"pending": "Pending", "attempted": "Attempted, not finished", "done": "Done", "failed": "Failed", "skipped": "Skipped"}


def _set(db: Database, etype: str, eid: str, stage: str, status: str, detail: str | None, counts: dict[str, Any], meta: RequestMeta) -> None:
    db.run("stage_set", etype=etype, eid=eid, stage=stage, status=status, detail=detail, counts=counts, session_ref=meta.session_ref)


# ===================================================================== the run
class _Ctx:
    def __init__(self, db: Database, settings: Settings, etype: str, eid: str, meta: RequestMeta, run: rr._Run, fetch, transport, search_transport):
        self.db, self.settings, self.etype, self.eid, self.meta, self.run = db, settings, etype, eid, meta, run
        self.fetch, self.transport, self.search_transport = fetch, transport, search_transport
        self.ai_reason = ai_extraction.available(settings)
        self.search_reason = web_search.available(settings)
        self.searches: list[dict[str, Any]] = []
        self.scope: dict[str, Any] = {}

    def read(self) -> None:
        rr._read_everything(self.db, self.settings, self.run, self.fetch, self.transport, self.ai_reason)

    def limit_hit(self) -> bool:
        return any("fetch limit" in x or "organisation limit" in x for x in self.run.limits_hit)

    def search(self, queries: list[Any], countries: list[str]) -> list[dict[str, Any]]:
        out = rr._run_searches(self.db, self.settings, self.run, queries, countries, self.search_transport)
        self.searches.extend(out)
        return out

    def orgs_known(self) -> list[dict[str, Any]]:
        return [o for o in self.run.orgs]

    def add_orgs(self, found: list[dict[str, Any]]) -> None:
        """An organisation that comes to light during the run joins it AND the work queues of the stages that concern it, so it is
        researched on this run or the next, never silently left with empty fields."""
        for o in found:
            if o["name"] not in self.run.org_names:
                self.run.org_names.append(o["name"])
                row = self.db.one("org_get_for_research", id=o["id"])
                if row:
                    org = dict(row, involvement="named in the research")
                    self.run.orgs.append(org)
                    self.queue("identity" if not org.get("website") else "company", [org])
                    self.queue("people", [org])
                    self.queue("relevance", [org])

    # ---- the persisted work queue of each organisation-scoped stage (amendment item 2): nothing is sliced away silently
    def queue(self, stage: str, orgs: list[dict[str, Any]]) -> None:
        ids = [str(o["id"]) for o in orgs]
        if ids:
            self.db.run("stage_items_queue", etype=self.etype, eid=self.eid, stage=stage, orgs=ids, session_ref=self.meta.session_ref)

    def take(self, stage: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.db.all("stage_items_take", etype=self.etype, eid=self.eid, stage=stage, limit=limit or 1_000_000)
        by = {str(o["id"]): o for o in self.run.orgs}
        return [by[str(r["organisation_id"])] for r in rows if str(r["organisation_id"]) in by]

    def item(self, stage: str, org: dict[str, Any], status: str, detail: str | None = None) -> None:
        self.db.run("stage_item_set", etype=self.etype, eid=self.eid, stage=stage, org=str(org["id"]), status=status, detail=detail)

    def counts(self, stage: str) -> dict[str, int]:
        c = self.db.one("stage_items_counts", etype=self.etype, eid=self.eid, stage=stage) or {}
        return {k: int(c.get(k) or 0) for k in ("total", "attempted", "completed", "failed", "pending", "skipped")}

    def outcome(self, stage: str, base: dict[str, Any], done_detail: str) -> tuple[str, str, dict[str, Any]]:
        """The stage's status from its queue — never an unqualified 'done' while work is pending or a failure is unresolved:
        incomplete (pending work: continue) · failed (every organisation failed: retry) · done_with_failures (finished, some failed: retry)
        · done (complete)."""
        c = self.counts(stage)
        counts = {**base, **c}
        tally = f"{c['completed']} completed, {c['failed']} failed, {c['pending']} pending of {c['total']}"
        if c["pending"]:
            return "incomplete", f"{tally} (per-run limit {MAX_ORGS_PER_STAGE}): continue the research", counts
        if self.limit_hit():
            return "incomplete", f"{tally}; the per-run page limit was reached: continue the research", counts
        if c["failed"] and not c["completed"]:
            return "failed", f"{tally}: every organisation failed — retry the failed organisations", counts
        if c["failed"]:
            return "done_with_failures", f"{tally}: {done_detail}; {c['failed']} unresolved failure(s) — retry the failed organisations", counts
        return "done", done_detail, counts


def run(db: Database, settings: Settings, entity_type: str, entity_id: str, meta: RequestMeta, *, stages: list[str] | None = None,
        fetch=None, transport=None, search_transport=None) -> dict[str, Any]:
    if entity_type not in ("opportunity", "organisation"):
        raise ResearchRejected(422, "staged research runs for an opportunity or a company")
    fetch = fetch or (lambda url: retrieval.fetch(url, allow_private_hosts=frozenset(settings.retrieval_allow_private_hosts)))
    if entity_type == "opportunity":
        opp = db.one("opportunity_get2", id=entity_id)
        if opp is None:
            raise ResearchRejected(404, "Opportunity not found")
        orgs = db.all("opportunity_organisations", id=entity_id)
        for extra in db.all("opp_research_organisations", id=entity_id):
            if not any(str(o["id"]) == str(extra["id"]) for o in orgs):
                orgs.append(dict(extra, involvement="named in the research"))
        org_names = [o["name"] for o in orgs if o["name"]]
        subject = [o["name"] for o in orgs if o["name"] and o["involvement"] in ("issuer", "named in the evidence")] or org_names[:1]
        countries = [g["country_code"] for g in db.all("opportunity_geo", id=entity_id)]
        r = rr._Run(entity_id, meta, org_names, subject, orgs, company_mode=True)
        ctx = _Ctx(db, settings, entity_type, entity_id, meta, r, fetch, transport, search_transport)
        ctx.scope = {"id": None, "opportunity_id": entity_id, "org_research_id": None, "countries": countries, "airport_iata": None,
                     "capability_area": opp["module"], "title": opp["title"], "module": opp["module"], "reference": opp.get("tender_ref")}
    else:
        org = db.one("org_get_for_research", id=entity_id)
        if org is None:
            raise ResearchRejected(404, "Company not found")
        orgs = [dict(org, involvement="the company researched")]
        for extra in db.all("org_research_organisations", id=entity_id):          # counterparties found by an earlier pass: researched on continuation
            orgs.append(dict(extra, involvement="named in the research"))
        r = rr._Run(None, meta, [o["name"] for o in orgs], [org["name"]], orgs, org_research_id=entity_id, company_mode=True)
        ctx = _Ctx(db, settings, entity_type, entity_id, meta, r, fetch, transport, search_transport)
        ctx.scope = {"id": None, "opportunity_id": None, "org_research_id": entity_id, "countries": [org["country"]] if org.get("country") else [],
                     "airport_iata": None, "capability_area": None, "title": org["name"], "module": None, "reference": None}
    if ctx.ai_reason:
        r.unavailable.append({"method": "configured_extractor", "reason": ctx.ai_reason})
    if ctx.search_reason:
        r.unavailable.append({"method": "web_search", "reason": ctx.search_reason})
    current = {s["stage"]: s for s in globals()["stages"](db, entity_type, entity_id)}
    # Continue: the stages with pending or unstarted work (and relevance, which is cheap). A stage complete with unresolved failures is left
    # alone by Continue — its failed organisations are retried only by the explicit retry action (`retry_failed`).
    wanted = list(stages) if stages else [s for s in STAGES if current[s]["status"] not in ("done", "done_with_failures", "not_applicable") or s == "relevance"]
    if not stages:
        # pages queued since the last run (a page a person added, a link found late) are pending work: they are read, their organisations
        # recorded and their people and addresses attributed — "complete" never hides an unread page
        queued = [d for d in db.all("rdoc_for_opp", id=ctx.scope.get("opportunity_id"), disc=None, org=ctx.scope.get("org_research_id")) if d["status"] == "queued"]
        if queued:
            wanted = sorted({*wanted, *(["identify"] if entity_type == "opportunity" else ["company"]), "people", "relationships", "relevance"}, key=STAGES.index)
    executed = []
    for stage in STAGES:
        if stage not in wanted:
            continue
        if ctx.limit_hit() and stage not in ("relationships", "relevance"):
            _set(db, entity_type, entity_id, stage, "incomplete", "the per-run page limit was reached before this stage: continue the research", {}, meta)
            executed.append(stage)
            continue
        _set(db, entity_type, entity_id, stage, "running", None, {}, meta)
        try:
            status, detail, counts = _STAGE_FN[stage](ctx)
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal to the other stages
            status, detail, counts = "failed", f"{exc.__class__.__name__}: {str(exc)[:200]}", {}
        _set(db, entity_type, entity_id, stage, status, detail, counts, meta)
        executed.append(stage)
    # organisations that came to light after the identity stage (a counterparty named on a company page) have not been researched yet:
    # the identity and company stages are marked incomplete so a continuation covers them, instead of leaving their fields silently empty
    # organisations that came to light during the run (a counterparty named on a company page) sit in the queues of the stages that concern
    # them: any stage left 'done' with pending work is marked incomplete, so a continuation researches them instead of leaving their fields empty
    final = {s["stage"]: s for s in globals()["stages"](db, entity_type, entity_id)}
    for row in db.all("stage_items_pending_any", etype=entity_type, eid=entity_id):
        st = final.get(row["stage"])
        if st and st["status"] in ("done", "not_applicable") and (ctx.search_reason is None or row["stage"] == "company"):
            c = ctx.counts(row["stage"])
            _set(db, entity_type, entity_id, row["stage"], "incomplete",
                 f"{c['completed']} of {c['total']} organisation(s) researched; {c['pending']} found later or still pending: continue the research", {**(st.get("counts") or {}), **c}, meta)
    audit(db, "deep_research_run", meta, entity_type=entity_type, entity_id=entity_id,
          detail={"stages": executed, "fetches": r.fetches, "cost_usd": str(r.cost), "limits": sorted(set(r.limits_hit))})
    out = {"entity_type": entity_type, "entity_id": entity_id, "stages": globals()["stages"](db, entity_type, entity_id), "executed": executed,
           "fetches": r.fetches, "cost_usd": str(r.cost), "limits_hit": sorted(set(r.limits_hit)), "unavailable": rr._dedupe(r.unavailable), "searches": ctx.searches,
           "queue": queue_items(db, entity_type, entity_id), "progress": progress(db, entity_type, entity_id)}
    # Continue is offered while work is pending or stages have not run; a stage blocked by an unresolved failure waits for the retry
    out["resumable"] = out["progress"]["state"] in ("incomplete", "not_run")
    out["retryable"] = out["progress"]["failed"] > 0 or any(s["status"] == "failed" for s in out["stages"])
    if entity_type == "opportunity":
        out["research_file"] = research_file(db, entity_id)
    else:
        out["profile"] = cmp.profile(db, entity_id)
    return out


# ===================================================================== stages
def _identify(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """The organisations involved: from the opportunity's documents, its organisation pages and the first searches."""
    db, run = ctx.db, ctx.run
    if ctx.etype == "organisation":
        return "not_applicable", "the company itself is the subject", {}
    have = db.all("rdoc_for_opp", id=ctx.eid, disc=None, org=None)
    if not have:
        opp = db.one("opportunity_get2", id=ctx.eid)
        for d in db.all("opportunity_documents", id=ctx.eid):
            if d.get("body_text"):
                rr._queue(db, run, origin="opportunity_source", source_doc=str(d["id"]), url=None, title=d["title"] or d["canonical_url"], page_kind="document",
                          found_via="source of this opportunity", body=d["body_text"])
        rr._queue_org_pages(db, run)
        queries = plan.build_queries(module=opp["module"], title=opp["title"], reference=opp.get("tender_ref"), organisations=run.org_names,
                                     countries=[c for c in (rr._country_name(c) for c in ctx.scope["countries"]) if c], limit=max(ctx.settings.search_max_queries, 1))
        ctx.search(queries, ctx.scope["countries"])
    else:
        db.all("rdoc_requeue_failed", id=ctx.eid, disc=None, org=None)
    ctx.read()
    found = cmp.record_organisations(db, run, ctx.scope)
    ctx.add_orgs(found)
    _opportunity_airports(db, ctx)
    docs = db.all("rdoc_for_opp", id=ctx.eid, disc=None, org=None)
    read = [d for d in docs if d["status"] in ("read", "partial")]
    counts = {"documents": len(docs), "read": len(read), "organisations": len(run.orgs), "new_organisations": sum(1 for f in found if f["new"])}
    if not read and ctx.search_reason and not docs:
        return "not_run", f"nothing could be read: {ctx.search_reason}; no source text retained and no organisation page recorded", counts
    if ctx.limit_hit() or any(d["status"] == "queued" for d in docs):
        return "incomplete", "pages remain to be read (per-run limit): continue the research", counts
    return "done", f"{len(run.orgs)} organisation(s) involved; {len(read)} document(s) read", counts


_WEB_QUERIES = [('"{name}" official website', "Official website of {name}"), ('"{name}" contact', "Contact page of {name}"),
                ('"{name}" cargo', "{name} in cargo sources")]


def _identity(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """Official identity: website and contact page for every organisation without one — a targeted follow-up search, then the pages read;
    a site is recorded only when the page states the organisation's name (similarity alone is never proof). Organisations are taken from
    the persisted queue, at most MAX_ORGS_PER_STAGE per run; the rest stay pending and the stage says so."""
    db, run = ctx.db, ctx.run
    ctx.queue("identity", [o for o in run.orgs if not o.get("website")])
    targets = ctx.take("identity", MAX_ORGS_PER_STAGE)
    resolved = 0
    for o in targets:
        oid = str(o["id"])
        if o.get("website"):                                            # resolved meanwhile (a page of the run named its site)
            ctx.item("identity", o, "done", "website already recorded")
            continue
        if ctx.search_reason:
            cmp.set_field_status(db, oid, "website", "not_searched", f"no search connector: {ctx.search_reason}")
            cmp.set_field_status(db, oid, "contact_page", "not_searched", "no search connector")
            ctx.item("identity", o, "attempted", f"not searched: {ctx.search_reason}")
            ctx.item("identity", o, "pending", f"not searched: {ctx.search_reason}")
            continue
        if ctx.limit_hit():
            ctx.item("identity", o, "pending", "the per-run page limit was reached before this organisation was searched")
            continue
        ctx.item("identity", o, "attempted")
        queries = [plan.Query(label.format(name=o["name"]), q.format(name=o["name"])) for q, label in _WEB_QUERIES[:2]]
        ran = ctx.search(queries, ctx.scope["countries"])
        if ctx.limit_hit():
            cmp.set_field_status(db, oid, "website", "incomplete", "the per-run page limit was reached before the results were read")
            ctx.item("identity", o, "pending", "results remain to be read (per-run limit)")
            continue
        ctx.read()
        ctx.add_orgs(cmp.record_organisations(db, run, ctx.scope))
        row = db.one("org_get_for_research", id=oid)
        if row and row.get("website"):
            resolved += 1
            o["website"] = row["website"]
            ctx.queue("company", [o])                                   # its pages are read by the company stage
            if not (db.one("org_profile_get", id=oid) or {}).get("contact_url"):
                cmp.set_field_status(db, oid, "contact_page", "not_found_after_research", "no contact page among the pages read")
            ctx.item("identity", o, "done", f"website found: {row['website']}")
        else:
            failed = [r for r in ran if r["status"] == "failed"]
            unread = [d for d in db.all("rdoc_for_opp", id=ctx.scope.get("opportunity_id"), disc=None, org=ctx.scope.get("org_research_id"))
                      if d["status"] == "failed" and f'"{o["name"]}"' in (d.get("found_via") or "")]
            if failed and len(failed) == len(ran):
                cmp.set_field_status(db, oid, "website", "inaccessible", "every search for the official site failed")
                ctx.item("identity", o, "failed", "every search for the official site failed")
            elif unread:
                # the search found pages but they could not be read: that is a failure to retry, never "not found after research"
                why = unread[0].get("status_reason") or "the page could not be read"
                cmp.set_field_status(db, oid, "website", "inaccessible", f"{len(unread)} result page(s) could not be read ({why})")
                ctx.item("identity", o, "failed", f"{len(unread)} result page(s) could not be read: {why}")
            elif ctx.limit_hit():
                cmp.set_field_status(db, oid, "website", "incomplete", "results remain to be read")
                ctx.item("identity", o, "pending", "results remain to be read (per-run limit)")
            else:
                cmp.set_field_status(db, oid, "website", "not_found_after_research",
                                     f"{len(ran)} targeted search(es) run; no page stating the organisation's name on a matching site")
                cmp.set_field_status(db, oid, "contact_page", "not_found_after_research", "no official site found")
                ctx.item("identity", o, "done", f"not found after {len(ran)} targeted search(es)")
    for o in run.orgs:
        if o.get("website"):
            cmp.set_field_status(db, str(o["id"]), "website", "found", o["website"])
    base = {"organisations": len(run.orgs), "taken_this_run": len(targets), "resolved": resolved}
    c = ctx.counts("identity")
    if c["pending"] and ctx.search_reason:
        return "not_run", f"{c['pending']} organisation(s) without a website could not be searched: {ctx.search_reason}", {**base, **c}
    return ctx.outcome("identity", base, f"{resolved} website(s) resolved; {c['total']} organisation(s) without a website examined" if c["total"] else "every organisation already has a website")


def _company(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """The company's own pages: profile, services, offices and airports, contact page and addresses, represented airlines and partners.
    Organisations with a website are taken from the persisted queue, at most MAX_ORGS_PER_STAGE per run."""
    db, run = ctx.db, ctx.run
    ctx.queue("company", [o for o in run.orgs if o.get("website")])
    for o in run.orgs:
        if not o.get("website"):
            for f in ("emails", "services", "locations", "airports", "representation"):
                cmp.set_field_status(db, str(o["id"]), f, "not_searched", "no official website to read")
    taken = ctx.take("company", MAX_ORGS_PER_STAGE)
    if not taken and not ctx.counts("company")["total"]:
        return ("not_run", "no organisation has an official website recorded: nothing to read", {"organisations": len(run.orgs), **ctx.counts("company")})
    for o in taken:
        ctx.item("company", o, "attempted")
    saved = run.orgs
    run.orgs = taken
    rr._queue_org_pages(db, run)
    run.orgs = saved
    ctx.read()
    ctx.add_orgs(cmp.record_organisations(db, run, ctx.scope))      # a counterparty named on a company page joins the run and its queues
    docs = db.all("rdoc_for_opp", id=ctx.scope.get("opportunity_id"), disc=None, org=ctx.scope.get("org_research_id"))
    pages_read = 0
    for o in taken:
        oid = str(o["id"])
        site_docs = [d for d in docs if str(d.get("organisation_id") or "") == oid]
        read = [d for d in site_docs if d["status"] in ("read", "partial")]
        failed = [d for d in site_docs if d["status"] == "failed"]
        skipped = [d for d in site_docs if d["status"] == "skipped"]
        queued = [d for d in site_docs if d["status"] == "queued"]
        pages_read += len(read)
        prof = cmp.profile(db, oid)
        has = {"emails": bool(prof["contacts"]), "services": bool(prof.get("services_text")), "locations": bool(prof.get("locations_text")),
               "airports": bool(prof.get("airports")), "representation": bool(prof["relationships"]), "contact_page": bool(prof.get("contact_url")),
               "parent": bool(prof.get("parent_group"))}
        for f, ok in has.items():
            if ok:
                cmp.set_field_status(db, oid, f, "found", None)
            elif ctx.limit_hit() or queued:
                cmp.set_field_status(db, oid, f, "incomplete", "pages of the site remain to be read")
            elif not read and (failed or skipped):
                cmp.set_field_status(db, oid, f, "inaccessible", (failed or skipped)[0].get("status_reason") or "the site could not be read")
            elif read:
                cmp.set_field_status(db, oid, f, "not_found_after_research", f"{len(read)} page(s) of the site read; not stated")
        if queued or (ctx.limit_hit() and not read):
            ctx.item("company", o, "pending", f"{len(queued)} page(s) of the site remain to be read (per-run limit)")
        elif not read and (failed or skipped):
            ctx.item("company", o, "failed", (failed or skipped)[0].get("status_reason") or "the site could not be read")
        else:
            ctx.item("company", o, "done", f"{len(read)} page(s) read")
    base = {"organisations": len(run.orgs), "taken_this_run": len(taken), "pages_read": pages_read}
    return ctx.outcome("company", base, f"{pages_read} company page(s) read this run for {len(taken)} organisation(s)")


def _people(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """Relevant people: the leadership pages already followed, plus targeted role searches per organisation (taken from the persisted
    queue, at most MAX_ORGS_PER_STAGE per run); then the published professional e-mail of each person under the attribution rule."""
    db, run = ctx.db, ctx.run
    module = ctx.scope.get("module")
    ctx.queue("people", run.orgs)
    targets = ctx.take("people", MAX_ORGS_PER_STAGE)
    searched: list[dict[str, Any]] = []
    for o in targets:
        if ctx.search_reason:
            continue
        if ctx.limit_hit():
            ctx.item("people", o, "pending", "the per-run page limit was reached before this organisation was searched")
            continue
        ctx.item("people", o, "attempted")
        queries = plan.build_discovery_queries(module=module, organisation=o["name"], countries=[c for c in (rr._country_name(c) for c in ctx.scope["countries"][:1]) if c],
                                               role_focus=None, limit=MAX_PEOPLE_QUERIES_PER_ORG)[:MAX_PEOPLE_QUERIES_PER_ORG]
        ctx.search(queries, ctx.scope["countries"])
        searched.append(o)
    ctx.read()
    for rd in db.all("rdoc_bodies", disc=None, id=ctx.scope.get("opportunity_id"), org=ctx.scope.get("org_research_id")):
        rr._read_rules(db, run, rd, rd.get("body_text") or "", page_url=rd.get("url"))
        db.run("rdoc_people", id=str(rd["id"]))
    all_ids = [str(o["id"]) for o in run.orgs]
    people = db.all("people_at_orgs", orgs=all_ids) if all_ids else []
    emails_found = _person_emails(db, ctx, people)
    for o in targets:
        n = sum(1 for p in people if str(p.get("organisation_id")) == str(o["id"]))
        if ctx.search_reason and not o.get("website"):
            cmp.set_field_status(db, str(o["id"]), "people", "found" if n else "not_searched", f"{n} person(s) bound by pages already read" if n else "no site to read and no search connector")
            ctx.item("people", o, "pending", f"not searched: {ctx.search_reason}")
        elif o in searched and ctx.limit_hit() and not n:
            cmp.set_field_status(db, str(o["id"]), "people", "incomplete", "pages remain to be read")
            ctx.item("people", o, "pending", "results remain to be read (per-run limit)")
        elif o in searched or n or ctx.search_reason:
            if n:
                cmp.set_field_status(db, str(o["id"]), "people", "found", f"{n} person(s) bound to the organisation by its pages")
            else:
                cmp.set_field_status(db, str(o["id"]), "people", "not_found_after_research", "no page read names a person with a title bound to the organisation")
            ctx.item("people", o, "done", f"{n} person(s)")
    counts = ctx.counts("people")
    base = {"organisations": len(run.orgs), "taken_this_run": len(targets), "people": len(people), "emails_found": emails_found}
    if ctx.search_reason and counts["pending"] and not any(o.get("website") for o in targets):
        return "not_run", f"no search connector and no site to read: {ctx.search_reason}", {**base, **counts}
    return ctx.outcome("people", base, f"{len(people)} person(s) at {len(run.orgs)} organisation(s); {emails_found} published e-mail(s) attributed")


EMAIL_BASIS_LABELS = {"name_match": "the address is the person's own name (assigned before 4.8.0; re-checked)", "explicit_statement": "stated in the same sentence as the person, nobody else between",
                      "contact_block": "in the person's labelled contact block", "table_row": "in the table row naming only this person"}


def _org_domains(orgs: list[dict[str, Any]]) -> list[str]:
    """The organisations' own web domains, for the e-mail domain check. A host that is an IP address or has no dot (a local or test host)
    says nothing about which e-mail domain is the organisation's, so it is left out rather than making every address look foreign."""
    out = []
    for o in orgs:
        w = (o.get("website") or "").lower()
        if "://" in w:
            host = w.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0].removeprefix("www.")
            if "." in host and not re.fullmatch(r"[\d.]+", host):
                out.append(host)
    return out


def _annotate(tx: Database, person_id: str, note: str, *, rdoc: str | None, url: str | None, quote: str | None, session_ref: str | None) -> None:
    """An annotation on a person's evidence (a re-check outcome, a historical address). Stored as a note — outside the passage
    de-duplication, which would otherwise drop it because it quotes a passage already recorded — and never twice with the same text."""
    if tx.one("person_note_exists", person=person_id, note=note):
        return
    tx.scalar("rel_evidence_add2", person=person_id, supports="relevance", kind="note", doc=None, rdoc=rdoc, url=url, quote=(quote or "")[:300] or None,
              note=note, session_ref=session_ref)


def _person_emails(db: Database, ctx: _Ctx, people: list[dict[str, Any]]) -> int:
    """A person's published professional e-mail, under the attribution rule (`domain.email_attribution`).

    * Ownership: the page must tie the address to that individual (explicit statement, contact block, table row). A matching local part,
      an unexplained other domain, a supplier's or partner's contact, or a passage shared by several people leaves it a candidate pending
      review. When two people of the same name are recorded, the passage must also name the person's organisation (or the address be on its
      domain).
    * Currency: an address a page marks obsolete, replaced, withdrawn or a former employee's is kept as historical evidence, never offered as
      a current route. When one page presents an address as current and another as obsolete, the conflict is shown and the address goes to
      review. Publication is never a claim of deliverability.
    * A later page stating a different address flags the record for re-checking rather than overwriting it; an address a person has
      verified is never changed by research."""
    found = 0
    bodies = db.all("rdoc_bodies", disc=None, id=ctx.scope.get("opportunity_id"), org=ctx.scope.get("org_research_id"))
    names = [p["full_name"] for p in people]
    name_count: dict[str, int] = {}
    for n in names:
        name_count[n.lower()] = name_count.get(n.lower(), 0) + 1
    domains = _org_domains(ctx.run.orgs)
    org_site = {str(o["id"]): (_org_domains([o]) or [None])[0] for o in ctx.run.orgs}
    org_names = [o["name"] for o in ctx.run.orgs]
    pages = [(d, ea.attribute(d.get("body_text") or "", list(dict.fromkeys(names)), org_domains=domains, org_names=org_names))
             for d in bodies if "@" in (d.get("body_text") or "")]
    for p in people:
        name = p["full_name"]
        clear: list[tuple[ea.Attribution, dict[str, Any]]] = []
        pending: list[tuple[ea.Attribution, dict[str, Any]]] = []
        historical: list[tuple[ea.Attribution, dict[str, Any]]] = []
        for d, att in pages:
            c, pend = ea.for_person(att, name)
            if c and name_count[name.lower()] > 1:
                # a namesake is recorded: the passage must also name this person's organisation, or the address be on its domain
                own_dom = org_site.get(str(p.get("organisation_id")))
                if not ((p.get("organisation") and p["organisation"].lower() in c.quote.lower()) or (own_dom and c.email.endswith("@" + own_dom))):
                    # a copy: the attribution is shared by every person of this name, so it is never changed in place
                    pend = [*pend, dataclasses.replace(c, person=None, confidence="ambiguous", candidates=[name],
                                                       reason=f"another person named {name} is recorded; the passage does not say which one ({c.reason}): pending review")]
                    c = None
            if c:
                clear.append((c, d))
            pending.extend((x, d) for x in pend)
            historical.extend((h, d) for h in ea.historical_for(att, name))
        hist_addrs = {h.email for h, _d in historical}
        conflict = [(a, d) for a, d in clear if a.email in hist_addrs]
        clear = [(a, d) for a, d in clear if a.email not in hist_addrs]
        with db.transaction() as tx:
            st = (tx.one("person_research_status", id=str(p["id"])) or {}).get("research_status") or {}
            now = _now().isoformat()
            for h, d in historical:                                           # historical evidence, kept and labelled, never a route
                _annotate(tx, str(p["id"]), f"historical e-mail address {h.email}: {h.currency_reason} — not a current contact route",
                          rdoc=str(d["id"]), url=d.get("url"), quote=h.quote, session_ref=ctx.meta.session_ref)
            if historical:
                st["email_history"] = sorted({*(st.get("email_history") or []), *hist_addrs})
            current = (p.get("published_email") or "").lower() or None
            pstatus = p.get("published_email_status")
            if current:
                if current in hist_addrs:
                    h, d = next((h, d) for h, d in historical if h.email == current)
                    is_conflict = any(a.email == current for a, _ in conflict)
                    if pstatus != "verified":
                        tx.run("person_email_status_set", id=str(p["id"]), status="under_review" if is_conflict else "historical")
                    st["email"] = {"status": "conflict" if is_conflict else "historical", "at": now, "value": current, "url": d.get("url"),
                                   "detail": (("sources conflict: one page presents it as current, another says " if is_conflict else "a page says ")
                                              + (h.currency_reason or "it is no longer valid")
                                              + (" (verified by a person — kept, re-check)" if pstatus == "verified" else ""))}
                    tx.run("person_research_status_set", id=str(p["id"]), status=st)
                    continue
                other = [(a, d) for a, d in clear if a.email != current]
                same = [(a, d) for a, d in clear if a.email == current]
                if other and pstatus not in ("under_review", "historical"):
                    a, d = other[0]
                    if pstatus != "verified":                                    # a person's verification survives research
                        tx.run("person_email_status_set", id=str(p["id"]), status="under_review")
                    tx.scalar("rel_evidence_add2", person=str(p["id"]), supports="relevance", kind="research_document", doc=None, rdoc=str(d["id"]), url=d.get("url"),
                              quote=a.quote, note=f"changed evidence: this page ties {a.email} to the person ({EMAIL_BASIS_LABELS[a.basis]}); {current} is recorded — re-check",
                              session_ref=ctx.meta.session_ref)
                    st["email"] = {"status": "recheck", "at": now, "detail": f"a page read now states {a.email}; {current} is recorded" + (" (verified by a person, kept)" if pstatus == "verified" else ""),
                                   "value": a.email, "url": d.get("url")}
                elif same and not (st.get("email") or {}).get("basis"):
                    a, d = same[0]
                    st["email"] = {"status": "found", "at": now, "detail": d.get("url"), "basis": a.basis, "basis_label": EMAIL_BASIS_LABELS[a.basis],
                                   "supporting": a.supporting}
                tx.run("person_research_status_set", id=str(p["id"]), status=st)
                continue
            if clear:
                a, d = clear[0]
                if tx.scalar("person_email_set", id=str(p["id"]), email=a.email, status="published", url=d.get("url")):
                    tx.scalar("rel_evidence_add2", person=str(p["id"]), supports="relevance", kind="research_document", doc=None, rdoc=str(d["id"]), url=d.get("url"),
                              quote=a.quote, note=f"published e-mail address: {EMAIL_BASIS_LABELS[a.basis]}" + (f"; supporting: {'; '.join(a.supporting)}" if a.supporting else ""),
                              session_ref=ctx.meta.session_ref)
                    found += 1
                st["email"] = {"status": "found", "at": now, "detail": d.get("url"), "basis": a.basis, "basis_label": EMAIL_BASIS_LABELS[a.basis], "supporting": a.supporting}
            elif conflict:
                a, d = conflict[0]
                h = next(h for h, _ in historical if h.email == a.email)
                st["email"] = {"status": "conflict", "at": now, "value": a.email, "url": d.get("url"),
                               "detail": f"sources conflict: one page ties {a.email} to the person, another says {h.currency_reason} — not assigned, review"}
            elif pending:
                a, d = pending[0]
                st["email"] = {"status": "candidate", "at": now, "value": a.email, "url": d.get("url"), "detail": a.reason + " (not assigned)",
                               "candidates": a.candidates, "supporting": a.supporting}
            elif historical:
                h, d = historical[0]
                st["email"] = {"status": "historical", "at": now, "value": h.email, "url": d.get("url"),
                               "detail": f"only a historical address was found ({h.currency_reason}); no current address tied to the person"}
            else:
                st["email"] = {"status": "not_found_after_research" if bodies else "not_searched", "at": now,
                               "detail": f"{len(bodies)} page(s) read; no address tied to the person" if bodies else "no page read yet"}
            tx.run("person_research_status_set", id=str(p["id"]), status=st)
    return found


OLD_RULE_NOTE = "published e-mail address beside the person's name on a page read"
RECHECK_VERSION = "4.8.0"


def recheck_published_emails(db: Database, meta: RequestMeta) -> dict[str, Any]:
    """Re-examine every recorded person address that a person has not verified against the current rule (ownership needs explicit
    evidence; currency), on the page or passage it came from — including addresses assigned in 4.6.0 (first address in the sentence) and in
    4.7.0 (a matching local part alone). Confirmed assignments keep the address and gain the basis; an address the source marks obsolete
    becomes historical; anything else keeps its value and evidence and goes to review. Addresses a person verified are never changed —
    a conflicting source only adds an evidence note and a re-check flag. Every outcome is recorded as evidence and in the audit log.
    Idempotent per version."""
    rows = db.all("people_published_for_recheck", version=RECHECK_VERSION)
    out = {"examined": len(rows), "confirmed": 0, "flagged": 0, "historical": 0, "verified_kept": 0}
    for p in rows:
        names = [x["full_name"] for x in db.all("people_at_orgs", orgs=[str(p["organisation_id"])])] if p.get("organisation_id") else [p["full_name"]]
        if p["full_name"] not in names:
            names.append(p["full_name"])
        domains = _org_domains([{"website": p.get("website")}])
        text = p.get("body_text") or p.get("quote") or ""
        att = ea.attribute(text, names, org_domains=domains, org_names=[p.get("organisation") or ""])
        email = (p["published_email"] or "").lower()
        clear, pend = ea.for_person(att, p["full_name"])
        hist = [h for h in ea.historical_for(att, p["full_name"]) if h.email == email] or [a for a in att if a.email == email and a.currency == "historical"]
        verified = p.get("published_email_status") == "verified"
        with db.transaction() as tx:
            st = (tx.one("person_research_status", id=str(p["id"])) or {}).get("research_status") or {}
            stamp = {"rechecked_at": _now().isoformat(), "recheck_version": RECHECK_VERSION}
            if hist:
                if verified:
                    out["verified_kept"] += 1
                    st["email"] = {**(st.get("email") or {}), **stamp, "status": "recheck", "detail": f"verified by a person — kept; the source says {hist[0].currency_reason}"}
                    note = f"re-check {RECHECK_VERSION}: the source says the address is no longer valid ({hist[0].currency_reason}); verified by a person, kept — re-check"
                else:
                    tx.run("person_email_status_set", id=str(p["id"]), status="historical")
                    st["email"] = {**(st.get("email") or {}), **stamp, "status": "historical", "value": email, "detail": hist[0].currency_reason}
                    st["email_history"] = sorted({*(st.get("email_history") or []), email})
                    note = f"re-check {RECHECK_VERSION}: historical — {hist[0].currency_reason}; kept as evidence, not a current route"
                    out["historical"] += 1
            elif clear and clear.email == email:
                st["email"] = {**(st.get("email") or {}), **stamp, "status": "found", "basis": clear.basis, "basis_label": EMAIL_BASIS_LABELS[clear.basis],
                               "supporting": clear.supporting, "detail": p.get("source_url")}
                note = f"re-check {RECHECK_VERSION}: confirmed — {EMAIL_BASIS_LABELS[clear.basis]}"
                out["confirmed"] += 1
            elif verified:
                out["verified_kept"] += 1
                note = None
                st["email"] = {**(st.get("email") or {}), **stamp}
            else:
                why = next((a.reason for a in att if a.email == email), "the passage does not tie the address to this person")
                tx.run("person_email_status_set", id=str(p["id"]), status="under_review")
                st["email"] = {**(st.get("email") or {}), **stamp, "status": "candidate", "value": email, "detail": f"re-check {RECHECK_VERSION}: {why}",
                               "candidates": (pend[0].candidates if pend else [p["full_name"]])}
                note = f"re-check {RECHECK_VERSION}: uncertain — {why}; previous evidence kept, flagged for review"
                out["flagged"] += 1
            tx.run("person_research_status_set", id=str(p["id"]), status=st)
            if note:
                _annotate(tx, str(p["id"]), note, rdoc=p.get("research_document_id"), url=p.get("source_url"), quote=p.get("quote"), session_ref=meta.session_ref)
    if rows:
        audit(db, "person_email_recheck", meta, entity_type="people", entity_id=None, detail={**out, "version": RECHECK_VERSION})
    return out


def _relationships(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """What WFC already has: recorded relationships, introduction routes, people confirmed; no fetching."""
    db = ctx.db
    org_ids = [str(o["id"]) for o in ctx.run.orgs]
    people = db.all("people_at_orgs", orgs=org_ids) if org_ids else []
    if ctx.etype == "opportunity":
        from .relationship_service import opportunity_relationships
        rels = opportunity_relationships(db, ctx.eid)
        counts = {"people": len(rels["people"]), "coverage": rels["coverage"], "relationships": len(rels["relationships"]),
                  "routes_available": len(rels["routes_available"]), "routes_possible": len(rels["routes_possible"]), "gaps": len(rels["gaps"])}
        return "done", f"relationship position: {rels['coverage_label']}; {counts['relationships']} relationship(s), {counts['routes_available']} route(s) available", counts
    active = sum(int(p.get("relationships") or 0) for p in people)
    routes = sum(int(p.get("routes") or 0) for p in people)
    reps = db.all("org_relationships", org=ctx.eid)
    counts = {"people": len(people), "relationships": active, "routes": routes, "representations": len(reps)}
    return "done", f"{len(people)} person(s), {active} active relationship(s), {routes} route(s); {len(reps)} representation or partnership entries", counts


def _relevance(ctx: _Ctx) -> tuple[str, str, dict[str, Any]]:
    """Fit, evidence, completeness, relationship position and opportunity status, kept apart, per organisation."""
    db = ctx.db
    module = ctx.scope.get("module")
    wanted = ci.kinds_for([module] if module else [])
    brief_airports = [a["airport_ident"] for a in db.all("opp_airports", id=ctx.eid)] if ctx.etype == "opportunity" else []
    record = None
    if ctx.etype == "opportunity":
        rows = db.all("records_list", types=None, modules=None, geo=None, tender=None, progress=None, coverage=None, org=None, q=None, deadline_days=None,
                      saved=None, since=None, id=ctx.eid, sort="created", limit=1, offset=0)
        record = rows[0] if rows else None
    summary = []
    ctx.queue("relevance", ctx.run.orgs)
    for o in ctx.run.orgs:
        ctx.item("relevance", o, "done", "assessed")
        parts = cmp.assess(db, str(o["id"]), wanted_kinds=wanted, brief_countries=ctx.scope["countries"], brief_airports=brief_airports,
                           brief_terms=ci.brief_terms(ctx.scope.get("title")), record=record)
        summary.append({"organisation_id": str(o["id"]), "name": o["name"], "fit": parts["fit"]["score"], "fit_band": parts["fit"]["band"],
                        "evidence": parts["evidence"]["band"], "completeness": parts["completeness"]["score"], "freight_scope": parts["freight_scope"],
                        "in_scope": asm.in_cargo_scope(parts["freight_scope"])})
    out_of_scope = [s for s in summary if not s["in_scope"]]
    counts = {"assessed": len(summary), "out_of_scope": len(out_of_scope), "organisations": summary, **ctx.counts("relevance")}
    detail = f"{len(summary)} organisation(s) assessed" + (f"; {len(out_of_scope)} passenger-only, outside the cargo scope" if out_of_scope else "")
    return "done", detail, counts


_STAGE_FN = {"identify": _identify, "identity": _identity, "company": _company, "people": _people, "relationships": _relationships, "relevance": _relevance}


def _opportunity_airports(db: Database, ctx: _Ctx) -> None:
    """Airports named with an IATA code in the opportunity's source documents: scope of the opportunity (never a company's office)."""
    rx = re.compile(r"\b(between|from|to|at|via|serving|gateway at|hub at)\b([^.;\n]{0,60}?)\(([A-Z]{3})\)", re.I)
    more = re.compile(r"\s*(?:,|and|&)\s+[^.;\n(]{0,60}?\(([A-Z]{3})\)")
    source_urls = {(d.get("canonical_url") or "").rstrip("/") for d in db.all("opportunity_documents", id=ctx.eid)}
    for d in db.all("rdoc_bodies", disc=None, id=ctx.eid, org=None):
        if d.get("origin") != "opportunity_source" and (d.get("url") or "").rstrip("/") not in source_urls:
            continue
        text = d.get("body_text") or ""
        for m in rx.finditer(text[:20000]):
            a = ad.resolve(db, m.group(3))
            if not a:
                continue
            w = m.group(1).lower()
            role = "origin" if w in ("from", "between") else "destination" if w == "to" else "gateway" if "gateway" in w or w == "via" else "scope"
            basis = " ".join(text[max(0, m.start() - 60): m.end() + 30].split())[:200]
            db.run("opp_airport_upsert", opp=ctx.eid, ident=a["ident"], role=role, support="supported", basis=basis)
            nxt = more.match(text, m.end())
            if nxt:
                b = ad.resolve(db, nxt.group(1))
                if b:
                    db.run("opp_airport_upsert", opp=ctx.eid, ident=b["ident"], role="destination" if role == "origin" else role, support="supported", basis=basis)


# ===================================================================== the research file
def research_file(db: Database, opp_id: str) -> dict[str, Any]:
    opp = db.one("opportunity_get2", id=opp_id)
    if opp is None:
        raise ResearchRejected(404, "Opportunity not found")
    from .relationship_service import opportunity_relationships
    rels = opportunity_relationships(db, opp_id)
    geo = db.all("opportunity_geo", id=opp_id)
    names = sorted({g["name"] for g in geo if g["support"] in ("supported", "internal_record")})
    rows = db.all("records_list", types=None, modules=None, geo=None, tender=None, progress=None, coverage=None, org=None, q=None, deadline_days=None, saved=None,
                  since=None, id=opp_id, sort="created", limit=1, offset=0)
    record = rows[0] if rows else dict(opp, coverage="none", reviewed_claims=0)
    record["gaps"] = opp.get("gaps") or []
    interp = ov.interpretation(record, names)
    docs = db.all("opportunity_documents", id=opp_id)
    airports = db.all("opp_airports", id=opp_id)
    orgs = list(rels["organisations"])
    for extra in db.all("opp_research_organisations", id=opp_id):
        if not any(str(o["id"]) == str(extra["id"]) for o in orgs):
            orgs.append(dict(extra, involvement="named in the research"))
    org_files = []
    for o in orgs:
        prof = cmp.profile(db, str(o["id"]))
        org_files.append({"id": str(o["id"]), "name": prof["canonical_name"], "role": o.get("involvement"), "kind_label": prof["kind_label"], "country_name": prof["country_name"],
                          "website": prof.get("website"), "website_basis": prof.get("website_basis"), "contact_url": prof.get("contact_url"),
                          "freight_scope": prof["freight_scope"], "freight_scope_label": prof["freight_scope_label"], "in_cargo_scope": prof["in_cargo_scope"],
                          "state_label": prof["state_label"], "verified_at": prof.get("verified_at"),
                          "emails": [{"value": c["value"], "status": c["status"], "status_label": c.get("status_label"), "department": c.get("department") or c.get("purpose"),
                                      "source_url": c.get("source_url"), "current": c["status"] in cmp.CURRENT_CONTACT, "note": c.get("source_note")}
                                     for c in prof["contacts"] if c["kind"] == "email"],
                          "airports": [{"label": f"{a.get('name') or a['airport_ident']} ({a.get('iata') or a['airport_ident']})", "role": a["role_label"], "status": a["status"]} for a in prof["airports"]],
                          "offices": prof.get("locations_text"), "services": prof.get("services_text"), "parent_group": prof.get("parent_group"),
                          "representation": [{"counterparty": r.get("counterparty"), "relationship": r["relationship_label"], "status": r["status_label"], "basis": r["basis"]} for r in prof["relationships"]],
                          "represented_by": prof["represented_by"], "people": len(prof["people"]), "research": prof["research"], "evidence_strength": prof["evidence_strength"],
                          "evidence": [{"supports": e["supports"], "quote": e["quote"], "url": e["url"], "note": e["note"], "observed_at": e["observed_at"], "source_kind": e["source_kind"]} for e in prof["evidence"]][:40]})
    people = []
    org_people = {str(x["id"]): x for x in (db.all("people_at_orgs", orgs=[str(o["id"]) for o in orgs]) if orgs else [])}
    for p in rels["people"]:
        prow = org_people.get(str(p["id"]))
        people.append({"id": str(p["id"]), "full_name": p["full_name"], "role_title": p.get("role_title"), "organisation": p.get("organisation"),
                       "remit_countries": [COUNTRIES.get(c, (c,))[0] for c in (p.get("remit_countries") or [])], "state_label": p["state_label"],
                       "involvement": p.get("involvement"), "involvement_label": p.get("involvement_label"),
                       "role_on_opportunity": p.get("role_on_opportunity"), "linkedin_profile_url": p.get("linkedin_profile_url"), "linkedin_search_url": p.get("linkedin_search_url"),
                       "published_email": (prow or {}).get("published_email"), "email_status": ((prow or {}).get("research_status") or {}).get("email", {}).get("status") or "not_searched",
                       "published_email_status": (prow or {}).get("published_email_status"), "email_research": ((prow or {}).get("research_status") or {}).get("email"),
                       "relationships": int((prow or {}).get("relationships") or 0), "routes": int((prow or {}).get("routes") or 0),
                       "evidence_quote": (prow or {}).get("quote") or p.get("quote"), "source_url": (prow or {}).get("source_url") or p.get("source_url")})
    st = stages(db, "opportunity", opp_id)
    uncertain: list[str] = []
    uncertain.extend(interp.get("unconfirmed") or [])
    uncertain.extend(rels["gaps"])
    for o in org_files:
        for e in o["emails"]:
            if e["status"] == "under_review":
                uncertain.append(f"{o['name']}: {e['value']} — sources conflict ({e.get('note') or 'review before use'})")
        grouped: dict[str, list[str]] = {}
        for f in o["research"]["fields"]:
            if f["status"] in ("not_found_after_research", "inaccessible", "incomplete", "not_searched"):
                grouped.setdefault(f["status_label"].lower(), []).append(f["label"].lower())
        for status_label, fields in grouped.items():
            uncertain.append(f"{o['name']}: {', '.join(fields)} — {status_label}")
        if o["freight_scope"] == "unresolved":
            uncertain.append(f"{o['name']}: freight scope unresolved")
    for p in people:
        if p.get("published_email_status") == "under_review":
            uncertain.append(f"{p['full_name']}: e-mail {p['published_email']} under review — " + ((p.get("email_research") or {}).get("detail") or "attribution not confirmed"))
        elif p["email_status"] == "candidate":
            uncertain.append(f"{p['full_name']}: candidate e-mail {(p.get('email_research') or {}).get('value')} not assigned — pending review")
        elif p["email_status"] == "recheck":
            uncertain.append(f"{p['full_name']}: a page now states a different e-mail — re-check")
        elif p["email_status"] == "conflict":
            uncertain.append(f"{p['full_name']}: sources conflict on {(p.get('email_research') or {}).get('value')} — " + ((p.get("email_research") or {}).get("detail") or "review"))
        elif p["email_status"] == "historical" or p.get("published_email_status") == "historical":
            uncertain.append(f"{p['full_name']}: only a historical address is known ({(p.get('email_research') or {}).get('value') or p.get('published_email')}) — no current route")
        elif p["email_status"] != "found" and not p.get("published_email"):
            uncertain.append(f"{p['full_name']}: no published e-mail " + ("found after research" if p["email_status"] == "not_found_after_research" else "searched yet"))
    seen: set[str] = set()
    uncertain = [u for u in uncertain if not (u in seen or seen.add(u))][:30]
    prog = progress(db, "opportunity", opp_id)
    if prog["failed"]:
        uncertain.insert(0, f"Research: {prog['failed']} organisation-stage item(s) failed and are unresolved — retry the failed organisations")
    if prog["pending"]:
        uncertain.insert(0, f"Research: {prog['pending']} organisation-stage item(s) pending — continue the research")
    # a person's own next action first; then unfinished research (it changes everything below it); then the relationship suggestion
    next_action = (opp.get("next_action")
                   or ("Retry the failed organisations" if prog["state"] in ("failed", "complete_with_failures") else None)
                   or ("Continue the staged research" if prog["state"] == "incomplete" else None)
                   or (rels["actions"][0] if rels["actions"] else None)
                   or ("Run the staged research" if prog["state"] == "not_run" else "Review the file and decide whether to pursue"))
    return {
        "opportunity": {"id": opp_id, "title": opp["title"], "record_type": opp["record_type"], "record_type_label": ov.RECORD_TYPE_LABELS.get(opp["record_type"], opp["record_type"]),
                        "module": opp["module"], "category": ov.CATEGORY_LABELS.get(opp["module"], opp["module"]), "progress": opp.get("progress"),
                        "tender_status": opp.get("tender_status"), "tender_status_label": ov.TENDER_STATUS_LABELS.get(opp.get("tender_status") or "", None),
                        "origin_interpretation": opp.get("origin_interpretation"), "next_action": opp.get("next_action"), "next_action_due": opp.get("next_action_due")},
        "summary": {
            "what": {"text": opp["title"], "sources": [{"title": d["title"], "url": d["canonical_url"], "published_at": d["published_at"]} for d in docs][:6],
                     "source_count": len(docs)},
            "why": {"text": interp.get("text"), "label": interp.get("label"), "unconfirmed": interp.get("unconfirmed") or [], "priority_reason": ov.priority(record)[1]},
            "organisations": [{"id": o["id"], "name": o["name"], "role": o["role"], "kind_label": o["kind_label"], "freight_scope_label": o["freight_scope_label"],
                               "in_cargo_scope": o["in_cargo_scope"]} for o in org_files],
            "geography": {"countries": names, "airports": [{"label": f"{a.get('name') or a['airport_ident']} ({a.get('iata') or a['airport_ident']})", "role": a["role"], "support": a["support"]} for a in airports],
                          "company_airports": [{"company": o["name"], **a} for o in org_files for a in o["airports"]]},
            "services": {"category": ov.CATEGORY_LABELS.get(opp["module"], opp["module"]), "service": opp.get("service"), "related": []},
            "people": people,
            "external_contacts": [{"id": str(x["id"]), "full_name": x["full_name"], "role_title": x.get("role_title"), "involvement": x.get("involvement"),
                                   "involvement_label": x.get("involvement_label"), "organisation": x.get("involvement_org") or x.get("organisation"),
                                   "basis": x.get("involvement_basis")} for x in rels.get("external_contacts", [])],
            "routes": [{"company": o["name"], "website": o["website"], "contact_page": o["contact_url"], "emails": o["emails"]} for o in org_files],
            "relationships": {"coverage": rels["coverage"], "coverage_label": rels["coverage_label"], "recorded": rels["relationships"],
                              "routes_available": rels["routes_available"], "routes_possible": rels["routes_possible"],
                              "representation": [{"company": o["name"], **r} for o in org_files for r in o["representation"]]},
            "uncertain": uncertain,
            "next_action": next_action,
        },
        "stages": st,
        "queue": queue_items(db, "opportunity", opp_id),
        "progress": progress(db, "opportunity", opp_id),
        "companies": org_files,
        "supporting": {"documents": rels["documents"], "latest_research": rels["latest_research"], "searches": (rels["latest_research"] or {}).get("searches") or [],
                       "linkedin_searches": rels["searches"], "target_roles": rels["target_roles"]},
        "rule": "The file is the record: every statement carries its source or says it was not found. Research completeness and relationship position are shown "
                "beside fit and evidence, never added into one number. Not a probability of winning.",
    }


INVOLVEMENT_VERSION = "4.9.0"


def recheck_involvement(db: Database, meta: RequestMeta) -> dict[str, Any]:
    """Re-classify every research-recorded person's involvement from the passages already on record (4.9.0): a third-party press contact
    named in an announcement stops counting as a commercial contact; useful external contacts keep their role. A person's own setting is
    never changed. Opportunity links follow (candidate ⇄ external contact; a person's relevant / not-relevant decision is never changed).
    Every change is an evidence note; the run is audited. Idempotent per version."""
    from ..domain import involvement as inv
    out = {"examined": 0, "changed": 0, "press_contact": 0, "external_adviser": 0, "appointed_representative": 0, "employee": 0, "unresolved": 0,
           "links_moved": 0}
    for p in db.all("people_for_involvement_recheck", version=INVOLVEMENT_VERSION):
        out["examined"] += 1
        quotes = p.get("quotes") or ""
        org = p.get("organisation") or p.get("role_org_label")
        new, basis = inv.classify(quotes, p.get("role_title"), org, p.get("affiliation") or "unknown", [x for x in (p.get("subject_orgs") or []) if x])
        out[new] += 1
        with db.transaction() as tx:
            st = (tx.one("person_research_status", id=str(p["id"])) or {}).get("research_status") or {}
            if new != p["involvement"]:
                if tx.scalar("person_involvement_set", id=str(p["id"]), inv=new, basis=basis, org=org if new in inv.EXTERNAL else None):
                    out["changed"] += 1
                    _annotate(tx, str(p["id"]), f"involvement re-check {INVOLVEMENT_VERSION}: {inv.LABELS[p['involvement']]} → {inv.LABELS[new]} — {basis}",
                              rdoc=None, url=None, quote=quotes[:300], session_ref=meta.session_ref)
            out["links_moved"] += len(tx.all("opp_links_external_sync", id=str(p["id"])))
            st["involvement_version"] = INVOLVEMENT_VERSION
            tx.run("person_research_status_set", id=str(p["id"]), status=st)
    if out["examined"]:
        audit(db, "person_involvement_recheck", meta, entity_type="people", entity_id=None, detail={**out, "version": INVOLVEMENT_VERSION})
    return out
