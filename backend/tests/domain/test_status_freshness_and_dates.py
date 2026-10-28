"""27 Oct 2026, fourth instruction, items 1, 2 and 4: status freshness, truthful publication dates and the remaining
classification rules, at rule level. The same behaviour through ingestion, the database, briefing, live counts, country
results, export and the v6 re-check is in tests/integration/test_status_freshness_pipeline.py."""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import content, identity
from app.domain import evidence as ev
from app.domain import publication as pub
from app.domain.deadlines import StatedDeadline
from app.domain.field_validation import FieldClaim, validate_claim

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def obs(doc: str, days_ago: int | None, status: str | None = None, *, deadline: StatedDeadline | None = None, retrieved_days_ago: int = 0):
    published = NOW - timedelta(days=days_ago) if days_ago is not None else None
    return ev.TenderObservation(doc, f"fam-{doc}", "issuer", "official_portal", published, status, deadline=deadline,  # type: ignore[arg-type]
                                retrieved_at=NOW - timedelta(days=retrieved_days_ago))


# ------------------------------------------------------------------ item 1: the reported defect, reproduced
def test_the_reported_defect_an_old_open_assertion_stays_unverified_when_a_new_status_less_document_arrives():
    old_open = obs("a", 365, "open")
    assert ev.resolve_tender([old_open], NOW).status == "unverified"
    today_no_status = obs("b", 0, None)
    state = ev.resolve_tender([old_open, today_no_status], NOW, announced=True)
    assert state.status == "unverified" and not state.actionable
    assert state.status_verified_at == NOW - timedelta(days=365) and state.status_document_id == "a"
    assert state.published_at == NOW                         # the newest document is today's ...
    assert "365 days ago" in state.basis and "do not renew" in state.basis   # ... and it is not the status's date


@pytest.mark.parametrize("kind", ["eligibility", "contact", "deadline-only clarification"])
def test_new_eligibility_contact_or_deadline_documents_never_renew_an_old_open_assertion(kind):
    # Each of these documents is a tender observation that states no status; only a statement of the status renews it.
    newer = obs(kind, 1, None)
    assert ev.resolve_tender([obs("a", 200, "open"), newer], NOW).status == "unverified"


def test_a_genuine_explicit_reconfirmation_renews_the_status():
    state = ev.resolve_tender([obs("a", 365, "open"), obs("b", 3, "open")], NOW)
    assert state.status == "open" and state.status_document_id == "b"
    assert state.status_asserted_at == NOW - timedelta(days=365) and state.status_verified_at == NOW - timedelta(days=3)
    assert "reconfirmed" in state.basis


@pytest.mark.parametrize("terminal", ["awarded", "cancelled", "closed"])
def test_terminal_statuses_are_preserved(terminal):
    assert ev.resolve_tender([obs("a", 365, "open"), obs("b", 2, terminal)], NOW).status == terminal
    assert ev.resolve_tender([obs("a", 365, terminal), obs("b", 2, None)], NOW).status == terminal


def test_a_stated_future_closing_date_still_decides_and_a_passed_one_expires():
    future = StatedDeadline.from_json({"precision": "date", "day": "2027-01-20", "earliest_utc": "2027-01-19T10:00:00+00:00",
                                       "latest_utc": "2027-01-21T12:00:00+00:00"})
    past = StatedDeadline.from_json({"precision": "date", "day": "2026-01-10", "earliest_utc": "2026-01-09T10:00:00+00:00",
                                     "latest_utc": "2026-01-11T12:00:00+00:00"})
    assert ev.resolve_tender([obs("a", 200, "open", deadline=future)], NOW).status == "open"
    assert ev.resolve_tender([obs("a", 300, "open"), obs("b", 1, None, deadline=past)], NOW).status == "expired"


def test_unknown_publication_date_gives_no_age_and_retrieval_never_verifies_status():
    state = ev.resolve_tender([obs("a", None, "open", retrieved_days_ago=0)], NOW)
    assert state.status == "unverified" and not state.status_date_known
    assert "no usable publication date" in state.basis and "does not verify" in state.basis
    assert "days ago" not in state.basis
    # a recent, dated open statement is open
    assert ev.resolve_tender([obs("a", 10, "open")], NOW).status == "open"


def test_announced_and_historical_follow_publication_not_retrieval():
    assert ev.resolve_tender([obs("a", None, None)], NOW, announced=True).status == "announced"
    old = ev.resolve_tender([obs("a", 1200, None)], NOW, announced=True)
    assert old.status == "historical" and "1200 days ago" in old.basis
    assert "-1 days" not in old.basis


