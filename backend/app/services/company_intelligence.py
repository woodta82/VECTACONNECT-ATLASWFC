"""Company intelligence (29 Oct 2026: the four research purposes; company and people intelligence built directly; supplied data).

- Company discovery runs through the same pipeline as contact discovery (`relationship_research`: organisation pages, authorised web
  search results, robots.txt, per-run limits) with the purpose 'companies': every organisation named in a page that was read is
  recorded with the passage that names it, the kind the sentence states, published e-mail addresses from the same sentence or the
  organisation's own site, represented airlines when the sentence states representation (cargo kept apart from passenger ticket
  sales), and the people the pages bind to it. Nothing comes from the model's memory; a name alone creates no record (a legal or
  trade suffix, or a known name, is required) and nothing is merged on a name alone.
- A supplied dataset (a station's GSA list, e.g. the BRU benchmark) is preserved row by row and every organisation, address and
  represented airline from it is marked SUPPLIED — awaiting verification — until research sources it or a person verifies it. The
  spreadsheet is a benchmark of the output expected everywhere, not a database and not a Belgium-only scope.
- A researched company is not an opportunity. A person records a potential opportunity from a company with the interpretation that
  led to it, and that record goes into the ordinary pipeline as a commercial opportunity.
"""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any
from urllib.parse import urlsplit

from ..config import Settings
from ..domain import company_intel as ci
from ..domain import overview as ov
from ..reference.airline_codes import AIRLINE_CODES, resolve
from ..reference.airports import airport
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit
from . import relationship_research as rr

MAX_ORGS_PER_RUN = 60
MAX_SUPPLIED_ROWS = 2000


class CompanyRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _host(url: str | None) -> str | None:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else (h or None)


def _org_find(db: Database, name: str) -> str | None:
    oid = db.scalar("org_find_for_person", name=name, norm=_norm(name))
    return str(oid) if oid else None


def _name_tokens(name: str) -> list[str]:
    stop = {"the", "and", "cargo", "air", "airlines", "airways", "aviation", "logistics", "freight", "services", "ltd", "limited", "nv", "sa",
            "bv", "gmbh", "llc", "inc", "group", "international", "handling", "express", "trucking", "transport"}
    return [t for t in re.findall(r"[a-z0-9]{4,}", name.lower()) if t not in stop]


def _is_private_host(host: str | None) -> bool:
    return bool(host) and (host in ("localhost",) or bool(re.fullmatch(r"[0-9.]+", host)) or host.endswith((".local", ".internal")))


def _site_of(url: str | None) -> str | None:
    """The site a page belongs to: its origin. On a private host (the local fixture server, which serves many invented sites from
    one address) the first path segment stands for the site."""
    if not url:
        return None
    p = urlsplit(url)
    if _is_private_host(p.hostname):
        first = p.path.strip("/").split("/")[0] if p.path.strip("/") else ""
        return f"{p.scheme}://{p.netloc}/{first}/" if first else f"{p.scheme}://{p.netloc}/"
    return f"{p.scheme}://{p.netloc}/"


def _site_token(url: str | None) -> str | None:
    p = urlsplit(url or "")
    if _is_private_host(p.hostname):
        first = p.path.strip("/").split("/")[0] if p.path.strip("/") else ""
        return first.replace("-", "").lower() or None
    h = _host(url)
    return h.split(".")[0].replace("-", "") if h else None


def _site_names_org(url: str | None, name: str) -> bool:
    """The page's site carries the organisation's name (thousandhills.example for 'Thousand Hills Cargo Services Ltd')."""
    hp = _site_token(url)
    if not hp:
        return False
    toks = _name_tokens(name)
    joined = "".join(toks)
    return bool(toks) and (hp == joined or (len(toks[0]) >= 5 and hp.startswith(toks[0])) or (len(joined) >= 8 and joined in hp)
                           or (len(toks) >= 2 and hp == "".join(toks[:2])))


