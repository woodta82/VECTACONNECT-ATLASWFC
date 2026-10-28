"""Held-out set 7 (written 27 Oct 2026, fifth instruction, BEFORE any rule of that instruction was changed; run once at the
end of the release; no rule changed afterwards).

PROVENANCE: authored for this build in the form of real airline and procurement notices. None is a genuine notice.
The evaluation date is 26 Oct 2026 (`run.NOW`); documents are served in the order listed (main document first).

Gold conventions as in `heldout6.py`, plus:
- `historical`: terminal notices (cancellation, award, closure) to be KEPT as a tender record with that status, never live;
- a tender that is not yet tracked and whose evidence ends in a terminal status is never created as an opportunity
  (labels v4); a tracked tender moves to the terminal status;
- 'contradictory': conflicting status statements that need a person.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

HELDOUT7: list[Case] = []


def add(c: Case) -> Case:
    HELDOUT7.append(c)
    return c


def tender(airline: str, country: str, ref: str, quote: str, *, status: str | None = "open", status_quote: str | None = None,
           deadline: tuple[str, str] | None = None, gold_status: bool = True, gold: dict | None = None, ctype: str = "gssa_tender",
           service: str = "GSSA") -> dict:
    fields = {"airline": f(airline, quote), "country": f(country, quote), "service": f(service, quote), "tender_ref": f(ref, quote)}
    g = {"airline": True, "country": True, "service": True, "tender_ref": True}
    if status is not None:
        fields["status"] = f(status, status_quote or quote)
        g["status"] = gold_status
    if deadline is not None:
        fields["deadline"] = f(deadline[0], deadline[1])
        g["deadline"] = True
    g.update(gold or {})
    return claim(ctype, quote, fields, g)


def status_claim(airline_quote: str, airline: str, ref: str, quote: str, status: str, *, deadline: tuple[str, str] | None = None) -> dict:
    fields = {"airline": f(airline, airline_quote), "tender_ref": f(ref, quote), "status": f(status, quote)}
    g = {"tender_ref": True, "status": True}
    if deadline:
        fields["deadline"] = f(deadline[0], deadline[1])
        g["deadline"] = True
    return claim("tender_status", quote, fields, g)


def KE(code: str = "KE") -> dict:
    return {"geo_mode": "country", "countries": [code]}


# q01 the reported defect: a dated cancellation, then an UNDATED open notice with a future deadline, retrieved later
QA1 = "Tender EXA-CGO-2026-61 for a cargo general sales and service agent in Kenya, issued by Example Air, has been cancelled."
QA2 = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2026-61."
QA3 = "Proposals must be submitted by 20 January 2027."
add(Case("q01-dated-cancellation-then-undated-open-ke", "heldout7", "en", "airline_representation", KE(), ["KE"],
         ["status_transition", "undated", "cancellation"], "html", "Cancellation EXA-CGO-2026-61", QA1,
         [status_claim(QA1, "Example Air", "EXA-CGO-2026-61", QA1, "cancelled"),
          tender("Example Air", "Kenya", "EXA-CGO-2026-61", QA2, deadline=("2027-01-20", QA3), status_quote=QA2)],
         {"opportunities": [], "historical": [{"ref": "EXA-CGO-2026-61", "status": "cancelled"}]},
         published="2026-10-24T08:00:00Z",
         documents=[{"title": "RFP EXA-CGO-2026-61", "body": f"{QA2}\n\n{QA3}", "published": None}],
         notes="An undated open notice does not establish that the cancellation was superseded."))

# q02 award, then an undated open notice with a future deadline
QB1 = "Tender SAW-CGO-2026-62 for a cargo GSSA in Uganda has been awarded to Entebbe Cargo Agents. Sample Airways."
QB2 = "Sample Airways invites proposals from cargo general sales and service agents for Uganda. Reference SAW-CGO-2026-62. Proposals must be submitted by 15 February 2027."
add(Case("q02-award-then-undated-open-with-deadline-ug", "heldout7", "en", "airline_representation", KE("UG"), ["UG"],
         ["status_transition", "undated", "award"], "html", "Award SAW-CGO-2026-62", QB1,
         [status_claim(QB1, "Sample Airways", "SAW-CGO-2026-62", QB1, "awarded"),
          tender("Sample Airways", "Uganda", "SAW-CGO-2026-62", QB2, deadline=("2027-02-15", QB2))],
         {"opportunities": [], "historical": [{"ref": "SAW-CGO-2026-62", "status": "awarded"}]},
         published="2026-10-15T08:00:00Z",
         documents=[{"title": "RFP SAW-CGO-2026-62", "body": QB2, "published": None}]))

# q03 closed, then an undated copy of an open notice without a deadline
QC1 = "Tender EXA-CGO-2026-63 (cargo GSSA, Tanzania, Example Air) is closed; no further proposals will be accepted."
QC2 = "Example Air invites proposals from cargo general sales and service agents for Tanzania. Reference EXA-CGO-2026-63."
add(Case("q03-closed-then-undated-open-tz", "heldout7", "en", "airline_representation", KE("TZ"), ["TZ"],
         ["status_transition", "undated", "closed"], "html", "Closure EXA-CGO-2026-63", QC1,
         [status_claim(QC1, "Example Air", "EXA-CGO-2026-63", QC1, "closed"),
          tender("Example Air", "Tanzania", "EXA-CGO-2026-63", QC2)],
         {"opportunities": [], "historical": [{"ref": "EXA-CGO-2026-63", "status": "closed"}]},
         published="2026-10-20T08:00:00Z",
         documents=[{"title": "RFP EXA-CGO-2026-63", "body": QC2, "published": None}]))

# q04 an older dated notice rediscovered after the closure
QD1 = "Tender SAW-CGO-2026-64 (cargo GSSA, Rwanda, Sample Airways) is closed."
QD2 = "Sample Airways invites proposals from cargo general sales and service agents for Rwanda. Reference SAW-CGO-2026-64. Proposals must be submitted by 1 December 2026."
add(Case("q04-older-notice-rediscovered-after-closure-rw", "heldout7", "en", "airline_representation", KE("RW"), ["RW"],
         ["status_transition", "rediscovered"], "html", "Closure SAW-CGO-2026-64", QD1,
         [status_claim(QD1, "Sample Airways", "SAW-CGO-2026-64", QD1, "closed"),
          tender("Sample Airways", "Rwanda", "SAW-CGO-2026-64", QD2, deadline=("2026-12-01", QD2))],
         {"opportunities": [], "historical": [{"ref": "SAW-CGO-2026-64", "status": "closed"}]},
         published="2026-10-21T08:00:00Z",
         documents=[{"title": "RFP SAW-CGO-2026-64", "body": QD2, "published": "2026-06-01T08:00:00Z"}]))

# q05 tracked tender, cancelled, then an undated repeated copy of the original announcement
QE1 = "Example Air invites proposals from cargo general sales and service agents for Zambia. Reference EXA-CGO-2026-65. Proposals must be submitted by 15 December 2026."
QE2 = "Tender EXA-CGO-2026-65 (cargo GSSA, Zambia, Example Air) has been cancelled."
add(Case("q05-cancelled-then-undated-copy-of-announcement-zm", "heldout7", "en", "airline_representation", KE("ZM"), ["ZM"],
         ["status_transition", "undated", "copy", "cancellation"], "html", "RFP EXA-CGO-2026-65", QE1,
         [tender("Example Air", "Zambia", "EXA-CGO-2026-65", QE1, deadline=("2026-12-15", QE1)),
          status_claim(QE2, "Example Air", "EXA-CGO-2026-65", QE2, "cancelled")],
         {"opportunities": [opp("EXA-CGO-2026-65", status="cancelled", service="GSSA", day="2026-12-15", precision="date")],
          "historical": [{"ref": "EXA-CGO-2026-65", "status": "cancelled"}]},
         published="2026-09-01T08:00:00Z",
         documents=[{"title": "Cancellation EXA-CGO-2026-65", "body": QE2, "published": "2026-10-10T08:00:00Z"},
                    {"title": "RFP EXA-CGO-2026-65 (copy)", "body": QE1, "published": None}],
         notes="The tracked tender moves to cancelled; the undated copy of the announcement does not reopen it."))

# q06 conflicting statements with identical publication dates
QF1 = "Sample Airways invites proposals from cargo general sales and service agents for Malawi. Reference SAW-CGO-2026-66. Proposals must be submitted by 20 December 2026."
QF2 = "Tender SAW-CGO-2026-66 (cargo GSSA, Malawi, Sample Airways) has been cancelled."
add(Case("q06-same-date-open-and-cancelled-mw", "heldout7", "en", "airline_representation", KE("MW"), ["MW"],
         ["status_transition", "same_date_conflict"], "html", "RFP SAW-CGO-2026-66", QF1,
         [tender("Sample Airways", "Malawi", "SAW-CGO-2026-66", QF1, deadline=("2026-12-20", QF1)),
          status_claim(QF2, "Sample Airways", "SAW-CGO-2026-66", QF2, "cancelled")],
         {"opportunities": [opp("SAW-CGO-2026-66", status="contradictory", service="GSSA", day="2026-12-20", precision="date")]},
         published="2026-10-20T08:00:00Z",
         documents=[{"title": "Cancellation SAW-CGO-2026-66", "body": QF2, "published": "2026-10-20T08:00:00Z"}],
         notes="Same publication date, opposite statements: a person decides; never actionable."))

# q07 an explicit, dated reopening of a cancelled tender
QG1 = "Tender EXA-CGO-2026-67 (cargo GSSA, Botswana, Example Air) has been cancelled."
QG2 = "Tender EXA-CGO-2026-67 has been reopened: Example Air invites proposals from cargo general sales and service agents for Botswana again."
QG3 = "Proposals must be submitted by 15 January 2027."
add(Case("q07-dated-reopening-bw", "heldout7", "en", "airline_representation", KE("BW"), ["BW"],
         ["status_transition", "reopening"], "html", "Cancellation EXA-CGO-2026-67", QG1,
         [status_claim(QG1, "Example Air", "EXA-CGO-2026-67", QG1, "cancelled"),
          tender("Example Air", "Botswana", "EXA-CGO-2026-67", QG2, deadline=("2027-01-15", QG3))],
         {"opportunities": [opp("EXA-CGO-2026-67", status="open", service="GSSA", day="2027-01-15", precision="date", freight_scope="cargo")]},
         published="2026-09-15T08:00:00Z",
         documents=[{"title": "Reopening EXA-CGO-2026-67", "body": f"{QG2}\n\n{QG3}", "published": "2026-10-20T08:00:00Z"}],
         notes="A dated notice of the same tender explicitly reopens it after the cancellation: open again."))

# q08 a new procurement round with a similar title after an award
QH1 = "Tender EXA-CGO-2026-70 for a cargo GSSA in Ghana has been awarded to Accra Cargo Agents. Example Air."
QH2 = "Example Air invites proposals from cargo general sales and service agents for Ghana in a new procurement round. Reference EXA-CGO-2026-88. Proposals must be submitted by 10 January 2027."
add(Case("q08-new-round-similar-title-gh", "heldout7", "en", "airline_representation", KE("GH"), ["GH"],
         ["status_transition", "new_round"], "html", "Award: cargo GSSA, Ghana", QH1,
         [status_claim(QH1, "Example Air", "EXA-CGO-2026-70", QH1, "awarded"),
          tender("Example Air", "Ghana", "EXA-CGO-2026-88", QH2, deadline=("2027-01-10", QH2))],
         {"opportunities": [opp("EXA-CGO-2026-88", status="open", service="GSSA", day="2027-01-10", precision="date", freight_scope="cargo")],
          "historical": [{"ref": "EXA-CGO-2026-70", "status": "awarded"}]},
         published="2026-08-01T08:00:00Z",
         documents=[{"title": "RFP: cargo GSSA, Ghana", "body": QH2, "published": "2026-10-20T08:00:00Z"}]))

# q09 an UNDATED reopening after a dated cancellation: not verified
QI1 = "Tender SAW-CGO-2026-69 (cargo GSSA, Namibia, Sample Airways) has been cancelled."
QI2 = "Tender SAW-CGO-2026-69 has been reopened: Sample Airways invites proposals from cargo general sales and service agents for Namibia again."
add(Case("q09-undated-reopening-na", "heldout7", "en", "airline_representation", KE("NA"), ["NA"],
         ["status_transition", "undated", "reopening"], "html", "Cancellation SAW-CGO-2026-69", QI1,
         [status_claim(QI1, "Sample Airways", "SAW-CGO-2026-69", QI1, "cancelled"),
          tender("Sample Airways", "Namibia", "SAW-CGO-2026-69", QI2)],
         {"opportunities": [], "historical": [{"ref": "SAW-CGO-2026-69", "status": "cancelled"}]},
         published="2026-10-01T08:00:00Z",
         documents=[{"title": "Reopening SAW-CGO-2026-69", "body": QI2, "published": None}],
         notes="Without a date the reopening cannot be placed after the cancellation: the record stays cancelled, flagged for review."))

# q10 an award notice for a tender never tracked: historical intelligence only
QJ1 = "Example Air has awarded tender EXA-CGO-2026-71 (cargo GSSA, Senegal) to Dakar Cargo Services."
add(Case("q10-award-only-sn", "heldout7", "en", "airline_representation", KE("SN"), ["SN"],
         ["award", "terminal_only"], "html", "Award EXA-CGO-2026-71", QJ1,
         [status_claim(QJ1, "Example Air", "EXA-CGO-2026-71", QJ1, "awarded")],
         {"opportunities": [], "historical": [{"ref": "EXA-CGO-2026-71", "status": "awarded"}]},
         published="2026-10-18T08:00:00Z"))

# q11 a contact update referencing an established tender: supporting information, no status refresh
QK1 = "Sample Airways invites proposals from cargo general sales and service agents for Ethiopia. Reference SAW-CGO-2026-72."
QK2 = "Contact update for tender SAW-CGO-2026-72 (cargo GSSA, Ethiopia, Sample Airways): enquiries now go to the commercial office in Addis Ababa."
add(Case("q11-contact-update-attached-et", "heldout7", "en", "airline_representation", KE("ET"), ["ET"],
         ["contextual", "contact_update", "status_freshness"], "html", "RFP SAW-CGO-2026-72", QK1,
         [tender("Sample Airways", "Ethiopia", "SAW-CGO-2026-72", QK1),
          tender("Sample Airways", "Ethiopia", "SAW-CGO-2026-72", QK2, status=None)],
         {"opportunities": [opp("SAW-CGO-2026-72", status="unverified", service="GSSA", freight_scope="cargo")]},
         published="2026-06-01T08:00:00Z",
         documents=[{"title": "Contact update SAW-CGO-2026-72", "body": QK2, "published": "2026-10-25T08:00:00Z"}],
         notes="The contact update is attached as supporting information; it does not refresh the 147-day-old open statement."))

# q12 lot issuer stated explicitly in the introduction
QL0 = "Sample Airways invites proposals for the following lot."
QL1 = "Lot 1: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-31. Proposals are due on 15 April 2027."
add(Case("q12-lot-issuer-from-introduction-ke", "heldout7", "en", "airline_representation", KE(), ["KE"],
         ["contextual", "multi_lot"], "html", "Request for proposals: cargo sales agent, Kenya", f"{QL0}\n\n{QL1}",
         [tender("Sample Airways", "Kenya", "SAW-CGO-2027-31", QL1, deadline=("2027-04-15", QL1))],
         {"opportunities": [opp("SAW-CGO-2027-31", status="open", service="GSSA", day="2027-04-15", precision="date", freight_scope="cargo")]},
         published="2026-10-20T08:00:00Z",
         notes="The introduction names the issuer of the lot; the airline is established through that explicit relationship."))

# q13 two possible issuers in the introduction: the lot's issuer stays pending review
QM0 = "Sample Airways and Example Air publish the following joint lot."
QM1 = "Lot 2: cargo general sales and service agent in Uganda. Reference JNT-CGO-2027-32. Proposals are due on 20 April 2027."
add(Case("q13-lot-issuer-ambiguous-ug", "heldout7", "en", "airline_representation", KE("UG"), ["UG"],
         ["contextual", "multi_lot", "ambiguous_issuer"], "html", "Joint request for proposals, Uganda", f"{QM0}\n\n{QM1}",
         [tender("Sample Airways", "Uganda", "JNT-CGO-2027-32", QM1, deadline=("2027-04-20", QM1), gold={"airline": False})],
         {"opportunities": [opp("JNT-CGO-2027-32", status="open", service="GSSA", day="2027-04-20", precision="date", freight_scope="cargo")]},
         published="2026-10-20T08:00:00Z",
         notes="Two airlines are named: neither is established as the lot's issuer; review."))

# q14 a contact update after the deadline passed: no refresh, still expired
QN1 = "Example Air invites proposals from cargo general sales and service agents for Mozambique. Reference EXA-CGO-2026-73. Proposals must be submitted by 1 October 2026."
QN2 = "Contact update for tender EXA-CGO-2026-73 (cargo GSSA, Mozambique, Example Air): enquiries now go to the commercial office in Maputo."
add(Case("q14-contact-update-after-deadline-mz", "heldout7", "en", "airline_representation", KE("MZ"), ["MZ"],
         ["contextual", "contact_update", "expired"], "html", "RFP EXA-CGO-2026-73", QN1,
         [tender("Example Air", "Mozambique", "EXA-CGO-2026-73", QN1, deadline=("2026-10-01", QN1)),
          tender("Example Air", "Mozambique", "EXA-CGO-2026-73", QN2, status=None)],
         {"opportunities": [opp("EXA-CGO-2026-73", status="expired", service="GSSA", day="2026-10-01", precision="date", freight_scope="cargo")]},
         published="2026-09-01T08:00:00Z",
         documents=[{"title": "Contact update EXA-CGO-2026-73", "body": QN2, "published": "2026-10-25T08:00:00Z"}]))


def heldout7_cases() -> list[Case]:
    return list(HELDOUT7)
