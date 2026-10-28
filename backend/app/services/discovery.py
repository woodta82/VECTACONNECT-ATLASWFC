"""Country-based opportunity discovery (directive §4) and source runs (§5).

A search selects geography (one country, several, regions, or worldwide),
any of the nine capability areas, and optional organisation, airline,
keyword and date filters. Running it RETRIEVES new documents: it plans the
enabled sources whose coverage intersects the geography and capability
areas, fetches them (search-template URLs per country, listing pages, RSS
feeds, single pages) through the SSRF-safe fetcher, extracts readable
content, proposes claims with the budget-controlled AI extractor, validates
them field by field, resolves entities, links evidence and updates signals
and opportunities. It then reports which signals MATCH the search and why.

Outcomes are kept distinct and never overstated:
- results / no relevant results;
- partial coverage: some selected countries have no covering source;
- source failure: every planned source failed;
- incomplete: ANY potentially relevant target was not fully processed: a
  failed retrieval, a document in a language the source does not permit, an
  extraction that did not run (AI not connected, budget refused, the run's
  spending bound reached, failure), an extraction whose every claim was
  rejected, or targets beyond the per-run limits. Each such target is listed
  on the run with its reason (review of 26 Oct 2026, §2).
- no sources: nothing covered the search, so nothing was searched.
Coverage is always reported as "N sources covering X of Y countries"; a
worldwide search is never described as complete.

Repeated runs are idempotent: an already-stored document with claims is not
re-extracted; signals and opportunities are upserted on stable keys.

Spending: every run has an approved upper bound (`budget_cap_usd`) equal to the
plan's upper-bound estimate, computed from the SAME per-source document limits
the executor enforces (`_doc_bound`). Each AI call reserves against that bound
atomically (`reserve_run_budget`), together with the monthly cap and kill
switch; a retry spends against its original run's bound.

Dates: a document's publication date comes from the page, else from the feed
item that linked it (provenance kept). With a date filter, documents whose date
is unknown are either processed and flagged (default) or excluded and listed
(`date_filter = strict`); they are never presented as verified in-period.

Coverage: a template source that needs more country queries than the per-run
limit continues from a saved checkpoint on the next run of the same search;
planned, attempted, retrieved and extracted countries are reported separately.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

from ..ai import extraction as ai
from ..config import Settings
from ..domain import content as ct
from ..domain import publication
from ..domain import retrieval
from ..reference.geography import COUNTRIES, expand_geography
from ..repo.db import Database
from . import ingestion as ing
from . import reading
from ..domain import sections as sec_mod

log = logging.getLogger("atlas.discovery")

MODULES = ("airline_representation", "account_growth", "forwarder_sales", "capacity_lanes", "service_operations",
           "trucking_gateways", "outsourcing_training", "technology_solutions", "network_development")
MAX_URLS_PER_SOURCE_PER_RUN = 25           # documents fetched and extracted per source per run (cost control)
MAX_COUNTRY_QUERIES_PER_SOURCE = 60
MAX_LINK_ATTEMPTS = 3                       # a queued link that fails to fetch this many times is given up (and listed)        # per-country search pages per template source per run
SCOPE_ROLES = ("delivery", "contract_territory", "origin", "destination")


class DiscoveryRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class RunCancelled(Exception):
    pass


# ===================================================================== searches


@dataclass
class SearchSpec:
    geo_mode: str
    countries: list[str]
    regions: list[str]
    modules: list[str]
    organisation: str | None = None
    airline: str | None = None
    keywords: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    name: str | None = None
    saved: bool = False
    date_filter: str = "include_unknown"


def validate_spec(db: Database, spec: SearchSpec) -> SearchSpec:
    if spec.geo_mode not in ("country", "countries", "region", "worldwide"):
        raise DiscoveryRejected(422, "geo_mode must be country, countries, region or worldwide")
    countries = sorted({c.strip().upper() for c in spec.countries if c and c.strip()})
    bad = [c for c in countries if c not in COUNTRIES]
    if bad:
        raise DiscoveryRejected(422, f"unknown country code(s): {', '.join(bad)}")
    known_regions = {r["code"] for r in db.all("regions_list")}
    regions = sorted({r.strip().upper() for r in spec.regions if r and r.strip()})
    bad = [r for r in regions if r not in known_regions]
    if bad:
        raise DiscoveryRejected(422, f"unknown region(s): {', '.join(bad)}")
    if spec.geo_mode == "country" and len(countries) != 1:
        raise DiscoveryRejected(422, "single-country search needs exactly one country")
    if spec.geo_mode == "countries" and not countries:
        raise DiscoveryRejected(422, "select at least one country")
    if spec.geo_mode == "region" and not regions:
        raise DiscoveryRejected(422, "select at least one region")
    if spec.geo_mode == "worldwide":
        countries, regions = [], []
    modules = sorted({m for m in spec.modules if m})
    bad = [m for m in modules if m not in MODULES]
    if bad:
        raise DiscoveryRejected(422, f"unknown capability area(s): {', '.join(bad)}")
    if spec.date_from and spec.date_to and spec.date_to < spec.date_from:
        raise DiscoveryRejected(422, "date_to is before date_from")
    if spec.saved and not (spec.name and spec.name.strip()):
        raise DiscoveryRejected(422, "a saved search needs a name")
    if spec.date_filter not in ("include_unknown", "strict"):
        raise DiscoveryRejected(422, "date_filter must be include_unknown or strict")
    return SearchSpec(spec.geo_mode, countries, regions, modules, (spec.organisation or "").strip() or None,
                      (spec.airline or "").strip() or None, (spec.keywords or "").strip() or None, spec.date_from, spec.date_to,
                      (spec.name or "").strip() or None, spec.saved, spec.date_filter)


def create_search(db: Database, spec: SearchSpec) -> str:
    s = validate_spec(db, spec)
    return str(db.scalar("search_insert", name=s.name, saved=s.saved, geo_mode=s.geo_mode, countries=s.countries, regions=s.regions,
                         modules=s.modules, organisation=s.organisation, airline=s.airline, keywords=s.keywords,
                         date_from=s.date_from, date_to=s.date_to, date_filter=s.date_filter))


def _custom_regions(db: Database) -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {}
    for r in db.all("region_members"):
        out.setdefault(r["region_code"], []).append(r["country_code"])
    return {k: tuple(v) for k, v in out.items()}


def country_set(db: Database, search: dict[str, Any]) -> set[str] | None:
    return expand_geography(search["geo_mode"], list(search["countries"] or []), list(search["regions"] or []), _custom_regions(db))


# ===================================================================== planning


def plan(db: Database, search: dict[str, Any] | None, source_id: str | None, settings: Settings) -> dict[str, Any]:
    """Which sources this run will use, which selected countries no source
    covers, and an upper-bound cost estimate."""
    if source_id:
        src = db.one("source_get", id=source_id)
        if src is None or src["deleted_at"] is not None:
            raise DiscoveryRejected(404, "source not found")
        if src["source_type"] == "file_import":
            raise DiscoveryRejected(422, "file-import sources are loaded through Data Sources and Imports")
        sources = [src]
        wanted: set[str] | None = None
        modules: list[str] = []
    else:
        assert search is not None
        wanted = country_set(db, search)
        modules = list(search["modules"] or [])
        sources = []
        for s in db.all("sources_discoverable"):
            covers = set(s["country_coverage"] or [])
            geo_ok = wanted is None or s["global_coverage"] or bool(covers & wanted)
            mod_ok = not modules or not (s["modules"] or []) or bool(set(s["modules"]) & set(modules))
            if geo_ok and mod_ok:
                sources.append(s)
    covered: set[str] = set()
    global_sources = [s for s in sources if s["global_coverage"]]
    for s in sources:
        covered |= set(s["country_coverage"] or [])
    gaps: list[str] = []
    if wanted is not None:
        if not global_sources:
            gaps = sorted(wanted - covered)
    per_doc = ai.estimate_per_document(settings)
    bounds = {str(s["id"]): _doc_bound(s, wanted) for s in sources}
    max_docs = sum(bounds.values())
    return {
        "countries": sorted(wanted) if wanted is not None else "worldwide",
        "modules": modules or "all",
        "sources": [{"id": str(s["id"]), "name": s["name"], "type": s["source_type"], "authority": s["authority"],
                     "global": bool(s["global_coverage"]), "countries": list(s["country_coverage"] or []),
                     "max_documents": bounds[str(s["id"])],
                     "country_queries": min(_country_queries(s, wanted), MAX_COUNTRY_QUERIES_PER_SOURCE)} for s in sources],
        "max_documents": max_docs,
        "planned_countries": sorted(_planned_countries(sources, wanted)),
        "coverage_gaps": gaps,
        "coverage_note": _coverage_note(len(sources), wanted, covered, bool(global_sources),
                                        capped=[s["name"] for s in sources if _country_queries(s, wanted) > MAX_COUNTRY_QUERIES_PER_SOURCE]),
        # An UPPER BOUND: the executor never extracts more documents than max_documents (see _doc_bound).
        "estimated_cost_usd": str((per_doc * max_docs).quantize(Decimal("0.0001"))) if per_doc is not None else None,
        "estimate_is_upper_bound": True,
        "estimate_basis": ("one extraction call (one section, about 17 KB of text) per document; longer documents are read completely "
                           "in further sections, within the same approved run ceiling — reading pauses at the ceiling and resumes "
                           "after approval or in the next run, and the document is shown as partly read until then"),
        # The approved ceiling for this run's AI spending: the upper-bound estimate, never more than this month's
        # per-run cap. Every call, retry and manual re-extraction for the run counts against it.
        "run_budget_cap_usd": _run_cap(db, per_doc, max_docs),
        "ai_status": "connected" if per_doc is not None else (ai.available(settings) or "not connected"),
    }


def _run_cap(db: Database, per_doc: Decimal | None, max_docs: int) -> str | None:
    if per_doc is None:
        return None
    per_run = db.scalar("budget_per_run_cap")
    if per_run is None:
        return "0.0000"
    return str(min(per_doc * max_docs, Decimal(per_run)).quantize(Decimal("0.0001")))


def _doc_bound(src: dict[str, Any], wanted: set[str] | None) -> int:
    """The most documents the executor will fetch and extract from this source in one run. The plan prices
    exactly this, and the executor enforces exactly this, so a run cannot extract more than it priced."""
    per_page = int(src["max_items"] or 1)
    if src["source_type"] == "web_page":
        return 1
    if src["source_type"] == "search_template":
        queries = min(_country_queries(src, wanted), MAX_COUNTRY_QUERIES_PER_SOURCE)
        return min(per_page * queries, MAX_URLS_PER_SOURCE_PER_RUN)
    return min(per_page, MAX_URLS_PER_SOURCE_PER_RUN)


def _planned_countries(sources: list[dict[str, Any]], wanted: set[str] | None) -> set[str]:
    out: set[str] = set()
    for s in sources:
        cover = set(s["country_coverage"] or [])
        if wanted is None:
            out |= cover
        else:
            out |= wanted if s["global_coverage"] else (wanted & cover)
    return out


def _country_queries(src: dict[str, Any], wanted: set[str] | None) -> int:
    """How many per-country search pages a template source would need for this geography."""
    if src["source_type"] != "search_template" or "{country" not in (src["query_template"] or ""):
        return 1
    cover = set(src["country_coverage"] or [])
    if wanted is None:
        return len(cover) or 1
    return len(wanted) if src["global_coverage"] else len(wanted & cover)


def _coverage_note(n_sources: int, wanted: set[str] | None, covered: set[str], has_global: bool, capped: list[str] | None = None) -> str:
    cap = (f" Per run, {', '.join(capped)} search{'es' if len(capped) == 1 else ''} at most {MAX_COUNTRY_QUERIES_PER_SOURCE} countries; "
           "the countries not reached are listed on the run and it is marked incomplete." if capped else "")
    if n_sources == 0:
        return "No enabled source covers this geography and capability area. Nothing was searched."
    if wanted is None:
        return (f"Worldwide search across {n_sources} configured source(s). Results are limited to these sources and are "
                "not a complete worldwide view." + cap)
    hit = len(wanted & covered) if not has_global else len(wanted)
    return (f"{n_sources} source(s) covering {hit} of {len(wanted)} selected country(ies)"
            + (" (including sources with global coverage)" if has_global else "") + ". Results are limited to these sources." + cap)


def _set_run_budget(tx: Database, run_id: str, p: dict[str, Any], budget_root: str | None) -> None:
    """Approved spending bound: the plan's upper-bound estimate, never more than this month's per-run cap.
    A retry spends against its original run's bound and gets none of its own."""
    if budget_root:
        tx.run("run_set_budget", id=run_id, root=budget_root, cap=None)
        root = tx.one("run_get", id=budget_root)
        if root is not None and not (root["plan"] or {}).get("run_budget_cap_usd") and p.get("run_budget_cap_usd"):
            # The original run was planned while AI was unavailable, so it never had an approved ceiling. Retrying it
            # once AI is connected approves the retry's own upper-bound plan for the run family, once.
            tx.run("run_set_budget", id=budget_root, root=None, cap=Decimal(p["run_budget_cap_usd"]))
            tx.run("run_plan_set_cap", id=budget_root, cap=p["run_budget_cap_usd"])
        return
    tx.run("run_set_budget", id=run_id, root=None, cap=Decimal(p["run_budget_cap_usd"]) if p.get("run_budget_cap_usd") else Decimal("0"))


