"""Reviewer workflow (directive §3, §6, §12): add, correct, confirm and reject
claims; resolve rejected extraction output; decide merge candidates;
re-run extraction for a document.

Every action is by the shared authenticated session, audited, and followed
by re-evaluation of the affected signals and opportunities, so classification,
tender state and qualification always reflect the reviewed evidence.
Human-entered fields are validated exactly like extracted ones: a field is a
fact only when its own verbatim quote states it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ..config import Settings
from ..domain import content as ct
from ..domain import retrieval
from ..domain.field_validation import FieldClaim
from ..repo.db import Database
from . import ingestion as ing
from . import reading
from ..domain import sections as sec
from .audit import RequestMeta, audit


class ReviewRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _reevaluate_signals_of_claim(tx: Database, claim_id: str, now: datetime) -> list[ing.SignalOutcome]:
    return [ing.evaluate_signal(tx, r["signal_id"], now) for r in tx.all("signals_of_claim", claim=claim_id)]


def confirm_claim(db: Database, claim_id: str, note: str | None, meta: RequestMeta) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with db.transaction() as tx:
        c = tx.one("claim_get", id=claim_id)
        if c is None:
            raise ReviewRejected(404, "claim not found")
        if c["review_status"] in ("rejected", "corrected"):
            raise ReviewRejected(409, f"claim was {c['review_status']}; add a new claim instead")
        tx.run("claim_set_review", id=claim_id, review="confirmed", note=note)
        outcomes = _reevaluate_signals_of_claim(tx, claim_id, now)
        audit(tx, "claim_confirmed", meta, entity_type="claim", entity_id=claim_id)
    return {"claim_id": claim_id, "review_status": "confirmed", "signals": [o.__dict__ for o in outcomes]}


def reject_claim(db: Database, claim_id: str, note: str, meta: RequestMeta) -> dict[str, Any]:
    if len((note or "").strip()) < 5:
        raise ReviewRejected(422, "give a reason (at least 5 characters)")
    now = datetime.now(timezone.utc)
    with db.transaction() as tx:
        c = tx.one("claim_get", id=claim_id)
        if c is None:
            raise ReviewRejected(404, "claim not found")
        tx.run("claim_set_review", id=claim_id, review="rejected", note=note)
        ing.refresh_claim_status(tx, claim_id)
        outcomes = _reevaluate_signals_of_claim(tx, claim_id, now)
        audit(tx, "claim_rejected", meta, entity_type="claim", entity_id=claim_id)
    return {"claim_id": claim_id, "review_status": "rejected", "signals": [o.__dict__ for o in outcomes]}


def _proposal(claim_type: str, quote: str, fields: dict[str, dict[str, str]], stance: str, tz: str | None) -> ing.ClaimProposal:
    return ing.ClaimProposal(claim_type, quote, {k: FieldClaim(v.get("value", ""), v.get("quote")) for k, v in fields.items()
                                                  if v.get("value")}, assessed_by="human", stance=stance, deadline_timezone=tz)  # type: ignore[arg-type]


def _with_document_anchor(tx: Database, document_id: str, prop: ing.ClaimProposal) -> tuple[list[ing.ClaimProposal], set[str]]:
    """A reviewer's deadline/status/scope/eligibility claim that cites no reference belongs to the tender the document
    announces: the stored anchor is re-applied with it (idempotent, same claim key), exactly as later sections of a
    long document are read (services/reading.py). Returns the proposals and the anchor's existing claim ids."""
    if prop.claim_type not in ing.TENDER_FOLLOWERS:
        return [prop], set()
    for a in tx.all("document_anchor_claims", id=document_id):
        flds = {f["field"]: FieldClaim(f["value"], f["quote"]) for f in (a["fields"] or []) if f.get("value")}
        return [ing.ClaimProposal(a["claim_type"], a["quote"] or "", flds, assessed_by=a["assessed_by"] or "ai_proposed"), prop], {a["claim_id"]}
    return [prop], set()


def _review_text(db: Database, document_id: str, settings: Settings | None, fetch: Any) -> str:
    """Full document text for validating a reviewer's claim (document-wide negation and contradiction checks need all
    of it): the retained body, else the page fetched again and checked against the stored hash. Never the excerpt."""
    doc = db.one("document_review_get", id=document_id)
    if doc is None:
        raise ReviewRejected(404, "document not found")
    if doc.get("body_text"):
        return str(doc["body_text"])
    if settings is None:
        raise ReviewRejected(409, "the full text is not retained for this source; it must be fetched again to check a claim")
    return _full_text(doc, settings, fetch)[0]


def _partly_read(doc: dict[str, Any]) -> bool:
    p = sec.Progress.from_json(doc.get("read_progress"))
    return p is not None and not p.complete


