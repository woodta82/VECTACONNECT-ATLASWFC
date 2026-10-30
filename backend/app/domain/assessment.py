"""Assessment kept in separate parts (30 Oct 2026, item 8): fit with the research brief, strength of source evidence, research
completeness, relationship position, opportunity status and readiness. Each part is scored and explained on its own; the parts are
never added into one number that pretends to be a probability of winning. A fuller profile or an e-mail address never raises fit.

Also the cargo-industry scope (item 7): freight scope labelled as freighter cargo, belly cargo, mixed cargo operations, cargo
services (a non-airline cargo company), passenger-only or unresolved; passenger ticket sales, tourism and passenger-only mandates
are outside the scope and said so.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STAGES = ("identify", "identity", "company", "people", "relationships", "relevance")
STAGE_LABELS = {"identify": "Identify the organisations involved", "identity": "Resolve official identity (website, contact page)",
                "company": "Research the company (services, offices, airports, addresses, representation)", "people": "Research relevant people",
                "relationships": "Connect relationships and introduction routes", "relevance": "Assess commercial relevance"}
STAGE_STATUS_LABELS = {"not_run": "Not run", "running": "Running", "done": "Complete", "done_with_failures": "Complete with unresolved failures — retry",
                       "incomplete": "Incomplete — pending work, continue", "failed": "Failed — retry", "not_applicable": "Not applicable"}


def stage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every stage in order, labelled; stages not yet run are listed as not run."""
    by = {r["stage"]: r for r in rows}
    out = []
    for st in STAGES:
        r = by.get(st) or {"stage": st, "status": "not_run", "detail": None, "counts": {}, "attempts": 0, "started_at": None, "finished_at": None}
        c = r.get("counts") or {}
        progress = None
        if isinstance(c, dict) and c.get("total") is not None and st in ("identity", "company", "people", "relevance"):
            progress = f"{int(c.get('completed') or 0)} completed, {int(c.get('failed') or 0)} failed, {int(c.get('pending') or 0)} pending of {int(c['total'])}"
        out.append({**r, "label": STAGE_LABELS[st], "status_label": STAGE_STATUS_LABELS.get(r["status"], r["status"]), "progress": progress})
    return out


FREIGHT_SCOPE_LABELS = {"freighter": "Freighter cargo", "belly": "Belly cargo (passenger aircraft)", "mixed": "Mixed cargo operations (freighter and belly)",
                        "cargo_services": "Cargo services (non-airline)", "passenger_only": "Passenger-only (outside the freight scope)",
                        "unresolved": "Freight scope unresolved"}
FIELD_LABELS = {"website": "Official website", "contact_page": "Contact page", "emails": "Published e-mail addresses", "services": "Services",
                "locations": "Offices and locations", "airports": "Airports served", "representation": "Represented airlines / partners", "people": "Relevant people",
                "parent": "Parent or group"}
COMPLETENESS_FIELDS = ("website", "contact_page", "emails", "services", "locations", "airports", "representation", "people")


def freight_scope(*, kind: str | None, carrier_type: str | None, relationships: list[dict[str, Any]], services_text: str | None,
                  description: str | None) -> tuple[str, str]:
    """(scope, basis) from what the sources state. Nothing is inferred from the name."""
    text = " ".join(x for x in (services_text, description) if x).lower()
    rels = [r for r in relationships if r.get("status") not in ("lapsed", "not_established")]
    cargo_rel = [r for r in rels if r.get("relationship") in ("cargo_representation", "handling", "trucking")]
    pax_rel = [r for r in rels if r.get("relationship") == "passenger_representation"]
    if kind == "airline":
        if carrier_type == "cargo_only":
            return "freighter", "stated as a cargo-only airline"
        if carrier_type == "passenger_belly":
            return "belly", "stated as a passenger airline carrying belly cargo"
        if carrier_type == "combination":
            return "mixed", "stated as operating passenger and freighter aircraft"
        if "freighter" in text and ("passenger" in text or "belly" in text):
            return "mixed", "the sources mention freighter and passenger operations"
        if "freighter" in text:
            return "freighter", "the sources mention freighter operations"
        if "belly" in text or "passenger" in text:
            return "belly", "the sources mention passenger flights carrying cargo"
        return "unresolved", "no source states how the airline carries cargo"
    if kind in ("gssa", "forwarder", "handler", "trucking_provider", "integrator", "charter_broker", "technology_provider", "airport_operator"):
        if pax_rel and not cargo_rel and kind == "gssa":
            cargo_words = any(w in text for w in ("cargo", "freight", "airfreight"))
            if not cargo_words:
                return "passenger_only", "only passenger ticket-sales representation is stated; no cargo activity stated by any source"
        if kind == "gssa" and not cargo_rel and not any(w in text for w in ("cargo", "freight", "gssa", "airfreight")):
            return "unresolved", "a sales agent whose cargo activity no source states yet"
        return "cargo_services", {"gssa": "a cargo sales agent", "forwarder": "a freight forwarder", "handler": "a cargo or ground handler",
                                  "trucking_provider": "a road feeder or trucking provider", "integrator": "an integrator", "charter_broker": "a charter broker",
                                  "technology_provider": "a cargo technology provider", "airport_operator": "an airport operator"}[kind] + " (stated)"
    if pax_rel and not cargo_rel:
        return "passenger_only", "only passenger ticket sales is stated"
    return "unresolved", "no source states the organisation's part in air cargo"