# ===================================================================== organisations from the pages a discovery read
def record_organisations(db: Database, run: rr._Run, disc: dict[str, Any]) -> list[dict[str, Any]]:
    """Organisations named in the pages this discovery read, recorded with evidence. Returns the organisations recorded (id, name, new)."""
    countries = list(disc.get("countries") or [])
    default_country = countries[0] if len(countries) == 1 else None
    brief_airport = disc.get("airport_iata")
    known = [o["name"] for o in run.orgs if o.get("name")]
    airline_names = list(AIRLINE_CODES.values()) + [r["canonical_name"] for r in db.all("org_airline_names")]
    recorded: dict[str, dict[str, Any]] = {}
    for d in db.all("rdoc_bodies", disc=str(disc["id"])):
        text = d.get("body_text") or ""
        page_url = d.get("url")
        page_host = _host(page_url)
        mentions = ci.organisations_in_text(text, known=known + [r["name"] for r in recorded.values()], airline_names=airline_names)
        mentions.sort(key=lambda m: m.subject)          # counterparties first, so a representation can point at their record
        own_site_org: str | None = None
        own_name = ""
        if d.get("organisation_id"):
            site_org = db.one("org_get_for_research", id=str(d["organisation_id"]))
            if site_org and site_org.get("website") and _site_of(page_url) == _site_of(site_org["website"]):
                own_site_org, own_name = str(site_org["id"]), site_org["name"]      # a page of the organisation's own site (e.g. its contact page)
        for m in mentions:
            if len(recorded) >= MAX_ORGS_PER_RUN:
                run.limits_hit.append(f"organisation limit for one run reached ({MAX_ORGS_PER_RUN})")
                break
            if not m.subject and m.kind is None:
                continue        # named in passing (a parent group, a partner): the sentence says nothing about it
            if m.name.lower() in {a.lower() for a in airline_names} and not m.subject and not any(m.name in x.represented for x in mentions) \
                    and not _site_names_org(page_url, m.name):
                continue        # a well-known airline merely named in passing is not a company result of this brief
            own_site = _site_names_org(page_url, m.name)
            country = default_country if m.subject else None              # a counterparty's country is never assumed from the brief
            with db.transaction() as tx:
                oid = _org_find(tx, m.name)
                created = oid is None
                if created:
                    oid = str(tx.scalar("org_insert_profile", name=m.name, kind=m.kind or "other", country=country,
                                        website=(_site_of(page_url) if own_site and page_url else None),
                                        origin="discovery", airport=brief_airport if default_country else None, carrier_type=None))
                ev = tx.scalar("org_evidence_add", org=oid, supports="identity", source_kind="research_document", rdoc=str(d["id"]), url=page_url,
                               quote=m.quote, note=f"named on a page read by the discovery ({rr._method_label(d)}); kind: {m.kind_basis}",
                               import_id=None, session_ref=run.meta.session_ref)
                if ev is None:
                    ev = tx.scalar("org_evidence_find", org=oid, supports="identity", source_kind="research_document", rdoc=str(d["id"]), url=page_url,
                                   quote=m.quote, note=f"named on a page read by the discovery ({rr._method_label(d)}); kind: {m.kind_basis}")
                if m.kind:
                    tx.scalar("org_evidence_add", org=oid, supports="kind", source_kind="research_document", rdoc=str(d["id"]), url=page_url,
                              quote=m.quote, note=m.kind_basis, import_id=None, session_ref=run.meta.session_ref)
                if own_site and page_url:
                    site = _site_of(page_url)
                    tx.scalar("org_evidence_add", org=oid, supports="website", source_kind="public_page", rdoc=str(d["id"]), url=page_url,
                              quote=None, note=f"the page is on a site carrying the organisation's name ({page_host})", import_id=None,
                              session_ref=run.meta.session_ref)
                    tx.run("org_profile_fill", id=oid, website=site, country=country, kind=m.kind, description=m.quote[:400],
                           services=_services_from(text), locations=_locations_from(text, m.quote), parent=_parent_from(m.quote),
                           airport=brief_airport if country else _airport_from(m.quote), carrier_type=None, areas=[disc["capability_area"]] if disc.get("capability_area") else [],
                           researched=True)
                    own_site_org, own_name = oid, m.name
                else:
                    tx.run("org_profile_fill", id=oid, website=None, country=country, kind=m.kind, description=m.quote[:400], services=None,
                           locations=_locations_from(m.quote, m.quote), parent=_parent_from(m.quote), airport=_airport_from(m.quote) or (brief_airport if country else None),
                           carrier_type=None, areas=[disc["capability_area"]] if disc.get("capability_area") else [], researched=m.subject)
                for e in m.emails:
                    dom = e.split("@", 1)[1]
                    own_domain = page_host is not None and (dom == page_host or dom.endswith("." + page_host))
                    eev = tx.scalar("org_evidence_add", org=oid, supports="email", source_kind="research_document", rdoc=str(d["id"]), url=page_url, quote=m.quote,
                                    note="published address in the sentence naming the organisation" + ("; on the organisation's own site" if own_domain and own_site else ""),
                                    import_id=None, session_ref=run.meta.session_ref)
                    tx.one("org_contact_upsert", org=oid, kind="email", value=e, purpose=None, status="published", url=page_url,
                           note="published on a page read by the discovery", evidence=str(eev) if eev else None, session_ref=run.meta.session_ref)
                for rep in m.represented:
                    _record_representation(tx, oid, rep, m.representation_scope, quote=m.quote, rdoc=str(d["id"]), url=page_url,
                                           airport=brief_airport, countries=countries, session_ref=run.meta.session_ref, status="sourced")
                tx.run("disc_org_link", disc=str(disc["id"]), org=oid, new=created)
                if own_site:
                    tx.run("rdoc_set_org", id=str(d["id"]), org=oid)
            recorded.setdefault(oid, {"id": oid, "name": m.name, "new": created, "kind": m.kind})
        # e-mail addresses published on an organisation's own site, beyond the sentence that names it
        if own_site_org:
            with db.transaction() as tx:
                for e in ci.emails_in_text(text, page_host):
                    dom = e["email"].split("@", 1)[1]
                    if e["own_site"] == "yes" or _site_names_org(f"https://{dom}/", own_name):
                        eev = tx.scalar("org_evidence_add", org=own_site_org, supports="email", source_kind="public_page", rdoc=str(d["id"]), url=page_url,
                                        quote=e["quote"], note="published on the organisation's own site", import_id=None, session_ref=run.meta.session_ref)
                        tx.one("org_contact_upsert", org=own_site_org, kind="email", value=e["email"], purpose=_email_purpose(e["quote"]), status="published",
                               url=page_url, note="published on the organisation's own site", evidence=str(eev) if eev else None, session_ref=run.meta.session_ref)
    return list(recorded.values())


