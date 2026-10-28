"""Held-out set 6 (written 27 Oct 2026, fourth instruction, BEFORE any rule of that instruction was changed; run once at the
end of the release; no rule changed afterwards).

PROVENANCE: authored for this build in the form of real airline and procurement notices. None is a genuine notice.
The evaluation date is 26 Oct 2026 (`run.NOW`); the age review threshold is the default 90 days.

Gold conventions as in `heldout5.py`, plus:
- several documents per case (`Case.documents`), served from the same source in order;
- `excluded` entries name the excluded record by its tender/lot `ref` (or `quote`), never by the airline alone;
- `publication_flag`: the flag the documents' publication dates must carry ('future', 'inconsistent') or None;
- `opp(status=...)` may be 'unverified' (stated open, but nothing dated and current confirms it), 'announced',
  'historical' or a terminal status.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

HELDOUT6: list[Case] = []


def add(c: Case) -> Case:
    HELDOUT6.append(c)
    return c


def tender(airline: str, country: str, ref: str, quote: str, *, status_quote: str | None = None, deadline: tuple[str, str] | None = None,
           gold_status: bool = True, gold_deadline: bool = True, ctype: str = "gssa_tender", service: str = "GSSA") -> dict:
    fields = {"airline": f(airline, quote), "country": f(country, quote), "service": f(service, quote), "tender_ref": f(ref, quote)}
    gold = {"airline": True, "country": True, "service": True, "tender_ref": True}
    if status_quote is not None:
        fields["status"] = f("open", status_quote)
        gold["status"] = gold_status
    if deadline is not None:
        fields["deadline"] = f(deadline[0], deadline[1])
        gold["deadline"] = gold_deadline
    return claim(ctype, quote, fields, gold)


KE = {"geo_mode": "country", "countries": ["KE"]}

# p01 the reported defect: an open assertion published 365 days ago without a deadline, then a contact update published today
PA1 = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2025-31."
PA2 = "Contact update for EXA-CGO-2025-31 (cargo GSSA, Kenya, Example Air): enquiries now go to the commercial office in Nairobi."
add(Case("p01-old-open-plus-new-contact-update-ke", "heldout6", "en", "airline_representation", KE, ["KE"],
         ["status_freshness", "multi_document"], "html", "RFP EXA-CGO-2025-31", PA1,
         [tender("Example Air", "Kenya", "EXA-CGO-2025-31", PA1, status_quote=PA1),
          tender("Example Air", "Kenya", "EXA-CGO-2025-31", PA2)],
         {"opportunities": [opp("EXA-CGO-2025-31", status="unverified", service="GSSA", freight_scope="cargo")]},
         published="2025-10-26T08:00:00Z",
         documents=[{"title": "Contact update EXA-CGO-2025-31", "body": PA2, "published": "2026-10-26T07:00:00Z"}],
         notes="A new document with no status wording does not refresh a year-old open assertion."))

# p02 a new eligibility document does not renew an old open assertion
PB1 = "Sample Airways invites proposals from cargo GSSA providers for Uganda. Reference SAW-CGO-2025-12."
PB2 = "Eligibility for SAW-CGO-2025-12: applicants must hold IATA cargo agent accreditation."
add(Case("p02-old-open-plus-new-eligibility-ug", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["status_freshness", "multi_document"], "html", "RFP SAW-CGO-2025-12", PB1,
         [tender("Sample Airways", "Uganda", "SAW-CGO-2025-12", PB1, status_quote=PB1),
          claim("eligibility", PB2, {"airline": f("Sample Airways", PB1), "tender_ref": f("SAW-CGO-2025-12", PB2),
                                     "eligibility": f("IATA cargo agent accreditation", PB2)}, {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("SAW-CGO-2025-12", status="unverified", service="GSSA", freight_scope="cargo")]},
         published="2025-12-01T08:00:00Z",
         documents=[{"title": "Eligibility SAW-CGO-2025-12", "body": PB2, "published": "2026-10-24T07:00:00Z"}]))

# p03 a genuine explicit reconfirmation does refresh the status
PC1 = "Example Air invites proposals from cargo general sales and service agents for Tanzania. Reference EXA-CGO-2025-33."
PC2 = "Tender EXA-CGO-2025-33 remains open: proposals from cargo GSSA providers are still being accepted."
add(Case("p03-old-open-plus-explicit-reconfirmation-tz", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["TZ"]}, ["TZ"],
         ["status_freshness", "multi_document", "reconfirmation"], "html", "RFP EXA-CGO-2025-33", PC1,
         [tender("Example Air", "Tanzania", "EXA-CGO-2025-33", PC1, status_quote=PC1),
          claim("tender_status", PC2, {"airline": f("Example Air", PC1), "tender_ref": f("EXA-CGO-2025-33", PC2), "status": f("open", PC2)},
                {"tender_ref": True, "status": True})],
         {"opportunities": [opp("EXA-CGO-2025-33", status="open", service="GSSA", freight_scope="cargo")]},
         published="2025-10-20T08:00:00Z",
         documents=[{"title": "Status EXA-CGO-2025-33", "body": PC2, "published": "2026-10-22T07:00:00Z"}]))

# p04 a terminal status stays terminal
PD1 = "Example Air invites proposals from cargo general sales and service agents for Rwanda. Reference EXA-CGO-2025-34."
PD2 = "Tender EXA-CGO-2025-34 has been awarded to Kivu Cargo Services."
add(Case("p04-old-open-then-awarded-rw", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["RW"]}, ["RW"],
         ["status_freshness", "multi_document", "award"], "html", "RFP EXA-CGO-2025-34", PD1,
         [tender("Example Air", "Rwanda", "EXA-CGO-2025-34", PD1, status_quote=PD1),
          claim("tender_status", PD2, {"airline": f("Example Air", PD1), "tender_ref": f("EXA-CGO-2025-34", PD2), "status": f("awarded", PD2)},
                {"tender_ref": True, "status": True})],
         {"opportunities": [opp("EXA-CGO-2025-34", status="awarded", service="GSSA")]},
         published="2025-11-03T08:00:00Z",
         documents=[{"title": "Award EXA-CGO-2025-34", "body": PD2, "published": "2026-10-21T07:00:00Z"}]))

# p05 PDF published in 2022 (date in the PDF's own metadata), title-only status
PE1 = "Request for proposal for the appointment of a cargo general sales and service agent in Mozambique. Sample Airways. Reference SAW-CGO-2022-4."
add(Case("p05-pdf-2022-title-only-mz", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["MZ"]}, ["MZ"],
         ["pdf", "publication_date", "stale"], "pdf", "RFP SAW-CGO-2022-4", PE1,
         [tender("Sample Airways", "Mozambique", "SAW-CGO-2022-4", PE1, status_quote=PE1, gold_status=False)],
         {"opportunities": [opp("SAW-CGO-2022-4", status="historical", service="GSSA", freight_scope="cargo")], "publication_flag": None},
         published="2022-03-14T09:00:00Z",
         notes="The PDF was issued in 2022: historical, and its explanation shows the real age, never 'published -1 days ago'."))

# p06 PDF without a metadata date; the issue date is stated in the notice
PF1 = "Date of issue: 5 October 2026."
PF2 = "Request for proposal: cargo general sales and service agent for Zambia. Example Air. Reference EXA-CGO-2026-51."
add(Case("p06-pdf-issue-date-in-text-zm", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["pdf", "publication_date"], "pdf", "RFP EXA-CGO-2026-51", f"{PF1}\n\n{PF2}",
         [tender("Example Air", "Zambia", "EXA-CGO-2026-51", PF2, status_quote=PF2, gold_status=False)],
         {"opportunities": [opp("EXA-CGO-2026-51", status="announced", service="GSSA", freight_scope="cargo")], "publication_flag": None},
         published=None, extra={"pdf_created": None},
         notes="Recent by its own stated issue date: announced (not open, not historical)."))

# p07 PDF with no date anywhere: the date stays unknown
PG1 = "Request for proposal: cargo general sales and service agent for Malawi. Sample Airways. Reference SAW-CGO-2026-52."
add(Case("p07-pdf-no-date-mw", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["MW"]}, ["MW"],
         ["pdf", "publication_date", "missing_date"], "pdf", "RFP SAW-CGO-2026-52", PG1,
         [tender("Sample Airways", "Malawi", "SAW-CGO-2026-52", PG1, status_quote=PG1, gold_status=False)],
         {"opportunities": [opp("SAW-CGO-2026-52", status="announced", service="GSSA", freight_scope="cargo")], "publication_flag": None},
         published=None, extra={"pdf_created": None},
         notes="No publication date anywhere: unknown, never the retrieval time."))

# p08 HTML page whose publication date lies in the future
PH1 = "Example Air invites proposals from cargo general sales and service agents for Botswana. Reference EXA-CGO-2026-53."
add(Case("p08-future-publication-date-bw", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["BW"]}, ["BW"],
         ["publication_date", "future_date"], "html", "RFP EXA-CGO-2026-53", PH1,
         [tender("Example Air", "Botswana", "EXA-CGO-2026-53", PH1, status_quote=PH1)],
         {"opportunities": [opp("EXA-CGO-2026-53", status="unverified", service="GSSA", freight_scope="cargo")], "publication_flag": "future"},
         published="2027-03-01T08:00:00Z",
         notes="A publication date after retrieval is flagged, not used to call the status current."))

# p09 HTML page with no date: retrieval does not verify the open status
PI1 = "Sample Airways invites proposals from cargo general sales and service agents for Namibia. Reference SAW-CGO-2026-54."
add(Case("p09-no-date-open-na", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["NA"]}, ["NA"],
         ["publication_date", "missing_date"], "html", "RFP SAW-CGO-2026-54", PI1,
         [tender("Sample Airways", "Namibia", "SAW-CGO-2026-54", PI1, status_quote=PI1)],
         {"opportunities": [opp("SAW-CGO-2026-54", status="unverified", service="GSSA", freight_scope="cargo")], "publication_flag": None},
         published=None,
         notes="Open wording of unknown date, no closing date: not verified as currently open."))

# p10 control: recent open notice, no deadline
PJ1 = "Example Air invites proposals from cargo general sales and service agents for Ghana. Reference EXA-CGO-2026-55."
add(Case("p10-recent-open-gh", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["GH"]}, ["GH"],
         ["status_freshness", "control"], "html", "RFP EXA-CGO-2026-55", PJ1,
         [tender("Example Air", "Ghana", "EXA-CGO-2026-55", PJ1, status_quote=PJ1)],
         {"opportunities": [opp("EXA-CGO-2026-55", status="open", service="GSSA", freight_scope="cargo")], "publication_flag": None},
         published="2026-10-12T08:00:00Z"))

# p11 the page's metadata date and its own stated publication date disagree
PK1 = "Published: 12 March 2024."
PK2 = "Sample Airways invites proposals from cargo general sales and service agents for Senegal. Reference SAW-CGO-2024-9."
add(Case("p11-inconsistent-publication-dates-sn", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["SN"]}, ["SN"],
         ["publication_date", "inconsistent_date"], "html", "RFP SAW-CGO-2024-9", f"{PK1}\n\n{PK2}",
         [tender("Sample Airways", "Senegal", "SAW-CGO-2024-9", PK2, status_quote=PK2)],
         {"opportunities": [opp("SAW-CGO-2024-9", status="unverified", service="GSSA", freight_scope="cargo")], "publication_flag": "inconsistent"},
         published="2026-10-20T08:00:00Z",
         notes="Metadata says October 2026, the notice says March 2024: flagged; the status is not called current."))

# p12 freighter route launch without trucking scope
PL1 = "Example Cargo will start a twice-weekly Boeing 777 freighter service between Dubai and Nairobi from 4 January 2027."
add(Case("p12-freighter-route-launch", "heldout6", "en", "capacity_lanes", {"geo_mode": "countries", "countries": ["AE", "KE"]}, ["AE", "KE"],
         ["capacity", "route_area"], "html", "Example Cargo adds Dubai-Nairobi freighter", PL1,
         [claim("route_launch", PL1, {"airline": f("Example Cargo", PL1), "origin": f("United Arab Emirates", PL1), "destination": f("Kenya", PL1)},
                {"airline": True, "origin": True, "destination": True})],
         {"opportunities": [], "signal_expected": "capacity_lanes"}))

# p13 passenger lot rejected before field validation, cargo lot an opportunity
PM0 = "Sample Airways invites proposals for two separate lots."
PM1 = "Lot A: passenger sales and ticketing agent in Kenya. Reference SAW-PAX-2027-8. Proposals are due on 15 April 2027."
PM2 = "Lot B: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-9. Proposals are due on 15 April 2027."
add(Case("p13-passenger-lot-kept-as-excluded-ke", "heldout6", "en", "airline_representation", KE, ["KE"],
         ["freight_relevance", "multi_lot"], "html", "Request for proposals: sales agents, Kenya (two lots)", f"{PM0}\n\n{PM1}\n\n{PM2}",
         [tender("Sample Airways", "Kenya", "SAW-PAX-2027-8", PM1, status_quote=PM1, deadline=("2027-04-15", PM1)),
          tender("Sample Airways", "Kenya", "SAW-CGO-2027-9", PM2, status_quote=PM2, deadline=("2027-04-15", PM2))],
         {"opportunities": [opp("SAW-CGO-2027-9", day="2027-04-15", precision="date", service="GSSA", freight_scope="cargo")],
          "excluded": [{"scope": "passenger", "ref": "SAW-PAX-2027-8"}]},
         notes="Lot A stays inspectable as excluded evidence with its reason; lot B is the opportunity."))

# p14 two notices of the same airline: one passenger, one cargo
PN1 = "Example Air invites proposals for a passenger general sales agent in Uganda. Reference EXA-PAX-2027-20. Proposals are due on 1 May 2027."
PN2 = "Example Air invites proposals for a cargo general sales and service agent in Uganda. Reference EXA-CGO-2027-21. Proposals are due on 1 May 2027."
add(Case("p14-same-airline-two-notices-ug", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["freight_relevance", "multi_document", "same_airline"], "html", "RFP EXA-PAX-2027-20", PN1,
         [tender("Example Air", "Uganda", "EXA-PAX-2027-20", PN1, status_quote=PN1, deadline=("2027-05-01", PN1)),
          tender("Example Air", "Uganda", "EXA-CGO-2027-21", PN2, status_quote=PN2, deadline=("2027-05-01", PN2))],
         {"opportunities": [opp("EXA-CGO-2027-21", day="2027-05-01", precision="date", service="GSSA", freight_scope="cargo")],
          "excluded": [{"scope": "passenger", "ref": "EXA-PAX-2027-20"}]},
         documents=[{"title": "RFP EXA-CGO-2027-21", "body": PN2, "published": "2026-10-20T08:00:00Z"}]))

# p15 mixed passenger and cargo handling: held for review
PO1 = "Example Air invites tenders for passenger and cargo ground handling at Lusaka, Zambia. Reference EXA-HDL-2027-22. Bids are due on 30 January 2027."
add(Case("p15-mixed-handling-zm", "heldout6", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["freight_relevance", "mixed_scope"], "html", "Tender EXA-HDL-2027-22", PO1,
         [tender("Example Air", "Zambia", "EXA-HDL-2027-22", PO1, status_quote=PO1, deadline=("2027-01-30", PO1), ctype="service_tender", service="HANDLING")],
         {"opportunities": [opp("EXA-HDL-2027-22", day="2027-01-30", precision="date", service="HANDLING", freight_scope="mixed")]}))

# p16 a recent query deadline does not renew an old open assertion and is not the proposal deadline
PP1 = "Sample Airways invites proposals from cargo GSSA providers for Ethiopia. Reference SAW-CGO-2026-40."
PP2 = "Questions about SAW-CGO-2026-40 may be sent until 10 November 2026."
add(Case("p16-old-open-plus-query-deadline-et", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["ET"]}, ["ET"],
         ["status_freshness", "multi_document", "query_deadline"], "html", "RFP SAW-CGO-2026-40", PP1,
         [tender("Sample Airways", "Ethiopia", "SAW-CGO-2026-40", PP1, status_quote=PP1),
          claim("tender_deadline", PP2, {"airline": f("Sample Airways", PP1), "tender_ref": f("SAW-CGO-2026-40", PP2), "deadline": f("2026-11-10", PP2)},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("SAW-CGO-2026-40", status="unverified", service="GSSA", freight_scope="cargo")]},
         published="2026-04-10T08:00:00Z",
         documents=[{"title": "Clarifications SAW-CGO-2026-40", "body": PP2, "published": "2026-10-23T07:00:00Z"}]))

# p17 ambiguous numeric date: the deadline waits for review
PQ1 = "Example Air invites proposals from cargo general sales and service agents for Zimbabwe. Reference EXA-CGO-2026-57."
PQ2 = "Closing date: 05/04/2027."
add(Case("p17-ambiguous-numeric-deadline-zw", "heldout6", "en", "airline_representation", {"geo_mode": "country", "countries": ["ZW"]}, ["ZW"],
         ["ambiguous_date"], "html", "RFP EXA-CGO-2026-57", f"{PQ1}\n\n{PQ2}",
         [tender("Example Air", "Zimbabwe", "EXA-CGO-2026-57", PQ1, status_quote=PQ1, deadline=("2027-04-05", PQ2), gold_deadline=False)],
         {"opportunities": [opp("EXA-CGO-2026-57", status="open", service="GSSA", freight_scope="cargo")]},
         published="2026-10-15T08:00:00Z",
         notes="05/04/2027 has no day/month convention in the notice: it waits for a person, never a fact."))


def heldout6_cases() -> list[Case]:
    return list(HELDOUT6)
