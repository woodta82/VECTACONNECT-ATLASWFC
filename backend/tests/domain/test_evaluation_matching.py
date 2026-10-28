"""27 Oct 2026, fourth instruction, item 5: the evaluation matches excluded records by tender/lot identity and source
evidence, never by a shared airline name. Multiple lots and multiple notices of the same airline."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation import run  # noqa: E402
from evaluation.notices import Case, opp  # noqa: E402

LOT_A = "Lot A: passenger sales and ticketing agent in Kenya. Reference SAW-PAX-2027-8."
LOT_B = "Lot B: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-9."


def _case(excluded: list[dict]) -> Case:
    return Case("x", "test", "en", "airline_representation", {"geo_mode": "country", "countries": ["KE"]}, ["KE"], [], "html", "t", "b", [],
                {"opportunities": [opp("SAW-CGO-2027-9", service="GSSA", freight_scope="cargo")], "excluded": excluded})


def _result(signals: list[list[str]]) -> dict:
    return {"found": [{"id": "o1", "ref": "SAW-CGO-2027-9", "title": "Sample Airways: GSSA tender KE (SAW-CGO-2027-9)", "status": "open",
                       "deadline_day": None, "deadline_precision": None, "service": "GSSA", "module": "airline_representation",
                       "deadline_conflict": False, "freight_scope": "cargo", "status_basis": "", "evidence": [LOT_B]}],
            "signals": signals, "fields": [], "first_run": {"documents": [], "status": "ok", "outcome": "ok"},
            "final": {"documents": []}}


CARGO_SIG = ["airline_representation", "qualified_opportunity", "open", "cargo", "", "Sample Airways: GSSA tender KE (SAW-CGO-2027-9)",
             "SAW-CGO-2027-9", LOT_B]
PAX_SIG = ["airline_representation", "excluded", "open", "passenger", "passenger", "Sample Airways: GSSA tender KE (SAW-PAX-2027-8)",
           "SAW-PAX-2027-8", LOT_A]


def test_a_cargo_lot_of_the_same_airline_is_never_counted_as_a_leaked_passenger_lot():
    for label in ({"scope": "passenger", "ref": "SAW-PAX-2027-8"}, {"scope": "passenger", "quote": LOT_A},
                  {"scope": "passenger", "title_contains": "Sample Airways"}):
        m = run.measure(_case([label]), _result([CARGO_SIG]))
        assert m["excluded_leaked"] == 0, label          # the only opportunity is the gold cargo lot
        assert m["excluded_found"] == 0, label           # and no excluded record exists to be found


def test_the_excluded_lot_is_found_by_its_own_reference_or_passage():
    for label in ({"scope": "passenger", "ref": "SAW-PAX-2027-8"}, {"scope": "passenger", "quote": LOT_A}):
        m = run.measure(_case([label]), _result([CARGO_SIG, PAX_SIG]))
        assert (m["excluded_found"], m["excluded_leaked"]) == (1, 0), label
        # the cargo lot's signal does not satisfy the passenger label, even though the airline is the same
        m = run.measure(_case([label]), _result([CARGO_SIG, ["airline_representation", "excluded", "", "passenger", "", "Sample Airways: other",
                                                              "SAW-PAX-2027-99", "Another passage"]]))
        assert m["excluded_found"] == 0, label


def test_a_passenger_notice_that_really_became_an_opportunity_is_a_leak():
    r = _result([CARGO_SIG])
    r["found"].append({"id": "o2", "ref": "SAW-PAX-2027-8", "title": "Sample Airways: GSSA tender KE (SAW-PAX-2027-8)", "status": "open",
                       "deadline_day": None, "deadline_precision": None, "service": "GSSA", "module": "airline_representation",
                       "deadline_conflict": False, "freight_scope": "passenger", "status_basis": "", "evidence": [LOT_A]})
    for label in ({"scope": "passenger", "ref": "SAW-PAX-2027-8"}, {"scope": "passenger", "quote": LOT_A}):
        assert run.measure(_case([label]), r)["excluded_leaked"] == 1, label


def test_two_notices_of_the_same_airline_are_matched_separately():
    labels = [{"scope": "passenger", "ref": "SAW-PAX-2027-8"}, {"scope": "not_freight", "ref": "SAW-ENG-2027-3"}]
    eng = ["outsourcing_training", "excluded", "", "not_freight", "", "Sample Airways: handling tender KE (SAW-ENG-2027-3)", "SAW-ENG-2027-3",
           "Ramp lighting maintenance."]
    m = run.measure(_case(labels), _result([CARGO_SIG, PAX_SIG, eng]))
    assert (m["excluded_expected"], m["excluded_found"], m["excluded_leaked"]) == (2, 2, 0)
    m = run.measure(_case(labels), _result([CARGO_SIG, PAX_SIG]))
    assert m["excluded_found"] == 1