def in_cargo_scope(scope: str) -> bool:
    return scope != "passenger_only"


def completeness(research_status: dict[str, Any] | None, *, has: dict[str, bool]) -> dict[str, Any]:
    """Research completeness per field: found / not searched / not found after research / inaccessible / incomplete — a separate measure,
    never part of fit."""
    rs = research_status or {}
    fields = []
    found = searched = 0
    for f in COMPLETENESS_FIELDS:
        st = (rs.get(f) or {}).get("status")
        if has.get(f) and st != "recheck":          # a value on record counts as found, unless a page read contradicts it (re-check pending)
            st = "found"
        st = st or "not_searched"
        fields.append({"field": f, "label": FIELD_LABELS[f], "status": st, "detail": (rs.get(f) or {}).get("detail"), "at": (rs.get(f) or {}).get("at")})
        found += st in ("found", "recheck")       # the value is on record; the re-check is shown beside it
        searched += st != "not_searched"
    pct = round(100 * found / len(COMPLETENESS_FIELDS))
    return {"score": pct, "fields": fields, "found": found, "searched": searched, "total": len(COMPLETENESS_FIELDS),
            "explanation": f"{found} of {len(COMPLETENESS_FIELDS)} profile fields found; {len(COMPLETENESS_FIELDS) - searched} not searched yet; "
                           f"{searched - found} searched without result or incomplete"}