def start_run(db: Database, settings: Settings, *, search_id: str | None = None, source_id: str | None = None,
              trigger: str = "manual", retry_of: str | None = None, budget_root: str | None = None) -> dict[str, Any]:
    search = db.one("search_get", id=search_id) if search_id else None
    if search_id and (search is None or search["deleted_at"] is not None):
        raise DiscoveryRejected(404, "search not found")
    p = plan(db, search, source_id, settings)
    with db.transaction() as tx:
        run_id = str(tx.scalar("run_insert", search=search_id, source=source_id, trigger=trigger, plan=p,
                               estimated=Decimal(p["estimated_cost_usd"]) if p["estimated_cost_usd"] else None))
        _set_run_budget(tx, run_id, p, budget_root)
        job_id = tx.scalar("job_enqueue2", job_type="discovery_search", key=f"discovery-run:{run_id}", schedule=None,
                           payload={"run_id": run_id}, retry_of=retry_of)
        tx.run("run_set_job", id=run_id, job=str(job_id))
    return {"run_id": run_id, "job_id": str(job_id), "plan": p}


# ===================================================================== execution


def _urls_for(src: dict[str, Any], search: dict[str, Any] | None, wanted: set[str] | None) -> list[tuple[str, str | None]]:
    """(url, country) pairs to fetch for one source."""
    if src["source_type"] != "search_template":
        return [(src["base_url"], None)]
    template = src["query_template"] or src["base_url"]
    keywords = (search or {}).get("keywords") or ""
    airline = (search or {}).get("airline") or ""
    org = (search or {}).get("organisation") or ""
    countries: list[str | None]
    if "{country" in template:  # noqa: SIM108
        cover = set(src["country_coverage"] or [])
        if wanted is None:
            countries = list(sorted(cover)) if cover else [None]
        else:
            countries = list(sorted(wanted if src["global_coverage"] else (wanted & cover)))
    else:
        countries = [None]
    out = []
    for c in countries:
        url = (template.replace("{keywords}", quote_plus(keywords)).replace("{airline}", quote_plus(airline))
               .replace("{organisation}", quote_plus(org)).replace("{country}", quote_plus(c or ""))
               .replace("{country_name}", quote_plus(COUNTRIES[c][0] if c else "")))
        out.append((url, c))
    return out