def add_claim(db: Database, document_id: str, *, claim_type: str, quote: str, fields: dict[str, dict[str, str]],
              stance: str = "supports", deadline_timezone: str | None = None, meta: RequestMeta,
              settings: Settings | None = None, fetch: Any = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    text = _review_text(db, document_id, settings, fetch)
    with db.transaction() as tx:
        doc = tx.one("document_review_get", id=document_id)
        if doc is None:
            raise ReviewRejected(404, "document not found")
        prop = _proposal(claim_type, quote, fields, stance, deadline_timezone)
        props, anchor_ids = _with_document_anchor(tx, document_id, prop)
        claim_ids, outcomes, rejected = ing.apply_claims(tx, document_id, doc["family_key"] or document_id, text, props, now=now)
        claim_ids = [c for c in claim_ids if c not in anchor_ids]
        # A reviewer's claim does not make a partly read document "read": it stays incomplete until every section is read.
        if doc["extraction_status"] in ("not_connected", "budget_refused", "failed", "pending", "no_claims") and claim_ids \
                and not _partly_read(doc):
            tx.run("document_set_extraction", id=document_id, status="manual", detail="claims added by a reviewer")
        audit(tx, "claim_added", meta, entity_type="source_document", entity_id=document_id,
              detail={"claim_type": claim_type, "accepted": bool(claim_ids)})
        fields_out = tx.all("claim_fields_for", claim=claim_ids[0], doc=document_id) if claim_ids else []
    return {"claim_ids": claim_ids, "rejected": rejected, "fields": fields_out, "signals": [o.__dict__ for o in outcomes]}


def correct_claim(db: Database, claim_id: str, *, document_id: str, claim_type: str | None, quote: str | None,
                  fields: dict[str, dict[str, str]], note: str, meta: RequestMeta, settings: Settings | None = None,
                  fetch: Any = None) -> dict[str, Any]:
    """A correction replaces the claim: the original is marked `corrected`
    (kept, excluded from evidence) and a reviewer claim is created on the
    same document with the corrected fields, validated against the text."""
    if len((note or "").strip()) < 5:
        raise ReviewRejected(422, "give a reason for the correction (at least 5 characters)")
    now = datetime.now(timezone.utc)
    text = _review_text(db, document_id, settings, fetch)
    with db.transaction() as tx:
        c = tx.one("claim_get", id=claim_id)
        if c is None:
            raise ReviewRejected(404, "claim not found")
        doc = tx.one("document_review_get", id=document_id)
        if doc is None or tx.scalar("claim_has_document", claim=claim_id, doc=document_id) is None:
            raise ReviewRejected(422, "the correction must be made against a document that evidences this claim")
        current = {r["field"]: {"value": r["value"], "quote": r["quote"] or ""}
                   for r in tx.all("claim_fields_for", claim=claim_id, doc=document_id) if r["field"] != "opportunity_type"}
        current.update({k: v for k, v in fields.items() if v.get("value")})
        for k, v in fields.items():
            if not v.get("value"):
                current.pop(k, None)   # an emptied field is removed
        prop = _proposal(claim_type or c["claim_type"], quote or c["evidence_quote"] or "", current,
                         c["stance"] or "supports", c["deadline_source_tz"])
        tx.run("claim_set_review", id=claim_id, review="corrected", note=note)
        tx.run("claim_evidence_exclude", claim=claim_id, doc=document_id)
        ing.refresh_claim_status(tx, claim_id)
        props, anchor_ids = _with_document_anchor(tx, document_id, prop)
        new_ids, outcomes, rejected = ing.apply_claims(tx, document_id, doc["family_key"] or document_id, text, props, now=now)
        new_ids = [c for c in new_ids if c not in anchor_ids]
        old = _reevaluate_signals_of_claim(tx, claim_id, now)
        audit(tx, "claim_corrected", meta, entity_type="claim", entity_id=claim_id,
              detail={"document_id": document_id, "replacement": new_ids[0] if new_ids else None})
    return {"claim_id": claim_id, "replacement_claim_ids": new_ids, "rejected": rejected,
            "signals": [o.__dict__ for o in outcomes + old]}


def resolve_rejection(db: Database, rejection_id: str, status: str, note: str, meta: RequestMeta) -> None:
    if status not in ("resolved", "dismissed"):
        raise ReviewRejected(422, "status must be resolved or dismissed")
    if db.scalar("rejection_resolve", id=rejection_id, status=status, note=note) is None:
        raise ReviewRejected(404, "open rejection not found")
    audit(db, f"extraction_rejection_{status}", meta, entity_type="extraction_rejection", entity_id=rejection_id)


def _full_text(doc: dict[str, Any], settings: Settings, fetch: Any) -> tuple[str, Any]:
    """The document's COMPLETE text: the retained body, or (when the source does not permit retention) the page
    fetched again and checked against the stored content hash. Never the stored excerpt: extracting from an
    excerpt would mark a partly read document as checked."""
    if doc.get("body_text"):
        return doc["body_text"], None
    url = doc.get("original_url") or doc.get("canonical_url")
    fetch = fetch or (lambda u: retrieval.fetch(u, allow_private_hosts=frozenset(settings.retrieval_allow_private_hosts)))
    try:
        fr = fetch(url)
        page = ct.extract(fr.body, fr.content_type, fr.final_url)
    except (retrieval.RetrievalBlocked, retrieval.RetrievalFailed, ct.ContentUnavailable) as exc:
        raise ReviewRejected(502, f"the full text is not retained for this source and the page could not be fetched again: {exc}") from exc
    if ing.ev.content_hash(page.text) != doc.get("content_hash"):
        raise ReviewRejected(409, "the page has changed since it was stored; run the discovery search again to read the current version")
    return page.text, (page.page_of if page.page_starts else None)


def extract_document(db: Database, settings: Settings, document_id: str, meta: RequestMeta,
                     approve_additional_usd: Decimal | None = None, *, fetch: Any = None, transport: Any = None) -> dict[str, Any]:
    """Run the budget-controlled extractor for one stored document now: a document left unextracted (AI not
    connected, budget refused) or only partly read. Reading continues at the first unread section.

    A document found by a discovery run is charged to that run's cumulative ceiling, like the run's own calls
    and retries. When that ceiling is reached the reviewer must explicitly approve an additional amount
    (`approve_additional_usd`), which raises the run's ceiling by exactly that much and is audited."""
    doc = db.one("document_review_get", id=document_id)
    if doc is None:
        raise ReviewRejected(404, "document not found")
    run_id = db.scalar("document_run", id=document_id)
    run_id = str(run_id) if run_id else None
    if approve_additional_usd is not None:
        if run_id is None:
            raise ReviewRejected(422, "this document is not part of a discovery run; only the monthly budget applies")
        if approve_additional_usd <= 0 or approve_additional_usd > Decimal("100"):
            raise ReviewRejected(422, "the additional approval must be between 0 and 100 USD")
        with db.transaction() as tx:
            new_cap = tx.scalar("run_raise_cap", id=run_id, amount=approve_additional_usd)
            audit(tx, "run_budget_raised", meta, entity_type="discovery_run", entity_id=run_id,
                  detail={"additional_usd": str(approve_additional_usd), "new_cap_usd": str(new_cap), "document_id": document_id})
    text, page_of = _full_text(doc, settings, fetch)
    # A person asked to continue: sections that failed before are tried again (the failure count starts over).
    stored = dict(doc.get("read_progress") or {}) or None
    if stored:
        stored["failures"] = {}
    now = datetime.now(timezone.utc)
    ro = reading.read_document(db, settings, document_id, doc["family_key"] or document_id, text, job_id=None, run_id=run_id, now=now,
                               transport=transport, page_of=page_of, stored_progress=stored)
    audit(db, "document_extracted", meta, entity_type="source_document", entity_id=document_id,
          detail={"status": ro.status, "claims": ro.claims, "sections": ro.progress.to_json()["done"], "of": ro.progress.total,
                  "calls": ro.calls})
    return {"status": ro.status, "detail": ro.detail, "budget_scope": ro.budget_scope, "claims": ro.claims, "rejected": ro.rejected,
            "read": {"sections_read": len(set(ro.progress.done)), "sections_total": ro.progress.total, "complete": ro.progress.complete},
            "signals": [{"signal_id": s, "is_new": n} for s, n in ro.signals]}


def propose_merge(db: Database, opportunity_id: str, other_opportunity_id: str, reason: str, meta: RequestMeta) -> dict[str, Any]:
    """A reviewer proposes that two opportunities are the same tender (e.g. an amendment that arrived
    without naming the airline created its own record). Nothing merges until the pair is decided."""
    if opportunity_id == other_opportunity_id:
        raise ReviewRejected(422, "choose two different opportunities")
    if len((reason or "").strip()) < 5:
        raise ReviewRejected(422, "give a reason (at least 5 characters)")
    with db.transaction() as tx:
        a = tx.scalar("opportunity_signal", id=opportunity_id)
        b = tx.scalar("opportunity_signal", id=other_opportunity_id)
        if a is None or b is None:
            raise ReviewRejected(404, "both opportunities must exist and come from discovered evidence")
        sa, sb = tx.one("signal_get", id=str(a)), tx.one("signal_get", id=str(b))
        if sa is None or sb is None or sa["merged_into_id"] or sb["merged_into_id"]:
            raise ReviewRejected(409, "one of the records was already merged")
        if sa["tender_ref"] and sb["tender_ref"] and ing.norm_ref(sa["tender_ref"]) != ing.norm_ref(sb["tender_ref"]):
            raise ReviewRejected(409, "the two tenders carry different references and cannot be the same tender")
        left, right = sorted([str(a), str(b)])
        tx.run("merge_candidate_add", entity_type="signal", left=left, right=right, score=None, reason=f"proposed by a reviewer: {reason}")
        cid = tx.scalar("merge_candidate_find", entity_type="signal", left=left, right=right)
        audit(tx, "merge_proposed", meta, entity_type="signal", entity_id=left, detail={"other": right})
    return {"candidate_id": str(cid)}


def decide_merge(db: Database, candidate_id: str, decision: str, note: str, meta: RequestMeta) -> dict[str, Any]:
    if decision not in ("merged", "kept_separate"):
        raise ReviewRejected(422, "decision must be merged or kept_separate")
    if len((note or "").strip()) < 5:
        raise ReviewRejected(422, "give a reason (at least 5 characters)")
    now = datetime.now(timezone.utc)
    with db.transaction() as tx:
        mc = tx.one("merge_candidate_lock", id=candidate_id)
        if mc is None or mc["status"] != "open":
            raise ReviewRejected(404, "open merge candidate not found")
        left, right = str(mc["left_id"]), str(mc["right_id"])
        if decision == "merged":
            if mc["entity_type"] == "signal":
                # The survivor is the signal that already carries the opportunity (else the older one),
                # so the opportunity's history, scope, owner and approval trail stay with it.
                a, b = tx.one("signal_merge_info", id=left), tx.one("signal_merge_info", id=right)
                if a is None or b is None:
                    raise ReviewRejected(409, "one of the signals no longer exists")
                ordered = sorted([a, b], key=lambda x: (x["opp"] is None, x["created_at"]))
                _merge_signals(tx, ordered[0]["id"], ordered[1]["id"], note, meta, now)
            else:
                _merge_organisations(tx, left, right)
        tx.run("merge_candidate_decide", id=candidate_id, status=decision, note=note)
        audit(tx, f"merge_{decision}", meta, entity_type=mc["entity_type"], entity_id=left, detail={"other": right})
    return {"id": candidate_id, "status": decision}


def _merge_signals(tx: Database, survivor: str, merged: str, note: str, meta: RequestMeta, now: datetime) -> None:
    a, b = tx.one("signal_get", id=survivor), tx.one("signal_get", id=merged)
    if a is None or b is None or a["merged_into_id"] or b["merged_into_id"]:
        raise ReviewRejected(409, "one of the signals no longer exists or was already merged")
    if a["tender_ref"] and b["tender_ref"] and a["tender_ref"] != b["tender_ref"]:
        raise ReviewRejected(409, "the two tenders carry different references and cannot be the same tender")
    tx.run("signal_adopt_identifiers", id=survivor, src=merged)   # later evidence citing B's reference finds the survivor
    tx.run("signal_claims_move", src=merged, dst=survivor)
    tx.run("signal_geo_move", src=merged, dst=survivor)
    tx.run("signal_mark_merged", id=merged, into=survivor)
    opp_a, opp_b = tx.scalar("opportunity_by_signal", signal=survivor), tx.scalar("opportunity_by_signal", signal=merged)
    if opp_b is not None and opp_a is None:
        tx.run("opportunity_repoint_signal", id=str(opp_b), signal=survivor)
    elif opp_b is not None and opp_a is not None:
        tx.run("opportunity_mark_merged", id=str(opp_b), into=str(opp_a))
        tx.run("opportunity_history_add", id=str(opp_b), field="merge", **{"from": None}, to=str(opp_a),
               reason=f"merged into another opportunity for the same tender: {note}", session_ref=meta.session_ref)
    ing.evaluate_signal(tx, survivor, now)


def _merge_organisations(tx: Database, survivor: str, merged: str) -> None:
    if int(tx.scalar("organisation_import_refs", id=merged) or 0) > 0:
        raise ReviewRejected(409, "this organisation is referenced by imported records (bookings, quotes, agreements); "
                                  "correct it in the source register and re-import instead")
    if tx.scalar("is_airline", id=merged):
        tx.run("airline_ensure", org=survivor, iata=None)
        tx.run("organisation_merge_airline_refs", src=merged, dst=survivor)
    tx.run("organisation_merge_refs", src=merged, dst=survivor)
    tx.run("organisation_mark_merged", id=merged, into=survivor)
