"""The reviewed evaluation set (26 Oct 2026, evening, item 4).

PROVENANCE: every notice below was AUTHORED for this build in the form of real airline and procurement notices
(request-for-proposal pages, corrigenda, award notices, newsroom items, tabular tender listings, PDF notices, in
English, French, Spanish, Portuguese and German). None is a genuine notice: no public portal was reachable from the
build environment and no authorised source was supplied. Replace or extend with genuine notices (same shape) before
treating the measured numbers as real-world quality.

Each case gives: the document (HTML, HTML table or PDF), what a plausible extractor proposes for it (correct and
incorrect readings alike, as a model would), and the GOLD labels a reviewer established by reading the notice:
- `opportunities`: the opportunities a careful reader finds (empty when the notice is cancelled, historical or
  not a procurement), with their reference, status, deadline day and precision;
- per proposed field, whether the notice really states the value (`supported` True/False);
- whether the document must be read completely (long notices), and the expected extraction status.

SPLITS: `tuning` cases were used while adjusting the validation rules; `heldout` cases were written before the final
rule changes and were run once, at the end, without changing any rule afterwards.

LABELS v4 (27 Oct 2026, fifth instruction, item 4): one policy for terminal-only records. A cancellation, award or closure
of a tender that is not already tracked is kept as HISTORICAL INTELLIGENCE (a tender record with the terminal status,
outside the actionable pipeline and the live counts), never created as an opportunity. Labels that expected a terminal
opportunity (t04, t15, h04, j04 in notices.py; m10 in heldout4.py) or nothing at all (g09 in genuine.py, k12 in heldout3.py) now expect a
`historical` record instead. Previous results are kept in the release evidence.

LABELS v3 (27 Oct 2026, third instruction, item 3): a procurement heading ("request for proposal", "RFP",
"convocatoria", "licitación") establishes that a notice exists, not that it is open. The two t07 status labels quote only
"Each line is a separate request for proposal." and are therefore relabelled as not stated (was: stated). The
"open procurements" wording sits in a different, unquoted sentence. The Spanish/Portuguese verb "convoca" ("calls a
tender", like "invites") remains active wording, so t10, t16 and h07 keep their labels. The rules were corrected to
match. Earlier label versions' results are kept in the release evidence for comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Capability areas discovery can feed from public notices, and the three fed by WFC's own records.
DISCOVERY_AREAS = ("airline_representation", "outsourcing_training", "trucking_gateways", "technology_solutions", "capacity_lanes",
                   "network_development")
INTERNAL_AREAS = ("account_growth", "forwarder_sales", "service_operations")


@dataclass
class Case:
    id: str
    split: str                      # tuning | heldout
    language: str
    module: str                     # the capability area the notice concerns
    search: dict[str, Any]          # geo_mode, countries, regions
    coverage: list[str]             # the source's country coverage
    categories: list[str]
    content_type: str               # html | html-table | pdf
    title: str
    body: str                       # paragraphs separated by blank lines; a table case uses `table_rows`
    proposals: list[dict[str, Any]]
    gold: dict[str, Any]
    published: str | None = "2026-10-20T08:00:00Z"
    table_rows: list[list[str]] | None = None
    long: bool = False
    notes: str = ""
    expect_status: str = "extracted"     # extraction status after one run (incomplete for a budget-stopped long document)
    extra: dict[str, Any] = field(default_factory=dict)
    # Further documents of the same source, served after the main one (27 Oct 2026, fourth instruction): each a dict with
    # `title`, `body`, `published` (None = no date metadata), `content_type` ('html' or 'pdf') and optionally `pdf_created`.
    # Their proposals are listed in `proposals` with the others; the scripted extractor returns each where its quote appears.
    documents: list[dict[str, Any]] = field(default_factory=list)


def f(value: str, quote: str) -> dict[str, str]:
    return {"value": value, "quote": quote}


def claim(ctype: str, quote: str, fields: dict[str, dict[str, str]], gold: dict[str, bool], *, stance: str = "supports",
          tz: str | None = None) -> dict[str, Any]:
    """An extractor proposal plus the gold support label of each field."""
    out: dict[str, Any] = {"claim_type": ctype, "stance": stance, "quote": quote, "fields": fields, "gold": gold}
    if tz:
        out["deadline_timezone"] = tz
    return out


def opp(ref: str | None, *, status: str = "open", day: str | None = None, precision: str | None = None, service: str | None = None,
        title_contains: str | None = None, freight_scope: str | None = None) -> dict[str, Any]:
    """`freight_scope` (27 Oct, second instruction): 'cargo', 'mixed' or 'unclear' when the gold asserts it; None = not asserted."""
    return {"ref": ref, "status": status, "deadline_day": day, "deadline_precision": precision, "service": service, "title_contains": title_contains,
            "freight_scope": freight_scope}


CASES: list[Case] = []


def add(c: Case) -> Case:
    CASES.append(c)
    return c


# ============================================================================ TUNING SET
# ---- airline representation (GSSA), one country, plain notice, English
A1 = "Example Air invites proposals from general sales and service agents (GSSA) for cargo sales representation in Kenya."
A1R = "Tender reference EXA-GSSA-2026-101."
A1D = "Proposals must be submitted by 30 November 2026 at 17:00 EAT."
A1E = "Bidders must have at least five years of GSSA experience and an annual turnover of not less than USD 2 million."
add(Case("t01-gssa-ke", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["plain", "eligibility_numeric"], "html", "Request for Proposal: GSSA services, Kenya",
         f"{A1}\n\n{A1R}\n\n{A1D}\n\n{A1E}",
         [claim("gssa_tender", A1, {"airline": f("Example Air", A1), "country": f("Kenya", A1), "service": f("GSSA", A1), "status": f("open", A1),
                                     "tender_ref": f("EXA-GSSA-2026-101", A1R), "deadline": f("2026-11-30T17:00:00", A1D)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Africa/Nairobi"),
          claim("eligibility", A1E, {"airline": f("Example Air", A1), "eligibility": f("at least 5 years of GSSA experience and an annual turnover of not less than USD 2 million", A1E),
                                     "tender_ref": f("EXA-GSSA-2026-101", A1R)}, {"eligibility": True, "tender_ref": True}),
          # a wrong reading an extractor could produce: minimum turned into a maximum
          claim("eligibility", A1E, {"airline": f("Example Air", A1), "eligibility": f("a maximum of 5 years of GSSA experience", A1E),
                                     "tender_ref": f("EXA-GSSA-2026-101", A1R)}, {"eligibility": False, "tender_ref": True})],
         {"opportunities": [opp("EXA-GSSA-2026-101", day="2026-11-30", precision="instant", service="GSSA")]}))

# ---- two opportunities in one document (two lots, two references)
B1 = "Sample Airways invites bids for two separate contracts."
B2 = "Lot 1: general sales agent (GSA) representation for cargo in Uganda. Tender reference SAW-GSA-2026-21. Bids are due on 10 December 2026."
B3 = "Lot 2: cargo handling services at Entebbe in Uganda. Tender reference SAW-HDL-2026-22. Bids are due on 17 December 2026."
add(Case("t02-two-lots-ug", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["multi_opportunity"], "html", "Invitation to bid: two lots, Uganda", f"{B1}\n\n{B2}\n\n{B3}",
         [claim("gssa_tender", B2, {"airline": f("Sample Airways", B1), "country": f("Uganda", B2), "service": f("GSSA", B2), "status": f("open", B2),
                                     "tender_ref": f("SAW-GSA-2026-21", B2), "deadline": f("2026-12-10", B2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("service_tender", B3, {"airline": f("Sample Airways", B1), "country": f("Uganda", B3), "service": f("HANDLING", B3), "status": f("open", B3),
                                        "tender_ref": f("SAW-HDL-2026-22", B3), "deadline": f("2026-12-17", B3)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          # wrong: the lot-1 deadline attached to lot 2
          claim("tender_deadline", B3, {"airline": f("Sample Airways", B1), "tender_ref": f("SAW-HDL-2026-22", B3), "deadline": f("2026-12-10", B3)},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("SAW-GSA-2026-21", day="2026-12-10", precision="date", service="GSSA"),
                            opp("SAW-HDL-2026-22", day="2026-12-17", precision="date", service="HANDLING")]}))

# ---- corrigendum / amendment: deadline extended
C1 = "Corrigendum No. 1 to tender EXA-GSSA-2026-101 (GSSA services, Kenya)."
C2 = "The deadline for proposals is extended from 30 November 2026 to 14 December 2026 at 17:00 EAT. All other terms remain unchanged."
add(Case("t03-corrigendum-ke", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["amendment"], "html", "Corrigendum No. 1: EXA-GSSA-2026-101", f"{C1}\n\n{C2}",
         [claim("tender_status", C2, {"airline": f("Example Air", C1), "tender_ref": f("EXA-GSSA-2026-101", C1), "status": f("revised", C2),
                                       "deadline": f("2026-12-14T17:00:00", C2)}, {"tender_ref": True, "status": True, "deadline": True}, tz="Africa/Nairobi"),
          # wrong: the OLD deadline read as the current one
          claim("tender_deadline", C2, {"airline": f("Example Air", C1), "tender_ref": f("EXA-GSSA-2026-101", C1), "deadline": f("2026-11-30T17:00:00", C2)},
                {"tender_ref": True, "deadline": False}, tz="Africa/Nairobi")],
         {"opportunities": [], "follower_only": True}, notes="A corrigendum alone announces nothing; it revises an existing tender."))

# ---- cancellation: no opportunity
D1 = "Example Air invites proposals from GSSA providers for cargo sales representation in Tanzania. Tender reference EXA-GSSA-2026-102."
D2 = "Update of 18 October 2026: this tender has been cancelled. No proposals will be evaluated and no contract will be awarded."
add(Case("t04-cancelled-tz", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["TZ"]}, ["TZ"],
         ["cancellation", "conflicting_statements"], "html", "RFP EXA-GSSA-2026-102 (cancelled)", f"{D1}\n\n{D2}",
         [claim("gssa_tender", D1, {"airline": f("Example Air", D1), "country": f("Tanzania", D1), "service": f("GSSA", D1), "status": f("open", D1),
                                     "tender_ref": f("EXA-GSSA-2026-102", D1)}, {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True}),
          claim("tender_status", D2, {"airline": f("Example Air", D1), "tender_ref": f("EXA-GSSA-2026-102", D1), "status": f("cancelled", D2)},
                {"tender_ref": True, "status": True})],
         {"opportunities": [], "historical": [{"ref": "EXA-GSSA-2026-102", "status": "cancelled"}], "contradictory_document": True},
         notes="Announcement and cancellation in one document: the record exists for history but is never shown as open."))

# ---- historical reference inside a current notice
E1 = "Coastal Air Cargo invites proposals for the appointment of a GSSA for Ghana. Tender reference CAC-GH-2026-07."
E2 = "The previous GSSA contract, awarded in 2021 under tender CAC-GH-2021-02, expires on 31 March 2027. Proposals are due by 20 January 2027."
add(Case("t05-historical-gh", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["GH"]}, ["GH"],
         ["historical_reference"], "html", "RFP CAC-GH-2026-07: GSSA Ghana", f"{E1}\n\n{E2}",
         [claim("gssa_tender", E1, {"airline": f("Coastal Air Cargo", E1), "country": f("Ghana", E1), "service": f("GSSA", E1), "status": f("open", E1),
                                     "tender_ref": f("CAC-GH-2026-07", E1), "deadline": f("2027-01-20", E2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          # wrong: the 2021 award read as this tender's status
          claim("tender_status", E2, {"airline": f("Coastal Air Cargo", E1), "tender_ref": f("CAC-GH-2026-07", E1), "status": f("awarded", E2)},
                {"tender_ref": True, "status": False}),
          # wrong: the contract expiry read as the deadline
          claim("tender_deadline", E2, {"airline": f("Coastal Air Cargo", E1), "tender_ref": f("CAC-GH-2026-07", E1), "deadline": f("2027-03-31", E2)},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("CAC-GH-2026-07", day="2027-01-20", precision="date", service="GSSA")]}))

# ---- complex eligibility: country roles, conditions, two quantities, inclusive date
F1 = "Blue Nile Cargo invites proposals from GSSA providers for Ethiopia. Tender reference BNC-ET-2026-3. Proposals are due on 5 January 2027."
F2 = ("Applicants based in Ethiopia must hold an ECAA licence; applicants based outside Ethiopia must hold a licence if operating in Djibouti. "
      "Applicants must have three years of insurance cover and five years of GSSA experience, and a certificate valid by 1 January 2027.")
add(Case("t06-eligibility-complex-et", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["ET"]}, ["ET"],
         ["eligibility_complex", "eligibility_roles", "eligibility_dates"], "html", "RFP BNC-ET-2026-3: GSSA Ethiopia", f"{F1}\n\n{F2}",
         [claim("gssa_tender", F1, {"airline": f("Blue Nile Cargo", F1), "country": f("Ethiopia", F1), "service": f("GSSA", F1), "status": f("open", F1),
                                     "tender_ref": f("BNC-ET-2026-3", F1), "deadline": f("2027-01-05", F1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", F2, {"airline": f("Blue Nile Cargo", F1), "tender_ref": f("BNC-ET-2026-3", F1),
                                    "eligibility": f("three years of insurance cover and five years of GSSA experience", F2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", F2, {"airline": f("Blue Nile Cargo", F1), "tender_ref": f("BNC-ET-2026-3", F1),
                                    "eligibility": f("five years of insurance cover and three years of GSSA experience", F2)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", F2, {"airline": f("Blue Nile Cargo", F1), "tender_ref": f("BNC-ET-2026-3", F1),
                                    "eligibility": f("applicants based in Djibouti must hold a licence if operating outside Ethiopia", F2)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", F2, {"airline": f("Blue Nile Cargo", F1), "tender_ref": f("BNC-ET-2026-3", F1),
                                    "eligibility": f("a certificate valid before 1 January 2027", F2)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", F2, {"airline": f("Blue Nile Cargo", F1), "tender_ref": f("BNC-ET-2026-3", F1),
                                    "eligibility": f("a certificate valid by 1 January 2027", F2)},
                {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("BNC-ET-2026-3", day="2027-01-05", precision="date", service="GSSA")]}))

# ---- table listing (HTML table): reference, service, country, deadline in cells
add(Case("t07-table-gcc", "tuning", "en", "outsourcing_training", {"geo_mode": "region", "countries": [], "regions": ["GCC"]}, ["AE", "OM", "QA"],
         ["table", "multi_opportunity"], "html-table", "Current tenders: Gulf Freight Services",
         "Gulf Freight Services publishes its open procurements below. Each line is a separate request for proposal.",
         [claim("service_tender", "GFS-HDL-2026-9 | Cargo handling at Muscat | Oman | 12 December 2026",
                {"organisation": f("Gulf Freight Services", "Gulf Freight Services publishes its open procurements below."),
                 "country": f("Oman", "GFS-HDL-2026-9 | Cargo handling at Muscat | Oman | 12 December 2026"), "service": f("HANDLING", "GFS-HDL-2026-9 | Cargo handling at Muscat"),
                 "status": f("open", "Each line is a separate request for proposal."), "tender_ref": f("GFS-HDL-2026-9", "GFS-HDL-2026-9 | Cargo handling at Muscat"),
                 "deadline": f("2026-12-12", "GFS-HDL-2026-9 | Cargo handling at Muscat | Oman | 12 December 2026")},
                {"organisation": True, "country": True, "service": True, "status": False, "tender_ref": True, "deadline": True}),
          claim("service_tender", "GFS-TRN-2026-10 | Dangerous goods training | Doha, Qatar | 19 December 2026",
                {"organisation": f("Gulf Freight Services", "Gulf Freight Services publishes its open procurements below."),
                 "country": f("Qatar", "GFS-TRN-2026-10 | Dangerous goods training | Doha, Qatar | 19 December 2026"), "service": f("TRAINING", "GFS-TRN-2026-10 | Dangerous goods training"),
                 "status": f("open", "Each line is a separate request for proposal."), "tender_ref": f("GFS-TRN-2026-10", "GFS-TRN-2026-10 | Dangerous goods training"),
                 "deadline": f("2026-12-19", "GFS-TRN-2026-10 | Dangerous goods training | Doha, Qatar | 19 December 2026")},
                {"organisation": True, "country": True, "service": True, "status": False, "tender_ref": True, "deadline": True}),
          # wrong: Qatar's deadline attached to the Oman lot
          claim("tender_deadline", "GFS-HDL-2026-9 | Cargo handling at Muscat | Oman | 12 December 2026",
                {"organisation": f("Gulf Freight Services", "Gulf Freight Services publishes its open procurements below."),
                 "tender_ref": f("GFS-HDL-2026-9", "GFS-HDL-2026-9 | Cargo handling at Muscat"), "deadline": f("2026-12-19", "GFS-HDL-2026-9 | Cargo handling at Muscat | Oman | 12 December 2026")},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("GFS-HDL-2026-9", day="2026-12-12", precision="date", service="HANDLING"),
                            opp("GFS-TRN-2026-10", day="2026-12-19", precision="date", service="TRAINING")]},
         table_rows=[["Reference", "Subject", "Location", "Closing date"],
                     ["GFS-HDL-2026-9", "Cargo handling at Muscat", "Oman", "12 December 2026"],
                     ["GFS-TRN-2026-10", "Dangerous goods training", "Doha, Qatar", "19 December 2026"]]))

# ---- PDF notice, trucking, several countries search
G1 = "Sample Airways requests quotations for road feeder trucking services between Dubai and Abu Dhabi in the United Arab Emirates."
G2 = "Reference SAW-RFS-2026-07. Quotations must be submitted by 5 December 2026 at 16:00 GST."
G3 = "Bidders must operate a fleet of at least 10 trucks and hold a valid UAE road transport licence."
add(Case("t08-pdf-trucking-ae", "tuning", "en", "trucking_gateways", {"geo_mode": "countries", "countries": ["AE", "SA"]}, ["AE"],
         ["pdf", "eligibility_numeric"], "pdf", "RFQ SAW-RFS-2026-07", f"{G1}\n\n{G2}\n\n{G3}",
         [claim("service_tender", G1, {"airline": f("Sample Airways", G1), "country": f("United Arab Emirates", G1), "service": f("TRUCKING", G1),
                                        "status": f("open", G2), "tender_ref": f("SAW-RFS-2026-07", G2), "deadline": f("2026-12-05T16:00:00", G2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Asia/Dubai"),
          claim("eligibility", G3, {"airline": f("Sample Airways", G1), "tender_ref": f("SAW-RFS-2026-07", G2),
                                    "eligibility": f("a fleet of at least 10 trucks and a valid UAE road transport licence", G3)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", G3, {"airline": f("Sample Airways", G1), "tender_ref": f("SAW-RFS-2026-07", G2),
                                    "eligibility": f("a fleet of at least 100 trucks", G3)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("SAW-RFS-2026-07", day="2026-12-05", precision="instant", service="TRUCKING")]}))

# ---- French notice, training, missing deadline
H1 = "Sample Airways lance un appel d'offres pour la formation du personnel cargo en Côte d'Ivoire."
H2 = "Référence de l'appel d'offres : SAW-FORM-2026-04. La date limite de dépôt des offres sera communiquée ultérieurement."
add(Case("t09-fr-training-no-deadline", "tuning", "fr", "outsourcing_training", {"geo_mode": "country", "countries": ["CI"]}, ["CI"],
         ["language_fr", "missing_deadline"], "html", "Appel d'offres SAW-FORM-2026-04", f"{H1}\n\n{H2}",
         [claim("service_tender", H1, {"airline": f("Sample Airways", H1), "country": f("Côte d'Ivoire", H1), "service": f("TRAINING", H1),
                                        "status": f("open", H1), "tender_ref": f("SAW-FORM-2026-04", H2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True}),
          # wrong: a deadline invented where the notice says it will be announced later
          claim("tender_deadline", H2, {"airline": f("Sample Airways", H1), "tender_ref": f("SAW-FORM-2026-04", H2), "deadline": f("2026-12-31", H2)},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("SAW-FORM-2026-04", day=None, precision=None, service="TRAINING")]}, extra={"lang": "fr"}))

# ---- Spanish notice, technology, time zone unclear
I1 = "Aerolínea Andina convoca una licitación para una plataforma de software de gestión de carga en Colombia."
I2 = "Referencia AND-TEC-2026-5. Las propuestas deben presentarse antes del 15 de enero de 2027 a las 18:00 horas."
add(Case("t10-es-technology-tz-unclear", "tuning", "es", "technology_solutions", {"geo_mode": "country", "countries": ["CO"]}, ["CO"],
         ["language_es", "timezone_unclear"], "html", "Licitación AND-TEC-2026-5", f"{I1}\n\n{I2}",
         [claim("service_tender", I1, {"airline": f("Aerolínea Andina", I1), "country": f("Colombia", I1), "service": f("TECHNOLOGY", I1),
                                        "status": f("open", I1), "tender_ref": f("AND-TEC-2026-5", I2), "deadline": f("2027-01-15T18:00:00", I2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="America/Bogota")],
         {"opportunities": [opp("AND-TEC-2026-5", day="2027-01-15", precision="local_time", service="TECHNOLOGY")]},
         notes="18:00 without a zone: local time, never an exact instant; the extractor's zone is an assumption.", extra={"lang": "es"}))

# ---- conflicting statements: two deadlines in one notice
J1 = "Example Air invites proposals for cargo handling services at Kigali in Rwanda. Tender reference EXA-HDL-2026-31."
J2 = "Proposals are due on 8 December 2026. The closing date for proposals is 12 December 2026."
add(Case("t11-conflicting-deadlines-rw", "tuning", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["RW"]}, ["RW"],
         ["conflicting_statements"], "html", "RFP EXA-HDL-2026-31", f"{J1}\n\n{J2}",
         [claim("service_tender", J1, {"airline": f("Example Air", J1), "country": f("Rwanda", J1), "service": f("HANDLING", J1), "status": f("open", J1),
                                        "tender_ref": f("EXA-HDL-2026-31", J1), "deadline": f("2026-12-08", "Proposals are due on 8 December 2026.")},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_deadline", J2, {"airline": f("Example Air", J1), "tender_ref": f("EXA-HDL-2026-31", J1),
                                        "deadline": f("2026-12-12", "The closing date for proposals is 12 December 2026.")}, {"tender_ref": True, "deadline": True})],
         {"opportunities": [opp("EXA-HDL-2026-31", day=None, precision=None, service="HANDLING")], "deadline_conflict": True},
         notes="Both dates are stated; the system must show the conflict, not pick one."))

# ---- capacity statement (capacity and trade lanes), worldwide search
K1 = "Northern Cargo Airlines adds a third weekly freighter frequency between Frankfurt and Nairobi, lifting capacity on the lane to 300 tonnes per week."
add(Case("t12-capacity-worldwide", "tuning", "en", "capacity_lanes", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["DE", "KE"],
         ["capacity", "worldwide"], "html", "Northern Cargo Airlines expands Frankfurt–Nairobi", K1,
         [claim("capacity_statement", K1, {"airline": f("Northern Cargo Airlines", K1), "origin": f("Germany", K1), "destination": f("Kenya", K1)},
                {"airline": True, "origin": True, "destination": True}),        # Frankfurt and Nairobi resolve through the city register
          # wrong: a capacity statement is not a tender
          claim("gssa_tender", K1, {"airline": f("Northern Cargo Airlines", K1), "country": f("Kenya", K1), "service": f("GSSA", K1), "status": f("open", K1)},
                {"airline": True, "country": False, "service": False, "status": False})],
         {"opportunities": [], "signal_expected": "capacity_lanes"}, notes="A capacity change is a research item for capacity lanes, not a tender."))

# ---- partnership (network development)
L1 = "Coastal Handling has signed a partnership agreement with a cargo terminal operator in Oman covering export handling at Muscat."
add(Case("t13-partnership-om", "tuning", "en", "network_development", {"geo_mode": "country", "countries": ["OM"]}, ["OM"],
         ["partnership"], "html", "Coastal Handling partners in Oman", L1,
         [claim("partnership", L1, {"organisation": f("Coastal Handling", L1), "country": f("Oman", L1)}, {"organisation": True, "country": True})],
         {"opportunities": [], "signal_expected": "network_development"}))

# ---- long PDF notice (sections, resume): announcement first, reference and deadline last
LONG_A = "Mauritius Cargo Airways invites proposals from GSSA providers for cargo sales and service representation in Mauritius."
LONG_Z = "Tender reference MCA-GSSA-2027-01. Proposals are due on 15 January 2027."
LONG_BODY = LONG_A + "\n\n" + "\n\n".join(f"Clause {i}. General conditions of contract: the selected provider shall comply with all applicable aviation "
                                           f"security, customs and data protection rules, maintain accurate records, report monthly on sales performance "
                                           f"and cooperate with audits requested by the airline (clause {i})." for i in range(1, 221)) + "\n\n" + LONG_Z
add(Case("t14-long-pdf-mu", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["MU"]}, ["MU"],
         ["long_document", "pdf"], "pdf", "RFP MCA-GSSA-2027-01", LONG_BODY,
         [claim("gssa_tender", LONG_A, {"airline": f("Mauritius Cargo Airways", LONG_A), "country": f("Mauritius", LONG_A), "service": f("GSSA", LONG_A),
                                         "status": f("open", LONG_A)}, {"airline": True, "country": True, "service": True, "status": True}),
          claim("tender_deadline", LONG_Z, {"airline": f("Mauritius Cargo Airways", LONG_A), "tender_ref": f("MCA-GSSA-2027-01", "Tender reference MCA-GSSA-2027-01."),
                                            "deadline": f("2027-01-15", "Proposals are due on 15 January 2027.")}, {"tender_ref": True, "deadline": True})],
         {"opportunities": [opp("MCA-GSSA-2027-01", day="2027-01-15", precision="date", service="GSSA")]}, long=True,
         notes="With a small per-run cap the run stops after two sections: the document is incomplete and the deadline is not yet found."))

# ---- award notice (closed): no opportunity
M1 = "Example Air announces the outcome of tender EXA-GSSA-2026-090 for GSSA services in Zambia: the contract has been awarded to Lusaka Cargo Agents."
add(Case("t15-award-zm", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["award", "historical_reference"], "html", "Award notice EXA-GSSA-2026-090", M1,
         [claim("gssa_tender", M1, {"airline": f("Example Air", M1), "country": f("Zambia", M1), "service": f("GSSA", M1), "status": f("open", M1),
                                     "tender_ref": f("EXA-GSSA-2026-090", M1)}, {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True}),
          claim("tender_status", M1, {"airline": f("Example Air", M1), "tender_ref": f("EXA-GSSA-2026-090", M1), "status": f("awarded", M1)},
                {"tender_ref": True, "status": True})],
         {"opportunities": [], "historical": [{"ref": "EXA-GSSA-2026-090", "status": "awarded"}]}, notes="An award notice: kept as historical intelligence (status 'awarded'), never an actionable opportunity."))

# ---- Portuguese, handling, several countries
N1 = "A Transportadora Atlântica convoca propostas para serviços de handling de carga em Luanda, Angola."
N2 = "Referência TAT-HDL-2026-2. As propostas devem ser entregues até 20 de dezembro de 2026."
add(Case("t16-pt-handling-ao", "tuning", "pt", "outsourcing_training", {"geo_mode": "countries", "countries": ["AO", "MZ"]}, ["AO"],
         ["language_pt"], "html", "Concurso TAT-HDL-2026-2", f"{N1}\n\n{N2}",
         [claim("service_tender", N1, {"airline": f("Transportadora Atlântica", N1), "country": f("Angola", N1), "service": f("HANDLING", N1),
                                        "status": f("open", N1), "tender_ref": f("TAT-HDL-2026-2", N2), "deadline": f("2026-12-20", N2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("TAT-HDL-2026-2", day="2026-12-20", precision="date", service="HANDLING")]}, extra={"lang": "pt"}))

# ---- not a procurement (newsroom item about a forwarder's results): no opportunity, forwarder sales area
O1 = "Horizon Forwarding reports a 12% rise in air export tonnage from Kenya in the third quarter and plans to open a sales office in Mombasa."
add(Case("t17-forwarder-news-ke", "tuning", "en", "forwarder_sales", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["not_procurement", "internal_area"], "html", "Horizon Forwarding Q3 update", O1,
         [claim("service_tender", O1, {"organisation": f("Horizon Forwarding", O1), "country": f("Kenya", O1), "service": f("HANDLING", O1), "status": f("open", O1)},
                {"organisation": True, "country": True, "service": False, "status": False})],
         {"opportunities": []}, notes="Forwarder sales is fed by WFC's own booking and account records, not by public notices."))

# ---- German notice, GSSA, EU region search
P1 = "Alpen Luftfracht schreibt die Bestellung eines General Sales and Service Agent (GSSA) für Luftfracht in Österreich aus."
P2 = "Referenz ALF-GSSA-2026-8. Angebote sind bis spätestens 9. Januar 2027, 12:00 Uhr MEZ einzureichen."
add(Case("t18-de-gssa-at", "tuning", "de", "airline_representation", {"geo_mode": "region", "countries": [], "regions": ["EU"]}, ["AT"],
         ["language_de"], "html", "Ausschreibung ALF-GSSA-2026-8", f"{P1}\n\n{P2}",
         [claim("gssa_tender", P1, {"airline": f("Alpen Luftfracht", P1), "country": f("Austria", P1), "service": f("GSSA", P1), "status": f("open", P2),
                                     "tender_ref": f("ALF-GSSA-2026-8", P2), "deadline": f("2027-01-09T12:00:00", P2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Europe/Vienna")],
         {"opportunities": [opp("ALF-GSSA-2026-8", day="2027-01-09", precision="instant", service="GSSA")]}, extra={"lang": "de"},
         notes="German announcement wording ('schreibt ... aus', 'bis spätestens') is not in the English lexicons: a known gap, measured here."))

# ---- operations notice (service operations area): not an opportunity
Q1 = "Example Air advises that cargo acceptance at Nairobi will close two hours earlier on 24 and 25 December 2026 because of reduced warehouse staffing."
add(Case("t19-ops-notice-ke", "tuning", "en", "service_operations", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["not_procurement", "internal_area"], "html", "Operational notice: Nairobi cargo acceptance", Q1,
         [claim("service_tender", Q1, {"airline": f("Example Air", Q1), "country": f("Kenya", Q1), "service": f("HANDLING", Q1), "status": f("open", Q1)},
                {"airline": True, "country": True, "service": False, "status": False})],
         {"opportunities": []}, notes="Service and operations is fed by WFC's operational records; a public notice is at most context."))

# ---- account growth: an airline newsroom item about a key account, not a procurement
R1 = "Sample Airways and Horizon Forwarding extend their block space agreement on the Dubai–Nairobi lane for a further two years."
add(Case("t20-account-growth-ae", "tuning", "en", "account_growth", {"geo_mode": "countries", "countries": ["AE", "KE"]}, ["AE"],
         ["not_procurement", "internal_area", "partnership"], "html", "Block space agreement extended", R1,
         [claim("partnership", R1, {"organisation": f("Sample Airways", R1), "country": f("Kenya", R1)}, {"organisation": True, "country": True})],
         {"opportunities": [], "signal_expected": "network_development"},
         notes="Account growth uses WFC's own revenue records; the notice is a network-development research item at most."))


# ============================================================================ FORMER HELD-OUT SET (release 3.1.0-wfc.3)
# Run once as held-out on 26 Oct 2026; its findings were then fixed (27 Oct, item 3), so these cases are now regression
# (tuning) material. The fresh held-out set for this release is HELD-OUT 2 below.
HA1 = "Island Freight Airways invites proposals from general sales agents for cargo representation in Seychelles. Tender reference IFA-GSA-2026-4."
HA2 = "Proposals must be received no later than 22 December 2026 at 15:00 SCT."
HA3 = ("Bidders registered in Seychelles must hold a Seychelles Civil Aviation Authority licence; bidders registered outside Seychelles must hold an "
       "equivalent licence if operating in Mauritius. Bidders must have two years of cargo sales experience and four years of accounting records.")
add(Case("h01-gssa-sc-roles", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["SC"]}, ["SC"],
         ["eligibility_roles", "eligibility_complex"], "html", "RFP IFA-GSA-2026-4", f"{HA1}\n\n{HA2}\n\n{HA3}",
         [claim("gssa_tender", HA1, {"airline": f("Island Freight Airways", HA1), "country": f("Seychelles", HA1), "service": f("GSSA", HA1),
                                      "status": f("open", HA1), "tender_ref": f("IFA-GSA-2026-4", HA1), "deadline": f("2026-12-22T15:00:00", HA2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Indian/Mahe"),
          claim("eligibility", HA3, {"airline": f("Island Freight Airways", HA1), "tender_ref": f("IFA-GSA-2026-4", HA1),
                                     "eligibility": f("bidders registered in Mauritius must hold an equivalent licence if operating in Seychelles", HA3)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", HA3, {"airline": f("Island Freight Airways", HA1), "tender_ref": f("IFA-GSA-2026-4", HA1),
                                     "eligibility": f("four years of cargo sales experience and two years of accounting records", HA3)},
                {"tender_ref": True, "eligibility": False}),
          claim("eligibility", HA3, {"airline": f("Island Freight Airways", HA1), "tender_ref": f("IFA-GSA-2026-4", HA1),
                                     "eligibility": f("two years of cargo sales experience and four years of accounting records", HA3)},
                {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("IFA-GSA-2026-4", day="2026-12-22", precision="instant", service="GSSA")]}))

HB1 = "Request for proposals: Desert Air Cargo seeks a provider of cargo invoicing and collections services in Saudi Arabia. Reference DAC-FIN-2026-12."
HB2 = "Proposals are due before 1 February 2027. Providers must hold a licence valid after 30 June 2027 and employ at least 25 staff."
add(Case("h02-invoicing-sa-dates", "tuning", "en", "outsourcing_training", {"geo_mode": "region", "countries": [], "regions": ["GCC"]}, ["SA"],
         ["eligibility_dates", "eligibility_numeric"], "html", "RFP DAC-FIN-2026-12", f"{HB1}\n\n{HB2}",
         [claim("service_tender", HB1, {"airline": f("Desert Air Cargo", HB1), "country": f("Saudi Arabia", HB1), "service": f("INVOICING", HB1),
                                         "status": f("open", HB1), "tender_ref": f("DAC-FIN-2026-12", HB1), "deadline": f("2027-02-01", HB2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", HB2, {"airline": f("Desert Air Cargo", HB1), "tender_ref": f("DAC-FIN-2026-12", HB1),
                                     "eligibility": f("a licence valid from 30 June 2027 and at least 25 staff", HB2)}, {"tender_ref": True, "eligibility": False}),
          claim("eligibility", HB2, {"airline": f("Desert Air Cargo", HB1), "tender_ref": f("DAC-FIN-2026-12", HB1),
                                     "eligibility": f("a licence valid after 30 June 2027 and at least 25 staff", HB2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", HB2, {"airline": f("Desert Air Cargo", HB1), "tender_ref": f("DAC-FIN-2026-12", HB1),
                                     "eligibility": f("at most 25 staff", HB2)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("DAC-FIN-2026-12", day="2027-02-01", precision="date", service="INVOICING")]},
         notes="'before 1 February' is exclusive; the deadline day recorded is the stated date, the exclusivity is a note."))

HC1 = "Avis d'appel d'offres : Air Sahel invite les prestataires de services de camionnage (RFS) entre Dakar et Bamako."
HC2 = "Référence ASH-RFS-2026-2. Les offres doivent être soumises au plus tard le 11 janvier 2027 à 10:00 GMT."
HC3 = "Les soumissionnaires doivent disposer d'au moins 8 camions et d'une licence de transport routier valide au Sénégal."
add(Case("h03-fr-trucking-sn", "tuning", "fr", "trucking_gateways", {"geo_mode": "countries", "countries": ["SN", "ML"]}, ["SN"],
         ["language_fr", "eligibility_numeric"], "html", "Appel d'offres ASH-RFS-2026-2", f"{HC1}\n\n{HC2}\n\n{HC3}",
         [claim("service_tender", HC1, {"airline": f("Air Sahel", HC1), "country": f("Senegal", HC1), "service": f("TRUCKING", HC1), "status": f("open", HC1),
                                         "tender_ref": f("ASH-RFS-2026-2", HC2), "deadline": f("2027-01-11T10:00:00", HC2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Africa/Dakar"),
          claim("eligibility", HC3, {"airline": f("Air Sahel", HC1), "tender_ref": f("ASH-RFS-2026-2", HC2),
                                     "eligibility": f("au moins 8 camions et une licence de transport routier valide au Sénégal", HC3)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", HC3, {"airline": f("Air Sahel", HC1), "tender_ref": f("ASH-RFS-2026-2", HC2),
                                     "eligibility": f("au plus 8 camions", HC3)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("ASH-RFS-2026-2", day="2027-01-11", precision="instant", service="TRUCKING")]}, extra={"lang": "fr"}))

HD1 = "Example Air invites proposals for GSSA representation in Malawi. Tender reference EXA-GSSA-2026-110. Proposals are due on 3 December 2026."
HD2 = "Addendum of 20 October 2026: the tender is withdrawn with immediate effect; a new procurement will be announced in 2027."
add(Case("h04-withdrawn-mw", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["MW"]}, ["MW"],
         ["cancellation", "conflicting_statements", "amendment"], "html", "RFP EXA-GSSA-2026-110 (withdrawn)", f"{HD1}\n\n{HD2}",
         [claim("gssa_tender", HD1, {"airline": f("Example Air", HD1), "country": f("Malawi", HD1), "service": f("GSSA", HD1), "status": f("open", HD1),
                                      "tender_ref": f("EXA-GSSA-2026-110", HD1), "deadline": f("2026-12-03", HD1)},
                {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True, "deadline": True}),
          claim("tender_status", HD2, {"airline": f("Example Air", HD1), "tender_ref": f("EXA-GSSA-2026-110", HD1), "status": f("cancelled", HD2)},
                {"tender_ref": True, "status": True})],
         {"opportunities": [], "historical": [{"ref": "EXA-GSSA-2026-110", "status": "cancelled"}], "contradictory_document": True}))

HE_TITLE = "Open procurements — Lakeside Air Services"
add(Case("h05-table-ea", "tuning", "en", "technology_solutions", {"geo_mode": "region", "countries": [], "regions": ["EASTERN_AFRICA"]}, ["KE", "UG", "TZ"],
         ["table", "multi_opportunity", "missing_deadline"], "html-table", HE_TITLE,
         "Lakeside Air Services lists its open requests for proposal below.",
         [claim("service_tender", "LAS-TEC-2026-1 | Cargo management software | Kenya | 16 January 2027",
                {"airline": f("Lakeside Air Services", "Lakeside Air Services lists its open requests for proposal below."),
                 "country": f("Kenya", "LAS-TEC-2026-1 | Cargo management software | Kenya | 16 January 2027"), "service": f("TECHNOLOGY", "LAS-TEC-2026-1 | Cargo management software"),
                 "status": f("open", "Lakeside Air Services lists its open requests for proposal below."), "tender_ref": f("LAS-TEC-2026-1", "LAS-TEC-2026-1 | Cargo management software"),
                 "deadline": f("2027-01-16", "LAS-TEC-2026-1 | Cargo management software | Kenya | 16 January 2027")},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("service_tender", "LAS-HDL-2026-2 | Ramp handling at Entebbe | Uganda | to be announced",
                {"airline": f("Lakeside Air Services", "Lakeside Air Services lists its open requests for proposal below."),
                 "country": f("Uganda", "LAS-HDL-2026-2 | Ramp handling at Entebbe | Uganda | to be announced"), "service": f("HANDLING", "LAS-HDL-2026-2 | Ramp handling at Entebbe"),
                 "status": f("open", "Lakeside Air Services lists its open requests for proposal below."), "tender_ref": f("LAS-HDL-2026-2", "LAS-HDL-2026-2 | Ramp handling at Entebbe")},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True}),
          claim("tender_deadline", "LAS-HDL-2026-2 | Ramp handling at Entebbe | Uganda | to be announced",
                {"airline": f("Lakeside Air Services", "Lakeside Air Services lists its open requests for proposal below."),
                 "tender_ref": f("LAS-HDL-2026-2", "LAS-HDL-2026-2 | Ramp handling at Entebbe"), "deadline": f("2027-01-16", "LAS-HDL-2026-2 | Ramp handling at Entebbe | Uganda | to be announced")},
                {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("LAS-TEC-2026-1", day="2027-01-16", precision="date", service="TECHNOLOGY"),
                            opp("LAS-HDL-2026-2", day=None, precision=None, service="HANDLING")]},
         table_rows=[["Reference", "Subject", "Country", "Closing date"],
                     ["LAS-TEC-2026-1", "Cargo management software", "Kenya", "16 January 2027"],
                     ["LAS-HDL-2026-2", "Ramp handling at Entebbe", "Uganda", "to be announced"]]))

HF_A = "Cabo Verde Cargo invites proposals from GSSA providers for cargo sales representation in Cabo Verde."
HF_Z = "Tender reference CVC-GSSA-2027-02. Proposals must be submitted by 28 February 2027 at 12:00 CVT."
HF_BODY = HF_A + "\n\n" + "\n\n".join(f"Article {i}. Terms: the agent shall remit sales proceeds within thirty days, keep records for seven years, "
                                       f"and permit audits on reasonable notice (article {i})." for i in range(1, 241)) + "\n\n" + HF_Z
add(Case("h06-long-pdf-cv", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["CV"]}, ["CV"],
         ["long_document", "pdf"], "pdf", "RFP CVC-GSSA-2027-02", HF_BODY,
         [claim("gssa_tender", HF_A, {"airline": f("Cabo Verde Cargo", HF_A), "country": f("Cabo Verde", HF_A), "service": f("GSSA", HF_A),
                                       "status": f("open", HF_A)}, {"airline": True, "country": True, "service": True, "status": True}),
          claim("tender_deadline", HF_Z, {"airline": f("Cabo Verde Cargo", HF_A), "tender_ref": f("CVC-GSSA-2027-02", "Tender reference CVC-GSSA-2027-02."),
                                          "deadline": f("2027-02-28T12:00:00", "Proposals must be submitted by 28 February 2027 at 12:00 CVT.")},
                {"tender_ref": True, "deadline": True}, tz="Atlantic/Cape_Verde")],
         {"opportunities": [opp("CVC-GSSA-2027-02", day="2027-02-28", precision="instant", service="GSSA")]}, long=True))

HG1 = "Aerocarga del Sur convoca licitación para servicios de capacitación en mercancías peligrosas en Chile. Referencia ACS-CAP-2026-3."
HG2 = "Las ofertas se reciben hasta el 20 de enero de 2027. Los oferentes deben contar con al menos tres instructores certificados."
add(Case("h07-es-training-cl", "tuning", "es", "outsourcing_training", {"geo_mode": "country", "countries": ["CL"]}, ["CL"],
         ["language_es", "eligibility_numeric"], "html", "Licitación ACS-CAP-2026-3", f"{HG1}\n\n{HG2}",
         [claim("service_tender", HG1, {"airline": f("Aerocarga del Sur", HG1), "country": f("Chile", HG1), "service": f("TRAINING", HG1), "status": f("open", HG1),
                                         "tender_ref": f("ACS-CAP-2026-3", HG1), "deadline": f("2027-01-20", HG2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", HG2, {"airline": f("Aerocarga del Sur", HG1), "tender_ref": f("ACS-CAP-2026-3", HG1),
                                     "eligibility": f("al menos tres instructores certificados", HG2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", HG2, {"airline": f("Aerocarga del Sur", HG1), "tender_ref": f("ACS-CAP-2026-3", HG1),
                                     "eligibility": f("al menos treinta instructores certificados", HG2)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("ACS-CAP-2026-3", day="2027-01-20", precision="date", service="TRAINING")]}, extra={"lang": "es"}))

HH1 = "Pacific Freighters will operate a new weekly freighter service from Singapore to Perth from 1 March 2027, offering 90 tonnes per flight."
add(Case("h08-capacity-sg-au", "tuning", "en", "capacity_lanes", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["SG"],
         ["capacity", "worldwide"], "html", "Pacific Freighters announces Singapore–Perth", HH1,
         [claim("route_launch", HH1, {"airline": f("Pacific Freighters", HH1), "origin": f("Singapore", HH1), "destination": f("Australia", HH1)},
                {"airline": True, "origin": True, "destination": True}),        # Perth resolves through the city register
          claim("service_tender", HH1, {"airline": f("Pacific Freighters", HH1), "country": f("Australia", HH1), "service": f("HANDLING", HH1), "status": f("open", HH1)},
                {"airline": True, "country": True, "service": False, "status": False})],
         {"opportunities": [], "signal_expected": "airline_representation"}))

HI1 = "Example Air invites proposals for GSSA services in Botswana. Tender reference EXA-GSSA-2026-115. Proposals are due by 30 November 2026 at 23:59."
HI2 = "Only bidders with an office in Gaborone or Francistown may apply."
add(Case("h09-or-condition-bw", "tuning", "en", "airline_representation", {"geo_mode": "country", "countries": ["BW"]}, ["BW"],
         ["eligibility_complex", "timezone_unclear"], "html", "RFP EXA-GSSA-2026-115", f"{HI1}\n\n{HI2}",
         [claim("gssa_tender", HI1, {"airline": f("Example Air", HI1), "country": f("Botswana", HI1), "service": f("GSSA", HI1), "status": f("open", HI1),
                                      "tender_ref": f("EXA-GSSA-2026-115", HI1), "deadline": f("2026-11-30T23:59:00", HI1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", HI2, {"airline": f("Example Air", HI1), "tender_ref": f("EXA-GSSA-2026-115", HI1),
                                     "eligibility": f("an office in Gaborone and Francistown", HI2)}, {"tender_ref": True, "eligibility": False}),
          claim("eligibility", HI2, {"airline": f("Example Air", HI1), "tender_ref": f("EXA-GSSA-2026-115", HI1),
                                     "eligibility": f("an office in Gaborone or Francistown", HI2)}, {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("EXA-GSSA-2026-115", day="2026-11-30", precision="local_time", service="GSSA")]}))

HJ1 = "Horizon Forwarding opens a new consolidation hub in Johannesburg, South Africa, adding 1,200 square metres of bonded warehouse space."
add(Case("h10-forwarder-hub-za", "tuning", "en", "forwarder_sales", {"geo_mode": "country", "countries": ["ZA"]}, ["ZA"],
         ["not_procurement", "internal_area"], "html", "Horizon Forwarding opens Johannesburg hub", HJ1,
         [claim("service_tender", HJ1, {"organisation": f("Horizon Forwarding", HJ1), "country": f("South Africa", HJ1), "service": f("HANDLING", HJ1), "status": f("open", HJ1)},
                {"organisation": True, "country": True, "service": False, "status": False})],
         {"opportunities": []}))

HK1 = "Northern Cargo Airlines amends tender NCA-DATA-2026-6 (cargo documentation processing, Germany): the scope now includes Austria. Submissions are due on 15 January 2027."
add(Case("h11-amended-scope-de", "tuning", "en", "outsourcing_training", {"geo_mode": "countries", "countries": ["DE", "AT"]}, ["DE"],
         ["amendment"], "html", "Amendment: NCA-DATA-2026-6", HK1,
         [claim("service_tender", HK1, {"airline": f("Northern Cargo Airlines", HK1), "country": f("Germany", HK1), "service": f("DATA_PROCESSING", HK1),
                                         "status": f("revised", HK1), "tender_ref": f("NCA-DATA-2026-6", HK1), "deadline": f("2027-01-15", HK1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("NCA-DATA-2026-6", status="revised", day="2027-01-15", precision="date", service="DATA_PROCESSING")]}))

HL1 = "Example Air advises customers that the Mombasa cargo office will relocate to the airport cargo village on 1 December 2026; services continue unchanged."
add(Case("h12-ops-relocation-ke", "tuning", "en", "service_operations", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["not_procurement", "internal_area"], "html", "Mombasa office relocation", HL1,
         [claim("tender_status", HL1, {"airline": f("Example Air", HL1), "status": f("open", HL1)}, {"status": False})],
         {"opportunities": []}))


# ============================================================================ HELD-OUT 2 (written 27 Oct 2026 BEFORE the item-3 rules were
# tuned against the former held-out set's findings; run once at the end of the release; no rule changed afterwards)
JA1 = "Savanna Air Cargo invites proposals from general sales agents for cargo representation in Namibia. Tender reference SAC-GSA-2026-9."
JA2 = "Only agents with a registered office in Windhoek or Walvis Bay may apply. Proposals are due by 12 February 2027 at 16:00 CAT."
JA3 = "Agents must hold a certificate valid until 30 June 2027 and have two years of GSA experience and four years of audited accounts."
add(Case("j01-gssa-na-only-may-apply", "heldout2", "en", "airline_representation", {"geo_mode": "country", "countries": ["NA"]}, ["NA"],
         ["eligibility_complex", "eligibility_dates", "only_may_apply"], "html", "RFP SAC-GSA-2026-9", f"{JA1}\n\n{JA2}\n\n{JA3}",
         [claim("gssa_tender", JA1, {"airline": f("Savanna Air Cargo", JA1), "country": f("Namibia", JA1), "service": f("GSSA", JA1), "status": f("open", JA2),
                                      "tender_ref": f("SAC-GSA-2026-9", JA1), "deadline": f("2027-02-12T16:00:00", JA2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Africa/Windhoek"),
          claim("eligibility", JA2, {"airline": f("Savanna Air Cargo", JA1), "tender_ref": f("SAC-GSA-2026-9", JA1),
                                     "eligibility": f("a registered office in Windhoek or Walvis Bay", JA2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", JA2, {"airline": f("Savanna Air Cargo", JA1), "tender_ref": f("SAC-GSA-2026-9", JA1),
                                     "eligibility": f("a registered office in Windhoek and Walvis Bay", JA2)}, {"tender_ref": True, "eligibility": False}),
          claim("eligibility", JA3, {"airline": f("Savanna Air Cargo", JA1), "tender_ref": f("SAC-GSA-2026-9", JA1),
                                     "eligibility": f("a certificate valid until 30 June 2027 and two years of GSA experience and four years of audited accounts", JA3)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", JA3, {"airline": f("Savanna Air Cargo", JA1), "tender_ref": f("SAC-GSA-2026-9", JA1),
                                     "eligibility": f("four years of GSA experience and two years of audited accounts", JA3)}, {"tender_ref": True, "eligibility": False}),
          claim("eligibility", JA3, {"airline": f("Savanna Air Cargo", JA1), "tender_ref": f("SAC-GSA-2026-9", JA1),
                                     "eligibility": f("a certificate valid until 12 February 2027", JA3)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("SAC-GSA-2026-9", day="2027-02-12", precision="instant", service="GSSA")]}))

JB1 = "Appel d'offres : Air Atlas Maroc recherche un prestataire pour la manutention du fret à Casablanca, Maroc. Référence AAM-HDL-2026-4."
JB2 = "Seuls les prestataires titulaires d'un agrément de l'ONDA peuvent soumissionner. Les offres doivent parvenir avant le 5 mars 2027 à 11:00 WET."
add(Case("j02-fr-handling-ma", "heldout2", "fr", "outsourcing_training", {"geo_mode": "region", "countries": [], "regions": ["NORTHERN_AFRICA"]}, ["MA"],
         ["language_fr", "eligibility_complex", "timezone_context"], "html", "Appel d'offres AAM-HDL-2026-4", f"{JB1}\n\n{JB2}",
         [claim("service_tender", JB1, {"airline": f("Air Atlas Maroc", JB1), "country": f("Morocco", JB1), "service": f("HANDLING", JB1), "status": f("open", JB2),
                                         "tender_ref": f("AAM-HDL-2026-4", JB1), "deadline": f("2027-03-05T11:00:00", JB2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Africa/Casablanca"),
          claim("eligibility", JB2, {"airline": f("Air Atlas Maroc", JB1), "tender_ref": f("AAM-HDL-2026-4", JB1),
                                     "eligibility": f("les prestataires titulaires d'un agrément de l'ONDA", JB2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", JB2, {"airline": f("Air Atlas Maroc", JB1), "tender_ref": f("AAM-HDL-2026-4", JB1),
                                     "eligibility": f("les prestataires titulaires d'un agrément de l'IATA", JB2)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("AAM-HDL-2026-4", day="2027-03-05", precision="instant", service="HANDLING")]}, extra={"lang": "fr"},
         notes="WET is established by the notice naming Morocco; 'avant' is exclusive."))

JC1 = "Licitación pública: Carga Andina S.A. requiere servicios de camionaje entre Lima y Santiago. Referencia CAN-RFS-2026-11."
JC2 = "Las propuestas se recibirán hasta el 28 de enero de 2027 a las 17:00 horas. Sólo podrán participar empresas con al menos 12 camiones."
add(Case("j03-es-trucking-ambiguous-city", "heldout2", "es", "trucking_gateways", {"geo_mode": "countries", "countries": ["PE", "CL"]}, ["PE"],
         ["language_es", "ambiguous_city", "timezone_unclear", "eligibility_numeric"], "html", "Licitación CAN-RFS-2026-11", f"{JC1}\n\n{JC2}",
         [claim("service_tender", JC1, {"organisation": f("Carga Andina S.A.", JC1), "country": f("Peru", JC1), "service": f("TRUCKING", JC1),
                                         "status": f("open", JC2), "tender_ref": f("CAN-RFS-2026-11", JC1), "deadline": f("2027-01-28T17:00:00", JC2)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("service_tender", JC1, {"organisation": f("Carga Andina S.A.", JC1), "country": f("Chile", JC1), "service": f("TRUCKING", JC1),
                                         "status": f("open", JC2), "tender_ref": f("CAN-RFS-2026-11", JC1)},
                {"organisation": True, "country": False, "service": True, "status": True, "tender_ref": True}),
          claim("eligibility", JC2, {"organisation": f("Carga Andina S.A.", JC1), "tender_ref": f("CAN-RFS-2026-11", JC1),
                                     "eligibility": f("al menos 12 camiones", JC2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", JC2, {"organisation": f("Carga Andina S.A.", JC1), "tender_ref": f("CAN-RFS-2026-11", JC1),
                                     "eligibility": f("como máximo 12 camiones", JC2)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [opp("CAN-RFS-2026-11", day="2027-01-28", precision="local_time", service="TRUCKING")]}, extra={"lang": "es"},
         notes="Santiago is ambiguous (Chile, Spain, ...): Chile must go to review, never be supported; Lima resolves to Peru."))

JD1 = "Example Air announces that tender EXA-HDL-2026-40 (ramp handling, Entebbe, Uganda) is withdrawn with immediate effect following a change in the airline's network plan."
add(Case("j04-withdrawn-ug", "heldout2", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["UG"]}, ["UG"],
         ["cancellation", "withdrawn"], "html", "Tender EXA-HDL-2026-40 withdrawn", JD1,
         [claim("tender_status", JD1, {"airline": f("Example Air", JD1), "tender_ref": f("EXA-HDL-2026-40", JD1), "status": f("cancelled", JD1)},
                {"tender_ref": True, "status": True}),
          claim("service_tender", JD1, {"airline": f("Example Air", JD1), "country": f("Uganda", JD1), "service": f("HANDLING", JD1), "status": f("open", JD1),
                                         "tender_ref": f("EXA-HDL-2026-40", JD1)}, {"airline": True, "country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [], "historical": [{"ref": "EXA-HDL-2026-40", "status": "cancelled"}]},
         notes="A withdrawal notice alone: the record, if created, must carry 'cancelled', never 'open'."))

JE_TITLE = "Open tenders — Harbour Air Services"
add(Case("j05-table-parentheses", "heldout2", "en", "technology_solutions", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["GH", "NG"],
         ["table", "multi_opportunity", "worldwide"], "html-table", JE_TITLE, "Harbour Air Services lists its open requests for proposal below.",
         [claim("service_tender", "HAS-TEC-2026-2 | Cargo booking portal (software) | Accra, Ghana | 23 January 2027",
                {"airline": f("Harbour Air Services", "Harbour Air Services lists its open requests for proposal below."),
                 "country": f("Ghana", "HAS-TEC-2026-2 | Cargo booking portal (software) | Accra, Ghana | 23 January 2027"), "service": f("TECHNOLOGY", "HAS-TEC-2026-2 | Cargo booking portal (software)"),
                 "status": f("open", "Harbour Air Services lists its open requests for proposal below."), "tender_ref": f("HAS-TEC-2026-2", "HAS-TEC-2026-2 | Cargo booking portal (software)"),
                 "deadline": f("2027-01-23", "HAS-TEC-2026-2 | Cargo booking portal (software) | Accra, Ghana | 23 January 2027")},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("service_tender", "HAS-ACC-2026-3 | Cargo revenue accounting | Lagos, Nigeria | 30 January 2027",
                {"airline": f("Harbour Air Services", "Harbour Air Services lists its open requests for proposal below."),
                 "country": f("Nigeria", "HAS-ACC-2026-3 | Cargo revenue accounting | Lagos, Nigeria | 30 January 2027"), "service": f("ACCOUNTING", "HAS-ACC-2026-3 | Cargo revenue accounting"),
                 "status": f("open", "Harbour Air Services lists its open requests for proposal below."), "tender_ref": f("HAS-ACC-2026-3", "HAS-ACC-2026-3 | Cargo revenue accounting"),
                 "deadline": f("2027-01-30", "HAS-ACC-2026-3 | Cargo revenue accounting | Lagos, Nigeria | 30 January 2027")},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("service_tender", "HAS-ACC-2026-3 | Cargo revenue accounting | Lagos, Nigeria | 30 January 2027",
                {"airline": f("Harbour Air Services", "Harbour Air Services lists its open requests for proposal below."),
                 "country": f("Ghana", "HAS-ACC-2026-3 | Cargo revenue accounting | Lagos, Nigeria | 30 January 2027"), "service": f("ACCOUNTING", "HAS-ACC-2026-3 | Cargo revenue accounting"),
                 "status": f("open", "Harbour Air Services lists its open requests for proposal below."), "tender_ref": f("HAS-ACC-2026-3", "HAS-ACC-2026-3 | Cargo revenue accounting")},
                {"airline": True, "country": False, "service": True, "status": True, "tender_ref": True})],
         {"opportunities": [opp("HAS-TEC-2026-2", day="2027-01-23", precision="date", service="TECHNOLOGY"),
                            opp("HAS-ACC-2026-3", day="2027-01-30", precision="date", service="ACCOUNTING")]},
         table_rows=[["Reference", "Subject", "Location", "Closing date"],
                     ["HAS-TEC-2026-2", "Cargo booking portal (software)", "Accra, Ghana", "23 January 2027"],
                     ["HAS-ACC-2026-3", "Cargo revenue accounting", "Lagos, Nigeria", "30 January 2027"]]))

JF_A = "Indian Ocean Freighters invites proposals from GSSA providers for cargo sales representation in Madagascar."
JF_Z = "Tender reference IOF-GSSA-2027-03. Proposals are due on 31 March 2027 at 10:00 EAT."
JF_BODY = JF_A + "\n\n" + "\n\n".join(f"Schedule {i}. Service levels: the agent shall answer rate requests within one working day, report weekly, "
                                       f"and keep sales records for five years (schedule {i})." for i in range(1, 231)) + "\n\n" + JF_Z
add(Case("j06-long-pdf-mg", "heldout2", "en", "airline_representation", {"geo_mode": "region", "countries": [], "regions": ["EASTERN_AFRICA"]}, ["MG"],
         ["long_document", "pdf"], "pdf", "RFP IOF-GSSA-2027-03", JF_BODY,
         [claim("gssa_tender", JF_A, {"airline": f("Indian Ocean Freighters", JF_A), "country": f("Madagascar", JF_A), "service": f("GSSA", JF_A),
                                       "status": f("open", JF_A)}, {"airline": True, "country": True, "service": True, "status": True}),
          claim("tender_deadline", JF_Z, {"airline": f("Indian Ocean Freighters", JF_A), "tender_ref": f("IOF-GSSA-2027-03", "Tender reference IOF-GSSA-2027-03."),
                                          "deadline": f("2027-03-31T10:00:00", "Proposals are due on 31 March 2027 at 10:00 EAT.")}, {"tender_ref": True, "deadline": True},
                tz="Indian/Antananarivo")],
         {"opportunities": [opp("IOF-GSSA-2027-03", day="2027-03-31", precision="instant", service="GSSA")]}, long=True))

JG1 = "Corrigendum No. 2 to tender SAC-GSA-2026-9 (GSA representation, Namibia)."
JG2 = "The closing date is extended from 12 February 2027 to 26 February 2027 at 16:00 CAT; the requirement for four years of audited accounts is reduced to three years."
add(Case("j07-corrigendum-na", "heldout2", "en", "airline_representation", {"geo_mode": "country", "countries": ["NA"]}, ["NA"],
         ["amendment"], "html", "Corrigendum No. 2: SAC-GSA-2026-9", f"{JG1}\n\n{JG2}",
         [claim("tender_status", JG2, {"airline": f("Savanna Air Cargo", JG1), "tender_ref": f("SAC-GSA-2026-9", JG1), "status": f("revised", JG2),
                                       "deadline": f("2027-02-26T16:00:00", JG2)}, {"tender_ref": True, "status": True, "deadline": True}, tz="Africa/Windhoek"),
          claim("tender_deadline", JG2, {"airline": f("Savanna Air Cargo", JG1), "tender_ref": f("SAC-GSA-2026-9", JG1), "deadline": f("2027-02-12T16:00:00", JG2)},
                {"tender_ref": True, "deadline": False}, tz="Africa/Windhoek"),
          claim("eligibility", JG2, {"airline": f("Savanna Air Cargo", JG1), "tender_ref": f("SAC-GSA-2026-9", JG1), "eligibility": f("three years of audited accounts", JG2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", JG2, {"airline": f("Savanna Air Cargo", JG1), "tender_ref": f("SAC-GSA-2026-9", JG1), "eligibility": f("four years of audited accounts", JG2)},
                {"tender_ref": True, "eligibility": False})],
         {"opportunities": [], "follower_only": True}, notes="A corrigendum alone announces nothing; the superseded deadline and requirement must not be supported."))

JH1 = "Horizon Forwarding reports that its Nairobi branch handled 14% more export tonnage in the third quarter and will add a second night shift."
add(Case("j08-forwarder-news-ke", "heldout2", "en", "forwarder_sales", {"geo_mode": "country", "countries": ["KE"]}, ["KE"],
         ["not_procurement", "internal_area"], "html", "Horizon Forwarding Q3", JH1,
         [claim("service_tender", JH1, {"organisation": f("Horizon Forwarding", JH1), "country": f("Kenya", JH1), "service": f("HANDLING", JH1), "status": f("open", JH1)},
                {"organisation": True, "country": True, "service": False, "status": False})],
         {"opportunities": []}))

JI1 = "Example Air invites proposals from GSSA providers for cargo sales representation in Mauritius. Tender reference EXA-GSSA-2026-120."
JI2 = "Proposals must be submitted by 20 January 2027 at 15:00 MUT. Bidders must have a cargo sales track record in the region."
add(Case("j09-context-zone-uninterpreted-mu", "heldout2", "en", "airline_representation", {"geo_mode": "country", "countries": ["MU"]}, ["MU"],
         ["timezone_context", "uninterpretable_eligibility"], "html", "RFP EXA-GSSA-2026-120", f"{JI1}\n\n{JI2}",
         [claim("gssa_tender", JI1, {"airline": f("Example Air", JI1), "country": f("Mauritius", JI1), "service": f("GSSA", JI1), "status": f("open", JI2),
                                      "tender_ref": f("EXA-GSSA-2026-120", JI1), "deadline": f("2027-01-20T15:00:00", JI2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}, tz="Indian/Mauritius"),
          claim("eligibility", JI2, {"airline": f("Example Air", JI1), "tender_ref": f("EXA-GSSA-2026-120", JI1),
                                     "eligibility": f("a cargo sales track record in the region", JI2)}, {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("EXA-GSSA-2026-120", day="2027-01-20", precision="instant", service="GSSA")]},
         notes="MUT is established by the notice naming Mauritius; the eligibility sentence has 'must', so it is interpreted."))

JJ1 = "Sample Airways will start a twice-weekly freighter service from Dubai to Lagos on 15 February 2027, adding 180 tonnes of weekly capacity."
add(Case("j10-route-dubai-lagos", "heldout2", "en", "capacity_lanes", {"geo_mode": "worldwide", "countries": [], "regions": []}, ["AE"],
         ["capacity", "worldwide"], "html", "Sample Airways: Dubai–Lagos freighter", JJ1,
         [claim("route_launch", JJ1, {"airline": f("Sample Airways", JJ1), "origin": f("United Arab Emirates", JJ1), "destination": f("Nigeria", JJ1)},
                {"airline": True, "origin": True, "destination": True}),
          claim("route_launch", JJ1, {"airline": f("Sample Airways", JJ1), "origin": f("Nigeria", JJ1), "destination": f("United Arab Emirates", JJ1)},
                {"airline": True, "origin": False, "destination": False})],
         {"opportunities": [], "signal_expected": "airline_representation"}))

JK1 = "Example Air invites proposals for cargo accounting and invoicing services in Zambia. Tender reference EXA-FIN-2026-7. Proposals are due on 9 February 2027."
JK2 = "Update of 24 October 2026: proposals are now due on 23 February 2027. The tender remains open."
add(Case("j11-extension-same-doc-zm", "heldout2", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["amendment", "conflicting_statements"], "html", "RFP EXA-FIN-2026-7 (updated)", f"{JK1}\n\n{JK2}",
         [claim("service_tender", JK1, {"airline": f("Example Air", JK1), "country": f("Zambia", JK1), "service": f("ACCOUNTING", JK1), "status": f("open", JK1),
                                         "tender_ref": f("EXA-FIN-2026-7", JK1), "deadline": f("2027-02-09", JK1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_status", JK2, {"airline": f("Example Air", JK1), "tender_ref": f("EXA-FIN-2026-7", JK1), "status": f("revised", JK2), "deadline": f("2027-02-23", JK2)},
                {"tender_ref": True, "status": True, "deadline": True})],
         {"opportunities": [opp("EXA-FIN-2026-7", status="revised", day="2027-02-23", precision="date", service="ACCOUNTING")]},
         notes="The update says 'now due': a revision in the same document, so the later date stands and the status is revised."))

JL1 = "Example Air advises that Lusaka cargo acceptance moves to the new terminal from 1 December 2026; cut-off times are unchanged."
add(Case("j12-ops-notice-zm", "heldout2", "en", "service_operations", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["not_procurement", "internal_area"], "html", "Lusaka terminal move", JL1,
         [claim("tender_deadline", JL1, {"airline": f("Example Air", JL1), "deadline": f("2026-12-01", JL1)}, {"deadline": False})],
         {"opportunities": []}))


def cases(split: str | None = None) -> list[Case]:
    return [c for c in CASES if split is None or c.split == split]