def _date_status(published: datetime | None, search: dict[str, Any] | None) -> str:
    """'in_range', 'out_of_range', 'unknown' (date-filtered search, no date) or 'unfiltered'."""
    if not search or not (search.get("date_from") or search.get("date_to")):
        return "unfiltered"
    if published is None:
        return "unknown"
    d = published.date()
    if search.get("date_from") and d < search["date_from"]:
        return "out_of_range"
    if search.get("date_to") and d > search["date_to"]:
        return "out_of_range"
    return "in_range"


# Issue reasons. All but the deliberate exclusions make a run incomplete: a potentially relevant target was not processed.
MATERIAL_ISSUES = {"retrieval_failed", "language_not_permitted", "extraction_not_run", "extraction_rejected", "not_fetched_limit",
                   "budget_run_cap", "source_disabled", "document_partially_read"}
DELIBERATE_ISSUES = {"date_unknown_excluded"}
# Listed on the run but not incomplete work: the document was extracted, some proposed claims were rejected into review.
INFORMATIONAL_ISSUES = {"some_claims_rejected", "listing_links_not_followed"}
MAX_LISTED_ISSUES = 200


class _Ctx:
    """Progress, cancellation and lease heartbeat for one run."""

    def __init__(self, db: Database, run_id: str, job_ctx: Any):
        self.db = db
        self.run_id = run_id
        self.job_ctx = job_ctx
        self.progress: dict[str, Any] = {"sources_total": 0, "sources_done": 0, "documents_seen": 0, "documents_new": 0,
                                         "documents_extracted": 0, "current_source": None}

    def tick(self, **changes: Any) -> None:
        self.progress.update(changes)
        self.db.run("run_progress", id=self.run_id, progress=self.progress)
        if self.job_ctx is not None and not self.job_ctx.heartbeat(self.progress):
            raise RunCancelled()
        if self.db.scalar("run_status", id=self.run_id) == "cancelled":
            raise RunCancelled()


def _rotate(countries: list[str | None], offset: int) -> list[str | None]:
    if not countries or offset <= 0:
        return countries
    k = offset % len(countries)
    return countries[k:] + countries[:k]


