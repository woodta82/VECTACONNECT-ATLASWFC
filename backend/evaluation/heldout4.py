"""Held-out set 4 (written 27 Oct 2026 after held-out set 3 was run once and BEFORE any rule was changed in response to it;
run once at the end of the release; no rule changed afterwards).

PROVENANCE: authored for this build in the form of real airline and procurement notices. None is a genuine notice.
Same gold conventions as `heldout3.py` (freight_scope, excluded, geography_conflict).

LABELS v4 (27 Oct 2026, fifth instruction, item 4): one policy for terminal-only records. A cancellation, award or closure
of a tender that is not already tracked is kept as HISTORICAL INTELLIGENCE (a tender record with the terminal status,
outside the actionable pipeline and the live counts), never created as an opportunity. Labels that expected a terminal
opportunity (t04, t15, h04, j04 in notices.py; m10 in heldout4.py) or nothing at all (g09 in genuine.py, k12 in heldout3.py) now expect a
`historical` record instead. Previous results are kept in the release evidence.
"""
from __future__ import annotations

from evaluation.notices import Case, claim, f, opp

HELDOUT4: list[Case] = []


def add(c: Case) -> Case:
    HELDOUT4.append(c)
    return c


# m01 defined territory written "i.e. Jordan" (no comma), disclaimer naming another country: conflict, the other country never supported
MA_T = "Request for proposal: cargo general sales and service agent for the Territory"
MA1 = "Levant Example Cargo invites proposals from cargo GSSA providers for the Territory. Tender reference LEC-GSSA-2027-1."
MA2 = "In this RFP, Territory means the Hashemite Kingdom of Jordan, i.e. Jordan."
MA3 = "Disclaimer: this request is issued for cargo sales in Lebanon and nothing herein creates an obligation."
MA4 = "Proposals must be submitted by 3 March 2027 at 12:00 (UTC+3)."
add(Case("m01-defined-territory-ie-no-comma-jo", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["JO"]}, ["JO", "LB"],
         ["geography_conflict", "defined_territory", "conflicting_statements"], "pdf", MA_T, f"{MA_T}\n\n{MA1}\n\n{MA2}\n\n{MA3}\n\n{MA4}",
         [claim("gssa_tender", MA1, {"airline": f("Levant Example Cargo", MA1), "country": f("Jordan", MA2), "service": f("GSSA", MA1), "status": f("open", MA4),
                                      "tender_ref": f("LEC-GSSA-2027-1", MA1), "deadline": f("2027-03-03T12:00:00", MA4)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("gssa_tender", MA1, {"airline": f("Levant Example Cargo", MA1), "country": f("Lebanon", MA3), "service": f("GSSA", MA1), "status": f("open", MA4),
                                      "tender_ref": f("LEC-GSSA-2027-1", MA1)},
                {"airline": True, "country": False, "service": True, "status": True, "tender_ref": True})],
         {"opportunities": [opp("LEC-GSSA-2027-1", day="2027-03-03", precision="instant", service="GSSA", freight_scope="cargo")], "geography_conflict": True}))

# m02 territory stated in a schedule line, another passage naming the issuer's country (issuer role, not a conflict)
MB_T = "RFP SAW-GSSA-2027-8: cargo GSSA"
MB1 = "Sample Airways, headquartered in Kenya, invites proposals from cargo GSSA providers. Tender reference SAW-GSSA-2027-8."
MB2 = "Schedule A: Tanzania (Dar es Salaam and Kilimanjaro)."
MB3 = "Proposals are due on 10 March 2027."
add(Case("m02-schedule-territory-issuer-elsewhere-tz", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["TZ"]}, ["TZ"],
         ["geography_roles", "multi_lot"], "html", MB_T, f"{MB1}\n\n{MB2}\n\n{MB3}",
         [claim("gssa_tender", MB1, {"airline": f("Sample Airways", MB1), "issuer_country": f("Kenya", MB1), "service": f("GSSA", MB1), "status": f("open", MB1),
                                      "tender_ref": f("SAW-GSSA-2027-8", MB1), "deadline": f("2027-03-10", MB3)},
                {"airline": True, "issuer_country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_scope", MB2, {"airline": f("Sample Airways", MB1), "tender_ref": f("SAW-GSSA-2027-8", MB1), "contract_territory": f("Tanzania", MB2)},
                {"tender_ref": True, "contract_territory": True}),
          claim("gssa_tender", MB1, {"airline": f("Sample Airways", MB1), "country": f("Kenya", MB1), "tender_ref": f("SAW-GSSA-2027-8", MB1)},
                {"airline": True, "country": False, "tender_ref": True})],
         {"opportunities": [opp("SAW-GSSA-2027-8", day="2027-03-10", precision="date", service="GSSA", freight_scope="cargo")], "geography_conflict": False}))

# m03 corrigendum: closing date moved and a quantity raised, worded without "extended" or "amended"
MC1 = "Addendum No. 2 to tender EXA-HDL-2027-5 (cargo handling, Ghana)."
MC2 = "The closing date has been moved from 4 March 2027 to 18 March 2027. The minimum number of forklifts has been raised from 6 to 10."
add(Case("m03-addendum-moved-and-raised-gh", "heldout4", "en", "outsourcing_training", {"geo_mode": "country", "countries": ["GH"]}, ["GH"],
         ["amendment", "quantity_replaced", "extension"], "html", "Addendum No. 2: EXA-HDL-2027-5", f"{MC1}\n\n{MC2}",
         [claim("tender_status", MC2, {"airline": f("Example Air", MC1), "tender_ref": f("EXA-HDL-2027-5", MC1), "status": f("revised", MC2), "deadline": f("2027-03-18", MC2)},
                {"airline": False, "tender_ref": True, "status": True, "deadline": True}),
          claim("tender_deadline", MC2, {"tender_ref": f("EXA-HDL-2027-5", MC1), "deadline": f("2027-03-04", MC2)}, {"tender_ref": True, "deadline": False}),
          claim("eligibility", MC2, {"tender_ref": f("EXA-HDL-2027-5", MC1), "eligibility": f("a minimum of 10 forklifts", MC2)}, {"tender_ref": True, "eligibility": True}),
          claim("eligibility", MC2, {"tender_ref": f("EXA-HDL-2027-5", MC1), "eligibility": f("a minimum of 6 forklifts", MC2)}, {"tender_ref": True, "eligibility": False})],
         {"opportunities": [], "follower_only": True}, notes="The new date and the new quantity stand. 'Example Air' is not named in the quote."))

# m04 passenger-only call centre / reservations agent (no 'passenger' word, but ticketing and reservations)
MD1 = "Coastal Example Airways invites proposals for a general sales agent to handle ticketing, reservations and BSP reporting in Malawi. Reference CEA-GSA-2027-2."
MD2 = "Proposals are due on 15 February 2027."
add(Case("m04-ticketing-gsa-mw", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["MW"]}, ["MW"],
         ["passenger_only", "freight_relevance"], "html", "RFP CEA-GSA-2027-2", f"{MD1}\n\n{MD2}",
         [claim("gssa_tender", MD1, {"airline": f("Coastal Example Airways", MD1), "country": f("Malawi", MD1), "service": f("GSSA", MD1), "status": f("open", MD1),
                                      "tender_ref": f("CEA-GSA-2027-2", MD1), "deadline": f("2027-02-15", MD2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [], "excluded": [{"scope": "passenger", "title_contains": "Coastal Example Airways"}]}))

# m05 cargo wording only in the title; body generic
ME_T = "Invitation: cargo sales representation in Botswana"
ME1 = "Sample Airways invites proposals from general sales agents for representation in Botswana. Tender reference SAW-GSA-2027-12. Bids are due on 1 March 2027."
add(Case("m05-cargo-title-generic-body-bw", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["BW"]}, ["BW"],
         ["freight_relevance"], "html", ME_T, ME1,
         [claim("gssa_tender", ME1, {"airline": f("Sample Airways", ME1), "country": f("Botswana", ME1), "service": f("GSSA", ME1), "status": f("open", ME1),
                                      "tender_ref": f("SAW-GSA-2027-12", ME1), "deadline": f("2027-03-01", ME1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("SAW-GSA-2027-12", day="2027-03-01", precision="date", service="GSSA", freight_scope="cargo")]}))

# m06 notice 200 days old: open wording AND a future closing date — the deadline decides, not the age
MF1 = "Example Air invites proposals from cargo GSSA providers in Namibia. Tender reference EXA-GSSA-2026-99. Proposals are due on 30 April 2027."
add(Case("m06-old-notice-future-deadline-na", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["NA"]}, ["NA"],
         ["status_age"], "html", "RFP EXA-GSSA-2026-99", MF1,
         [claim("gssa_tender", MF1, {"airline": f("Example Air", MF1), "country": f("Namibia", MF1), "service": f("GSSA", MF1), "status": f("open", MF1),
                                      "tender_ref": f("EXA-GSSA-2026-99", MF1), "deadline": f("2027-04-30", MF1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("EXA-GSSA-2026-99", day="2027-04-30", precision="date", service="GSSA", freight_scope="cargo")]}, published="2026-04-10T08:00:00Z"))

# m07 Portuguese-language trucking tender (in scope language list), cargo by nature
MG1 = "Concurso: a Carga Lusa S.A. solicita propostas para serviços de transporte rodoviário de carga aérea entre Maputo e Beira, Moçambique. Referência CLS-RFS-2027-1."
MG2 = "As propostas devem ser entregues até 26 de fevereiro de 2027."
add(Case("m07-pt-trucking-mz", "heldout4", "pt", "trucking_gateways", {"geo_mode": "country", "countries": ["MZ"]}, ["MZ"],
         ["language_pt", "procurement_wording"], "html", "Concurso CLS-RFS-2027-1", f"{MG1}\n\n{MG2}",
         [claim("service_tender", MG1, {"organisation": f("Carga Lusa S.A.", MG1), "country": f("Mozambique", MG1), "service": f("TRUCKING", MG1),
                                         "status": f("open", MG2), "tender_ref": f("CLS-RFS-2027-1", MG1), "deadline": f("2027-02-26", MG2)},
                {"organisation": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True})],
         {"opportunities": [opp("CLS-RFS-2027-1", day="2027-02-26", precision="date", service="TRUCKING", freight_scope="cargo")]}, extra={"lang": "pt"}))

# m08 numeric date with a month-first convention established by another date in the notice
MH1 = "Example Air invites proposals from cargo GSSA providers in Belize. Tender reference EXA-GSSA-2027-21. Issued 01/15/2027."
MH2 = "Closing date: 03/04/2027 at 17:00 CST (Belize)."
add(Case("m08-month-first-convention-bz", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["BZ"]}, ["BZ"],
         ["ambiguous_dates", "date_convention", "timezone_unclear"], "html", "RFP EXA-GSSA-2027-21", f"{MH1}\n\n{MH2}",
         [claim("gssa_tender", MH1, {"airline": f("Example Air", MH1), "country": f("Belize", MH1), "service": f("GSSA", MH1), "status": f("open", MH2),
                                      "tender_ref": f("EXA-GSSA-2027-21", MH1), "deadline": f("2027-03-04T17:00:00", MH2)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("tender_deadline", MH2, {"tender_ref": f("EXA-GSSA-2027-21", MH1), "deadline": f("2027-04-03T17:00:00", MH2)}, {"tender_ref": True, "deadline": False})],
         {"opportunities": [opp("EXA-GSSA-2027-21", day="2027-03-04", precision="local_time", service="GSSA", freight_scope="cargo")]},
         notes="'01/15/2027' establishes month-first, so 03/04/2027 is 4 March. CST is not established (Belize is not in its context set): a local time."))

# m09 advisory 'preferably' and mandatory 'shall' in one sentence pair
MI1 = "Example Air invites proposals from cargo GSSA providers in Zambia. Tender reference EXA-GSSA-2027-30. Proposals are due on 20 March 2027."
MI2 = "Bidders shall hold a valid IATA cargo agent accreditation. Bidders should preferably have an office at Lusaka airport."
add(Case("m09-shall-and-preferably-zm", "heldout4", "en", "airline_representation", {"geo_mode": "country", "countries": ["ZM"]}, ["ZM"],
         ["advisory_wording", "eligibility_complex"], "html", "RFP EXA-GSSA-2027-30", f"{MI1}\n\n{MI2}",
         [claim("gssa_tender", MI1, {"airline": f("Example Air", MI1), "country": f("Zambia", MI1), "service": f("GSSA", MI1), "status": f("open", MI1),
                                      "tender_ref": f("EXA-GSSA-2027-30", MI1), "deadline": f("2027-03-20", MI1)},
                {"airline": True, "country": True, "service": True, "status": True, "tender_ref": True, "deadline": True}),
          claim("eligibility", MI2, {"tender_ref": f("EXA-GSSA-2027-30", MI1), "eligibility": f("a valid IATA cargo agent accreditation", MI2)},
                {"tender_ref": True, "eligibility": True}),
          claim("eligibility", MI2, {"tender_ref": f("EXA-GSSA-2027-30", MI1), "eligibility": f("an office at Lusaka airport", MI2)},
                {"tender_ref": True, "eligibility": True})],
         {"opportunities": [opp("EXA-GSSA-2027-30", day="2027-03-20", precision="date", service="GSSA", freight_scope="cargo")]}))

# m10 cancellation in French with "annulé" and a reserved-right sentence in the same notice
MJ1 = "Avis d'annulation : l'appel d'offres AEX-FRT-2026-8 relatif à l'assistance en escale fret à Dakar, Sénégal, est annulé."
MJ2 = "La compagnie se réserve le droit de relancer une nouvelle procédure."
add(Case("m10-fr-annule-with-reserved-right-sn", "heldout4", "fr", "outsourcing_training", {"geo_mode": "country", "countries": ["SN"]}, ["SN"],
         ["language_fr", "cancellation"], "html", "Avis d'annulation AEX-FRT-2026-8", f"{MJ1}\n\n{MJ2}",
         [claim("tender_status", MJ1, {"tender_ref": f("AEX-FRT-2026-8", MJ1), "status": f("cancelled", MJ1)}, {"tender_ref": True, "status": True}),
          claim("service_tender", MJ1, {"country": f("Senegal", MJ1), "service": f("HANDLING", MJ1), "status": f("open", MJ2), "tender_ref": f("AEX-FRT-2026-8", MJ1)},
                {"country": True, "service": True, "status": False, "tender_ref": True})],
         {"opportunities": [], "historical": [{"ref": "AEX-FRT-2026-8", "status": "cancelled"}]}, extra={"lang": "fr"},
         notes="A cancellation; the reserved right to relaunch is a possibility, not an open process."))


def heldout4_cases() -> list[Case]:
    return list(HELDOUT4)