def _record_representation(tx: Database, agent_id: str, rep: str, scope: str | None, *, quote: str, rdoc: str | None, url: str | None,
                           airport: str | None, countries: list[str], session_ref: str | None, status: str, import_id: str | None = None,
                           basis: str | None = None) -> None:
    code, label, counterparty = None, None, None
    if re.fullmatch(r"[A-Z0-9]{2,3}", rep):
        code = rep
        cid = tx.scalar("org_by_code", code=code)
        counterparty = str(cid) if cid else None
        label = resolve(code)[0]
    else:
        label = rep
        counterparty = _org_find(tx, rep)
    relationship = {"cargo": "cargo_representation", "passenger": "passenger_representation"}.get(scope or "", "representation_unspecified")
    ev = None
    if status == "sourced":
        ev = tx.scalar("org_evidence_add", org=agent_id, supports="representation", source_kind="research_document", rdoc=rdoc, url=url, quote=quote,
                       note=f"{ci.RELATIONSHIP_LABELS[relationship]} stated in the passage", import_id=None, session_ref=session_ref)
    tx.one("org_rel_upsert", org=agent_id, counterparty=counterparty, code=code, label=label, relationship=relationship, territories=countries[:5],
           airport=airport, status=status, basis=basis or ("stated by the page read: " + quote[:200] if status == "sourced" else "supplied"),
           evidence=str(ev) if ev else None, session_ref=session_ref)