def execute_run(db: Database, settings: Settings, run_id: str, job_ctx: Any = None, *,
                fetch: Any = None, transport: Any = None, now: datetime | None = None) -> dict[str, Any]:
    run = db.one("run_get", id=run_id)
    if run is None:
        raise DiscoveryRejected(404, "run not found")
    if run["status"] in ("completed", "partial", "failed", "cancelled"):
        return {"run_id": run_id, "status": run["status"], "skipped": "already finished"}
    search = db.one("search_get", id=str(run["search_id"])) if run["search_id"] else None
    wanted = country_set(db, search) if search else None
    db.run("run_start", id=run_id)
    fetch = fetch or (lambda url: retrieval.fetch(url, allow_private_hosts=frozenset(settings.retrieval_allow_private_hosts)))
    ctx = _Ctx(db, run_id, job_ctx)
    sources = run["plan"].get("sources", [])
    ctx.tick(sources_total=len(sources))
    counts: dict[str, Any] = {"documents": 0, "new_documents": 0, "skipped_out_of_range": 0, "skipped_language": 0, "unextracted": 0,
                              "failed_sources": 0, "partial_sources": 0, "succeeded_sources": 0, "claims": 0, "rejected_claims": 0,
                              "date_unknown": 0, "issues": [], "issue_counts": {},
                              "coverage": {"planned": list(run["plan"].get("planned_countries") or []), "attempted": [],
                                           "retrieved": [], "extracted": []}}
    touched: dict[str, dict[str, Any]] = {}   # signal_id -> {"is_new": bool, "sources": set, "date_unknown": bool}
    try:
        for s in sources:
            src = db.one("source_get", id=s["id"])
            if src is None or not src["enabled"] or src["deleted_at"] is not None:
                skipped: list[dict[str, Any]] = []
                _issue(counts, skipped, (src or {}).get("base_url") or s.get("name") or s["id"], "source_disabled",
                       f"{s.get('name') or 'source'} was disabled or deleted after the run was planned; it was not searched")
                db.run("run_source_set", run=run_id, source=s["id"], status="skipped", detail="source disabled since planning; not searched",
                       documents=0, new_documents=0, failures=0, issues=skipped)
                counts["skipped_sources"] = counts.get("skipped_sources", 0) + 1
                continue
            ctx.tick(current_source=src["name"])
            status = _run_source(db, settings, run_id, src, search, wanted, fetch, transport, ctx, counts, touched, now,
                                 bound=int(s.get("max_documents") or _doc_bound(src, wanted)))
            counts[{"succeeded": "succeeded_sources", "partial": "partial_sources", "failed": "failed_sources"}[status]] += 1
            ctx.tick(sources_done=ctx.progress["sources_done"] + 1)
    except RunCancelled:
        _finish(db, run_id, search, wanted, touched, counts, cancelled=True)
        return {"run_id": run_id, "status": "cancelled"}
    return _finish(db, run_id, search, wanted, touched, counts, cancelled=False)


def _issue(counts: dict[str, Any], issues: list[dict[str, Any]], url: str, reason: str, detail: str | None = None,
           country: str | None = None) -> None:
    item = {"url": url, "reason": reason, "detail": (detail or "")[:300] or None, "country": country}
    issues.append(item)
    counts["issue_counts"][reason] = counts["issue_counts"].get(reason, 0) + 1
    if len(counts["issues"]) < MAX_LISTED_ISSUES:
        counts["issues"].append(item)


