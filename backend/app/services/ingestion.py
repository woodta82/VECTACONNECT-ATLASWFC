"""Evidence pipeline (directive §3): retrieval -> content extraction -> claim
extraction -> FIELD VALIDATION -> entity resolution -> evidence linking ->
duplicate detection -> classification -> qualification -> prioritisation ->
opportunity display.

This service takes one retrieved document and the claims proposed for it
(by the AI extractor or by a human reviewer) and does everything after
extraction, in one transaction:

- every material field of every claim is validated on its own
  (domain.field_validation); unsupported fields are stored for review and
  never become facts;
- a claim whose TYPE is not stated by its quote is not a claim: it is
  recorded as an extraction rejection for the review queue;
- airlines, organisations, countries and airports are resolved to canonical
  records (services.resolution);
- signal identity follows tender references / procurement cycles /
  announcement families (domain.identity), so distinct tenders stay
  distinct, amendments apply to the right tender, route announcements are
  never merged with tenders, and look-alikes become merge-review candidates;
- confidence counts independent announcement FAMILIES (syndicated copies add
  nothing) and only documents that passed the authenticity check;
- an opportunity exists only for a supported tender from an authoritative
  source family; repeated runs update it, never multiply it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from ..domain import eligibility, relevance
from ..domain import evidence as ev
from ..domain import qualification as qual
from ..domain.deadlines import StatedDeadline
from ..domain.capability import CapabilityRecord, Credential, capability_readiness
from ..domain.field_validation import FieldClaim, validate_claim
from ..domain.identity import TENDER_ANCHORS, TENDER_FOLLOWERS, Identity, norm_ref, signal_identity, tender_similarity
from ..repo.db import Database
from . import resolution

PARSER_VERSION = "wfc-parse-2"
EXCERPT_CHARS = 4000

ROUTE_GAPS = [
    "Representation arrangements for this route are unknown",
    "Spare or bookable capacity is not established by a route announcement",
    "A route announcement does not establish an open representation appointment or a payable opportunity",
]
TENDER_GAPS_UNVERIFIED = ["Tender existence not confirmed by an authoritative source", "Deadline not confirmed"]
GEO_ROLE = {"country": "delivery", "issuer_country": "issuer", "contract_territory": "contract_territory",
            "origin": "origin", "destination": "destination"}
SCOPE_ROLES = ("delivery", "contract_territory", "origin", "destination")
SERVICE_FOR_TYPE = {"gssa_tender": "GSSA", "tcm_signal": "TCM"}


@dataclass
class SourceInfo:
    id: str
    family: str
    authority: str
    base_url: str | None
    retention_permitted: bool


@dataclass
class IncomingDocument:
    source: SourceInfo
    original_url: str
    final_url: str
    text: str
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    # Where the publication date comes from: 'document_text', 'page', 'pdf_metadata' or 'feed' (domain.publication); None = unknown.
    published_source: str | None = None
    publication_flag: str | None = None  # 'future' | 'inconsistent': a stated date that was not used
    publication_note: str | None = None  # what was found and why it was (not) used
    content_type: str | None = "text/html"
    snapshot_path: str | None = None
    page_ref: str | None = None
    run_id: str | None = None
    language: str | None = None
    retrieved: bool = True              # False for documents entered by hand


@dataclass
class ClaimProposal:
    """One claim proposed for one document, before validation."""
    claim_type: str
    quote: str
    fields: dict[str, FieldClaim] = field(default_factory=dict)
    assessed_by: Literal["rule", "ai_proposed", "human"] = "ai_proposed"
    stance: Literal["supports", "contradicts", "mentions"] = "supports"
    deadline_timezone: str | None = None
    summary: str | None = None
    raw: dict[str, Any] | None = None   # the extractor's original output, kept for rejections
    location: str | None = None         # where the quote sits in the full document ("page 3, chars 10450-10620")


@dataclass
class SignalOutcome:
    signal_id: str
    module: str
    classification: str
    is_new: bool
    opportunity_id: str | None
    qualification_status: str | None


@dataclass
class IngestResult:
    document_id: str
    document_new: bool
    family_key: str
    family_new: bool
    claim_ids: list[str]
    signals: list[SignalOutcome]
    rejected: list[str]

    def _first(self) -> SignalOutcome | None:
        tenders = [s for s in self.signals if s.opportunity_id]
        return tenders[0] if tenders else (self.signals[0] if self.signals else None)

    @property
    def signal_id(self) -> str | None:
        f = self._first()
        return f.signal_id if f else None

    @property
    def classification(self) -> str | None:
        f = self._first()
        return f.classification if f else None

    @property
    def opportunity_id(self) -> str | None:
        f = self._first()
        return f.opportunity_id if f else None

    @property
    def qualification_status(self) -> str | None:
        f = self._first()
        return f.qualification_status if f else None


# ===================================================================== ingest


def store_document(tx: Database, doc: IncomingDocument, *, extraction_status: str = "pending",
                   extraction_detail: str | None = None) -> tuple[str, bool, str, bool]:
    """Upsert the document (same canonical URL + content = same document) and
    its separate reachability/authenticity checks. Returns
    (document_id, inserted, family_key, family_new)."""
    canonical = ev.canonicalize_url(doc.final_url)
    chash = ev.content_hash(doc.text)
    excerpt = doc.text.strip()[:EXCERPT_CHARS]
    candidates = [ev.FamilyCandidate(r["family_key"], ev.shingles(ev.normalise_text(r["excerpt"] or "")))
                  for r in tx.all("family_candidates")]
    family_key, family_new, _sim = ev.assign_family(excerpt, candidates)
    family_id = tx.scalar("family_upsert", key=family_key)
    drow = tx.one("document_upsert", source_id=doc.source.id, run_id=doc.run_id, family_id=family_id,
                  original_url=doc.original_url, canonical_url=canonical, publisher=doc.publisher,
                  published_at=doc.published_at, event_date=None, content_hash=chash, content_type=doc.content_type,
                  byte_size=len(doc.text.encode("utf-8")), title=doc.title, excerpt=excerpt, page_ref=doc.page_ref,
                  snapshot_path=doc.snapshot_path if doc.source.retention_permitted else None,
                  parser_version=PARSER_VERSION, language=doc.language,
                  body_text=doc.text if doc.source.retention_permitted else None,
                  published_at_source=(doc.published_source or "page") if doc.published_at else None,
                  publication_flag=doc.publication_flag, publication_note=doc.publication_note)
    assert drow is not None
    doc_id = str(drow["id"])
    inserted = bool(drow["inserted"])
    if inserted:
        authentic = ev.authenticity_check(doc.final_url, doc.source.base_url)
        for check_type, result, detail in (
            ("reachability", "pass" if doc.retrieved else "unknown",
             "retrieved by the SSRF-safe fetcher" if doc.retrieved else "entered by a reviewer, not retrieved"),
            ("authenticity", authentic, f"served from {doc.final_url}"),
            ("current_status", "unknown", "not established by retrieval"),
        ):
            tx.run("document_check_add", doc=doc_id, check_type=check_type, result=result, detail=detail)
        tx.run("document_set_extraction", id=doc_id, status=extraction_status, detail=extraction_detail)
    return doc_id, inserted, family_key, family_new


def document_text(tx: Database, doc_id: str) -> str:
    row = tx.one("document_text", id=doc_id)
    if row is None:
        raise KeyError(doc_id)
    return row["body_text"] or row["excerpt"] or ""


def ingest(db: Database, doc: IncomingDocument, proposals: list[ClaimProposal], *, now: datetime | None = None,
           extraction_status: str | None = None, extraction_detail: str | None = None) -> IngestResult:
    now = now or datetime.now(timezone.utc)
    with db.transaction() as tx:
        doc_id, inserted, family_key, family_new = store_document(
            tx, doc, extraction_status=extraction_status or ("extracted" if proposals else "no_claims"),
            extraction_detail=extraction_detail)
        if not inserted and extraction_status:
            tx.run("document_set_extraction", id=doc_id, status=extraction_status, detail=extraction_detail)
        claim_ids, outcomes, rejected = apply_claims(tx, doc_id, family_key, doc.text, proposals, now=now)
        relevance = "pass" if claim_ids else ("fail" if proposals else "unknown")
        tx.run("document_check_add", doc=doc_id, check_type="relevance", result=relevance,
               detail=f"{len(claim_ids)} validated claim(s); {len(rejected)} rejected")
    return IngestResult(doc_id, inserted, family_key, family_new, claim_ids, outcomes, rejected)


# ===================================================================== claims


@dataclass
class _Prepared:
    proposal: ClaimProposal
    validation: Any
    subject_id: str | None
    subject_label: str | None
    geography: list[tuple[str, str, str]]       # (country, role, support)
    lane: str | None
    tender_ref: str | None
    cycle: str | None
    service: str | None
    deadline: StatedDeadline | None          # as precise as the source states it (domain.deadlines)
    status: str | None
    freight_scope: str | None = None         # cargo / passenger / mixed / unclear (domain.relevance), None when not applicable
    geography_conflict: str | None = None


def _prepare(tx: Database, doc_id: str, text: str, p: ClaimProposal) -> _Prepared:
    published = tx.scalar("document_published_at", id=doc_id)
    title = tx.scalar("document_title", id=doc_id)
    v = validate_claim(p.claim_type, p.fields, text, claim_quote=p.quote, deadline_timezone=p.deadline_timezone,
                       airport_country=lambda c: resolution.airport_country(tx, c),
                       reference_date=published.date() if published else None, stance=p.stance, document_title=title,
                       reviewer=p.assessed_by == "human")
    prov = None
    subject_id = subject_label = None
    air = v.first("airline")
    org = v.first("organisation")
    if air is not None:
        iata = air.value if len(air.value) == 2 and air.value.isupper() else None
        prov = prov or str(tx.scalar("provenance_insert", kind="source_document", job=None, row=None, doc=doc_id, note="entity resolution"))
        subject_id = resolution.airline(tx, name=None if iata else air.value, iata=iata, provenance_id=prov)
        subject_label = air.value
    elif org is not None:
        prov = prov or str(tx.scalar("provenance_insert", kind="source_document", job=None, row=None, doc=doc_id, note="entity resolution"))
        subject_id = resolution.organisation(tx, org.value, "other", provenance_id=prov)
        subject_label = org.value
    else:
        unsupported = next((f for f in v.fields if f.field in ("airline", "organisation")), None)
        subject_label = unsupported.value if unsupported else None
    geography: list[tuple[str, str, str]] = []
    for f in v.fields:
        if f.field in GEO_ROLE and f.support in ("supported", "unsupported") and f.extra.get("country"):
            geography.append((f.extra["country"], GEO_ROLE[f.field], "supported" if f.support == "supported" else "unverified"))
            # Proposed as the delivery country but stated only as where the issuer is based: keep that fact, in its true role,
            # so a search for that country shows an issuer-only match rather than a delivery match.
            if f.support == "unsupported" and GEO_ROLE[f.field] != "issuer" and "issuer" in f.extra.get("stated_roles", []):
                geography.append((f.extra["country"], "issuer", "supported"))
    o, d = v.first("origin"), v.first("destination")
    lane = f"{o.normalised}-{d.normalised}" if o and d else None
    ref = v.first("tender_ref")
    cyc = v.first("procurement_cycle")
    svc = v.first("service")
    dl = v.first("deadline")
    st = v.first("status")
    scope = next((f.normalised for f in v.fields if f.field == "freight_scope"), None)
    service = svc.normalised if svc else SERVICE_FOR_TYPE.get(p.claim_type)
    if service is None and p.claim_type in ("route_launch", "route_suspension", "representation_change"):
        service = _stated_trucking(p.quote, text)
    return _Prepared(p, v, subject_id, subject_label, geography, lane, ref.normalised if ref else None,
                     cyc.normalised if cyc else None, service,
                     StatedDeadline.from_json(dl.extra.get("deadline")) if dl else None,
                     st.normalised if st else None, scope, v.geography_conflict)


_TRUCKING_STATED = (r"\broad feeder\b", r"\brfs\b", r"\btrucking\b", r"\btruck(?:ed|s)? (?:service|connection|link)s?\b", r"\bcamionaje\b",
                    r"\btransport routier\b", r"\bcamionnage\b")


def _stated_trucking(quote: str, document: str) -> str | None:
    """TRUCKING when the claim's own quote states a road-feeder / trucking service, affirmed in its clause."""
    from ..domain import meaning
    m = meaning.first_match(_TRUCKING_STATED, quote or "")
    if m is None:
        return None
    pol = meaning.polarity_in_context(quote, m.start(), document, length=m.end() - m.start())
    return "TRUCKING" if pol in ("affirmed", "planned") else None


