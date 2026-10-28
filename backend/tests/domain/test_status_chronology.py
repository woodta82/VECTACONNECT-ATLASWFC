"""27 Oct 2026, fifth instruction, items 1, 2 and 5 at rule level: status follows the publication dates of status statements;
retrieval may order processing but never proves that one statement supersedes another. Every scenario is run for each
terminal status (cancelled, awarded, closed). Through ingestion, the database, qualification, briefing, live counts,
country results and exports: tests/integration/test_status_chronology_pipeline.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import evidence as ev
from app.domain import qualification as q
from app.domain.deadlines import StatedDeadline
from app.domain.field_validation import FieldClaim, issuer_from_lot_introduction, validate_claim

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
FUTURE = StatedDeadline.from_json({"precision": "date", "day": "2027-01-20", "earliest_utc": "2027-01-19T10:00:00+00:00",
                                   "latest_utc": "2027-01-21T12:00:00+00:00"})
TERMINALS = ["cancelled", "awarded", "closed"]


def o(doc: str, days_ago: int | None, status: str | None, *, deadline: StatedDeadline | None = None, retrieved_days_ago: int = 0,
      reopening: bool = False, family: str | None = None) -> ev.TenderObservation:
    return ev.TenderObservation(doc, family or f"fam-{doc}", "issuer", "official_portal",
                                NOW - timedelta(days=days_ago) if days_ago is not None else None, status,  # type: ignore[arg-type]
                                deadline=deadline, retrieved_at=NOW - timedelta(days=retrieved_days_ago), reopening=reopening)


def not_live(state: ev.TenderState) -> bool:
    return state.status not in ("open", "revised") and not state.actionable


# ------------------------------------------------------------------ the reported reproduction
def test_reproduction_dated_cancellation_then_undated_open_with_future_deadline():
    state = ev.resolve_tender([o("cancel", 2, "cancelled", retrieved_days_ago=1), o("rfp", None, "open", deadline=FUTURE, retrieved_days_ago=0)], NOW)
    assert state.status == "cancelled" and not state.actionable
    assert state.status_conflict and "does not establish that the cancelled status was superseded" in state.status_conflict
    # the result does not depend on the order the documents were retrieved in
    swapped = ev.resolve_tender([o("rfp", None, "open", deadline=FUTURE, retrieved_days_ago=5), o("cancel", 2, "cancelled", retrieved_days_ago=0)], NOW)
    assert swapped.status == "cancelled" and not swapped.actionable


@pytest.mark.parametrize("terminal", TERMINALS)
def test_undated_open_notice_retrieved_later_never_reopens(terminal):
    assert not_live(ev.resolve_tender([o("t", 3, terminal, retrieved_days_ago=3), o("u", None, "open", retrieved_days_ago=0)], NOW))


@pytest.mark.parametrize("terminal", TERMINALS)
def test_undated_notice_with_a_future_deadline_never_reopens(terminal):
    state = ev.resolve_tender([o("t", 3, terminal), o("u", None, "open", deadline=FUTURE)], NOW)
    assert state.status == terminal and not state.actionable and state.status_conflict


@pytest.mark.parametrize("terminal", TERMINALS)
def test_older_notice_rediscovered_after_closure_is_placed_by_its_own_date(terminal):
    state = ev.resolve_tender([o("t", 5, terminal, retrieved_days_ago=5), o("old", 140, "open", deadline=FUTURE, retrieved_days_ago=0)], NOW)
    assert state.status == terminal and not state.actionable and state.status_conflict is None


@pytest.mark.parametrize("terminal", TERMINALS)
def test_repeated_copies_of_the_original_announcement(terminal):
    original = o("orig", 60, "open", deadline=FUTURE, family="fam-orig")
    dated_copy = o("copy1", 60, "open", deadline=FUTURE, family="fam-orig", retrieved_days_ago=0)
    undated_copy = o("copy2", None, "open", deadline=FUTURE, family="fam-orig", retrieved_days_ago=0)
    later_dated_copy = o("copy3", 1, "open", deadline=FUTURE, family="fam-orig", retrieved_days_ago=0)
    end = o("end", 20, terminal)
    assert ev.resolve_tender([original, end, dated_copy], NOW).status == terminal
    assert ev.resolve_tender([original, end, undated_copy], NOW).status == terminal
    # a copy re-dated after the terminal statement without saying the tender was reopened: a person decides; never live
    state = ev.resolve_tender([original, end, later_dated_copy], NOW)
    assert state.status == "contradictory" and not state.actionable and "without saying it was reopened" in (state.status_conflict or "")


@pytest.mark.parametrize("terminal", TERMINALS)
def test_conflicting_statements_with_identical_publication_dates(terminal):
    state = ev.resolve_tender([o("a", 4, "open", deadline=FUTURE), o("b", 4, terminal)], NOW)
    assert state.status == "contradictory" and not state.actionable and "same day" in (state.status_conflict or "")
    # one document stating both is the existing single-document contradiction, unchanged
    same_doc = ev.resolve_tender([o("a", 4, "contradictory"), o("a", 4, terminal)], NOW)
    assert same_doc.status == terminal


@pytest.mark.parametrize("terminal", TERMINALS)
def test_explicit_dated_reopening_is_supported(terminal):
    state = ev.resolve_tender([o("t", 30, terminal), o("r", 3, "open", deadline=FUTURE, reopening=True)], NOW)
    assert state.status == "open" and state.actionable and state.status_conflict is None
    assert any(h.get("date_basis") == "published (reopening stated)" for h in state.history)


@pytest.mark.parametrize("terminal", TERMINALS)
def test_undated_reopening_is_not_verified(terminal):
    state = ev.resolve_tender([o("t", 30, terminal), o("r", None, "open", deadline=FUTURE, reopening=True)], NOW)
    assert state.status == terminal and not state.actionable and state.status_conflict


@pytest.mark.parametrize("terminal", TERMINALS)
def test_a_new_procurement_round_is_a_different_tender(terminal):
    # identity is by reference (ingestion); the resolver sees only the new round's own evidence
    old_round = ev.resolve_tender([o("t", 60, terminal)], NOW)
    new_round = ev.resolve_tender([o("n", 3, "open", deadline=FUTURE)], NOW)
    assert old_round.status == terminal and new_round.status == "open" and new_round.actionable


def test_undated_terminal_against_dated_live_needs_a_person():
    state = ev.resolve_tender([o("a", 5, "open", deadline=FUTURE), o("u", None, "cancelled")], NOW)
    assert state.status == "contradictory" and not state.actionable


def test_undated_statements_alone_apply_only_when_they_agree():
    assert ev.resolve_tender([o("a", None, "open", deadline=FUTURE), o("b", None, "open")], NOW).status == "open"
    assert ev.resolve_tender([o("a", None, "open", deadline=FUTURE), o("b", None, "cancelled")], NOW).status == "contradictory"


def test_qualification_never_passes_live_status_for_terminal_or_contradictory():
    ex = ev.assess_claim([ev.EvidenceLink("d", "f", "official_portal", "supports")])
    for obs in ([o("t", 2, "cancelled"), o("u", None, "open", deadline=FUTURE)], [o("a", 4, "open", deadline=FUTURE), o("b", 4, "awarded")]):
        checks = {c.code: c.result for c in q.airline_representation_checks(existence=ex, tender=ev.resolve_tender(obs, NOW), territory_cell_state="gap",
                                                                            capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                                                            scope_known=True, freight_scope="cargo")}
        assert checks["live_status"] != "pass"


@pytest.mark.parametrize("text,expected", [
    ("Tender EXA-1 has been reopened: proposals are invited again.", True),
    ("The tender has been re-issued with a new closing date.", True),
    ("Example Air invites proposals again for its cargo GSSA in Kenya.", True),
    ("L'appel d'offres est relancé.", True),
    ("The tender will not be reopened.", False),
    ("Example Air invites proposals from cargo GSSA providers.", False),
])
def test_reopening_wording(text, expected):
    assert ev.reopening_stated(text) is expected


# ------------------------------------------------------------------ item 5
def test_lot_issuer_from_an_explicit_introduction_and_ambiguity_kept_for_review():
    lot = "Lot 1: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-31."
    assert issuer_from_lot_introduction("Sample Airways", lot, f"Sample Airways invites proposals for the following lot.\n\n{lot}")[0] == "supported"
    assert issuer_from_lot_introduction("Sample Airways", lot, f"Sample Airways and Example Air publish the following joint lot.\n\n{lot}")[0] == "review_required"
    assert issuer_from_lot_introduction("Example Air", lot, f"Sample Airways invites proposals for the following lot.\n\n{lot}") is None
    assert issuer_from_lot_introduction("Sample Airways", "Cargo GSSA in Kenya.", "Sample Airways invites proposals. Cargo GSSA in Kenya.") is None


def test_tender_context_cites_the_reference_and_never_carries_status_or_deadline():
    t = "Contact update for tender SAW-CGO-2026-72 (cargo GSSA, Ethiopia, Sample Airways): enquiries now go to the commercial office."
    v = validate_claim("tender_context", {"tender_ref": FieldClaim("SAW-CGO-2026-72", t), "status": FieldClaim("open", t),
                                          "deadline": FieldClaim("2027-01-01", t)}, t, claim_quote=t)
    assert v.type_supported and not any(f.field in ("status", "deadline") for f in v.fields)
    other = validate_claim("tender_context", {"tender_ref": FieldClaim("XYZ-1", t)}, t, claim_quote=t)
    assert not other.type_supported