def _run_source(db: Database, settings: Settings, run_id: str, src: dict[str, Any], search: dict[str, Any] | None,
                wanted: set[str] | None, fetch: Any, transport: Any, ctx: _Ctx, counts: dict[str, Any],
                touched: dict[str, dict[str, Any]], now: datetime | None, *, bound: int) -> str:
    """Process one source. Returns 'succeeded' (every target fully processed), 'partial' (some processed,
    some not) or 'failed' (nothing processed). Every target not fully processed is recorded with its reason."""
    ing_run = str(db.scalar("ingestion_run_start2", source=str(src["id"]), job=None, discovery_run=run_id))
    info = ing.SourceInfo(str(src["id"]), src["family"], src["authority"], src["base_url"], bool(src["retention_permitted"]))
    docs = new_docs = failures = 0
    issues: list[dict[str, Any]] = []
    cov = counts["coverage"]
    # (url, title hint, published hint, country of the query that found it)
    targets: list[tuple[str, str | None, datetime | None, str | None]] = []
    sid = str(src["id"])
    scope = f"search:{search['id']}" if search is not None else f"source:{sid}"
    states = {r["url"]: r["status"] for r in db.all("queue_states", scope=scope, source=sid)}
    # Relevant links an earlier run of this search could not finish are read FIRST (amendments item 5).
    for q in db.all("queue_pending", scope=scope, source=sid):
        targets.append((q["url"], q["title"], q["published_hint"], q["country"]))
    queued_before = len(targets)
    counts["queue_resumed"] = counts.get("queue_resumed", 0) + queued_before

    def enqueue(url: str, title: str | None, published: datetime | None, country: str | None, reason: str, error: str | None = None) -> None:
        db.run("queue_add", scope=scope, source=sid, url=url, title=(title or "")[:300] or None, country=country, published=published,
               reason=reason, run=run_id, error=(error or "")[:500] or None)

    queries = _urls_for(src, search, wanted)
    cursor = (search or {}).get("coverage_cursor") or {}
    cursor_plan: tuple[int, int] | None
    if len(queries) > MAX_COUNTRY_QUERIES_PER_SOURCE:
        # Resume where the previous run of this search stopped, then save where this one stops.
        offset = int((cursor.get(sid) or {}).get("offset", 0)) % len(queries)
        ordered = queries[offset:] + queries[:offset]
        skipped = [c for _u, c in ordered[MAX_COUNTRY_QUERIES_PER_SOURCE:] if c]
        counts["not_searched_countries"] = sorted(set(counts.get("not_searched_countries", [])) | set(skipped))
        queries = ordered[:MAX_COUNTRY_QUERIES_PER_SOURCE]
        cursor_plan = (offset, len(ordered))
    else:
        cursor_plan = None
    source_countries = sorted(_planned_countries([src], wanted)) if src["source_type"] != "search_template" else []
    any_query_ok = False
    first_failed: int | None = None
    for qi, (url, country) in enumerate(queries):
        for c in ([country] if country else source_countries):
            if c and c not in cov["attempted"]:
                cov["attempted"].append(c)
        try:
            fr = fetch(url)
            if src["source_type"] == "rss":
                items = ct.parse_feed(fr.body, fr.final_url)
                for item in items[: int(src["max_items"])]:
                    targets.append((item.link, item.title, item.published_at, country))
                for item in items[int(src["max_items"]):]:     # feed items are articles: each one left out is queued and listed
                    if states.get(item.link) in ("done", "gave_up", "pending"):   # pending ones are already targets
                        continue
                    enqueue(item.link, item.title, item.published_at, country, "feed_overflow")
                    _issue(counts, issues, item.link, "not_fetched_limit",
                           f"feed item beyond this source's per-run item limit of {src['max_items']}; queued for the next run", country)
            elif src["source_type"] in ("listing", "search_template"):
                page = ct.extract(fr.body, fr.content_type, fr.final_url)
                links = ct.same_site_links(page.links, fr.final_url, 2000)
                relevant = [(lk, tx) for lk, tx in links if ct.is_article_link(lk, tx, fr.final_url, (search or {}).get("keywords"))]
                for link, text in relevant[: int(src["max_items"])]:
                    targets.append((link, text or None, None, country))
                for link, text in relevant[int(src["max_items"]):]:
                    # Relevant links beyond the per-page item limit are queued for the next run and listed, never dropped.
                    if states.get(link) in ("done", "gave_up", "pending"):
                        continue                                  # read before, given up (listed), or already a target from the queue
                    enqueue(link, text, None, country, "listing_overflow")
                    _issue(counts, issues, link, "not_fetched_limit",
                           f"article link beyond this source's per-page item limit of {src['max_items']}; queued for the next run", country)
                if len(links) > len(relevant):
                    _issue(counts, issues, fr.final_url, "listing_links_not_followed",
                           f"{len(links) - len(relevant)} navigation link(s) on this page ignored (not articles or notices)", country)
            else:
                targets.append((fr.final_url, None, None, country))
        except (retrieval.RetrievalBlocked, retrieval.RetrievalFailed, ct.ContentUnavailable) as exc:
            failures += 1
            first_failed = qi if first_failed is None else first_failed
            _issue(counts, issues, url, "retrieval_failed", f"{exc.__class__.__name__}: {exc}", country)
            continue
        any_query_ok = True
        for c in ([country] if country else source_countries):
            if c and c not in cov["retrieved"]:
                cov["retrieved"].append(c)

    if cursor_plan is not None and search is not None:
        # Resume point for the next run: past every query that was retrieved; a failed query is retried first.
        start, total = cursor_plan
        done = first_failed if first_failed is not None else len(queries)
        db.run("search_set_cursor", id=str(search["id"]), source=sid,
               cursor={"offset": (start + done) % total, "total": total, "updated_at": datetime.now(timezone.utc).isoformat()})

    # The executor never processes more documents than the plan priced (bound). Order: links queued by earlier runs,
    # then links never seen before, then links already read completely (re-checked for changes only if room is left).
    unique: dict[str, tuple[str, str | None, datetime | None, str | None]] = {}
    for tgt in targets:
        unique.setdefault(tgt[0], tgt)
    states = {r["url"]: r["status"] for r in db.all("queue_states", scope=scope, source=sid)}   # now incl. this run's queueing
    pending = [t for t in unique.values() if states.get(t[0]) == "pending"]
    fresh = [t for t in unique.values() if t[0] not in states]
    recheck = [t for t in unique.values() if states.get(t[0]) == "done"]
    ordered_targets = (pending + fresh + recheck)
    for url, title, pub, country in ordered_targets[bound:]:
        if states.get(url) == "done":
            counts["rechecks_deferred"] = counts.get("rechecks_deferred", 0) + 1     # read before; nothing is left unread
            continue
        if states.get(url) == "gave_up":
            continue
        enqueue(url, title, pub, country, "not_fetched_limit")
        _issue(counts, issues, url, "not_fetched_limit",
               f"beyond this source's per-run limit of {bound} document(s); queued for the next run", country)
    for url, title_hint, feed_date, country in ordered_targets[:bound]:
        try:
            outcome = process_document(db, settings, info, src, url, ing_run, search, fetch, transport, ctx, now,
                                       feed_published=feed_date, run_id=run_id)
        except (retrieval.RetrievalBlocked, retrieval.RetrievalFailed, ct.ContentUnavailable) as exc:
            failures += 1
            enqueue(url, title_hint, feed_date, country, "retrieval_failed", f"{exc.__class__.__name__}: {exc}")
            gave_up = {r["url"] for r in db.all("queue_give_up", scope=scope, source=sid, max=MAX_LINK_ATTEMPTS)}
            _issue(counts, issues, url, "retrieval_failed", f"{exc.__class__.__name__}: {exc}"
                   + ("; given up after repeated failures" if url in gave_up else "; queued to retry on the next run"), country)
            continue
        complete = outcome.get("complete", True) and outcome.get("extraction_status") not in ("not_connected", "budget_refused", "failed")
        if outcome.get("skip") or complete:
            db.run("queue_done", scope=scope, source=sid, url=url, run=run_id)
        else:
            enqueue(url, title_hint, feed_date, country, "partially_read" if outcome.get("sections_read") else "unextracted",
                    outcome.get("extraction_detail"))
            if outcome.get("gave_up"):
                db.run("queue_mark_gave_up", scope=scope, source=sid, url=url)
        skip = outcome.get("skip")
        if skip == "out_of_range":
            counts["skipped_out_of_range"] += 1
            continue
        if skip == "date_unknown_excluded":
            _issue(counts, issues, url, "date_unknown_excluded", "publication date unknown; excluded by the search's strict date filter", country)
            continue
        if skip == "language_not_permitted":
            counts["skipped_language"] += 1
            _issue(counts, issues, url, "language_not_permitted",
                   f"document language {outcome.get('language')!r}; this source is not permitted to process local-language documents", country)
            continue
        docs += 1
        new_docs += 1 if outcome["document_new"] else 0
        counts["claims"] += outcome["claims"]
        counts["rejected_claims"] += outcome["rejected"]
        if outcome["date_unknown"]:
            counts["date_unknown"] += 1
        status = outcome["extraction_status"]
        if not outcome.get("complete", True) and outcome.get("sections_read", 0) > 0:
            # Part of the document was read; the rest waits. Never reported as checked or as "no opportunities".
            counts["unextracted"] += 1
            counts["partially_read"] = counts.get("partially_read", 0) + 1
            _issue(counts, issues, url, "document_partially_read",
                   f"read {outcome['sections_read']} of {outcome['sections_total']} section(s); {outcome.get('extraction_detail') or ''}"
                   " — the next run (or Retry / Continue reading) resumes at the first unread section", country)
        elif not outcome.get("complete", True) and outcome.get("budget_scope") == "run":
            counts["unextracted"] += 1
            _issue(counts, issues, url, "budget_run_cap", outcome.get("extraction_detail"), country)
        elif not outcome.get("complete", True) or status in ("not_connected", "budget_refused", "failed", "incomplete"):
            counts["unextracted"] += 1
            _issue(counts, issues, url, "extraction_not_run", f"{status}: {outcome.get('extraction_detail') or ''}".strip(": "), country)
        elif outcome["claims"] == 0 and outcome["rejected"] > 0:
            _issue(counts, issues, url, "extraction_rejected",
                   f"all {outcome['rejected']} extracted claim(s) were rejected; the document needs review", country)
        else:
            if status == "partial" or outcome["rejected"]:
                _issue(counts, issues, url, "some_claims_rejected",
                       f"{outcome['rejected']} proposed claim(s) rejected into the review queue; {outcome['claims']} kept", country)
            for c in ([country] if country else source_countries):
                if c and c not in cov["extracted"]:
                    cov["extracted"].append(c)
        for sid_, is_new in outcome["signals"]:
            hit = touched.setdefault(sid_, {"is_new": False, "sources": set(), "date_unknown": False})
            hit["is_new"] = hit["is_new"] or is_new
            hit["sources"].add(src["name"])
            hit["date_unknown"] = hit["date_unknown"] or bool(outcome["date_unknown"])
        ctx.tick(documents_seen=ctx.progress["documents_seen"] + 1,
                 documents_new=ctx.progress["documents_new"] + (1 if outcome["document_new"] else 0))
    counts["documents"] += docs
    counts["new_documents"] += new_docs
    material = [i for i in issues if i["reason"] in MATERIAL_ISSUES]
    if not material:
        status_ = "succeeded"
    elif any_query_ok:
        status_ = "partial"     # the source answered; some targets were not fully processed (each listed with its reason)
    else:
        status_ = "failed"      # no query to this source succeeded
    by_reason: dict[str, int] = {}
    for i in issues:
        by_reason[i["reason"]] = by_reason.get(i["reason"], 0) + 1
    detail = "; ".join(f"{n} {r.replace('_', ' ')}" for r, n in sorted(by_reason.items())) or None
    first = next((i for i in issues if i["reason"] in MATERIAL_ISSUES and i["detail"]), None)
    if detail and first:
        detail = f"{detail} (first: {first['detail']})"
    db.run("ingestion_run_finish2", id=ing_run, status=status_,
           stats={"documents": docs, "new_documents": new_docs, "failures": failures, "issues": len(issues)}, error=detail)
    db.run("run_source_set", run=run_id, source=sid, status=status_, detail=detail, documents=docs, new_documents=new_docs,
           failures=failures, issues=issues[:MAX_LISTED_ISSUES])
    return status_