def _claim_key(signal_key: str, prep: _Prepared) -> str:
    """A claim is a (fact, stated value) pair within one signal: two documents
    stating the same deadline support ONE claim; a revised deadline or a
    cancellation is a different claim on the same signal."""
    parts = [signal_key, prep.proposal.claim_type]
    if prep.proposal.claim_type in TENDER_ANCHORS | TENDER_FOLLOWERS:
        parts += [prep.deadline.label() if prep.deadline else "-", prep.status or "-"]
    if prep.proposal.claim_type in ("eligibility", "tender_scope"):
        # Each criterion (or scope statement) is its own claim: three requirements in one notice are three claims, each
        # validated and reviewable on its own, never folded into the first one proposed.
        crit = prep.proposal.fields.get("eligibility") or prep.proposal.fields.get("contract_territory")
        key_text = (crit.value if crit is not None else prep.proposal.quote).strip().lower()
        parts.append(hashlib.sha256(" ".join(key_text.split()).encode()).hexdigest()[:12])
    return "|".join(parts)   # stance is NOT part of identity: a contradiction attaches to the same claim


def apply_claims(tx: Database, doc_id: str, family_key: str, text: str, proposals: list[ClaimProposal], *,
                 now: datetime) -> tuple[list[str], list[SignalOutcome], list[str]]:
    prepared: list[_Prepared] = []
    rejected: list[str] = []
    for i, p in enumerate(proposals):
        prep = _prepare(tx, doc_id, text, p)
        restates = p.claim_type in TENDER_ANCHORS and prep.validation.type_supported and "status" not in p.fields and "deadline" not in p.fields
        if (not prep.validation.type_supported or restates) and p.claim_type in TENDER_ANCHORS:
            ctx = _as_context(tx, p, doc_id)
            if ctx is not None:
                cprep = _prepare(tx, doc_id, text, ctx)
                if cprep.validation.type_supported:
                    prepared.append(cprep)
                    continue
        if not prep.validation.type_supported:
            reason = f"{p.claim_type}: {prep.validation.type_reason}"
            tx.run("rejection_add", doc=doc_id, call=None, idx=i, reason=reason,
                   raw=p.raw or {"claim_type": p.claim_type, "quote": p.quote,
                                 "fields": {k: {"value": f.value, "quote": f.quote} for k, f in p.fields.items()}})
            rejected.append(reason)
            continue
        prepared.append(prep)

    conflict = next((x.validation.contradiction for x in prepared if x.validation.contradiction), None)
    if conflict:
        tx.run("document_set_contradiction", id=doc_id, text=conflict[:1000])
    geo_conflict = next((x.geography_conflict for x in prepared if x.geography_conflict), None)
    if geo_conflict:
        tx.run("document_set_geography_conflict", id=doc_id, text=geo_conflict[:1000])
    # The document's tender (if it announces one) anchors its follower claims
    # (deadline, status, scope, eligibility) that carry no reference of their own.
    anchor = next((x for x in prepared if x.proposal.claim_type in TENDER_ANCHORS), None)
    family_key = _announcement_family(tx, doc_id, family_key, anchor)
    by_signal: dict[tuple[str, str], tuple[Any, list[tuple[_Prepared, str]]]] = {}
    claim_ids: list[str] = []
    for prep in prepared:
        ct = prep.proposal.claim_type
        subject = prep.subject_id
        countries = sorted({c for c, role, s in prep.geography if s == "supported" and role in SCOPE_ROLES})
        ref, cyc, svc = prep.tender_ref, prep.cycle, prep.service
        tender_module = None
        # A follower in the same document as the tender it belongs to. When the follower cites a reference the
        # announcement itself did not (a long notice: announcement on page 1, "Tender reference ..." at the end), it is
        # still the document's tender, unless that reference already identifies another tender (handled below).
        same_doc_ref = (ct in TENDER_FOLLOWERS and anchor is not None and bool(ref) and not anchor.tender_ref
                        and (subject is None or subject == anchor.subject_id))
        same_ref = (ct in TENDER_FOLLOWERS and anchor is not None and bool(ref) and bool(anchor.tender_ref)
                    and norm_ref(ref or "") == norm_ref(anchor.tender_ref or ""))
        if ct in TENDER_FOLLOWERS and anchor is not None and (not ref or same_doc_ref or same_ref):
            subject = subject or anchor.subject_id
            if not ref:
                ref, cyc = anchor.tender_ref, anchor.cycle
            countries = countries or sorted({c for c, role, s in anchor.geography if s == "supported" and role in SCOPE_ROLES})
            svc = svc or anchor.service
            tender_module = signal_identity(anchor.proposal.claim_type, subject=None, countries=[], lane=None, tender_ref=None,
                                            procurement_cycle=None, family_key=family_key, service_code=anchor.service).module
        ident = signal_identity(ct, subject=subject, countries=countries, lane=prep.lane,
                                tender_ref=None if same_doc_ref else ref, procurement_cycle=None if same_doc_ref else cyc,
                                family_key=family_key, service_code=svc, tender_module=tender_module)
        if ref and ct in TENDER_ANCHORS | TENDER_FOLLOWERS:
            ident = _tender_by_reference(tx, ref, subject) or ident
        stance = prep.proposal.stance
        key = _claim_key(ident.key, prep)
        cid = tx.scalar("claim_find", key=key)
        if cid is None:
            type_field = next((f for f in prep.validation.fields if f.field == "opportunity_type"), None)
            planned = bool(type_field and "planned" in (type_field.extra.get("modality") or []) and "affirmed" not in (type_field.extra.get("modality") or []))
            value = {"status": prep.status, "service": svc, "summary": prep.proposal.summary, "planned": True if planned else None}
            cid = tx.scalar("claim_insert2", claim_type=ct, key=key, signal_key=ident.key, airline_id=subject if prep.validation.first("airline") else None,
                            subject_org=subject, territory_id=None, lane_id=None, value={k: v for k, v in value.items() if v},
                            deadline=prep.deadline.exact_utc if prep.deadline else None,
                            tz=prep.deadline.zone if prep.deadline and prep.deadline.precision == "instant" else None,
                            info=prep.deadline.to_json() if prep.deadline else None, tender_ref=ref, cycle=cyc, label=prep.subject_label,
                            review="confirmed" if prep.proposal.assessed_by == "human" else "proposed")
        cid = str(cid)
        for f in prep.validation.fields:
            tx.run("claim_field_add", claim=cid, doc=doc_id, field=f.field, value=f.value[:2000], normalised=f.normalised[:2000],
                   quote=(f.quote or "")[:2000] or None, support=f.support, reason=f.reason[:500], assessed_by=prep.proposal.assessed_by,
                   version=eligibility.VALIDATION_VERSION)
        tx.run("claim_evidence_add", claim=cid, doc=doc_id, stance=stance, excerpt=prep.proposal.quote[:1000],
               page_ref=prep.proposal.location, assessed_by=prep.proposal.assessed_by)
        refresh_claim_status(tx, cid)
        claim_ids.append(cid)
        entry = by_signal.setdefault((ident.module, ident.key), (ident, []))
        entry[1].append((prep, cid))

    outcomes = [_upsert_signal(tx, ident, items, now) for ident, items in by_signal.values()]
    return claim_ids, outcomes, rejected