# ------------------------------------------------------------------ item 2: publication dates
def _pdf(created: str | None) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    SimpleDocTemplate(buf).build([Paragraph("Request for proposal: cargo GSSA, Mozambique. Reference SAW-CGO-2022-4.", getSampleStyleSheet()["Normal"])])
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(buf.getvalue())))
    w.add_metadata({"/Title": "RFP"} | ({"/CreationDate": created} if created else {}))
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def test_pdf_publication_date_is_read_from_its_metadata():
    page = content.extract(_pdf("D:20220314090000Z"), "application/pdf", "https://x.example/a.pdf")
    assert page.published_at == datetime(2022, 3, 14, 9, tzinfo=timezone.utc) and page.published_source == "pdf_metadata"
    res = pub.resolve([(page.published_source, page.published_at)], NOW)
    assert res.published_at == page.published_at and res.source == "pdf_metadata" and res.flag is None


def test_pdf_without_a_date_stays_unknown():
    page = content.extract(_pdf(None), "application/pdf", "https://x.example/b.pdf")
    assert page.published_at is None
    res = pub.resolve([(page.published_source or "page", page.published_at), ("document_text", pub.stated_in_text(page.text))], NOW)
    assert res.published_at is None and res.source is None and res.flag is None and "no publication date" in (res.note or "")


def test_pdf_generated_on_download_is_not_a_publication_date():
    res = pub.resolve([("pdf_metadata", NOW - timedelta(hours=3))], NOW)
    assert res.published_at is None and "generated on download" in (res.note or "")


def test_future_dates_are_flagged_and_not_used():
    res = pub.resolve([("page", NOW + timedelta(days=120))], NOW)
    assert res.published_at is None and res.flag == "future"
    # a day's tolerance for time zones
    assert pub.resolve([("page", NOW + timedelta(hours=10))], NOW).flag is None


def test_inconsistent_dates_are_flagged_and_left_unknown():
    res = pub.resolve([("page", NOW - timedelta(days=6)), ("document_text", datetime(2024, 3, 12, tzinfo=timezone.utc))], NOW)
    assert res.published_at is None and res.flag == "inconsistent" and "2024-03-12" in (res.note or "")
    # agreeing sources: the notice's own words are preferred
    ok = pub.resolve([("page", NOW - timedelta(days=6)), ("document_text", NOW - timedelta(days=5))], NOW)
    assert ok.source == "document_text" and ok.flag is None


def test_old_documents_keep_their_real_age():
    res = pub.resolve([("page", datetime(2021, 5, 2, tzinfo=timezone.utc))], NOW)
    assert res.published_at == datetime(2021, 5, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("text,expected", [
    ("Date of issue: 5 October 2026.\n\nRequest for proposal ...", "2026-10-05"),
    ("Issued on October 5, 2026", "2026-10-05"),
    ("Publié le 3 septembre 2026. Appel d'offres ...", "2026-09-03"),
    ("Fecha de publicación: 14 de agosto de 2026", "2026-08-14"),
    ("Publication date: 2026-07-01", "2026-07-01"),
    ("Published: 25/09/2026", "2026-09-25"),
])
def test_issue_dates_stated_in_the_notice_are_read(text, expected):
    d = pub.stated_in_text(text)
    assert d is not None and d.date().isoformat() == expected


def test_ambiguous_or_unlabelled_dates_are_not_taken_as_publication():
    assert pub.stated_in_text("Published: 05/04/2026") is None              # day/month could be swapped
    assert pub.stated_in_text("Proposals are due on 12 March 2027.") is None  # a deadline, not a publication date


# ------------------------------------------------------------------ item 4
def _type_extra(v):
    return next(f for f in v.fields if f.field == "opportunity_type").extra


def test_route_launch_without_trucking_scope_is_capacity_and_lanes():
    assert identity.module_for("route_launch", None)[0] == "capacity_lanes"
    assert identity.module_for("route_suspension", None)[0] == "capacity_lanes"
    assert identity.module_for("route_launch", "TRUCKING")[0] == "trucking_gateways"


def test_a_passenger_lot_is_kept_as_an_out_of_scope_tender_not_dropped():
    lot = "Lot A: passenger sales and ticketing agent in Kenya. Reference SAW-PAX-2027-8. Proposals are due on 15 April 2027."
    v = validate_claim("gssa_tender", {"service": FieldClaim("GSSA", lot)}, lot, claim_quote=lot)
    assert v.type_supported and _type_extra(v).get("outside_freight_scope")
    fs = next(f for f in v.fields if f.field == "freight_scope")
    assert fs.value == "passenger" and fs.support == "unsupported"
    # a cargo lot is not affected, and wording that is not a procurement is still rejected
    cargo = "Lot B: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-9."
    assert _type_extra(validate_claim("gssa_tender", {}, cargo, claim_quote=cargo)).get("outside_freight_scope") is None
    news = "Our passenger sales and ticketing agents attended a workshop in Nairobi."
    assert not validate_claim("gssa_tender", {}, news, claim_quote=news).type_supported