def process_document(db: Database, settings: Settings, info: ing.SourceInfo, src: dict[str, Any], url: str, ing_run: str,
                     search: dict[str, Any] | None, fetch: Any, transport: Any, ctx: _Ctx | None,
                     now: datetime | None, *, feed_published: datetime | None = None, run_id: str | None = None) -> dict[str, Any]:
    fr = fetch(url)
    page = ct.extract(fr.body, fr.content_type, fr.final_url)
    if not page.text:
        raise ct.ContentUnavailable("no readable text")
    # Publication date (fourth instruction of 27 Oct, item 2): the notice's own stated issue date, the page's or PDF's metadata,
    # the feed item's date: whichever is reliable (domain.publication). Unknown stays unknown; retrieval time is never used;
    # future or inconsistent dates are flagged and not used for any age.
    now_ = now or datetime.now(timezone.utc)
    pub = publication.resolve([(page.published_source or "page", page.published_at), ("document_text", publication.stated_in_text(page.text)),
                               ("feed", feed_published)], now_)
    published, published_source = pub.published_at, pub.source
    date_state = _date_status(published, search)
    if date_state == "out_of_range":
        return {"skip": "out_of_range"}
    if date_state == "unknown" and (search or {}).get("date_filter") == "strict":
        return {"skip": "date_unknown_excluded"}
    language = page.language or src["language"]
    if language and language != "en" and not src["local_language_permitted"]:
        return {"skip": "language_not_permitted", "language": language}
    doc = ing.IncomingDocument(info, url, fr.final_url, page.text, title=page.title, publisher=src["name"],
                               published_at=published, published_source=published_source, content_type=fr.content_type,
                               run_id=ing_run, language=language, publication_flag=pub.flag, publication_note=pub.note)
    existing = db.one("document_by_content", canonical=ing.ev.canonicalize_url(fr.final_url), hash=ing.ev.content_hash(page.text))
    if existing is not None and published_source == "feed" and published is not None \
            and db.scalar("document_set_feed_date", id=str(existing["id"]), published=published):
        for r in db.all("signals_for_document", doc=str(existing["id"])):
            ing.evaluate_signal(db, str(r["signal_id"]), now_)
    read_by_old_version = (existing is not None and existing["read_progress"] is None
                           and len(page.text.encode()) > ai.SECTION_BYTES)    # an earlier version cut long documents short
    if existing is not None and existing["extraction_status"] in ("extracted", "partial", "no_claims", "manual") \
            and not read_by_old_version:
        # Completely read before: nothing is re-extracted or re-charged. The run reports the document's STORED state
        # (accepted claims, open rejections), so a document whose claims were all rejected stays incomplete.
        doc_id = str(existing["id"])
        st = db.one("document_claim_state", id=doc_id) or {}
        sigs = [(r["signal_id"], False) for r in db.all("signals_for_document", doc=doc_id)]
        return {"document_new": False, "claims": int(st.get("claims") or 0), "rejected": int(st.get("rejected") or 0),
                "extraction_status": existing["extraction_status"], "signals": sigs, "date_unknown": date_state == "unknown",
                "already_processed": True, "complete": True}

    if existing is None:
        stored = ing.ingest(db, doc, [], now=now_, extraction_status="pending")
        doc_id, family_key, document_new = stored.document_id, stored.family_key, stored.document_new
        prior_progress = None
    else:   # stored earlier but not completely read: resume where reading stopped
        doc_id, family_key, document_new = str(existing["id"]), existing["family_key"] or str(existing["id"]), False
        prior_progress = existing["read_progress"]
        stuck = sec_mod.Progress.from_json(prior_progress)
        if stuck is not None and any(n >= reading.MAX_SECTION_FAILURES for n in (stuck.failures or {}).values()):
            # A section kept failing: not retried (and not charged) on every run. A person resumes it from Evidence Review.
            sigs = [(r["signal_id"], False) for r in db.all("signals_for_document", doc=doc_id)]
            return {"document_new": False, "claims": 0, "rejected": 0, "extraction_status": "failed", "signals": sigs,
                    "extraction_detail": f"{stuck.label()}; a section failed repeatedly — use 'Continue reading' in Evidence Review",
                    "date_unknown": date_state == "unknown", "complete": False, "sections_read": len(set(stuck.done)),
                    "sections_total": stuck.total, "gave_up": True}
    job_id = getattr(ctx.job_ctx, "job_id", None) if ctx else None
    ro = reading.read_document(db, settings, doc_id, family_key, page.text, job_id=job_id, run_id=run_id, now=now_,
                               transport=transport, page_of=page.page_of if page.page_starts else None,
                               stored_progress=prior_progress, on_section=ctx.tick if ctx else None,
                               page_starts=page.page_starts or None)
    sigs = list(ro.signals)
    if existing is not None:
        seen = {s for s, _ in sigs}
        sigs += [(r["signal_id"], False) for r in db.all("signals_for_document", doc=doc_id) if r["signal_id"] not in seen]
    return {"document_new": document_new, "claims": ro.claims, "rejected": ro.rejected, "extraction_status": ro.status,
            "extraction_detail": ro.detail, "budget_scope": ro.budget_scope, "signals": sigs, "date_unknown": date_state == "unknown",
            "complete": ro.progress.complete, "sections_read": len(set(ro.progress.done)), "sections_total": ro.progress.total,
            "gave_up": ro.gave_up}