_SERVICE_RX = re.compile(r"(?:(?:we|our|the company)\s+(?:offer|provide|specialis|specializ|deliver)[^.]{10,200}\.)", re.I)
_LOC_RX = re.compile(r"\b(?:offices?|based|headquartered|located|stations?|branches?|presence)\s+(?:in|at)\s+([A-Z][A-Za-z' \-]+(?:,\s*[A-Z][A-Za-z' \-]+){0,4})")
_PARENT_RX = re.compile(r"\b(?:part of|a subsidiary of|a member of|owned by|a division of)\s+(?:the\s+)?([A-Z][A-Za-z0-9&' \-]{2,60}?(?:Group|Holding|Holdings|N\.?V\.?|S\.?A\.?|Ltd|Limited|GmbH|Inc|LLC|plc))\b")


def _services_from(text: str) -> str | None:
    m = _SERVICE_RX.search(text)
    return " ".join(m.group(0).split())[:300] if m else None


def _locations_from(text: str, quote: str) -> str | None:
    found: list[str] = []
    for src in (quote, text):
        for m in _LOC_RX.finditer(src):
            v = " ".join(m.group(1).split()).strip(" ,")
            if v and v not in found:
                found.append(v)
        if found:
            break
    return "; ".join(found)[:300] or None


def _parent_from(quote: str) -> str | None:
    m = _PARENT_RX.search(quote)
    return m.group(1).strip() if m else None


def _airport_from(quote: str) -> str | None:
    for tok in re.findall(r"\b[A-Z]{3}\b", quote):
        if airport(tok):
            return tok
    return None


def _email_purpose(quote: str) -> str | None:
    q = quote.lower()
    for key, label in (("reservation", "reservations"), ("booking", "bookings"), ("sales", "sales"), ("cargo", "cargo"), ("ops", "operations"),
                       ("operation", "operations"), ("claims", "claims"), ("info", "general")):
        if key in q:
            return label
    return None


def score_organisations(db: Database, disc: dict[str, Any]) -> None:
    wanted = ci.kinds_for([disc["capability_area"]] if disc.get("capability_area") else [], list(disc.get("organisation_kinds") or []))
    bt = ci.brief_terms(disc.get("brief_text")).lower().split()
    for o in db.all("disc_orgs", id=str(disc["id"])):
        hay = " ".join(x for x in (o.get("canonical_name"), o.get("services_text"), o.get("quote")) if x).lower()
        hit = bool(bt) and any(t in hay for t in bt)
        r = ci.company_relevance(kind=o.get("kind"), wanted_kinds=wanted, country=o.get("country"), brief_countries=list(disc.get("countries") or []),
                                 airport_iata=o.get("airport_iata"), brief_airport=disc.get("airport_iata"),
                                 represented=len(o.get("relationships") or []), emails=len(o.get("emails") or []), website=bool(o.get("website")),
                                 evidence_count=int(o.get("evidence") or 0), brief_terms_hit=hit)
        db.run("disc_org_relevance", disc=str(disc["id"]), org=str(o["organisation_id"]), score=r["score"], relevance=r)