def evidence_strength(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """How well the record is sourced: independent documents, own-site pages, supplied-only rows, age."""
    docs = {e.get("research_document_id") or e.get("url") for e in evidence if e.get("source_kind") in ("research_document", "public_page")}
    own = sum(1 for e in evidence if e.get("source_kind") == "public_page")
    supplied = sum(1 for e in evidence if e.get("source_kind") == "supplied")
    notes = sum(1 for e in evidence if e.get("source_kind") == "note")
    n = len(docs)
    if n == 0 and supplied:
        band, expl = "supplied_only", "supplied data only: nothing sourced from a public page yet"
    elif n == 0:
        band, expl = "none", "no source document recorded"
    elif n == 1:
        band, expl = "single_source", "one public source"
    elif n < 4:
        band, expl = "several", f"{n} independent public documents"
    else:
        band, expl = "well_sourced", f"{n} independent public documents"
    if own:
        expl += f"; {own} fact(s) from the organisation's own site"
    if notes:
        expl += f"; {notes} note(s) by a person"
    return {"band": band, "documents": n, "own_site_facts": own, "supplied_facts": supplied, "explanation": expl}


def fit(*, kind: str | None, wanted_kinds: list[str], country: str | None, brief_countries: list[str], airports: list[str], brief_airports: list[str],
        freight_scope_value: str, brief_terms_hit: bool, module_match: bool | None = None) -> dict[str, Any]:
    """Fit with the research brief: kind, geography, airport, freight scope and the brief's words. Nothing about completeness."""
    reasons = []
    pts = 0
    if freight_scope_value == "passenger_only":
        return {"score": 0, "band": "out_of_scope", "reasons": ["passenger-only: outside the air cargo scope of the brief"]}
    if kind and kind in wanted_kinds:
        pts += 40
        reasons.append("a kind of organisation the brief asks for")
    elif kind:
        pts += 10
        reasons.append("not a kind the brief asks for")
    else:
        reasons.append("kind not established by any source")
    if brief_airports and set(airports) & set(brief_airports):
        pts += 30
        reasons.append("at an airport in the brief")
    elif brief_countries and country in brief_countries:
        pts += 25 if not brief_airports else 15
        reasons.append("in a country of the brief" + ("; not yet tied to the airport asked for" if brief_airports else ""))
    elif not brief_countries and not brief_airports:
        pts += 20
        reasons.append("no geography in the brief")
    elif country:
        reasons.append("outside the geography of the brief")
    else:
        pts += 5
        reasons.append("country not established")
    if freight_scope_value in ("freighter", "belly", "mixed", "cargo_services"):
        pts += 15
        reasons.append(FREIGHT_SCOPE_LABELS[freight_scope_value].lower())
    else:
        reasons.append("freight scope unresolved")
    if brief_terms_hit:
        pts += 15
        reasons.append("the sources match the brief's words")
    if module_match:
        reasons.append("matches the capability area")
    band = "strong" if pts >= 75 else "good" if pts >= 55 else "partial" if pts >= 30 else "weak"
    return {"score": min(100, pts), "band": band, "reasons": reasons}


def relationship_position(*, coverage: str | None, people: int, relationships: int, routes: int) -> dict[str, Any]:
    labels = {"existing_relationship": "an existing WFC relationship", "introduction_available": "an introduction route available",
              "people_confirmed": "people confirmed, no relationship yet", "candidates_only": "research candidates only", "none": "nobody identified yet"}
    cov = coverage or ("candidates_only" if people else "none")
    return {"coverage": cov, "label": labels.get(cov, cov), "people": people, "relationships": relationships, "routes": routes,
            "explanation": f"{labels.get(cov, cov)}: {people} person(s) recorded, {relationships} active relationship(s), {routes} route(s)"}


def opportunity_status(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {"status": "none", "label": "No opportunity recorded", "readiness": "n/a",
                "explanation": "a relevant company is not an opportunity until a person records one with the interpretation"}
    rt = record.get("record_type")
    prog = record.get("progress") or "untracked"
    ts = record.get("tender_status")
    qs = record.get("qualification_status")
    ready = "ready" if qs in ("ready_for_review", "approved_for_pursuit") else "blocked" if qs == "blocked" else "incomplete"
    label = {"tender": "Tender", "commercial": "Commercial opportunity", "market_signal": "Market signal"}.get(rt, rt or "record")
    expl = f"{label}; progress {prog}" + (f"; tender status {ts}" if ts else "") + (f"; qualification {qs}" if qs else "")
    return {"status": rt, "label": label, "progress": prog, "tender_status": ts, "qualification_status": qs, "readiness": ready, "explanation": expl}


def rank_explanation(parts: dict[str, Any]) -> str:
    """Plain language, no probability."""
    f = parts.get("fit", {})
    e = parts.get("evidence", {})
    c = parts.get("completeness", {})
    r = parts.get("relationship", {})
    return (f"Fit {f.get('band', 'n/a')} ({', '.join(f.get('reasons', [])[:3])}); evidence {e.get('band', 'n/a').replace('_', ' ')}; "
            f"research {c.get('found', 0)}/{c.get('total', 0)} fields found; relationship: {r.get('label', 'n/a')}. "
            "Ranking follows fit first, then evidence; completeness and relationship position are shown beside it and never stand in for fit.")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Overall research state, the same on the research file, the company page and the Dashboard (4.8.0).
OVERALL_LABELS = {"not_run": "Research not run", "incomplete": "Research incomplete — pending work", "failed": "Research failed — retry",
                  "complete_with_failures": "Research complete with unresolved failures", "complete": "Research complete"}


def overall(st: list[dict], t: dict[str, int]) -> dict[str, str]:
    """The overall state of an entity's staged research, from its stages and its work-queue totals:
    not run · incomplete (pending work, or stages not run) · failed (nothing completed) · complete with unresolved failures · complete."""
    statuses = [s["status"] for s in st if s["status"] != "not_applicable"]
    not_run = [s for s in st if s["status"] == "not_run"]
    failed_items, pending = t.get("failed", 0), t.get("pending", 0)
    stage_failed = any(x == "failed" for x in statuses)
    if not statuses or all(x == "not_run" for x in statuses):
        state, label = "not_run", OVERALL_LABELS["not_run"]
    elif pending or any(x in ("incomplete", "running") for x in statuses):
        state, label = "incomplete", OVERALL_LABELS["incomplete"]
    elif failed_items or stage_failed or "done_with_failures" in statuses:
        nothing_done = not t.get("completed") and not any(x in ("done", "done_with_failures") for x in statuses)
        state = "failed" if nothing_done else "complete_with_failures"
        label = OVERALL_LABELS[state] + (f" ({len(not_run)} stage(s) could not run until the failures are retried)" if not_run else "")
    elif not_run:
        state, label = "incomplete", f"Research incomplete — {len(not_run)} stage(s) not run ({', '.join(s['stage'] for s in not_run)})"
    else:
        state, label = "complete", OVERALL_LABELS["complete"]
    return {"state": state, "state_label": label, "tally": f"{t.get('completed', 0)} completed, {failed_items} failed, {pending} pending"}
