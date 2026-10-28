"""Review of 26 Oct 2026, §1/§5: deadline precision is preserved; assumptions never become source facts."""
from datetime import date, datetime, timezone

import pytest

from app.domain import deadlines as dl
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import validate_claim

UTC = timezone.utc


def deadline(text, value, tz_hint=None):
    v = validate_claim("tender_deadline", {"deadline": F(value, text)}, text, claim_quote=text, deadline_timezone=tz_hint,
                       reference_date=date(2026, 10, 26))
    f = next(f for f in v.fields if f.field == "deadline")
    return f, dl.StatedDeadline.from_json(f.extra.get("deadline"))


def test_date_only_stays_date_only():
    f, d = deadline("Proposals are due on 30 November 2026.", "2026-11-30T00:00:00Z")
    assert f.support == "supported" and d.precision == "date" and d.exact_utc is None and f.normalised == "2026-11-30"
    assert "the extractor's time 00:00 is not stated" in f.reason
    # bounds: the date begins at UTC+14 and ends at UTC-12; neither is presented as the deadline
    assert d.earliest_utc == datetime(2026, 11, 29, 10, 0, tzinfo=UTC)
    assert d.latest_utc == datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    assert not dl.is_past(d, datetime(2026, 11, 30, 23, 0, tzinfo=UTC))      # never expires early


def test_zone_hint_is_an_assumption_not_a_fact():
    f, d = deadline("Bids close on 30 November 2026 at 17:00.", "2026-11-30T17:00", tz_hint="Africa/Nairobi")
    assert d.precision == "local_time" and d.exact_utc is None
    assert d.assumed_zone == "Africa/Nairobi" and d.assumed_utc == datetime(2026, 11, 30, 14, 0, tzinfo=UTC)
    assert "assumption, not a source fact" in f.reason


def test_stated_offset_and_named_abbreviation_give_an_instant():
    _, d = deadline("Proposals must be submitted by 30 November 2026 at 17:00 EAT.", "2026-11-30T17:00")
    assert d.precision == "instant" and d.exact_utc == datetime(2026, 11, 30, 14, 0, tzinfo=UTC) and d.zone == "EAT"
    _, d = deadline("Deadline: 30 November 2026, 17:00 UTC+3.", "2026-11-30T17:00")
    assert d.exact_utc == datetime(2026, 11, 30, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize("abbr", ["CST", "IST", "BST", "AST", "PST"])
def test_ambiguous_abbreviations_are_not_used(abbr):
    f, d = deadline(f"Submissions by 30 November 2026 at 17:00 {abbr}.", "2026-11-30T17:00")
    assert d.precision == "local_time" and d.exact_utc is None and "ambiguous" in f.reason


def test_named_zone_follows_daylight_saving():
    _, summer = deadline("Bids close 15 July 2026 at 12:00 London time.", "2026-07-15T12:00")
    _, winter = deadline("Bids close 15 December 2026 at 12:00 London time.", "2026-12-15T12:00")
    assert summer.exact_utc == datetime(2026, 7, 15, 11, 0, tzinfo=UTC)       # BST, UTC+1
    assert winter.exact_utc == datetime(2026, 12, 15, 12, 0, tzinfo=UTC)      # GMT


def test_nonexistent_and_repeated_local_times_are_not_claimed():
    f, d = deadline("Bids close 29 March 2026 at 01:30 London time.", "2026-03-29T01:30")     # clocks go forward 01:00 -> 02:00
    assert d.precision == "local_time" and d.exact_utc is None and "does not exist" in f.reason
    f, d = deadline("Bids close 25 October 2026 at 01:30 London time.", "2026-10-25T01:30")   # 01:00-02:00 occurs twice
    assert d.precision == "local_time" and d.exact_utc is None and "occurs twice" in f.reason


def test_2400_is_the_end_of_the_stated_day():
    f, d = deadline("Proposals are due by 30 November 2026 at 24:00 GST.", "2026-11-30T24:00")
    assert d.day == date(2026, 12, 1) and d.local_time == "00:00" and d.exact_utc == datetime(2026, 11, 30, 20, 0, tzinfo=UTC)
    assert "24:00 read as the end of the stated day" in f.reason
    _, m = deadline("Proposals are due by 30 November 2026 at midnight EAT.", "2026-11-30")
    assert m.exact_utc == datetime(2026, 11, 30, 21, 0, tzinfo=UTC)


def test_local_time_wording_is_not_a_zone():
    f, d = deadline("Bids are due on 30 November 2026 at 17:00 local time.", "2026-11-30T17:00")
    assert d.precision == "local_time" and "local time" in f.reason


def test_bounds_for_timed_local_deadline():
    d = dl.build(date(2026, 11, 30), (17, 0))
    assert d.earliest_utc == datetime(2026, 11, 30, 3, 0, tzinfo=UTC) and d.latest_utc == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    assert dl.may_be_past(d, datetime(2026, 11, 30, 10, 0, tzinfo=UTC)) and not dl.is_past(d, datetime(2026, 11, 30, 10, 0, tzinfo=UTC))


def test_round_trip_and_comparison():
    a = dl.build(date(2026, 11, 30), None)
    b = dl.build(date(2026, 11, 30), (17, 0), offset_minutes=180, zone_label="EAT")
    assert dl.StatedDeadline.from_json(b.to_json()) == b
    assert a.same_stated_value(b)                                # a timed notice refines a date-only one
    assert not b.same_stated_value(dl.build(date(2026, 12, 14), (17, 0), offset_minutes=180))