# ===================================================================== supplied datasets
def import_supplied(db: Database, settings: Settings, *, data: bytes, filename: str, name: str | None, notes: str | None, meta: RequestMeta,
                    by: str | None = None) -> dict[str, Any]:
    try:
        import openpyxl  # noqa: WPS433
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise CompanyRejected(422, f"The workbook could not be read: {str(exc)[:120]}") from exc
    sheets: dict[str, list[list[Any]]] = {}
    total = 0
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(list(r))
            total += 1
            if total > MAX_SUPPLIED_ROWS:
                raise CompanyRejected(413, f"More than {MAX_SUPPLIED_ROWS} rows: split the workbook")
        sheets[ws.title] = rows
    ds = ci.parse_supplied_sheets(sheets, filename=filename)
    if not ds.rows:
        raise CompanyRejected(422, "No company or airline rows were recognised: a sheet needs a header row naming the company (GSA), "
                                   "represented airlines and e-mail columns. " + "; ".join(ds.skipped)[:300])
    sha = hashlib.sha256(data).hexdigest()
    prior = db.one("supplied_import_by_sha", sha=sha)
    if prior:
        raise CompanyRejected(409, f"This file was already imported as '{prior['name']}' on {prior['imported_at']:%d %b %Y}")
    label = name or (f"Supplied list {ds.airport_iata}" if ds.airport_iata else filename)
    import_id = str(db.scalar("supplied_import_insert", name=label, filename=filename, sha=sha, airport=ds.airport_iata, country=ds.country,
                              notes=notes, by=by, session_ref=meta.session_ref))
    n_org = n_rel = n_contact = 0
    org_ids: set[str] = set()
    for row in ds.rows:
        with db.transaction() as tx:
            if row.kind == "gssa":
                oid = _org_find(tx, row.name or "")
                if oid is None:
                    oid = str(tx.scalar("org_insert_profile", name=row.name, kind="gssa", country=ds.country, website=None, origin="supplied",
                                        airport=ds.airport_iata, carrier_type=None))
                else:
                    tx.run("org_profile_fill", id=oid, website=None, country=ds.country, kind="gssa", description=None, services=None, locations=None,
                           parent=None, airport=ds.airport_iata, carrier_type=None, areas=["airline_representation"], researched=False)
                note = f"supplied list '{label}', sheet '{row.sheet}', row {row.row_number}: awaiting verification against current sources"
                tx.scalar("org_evidence_add", org=oid, supports="identity", source_kind="supplied", rdoc=None, url=None, quote=None, note=note,
                          import_id=import_id, session_ref=meta.session_ref)
                for e in row.emails:
                    tx.one("org_contact_upsert", org=oid, kind="email", value=e, purpose=None, status="supplied", url=None, note=note, evidence=None,
                           session_ref=meta.session_ref)
                    n_contact += 1
                for code in row.airline_codes:
                    _record_representation(tx, oid, code, "cargo", quote="", rdoc=None, url=None, airport=ds.airport_iata,
                                           countries=[ds.country] if ds.country else [], session_ref=meta.session_ref, status="supplied",
                                           import_id=import_id, basis=f"listed as represented airline in {note}; not assumed current")
                    n_rel += 1
                    org_ids.add(_ensure_airline(tx, code, meta, note))
                if any("ALL" in n for n in row.notes):
                    tx.scalar("org_evidence_add", org=oid, supports="representation", source_kind="supplied", rdoc=None, url=None, quote=None,
                              note=f"{note}; represented airlines stated as 'ALL' — no list supplied, nothing recorded as represented", import_id=import_id,
                              session_ref=meta.session_ref)
            else:
                codes = row.airline_codes or []
                oid = None
                for code in codes:
                    oid = _ensure_airline(tx, code, meta, f"supplied list '{label}', sheet '{row.sheet}', row {row.row_number}: awaiting verification",
                                          carrier_type=row.carrier_type)
                    org_ids.add(oid)
                    for e in row.emails:
                        tx.one("org_contact_upsert", org=oid, kind="email", value=e, purpose=None, status="supplied", url=None,
                               note=f"supplied list '{label}', sheet '{row.sheet}', row {row.row_number}; station {ds.airport_iata or '—'}", evidence=None,
                               session_ref=meta.session_ref)
                        n_contact += 1
                    if ds.airport_iata:
                        tx.run("org_profile_fill", id=oid, website=None, country=None, kind=None, description=None, services=None,
                               locations=f"station {ds.airport_iata}", parent=None, airport=None, carrier_type=row.carrier_type, areas=[], researched=False)
                if oid is None and row.name:
                    oid = _org_find(tx, row.name) or str(tx.scalar("org_insert_profile", name=row.name, kind="airline", country=None, website=None,
                                                                   origin="supplied", airport=None, carrier_type=row.carrier_type))
            if oid:
                org_ids.add(oid)
            tx.scalar("supplied_row_insert", import_id=import_id, sheet=row.sheet, row=row.row_number, raw=row.raw, org=oid,
                      note="; ".join(row.notes) or None)
    n_org = len(org_ids)
    db.run("supplied_import_finish", id=import_id, rows=len(ds.rows), orgs=n_org, rels=n_rel, contacts=n_contact)
    audit(db, "supplied_dataset_imported", meta, entity_type="supplied_import", entity_id=import_id,
          detail={"name": label, "rows": len(ds.rows), "organisations": n_org, "relationships": n_rel, "contacts": n_contact, "skipped": ds.skipped[:20]})
    return {"id": import_id, "name": label, "airport_iata": ds.airport_iata, "country": ds.country, "rows": len(ds.rows), "organisations": n_org,
            "relationships": n_rel, "contacts": n_contact, "skipped": ds.skipped,
            "note": "Everything from this file is recorded as supplied data awaiting verification: contacts and representation agreements are not "
                    "assumed current. Research each company (Discover → Companies) to source current evidence, then verify."}