def _announcement_family(tx: Database, doc_id: str, family_key: str, anchor: "_Prepared | None") -> str:
    """Identity for a tender WITHOUT a reference or cycle is its announcement family, so syndicated copies
    of one notice (other sources) attach to one tender. But a second notice from the SAME source at a
    different address is a different tender even when it reuses the same template (directive §6): it gets
    its own identity and, if it resembles the first, goes to merge review instead of merging silently."""
    if anchor is None or anchor.tender_ref or anchor.cycle:
        return family_key
    if tx.scalar("family_has_other_doc_same_source", family=family_key, doc=doc_id):
        return f"{family_key}|doc:{doc_id}"
    return family_key


def _as_context(tx: Database, p: ClaimProposal, doc_id: str) -> "ClaimProposal | None":
    """Supporting information (`tender_context`) about a tender ALREADY established by another document (fifth instruction of
    27 Oct 2026, item 5): a tender proposal that announces no procurement (a contact update, a clarification), or that cites
    the tender without stating any status or deadline. Attached to that tender; it carries no status or deadline and is not a
    tender observation, so it never refreshes live status or the age of the announcement."""
    tr = p.fields.get("tender_ref")
    if tr is None or not tr.value:
        return None
    ident = _tender_by_reference(tx, str(tr.value), None)
    if ident is None or tx.scalar("signal_has_document", key=ident.key, doc=doc_id):
        return None
    keep = {k: v for k, v in p.fields.items() if k not in ("status", "deadline", "opportunity_type")}
    return ClaimProposal("tender_context", p.quote, keep, assessed_by=p.assessed_by, stance=p.stance, summary=p.summary,
                         raw=p.raw, location=p.location)


