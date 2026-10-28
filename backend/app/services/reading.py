"""Reading a whole stored document with the budget-controlled extractor, section by section (amendments
of 26 Oct 2026, item 1).

- The full text is split into overlapping sections that together cover every character (domain/sections.py).
- Each section is one extraction call, reserved against the same budgets as before (run ceiling, monthly cap,
  kill switch). Claims are applied to the document as each section finishes, with their location in the
  full text ("chars a-b", and the page for PDFs) recorded on the evidence.
- Progress is saved on the document after every section (`source_documents.read_progress`). A run that stops
  (budget, provider failure, cancellation, crash) leaves the document `incomplete`, never `no_claims`, and the
  next run or a reviewer's "Continue reading" resumes at the first unread section. If the text has changed
  since, reading starts again from the beginning.
- Validation always sees the FULL document text, so document-wide checks (contradictions, negation in context)
  are not limited to one section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from ..ai import extraction as ai
from ..config import Settings
from ..domain import sections as sec
from ..domain.ai_guard import DocumentTooLong
from ..domain.field_validation import FieldClaim
from ..domain.identity import TENDER_ANCHORS, TENDER_FOLLOWERS
from ..repo.db import Database
from . import ingestion as ing


@dataclass
class ReadOutcome:
    status: str                      # extracted | partial | no_claims | incomplete | not_connected | budget_refused | failed
    detail: str
    progress: sec.Progress
    claims: int = 0
    rejected: int = 0
    signals: list[tuple[str, bool]] = field(default_factory=list)
    budget_scope: str | None = None  # why reading stopped, when it did: "run" | "month"
    stop_status: str | None = None   # extractor status that stopped reading
    calls: int = 0
    gave_up: bool = False            # a section failed MAX_SECTION_FAILURES times; reading stopped and needs a person


def _location(full_text: str, quote: str, section: sec.Section, page_of: Callable[[int], int | None] | None) -> str | None:
    span = sec.locate_quote(full_text, quote, section.start)
    if span is None:
        return f"section {section.index + 1}"
    a, b = span
    page = page_of(a) if page_of else None
    return (f"page {page}, " if page else "") + f"chars {a}-{b}"


MAX_SECTION_FAILURES = 3


def read_document(db: Database, settings: Settings, doc_id: str, family_key: str, full_text: str, *, job_id: str | None,
                  run_id: str | None, now: datetime, transport: Any = None, page_of: Callable[[int], int | None] | None = None,
                  stored_progress: dict | None = None, on_section: Callable[[], None] | None = None,
                  page_starts: list[int] | None = None) -> ReadOutcome:
    sections = sec.split(full_text, ai.SECTION_BYTES)
    fp = sec.text_fingerprint(full_text)
    progress = sec.Progress.from_json(stored_progress)
    if progress is None or progress.fingerprint != fp or progress.section_bytes != ai.SECTION_BYTES or progress.total != len(sections):
        progress = sec.Progress(len(sections), [], ai.SECTION_BYTES, fp, {}, page_starts)
    if page_starts and not progress.page_starts:
        progress.page_starts = page_starts
    if page_of is None and progress.page_starts:
        starts = progress.page_starts

        def page_of(offset: int) -> int | None:
            return sum(1 for st in starts if st <= offset) or None
    out = ReadOutcome("incomplete", "", progress)
    # The tender a document announces anchors deadline/status/eligibility claims found in LATER sections, also when
    # reading resumes in a later run: anchors already stored for this document are carried into every section.
    anchors: list[ing.ClaimProposal] = []
    for a in db.all("document_anchor_claims", id=doc_id):
        flds = {f["field"]: FieldClaim(f["value"], f["quote"]) for f in (a["fields"] or []) if f.get("value")}
        anchors.append(ing.ClaimProposal(a["claim_type"], a["quote"] or "", flds, assessed_by=a["assessed_by"] or "ai_proposed"))
    any_partial = False
    claims_total = 0
    kwargs = {"transport": transport} if transport else {}
    for i in progress.remaining():
        s = sections[i]
        try:
            outcome = ai.extract_claims(db, settings, s.text, job_id=job_id, run_id=run_id, **kwargs)
        except DocumentTooLong as exc:   # cannot happen with SECTION_BYTES; recorded, never truncated
            outcome = ai.ExtractionOutcome("failed", detail=f"section {i + 1} could not be prepared: {exc}")
        if outcome.status in ("not_connected", "budget_refused", "failed") and not outcome.claims:
            out.stop_status, out.budget_scope = outcome.status, outcome.budget_scope
            out.detail = outcome.detail or outcome.status
            if outcome.status == "failed":
                failures = progress.failures if progress.failures is not None else {}
                failures[i] = failures.get(i, 0) + 1
                progress.failures = failures
                if failures[i] >= MAX_SECTION_FAILURES:
                    out.gave_up = True
                    out.detail = (f"section {i + 1} of {progress.total} failed {failures[i]} times ({outcome.detail}); reading stopped "
                                  "and needs a person — the document is NOT fully checked")
            if outcome.call_id is not None:
                out.calls += 1
            for idx, reason, raw in outcome.rejected:
                db.run("rejection_add", doc=doc_id, call=outcome.call_id, idx=idx if idx >= 0 else None,
                       reason=f"section {i + 1}: {reason}", raw=raw if isinstance(raw, dict) else {"raw": str(raw)[:4000]})
            break
        out.calls += 1
        proposals = [ing.ClaimProposal(c.claim_type, c.quote, {k: FieldClaim(v, q) for k, (v, q) in c.fields.items()},
                                       assessed_by="ai_proposed", stance=c.stance,  # type: ignore[arg-type]
                                       deadline_timezone=c.deadline_timezone, summary=c.summary, raw=c.raw,
                                       location=_location(full_text, c.quote, s, page_of)) for c in outcome.claims]
        if proposals and not any(p.claim_type in TENDER_ANCHORS for p in proposals) \
                and any(p.claim_type in TENDER_FOLLOWERS for p in proposals) and anchors:
            proposals = anchors[:1] + proposals          # re-applying a stored anchor is idempotent (same claim key)
        anchors += [p for p in proposals if p.claim_type in TENDER_ANCHORS and p not in anchors]
        with db.transaction() as tx:
            claim_ids, sig_outcomes, rejected = ing.apply_claims(tx, doc_id, family_key, full_text, proposals, now=now)
            for idx, reason, raw in outcome.rejected:
                tx.run("rejection_add", doc=doc_id, call=outcome.call_id, idx=idx if idx >= 0 else None,
                       reason=f"section {i + 1}: {reason}", raw=raw if isinstance(raw, dict) else {"raw": str(raw)[:4000]})
            if i == 0 and (outcome.summary_en or outcome.language):
                tx.run("document_set_summary", id=doc_id, summary=outcome.summary_en,
                       translated=bool(outcome.summary_en and (outcome.language or "en") != "en"), language=outcome.language)
            progress.done.append(i)
            tx.run("document_set_progress", id=doc_id, progress=progress.to_json())
        claims_total += len(claim_ids)
        out.rejected += len(rejected) + len(outcome.rejected)
        any_partial = any_partial or outcome.status == "partial" or bool(rejected)
        out.signals += [(o.signal_id, o.is_new) for o in sig_outcomes]
        if on_section:
            on_section()
    out.claims = claims_total
    out.progress = progress
    if progress.complete:
        prior = int(db.scalar("document_claim_count", id=doc_id) or 0)
        open_rejections = int((db.one("document_claim_state", id=doc_id) or {}).get("rejected") or 0)
        # partial when ANY section (this run or an earlier one) left rejected claims open in the review queue
        out.status = "partial" if (any_partial or open_rejections) else ("extracted" if (claims_total or prior) else "no_claims")
        out.detail = f"read all {progress.total} section(s); {claims_total} claim(s) added, {out.rejected} rejected"
        db.run("document_check_add", doc=doc_id, check_type="relevance", result="pass" if (claims_total or prior) else "fail",
               detail=f"complete read: {progress.total} section(s)")
    elif out.gave_up:
        out.status = "failed"
        out.detail = f"{progress.label()}; {out.detail}"
    elif progress.done:
        out.status = "incomplete"
        out.detail = f"{progress.label()}; stopped: {out.detail}"
    else:
        out.status = out.stop_status or "incomplete"
    db.run("document_set_extraction", id=doc_id, status=out.status, detail=out.detail[:1000])
    db.run("document_set_progress", id=doc_id, progress=progress.to_json())
    return out