def _ensure_airline(tx: Database, code: str, meta: RequestMeta, note: str, carrier_type: str | None = None) -> str:
    cid = tx.scalar("org_by_code", code=code)
    if cid:
        if carrier_type:
            tx.run("org_profile_fill", id=str(cid), website=None, country=None, kind=None, description=None, services=None, locations=None, parent=None,
                   airport=None, carrier_type=carrier_type, areas=[], researched=False)
        return str(cid)
    name, label = resolve(code)
    oid = _org_find(tx, name) if name else None
    if oid is None:
        oid = str(tx.scalar("org_insert_profile", name=name or label, kind="airline", country=None, website=None, origin="supplied", airport=None,
                            carrier_type=carrier_type or "unknown"))
        tx.scalar("org_evidence_add", org=oid, supports="identity", source_kind="supplied", rdoc=None, url=None, quote=None,
                  note=note + (f"; designator {code} resolved from the reference list (a reading aid, not evidence)" if name else
                               f"; designator {code} not in the reference list: kept as written"), import_id=None, session_ref=meta.session_ref)
    tx.run("airline_ensure", org=oid, iata=code)
    if carrier_type:
        tx.run("org_profile_fill", id=oid, website=None, country=None, kind=None, description=None, services=None, locations=None, parent=None,
               airport=None, carrier_type=carrier_type, areas=[], researched=False)
        tx.scalar("org_evidence_add", org=oid, supports="carrier_type", source_kind="supplied", rdoc=None, url=None, quote=None,
                  note=f"{note}; type stated as {ci.CARRIER_LABELS.get(carrier_type, carrier_type)}", import_id=None, session_ref=meta.session_ref)
    return oid


# ===================================================================== profiles, verification, opportunities
def profile(db: Database, org_id: str) -> dict[str, Any]:
    o = db.one("org_profile_get", id=org_id)
    if o is None:
        raise CompanyRejected(404, "Company not found")
    from ..domain import relationships as rel
    people = db.all("org_people", org=org_id)
    for p in people:
        p["linkedin_search_url"] = rel.linkedin_search_url(p["full_name"], o["canonical_name"])
        p["state_label"] = rel.STATE_LABELS.get(p.get("state") or "research_candidate", "Research candidate")
    rels = db.all("org_relationships", org=org_id)
    for r in rels:
        r["relationship_label"] = ci.RELATIONSHIP_LABELS.get(r["relationship"], r["relationship"])
        r["status_label"] = REL_STATUS_LABELS.get(r["status"], r["status"])
        if r.get("counterparty_code") and not r.get("counterparty"):
            r["counterparty"] = resolve(r["counterparty_code"])[1]
    contacts = db.all("org_contacts", org=org_id)
    for c in contacts:
        c["status_label"] = CONTACT_STATUS_LABELS.get(c["status"], c["status"])
    state = _state(o)
    ap = airport(o.get("airport_iata"))
    return {**o, "kind_label": ci.KIND_LABELS.get(o["kind"], o["kind"]), "carrier_type_label": ci.CARRIER_LABELS.get(o.get("carrier_type") or "", None),
            "country_name": COUNTRIES.get(o.get("country") or "", (None,))[0], "airport_name": ap[0] if ap else None,
            "capability_area_labels": [ov.CATEGORY_LABELS.get(a, a) for a in (o.get("capability_areas") or [])],
            "state": state, "state_label": STATE_LABELS[state], "people": people, "relationships": rels, "represented_by": db.all("org_represented_by", org=org_id),
            "contacts": contacts, "evidence": db.all("org_evidence", org=org_id), "actions": _actions(o, contacts, rels, people),
            "rule": "What is shown is what a source said or a supplied list stated. Supplied items are not assumed current; a person verifies them "
                    "against current evidence. A relevant company is not an opportunity until a person records one with the interpretation."}