def _tender_by_reference(tx: Database, ref: str, subject: str | None) -> "Identity | None":
    """A claim that cites a tender reference attaches to the existing tender with that reference, whatever
    the claim's capability area and even when the claim does not name the airline (a corrigendum citing
    only the reference). Several candidates (same reference, different issuers) are not guessed between."""
    rows = tx.all("tender_signals_by_ref", ref=norm_ref(ref), subject=subject)
    if len(rows) != 1:
        return None
    return Identity(rows[0]["signal_key"], "tender_ref", rows[0]["module"], tuple(rows[0]["related_modules"] or ()))


def refresh_claim_status(tx: Database, claim_id: str) -> str:
    row = tx.one("claim_review_state", id=claim_id)
    if row and row["review_status"] == "rejected":
        tx.run("claim_set_status", id=claim_id, status="withdrawn")
        return "withdrawn"
    links = [ev.EvidenceLink(r["document_id"], r["family_key"] or r["document_id"], r["authority"], r["stance"],
                             r["published_at"], r["authentic"]) for r in tx.all("claim_links", claim=claim_id)]
    status = ev.assess_claim(links).status
    tx.run("claim_set_status", id=claim_id, status=status)
    return status


# ===================================================================== signals


def _fingerprint(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _upsert_signal(tx: Database, ident: Any, items: list[tuple[_Prepared, str]], now: datetime) -> SignalOutcome:
    first = items[0][0]
    anchor = next((p for p, _ in items if p.proposal.claim_type in TENDER_ANCHORS), first)
    title = _title(anchor)
    # The reference may be stated only by a follower (a deadline clause at the end of a long notice): the signal keeps it.
    ref = anchor.tender_ref or next((p.tender_ref for p, _ in items if p.tender_ref), None)
    cycle = anchor.cycle or next((p.cycle for p, _ in items if p.cycle), None)
    srow = tx.one("signal_upsert2", module=ident.module, classification="research_item", key=ident.key, title=title,
                  summary=None, gaps=[], basis=ident.basis, tender_ref=ref, cycle=cycle,
                  subject=anchor.subject_id, related=list(ident.related_modules))
    assert srow is not None
    signal_id, is_new = str(srow["id"]), bool(srow["inserted"])
    survivor = str(tx.scalar("signal_survivor", id=signal_id))
    if survivor != signal_id:          # merged after review: new evidence goes to the surviving signal
        signal_id, is_new = survivor, False
    for prep, cid in items:
        tx.run("signal_claim_link", signal=signal_id, claim=cid)
        for country, role, support in prep.geography:
            tx.run("signal_geo_add", signal=signal_id, country=country, role=role, support=support)
    if is_new and ident.basis in ("announcement", "procurement_cycle"):
        _merge_review(tx, signal_id, ident, anchor)
    return evaluate_signal(tx, signal_id, now, is_new=is_new)


def _merge_review(tx: Database, signal_id: str, ident: Any, anchor: _Prepared) -> None:
    """A tender without a reliable identifier that resembles another tender of
    the same subject goes to merge review. Nothing is merged automatically."""
    mine = {c for c, role, s in anchor.geography if s == "supported" and role in SCOPE_ROLES}
    for other in tx.all("tender_signals_for_subject", subject=anchor.subject_id, id=signal_id, module=ident.module):
        theirs = set(other["countries"] or [])
        if mine and theirs and not (mine & theirs):
            continue
        score = tender_similarity(mine, theirs, anchor.proposal.quote, other["title"] or "")
        left, right = sorted([signal_id, other["id"]])
        tx.run("merge_candidate_add", entity_type="signal", left=left, right=right, score=score,
               reason="tender without a stable reference resembles an existing tender of the same subject; review before merging")


def evaluate_signal(tx: Database, signal_id: str, now: datetime, *, is_new: bool = False) -> SignalOutcome:
    """Classify a signal from ALL its live evidence, resolve tender state with
    history, keep its opportunity and qualification in step."""
    sig = tx.one("signal_get", id=signal_id)
    assert sig is not None
    module = sig["module"]
    rows = tx.all("signal_claim_evidence2", signal=signal_id)
    live = [r for r in rows if r["review_status"] != "rejected" and r["excluded_at"] is None]
    claim_types = {r["claim_type"] for r in live if r["stance"] != "mentions"}
    anchor_links = [ev.EvidenceLink(r["document_id"], r["family_key"] or r["document_id"], r["authority"], r["stance"],
                                    r["published_at"], r["authentic"]) for r in live if r["claim_type"] in TENDER_ANCHORS]
    existence = ev.assess_claim(anchor_links) if anchor_links else None
    has_anchor = bool(claim_types & TENDER_ANCHORS)
    classification = qual.classify_airline_signal(
        claim_types=(claim_types - {"service_tender"}) | ({"gssa_tender"} if "service_tender" in claim_types else set()),
        tender_existence=existence)
    # A tender that every anchor describes only as PLANNED ("will issue a tender", "será licitada") is a lead, not an opportunity:
    # nothing is open until a source announces it.
    anchor_values = [r["value"] or {} for r in live if r["claim_type"] in TENDER_ANCHORS and r["stance"] == "supports"]
    planned_only = bool(anchor_values) and all(v.get("planned") for v in anchor_values)
    if planned_only and classification == "qualified_opportunity":
        classification = "unverified_lead"

    observations = []
    for r in live:
        if r["claim_type"] not in TENDER_ANCHORS | {"tender_status", "tender_deadline"} or r["stance"] != "supports":
            continue
        if r["authentic"] == "fail":
            continue
        value = r["value"] or {}
        observations.append(ev.TenderObservation(
            r["document_id"], r["family_key"] or r["document_id"], r["source_family"], r["authority"],
            r["published_at"],              # the PUBLICATION date only: retrieval is never a status date (fourth instruction, items 1-2)
            "contradictory" if r.get("status_contradiction") and value.get("status") in (None, "open", "revised") else value.get("status"),
            r["deadline_utc"], r["deadline_source_tz"], StatedDeadline.from_json(r["deadline_info"]),
            contradiction=r.get("status_contradiction"), retrieved_at=r["retrieved_at"],
            reopening=value.get("status") in ("open", "revised") and ev.reopening_stated(r.get("status_quote"), r.get("excerpt"))))
    # A supported anchor establishes that the procurement notice exists ("announced"); it does not by itself make it open.
    tender = ev.resolve_tender(observations, now, announced=has_anchor and existence is not None and existence.status == "supported") \
        if (has_anchor or observations) else None
    # Geography follows the LIVE field assessments: a delivery country whose 'supported' verdict was withdrawn (re-check,
    # correction, rejection) is no longer a supported country of the signal, so it leaves country matches, exports and briefings.
    tx.run("signal_geo_recompute", signal=signal_id)
    geo = tx.all("signal_geo", signal=signal_id)
    # Freight relevance of the signal, from its live anchor claims (domain.relevance); passenger-only mandates are excluded.
    scope_rows = tx.all("signal_scope_fields", signal=signal_id)
    freight_scope: str | None = relevance.combine([r["normalised"] for r in scope_rows]) if scope_rows else None
    freight_reason = next((r["reason"] for r in scope_rows if r["normalised"] == freight_scope), None) if freight_scope else None
    if has_anchor and freight_scope is None:
        freight_scope, freight_reason = "unclear", "freight relevance not yet assessed for this record (assessment made under earlier validation rules)"
    if freight_scope in relevance.EXCLUDED_SCOPES and classification in ("qualified_opportunity", "unverified_lead"):
        classification = "excluded"
    elif freight_scope in relevance.REVIEW_SCOPES and classification == "qualified_opportunity":
        # A reviewable candidate, not a qualified freight opportunity: the record exists so a person can settle the freight scope.
        classification = "freight_candidate"
    geo_conflict = next((r["geography_conflict"] for r in tx.all("signal_geo_conflicts", signal=signal_id)), None)

    gaps: list[str] = []
    if planned_only:
        gaps.append("A planned tender is stated; it is not open until a source announces it")
    if freight_scope in relevance.EXCLUDED_SCOPES:
        gaps.append(f"Excluded from the freight pipeline: {freight_reason}")
    elif freight_scope in relevance.REVIEW_SCOPES:
        gaps.append(f"Freight candidate, not a qualified freight opportunity — freight relevance pending review: {freight_reason}")
    if geo_conflict:
        gaps.append(f"Geography conflict in the source: {geo_conflict}")
    if claim_types & {"route_launch", "route_suspension", "capacity_statement"}:
        gaps += ROUTE_GAPS
    if has_anchor and classification not in ("qualified_opportunity", "freight_candidate", "excluded"):
        gaps += TENDER_GAPS_UNVERIFIED
    if not any(g["support"] == "supported" and g["role"] in SCOPE_ROLES for g in geo):
        gaps.append("Delivery country not established by the evidence")
    if sig["subject_organisation_id"] is None:
        gaps.append("Airline or issuing organisation not established by the evidence")
    if tender is not None:
        gaps += [r for r in tender.reasons if r not in gaps]
        dl_fields = tx.all("signal_deadline_field_notes", signal=signal_id)
        gaps += sorted({n["reason"].split("; ", 1)[1] for n in dl_fields if "; " in (n["reason"] or "") and "assum" in n["reason"]})
    if any(r["assessed_by"] == "ai_proposed" and r["review_status"] == "proposed" for r in live):
        gaps.append("AI-proposed evidence awaits reviewer confirmation")
    withdrawn = tx.all("signal_withdrawn_verdicts", signal=signal_id)
    if withdrawn:
        gaps.append(f"{len(withdrawn)} eligibility assessment(s) re-checked under the current validation rules: an earlier 'supported' "
                    "verdict was withdrawn; a reviewer must confirm or correct the reading")
    families = len({r["family_key"] for r in live})
    tender_state = None if tender is None else {
        "status": tender.status, "stated_status": tender.stated_status, "basis": tender.basis,
        "published_at": tender.published_at.isoformat() if tender.published_at else None,
        "status_asserted_at": tender.status_asserted_at.isoformat() if tender.status_asserted_at else None,
        "status_verified_at": tender.status_verified_at.isoformat() if tender.status_verified_at else None,
        "status_document_id": tender.status_document_id, "status_date_known": tender.status_date_known,
        "retrieved_at": tender.retrieved_at.isoformat() if tender.retrieved_at else None,
        "status_conflict": tender.status_conflict,
        "deadline_utc": tender.deadline_utc.astimezone(timezone.utc).isoformat() if tender.deadline_utc else None,
        "deadline_source_tz": tender.deadline_source_tz, "deadline": tender.deadline.to_json() if tender.deadline else None,
        "deadline_conflict": tender.deadline_conflict,
        "actionable": tender.actionable, "history": tender.history, "reasons": tender.reasons}
    tx.run("signal_update_eval", id=signal_id, classification=classification,
           summary=f"{len(live)} evidence link(s) across {families} announcement family(ies)", gaps=gaps, tender_state=tender_state,
           first_published=min((r["published_at"] for r in live if r["published_at"]), default=None),
           last_evidence=max((r["retrieved_at"] for r in live if r["retrieved_at"]), default=None))
    tx.run("signal_set_scope", id=signal_id, scope=freight_scope, reason=freight_reason)

    existing_opp = tx.scalar("opportunity_by_signal", signal=signal_id)
    if existing_opp is None and tender is not None and tender.status in ev.TERMINAL and classification != "excluded":
        # Terminal-only records (fifth instruction of 27 Oct, item 4): a cancellation, award or closure of a tender that is not
        # already tracked is HISTORICAL INTELLIGENCE: the tender record keeps the evidence and its terminal status, outside the
        # actionable pipeline and the live counts. A tracked tender (an existing opportunity) moves to the terminal status.
        tx.run("signal_set_classification", id=signal_id, classification="historical_record")
        return SignalOutcome(signal_id, module, "historical_record", is_new, None, None)
    if (classification not in ("qualified_opportunity", "freight_candidate") or not has_anchor) and existing_opp is None:
        # An excluded (passenger-only) tender never becomes an opportunity; the signal keeps the evidence and the reason.
        return SignalOutcome(signal_id, module, classification, is_new, None, None)
    assert tender is not None

    # Opportunity: one per signal; later evidence (incl. contradictions) always re-evaluates it.
    delivery = sorted({g["country_code"] for g in geo if g["support"] == "supported" and g["role"] in ("delivery", "contract_territory")})
    territory_id = resolution.territory_for_country(tx, delivery[0]) if len(delivery) == 1 else None
    service_code = next((r["value"].get("service") for r in live if r["claim_type"] in TENDER_ANCHORS and r["value"]
                         and r["value"].get("service")), None)
    service_id = tx.scalar("service_by_code", code=service_code) if service_code else None
    is_airline = tx.scalar("is_airline", id=sig["subject_organisation_id"]) if sig["subject_organisation_id"] else False
    before = tx.one("opportunity_scope", id=existing_opp) if existing_opp else None
    params = dict(airline_id=sig["subject_organisation_id"] if is_airline else None,
                  organisation_id=None if is_airline else sig["subject_organisation_id"],
                  territory_id=territory_id, service_id=service_id, deadline=tender.deadline_utc, tz=tender.deadline_source_tz,
                  info=tender.deadline.to_json() if tender.deadline else None,
                  earliest=tender.deadline.earliest_utc if tender.deadline else None,
                  latest=tender.deadline.latest_utc if tender.deadline else None)
    if existing_opp is not None:   # update in place (also after a merge re-pointed it to this signal)
        tx.run("opportunity_update_from_signal", id=str(existing_opp), **params)
        opp_id = str(existing_opp)
    else:
        orow = tx.one("opportunity_upsert_from_signal2", module=module, signal=signal_id, key=sig["signal_key"], title=sig["title"], **params)
        assert orow is not None
        opp_id = str(orow["id"])
    tx.run("opportunity_geo_clear", opp=opp_id)
    tx.run("opportunity_geo_copy", opp=opp_id, signal=signal_id)
    if before is not None:
        old = StatedDeadline.from_json(before.get("deadline_info"))
        old_label = old.label() if old else (before["deadline_utc"].isoformat() if before.get("deadline_utc") else None)
        new_label = tender.deadline.label() if tender.deadline else None
        if old_label != new_label:
            tx.run("opportunity_history_add", id=opp_id, field="deadline", **{"from": old_label},
                   to=new_label or "unknown", reason="; ".join(tender.reasons) or "evidence updated", session_ref=None)
        old_status = (before.get("tender_status") or "unknown")
        if old_status != tender.status:
            tx.run("opportunity_history_add", id=opp_id, field="tender_status", **{"from": old_status}, to=tender.status,
                   reason="tender status from authoritative evidence", session_ref=None)
    else:
        tx.run("opportunity_history_add", id=opp_id, field="tender_status", **{"from": None}, to=tender.status,
               reason="opportunity created from a supported tender", session_ref=None)
    tx.run("opportunity_set_tender_status", id=opp_id, status=tender.status)
    if tender.status_conflict:
        # A status statement that could not be placed in time against another: shown to a person once per distinct conflict.
        flags = tx.scalar("opportunity_review_flags", id=opp_id) or []
        if not any(isinstance(f, dict) and f.get("flag") == "status_conflict" and f.get("reason") == tender.status_conflict for f in flags):
            tx.run("opportunity_add_review_flag", id=opp_id, flag=json.dumps([{
                "flag": "status_conflict", "from": (before or {}).get("tender_status") or "unknown", "to": tender.status,
                "reason": tender.status_conflict, "at": now.isoformat(), "version": eligibility.VALIDATION_VERSION}]))
    prev_scope = before.get("freight_scope") if before is not None else None
    if before is not None and prev_scope != freight_scope:
        tx.run("opportunity_history_add", id=opp_id, field="freight_scope", **{"from": prev_scope or "unknown"}, to=freight_scope or "unknown",
               reason=freight_reason or "freight relevance re-read from the evidence", session_ref=None)
    tx.run("opportunity_set_scope_basis", id=opp_id, scope=freight_scope, basis=tender.basis[:500] if tender.basis else None)

    # Eligibility is "known" only when a live eligibility FIELD is supported by its quote. A criterion that is unsupported,
    # uninterpreted or awaiting review never counts as established (it stays in the review queue with its reason).
    eligibility_support = {r["support"]: int(r["n"]) for r in tx.all("signal_field_support", signal=signal_id, field="eligibility")}
    eligibility_rows = [1] * eligibility_support.get("supported", 0)
    pending_elig = eligibility_support.get("review_required", 0) + eligibility_support.get("unsupported", 0)
    if existence is None:
        existence = ev.assess_claim([])
    representation = module == "airline_representation"
    checks = qual.airline_representation_checks(
        existence=existence, tender=tender,
        territory_cell_state=_territory_state(tx, sig["subject_organisation_id"] if is_airline else None, territory_id, now)
        if representation else None,
        capability_readiness="review_required",  # recomputed from the register in recompute_qualification
        eligibility_known=bool(eligibility_rows) or None, eligibility_met=None, eligibility_pending=pending_elig,
        scope_known=any(r["claim_type"] == "tender_scope" and r["stance"] == "supports" for r in live),
        freight_scope=freight_scope, freight_reason=freight_reason, geography_conflict=geo_conflict,
    )
    evidence_refs = sorted({r["document_id"] for r in live if r["claim_type"] in TENDER_ANCHORS})
    for c in checks:
        tx.run("check_upsert", id=opp_id, code=c.code, result=c.result, blocking=c.blocking, rationale=c.rationale,
               evidence=evidence_refs if c.code in ("existence", "not_expired") else [])
    # A check that no longer applies (e.g. not_expired after cancellation) is removed, not left stale.
    tx.run("checks_prune", id=opp_id, keep=[c.code for c in checks] + ["capability", "evidence_reviewed", "owner_assigned"])
    status = recompute_qualification(tx, opp_id, now=now)
    return SignalOutcome(signal_id, module, classification, is_new, opp_id, status)


def _territory_state(db: Database, airline_id: str | None, territory_id: str | None,
                     now: datetime) -> Literal["covered", "gap", "blocked", "unknown"]:
    if not airline_id or not territory_id:
        return "unknown"
    today = now.date()
    for a in db.all("agreement_cells_for", airline=airline_id, territory=territory_id):
        if a["status"] == "active" and (a["effective_from"] is None or a["effective_from"] <= today) and \
                (a["effective_to"] is None or a["effective_to"] >= today):
            return "covered"
    tps = [t for t in db.all("third_party_cells_for", airline=airline_id, territory=territory_id)
           if t["valid_to"] is None or t["valid_to"] >= today]
    if any(t["exclusivity"] == "exclusive" for t in tps):
        return "blocked"
    if any(t["exclusivity"] == "unknown" for t in tps):
        return "unknown"
    return "gap"


# ===================================================================== qualification


def _approval_basis(tx: Database, opp_id: str) -> dict[str, Any]:
    scope = tx.one("opportunity_scope", id=opp_id) or {}
    evidence = tx.all("opportunity_evidence_basis", id=opp_id)
    return {
        "operating_company_id": scope.get("operating_company_id"), "service_id": scope.get("service_id"),
        "station_airport_id": scope.get("station_airport_id"),
        "delivery_start": scope["delivery_start"].isoformat() if scope.get("delivery_start") else None,
        "required_credentials": sorted(scope.get("required_credentials") or []), "territory_id": scope.get("territory_id"),
        "deadline": (StatedDeadline.from_json(scope.get("deadline_info")).label()  # type: ignore[union-attr]
                     if scope.get("deadline_info") else (scope["deadline_utc"].isoformat() if scope.get("deadline_utc") else None)),
        "evidence": _fingerprint([[r["claim_id"], r["status"], r["review_status"]] for r in evidence]),
    }


def _refresh_derived_checks(tx: Database, opp_id: str, now: datetime) -> None:
    """Checks that depend on the clock, on the opportunity's scope or on records
    outside the evidence chain are re-derived on EVERY recomputation, so
    nothing outlives the conditions it was based on:
    - `not_expired` fails once even the latest reading of the stated deadline has passed (a date-only
      deadline is not expired until that date has ended everywhere);
    - `capability` comes from the capability register and credentials for the
      assigned company, service and station on the delivery date; clearing
      the company or service resets it to unknown;
    - `evidence_reviewed` passes only when a reviewer has confirmed or
      corrected the existence/deadline evidence (AI output is a proposal).
    """
    scope = tx.one("opportunity_scope", id=opp_id)
    if scope is None:
        return
    latest = scope.get("deadline_latest_utc") or scope.get("deadline_utc")
    if latest is not None and latest <= now:
        info = StatedDeadline.from_json(scope.get("deadline_info"))
        tx.run("check_upsert", id=opp_id, code="not_expired", result="fail", blocking=True,
               rationale=f"deadline {info.label() if info else latest.isoformat()} has passed", evidence=[])

    company, service = scope["operating_company_id"], scope["service_id"]
    if company and service:
        station = scope["station_code"]
        on: date = scope["delivery_start"] or now.date()
        recs = [CapabilityRecord(r["operating_company"], r["service_code"], r["station"], r["status"], r["valid_from"], r["valid_to"])
                for r in tx.all("capability_for_scope", company=str(company), service=str(service))]
        creds = [Credential(r["operating_company"], r["credential_type"], r["expires_on"], r["station"], r["issued_on"])
                 for r in tx.all("credentials_for_company", company=str(company), service=str(service))]
        required = sorted(set(scope["required_credentials"] or []) |
                          {r["credential_type"] for r in tx.all("service_requirements", service=str(service))})
        company_name = tx.scalar("company_name", id=str(company))
        service_code = tx.scalar("service_code", id=str(service))
        readiness = capability_readiness(recs, creds, operating_company=company_name, service_code=service_code, station=station,
                                         on=on, required_credentials=required)
        where = f"at {station}" if station else "company level (no delivery station set)"
        when = f"on {on.isoformat()}" + ("" if scope["delivery_start"] else " (delivery date unknown: today used)")
        if readiness.readiness == "ready":
            result, why = "pass", f"verified {service_code} capability {where} {when}" + (f"; credentials current: {', '.join(required)}" if required else "")
        elif readiness.readiness == "blocked":
            result, why = "fail", "; ".join(readiness.blockers) + f" ({where}, {when})"
        else:
            result, why = "unknown", "; ".join(readiness.unknowns) + f" ({where}, {when})"
        tx.run("check_upsert", id=opp_id, code="capability", result=result, blocking=True, rationale=why, evidence=[])
    else:
        missing = [n for n, v in (("operating company", company), ("service", service)) if not v]
        tx.run("check_upsert", id=opp_id, code="capability", result="unknown", blocking=True,
               rationale=f"{' and '.join(missing)} not assigned", evidence=[])

    if scope["signal_id"]:
        ev_rows = tx.all("opportunity_evidence_basis", id=opp_id)
        material = [r for r in ev_rows if r["claim_type"] in TENDER_ANCHORS | {"tender_deadline", "tender_status"}
                    and r["review_status"] != "rejected"]
        pending = [r for r in material if r["review_status"] == "proposed"]
        withdrawn = tx.all("signal_withdrawn_verdicts", signal=str(scope["signal_id"]))
        if withdrawn:
            tx.run("check_upsert", id=opp_id, code="evidence_reviewed", result="unknown", blocking=True,
                   rationale=f"{len(withdrawn)} eligibility verdict(s) withdrawn by re-check under validation rules v"
                             f"{eligibility.VALIDATION_VERSION}; reviewer confirmation needed", evidence=[])
        elif not material:
            tx.run("check_upsert", id=opp_id, code="evidence_reviewed", result="unknown", blocking=True,
                   rationale="no tender evidence to review", evidence=[])
        elif pending:
            tx.run("check_upsert", id=opp_id, code="evidence_reviewed", result="unknown", blocking=True,
                   rationale=f"{len(pending)} AI-proposed claim(s) await reviewer confirmation", evidence=[])
        else:
            tx.run("check_upsert", id=opp_id, code="evidence_reviewed", result="pass", blocking=True,
                   rationale="existence and deadline evidence confirmed by a reviewer", evidence=[])


def recompute_qualification(tx: Database, opp_id: str, checks: list[qual.Check] | None = None,
                            now: datetime | None = None, session_ref: str | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    _refresh_derived_checks(tx, opp_id, now)
    checks = [qual.Check(r["check_code"], r["result"], r["blocking"], r["rationale"]) for r in tx.all("opportunity_checks", id=opp_id)]
    overrides = [qual.Override(r["check_code"], r["override_result"], r["reason"], r["created_at"], r["expires_at"], r["revoked_at"] is not None)
                 for r in tx.all("opportunity_overrides", id=opp_id)]
    effective = qual.apply_overrides(checks, overrides, now)
    computed = qual.qualification_status(effective)
    current = tx.one("opportunity_lock", id=opp_id)
    assert current is not None
    prev = current["qualification_status"]
    new, reason = computed, "recomputed from checks"
    if prev == "approved_for_pursuit" and computed == "ready_for_review":
        basis = _approval_basis(tx, opp_id)
        recorded = current.get("approval_basis") or {}
        changed = sorted(k for k in basis if recorded.get(k) != basis[k])
        if changed:
            reason = f"approval withdrawn: {', '.join(changed)} changed since approval; re-approval required"
        else:
            new = prev  # approval stands while every check still passes on the same basis
    elif prev == "approved_for_pursuit":
        reason = "approval withdrawn: a check no longer passes"
    if new != prev:
        tx.run("opportunity_set_qual", id=opp_id, to=new)
        tx.run("opportunity_history_add", id=opp_id, field="qualification_status", **{"from": prev}, to=new,
               reason=reason, session_ref=session_ref)
    from . import prioritisation_service

    prioritisation_service.store(tx, opp_id, {c.code: c.result for c in effective}, now)
    return new


def approval_basis(tx: Database, opp_id: str) -> dict[str, Any]:
    return _approval_basis(tx, opp_id)


def recompute_open_opportunities(tx: Database, now: datetime | None = None) -> int:
    """After a capability, credential or agreement change: every live
    opportunity is re-evaluated (approvals included)."""
    n = 0
    for r in tx.all("opportunities_live"):
        recompute_qualification(tx, str(r["id"]), now=now)
        n += 1
    return n


def _title(prep: _Prepared) -> str:
    who = prep.subject_label or "Unknown organisation"
    where = ", ".join(sorted({c for c, role, s in prep.geography if s == "supported" and role in SCOPE_ROLES}))
    kind = {"route_launch": "route launch", "route_suspension": "route suspension", "gssa_tender": "GSSA tender",
            "service_tender": f"{(prep.service or 'service').replace('_', ' ').lower()} tender",
            "representation_change": "representation change", "tcm_signal": "TCM signal", "capacity_statement": "capacity statement",
            "partnership": "partnership"}.get(prep.proposal.claim_type, prep.proposal.claim_type.replace("_", " "))
    ref = f" ({prep.tender_ref})" if prep.tender_ref else ""
    lane = f" {prep.lane}" if prep.lane else ""
    return f"{who}: {kind}{lane} {where}{ref}".replace("  ", " ").strip()
