"""Directive §7: every material field is validated on its own quote."""
from app.domain.field_validation import FieldClaim, dates_in_text, quote_in_document, validate_claim

DOC = ("Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya. "
       "Tender reference EXA-CGO-2026-014. Proposals must be submitted by 30 November 2026 at 17:00 EAT. "
       "Eligible bidders must hold IATA cargo agent accreditation. Example Air is headquartered in the United Arab Emirates.")
Q1 = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya."


def _v(claim_type, fields, quote=Q1, doc=DOC, tz=None):
    return validate_claim(claim_type, {k: FieldClaim(*v) for k, v in fields.items()}, doc, claim_quote=quote, deadline_timezone=tz)


def by(v, name):
    return next(f for f in v.fields if f.field == name)


def test_each_field_needs_its_own_quote_stating_the_value():
    v = _v("gssa_tender", {"airline": ("Example Air", Q1), "country": ("Kenya", Q1),
                           "issuer_country": ("United Arab Emirates", Q1),          # true in the document, but not in THIS quote
                           "tender_ref": ("EXA-CGO-2026-014", "Tender reference EXA-CGO-2026-014.")})
    assert v.type_supported
    assert by(v, "airline").support == "supported"
    assert by(v, "country").support == "supported" and by(v, "country").normalised == "KE"
    assert by(v, "issuer_country").support == "unsupported"
    assert by(v, "tender_ref").support == "supported"


def test_quote_not_in_document_supports_nothing():
    v = _v("gssa_tender", {"airline": ("Example Air", "Example Air appoints a GSSA in Kenya.")},
           quote="Example Air appoints a GSSA in Kenya.")
    assert not v.type_supported and by(v, "airline").support == "unsupported"
    assert "verbatim" in by(v, "airline").reason


def test_value_not_stated_in_a_genuine_quote_is_unsupported():
    v = _v("gssa_tender", {"tender_ref": ("EXA-CGO-2026-099", "Tender reference EXA-CGO-2026-014.")})
    assert by(v, "tender_ref").support == "unsupported"


def test_gssa_mention_without_a_procurement_is_not_a_tender():
    doc = "Example Air works with a GSSA in Kenya."
    v = _v("gssa_tender", {}, quote=doc, doc=doc)
    assert not v.type_supported


def test_route_announcement_cannot_establish_tender_fields():
    doc = "Example Air will operate a new freighter route from Dubai to Nairobi from 1 December 2026."
    v = _v("route_launch", {"status": ("open", doc), "tender_ref": ("X-1", doc), "deadline": ("2026-12-01", doc),
                            "eligibility": ("anyone", doc), "origin": ("United Arab Emirates", doc)}, quote=doc, doc=doc)
    assert v.type_supported
    for name in ("status", "tender_ref", "deadline", "eligibility"):
        assert by(v, name).support == "not_applicable", name


def test_deadline_takes_date_time_and_zone_from_the_quote():
    q = "Proposals must be submitted by 30 November 2026 at 17:00 EAT."
    v = _v("tender_deadline", {"deadline": ("2026-11-30T17:00", q)}, quote=q)
    d = by(v, "deadline")
    assert d.support == "supported" and d.normalised == "2026-11-30T14:00:00+00:00"


def test_deadline_date_not_in_quote_is_unsupported():
    q = "Proposals must be submitted by 30 November 2026 at 17:00 EAT."
    v = _v("tender_deadline", {"deadline": ("2026-12-14T17:00", q)}, quote=q)
    assert by(v, "deadline").support == "unsupported"


def test_missing_zone_is_not_turned_into_utc():
    doc = "Submissions are due by 5 December 2026 at 12:00."
    v = _v("tender_deadline", {"deadline": ("2026-12-05T12:00", doc)}, quote=doc, doc=doc)
    d = by(v, "deadline")
    assert d.support == "supported" and d.extra["precision"] == "local_time" and d.normalised == "2026-12-05T12:00"
    assert d.extra["deadline"]["exact_utc"] is None and "zone_assumed" not in d.extra


def test_ambiguous_numeric_dates_are_not_read():
    assert dates_in_text("Closing 03/04/2026") == []
    assert [d.day.isoformat() for d in dates_in_text("Closing 2026-04-03")] == ["2026-04-03"]
    assert [d.day.isoformat() for d in dates_in_text("date limite : 3 avril 2026")] == ["2026-04-03"]


def test_quote_matching_tolerates_whitespace_and_case_only():
    assert quote_in_document("example   AIR invites", DOC)
    assert not quote_in_document("Example Air invites bids", DOC)