# ===================================================================== matching


def _finish(db: Database, run_id: str, search: dict[str, Any] | None, wanted: set[str] | None,
            touched: dict[str, dict[str, Any]], counts: dict[str, Any], *, cancelled: bool) -> dict[str, Any]:
    matched = 0
    for sid, t in touched.items():
        m = match_signal(db, sid, search, wanted)
        if m is None:
            continue
        m["sources"] = sorted(t["sources"])
        if t.get("date_unknown") and search and (search.get("date_from") or search.get("date_to")):
            m["date_note"] = "publication date unknown: included, but not verified to fall within the selected period"
        opp = db.scalar("opportunity_by_signal", signal=sid)
        db.run("result_add", run=run_id, signal=sid, opp=str(opp) if opp else None, is_new=t["is_new"], match=m)
        matched += 1
    run = db.one("run_get", id=run_id) or {}
    plan = run.get("plan") or {}
    gaps = plan.get("coverage_gaps") or []
    n_sources = len(plan.get("sources") or [])
    material = sum(n for r, n in counts["issue_counts"].items() if r in MATERIAL_ISSUES)   # includes source_disabled
    truncated = bool(counts.get("not_searched_countries"))
    scope = f"search:{search['id']}" if search is not None else (f"source:{plan['sources'][0]['id']}" if len(plan.get("sources") or []) == 1 else None)
    if scope:
        q = db.one("queue_remaining", scope=scope) or {}
        counts["queue"] = {"pending": int(q.get("pending") or 0), "gave_up": int(q.get("gave_up") or 0), "resumed": counts.get("queue_resumed", 0)}
        # Relevant links still waiting, or given up after repeated failures: never a complete search.
        truncated = truncated or counts["queue"]["pending"] > 0 or counts["queue"]["gave_up"] > 0
    flags = []
    if gaps:
        flags.append("partial_coverage")
    if counts["failed_sources"]:
        flags.append("source_failure")
    if material or truncated:
        flags.append("incomplete")
    if cancelled:
        status, outcome = "cancelled", "cancelled"
    elif n_sources == 0:
        status, outcome = "completed", "no_sources"      # nothing was searched: never "no relevant results"
    elif counts["failed_sources"] == n_sources:
        status, outcome = "failed", "source_failure"
    elif material or truncated or counts["failed_sources"] or counts["partial_sources"]:
        status, outcome = "partial", "incomplete"       # some potentially relevant work was not done; listed on the run
    elif gaps:
        status, outcome = "completed", "partial_coverage"
    else:
        status, outcome = "completed", ("results" if matched else "no_relevant_results")
    cov = counts["coverage"]
    for k in ("attempted", "retrieved", "extracted"):
        cov[k] = sorted(cov[k])
    cov["not_attempted"] = sorted(set(cov["planned"]) - set(cov["attempted"]))
    actual = db.scalar("run_actual_cost", id=run_id)
    counts_out = dict(counts) | {"matched": matched, "flags": flags}
    db.run("run_finish", id=run_id, status=status, outcome=outcome, counts=counts_out, actual=actual)
    return {"run_id": run_id, "status": status, "outcome": outcome, "counts": counts_out}