REL_STATUS_LABELS = {"supplied": "Supplied — awaiting verification", "sourced": "Sourced from a public page", "confirmed": "Confirmed by a person",
                     "lapsed": "Lapsed", "not_established": "Not established"}
CONTACT_STATUS_LABELS = {"supplied": "Supplied — awaiting verification", "published": "Published on a public page", "verified": "Verified by a person",
                         "lapsed": "Lapsed"}
STATE_LABELS = {"verified": "Verified", "awaiting_verification": "Supplied — awaiting verification", "researched": "Researched — not yet verified",
                "recorded": "Recorded"}


def _state(o: dict[str, Any]) -> str:
    if o.get("verified_at"):
        return "verified"
    if o.get("supplied_at") and not o.get("last_researched_at"):
        return "awaiting_verification"
    if o.get("last_researched_at"):
        return "researched"
    return "recorded"


def _actions(o: dict[str, Any], contacts: list[dict[str, Any]], rels: list[dict[str, Any]], people: list[dict[str, Any]]) -> list[str]:
    out = []
    if not o.get("website"):
        out.append("Record the official website so its pages can be read")
    if o.get("supplied_at") and not o.get("last_researched_at"):
        out.append("Research this company (Discover → Companies, named organisation) to source current evidence for the supplied data")
    if any(c["status"] == "supplied" for c in contacts):
        out.append("Check each supplied e-mail address against the company's current pages before use")
    if any(r["status"] == "supplied" for r in rels):
        out.append("Confirm or mark as lapsed each supplied representation: it is not assumed current")
    if not people:
        out.append("Discover relevant people at this company (Discover → People, named organisation)")
    if not o.get("verified_at"):
        out.append("Verify the record once the website, kind and country are confirmed by current sources")
    return out


def list_companies(db: Database, **filters: Any) -> dict[str, Any]:
    rows = db.all("companies_list", **filters)
    total = int(rows[0]["total"]) if rows else 0
    for r in rows:
        r.pop("total", None)
        r["kind_label"] = ci.KIND_LABELS.get(r["kind"], r["kind"])
        r["carrier_type_label"] = ci.CARRIER_LABELS.get(r.get("carrier_type") or "", None)
        r["country_name"] = COUNTRIES.get(r.get("country") or "", (None,))[0]
        st = _state(r)
        r["state"], r["state_label"] = st, STATE_LABELS[st]
    return {"items": rows, "total": total}


def edit(db: Database, org_id: str, data: dict[str, Any], meta: RequestMeta) -> None:
    kind = data.get("kind")
    if kind and kind not in ci.KIND_LABELS:
        raise CompanyRejected(422, "unknown kind")
    ct = data.get("carrier_type")
    if ct and ct not in ci.CARRIER_LABELS:
        raise CompanyRejected(422, "unknown carrier type")
    country = (data.get("country") or "").upper() or None
    if country and country not in COUNTRIES:
        raise CompanyRejected(422, "unknown country")
    ap = (data.get("airport_iata") or "").upper() or None
    if ap and not airport(ap):
        raise CompanyRejected(422, f"airport {ap} is not in the reference list")
    if not db.scalar("org_profile_edit", id=org_id, website=data.get("website"), kind=kind, country=country, description=data.get("description"),
                     services=data.get("services_text"), locations=data.get("locations_text"), parent=data.get("parent_group"), airport=ap, carrier_type=ct):
        raise CompanyRejected(404, "Company not found")
    if data.get("basis"):
        db.scalar("org_evidence_add", org=org_id, supports="note", source_kind="note", rdoc=None, url=data.get("source_url"), quote=None,
                  note=f"edited by a person: {data['basis']}", import_id=None, session_ref=meta.session_ref)
    audit(db, "company_edited", meta, entity_type="organisation", entity_id=org_id, detail={k: v for k, v in data.items() if v})


def verify(db: Database, org_id: str, basis: str, source_url: str | None, meta: RequestMeta) -> None:
    if not basis or len(basis.strip()) < 10:
        raise CompanyRejected(422, "say what was checked and where (at least 10 characters)")
    if not db.scalar("org_verify", id=org_id, basis=basis.strip()):
        raise CompanyRejected(404, "Company not found")
    db.scalar("org_evidence_add", org=org_id, supports="note", source_kind="note", rdoc=None, url=source_url, quote=None,
              note=f"verified by a person: {basis.strip()}", import_id=None, session_ref=meta.session_ref)
    audit(db, "company_verified", meta, entity_type="organisation", entity_id=org_id, detail={"basis": basis.strip(), "source_url": source_url})


def set_contact_status(db: Database, org_id: str, contact_id: str, status: str, note: str | None, meta: RequestMeta) -> None:
    if status not in ("verified", "lapsed"):
        raise CompanyRejected(422, "status must be verified or lapsed")
    if status == "verified" and not (note and len(note.strip()) >= 5):
        raise CompanyRejected(422, "say where the address was confirmed")
    if not db.scalar("org_contact_status", id=contact_id, org=org_id, status=status, note=note):
        raise CompanyRejected(404, "Contact not found")
    audit(db, "company_contact_status", meta, entity_type="organisation", entity_id=org_id, detail={"contact_id": contact_id, "status": status})


def set_relationship_status(db: Database, org_id: str, rel_id: str, status: str, basis: str, by: str | None, meta: RequestMeta) -> None:
    if status not in ("confirmed", "lapsed", "not_established"):
        raise CompanyRejected(422, "status must be confirmed, lapsed or not_established")
    if not basis or len(basis.strip()) < 10:
        raise CompanyRejected(422, "give the basis (at least 10 characters)")
    if not db.scalar("org_rel_status", id=rel_id, org=org_id, status=status, basis=basis.strip(), by=by):
        raise CompanyRejected(404, "Relationship not found")
    audit(db, "company_relationship_status", meta, entity_type="organisation", entity_id=org_id, detail={"relationship_id": rel_id, "status": status})


def create_opportunity(db: Database, org_id: str, data: dict[str, Any], meta: RequestMeta) -> dict[str, Any]:
    """A potential commercial opportunity from a researched company, with the interpretation a person gives. Never automatic."""
    o = db.one("org_profile_get", id=org_id)
    if o is None:
        raise CompanyRejected(404, "Company not found")
    module = data.get("module")
    if module not in ov.CATEGORY_LABELS:
        raise CompanyRejected(422, "choose a capability area")
    interp = (data.get("interpretation") or "").strip()
    if len(interp) < 20:
        raise CompanyRejected(422, "explain the interpretation: why this company could lead to business (at least 20 characters)")
    title = (data.get("title") or "").strip() or f"{o['canonical_name']}: {ov.CATEGORY_LABELS[module]}"
    row = db.one("opportunity_from_company", module=module, org=org_id, title=title[:200], interpretation=interp, by=data.get("by_label"))
    opp_id = str(row["id"])
    if row.get("inserted"):
        db.run("opportunity_history_add", id=opp_id, field="record_type", **{"from": None}, to="commercial",
               reason=f"recorded from the company record; interpretation: {interp[:200]}", session_ref=meta.session_ref)
    country = (data.get("country") or o.get("country") or "").upper() or None
    if country and country in COUNTRIES:
        db.run("opportunity_geo_add", opp=opp_id, country=country)
    audit(db, "opportunity_from_company", meta, entity_type="opportunity", entity_id=opp_id,
          detail={"organisation_id": org_id, "module": module, "interpretation": interp, "new": bool(row.get("inserted"))})
    return {"id": opp_id, "new": bool(row.get("inserted")), "title": title,
            "note": "Recorded as a potential commercial opportunity with your interpretation. It is not a tender and has no procurement reference; "
                    "qualification applies the commercial checks, not tender deadline checks."}


def supplied_imports(db: Database) -> list[dict[str, Any]]:
    return db.all("supplied_imports_list")


def supplied_import_detail(db: Database, import_id: str) -> dict[str, Any]:
    i = db.one("supplied_import_get", id=import_id)
    if i is None:
        raise CompanyRejected(404, "Supplied dataset not found")
    return {**i, "rows": db.all("supplied_rows_for", id=import_id)}