def match_signal(db: Database, signal_id: str, search: dict[str, Any] | None, wanted: set[str] | None) -> dict[str, Any] | None:
    """Why a signal matches a search, or None. Geography follows the actual
    opportunity scope (delivery, contract territory, lane): an issuer based
    in a selected country with delivery elsewhere is reported as an
    issuer-only match, never as a scope match."""
    sig = db.one("signal_match_view", id=signal_id)
    if sig is None or sig["merged_into_id"] is not None:
        return None
    geo = db.all("signal_geo", signal=signal_id)
    supported = [g for g in geo if g["support"] == "supported"]
    scope = [g for g in supported if g["role"] in SCOPE_ROLES]
    issuer = [g for g in supported if g["role"] == "issuer"]
    if wanted is None:
        basis, hits = "worldwide", scope + issuer
    else:
        hits = [g for g in scope if g["country_code"] in wanted]
        basis = "scope"
        if not hits:
            hits = [g for g in issuer if g["country_code"] in wanted]
            basis = "issuer_only"
        if not hits:
            return None
    if search:
        modules = set(search.get("modules") or [])
        if modules and sig["module"] not in modules and not (set(sig["related_modules"] or []) & modules):
            return None
        hay = " ".join(filter(None, [sig["title"], sig["subject_name"], sig["subject_label"], sig["evidence_text"]])).lower()
        for key in ("airline", "organisation"):
            want = (search.get(key) or "").lower()
            if want and want not in hay:
                return None
        kws = [k for k in re.split(r"[,;]\s*|\s+", (search.get("keywords") or "").lower()) if k]
        if kws and not any(k in hay for k in kws):
            return None
        ds = _date_status(sig["first_published_at"], search)
        if ds == "out_of_range" or (ds == "unknown" and search.get("date_filter") == "strict"):
            return None
    tender = sig["tender_state"] or {}
    return {
        "geography_basis": basis,
        "geography": [{"country": g["country_code"], "name": COUNTRIES.get(g["country_code"], (g["country_code"],))[0],
                       "role": g["role"]} for g in hits],
        "all_countries": [{"country": g["country_code"], "role": g["role"], "support": g["support"]} for g in geo],
        "capability_area": sig["module"], "related_areas": list(sig["related_modules"] or []),
        "classification": sig["classification"], "published_at": sig["first_published_at"],
        "deadline_utc": tender.get("deadline_utc"), "deadline_source_tz": tender.get("deadline_source_tz"),
        "deadline": tender.get("deadline"), "tender_status": tender.get("status"), "qualification_status": sig["qualification_status"],
        "confidence": {"independent_families": sig["families"], "best_authority": sig["best_authority"],
                       "claims_supported": sig["claims_supported"]},
        "gaps": sig["gaps"] or [],
        "recommended_next_action": next_action(sig, tender),
    }


def next_action(sig: dict[str, Any], tender: dict[str, Any]) -> str:
    cls = sig["classification"]
    qs = sig.get("qualification_status")
    gaps = " ".join(sig.get("gaps") or [])
    urgent = ""
    # Urgency uses the EARLIEST reading of the stated deadline (a date-only deadline may fall at the start of that day).
    dl = (tender.get("deadline") or {}).get("earliest_utc") or tender.get("deadline_utc")
    if dl:
        try:
            if datetime.fromisoformat(dl) - datetime.now(timezone.utc) < timedelta(days=7):
                urgent = "Urgent (deadline may fall within 7 days): "
        except ValueError:
            pass
    if cls == "risk_alert":
        return "Review the contradicting evidence before any further work"
    if cls == "excluded":
        return "No freight action: not a freight mandate (kept as evidence with the reason)"
    if cls == "freight_candidate":
        return "Review the freight scope: a candidate, not a qualified freight opportunity"
    if cls == "unverified_lead":
        return "Confirm the tender on the issuer's official channel or procurement portal"
    if cls == "market_signal":
        return "Check representation arrangements and commercial access for this route"
    if cls != "qualified_opportunity":
        return "Review the evidence and decide whether it is relevant"
    if tender.get("status") in ("cancelled", "awarded", "closed", "expired"):
        return f"No action: the tender is {tender['status']}"
    if tender.get("status") in ("unverified", "historical", "announced"):
        return f"Confirm with the issuer whether the notice is still current ({tender.get('basis') or tender['status']}) before any work"
    if "awaits reviewer confirmation" in gaps:
        return urgent + "Review and confirm the AI-proposed evidence"
    if qs == "blocked":
        return "Resolve the blocking qualification check"
    if qs == "ready_for_review":
        return urgent + "Approve for pursuit or defer"
    if qs == "approved_for_pursuit":
        return urgent + "Progress the opportunity"
    return urgent + "Assign operating company, service and delivery station, then complete qualification"


def cancel_run(db: Database, run_id: str) -> bool:
    row = db.one("run_get", id=run_id)
    if row is None or row["status"] not in ("queued", "running"):
        return False
    db.run("run_cancel", id=run_id)
    if row["job_id"]:
        db.run("job_cancel", job=str(row["job_id"]))
    return True


def retry_run(db: Database, settings: Settings, run_id: str) -> dict[str, Any]:
    row = db.one("run_get", id=run_id)
    if row is None:
        raise DiscoveryRejected(404, "run not found")
    if row["status"] not in ("failed", "partial", "cancelled"):
        raise DiscoveryRejected(409, f"only failed, partial or cancelled runs can be retried (run is {row['status']})")
    existing = db.one("run_retry_of", job=str(row["job_id"])) if row["job_id"] else None
    if existing is not None:   # Retry pressed twice (or two tabs): one retry run per failed run
        return {"run_id": str(existing["id"]), "job_id": str(existing["job_id"]), "plan": existing["plan"], "existing": True}
    return start_run(db, settings, search_id=str(row["search_id"]) if row["search_id"] else None,
                     source_id=str(row["source_id"]) if row["source_id"] else None, trigger="retry",
                     retry_of=str(row["job_id"]) if row["job_id"] else None,
                     budget_root=str(row["budget_root_id"] or row["id"]))


def refresh_matches(db: Database, signal_id: str, now: datetime | None = None, *, reason: str) -> int:
    """Re-check the stored country matches of past runs for one signal after its evidence changed (a re-check under new
    validation rules, a correction, a rejection). A match that no longer holds is marked withdrawn — kept with the reason
    and the previous geography, never silently deleted — so a run page never shows a country match the evidence no longer
    supports. Returns the number of result rows changed."""
    now = now or datetime.now(timezone.utc)
    changed = 0
    for r in db.all("discovery_results_of_signal", signal=signal_id):
        search = db.one("search_get", id=r["search_id"]) if r["search_id"] else None
        wanted = country_set(db, search) if search else None
        new = match_signal(db, signal_id, search, wanted)
        old = r["match"] or {}
        if new is None:
            if old.get("withdrawn"):
                continue
            db.run("result_set_match", run=r["run_id"], signal=signal_id,
                   match=old | {"withdrawn": True, "withdrawn_at": now.isoformat(), "withdrawn_reason": reason,
                                "previous_geography": old.get("geography")})
            changed += 1
        else:
            current = {k: v for k, v in old.items() if k not in ("withdrawn", "withdrawn_at", "withdrawn_reason", "previous_geography")}

            def _iso(x: Any) -> Any:
                return x.isoformat() if isinstance(x, datetime) else str(x)
            if current == json.loads(json.dumps(new, default=_iso)):
                continue
            db.run("result_set_match", run=r["run_id"], signal=signal_id, match=new)
            changed += 1
    return changed
